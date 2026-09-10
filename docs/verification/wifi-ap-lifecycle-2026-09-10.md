# Wi-Fi AP lifecycle boundary — 2026-09-10

Implemented on `codex/wifi-runtime`, based on `cbaa7bb` plus main's independent
audit commit. No startup hook, socket, controller task, provisioning, hardware,
serial, flashing, radio operation, network write or push was performed.

## API and lifecycle

`pios_litewing_wifi_ap.h` exposes singleton `lw_wifi_ap_start(root[32])`,
`lw_wifi_ap_stop(root[32])`, and `lw_wifi_ap_faults()`. One trusted task must
serialize lifecycle calls and exclude competing Wi-Fi/netif initialization.
Start loads and validates existing credentials before any network API. Missing
or invalid credentials return failure with zeroed output and no radio setup.
USB UART and settings are untouched. Existing Wi-Fi or any preexisting netif
causes refusal; custom interface names cannot bypass the ownership check.

Checked setup: global netif init; Wi-Fi log suppression with readback; create or
borrow default event loop; allocate AP netif; attach driver; install default
handlers; Wi-Fi init with NVS disabled; RAM storage; AP-only mode; bounded decoded
SSID/password; WPA2-Personal/CCMP, PMF capable (not required), one station,
channel 1 and 100-TU beacon; fault-handler registration; `esp_wifi_start`.
Only complete synchronous success without a latched fault copies the independent
application root to the trusted caller. Temporary credential/config buffers are
wiped through volatile stores on all exits. No default credentials, MAC-derived
SSID, identifier/password logging, NVS erase/write, eFuse or restart API is added.

The event callback only atomically ORs AP-stop/station-disconnect fault bits.
Polls and stop never clear them; a fresh lifecycle resets them before handler
registration. The owner must poll before controller admission/ingress/ticks and
retire control on faults. Events do not call controller/receiver APIs or stop
the radio in callback context. Duplicate starts do not restart the active AP.

Stop wipes caller root first, then stops a possibly partially started driver,
deinitializes owned Wi-Fi, unregisters the fault handler, clears owned default
attachment/handlers, destroys owned netif, deletes only an owned loop, and
restores saved Wi-Fi log levels. Failures latch a lifecycle fault and retain
remaining ownership for retry; new starts refuse while resources remain.
Driver-clear consumes its attachment even on an error in this SDK, so cleanup
does not double-free it. A borrowed default loop is never deleted. Global lwIP
initialization remains because IDF does not support its deinitialization.

## Pinned SDK evidence

Authoritative local SDK:
`/Users/lrrk-ultra/Documents/LiteWing/.toolchains/esp-idf-v5.3.2`.

- `components/esp_wifi/src/wifi_default.c`: default AP helper asserts/aborts;
  replaced with checked constituent APIs. AP slot is recorded before attach
  allocation can fail; clear removes that slot and consumes its driver.
- `components/esp_wifi/src/wifi_init.c`: init returns OK for an existing driver;
  `esp_wifi_get_mode` must first return `ESP_ERR_WIFI_NOT_INIT`. Init failures
  invoke SDK-internal unwind. `esp_wifi.h` defines mode/start/stop/deinit/storage.
- `esp_wifi_types_generic.h`: full AP/STA/NAN union types used directly by host
  fixtures, including SSID/password bounds, PMF and cipher semantics.
- `esp_netif/lwip/esp_netif_lwip.c`: valid driver-config assignment cannot fail;
  global init is repeatable and lwIP deinit is unsupported.
- `esp_event/default_event_loop.c` and `esp_event.c`: existing-loop result and
  instance-registration ownership; dispatch/unregister serialize on loop mutex.
- `wifi_default.c`, `wifi_init.c`, `lib_printf.c`, `esp_netif_lwip.c`, and
  `log/log.c`: Wi-Fi log tags, MAC log paths and silent allocation failure in
  `esp_log_level_set`; suppression/restoration use readback, never wildcard logs.

## Focused verification

Read and applied TDD skill plus `writing-good-tests.md`. Initial compiled stub
failed on stale secret output. Further RED/GREEN checks caught custom-netif
ownership and unsuppressed SDK logging before their fixes.

`python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p 'test_wifi_*.py' -v`
passed **3 methods** with fatal ASan/UBSan. AP fixture compiles the real adapter,
decoder and NVS loader, stubbing only SDK network/log/flash boundaries. Coverage:
missing/invalid credentials, null output, bounded maximal credentials, every
fallible setup call, RAM/WPA2/PMF/one-station settings and required call ordering,
borrowed resources, success-only root handoff, irrelevant/sticky events and
concurrent event production/polling, duplicate start, fault during start,
start-failure plus stop-failure, teardown retry and log-policy failures.
Wi-Fi config union types are real SDK headers; init/netif plumbing uses reduced
host fixtures, so host tests alone are not target compatibility evidence.

Final actual adapter translation unit compiled successfully with the pinned
Xtensa ESP32-S3 GCC, real IDF headers and `-Werror`: reused the existing build's
`pios_litewing_wifi_config.c` compile-command flags, substituted AP source/output,
and added esp_wifi/esp_event/esp_netif include directories. Temporary object was
removed. `git diff --check` passed. No full suite or full target build was run;
main owns the committed target build and linkage check.

## Open integration issues and limits

No blocker for handing off this uncalled dependency. API start success does not
prove AP-start event processing, DHCP readiness, peer connectivity, scheduling,
USB coexistence under radio load, or physical failsafe timing. A fault can arrive
immediately after success: the caller must poll before using the root/session.
Queued old events on a borrowed loop can conservatively fault a new lifecycle;
they cannot clear faults or admit control. Default-loop ownership and Wi-Fi log
tags must not be adopted/changed concurrently by another component.

SDK-private init/unwind, default-handler internal errors and binary-driver
behavior are outside host fault injection. Init's own failed internal unwind
cannot be certified clean by this public adapter. SDK log suppression covers
the inspected Wi-Fi paths; later target/runtime qualification must check any
other vendor output without retaining identifiers or secrets. Wiping cannot
prove erasure of compiler/driver copies; caller owns wiping derived keys and
all additional root copies. A failed stop must never be reported as radio off.
