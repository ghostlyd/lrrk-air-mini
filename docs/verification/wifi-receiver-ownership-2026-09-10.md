# Receiver ownership and publication: source verification

Production revision: `1530c1b`; additional release-race fixture: `919d439`.

The receiver now reserves wireless ownership only while disarmed, with no fresh
USB input and no admitted USB storage transaction in flight. Matching disarmed
release invalidates input. A generation and timestamp fence rejects delayed USB
publication across ownership changes. The in-flight counter keeps ownership
reservation outside a possibly blocking UAVObject unpack transaction; no spinlock
is held through that transaction.

Wireless publication checks retained reservation identity and active session
identity, then commits the private candidate and copies channels/timestamp under
one receiver lock. It does not pass wireless data to `UAVObjUnpack`. The caller
must hold its session mutex across preparation/publication and supply its retained
reservation identity when notifying the receiver of STOP or retired state.
Ownership is retained after failure/STOP, excluding automatic USB takeover.

## Evidence

- 17 receiver regressions pass, including storage/event assertions around an
  attempted ownership change during unpack. Independent review accepted the
  corrected in-flight transaction guard at `ccc7396`.
- Real session, codec, mbedTLS and receiver integration passes six standalone
  cases: mixed-channel publication with original timestamp expiry; delayed
  commit; wrong reservation; STOP invalidation; and release before publication
  without overwriting newer USB input; and rollback across the reservation clock
  fence. Fatal ASan/UBSan enabled.
- ESP-IDF 5.3.2 ESP32-S3 build passed at `1530c1b`. This compiles the adapter but
  does not prove a runtime caller exists; unused functions may be discarded.
- Publication review found a missing reservation-clock check and missing session
  symbols in two USB test harnesses. `c886d18` adds the check and shared aborting
  unused-path stubs for USB-only tests. All 26 GCS tests and all six real session
  integration scenarios pass after correction. The earlier full regression run
  encountered the old linkage errors; it is not evidence for this correction.
- Scoped re-review accepted both fixes with no new Critical/Important findings.
  The corrected full run completed: 361 tests, 349 passed, 12 skipped
  (130.381 seconds). It began at `e293ec3`, before the later UART write expansion.

## UART object-write exclusion

`87f4da0` extends the ownership/fence/in-flight transaction guard to every UART
object unpack, not only receiver packets. Settings and persistence writes cannot
bypass ownership via other object handles. Only receiver packets can update
private receiver channels. `3f35656` fixes the new request fixture's header.
Current focused checks: 29 GCS tests and six real SDK publication scenarios pass.
The real pinned parser answers telemetry requests with wireless ownership held
and without invoking object unpack. Review of this expansion is pending.

No application controller, AP/socket lifecycle, provisioning, flash, or live
hardware test is included in this slice. The next integration must serialize
session access, provide current flight-state/ownership observations, call
publication or invalidation on every relevant result, and retain USB recovery.
