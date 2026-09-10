# OpenAI provider smoke verification

Date: 2026-09-09 (America/Los_Angeles)

## Result

A bounded, explicitly authorized provider call completed successfully through
the pinned `openai-agents==0.22.1` integration. The input was the repository's
synthetic JSONL telemetry fixture, not a private board capture. Tracing was
disabled. No flight action or proposal execution tool was available.

The prompt required the deterministic preflight tool and one concise advisory
sentence. The provider returned:

> Overall result: **BLOCKED**; highest-priority reason: **telemetry link
> freshness is critical—the link is 143,292,622.1 ms old, exceeding the 500 ms
> limit.**

The process exited 0. This proves the approved host credential and provider SDK
could complete that one fixture-backed advisory request at that time. It does
not prove live-aircraft telemetry, current credential validity, flight
readiness, command authority, latency, billing, or future provider behavior.

## Secret boundary

The credential was read from an ignored mode-`0600` host environment file. Its
value was not printed, copied into this worktree, written to the capture, or
committed. The LiteWing never receives the API key.
