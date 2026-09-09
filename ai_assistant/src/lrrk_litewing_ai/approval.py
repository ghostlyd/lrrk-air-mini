"""Human-gated proposal state machine with no flight-command sink."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .jsonl import canonical_json
from .models import TelemetrySnapshot
from .safety import run_preflight


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
            "proposal_hash": self.proposal_hash,
        }


def _canonical_proposal_fields(fields: Dict[str, Any]) -> str:
    return canonical_json(fields)


class ApprovalStateMachine:
    def __init__(self, operator_session: str):
        if not operator_session or not isinstance(operator_session, str):
            raise ApprovalError("operator_session must be non-empty")
        self.operator_session = operator_session
        self.state = IDLE
        self.proposal: Optional[ActionProposal] = None
        self._approval_digest: Optional[str] = None

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
        }
        hash_fields = dict(fields)
        hash_fields["created_at"] = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        hash_fields["expires_at"] = expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        proposal_hash = hashlib.sha256(_canonical_proposal_fields(hash_fields).encode("utf-8")).hexdigest()
        self.proposal = ActionProposal(proposal_hash=proposal_hash, **fields)
        self.state = PROPOSAL_READY
        self._approval_digest = None
        return self.proposal

    def approve(
        self,
        proposal_id: str,
        human_approval_token: str,
        current_snapshot: TelemetrySnapshot,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
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
            self.state = EXPIRED
            raise ApprovalError("proposal has expired")
        if current_snapshot.snapshot_hash() != self.proposal.snapshot_hash:
            self.state = ABORTED
            raise ApprovalError("telemetry changed after proposal creation")
        report = run_preflight(current_snapshot, now=current)
        if report.overall in ("BLOCKED", "INCOMPLETE"):
            self.state = ABORTED
            raise ApprovalError("current safety report is not complete and clear")
        self._approval_digest = hashlib.sha256(human_approval_token.encode("utf-8")).hexdigest()
        self.state = APPROVED
        return {
            "state": self.state,
            "proposal_id": proposal_id,
            "proposal_hash": self.proposal.proposal_hash,
            "approved_at": current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "approval_token_hash": self._approval_digest,
        }

    def reject(self, proposal_id: str, reason: str) -> None:
        if self.state != PROPOSAL_READY or self.proposal is None or proposal_id != self.proposal.proposal_id:
            raise ApprovalError("proposal identity or state mismatch")
        if not reason:
            raise ApprovalError("rejection reason is required")
        self.state = REJECTED

    def abort(self, reason: str) -> None:
        if self.state == IDLE:
            raise ApprovalError("no active proposal to abort")
        if not reason:
            raise ApprovalError("abort reason is required")
        self.state = ABORTED
        self._approval_digest = None

    def expire(self, now: Optional[datetime] = None) -> bool:
        if self.state != PROPOSAL_READY or self.proposal is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ApprovalError("now must be timezone-aware")
        if current >= self.proposal.expires_at:
            self.state = EXPIRED
            return True
        return False

    def approval_is_current(self, current_snapshot: TelemetrySnapshot, now: Optional[datetime] = None) -> bool:
        if self.state != APPROVED or self.proposal is None or self._approval_digest is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current >= self.proposal.expires_at:
            self.state = EXPIRED
            self._approval_digest = None
            return False
        if current_snapshot.snapshot_hash() != self.proposal.snapshot_hash:
            self.state = ABORTED
            self._approval_digest = None
            return False
        # The snapshot can expire without its bytes/hash changing.
        if run_preflight(current_snapshot, now=current).overall != "PASS":
            self.state = ABORTED
            self._approval_digest = None
            return False
        return True
