# Board startup failure gate

## Scope and authority

First implementation slice of issue 27's checked startup work, under the
owner's standing design/source maintenance authority. Firmware source and host
tests only; no device I/O, flashing, arming/settings changes or paid AI calls.
Always Disarmed remains the installed configuration. This slice must never
publish BootFault OK or claim complete startup readiness.

## Decision

Use explicit early returns and a one-shot board-service status, retaining the
shared `void PIOS_Board_Init(void)` interface. The target entry point must check
`bool PIOS_LiteWing_BoardServicesInitialized(void)` before initializing modules.
The status means only that the synchronous board sequence reached its end
without a **reported** failure. It is false before/during initialization and
after any failure; repeat calls never reinitialize resources or reset a fault.
Only app_main invokes this sequence; the interface is not a concurrent reset API.

A monolithic rewrite of all upstream modules would be much harder to review.
A global allocation-hook trap would obscure failure ownership and introduce
lock/reentrancy hazards. Neither is needed to prevent the existing entry point
from running modules after a detected board failure.

## Failure handling

- Check the status returns from delay, LED, task monitor, callback scheduler,
  event dispatcher, settings storage, object manager, firmware identity reads
  and writes, safe settings recovery, alarms, UART/COM, receiver and target
  hardware initialization. Stop the sequence at its first reported error.
- Object generation remains void; before using SystemAlarms and GCSReceiver,
  require their generated handles. Remove the redundant GCSReceiverInitialize
  call (already registered objects return -2). Firmware identity getters must
  succeed before any bytes from their destination are used.
- Each failure latches the board status, calls the existing PWM Shutdown
  boundary, and attempts BootFault Critical only if alarm initialization has
  returned success. Do not use an LED until LED initialization has succeeded.
- Storage failure stops before object registration/default provisioning.
  Missing/corrupt required settings stop before receiver or output setup.
- PWM Shutdown before PWM Init currently does nothing. Safety here relies on
  the verified control flow never reaching output initialization or modules
  after that early failure, not an invented pre-init hardware latch. A failure
  after hardware initialization still uses the existing shutdown latch.
- Preserve PIOS_WDG_Init semantics: its return is previous boot watchdog flags,
  not an initialization status. Do not treat nonzero flags as a failure code.

## Explicit remaining gaps

EventDispatcherInitialize and AlarmsInitialize contain internal allocation
paths that can report success incorrectly. Generated object registration and
debug-log initialization do not expose complete failure status. Watchdog task
subscription, module/task creation and callback scheduler start are also not
fully checked. StartModules executes asynchronously inside System's task.
Consequently a nominal board-service result is **not** BootFault success, an
arming gate, or proof of valid scheduler/CPU runtime data. Those are subsequent
reviewable slices; issues 19, 26 and 27 stay open.

## Verification

Compile byte-for-byte copies of the production board initializer and entry
point, using generated object declarations and fake service boundaries. Each
process starts with clean static state. Assert no later service/module calls
after an injected failure, no success alarm, no invalid LED/alarm access,
shutdown requested, no duplicate initialization on a second call, and correct
nominal sequence. Test UART allocation/COM failures separately. Exercise the
real existing settings-recovery algorithm with controlled storage/object APIs.
These are orchestration tests, not real allocation, NVS, RTOS or electrical tests.

Run focused tests red before changing production, negative controls that bypass
the entry gate and error return, all existing host suites, and a real ESP-IDF
5.3.2 ESP32-S3 build. Review and CI must identify the exact source revision.
Do not infer installation or physical acceptance from any of these results.
