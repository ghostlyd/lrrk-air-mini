# Live UAVTalk and OpenAI advisory smoke verification

Date: 2026-09-09 (America/Los_Angeles)

## Scope and source

The bounded hardware and provider checks below ran from merged `main` at
`c28650af82bf75e39da7f9f4faf1cbdece38a8d2`. That commit includes the
read-side UAVTalk adapter and private audit creation reviewed in PRs #48 and
#49.

The host selected `/dev/cu.wchusbserial410` only after an exact WCH USB match:

- vendor/product: `1A86:7522`;
- topology location: `4-1`; and
- normalized transport identity: `usb-serial:1a86:7522:4-1`.

The USB bridge identity is not aircraft identity. Both audit runs left
`source.board` and `source.firmware` null.

## Offline live-telemetry result

The first run used no provider and completed one coherent five-object live
aggregate. The deterministic analyzer returned `BLOCKED` while reporting:

- a fresh 33.4 ms telemetry link;
- `Disarmed` flight status;
- 0.00 V battery telemetry, consistent with the physically absent battery;
- unknown IMU presence, identity, and health;
- four actuator observations within the decoder's `0..1000` range; and
- blocking actuator/CPU alarms plus multiple uninitialised subsystem states.

This is a telemetry observation, not proof of a persistent disarmed setting,
physical motor voltage, authenticated firmware, or flight readiness.

The private evidence was created in a mode-`0700` ignored directory. Neither
file is committed:

| Artifact | Bytes | Mode | SHA-256 |
| --- | ---: | ---: | --- |
| raw UAVTalk capture | 3,945 | `0600` | `96b1fa4d39c70a7e4acaf5372d3abb38adfefc79726ef3e4ebc255ca669cf532` |
| normalized audit JSONL | 4,711 | `0600` | `5cc3b2038c92d2cd1dc3198e2788fa9049c53f92a20252d852b0a8a6de4ff256` |

Audit replay validated a two-event hash chain containing only
`snapshot_received` and `preflight_result`; it contained zero action events.

## Live OpenAI advisory result

A second fresh aggregate was collected for one explicitly authorized OpenAI
call. Agents SDK tracing was disabled. The prompt required one concise
deterministic-preflight summary and prohibited proposing or executing an
action. The agent had read/advisory tools and no flight-action tool.

The immediate host analyzer returned `BLOCKED` with a 47.0 ms link age. By the
time the provider invoked the authoritative preflight tool, elapsed time had
made the same snapshot stale. The provider returned:

> Overall state: **BLOCKED** — highest-priority reason: **critical link
> telemetry is stale (4,836.2 ms; limit 500 ms)**.

The process exited 0. This proves that the merged live adapter, approved host
credential, pinned Agents SDK, and provider completed one advisory request
from actual connected-board telemetry at that time. It does not prove future
credential validity, provider availability, low latency, aircraft identity,
flight readiness, or command authority.

| Artifact | Bytes | Mode | SHA-256 |
| --- | ---: | ---: | --- |
| provider-run raw capture | 4,031 | `0600` | `4f83ca8c645d8b80e335c409a22f25a52c89fed545f16ac641a0d824d24efd64` |
| provider-run normalized audit | 4,644 | `0600` | `5d944a484e39a2bbbe6445ade963746c83c06f24b3e2b09c8c4315e632c4990a` |
| post-call private stdout transcript | 852 | `0600` | `071fa2c7200d45b457975f7c562600a758a79ef188ecda312b762271db901000` |

The normalized audit hash chain again validated two deterministic events and
zero action events. A credential-pattern scan found no API key or bearer token
in that audit. The credential value and raw capture bytes were not printed or
committed.

## Audit limitation discovered

The provider's final text is not currently a native hash-chained audit event;
the third artifact above is explicitly a post-call transcription of CLI
stdout. Consequently, the provider response is evidence-backed but weaker
than the deterministic snapshot/preflight chain. A production follow-up must
append redacted provider request/result metadata to the audit without recording
the API key, raw authorization header, hidden reasoning, or raw serial bytes.

## Control boundary

No reset, persistent setting, receiver write, arming write, actuator write,
navigation command, or flight command was issued. The live transport sent only
its allowlisted telemetry handshake, selected object requests, and required
acknowledgements. The battery remained absent, and this verification does not
claim flight or powered-propeller readiness.
