"""Advisory lifecycle evidence using the real native audit file and replay."""

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import AuditLog, validate_replay
from lrrk_litewing_ai.approval import ApprovalError, ApprovalStateMachine
from lrrk_litewing_ai.cli import main
from lrrk_litewing_ai.safety import SafetyPolicy
from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot
from lrrk_litewing_ai.tools import AssistantRuntime, propose_action, run_preflight_tool


PRIVATE = "private-prose-7d91"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
TOKEN = "synthetic-human-confirmation-f20a"
ERROR = "private-storage-error-e82c"
PAYLOAD_KEYS = {
    "from_state", "state", "reason_code", "proposal_id", "proposal_hash",
    "snapshot_hash", "policy_version", "policy_hash", "action_kind",
}


def snapshot(snapshot_id="approval-1", complete=True):
    return TelemetrySnapshot(
        snapshot_id=snapshot_id, captured_at=NOW, source=SourceIdentity("test"),
        link_age_ms=20, armed=False, flight_mode="attitude",
        battery=BatteryState(voltage_v=3.9, percent=80),
        sensors=SensorHealth(True, "MPU6050", True) if complete else SensorHealth(),
        actuators=(0, 0, 0, 0), alarms=(),
    )


class TransitionAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.directory / "audit.jsonl"
        self.log = AuditLog(self.path, "audit-session")

    def ready(self, log=None, state=None):
        runtime = AssistantRuntime(audit=log or self.log, latest=state or snapshot())
        proposal = runtime.approvals.create_proposal(
            runtime.latest, "inspect_telemetry", PRIVATE, PRIVATE, now=NOW,
        )
        return runtime, proposal

    def approve(self, runtime, proposal):
        return runtime.approvals.approve(proposal.proposal_id, TOKEN, runtime.latest, now=NOW)

    def assert_write_failure(self, operation):
        try:
            operation()
        except Exception as error:
            self.assertIsInstance(error, RuntimeError)
            self.assertEqual(str(error), "advisory transition audit write failed")
            self.assertNotIn(ERROR, str(error))
        else:
            self.fail("audit write failure did not surface")

    def transitions(self):
        return [(r["payload"]["from_state"], r["payload"]["state"],
                 r["payload"]["reason_code"]) for r in validate_replay(self.path)]

    def test_tool_proposal_is_recorded_before_return(self):
        try:
            runtime = AssistantRuntime(audit=self.log, latest=snapshot())
        except TypeError as error:
            self.fail("runtime has no optional audit attachment: %s" % error)
        result = propose_action(runtime, "inspect_telemetry", "private rationale", "private effect")
        records = validate_replay(self.path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_type"], "proposal_ready")
        self.assertEqual(records[0]["payload"], {
            "from_state": "IDLE", "state": "PROPOSAL_READY",
            "reason_code": "PROPOSAL_CREATED", "action_kind": "inspect_telemetry",
            **{key: result["proposal"][key] for key in (
                "proposal_id", "proposal_hash", "snapshot_hash", "policy_version", "policy_hash",
            )},
        })
        self.assertEqual(records[0]["source"], {})

    def test_alternating_independent_logs_refresh_chain_head(self):
        second = AuditLog(self.path, "audit-session")
        self.log.append("preflight_result", {"overall": "PASS"})
        second.append("preflight_result", {"overall": "BLOCKED"})
        self.log.append("preflight_result", {"overall": "INCOMPLETE"})
        try:
            records = validate_replay(self.path)
        except ValueError as error:
            self.fail("independent sequential writers broke replay: %s" % error)
        self.assertEqual([r["payload"]["overall"] for r in records], [
            "PASS", "BLOCKED", "INCOMPLETE",
        ])

    def test_all_terminal_paths_record_exactly_once(self):
        cases = (
            ("reject", False, "REJECTED", "HUMAN_REJECTED"),
            ("abort", False, "ABORTED", "EXPLICIT_ABORT"),
            ("abort", True, "ABORTED", "EXPLICIT_ABORT"),
            ("expire", False, "EXPIRED", "TIMEOUT"),
            ("timeout", False, "EXPIRED", "TIMEOUT"),
            ("timeout", True, "EXPIRED", "TIMEOUT"),
            ("snapshot", False, "ABORTED", "SNAPSHOT_DRIFT"),
            ("snapshot", True, "ABORTED", "SNAPSHOT_DRIFT"),
            ("stale", False, "ABORTED", "SAFETY_REGRESSION"),
            ("stale", True, "ABORTED", "SAFETY_REGRESSION"),
            ("incomplete", False, "ABORTED", "SAFETY_REGRESSION"),
            ("blocked", False, "ABORTED", "SAFETY_REGRESSION"),
        )
        for index, (route, approved, target, reason) in enumerate(cases):
            with self.subTest(route=route, approved=approved):
                self.path = self.directory / ("case-%d.jsonl" % index)
                self.log = AuditLog(self.path, "audit-session")
                state = snapshot(complete=route != "incomplete")
                if route == "blocked":
                    state = replace(state, armed=True)
                runtime, proposal = self.ready(state=state)
                machine = runtime.approvals
                if approved:
                    self.approve(runtime, proposal)
                if route == "reject":
                    machine.reject(proposal.proposal_id, PRIVATE)
                elif route == "abort":
                    machine.abort(PRIVATE)
                elif route == "expire":
                    self.assertTrue(machine.expire(now=NOW + timedelta(seconds=60)))
                else:
                    current = snapshot("changed") if route == "snapshot" else state
                    time = NOW + timedelta(seconds=60 if route == "timeout" else 1 if route == "stale" else 0)
                    if approved:
                        self.assertFalse(machine.approval_is_current(current, now=time))
                    else:
                        with self.assertRaises(ApprovalError):
                            machine.approve(proposal.proposal_id, TOKEN, current, now=time)
                expected = [("IDLE", "PROPOSAL_READY", "PROPOSAL_CREATED")]
                if approved:
                    expected.append(("PROPOSAL_READY", "APPROVED", "HUMAN_APPROVED"))
                expected.append(("APPROVED" if approved else "PROPOSAL_READY", target, reason))
                self.assertEqual(self.transitions(), expected)
                self.assertIsNone(machine._approval_digest)
                before = self.path.read_bytes()
                self.assertFalse(machine.expire(now=NOW + timedelta(seconds=60)))
                self.assertFalse(machine.approval_is_current(state, now=NOW))
                with self.assertRaises(ApprovalError):
                    machine.approve(proposal.proposal_id, TOKEN, state, now=NOW)
                with self.assertRaises(ApprovalError):
                    machine.abort(PRIVATE)
                self.assertEqual(self.path.read_bytes(), before)

    def test_policy_and_ingestion_drift_record_bound_identity(self):
        for route in ("runtime_policy", "machine_policy", "ingest", "analyzer_approve", "analyzer_current"):
            for approved in (False, True):
                with self.subTest(route=route, approved=approved):
                    runtime, proposal = self.ready()
                    if approved:
                        self.approve(runtime, proposal)
                    if route == "runtime_policy":
                        runtime.policy = SafetyPolicy(min_battery_voltage_v=4.1)
                    elif route == "machine_policy":
                        runtime.approvals.policy = SafetyPolicy(min_battery_voltage_v=4.1)
                    elif route == "ingest":
                        runtime.ingest(snapshot("changed"))
                    else:
                        with patch("lrrk_litewing_ai.safety.ANALYZER_VERSION", "next-analyzer"):
                            if route == "analyzer_approve":
                                with self.assertRaises(ApprovalError):
                                    self.approve(runtime, proposal)
                            else:
                                self.assertFalse(runtime.approvals.approval_is_current(runtime.latest, now=NOW))
                    event = validate_replay(self.path)[-1]
                    self.assertEqual(event["event_type"], "proposal_aborted")
                    self.assertEqual(event["payload"], {
                        "from_state": "APPROVED" if approved else "PROPOSAL_READY",
                        "state": "ABORTED", "action_kind": "inspect_telemetry",
                        "reason_code": "SNAPSHOT_DRIFT" if route == "ingest" else "POLICY_DRIFT",
                        **{key: getattr(proposal, key) for key in (
                            "proposal_id", "proposal_hash", "snapshot_hash", "policy_version", "policy_hash",
                        )},
                    })

    def test_rejected_calls_and_unchanged_observations_add_no_event(self):
        runtime, proposal = self.ready()
        machine = runtime.approvals
        before = self.path.read_bytes()
        for operation in (
            lambda: machine.create_proposal(snapshot(), "inspect_telemetry", PRIVATE, PRIVATE, now=NOW),
            lambda: machine.approve("wrong-id", TOKEN, snapshot(), now=NOW),
            lambda: machine.approve(proposal.proposal_id, "", snapshot(), now=NOW),
            lambda: machine.reject("wrong-id", PRIVATE),
            lambda: machine.reject(proposal.proposal_id, ""),
            lambda: machine.abort(""),
        ):
            with self.assertRaises(ApprovalError):
                operation()
        runtime.ingest(snapshot())
        runtime.policy = SafetyPolicy()
        self.assertFalse(machine.expire(now=NOW))
        self.assertFalse(machine.approval_is_current(snapshot(), now=NOW))
        self.assertEqual(self.path.read_bytes(), before)
        self.approve(runtime, proposal)
        self.assertEqual(len(validate_replay(self.path)), 2)
        before = self.path.read_bytes()
        with self.assertRaises(ApprovalError):
            self.approve(runtime, proposal)
        self.assertTrue(machine.approval_is_current(snapshot(), now=NOW))
        self.assertEqual(self.path.read_bytes(), before)

    def test_terminal_abort_is_illegal_even_without_a_recorder(self):
        for terminal in ("reject", "expire", "abort"):
            with self.subTest(terminal=terminal):
                machine = ApprovalStateMachine("offline-session")
                proposal = machine.create_proposal(snapshot(), "inspect_telemetry", PRIVATE, PRIVATE, now=NOW)
                if terminal == "reject":
                    machine.reject(proposal.proposal_id, PRIVATE)
                elif terminal == "expire":
                    machine.expire(now=NOW + timedelta(seconds=60))
                else:
                    machine.abort(PRIVATE)
                before = machine.state
                with self.assertRaises(ApprovalError):
                    machine.abort(PRIVATE)
                self.assertEqual(machine.state, before)

    def test_shared_and_independent_logs_preserve_interleaved_machine_order(self):
        for log in (self.log, AuditLog(self.path, "audit-session")):
            first, one = self.ready()
            second, two = self.ready(log=log)
            self.approve(second, two)
            first.approvals.reject(one.proposal_id, PRIVATE)
            second.approvals.abort(PRIVATE)
            replacement = first.approvals.create_proposal(snapshot(), "open_manual", PRIVATE, PRIVATE, now=NOW)
            first.approvals.expire(now=NOW + timedelta(seconds=60))
            rows = validate_replay(self.path)[-7:]
            self.assertEqual([r["event_type"] for r in rows], [
                "proposal_ready", "proposal_ready", "proposal_approved", "proposal_rejected",
                "proposal_aborted", "proposal_ready", "proposal_expired",
            ])
            self.assertEqual([r["payload"]["proposal_id"] for r in rows], [
                one.proposal_id, two.proposal_id, two.proposal_id, one.proposal_id,
                two.proposal_id, replacement.proposal_id, replacement.proposal_id,
            ])
            self.assertEqual(rows[5]["payload"]["from_state"], "REJECTED")
        self.assertEqual(len(validate_replay(self.path)), 14)

    def test_metadata_key_sets_exclude_prose_tokens_and_raw_observations(self):
        state = replace(snapshot(PRIVATE), source=replace(snapshot().source, board=PRIVATE))
        runtime = AssistantRuntime(audit=self.log, latest=state, operator_session=PRIVATE)
        for terminal in ("reject", "abort", "expire"):
            proposal = runtime.approvals.create_proposal(state, "open_manual", PRIVATE, PRIVATE, now=NOW)
            if terminal == "reject":
                runtime.approvals.reject(proposal.proposal_id, PRIVATE)
            elif terminal == "abort":
                self.approve(runtime, proposal)
                runtime.approvals.abort(PRIVATE)
            else:
                runtime.approvals.expire(now=NOW + timedelta(seconds=60))
        records = validate_replay(self.path)
        self.assertEqual(len(records), 7)
        for record in records:
            self.assertEqual(set(record), {
                "event_id", "event_type", "event_at", "session_id", "source", "payload", "prev_hash", "event_hash",
            })
            self.assertEqual(set(record["payload"]), PAYLOAD_KEYS)
            self.assertEqual(record["source"], {})
            self.assertEqual(record["session_id"], "audit-session")
        raw = self.path.read_text()
        for forbidden in (PRIVATE, TOKEN, ERROR, hashlib.sha256(TOKEN.encode()).hexdigest(),
                          '"rationale"', '"expected_effect"', '"reason"', '"approval_token_hash"',
                          '"snapshot"', '"prompt"', '"response"', '"error_class"', '"environment"',
                          '"serial"', '"reasoning"', '"credentials"'):
            self.assertNotIn(forbidden, raw)

    def test_no_recorder_preserves_library_use_without_creating_a_file(self):
        with contextlib.chdir(self.directory):
            runtime = AssistantRuntime(latest=snapshot())
            result = propose_action(runtime, "open_manual", PRIVATE, PRIVATE)
            runtime.approvals.approve(result["proposal"]["proposal_id"], TOKEN, snapshot(), now=NOW)
            runtime.approvals.abort(PRIVATE)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_proposal_write_failure_does_not_install_proposal(self):
        runtime = AssistantRuntime(audit=self.log, latest=snapshot())
        with patch("lrrk_litewing_ai.audit.append_record", side_effect=OSError(ERROR)):
            self.assert_write_failure(lambda: propose_action(runtime, "open_manual", PRIVATE, PRIVATE))
        self.assertEqual(runtime.approvals.state, "IDLE")
        self.assertIsNone(runtime.approvals.proposal)
        self.assertIsNone(runtime.approvals._approval_digest)
        self.assertFalse(self.path.exists())

    def test_approval_write_failure_does_not_grant_approval(self):
        runtime, proposal = self.ready()
        before = self.path.read_bytes()
        with patch("lrrk_litewing_ai.audit.append_record", side_effect=OSError(ERROR)):
            self.assert_write_failure(lambda: self.approve(runtime, proposal))
        self.assertEqual(runtime.approvals.state, "PROPOSAL_READY")
        self.assertIsNone(runtime.approvals._approval_digest)
        self.assertFalse(runtime.approvals.approval_is_current(snapshot(), now=NOW))
        self.assertEqual(self.path.read_bytes(), before)

    def test_safety_write_failures_still_invalidate_and_update_runtime(self):
        for route in ("abort", "reject", "expire", "timeout", "snapshot", "stale", "policy", "ingest"):
            for approved in (False, True):
                if approved and route in ("reject", "expire"):
                    continue
                with self.subTest(route=route, approved=approved):
                    runtime, proposal = self.ready()
                    machine = runtime.approvals
                    if approved:
                        self.approve(runtime, proposal)
                    with patch("lrrk_litewing_ai.safety._now", return_value=NOW):
                        run_preflight_tool(runtime)
                    changed = snapshot("changed")
                    def invalidate():
                        if route == "abort":
                            machine.abort(PRIVATE)
                        elif route == "reject":
                            machine.reject(proposal.proposal_id, PRIVATE)
                        elif route == "expire":
                            machine.expire(now=NOW + timedelta(seconds=60))
                        elif route == "policy":
                            machine.policy = SafetyPolicy(min_battery_voltage_v=4.1)
                        elif route == "ingest":
                            runtime.ingest(changed)
                        else:
                            current = changed if route == "snapshot" else snapshot()
                            time = NOW + timedelta(seconds=60 if route == "timeout" else 1 if route == "stale" else 0)
                            if approved:
                                machine.approval_is_current(current, now=time)
                            else:
                                machine.approve(proposal.proposal_id, TOKEN, current, now=time)
                    before = self.path.read_bytes()
                    with patch("lrrk_litewing_ai.audit.append_record", side_effect=OSError(ERROR)):
                        self.assert_write_failure(invalidate)
                    self.assertEqual(machine.state, "REJECTED" if route == "reject" else
                                     "EXPIRED" if route in ("expire", "timeout") else "ABORTED")
                    self.assertIsNone(machine._approval_digest)
                    self.assertEqual(self.path.read_bytes(), before)
                    if route in ("policy", "ingest"):
                        self.assertIsNone(runtime.last_report)
                    if route == "ingest":
                        self.assertEqual(runtime.latest, changed)
                        self.assertEqual(runtime.previous, snapshot())

    def test_ambiguous_write_failure_cannot_retry_a_success_transition(self):
        from lrrk_litewing_ai.jsonl import append_record
        for target in ("proposal", "approval"):
            with self.subTest(target=target):
                runtime = AssistantRuntime(audit=self.log, latest=snapshot())
                if target == "approval":
                    proposal = runtime.approvals.create_proposal(snapshot(), "open_manual", PRIVATE, PRIVATE, now=NOW)
                    operation = lambda: self.approve(runtime, proposal)
                else:
                    operation = lambda: propose_action(runtime, "open_manual", PRIVATE, PRIVATE)
                def ambiguous_write(path, record):
                    append_record(path, record)
                    raise OSError(ERROR)
                with patch("lrrk_litewing_ai.audit.append_record", new=ambiguous_write):
                    self.assert_write_failure(operation)
                before = self.path.read_bytes()
                self.assert_write_failure(operation)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertNotEqual(runtime.approvals.state, "APPROVED")
                self.assertIsNone(runtime.approvals._approval_digest)
                validate_replay(self.path)

    def test_cli_attaches_audit_to_real_advisory_tool_path(self):
        # Substitute only the offline text facade; execute the real proposal tool.
        def respond(assistant, prompt):
            return propose_action(assistant.runtime, "open_manual", PRIVATE, PRIVATE)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("lrrk_litewing_ai.agent.OfflineAssistant.respond", new=respond), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["--input", str(Path(__file__).parent / "fixtures/telemetry.jsonl"),
                           "--audit-log", str(self.path), "--prompt", "manual", "--json"])
        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual([r["event_type"] for r in validate_replay(self.path)], [
            "snapshot_received", "preflight_result", "proposal_ready",
        ])

    def test_unencodable_token_adds_no_approval_event_or_state(self):
        runtime, proposal = self.ready()
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            runtime.approvals.approve(proposal.proposal_id, TOKEN + "\ud800", snapshot(), now=NOW)
        self.assertEqual(runtime.approvals.state, "PROPOSAL_READY")
        self.assertIsNone(runtime.approvals._approval_digest)
        self.assertEqual(self.path.read_bytes(), before)

    def test_policy_callback_failure_cannot_prevent_invalidation(self):
        def broken_callback():
            raise RuntimeError("callback failed")
        machine = ApprovalStateMachine("operator", on_policy_change=broken_callback,
                                       transition_recorder=self.log.append)
        proposal = machine.create_proposal(snapshot(), "open_manual", PRIVATE, PRIVATE, now=NOW)
        machine.approve(proposal.proposal_id, TOKEN, snapshot(), now=NOW)
        with self.assertRaisesRegex(RuntimeError, "callback failed"):
            machine.policy = SafetyPolicy(min_battery_voltage_v=4.1)
        self.assertEqual(machine.state, "ABORTED")
        self.assertIsNone(machine._approval_digest)
        self.assertEqual(self.transitions()[-1], ("APPROVED", "ABORTED", "POLICY_DRIFT"))


if __name__ == "__main__":
    unittest.main()
