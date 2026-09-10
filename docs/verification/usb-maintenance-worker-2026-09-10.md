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
