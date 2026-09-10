import importlib.util
import unittest


class Link:
    """Scripted transport boundary; no networking or authentication claim."""
    def __init__(self):
        self.samples = []
        self.stops = 0
        self.closed = False
    def step(self, sample): self.samples.append(sample())
    def take_telemetry(self): return None
    def stop(self): self.stops += 1; self.closed = True; return True
    def close(self): self.closed = True


class SessionTests(unittest.TestCase):
    def make(self, link):
        self.assertIsNotNone(importlib.util.find_spec('lrrk_litewing_ai.keyboard_pilot'))
        from lrrk_litewing_ai.keyboard_pilot import KeyboardSession
        return KeyboardSession(link, lambda: self.now)

    def setUp(self): self.now = 0

    def test_focus_loss_stops_before_another_sample_and_cannot_resume(self):
        link = Link(); session = self.make(link)
        session.tick(True)
        self.assertEqual(link.samples[0][0], 1000)
        session.tick(False); session.tick(True)
        self.assertEqual(len(link.samples), 1)
        self.assertEqual(link.stops, 1)
        self.assertTrue(session.closed)

    def test_escape_uses_stop_not_another_pilot_sample(self):
        link = Link(); session = self.make(link)
        session.press('Escape'); session.tick(True)
        self.assertEqual(link.samples, [])
        self.assertEqual(link.stops, 1)

    def test_transport_failure_closes_link_and_retires_input(self):
        class FailedLink(Link):
            def step(self, sample): raise OSError('private address')
            def stop(self): raise OSError('private address')
        link = FailedLink(); session = self.make(link)
        session.tick(True)
        self.assertTrue(session.closed)
        self.assertTrue(link.closed)
        self.assertNotIn('private', session.status)
