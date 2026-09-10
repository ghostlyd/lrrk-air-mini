# USB maintenance worker — source verification

Implementation revision: `a07f98b`, stacked in draft PR #65.

The optional worker now connects receiver maintenance exclusion, cooperative
Wi-Fi shutdown and the scoped credential store. Submission copies one validated
request; status contains only phase, persistence result and transaction ID.
The worker rejects storage when flight status is not Disarmed, receiver
reservation fails, or shutdown misses its two-second monotonic deadline. It
wipes its owned credential buffers before checked token cleanup. Failed cleanup
retains the reservation and retries only cleanup, never the write.

## Observed checks

- `test_usb_maintenance.py`: one sanitizer-backed fixture, 14 separate process
  scenarios, passed. Actual worker, receiver and LWCF decoder; simulated RTOS
  scheduling, FlightStatus storage, radio lifecycle and NVS store boundary.
- Scenarios: success, armed, FlightStatus read failure, arming during shutdown,
  shutdown at the deadline, clock rollback, retained wireless owner, existing
  admission reservation, fresh receiver input, failed cleanup then recovery,
  uncertain/not-written/invalid store results, and failed task creation.
- Common assertions include malformed/null/short requests, zero transaction ID,
  single-pending rejection, input snapshot ownership, last-ID rejection,
  nonsecret status layout, real receiver exclusion during storage, and no
  duplicate write during cleanup.
- `test_maintenance_receiver.py`: passed; `test_gcs_receiver.py`: 20 passed.
- `test_wifi*.py`, with pinned IDF/mbedtls dependencies supplied: seven test
  methods passed, no skips (including the existing command-task cases).
- ESP-IDF 5.3.2 target build at `a07f98b`: exit 0. New worker translation unit
  compiled against actual generated FlightStatus headers. Persistence link
  verification passed. Image size `0xd4030`, 17% free in the unchanged 1 MiB
  application partition. Existing upstream CMake deprecation warning remains.

## Deliberately incomplete boundaries

The worker is in the target source list, but is not yet invoked at startup and
has no USB parser route. Unreferenced worker functions can therefore be removed
by the linker; this is compilation evidence, not an activated firmware feature.
Host credential-bundle storage, wire parsing/CRC/collision tests, startup wiring
and end-to-end provisioning remain subsequent work.

The receiver reservation excludes receiver ingress and settings loads, not
arbitrary trusted local UAVObject setters. Synthetic scheduling does not prove
physical stop latency or eliminate every concurrent scheduling race. NVS
readback does not prove power-loss durability; plaintext NVS and older dumps
retain their documented limitations.

No board access, flash, real credential creation, radio activation, arming or
motor commands occurred for these checks. This does not establish flight readiness.

## Independent review and follow-up

The independent review of `b1fcedc..a07f98b` returned **not ready to integrate**.

1. **Open, integration-blocking:** a normal flight-task arming transition can
   occur after a Disarmed snapshot. In particular, the pinned arming handler's
   AlwaysArmed path can act on cached input after maintenance takes the receiver
   reservation. A coordinated inhibit at the actual arming transition is
   required through storage and cleanup. Repeated snapshots are not sufficient.
   Do not connect this worker to startup or the USB parser before this is fixed.
2. **Late-observation acceptance corrected:** added tests advancing time inside
   FlightStatus reads during shutdown and immediately before storage. Both
   timeout tests failed against the original worker by observing a write, then
   passed after checking time after the quiescence observation and final getter.
   A rollback-during-getter case also passes. The worker suite now has 17
   scenarios. This denies late storage; it does **not** bound elapsed response
   time while a UAVObject getter waits on its upstream mutex. A bounded status
   observation path remains part of the arming-inhibit integration work.

The suite additionally now submits valid, distinct credentials while storing
and cleanup-blocked, rejects changed credentials under the retained ID, and
accepts a new transaction after completed cleanup. Deterministic concurrent
worker/flight-task tests and combined radio/storage integration remain needed.

## Arming exclusion implementation — `71bb267`

The worker now acquires a separate arming token before reserving receiver
ingress. The hash-checked object-manager build copy rejects Armed/Arming bytes
at all three normal mutation paths: full-object setter, field setter and
unpack. Observation, token acquisition and writes use the same existing
recursive object mutex. Token acquisition/status/release use zero-wait mutex
acquisition, so another task holding that mutex denies rather than blocks
maintenance. No mutex is held over radio shutdown, delays or NVS. Receiver
cleanup precedes arming-token release. This is temporary maintenance exclusion,
not an AlwaysDisarmed setting or a change to normal flight arming configuration.

Verification at that revision:

- The concurrent arming test uses pthread locks and the actual three generated
  object-manager function bodies. An arm operation caches Disarmed, pauses,
  resumes after reservation, and is rejected without a write/event. The same
  test compiled with the unmodified upstream write functions fails at that
  assertion, reproducing the original bug.
- Full/field/unpack inhibition, unrelated-object/field updates, allowed
  Disarmed writes, stale tokens, already-armed rejection, and busy-lock bounded
  rejection are exercised. Object lookup/events use small test storage fixtures;
  this is not a full simulated flight scheduler.
- The worker's 17 scenarios now include the real arming-token implementation
  and assert inhibition at the storage boundary. They pass, along with the
  separate receiver-maintenance fixture.
- ESP-IDF 5.3.2 build passed against the real generated FlightStatus API.
  Application size `0xd4110`, 17% partition headroom. Persistence link check
  passed. Upstream packed-pointer and CMake deprecation warnings remain.

The original P1/P2 source corrections are submitted for follow-up review;
this section does not claim review acceptance or physical validation. The USB
parser and worker startup are still not connected. Broader-suite results and
combined radio/storage execution must be reported separately.

Follow-up review accepted both P1 and P2 source corrections at `71bb267`, with
no new blocking correctness issue. Its additional cleanup-coverage request is
now exercised: another pthread holds the object mutex during arming-token
release; status stays CLEANUP_BLOCKED, valid submissions are rejected, inhibition
persists, storage runs once, and releasing the mutex allows eventual cleanup.
Receiver-cleanup retries also directly assert retained arming inhibition. The
worker suite now has 18 scenarios; all three maintenance test groups pass.

The broad port suite executed 385 tests: 370 passed, 13 skipped and two failed.
Both failures were build-script subprocesses selecting `/usr/bin/python3`
3.9.6 while the AI host package declares `>=3.11,<3.15`; the nested tests lacked
`unittest.TestCase.enterContext`. The outer runner was Python 3.14.7, but that
alone did not change subprocess PATH. This initial run is not a green broad
suite; the affected build-script cases require a corrected-PATH rerun.

Corrected-PATH rerun (`PATH=/opt/homebrew/bin:$PATH`): all three
`test_build_script.py` cases passed, including both previously failing cases.
No source workaround or Python compatibility relaxation was made. The full
385-test suite was not repeated after this targeted rerun.
