"""Offline assistant facade and explicit live-mode boundary."""

from __future__ import annotations

from typing import Any

from .providers import create_openai_agent
from .tools import AssistantRuntime, get_latest_telemetry, run_preflight_tool


class OfflineAssistant:
    def __init__(self, runtime: AssistantRuntime):
        self.runtime = runtime

    def respond(self, prompt: str) -> dict:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt is required")
        lowered = prompt.lower()
        if "preflight" in lowered or "safe" in lowered:
            return run_preflight_tool(self.runtime)
        if "telemetry" in lowered or "status" in lowered:
            return get_latest_telemetry(self.runtime)
        return {
            "mode": "offline",
            "answer": "Offline mode can inspect telemetry and run deterministic preflight checks; no model or network call was made.",
        }


def create_assistant(runtime: AssistantRuntime, live_agent: bool = False) -> Any:
    if live_agent:
        return create_openai_agent(runtime)
    return OfflineAssistant(runtime)
