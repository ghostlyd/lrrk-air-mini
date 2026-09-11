"""USB observations retain their source rather than impersonating Wi-Fi."""
import unittest

from test_advisory_handoff import observation
from lrrk_litewing_ai import advisory_handoff
from lrrk_litewing_ai.tools import AssistantRuntime


class USBAdvisoryTests(unittest.TestCase):
    def test_usb_observation_reaches_runtime_without_board_clock(self):
        observation_type = getattr(advisory_handoff, 'USBObservation', None)
        self.assertIsNotNone(observation_type, 'USB handoff is missing')
        # The snapshot is opaque to the inbox, which must preserve it exactly.
        snapshot = observation().snapshot
        item = observation_type(snapshot)
        inbox = advisory_handoff.AdvisoryTelemetryInbox()
        runtime = AssistantRuntime()
        self.assertTrue(inbox.offer(item))
        self.assertIs(inbox.ingest_latest(runtime), item)
        self.assertIs(runtime.latest, snapshot)
        self.assertIsNone(item.serialized_us)
        self.assertIsNone(item.sample_age_us)

    def test_usb_observation_rejects_non_snapshot(self):
        observation_type = getattr(advisory_handoff, 'USBObservation', None)
        self.assertIsNotNone(observation_type, 'USB handoff is missing')
        for invalid in (None, {}, b'raw serial'):
            with self.assertRaises(TypeError):
                observation_type(invalid)
