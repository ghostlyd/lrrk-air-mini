"""Bounded, read-only handoff from a trusted pilot owner to an advisory worker.

No socket, keys, command API, authentication, or background thread lives here.
Supply observations already accepted by the active session's telemetry consumer.
Use a fresh inbox per session and close it in the pilot owner's finally block.
The pilot owner calls offer; a separate serialized worker owns the runtime and
calls ingest_latest, then performs any analysis/API work outside the pilot loop.
"""
from threading import Lock
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
