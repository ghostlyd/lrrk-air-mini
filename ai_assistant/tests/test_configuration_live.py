"""Real wire -> collector -> normalized policy, with only clock and I/O faked."""
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from lrrk_litewing_ai.live_uavtalk import LiveUAVTalkCollector, OutboundProtocol, UAVTalkLiveError
from lrrk_litewing_ai.uavtalk import UAVTalkDecoder
from lrrk_litewing_ai.safety import run_preflight
from test_live_uavtalk import complete_stream, packet, FLIGHT_TELEMETRY_STATS
from test_configuration import FMS, SYS, FMS_BYTES, SYS_BYTES, SLOTS, NOW


def settings(kind=0x20):
    return packet(kind, FMS, FMS_BYTES) + packet(kind, SYS, SYS_BYTES)


def fast(mode=1):
    return complete_stream().replace(packet(0x20, 0xEF69B6BC, bytes([2, 0, 0, 0, 0, 1, 0, 0])),
                                     packet(0x20, 0xEF69B6BC, bytes([2, mode, 0, 0, 0, 1, 0, 0])))


def mode_status(state, delay=0):
    return next(f.status for f in run_preflight(state, now=state.captured_at + timedelta(milliseconds=delay)).findings
                if f.finding_id == 'capabilities.mode')


class WireTransport:
    identity = 'synthetic-configuration-test'

    def __init__(self, chunks=(), repeat=None, delay=.05):
        self.chunks = list(chunks)
        self.repeat = repeat
        self.delay = delay
        self.time = 0.0
        self.sent = []
        self.closed = False
        self.protocol = OutboundProtocol(self.write)

    def write(self, data):
        self.sent.append((self.time, UAVTalkDecoder().feed(data)[0]))
        return len(data)

    def handshake(self, value):
        self.protocol.handshake(value)

    def request(self, oid):
        self.protocol.request(oid)

    def ack(self, oid, instance):
        self.protocol.ack(oid, instance)

    def read(self, maximum):
        self.time += self.delay
        data = self.chunks.pop(0) if self.chunks else self.repeat(self.time) if self.repeat else b''
        if len(data) > maximum:
            self.chunks.insert(0, data[maximum:])
        return data[:maximum]

    def close(self):
        self.closed = True

    def sleep(self, seconds):
        self.time += seconds


