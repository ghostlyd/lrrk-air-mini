"""Supervise one USB acquisition session and its separate advisory worker."""
from threading import Event, Thread
import math
import time

from .advisory_handoff import AdvisoryWorker, USBObservation


class BoundedAnalysis:
    """Worker-owned admission budget; not a provider timeout or token budget.

    Dropped observations do not wait or queue. Failed attempts consume a slot.
    The callback must separately bound model turns, tokens and network retries.
    """

    def __init__(self, analyze, *, interval_s, max_calls, monotonic=time.monotonic):
        if (not callable(analyze) or not callable(monotonic)
                or isinstance(interval_s, bool)
                or not isinstance(interval_s, (float, int))
                or not math.isfinite(interval_s) or interval_s < 1
                or type(max_calls) is not int or not 1 <= max_calls <= 12):
            raise ValueError('invalid advisory analysis budget')
        self._analyze = analyze
        self._monotonic = monotonic
        self._interval = interval_s
        self._maximum = max_calls
        self._calls = 0
        self._last_clock = None
        self._next_call = None

    @property
    def calls(self):
        return self._calls

    def __call__(self, runtime, observation):
        now = self._monotonic()
        if (isinstance(now, bool) or not isinstance(now, (int, float))
                or not math.isfinite(now)
                or (self._last_clock is not None and now < self._last_clock)):
            raise ValueError('invalid advisory budget clock')
        self._last_clock = now
        if self._calls >= self._maximum or (self._next_call is not None and now < self._next_call):
            return
        self._calls += 1
        self._next_call = now + self._interval
        return self._analyze(runtime, observation)


def run_usb_advisory(collector, analyze, stop, *, duration_s,
                     interval_s=5.0, max_calls=3, cancellation=None):
    """Return offered snapshot count, not completed analysis count.

    The caller supplies a bounded analysis callback with provider deadlines.
    No provider or motor commands are created here. Pending observations are
    discarded on exit. In-flight analysis is historical and cannot be forcibly
    cancelled by Python threads; failure to join is reported, never success.
    """
    cancellation = cancellation if cancellation is not None else Event()
    try:
        bounded = BoundedAnalysis(analyze, interval_s=interval_s, max_calls=max_calls)
    except BaseException:
        cancellation.set()
        collector.transport.close()
        raise
    worker = AdvisoryWorker(bounded)
    thread = Thread(target=worker.run, name='usb-advisory', daemon=True)
    try:
        thread.start()
    except BaseException:
        cancellation.set()
        worker.close()
        collector.transport.close()
        raise
    try:
        count = collector.stream(
            lambda snapshot: worker.offer(USBObservation(snapshot)),
            lambda: cancellation.is_set() or stop() or worker.failed,
            duration_s=duration_s,
        )
    finally:
        cancellation.set()
        worker.close()
        thread.join(timeout=1.0)
    if thread.is_alive():
        raise RuntimeError('USB advisory analysis did not terminate')
    if worker.failed:
        raise RuntimeError('USB advisory analysis failed')
    return count
