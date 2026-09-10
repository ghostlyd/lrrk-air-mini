"""Bounded, read-only handoff from a trusted pilot owner to an advisory worker.

No socket, keys, command API, authentication, or background thread lives here.
Supply observations already accepted by the active session's telemetry consumer.
Use a fresh inbox per session and close it in the pilot owner's finally block.
The pilot owner calls offer; a separate serialized worker owns the runtime and
calls ingest_latest, then performs any analysis/API work outside the pilot loop.
"""
from threading import Event, Lock
from typing import TYPE_CHECKING

from .telemetry_session import TelemetryObservation

if TYPE_CHECKING:
    from .tools import AssistantRuntime


class AdvisoryTelemetryInbox:
    """Single latest observation, not an accumulated or synchronized snapshot.

    offer never waits for this inbox's mutex: contention drops the new item.
    It never invokes analysis. Python scheduling remains non-real-time.
    close and the single consumer briefly acquire the mutex, but never hold it
    across runtime callbacks or API requests. Closing discards pending data and
    rejects future offers; already-drained analysis may finish historically.
    It does not cancel an API request or clear a separately owned runtime.
    Returned observations are historical data, never a live authority token.
    """

    def __init__(self):
        self._lock = Lock()
        self._pending: TelemetryObservation | None = None
        self._closed = False

    def offer(self, observation: TelemetryObservation) -> bool:
        """True means queued, not analyzed, current, or accepted for flight."""
        if type(observation) is not TelemetryObservation:
            raise TypeError("expected a validated telemetry observation")
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._closed:
                return False
            self._pending = observation
            return True
        finally:
            self._lock.release()

    def ingest_latest(self, runtime: "AssistantRuntime") -> TelemetryObservation | None:
        """Worker-only drain; ingestion failure consumes this item, without retry.

        Keep all operations on runtime serialized in its owner worker. This
        method does not make AssistantRuntime itself thread-safe. Timestamps,
        unknowns and partial fields are preserved; no freshness is synthesized.
        """
        with self._lock:
            observation = self._pending
            self._pending = None
        if observation is not None:
            runtime.ingest(observation.snapshot)
        return observation

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending = None


class AdvisoryWorker:
    """One session, one runtime, one caller-owned analysis thread.

    Run ``run`` on a dedicated thread, never on the pilot loop. The trusted
    callback receives only the runtime and historical observation; do not give
    its closure pilot keys or controls. This is capability separation by API,
    not a Python sandbox or a hard real-time scheduling guarantee.

    close rejects offers and requests cooperative termination without joining.
    An already-admitted callback may finish after close; it must treat output
    as historical. A hung callback cannot be killed by this worker. Configure
    external API deadlines and join from supervision, never the pilot loop.
    Create a new instance on session change; never reuse its runtime.
    """

    def __init__(self, analyze):
        self._analyze = analyze
        self._inbox = AdvisoryTelemetryInbox()
        self._stop = Event()
        self._failed = Event()
        self._run_once = Lock()

    @property
    def failed(self) -> bool:
        """Analysis failed; exception text and telemetry are not retained."""
        return self._failed.is_set()

    def offer(self, observation: TelemetryObservation) -> bool:
        return self._inbox.offer(observation)

    def close(self) -> None:
        self._stop.set()
        self._inbox.close()

    def run(self) -> None:
        """Consume latest-only observations until closed or analysis fails.

        An idle worker waits 50 ms between polls. Offers remain nonblocking
        on inbox contention and do not invoke callback code or signal locks.
        No retries, network access, or analysis occur without an observation.
        """
        if not self._run_once.acquire(blocking=False):
            raise RuntimeError('advisory worker cannot restart')
        try:
            from .tools import AssistantRuntime

            runtime = AssistantRuntime()
            while not self._stop.is_set():
                item = self._inbox.ingest_latest(runtime)
                if item is not None and not self._stop.is_set():
                    self._analyze(runtime, item)
                self._stop.wait(.05)
        except Exception:
            self._failed.set()
        finally:
            self.close()
