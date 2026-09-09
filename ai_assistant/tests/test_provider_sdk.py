"""Exercise real SDK tool boundaries, without a provider call or real credential."""

import asyncio
import importlib.util
import json
import os
import socket
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.models import BatteryState, SourceIdentity, TelemetrySnapshot
from lrrk_litewing_ai.providers import create_openai_agent
from lrrk_litewing_ai.tools import AssistantRuntime


@unittest.skipUnless(importlib.util.find_spec("agents"), "install the optional openai extra")
class SdkToolTests(unittest.TestCase):
    def setUp(self):
        # Block transport, not SDK construction, validation or tool execution.
        for target in ("connect", "connect_ex", "sendto"):
            self.enterContext(patch.object(socket.socket, target, side_effect=AssertionError("network forbidden")))
        self.enterContext(patch("socket.getaddrinfo", side_effect=AssertionError("network forbidden")))
        self.enterContext(patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-test-not-a-real-credential",
            "OPENAI_AGENTS_DISABLE_TRACING": "1",
        }))
        self.runtime = AssistantRuntime(operator_session="sdk-local-test")

    def agent(self):
        try:
            return create_openai_agent(self.runtime)
        except Exception as exc:
            self.fail(f"advisory agent construction failed: {type(exc).__name__}: {exc}")

    def invoke(self, agent, name, arguments=None):
        from agents.tool_context import ToolContext

        encoded = json.dumps(arguments or {})
        context = ToolContext(context=None, tool_name=name, tool_call_id="local-test", tool_arguments=encoded)
        tool = next(tool for tool in agent.tools if tool.name == name)
        return asyncio.run(tool.on_invoke_tool(context, encoded))

    def snapshot(self, name="first", voltage=3.9):
        return TelemetrySnapshot(
            snapshot_id=name,
            captured_at=datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
            source=SourceIdentity("sdk-test"),
            link_age_ms=20,
            armed=False,
            battery=BatteryState(voltage_v=voltage),
        )

    def test_constructs_only_strict_advisory_function_tools(self):
        from agents import FunctionTool

        agent = self.agent()
        self.assertEqual({tool.name for tool in agent.tools}, {
            "telemetry_tool", "preflight_tool", "finding_tool", "compare_tool", "proposal_tool",
        })
        self.assertEqual(len(agent.tools), 5)
        for tool in agent.tools:
            self.assertIsInstance(tool, FunctionTool)
            self.assertTrue(tool.strict_json_schema)
            self.assertFalse(tool.params_json_schema["additionalProperties"])

    def test_compare_requires_two_observed_snapshots(self):
        agent = self.agent()
        self.assertFalse(self.invoke(agent, "compare_tool")["available"])
        self.runtime.ingest(self.snapshot())
        self.assertFalse(self.invoke(agent, "compare_tool")["available"])

    def test_compare_uses_runtime_data_not_model_supplied_telemetry(self):
        agent = self.agent()
        before = self.snapshot()
        after = self.snapshot("second", voltage=3.6)
        self.runtime.ingest(before)
        self.runtime.ingest(after)
        tool = next(tool for tool in agent.tools if tool.name == "compare_tool")
        self.assertEqual(tool.params_json_schema["properties"], {})
        result = self.invoke(agent, "compare_tool", {"before": {}, "after": {"armed": True}})
        self.assertEqual(result["before_hash"], before.snapshot_hash())
        self.assertEqual(result["after_hash"], after.snapshot_hash())
        self.assertAlmostEqual(result["battery_voltage_delta_v"], -0.3)
        self.assertFalse(result["armed_changed"])
        self.assertEqual(self.runtime.latest, after)

    def test_telemetry_tool_reads_current_runtime_snapshot(self):
        agent = self.agent()
        self.assertFalse(self.invoke(agent, "telemetry_tool")["available"])
        snapshot = self.snapshot()
        self.runtime.ingest(snapshot)
        result = self.invoke(agent, "telemetry_tool")
        self.assertTrue(result["available"])
        self.assertEqual(result["snapshot_hash"], snapshot.snapshot_hash())

    def test_preflight_and_explanation_preserve_stale_capture_block(self):
        snapshot = self.snapshot()
        self.runtime.ingest(snapshot)
        agent = self.agent()
        with patch("lrrk_litewing_ai.safety._now", return_value=snapshot.captured_at + timedelta(seconds=2)):
            self.assertEqual(self.invoke(agent, "preflight_tool")["overall"], "BLOCKED")
            finding = self.invoke(agent, "finding_tool", {"finding_id": "link.freshness"})
        self.assertEqual(finding["status"], "BLOCK")

    def test_allowed_proposal_remains_unapproved_and_bound_to_snapshot(self):
        snapshot = self.snapshot()
        self.runtime.ingest(snapshot)
        result = self.invoke(self.agent(), "proposal_tool", {
            "action_kind": "review_battery", "rationale": "inspect supply",
            "expected_effect": "human review", "expiry_seconds": 60,
        })
        self.assertEqual(result["state"], "PROPOSAL_READY")
        self.assertEqual(result["proposal"]["snapshot_hash"], snapshot.snapshot_hash())
        self.assertFalse(self.runtime.approvals.approval_is_current(snapshot))

    def test_flight_actions_cannot_create_a_proposal_through_sdk(self):
        self.runtime.ingest(self.snapshot())
        agent = self.agent()
        for action in ("arm", "takeoff", "land", "write_actuators", "change_gains", "change_failsafes"):
            with self.subTest(action=action):
                result = self.invoke(agent, "proposal_tool", {
                    "action_kind": action, "rationale": "test forbidden action",
                    "expected_effect": "must not happen", "expiry_seconds": 60,
                })
                self.assertIn("outside the advisory allowlist", result)
                self.assertEqual(self.runtime.approvals.state, "IDLE")
                self.assertIsNone(self.runtime.approvals.proposal)

    def test_invalid_proposal_expiry_is_rejected_through_sdk(self):
        self.runtime.ingest(self.snapshot())
        agent = self.agent()
        for expiry in (0, 301):
            with self.subTest(expiry=expiry):
                result = self.invoke(agent, "proposal_tool", {
                    "action_kind": "review_battery", "rationale": "inspect supply",
                    "expected_effect": "human review", "expiry_seconds": expiry,
                })
                self.assertIn("expiry_seconds must be between 1 and 300", result)
                self.assertEqual(self.runtime.approvals.state, "IDLE")


if __name__ == "__main__":
    unittest.main()
