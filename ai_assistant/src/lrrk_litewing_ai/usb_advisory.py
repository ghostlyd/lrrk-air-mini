"""Supervise one USB acquisition session and its separate advisory worker."""
from threading import Thread

from .advisory_handoff import AdvisoryWorker, USBObservation


def run_usb_advisory(collector, analyze, stop, *, duration_s):
    """Return offered snapshot count, not completed analysis count.

    The caller supplies a bounded analysis callback with provider deadlines.
    No provider or motor commands are created here. Pending observations are
    discarded on exit. In-flight analysis is historical and cannot be forcibly
    cancelled by Python threads; failure to join is reported, never success.
    """
    worker = AdvisoryWorker(analyze)
    thread = Thread(target=worker.run, name='usb-advisory', daemon=True)
    try:
        thread.start()
    except BaseException:
        worker.close()
        collector.transport.close()
        raise
    try:
        count = collector.stream(
            lambda snapshot: worker.offer(USBObservation(snapshot)),
            lambda: stop() or worker.failed,
            duration_s=duration_s,
        )
    finally:
        worker.close()
        thread.join(timeout=1.0)
    if thread.is_alive():
        raise RuntimeError('USB advisory analysis did not terminate')
    if worker.failed:
        raise RuntimeError('USB advisory analysis failed')
    return count