class ConfigurationLiveTests(unittest.TestCase):
    def collector(self, io, path):
        return LiveUAVTalkCollector(io, path, duration_s=2.4, monotonic=lambda: io.time,
                                   wall_clock=lambda: NOW + timedelta(seconds=io.time), sleep=io.sleep)

    def test_collection_and_stream_policy_and_ack_allowlist(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming), tempfile.TemporaryDirectory() as directory:
                io = WireTransport([fast() + settings(0x22)], repeat=lambda t: fast())
                collector = self.collector(io, Path(directory) / 'capture')
                results = []
                if streaming:
                    collector.stream(results.append, lambda: False, duration_s=.2)
                else:
                    results.append(collector.collect())
                self.assertTrue(results)
                self.assertEqual(results[0].configuration.stabilization_slots, SLOTS)
                self.assertTrue(all(mode_status(s) == 'PASS' for s in results))
                self.assertEqual({f.object_id for _, f in io.sent if f.message_type == 0x23}, {FMS, SYS, 0xB8229FE4})
                self.assertTrue(io.closed)
                with self.assertRaises(UAVTalkLiveError):
                    collector._aggregate()
                # Reusing a collector cannot carry settings into another session.
                collector.capture_path = Path(directory) / 'second'
                io.chunks = [fast()]
                self.assertIsNone(collector.collect().configuration)

    def test_absence_is_optional_for_collection_and_continuous_stream(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming), tempfile.TemporaryDirectory() as directory:
                io = WireTransport(repeat=lambda t: fast())
                collector = self.collector(io, Path(directory) / 'capture')
                results = []
                if streaming:
                    count = collector.stream(results.append, lambda: False, duration_s=2.3)
                    self.assertGreater(count, 20)
                else:
                    results.append(collector.collect())
                    self.assertLess(io.time, .2)
                self.assertTrue(all(s.configuration is None and mode_status(s) == 'UNKNOWN' for s in results))

    def test_independent_request_cadence_and_no_catchup_for_both_paths(self):
        for streaming in (False, True):
            for delay in (.05, .65):
                with self.subTest(streaming=streaming, delay=delay), tempfile.TemporaryDirectory() as directory:
                    # collect cannot complete before the first two seconds; stream
                    # receives all mandatory objects on every read, even after a stall.
                    io = WireTransport(delay=delay, repeat=lambda t: fast() if streaming or t > 2 else fast()[:48])
                    collector = self.collector(io, Path(directory) / 'capture')
                    if streaming:
                        collector.stream(lambda s: None, lambda: False, duration_s=2.3)
                    else:
                        collector.collect()
                    for oid, cadence in ((FMS, 1.0), (SYS, 1.0), (0xEF69B6BC, .2), (0xDA60A0C6, .2)):
                        times = [t for t, f in io.sent if f.message_type == 0x21 and f.object_id == oid]
                        self.assertGreaterEqual(len(times), 2)
                        self.assertEqual(times[0], 0)
                        self.assertTrue(all(b - a >= cadence - 1e-9 for a, b in zip(times, times[1:])), times)
                        self.assertTrue(all(b - a <= cadence + delay + .006 for a, b in zip(times, times[1:])), times)

    def test_nack_revokes_only_its_component_and_malformed_nack_fails(self):
        for oid in (FMS, SYS):
            for cached in (False, True):
                with self.subTest(oid=oid, cached=cached), tempfile.TemporaryDirectory() as directory:
                    io = WireTransport([fast() + (settings() if cached else b'') + packet(0x24, oid)])
                    state = self.collector(io, Path(directory) / 'capture').collect()
                    self.assertEqual(mode_status(state), 'UNKNOWN')
                    if cached:
                        self.assertEqual(state.configuration.stabilization_slots, () if oid == FMS else SLOTS)
                        self.assertEqual(state.configuration.airframe_type, None if oid == SYS else 'QuadX')
            for payload, instance in ((b'x', 0), (b'', 1)):
                with tempfile.TemporaryDirectory() as directory:
                    io = WireTransport([fast() + settings() + packet(0x24, oid, payload, instance)])
                    with self.assertRaises(UAVTalkLiveError):
                        self.collector(io, Path(directory) / 'capture').collect()

    def test_disconnect_reconnect_and_termination_clear_configuration(self):
        for status in (0, 1):
            with tempfile.TemporaryDirectory() as directory:
                reset = packet(0x20, FLIGHT_TELEMETRY_STATS, bytes(36) + bytes([status]))
                io = WireTransport([fast()[:48] + settings() + reset + fast()])
                state = self.collector(io, Path(directory) / 'capture').collect()
                self.assertIsNone(state.configuration)
        with tempfile.TemporaryDirectory() as directory:
            io = WireTransport([fast() + settings(), packet(0x20, FLIGHT_TELEMETRY_STATS, bytes(37))])
            collector = self.collector(io, Path(directory) / 'capture')
            results = []
            with self.assertRaisesRegex(UAVTalkLiveError, 'disconnected'):
                collector.stream(results.append, lambda: False, duration_s=.3)
            self.assertEqual(mode_status(results[0]), 'PASS')
            collector.capture_path = Path(directory) / 'next'
            io.chunks = [fast()]
            self.assertIsNone(collector.collect().configuration)

    def test_new_flight_status_selects_new_slot_and_settings_age_expires(self):
        changed = bytearray(FMS_BYTES)
        changed[34] = 12  # Slot 2 thrust = CruiseControl.
        with tempfile.TemporaryDirectory() as directory:
            io = WireTransport([fast() + packet(0x20, FMS, bytes(changed)) + packet(0x20, SYS, SYS_BYTES)],
                               repeat=lambda t: fast(2))
            results = []
            self.collector(io, Path(directory) / 'capture').stream(results.append, lambda: False, duration_s=.2)
            self.assertEqual(mode_status(results[0]), 'PASS')
            self.assertTrue(all(mode_status(s) == 'UNKNOWN' for s in results[1:]))
            self.assertEqual(mode_status(results[0], 2000), 'UNKNOWN')
        with tempfile.TemporaryDirectory() as directory:
            io = WireTransport([fast() + settings()], repeat=lambda t: fast())
            results = []
            self.collector(io, Path(directory) / 'capture').stream(results.append, lambda: False, duration_s=2.3)
            self.assertEqual(mode_status(results[0]), 'PASS')
            self.assertEqual(mode_status(results[-1]), 'UNKNOWN')

    def test_settings_after_fast_data_do_not_move_utc_or_freshen_imu(self):
        imu = packet(0x20, 0xDA60A0C6, bytes.fromhex('130000000101680101'))
        wire = packet(0x20, SYS, SYS_BYTES)
        with tempfile.TemporaryDirectory() as directory:
            io = WireTransport([fast() + imu + packet(0x20, FMS, FMS_BYTES) + wire[:15], wire[15:]], delay=.1)
            state = self.collector(io, Path(directory) / 'capture').collect()
            self.assertEqual(state.captured_at, NOW + timedelta(seconds=.1))
            self.assertEqual(state.link_age_ms, 0)
            self.assertEqual(state.sensors.imu_sample_age_ms, 19)
            self.assertEqual(state.configuration.system_settings_age_ms, 0)
            self.assertEqual(state.configuration.flight_mode_settings_age_ms, 0)
            self.assertEqual(mode_status(state, 2000), 'UNKNOWN')

    def test_settings_cannot_complete_mandatory_set_or_hide_truncation(self):
        for data in (fast()[:48] + settings(), fast() + settings()[:-1]):
            with tempfile.TemporaryDirectory() as directory:
                io = WireTransport([data])
                with self.assertRaises(UAVTalkLiveError):
                    self.collector(io, Path(directory) / 'capture').collect()

    def test_settings_protocol_rejects_metadata_wrong_instance_and_controls(self):
        io = WireTransport()
        for oid in (FMS | 1, SYS | 1, 0xffffffff):
            with self.assertRaises(UAVTalkLiveError):
                io.request(oid)
            with self.assertRaises(UAVTalkLiveError):
                io.ack(oid, 0)
        for oid in (FMS, SYS):
            with self.assertRaises(UAVTalkLiveError):
                io.ack(oid, 1)
            for kind, payload, instance in ((0x21, b'', 0), (0x23, b'', 0), (0x20, b'bad', 0),
                                             (0x20, FMS_BYTES if oid == FMS else SYS_BYTES, 1)):
                with tempfile.TemporaryDirectory() as directory:
                    transport = WireTransport([fast() + packet(kind, oid, payload, instance)])
                    with self.assertRaises(UAVTalkLiveError):
                        self.collector(transport, Path(directory) / 'capture').collect()
