# Provisioning source readiness checkpoint

Immutable implementation revision: `daeb3bf1c88b4f426a9be0f65a5090795de5e5ad`.

The pinned ESP-IDF 5.3.2 build completed successfully with the previously
validated dump-disabled configuration. Reserved-ID scanning passed for 115
generated objects, and the application is `0xd4d80` bytes with 17% of the
unchanged 1 MiB partition free. The existing upstream mbedtls CMake deprecation
warning remains. No flash command printed by the build was executed.

The full port suite with the pinned flight checkout supplied ran 372 tests:
351 passed and 21 skipped. It used Homebrew Python 3.14 with the corresponding
PATH, not the older system Python. This is not a claim that skipped optional
SDK/platform scenarios were exercised. Separate host results at `07ac8e2`
were 270 tests, with 261 passing and nine optional SDK tests skipped locally.
CI has distinct SDK-backed and platform permission jobs.

Implemented source path: private save-before-open, exact USB identity/serial
framing, one-shot submission, actual parser/worker/receiver/arming-helper/scoped
store integration, correlated status reconciliation, retained stored-copy
promotion and challenge-only application-key reachability. Per-slice reviews
and precise simulation boundaries are recorded in adjacent verification files.

Aggregate review of `origin/main..daeb3bf` found no remaining source-level
blocker or missing mandatory software deliverable against the approved
provisioning specification. The reviewer independently ran 47 synthetic host
tests, all passing. The clean-head port suite and target build above fulfill
the local verification conditions; latest-revision CI must pass before merge.
Documentation updates clarify previously stale unwired claims.

Physical provisioning/activation, fresh installed-image identity, radio
timing, wireless telemetry, operator input integration, battery qualification
and flight remain separate outstanding work. This checkpoint is not completion
of the overall LiteWing/OpenPilot and AI-assistance goal.
