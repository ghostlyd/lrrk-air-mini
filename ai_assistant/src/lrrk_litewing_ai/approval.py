"""Human-gated proposal state machine with no flight-command sink."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional

from .jsonl import canonical_json
from .models import TelemetrySnapshot
from .safety import SafetyPolicy, run_preflight


IDLE = "IDLE"
PROPOSAL_READY = "PROPOSAL_READY"
APPROVED = "APPROVED"
EXPIRED = "EXPIRED"
REJECTED = "REJECTED"
ABORTED = "ABORTED"

ALLOWED_ACTIONS = frozenset(
    {
        "inspect_telemetry",
        "run_preflight",
        "review_orientation",
        "review_battery",
        "reconnect_link",
        "open_manual",
    }
)


class ApprovalError(ValueError):
    pass


class ApprovalAuditError(RuntimeError):
    """Recording failed; this machine cannot issue further audited grants."""


class TransitionReason(str, Enum):
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    EXPLICIT_ABORT = "EXPLICIT_ABORT"
    TIMEOUT = "TIMEOUT"
    SNAPSHOT_DRIFT = "SNAPSHOT_DRIFT"
    POLICY_DRIFT = "POLICY_DRIFT"
    SAFETY_REGRESSION = "SAFETY_REGRESSION"


# Recorders must commit exactly one event on return and restore their prior
# storage state before raising. Native AuditLog.append provides this contract;
# a state machine cannot roll back an arbitrary custom callback's side effects.
TransitionRecorder = Callable[[str, Dict[str, Any]], Any]


@dataclass(frozen=True)
class ActionProposal:
    proposal_id: str
    action_kind: str
    rationale: str
    expected_effect: str
    created_at: datetime
    expires_at: datetime
    snapshot_hash: str
    operator_session: str
    policy_version: str
    policy_hash: str
    proposal_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "action_kind": self.action_kind,
            "rationale": self.rationale,
            "expected_effect": self.expected_effect,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "snapshot_hash": self.snapshot_hash,
            "operator_session": self.operator_session,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "proposal_hash": self.proposal_hash,
        }


def _canonical_proposal_fields(fields: Dict[str, Any]) -> str:
    return canonical_json(fields)


class ApprovalStateMachine:
    def __init__(
        self,
        operator_session: str,
        policy: SafetyPolicy = SafetyPolicy(),
        on_policy_change: Optional[Callable[[], None]] = None,
        transition_recorder: Optional[TransitionRecorder] = None,
    ):
        if not operator_session or not isinstance(operator_session, str):
            raise ApprovalError("operator_session must be non-empty")
        policy.validate()
        self.operator_session = operator_session
        self._policy = policy
        self._on_policy_change = on_policy_change
        self._transition_recorder = transition_recorder
        self._audit_failed = False
        self.state = IDLE
        self.proposal: Optional[ActionProposal] = None
        self._approval_digest: Optional[str] = None

    def _record_transition(
        self, from_state: str, state: str, proposal: ActionProposal, reason: TransitionReason,
    ) -> None:
        if self._audit_failed and state in (PROPOSAL_READY, APPROVED):
            raise ApprovalAuditError("advisory transition audit write failed")
        if self._transition_recorder is not None:
            try:
                self._transition_recorder("proposal_" + state.removeprefix("PROPOSAL_").lower(), {
                    "from_state": from_state,
                    "state": state,
                    "reason_code": reason.value,
                    "proposal_id": proposal.proposal_id,
                    "proposal_hash": proposal.proposal_hash,
                    "snapshot_hash": proposal.snapshot_hash,
                    "policy_version": proposal.policy_version,
                    "policy_hash": proposal.policy_hash,
                    "action_kind": proposal.action_kind,
                })
            except Exception:
                # Block future grants permanently, but allow a distinct terminal
                # transition to attempt recording. Never expose backend content.
                self._audit_failed = True
                raise ApprovalAuditError("advisory transition audit write failed") from None

    def _transition(
        self, state: str, reason: TransitionReason, proposal: Optional[ActionProposal] = None,
    ) -> None:
        allowed = {
            IDLE: (PROPOSAL_READY,),
            PROPOSAL_READY: (APPROVED, REJECTED, EXPIRED, ABORTED),
            APPROVED: (EXPIRED, ABORTED),
            REJECTED: (PROPOSAL_READY,),
            EXPIRED: (PROPOSAL_READY,),
            ABORTED: (PROPOSAL_READY,),
        }
        if state not in allowed[self.state]:
            raise ApprovalError("illegal proposal state transition")
        bound = proposal if proposal is not None else self.proposal
        if bound is None:
            raise ApprovalError("no active proposal")
        from_state = self.state
        terminal = state in (REJECTED, EXPIRED, ABORTED)
        if terminal:
            # Safety invalidation must survive a recorder failure.
            self.state = state
            self._approval_digest = None
        self._record_transition(from_state, state, bound, reason)
        if not terminal:
            self.proposal = bound
            self.state = state
            self._approval_digest = None

    def invalidate_for_snapshot(self, current_snapshot: TelemetrySnapshot) -> bool:
        if (self.state in (PROPOSAL_READY, APPROVED) and self.proposal is not None
                and current_snapshot.snapshot_hash() != self.proposal.snapshot_hash):
            self._transition(ABORTED, TransitionReason.SNAPSHOT_DRIFT)
            return True
        return False

    @property
    def policy(self) -> SafetyPolicy:
        return self._policy

    @policy.setter
    def policy(self, policy: SafetyPolicy) -> None:
        policy.validate()
        self._policy = policy
        try:
            self._policy_is_current()
        finally:
            if self._on_policy_change is not None:
                self._on_policy_change()

    def _policy_is_current(self) -> bool:
        if self.state in (PROPOSAL_READY, APPROVED) and self.proposal is not None:
            if (self.policy.policy_version != self.proposal.policy_version
                    or self.policy.policy_hash() != self.proposal.policy_hash):
                self._transition(ABORTED, TransitionReason.POLICY_DRIFT)
                return False
        return True

    def create_proposal(
        self,
        snapshot: TelemetrySnapshot,
        action_kind: str,
        rationale: str,
        expected_effect: str,
        expiry_seconds: int = 60,
        now: Optional[datetime] = None,
    ) -> ActionProposal:
        if self.state not in (IDLE, REJECTED, EXPIRED, ABORTED):
            raise ApprovalError("a proposal is already active")
        if action_kind not in ALLOWED_ACTIONS:
            raise ApprovalError("action kind is outside the advisory allowlist")
        if not rationale or not expected_effect:
            raise ApprovalError("rationale and expected_effect are required")
        if not isinstance(expiry_seconds, int) or not 1 <= expiry_seconds <= 300:
            raise ApprovalError("expiry_seconds must be between 1 and 300")
        created_at = now or datetime.now(timezone.utc)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ApprovalError("now must be timezone-aware")
        expires_at = created_at + timedelta(seconds=expiry_seconds)
        fields = {
            "proposal_id": str(uuid.uuid4()),
            "action_kind": action_kind,
            "rationale": rationale,
            "expected_effect": expected_effect,
            "created_at": created_at,
            "expires_at": expires_at,
            "snapshot_hash": snapshot.snapshot_hash(),
            "operator_session": self.operator_session,
            "policy_version": self.policy.policy_version,
            "policy_hash": self.policy.policy_hash(),
        }
        hash_fields = dict(fields)
        hash_fields["created_at"] = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        hash_fields["expires_at"] = expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        proposal_hash = hashlib.sha256(_canonical_proposal_fields(hash_fields).encode("utf-8")).hexdigest()
        proposal = ActionProposal(proposal_hash=proposal_hash, **fields)
        self._transition(PROPOSAL_READY, TransitionReason.PROPOSAL_CREATED, proposal)
        return proposal

    def approve(
        self,
        proposal_id: str,
        human_approval_token: str,
        current_snapshot: TelemetrySnapshot,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if not self._policy_is_current():
            raise ApprovalError("safety policy changed after proposal creation")
        if self.state != PROPOSAL_READY or self.proposal is None:
            raise ApprovalError("no proposal is waiting for approval")
        if proposal_id != self.proposal.proposal_id:
            raise ApprovalError("proposal identity mismatch")
        if not human_approval_token or not isinstance(human_approval_token, str):
            raise ApprovalError("a human approval token is required")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ApprovalError("now must be timezone-aware")
        if current >= self.proposal.expires_at:
            self._transition(EXPIRED, TransitionReason.TIMEOUT)
            raise ApprovalError("proposal has expired")
        if self.invalidate_for_snapshot(current_snapshot):
            raise ApprovalError("telemetry changed after proposal creation")
        report = run_preflight(current_snapshot, policy=self.policy, now=current)
        if report.overall in ("BLOCKED", "INCOMPLETE"):
            self._transition(ABORTED, TransitionReason.SAFETY_REGRESSION)
            raise ApprovalError("current safety report is not complete and clear")
        approval_digest = hashlib.sha256(human_approval_token.encode("utf-8")).hexdigest()
        self._transition(APPROVED, TransitionReason.HUMAN_APPROVED)
        self._approval_digest = approval_digest
        return {
            "state": self.state,
            "proposal_id": proposal_id,
            "proposal_hash": self.proposal.proposal_hash,
            "policy_version": self.proposal.policy_version,
            "policy_hash": self.proposal.policy_hash,
            "approved_at": current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "approval_token_hash": self._approval_digest,
        }

    def reject(self, proposal_id: str, reason: str) -> None:
        if self.state != PROPOSAL_READY or self.proposal is None or proposal_id != self.proposal.proposal_id:
            raise ApprovalError("proposal identity or state mismatch")
        if not reason:
            raise ApprovalError("rejection reason is required")
        self._transition(REJECTED, TransitionReason.HUMAN_REJECTED)

    def abort(self, reason: str) -> None:
        if self.state not in (PROPOSAL_READY, APPROVED):
            raise ApprovalError("no active proposal to abort")
        if not reason:
            raise ApprovalError("abort reason is required")
        self._transition(ABORTED, TransitionReason.EXPLICIT_ABORT)

    def expire(self, now: Optional[datetime] = None) -> bool:
        if self.state != PROPOSAL_READY or self.proposal is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ApprovalError("now must be timezone-aware")
        if current >= self.proposal.expires_at:
            self._transition(EXPIRED, TransitionReason.TIMEOUT)
            return True
        return False

    def approval_is_current(self, current_snapshot: TelemetrySnapshot, now: Optional[datetime] = None) -> bool:
        if not self._policy_is_current():
            return False
        if self.state != APPROVED or self.proposal is None or self._approval_digest is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current >= self.proposal.expires_at:
            self._transition(EXPIRED, TransitionReason.TIMEOUT)
            return False
        if self.invalidate_for_snapshot(current_snapshot):
            return False
        # The snapshot can expire without its bytes/hash changing.
        if run_preflight(current_snapshot, policy=self.policy, now=current).overall != "PASS":
            self._transition(ABORTED, TransitionReason.SAFETY_REGRESSION)
            return False
        return True
