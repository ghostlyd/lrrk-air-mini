"""Narrow, read-only assistant tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .approval import ApprovalStateMachine
from .models import TelemetrySnapshot
from .safety import PreflightReport, SafetyPolicy, run_preflight


TOOL_SCHEMAS = (
    {
        "name": "get_latest_telemetry",
        "description": "Read the latest normalized LiteWing telemetry snapshot.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_preflight",
        "description": "Run deterministic, fail-closed preflight checks on the latest snapshot.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "explain_finding",
        "description": "Explain one deterministic safety finding and its remediation.",
        "parameters": {
            "type": "object",
            "properties": {"finding_id": {"type": "string"}},
            "required": ["finding_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_snapshots",
        "description": "Compare the previous and latest observed runtime snapshots without changing flight state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "propose_action",
        "description": "Create a bounded advisory proposal for explicit human review; never execute it.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_kind": {"type": "string"},
                "rationale": {"type": "string"},
                "expected_effect": {"type": "string"},
                "expiry_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
            },
            "required": ["action_kind", "rationale", "expected_effect"],
            "additionalProperties": False,
        },
    },
)


@dataclass
class AssistantRuntime:
    policy: SafetyPolicy = field(default_factory=SafetyPolicy)
    operator_session: str = "offline-session"
    latest: Optional[TelemetrySnapshot] = None
    previous: Optional[TelemetrySnapshot] = None
    last_report: Optional[PreflightReport] = None
    approvals: ApprovalStateMachine = field(init=False)

    def __post_init__(self) -> None:
        self.approvals = ApprovalStateMachine(self.operator_session)

    def ingest(self, snapshot: TelemetrySnapshot) -> None:
        self.previous = self.latest
        self.latest = snapshot
        self.last_report = None


def get_latest_telemetry(runtime: AssistantRuntime) -> Dict[str, Any]:
    if runtime.latest is None:
        return {"available": False, "reason": "no telemetry snapshot is loaded"}
    return {
        "available": True,
        "snapshot_hash": runtime.latest.snapshot_hash(),
        "snapshot": runtime.latest.to_dict(),
    }


def run_preflight_tool(runtime: AssistantRuntime) -> Dict[str, Any]:
    if runtime.latest is None:
        return {"available": False, "overall": "INCOMPLETE", "reason": "no telemetry snapshot is loaded"}
    runtime.last_report = run_preflight(runtime.latest, policy=runtime.policy)
    return runtime.last_report.to_dict()


def explain_finding(runtime: AssistantRuntime, finding_id: str) -> Dict[str, Any]:
    if not isinstance(finding_id, str) or not finding_id:
        raise ValueError("finding_id is required")
    if runtime.latest is None:
        raise ValueError("a current telemetry snapshot is required")
    # Time-sensitive findings can expire without a new snapshot arriving.
    # Explain a fresh analysis, never a cached PASS from an earlier check.
    run_preflight_tool(runtime)
    assert runtime.last_report is not None
    for finding in runtime.last_report.findings:
        if finding.finding_id == finding_id:
            return finding.to_dict()
    raise ValueError("finding does not exist in the current report")


def compare_snapshots(before: TelemetrySnapshot, after: TelemetrySnapshot) -> Dict[str, Any]:
    def delta(first: Optional[float], second: Optional[float]) -> Optional[float]:
        if first is None or second is None:
            return None
        return second - first

    return {
        "before_hash": before.snapshot_hash(),
        "after_hash": after.snapshot_hash(),
        "link_age_delta_ms": delta(before.link_age_ms, after.link_age_ms),
        "battery_voltage_delta_v": delta(before.battery.voltage_v, after.battery.voltage_v),
        "armed_changed": None if before.armed is None or after.armed is None else before.armed != after.armed,
        "actuator_deltas": [delta(first, second) for first, second in zip(before.actuators, after.actuators)],
    }


def propose_action(
    runtime: AssistantRuntime,
    action_kind: str,
    rationale: str,
    expected_effect: str,
    expiry_seconds: int = 60,
) -> Dict[str, Any]:
    if runtime.latest is None:
        raise ValueError("a current telemetry snapshot is required")
    proposal = runtime.approvals.create_proposal(
        snapshot=runtime.latest,
        action_kind=action_kind,
        rationale=rationale,
        expected_effect=expected_effect,
        expiry_seconds=expiry_seconds,
    )
    return {"state": runtime.approvals.state, "proposal": proposal.to_dict()}
