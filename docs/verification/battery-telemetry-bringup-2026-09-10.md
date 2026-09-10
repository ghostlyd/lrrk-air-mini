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

Five host tests compile and call the actual C code. They cover nominal scaling,
uninitialized state, loss of calibration, invalid pad readings, exact age
boundary, future timestamps, and extreme signed timestamps. These are logic
tests, not measurements of the fitted board.

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
