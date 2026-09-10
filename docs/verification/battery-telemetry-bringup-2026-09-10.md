# Battery telemetry implementation status

Base: merged main `4626f90ae621d21ebcb33b5a55ce0fd32c8282e6`.

## Implemented in this branch

The repository-owned `litewing_battery_voltage` C core accepts calibrated ADC
pad millivolts and a monotonic timestamp. It applies the candidate board's
nominal equal-resistor 2:1 divider, invalidates acquisition/calibration failures,
and rejects readings older than 500 ms or timestamped in the future. Failed
reads clear their output. It reports no current, percentage, capacity, pack
presence, or flight-readiness verdict. A positive voltage is not proof of a
connected battery, particularly while USB is attached.

Six host tests compile and call the actual C code. They cover nominal scaling,
uninitialized state, loss of calibration, invalid pad readings, exact age
boundary, future timestamps, and extreme signed timestamps. These are logic
tests, not measurements of the fitted board. The sixth test exports C fields,
encodes the pinned FlightBatteryState layout, and decodes it through the real
host adapter, verifying that unavailable values stay unknown.

Validation: focused suite 5/5 passed after failing for the absent core;
port discovery 151 run, 115 passed, 36 optional-fixture skips using Homebrew
Python and its PATH for child processes. The first invocation used an older
system Python and failed in existing assistant tests requiring Python 3.11+;
the supported interpreter run passed. No ESP-IDF build is claimed here.

## Remaining integration work

1. Add the ESP-IDF ADC1 GPIO2 producer using the pinned IDF 5.3.2 APIs and
   calibrated conversion. Keep acquisition bounded; invalidate on overflow,
   calibration failure, or timeout. Timestamp acquisition rather than publication.
2. Add the source to the wrapper build only with its producer and lifecycle
   integration. The core is currently **not linked into the flight image**.
3. Publish voltage and validity/freshness through a contract the host decoder
   understands. Do not publish default zero current/capacity as measured data.
4. Exercise producer failures and telemetry decoding end to end, then build
   the ESP32-S3 target. Preserve settings and existing UART recovery.
5. Compare ADC readings against a meter on the fitted board and qualify the
   divider under operating conditions. A source BOM is not a fitted-board
   calibration certificate.
6. Select a pack only after connector, polarity, retention/mass, continuous
   discharge, and maximum charging current are known. See
   [parts selection](../PARTS_SELECTION.md).

Wi-Fi telemetry and pilot control remain separate, unfinished requirements of
the approved port. This voltage core does not replace them or enable arming.
No firmware flash or hardware I/O was performed for this implementation slice.

## Voltage-only wire convention

The inherited FlightBatteryState layout has no per-field validity flags.
The voltage-only exporter uses IEEE-754 NaN for unavailable float fields:
Current, BoardSupplyVoltage, PeakCurrent, AvgCurrent, ConsumedEnergy, and
EstimatedFlightTime are always unavailable. Voltage is NaN when invalid or
older than 500 ms at export. The eventual producer must set NbCells to the
configured value 1 and NbCellsAutodetected to False; these are not measurements.

The host adapter now accepts NaN only in battery float fields, translating
Voltage/Current to None before model construction and strict JSON encoding.
Positive/negative infinity remain errors, as do nonfinite attitude values.
Finite values from older full battery producers retain their existing decoding.
This does not reinterpret an older producer's zero current as missing.

This is a LiteWing producer/host convention, not a claim that every upstream
GCS handles NaN. GCS display compatibility must be checked before deployment.
Receiving a periodic object also does not establish ADC acquisition age: the
producer must invalidate stale samples before every publication. Host receipt
time alone is not an acquisition timestamp.

Latest checks: assistant suite 179 run, 170 passed, 9 optional-SDK skips;
battery C/host integration suite 6/6 passed. Initial decoder test exposed the
old blanket NaN rejection; exporter test failed for the missing C entry point
before implementation. No live ADC or ESP32-S3 build claim is made.

## Pinned driver inspection and next producer implementation

Inspected local ESP-IDF v5.3.2 headers and implementation, not an unversioned
API example:

- `components/esp_adc/include/esp_adc/adc_continuous.h`: bounded read timeout
  is in milliseconds; `ADC_MAX_DELAY` can block forever and must not be used.
  A frame and pool size are bytes, not sample counts. Callbacks run in ISR
  context and do not transfer ownership of the conversion buffer.
