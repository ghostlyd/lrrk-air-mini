import unittest
from types import SimpleNamespace
from unittest.mock import patch
from lrrk_litewing_ai import keyboard_pilot
from test_keyboard_session import Link
from test_advisory_handoff import observation


class WindowTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
        except Exception:
            self.skipTest('Tk display unavailable')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_explicit_connect_escape_and_no_automatic_reconnect(self):
        cls = getattr(keyboard_pilot, 'KeyboardWindow', None)
        self.assertIsNotNone(cls, 'keyboard window missing')
        links = []
        def connect():
            link = Link(); links.append(link); return link
        window = cls(self.root, connect, demo=True)
        self.assertEqual(links, [])
        window.connect()
        self.assertEqual(len(links), 1)
        window.key_press(SimpleNamespace(keysym='Escape'))
        window.poll()
        self.assertTrue(links[0].closed)
        self.assertEqual(len(links), 1)

    def test_window_displays_real_observation_as_historical(self):
        window = keyboard_pilot.KeyboardWindow(self.root, Link, demo=True)
        window.connect()
        window.session.observation = observation()
        window.poll()
        self.assertIn('Historical telemetry', window.observed.get())
        self.assertIn('armed=False', window.observed.get())
        window.stop()

    def test_worker_start_failure_retires_admitted_link(self):
        link = Link()
        window = keyboard_pilot.KeyboardWindow(self.root, lambda: link, demo=True)
        with patch('threading.Thread.start',side_effect=RuntimeError('unavailable')):
            window.connect()
        self.assertTrue(link.closed)
        self.assertTrue(window.session is None or window.session.closed)
        self.assertIn('unavailable',window.status.get())
