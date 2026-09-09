# OpenAI SDK tool verification — 2026-09-09

## Result and scope

The optional advisory agent constructs and its five real SDK function-tool
wrappers execute locally. This verifies the SDK boundary, not a model response
or live API access. No real credential, paid provider call, physical serial
connection, firmware flash, arming or motor test was used.

Host: macOS arm64, Python 3.14.7. Installed and checked:

- `openai-agents==0.22.1` (now pinned in the optional extra);
- `openai==3.10.0`;
- `pydantic==2.13.5`.

Transitive dependencies are resolved by pip, not fully locked. The dedicated
CI job separately installs the optional extra under Python 3.11 and checks
dependency consistency and the real tool wrappers. The deterministic core
retains its standard-library-only path.

## Reproduced failure and correction

Before the fix, creating the agent raised the SDK's `UserError` while decorating
`compare_tool(before: dict, after: dict)`: the unbounded dictionaries generated
`additionalProperties: true`, which the strict schema builder rejects. All
eight new integration tests failed at agent construction before changing the
implementation.

The wrapper now accepts zero arguments and compares the runtime's previous and
latest ingested snapshots. Without both, it returns an explicit unavailable
result. The model cannot provide replacement telemetry to this tool. The
underlying deterministic Python comparison function is unchanged; a comparison
is not a freshness verdict or permission to fly.

This follows the [Agents SDK's application-owned tool and state boundary](https://developers.openai.com/api/docs/guides/agents).

## Verification evidence

The eight SDK integration tests use actual decorators, JSON schemas, argument
parsing and `on_invoke_tool` handlers. Socket connect/connect_ex/sendto and DNS
resolution are blocked, tracing is disabled, and the process environment is
temporarily given a plainly fake test credential. No `Runner.run` is invoked.

They cover construction; zero/one/two-snapshot comparison; ignoring attempted
model-authored replacement telemetry; reading current runtime data; stale
preflight and explanations; unapproved snapshot-bound proposals; rejection of
six flight-control action kinds; and out-of-range proposal expiry.

Fresh local results:

- 60 assistant tests passed, including all eight optional-SDK tests;
- 37 port tests passed;
- `HOST_GATES=PASS`, with `ESP_IDF_BUILD=SKIPPED host-only`;
- `pip install './ai_assistant[openai]'` built and installed the project wheel;
- `pip check`: no broken requirements.

Expected negative cases produce the SDK warning that there is no active trace
span. Tracing stays disabled; these warnings do not indicate a provider call.
The diff and safety boundaries were self-reviewed. No independent reviewer was
available; this is not represented as an independent security review.

## Actual simulator capture through the SDK preflight tool

The saved capture from [the disarmed native integration](disarmed-simulator-2026-09-09.md)
was decoded by `UAVTalkCaptureAdapter`, ingested by `AssistantRuntime`, and
passed through the actual SDK `preflight_tool.on_invoke_tool` path:

| Evidence | Observation |
| --- | --- |
| Capture | `lrrk-disarmed-72k19e80/telemetry.uavtalk` |
| Bytes | 92,700 |
| SHA-256 | `4d619b75d1b976b4b11fe94c91f88a555cd04babc435161cc906dc7486963f3d` |
| Capture-end upper bound | `2026-09-09T12:16:26.926246+00:00`, filesystem mtime |
| Decoded partial snapshots | 1,212 |
| SDK preflight results | 1,212 `BLOCKED`, zero `PASS` |

The timestamp is only an upper bound on the last capture write, **not** a
verified timestamp for every sample. Raw UAVTalk capture contains partial
objects, not complete synchronized hardware health. The replay is historical;
missing fields remain unknown and it cannot pass live-flight preflight. The
capture remains local; this report publishes its digest and aggregate results.

## Still unverified

- Approved credential storage and a bounded real model/API call;
- model answer correctness, latency, billing and provider availability;
- live telemetry aggregation, dynamic/armed simulation and physical ESP32 HAL;
- battery/connector compatibility and human-supervised flight gates.