- `components/esp_adc/adc_continuous.c`, conversion callback dispatch: the
  driver attempts ring-buffer insertion, calls `on_conv_done`, then calls
  `on_pool_ovf` if insertion failed. Completion alone does not prove acceptance.
- `components/soc/esp32s3/include/soc/soc_caps.h`: continuous sampling bounds
  are 611 through 83333 Hz, so proposed 1000 Hz is within the target range.
- `components/esp_adc/include/esp_adc/adc_cali_scheme.h`: curve-fitting
  calibration creation can return `ESP_ERR_NOT_SUPPORTED` when required eFuse
  bits are absent. No guessed reference-voltage fallback is justified.

Implementation requirements for the next patch:

1. One task owns ADC start/read/stop and calibration calls. Configure ADC1,
   GPIO2/channel1, 12-bit, 12 dB, 1000 Hz; use 64-byte frames and a bounded
   256-byte pool. Confirm GPIO/channel through the SDK map during initialization.
2. Keep the read timeout finite (20 ms), check every sample's unit/channel and
   raw range, and reject partial/malformed frames. Do not timestamp queued old
   samples with the time of reading them as though newly acquired.
3. Establish a tested frame/timestamp association or a conservative acquisition
   age bound before publishing. An ISR-completion timestamp must not be attached
   to unrelated earlier bytes dequeued from the pool. Overflow invalidates the
   association; no plausible voltage may survive that failure.
4. Publish through the existing exporter. Missing calibration, initialization
   failure, timeout, overflow, and stale data produce unavailable voltage.
   Publishing unknown data must not silently alter the persistent arming policy.
5. Cover initialization cleanup, duplicate starts, task-creation failure,
   overflow ordering, malformed samples, timestamp association, and delayed
   publication in executable tests. Then integrate with the checked module
   lifecycle and add `esp_adc` to the component dependencies.

The driver implementation and startup wiring are still pending. Draft PR #54
collects this work; it must not be treated as a ready-to-flash producer.

## DMA batch processing implemented

`litewing_battery_process_dma` now processes one 16-word/64-byte ESP32-S3
TYPE2 frame. The decoder follows the pinned SDK's data/channel/unit bitfields,
requires ADC1/channel1, rejects ADC rail codes and wrong-sized frames, and
calibrates each raw value before averaging the resulting millivolts. A failed
conversion anywhere invalidates the whole sample, including a preceding valid
sample. No partial average escapes on a late failure.

The caller must supply the oldest acquisition timestamp and a current timestamp;
the processor rejects old/future/negative acquisition times and retains that
acquisition time for subsequent exports. This does not yet solve the DMA worker's
timestamp association: the worker must establish it rather than substitute
dequeue time. Overflow rejection remains a caller responsibility.

Focused suite: 11/11 passed, including five new batch-processing tests observed
failing for the missing implementation before it was added. The nonlinear
calibration fixture specifically detects averaging raw counts before calibration.
The raw decoder is host-tested; ADC resources and startup remain unimplemented.

## Bounded acquisition transaction implemented

The worker-facing `litewing_battery_acquire` transaction now flushes a stopped
ADC, records the start-time lower bound, starts acquisition, requests at most
16 words with a 20 ms read timeout, stops, checks overflow, and only then
calibrates/processes the batch. Read/overflow/calibration failures invalidate
voltage; flush/start/stop failures latch a persistent fault and prohibit retries.
A failed start receives one best-effort stop but remains latched regardless.

This intentionally replaces the earlier proposed always-running acquisition
with bounded bursts: the timestamp before each start conservatively dates
every sample without reconstructing timestamps across the driver's two queues.
The planned low-rate voltage worker can delay between bursts. Resource handles
are still created once, not reallocated on every burst. Actual sample cadence,
resource cost, and target build must be measured before qualification.

The operation interface is hardware-independent and tested against explicit
driver-boundary failures. It is not yet an ESP-IDF driver. Its stop contract
requires quiesced callbacks before overflow inspection. The native adapter
must satisfy this, for example by allocating the interrupt and running the
owning worker on the same pinned core, rather than assuming a cross-core
callback barrier from `adc_continuous_stop` alone.

Focused tests: 15/15 passed; four acquisition tests failed for the absent
transaction before implementation. They verify bounded read arguments,
stop-after-read-error, invalidation, lifecycle fault latching/no retry, and
delayed-worker acquisition age. ADC handle creation and firmware lifecycle
integration are the remaining implementation steps, not completed checks.
