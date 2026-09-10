"""Authenticated observations reach the real runtime without owning pilot I/O."""
from datetime import datetime, timezone
import json
import threading
import unittest

from lrrk_litewing_ai.advisory_handoff import AdvisoryTelemetryInbox
from lrrk_litewing_ai.telemetry_session import TelemetrySession
from lrrk_litewing_ai.telemetry_wire import TelemetryRecord, encode_telemetry
from lrrk_litewing_ai.tools import AssistantRuntime, get_latest_telemetry, run_preflight_tool


def observation(sequence=1):
    session, key = b's'*16, b't'*32
    consumer = TelemetrySession(session, key)
    record = TelemetryRecord(0xEF69B6BC, sequence*100, None, bytes(8))
    return consumer.receive(encode_telemetry(record,session,sequence,key),
                            sequence*100+10,datetime.now(timezone.utc))


class AdvisoryHandoffTests(unittest.TestCase):
    def test_empty_drain_does_not_clear_existing_runtime(self):
        inbox, runtime = AdvisoryTelemetryInbox(), AssistantRuntime()
        old = observation().snapshot
        runtime.ingest(old)
        self.assertIsNone(inbox.ingest_latest(runtime))
        self.assertIs(runtime.latest, old)

    def test_latest_replaces_backlog_and_preserves_partial_unknowns(self):
        inbox, runtime = AdvisoryTelemetryInbox(), AssistantRuntime()
        first, latest = observation(), observation(2)
        self.assertTrue(inbox.offer(first))
        self.assertTrue(inbox.offer(latest))
        self.assertIs(inbox.ingest_latest(runtime), latest)
        self.assertIs(runtime.latest, latest.snapshot)
        self.assertIsNone(runtime.previous)
        self.assertIsNone(inbox.ingest_latest(runtime))
        self.assertIsNone(runtime.latest.link_age_ms)
        self.assertIsNone(runtime.latest.battery.voltage_v)
        self.assertEqual(runtime.latest.captured_at, latest.received_at)
        result = get_latest_telemetry(runtime)
        self.assertFalse(result['snapshot']['armed'])
        self.assertNotIn((b's'*16).hex(),json.dumps(result))
        report = run_preflight_tool(runtime)
        self.assertNotEqual(report['overall'],'PASS')

    def test_closed_inbox_discards_pending_and_cannot_reopen(self):
        inbox, runtime = AdvisoryTelemetryInbox(), AssistantRuntime()
        self.assertTrue(inbox.offer(observation()))
        inbox.close(); inbox.close()
        self.assertFalse(inbox.offer(observation(2)))
        self.assertIsNone(inbox.ingest_latest(runtime))
        self.assertIsNone(runtime.latest)

    def test_contended_offer_drops_without_waiting(self):
        inbox = AdvisoryTelemetryInbox()
        result = []
        # Real critical-section contention; reverting to blocking acquisition
        # would leave this producer stuck until the holder releases.
        with inbox._lock:
            worker = threading.Thread(target=lambda: result.append(inbox.offer(observation())))
            worker.start()
            worker.join(.5)
            stopped = not worker.is_alive()
        worker.join(2)
        self.assertTrue(stopped)
        self.assertEqual(result,[False])

    def test_slow_runtime_never_holds_producer_lock(self):
        inbox = AdvisoryTelemetryInbox()
        entered, release = threading.Event(), threading.Event()
        class SlowRuntime(AssistantRuntime):
            def ingest(self, snapshot):
                entered.set()
                if not release.wait(2): raise RuntimeError('test worker not released')
                super().ingest(snapshot)
        runtime = SlowRuntime()
        first, latest = observation(), observation(2)
        inbox.offer(first)
        worker = threading.Thread(target=lambda: inbox.ingest_latest(runtime))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(inbox.offer(latest))
            inbox.close()
            self.assertFalse(inbox.offer(observation(3)))
        finally:
            release.set(); worker.join(2)
        self.assertFalse(worker.is_alive())
        # Already-drained analysis can complete as a historical observation;
        # close discards the queued newer item, not prior/in-flight work.
        self.assertIs(runtime.latest, first.snapshot)
        self.assertIsNone(inbox.ingest_latest(runtime))

    def test_failed_consumer_does_not_retry_or_erase_a_newer_offer(self):
        inbox = AdvisoryTelemetryInbox()
        first, latest = observation(), observation(2)
        class FailedRuntime(AssistantRuntime):
            def ingest(self, snapshot):
                inbox.offer(latest)
                raise RuntimeError('consumer failed')
        inbox.offer(first)
        with self.assertRaises(RuntimeError): inbox.ingest_latest(FailedRuntime())
        runtime = AssistantRuntime()
        self.assertIs(inbox.ingest_latest(runtime),latest)
        self.assertIsNone(inbox.ingest_latest(runtime))

    def test_wrong_input_rejected_without_replacing_pending(self):
        inbox, runtime = AdvisoryTelemetryInbox(), AssistantRuntime()
        item = observation()
        inbox.offer(item)
        for invalid in (None,{},item.snapshot,b'raw datagram'):
            with self.assertRaises(TypeError): inbox.offer(invalid)
        self.assertIs(inbox.ingest_latest(runtime),item)
