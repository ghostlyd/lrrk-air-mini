"""Optional live OpenAI provider; imports and credentials stay out of offline mode."""

from __future__ import annotations

import os
from typing import Any

from .tools import AssistantRuntime, compare_snapshots, explain_finding, get_latest_telemetry, propose_action, run_preflight_tool


class LiveProviderUnavailable(RuntimeError):
    pass


def create_openai_agent(runtime: AssistantRuntime) -> Any:
    """Create a read-only Agents SDK agent when explicitly requested.

    The SDK reads the process environment. This function never writes a key,
    sends it to the aircraft, or includes it in an exception.
    """

    key = os.environ.get("OPENAI_API_KEY")
    if not key or not isinstance(key, str) or len(key) < 12 or not key.startswith("sk-"):
        raise LiveProviderUnavailable("OPENAI_API_KEY is not available for live-agent mode")
    try:
        from agents import Agent, function_tool
    except ImportError as exc:
        raise LiveProviderUnavailable("optional openai-agents dependency is not installed") from exc

    @function_tool
    def telemetry_tool() -> dict:
        return get_latest_telemetry(runtime)

    @function_tool
    def preflight_tool() -> dict:
        return run_preflight_tool(runtime)

    @function_tool
    def finding_tool(finding_id: str) -> dict:
        return explain_finding(runtime, finding_id)

    @function_tool
    def compare_tool() -> dict:
        """Compare the runtime's previous and latest observed snapshots; never supply telemetry."""
        if runtime.previous is None or runtime.latest is None:
            return {"available": False, "reason": "two observed telemetry snapshots are required"}
        return compare_snapshots(runtime.previous, runtime.latest)

    @function_tool
    def proposal_tool(action_kind: str, rationale: str, expected_effect: str, expiry_seconds: int = 60) -> dict:
        return propose_action(runtime, action_kind, rationale, expected_effect, expiry_seconds)

    return Agent(
        name="LiteWing advisory assistant",
        instructions=(
            "You are advisory only. Use deterministic preflight results as authoritative. "
            "Never invent unknown telemetry. You may inspect data, explain findings, compare "
            "snapshots, and create bounded proposals for a human. You cannot arm, take off, "
            "land, tune, change failsafes, write actuators, or execute any flight action."
        ),
        tools=[telemetry_tool, preflight_tool, finding_tool, compare_tool, proposal_tool],
    )
