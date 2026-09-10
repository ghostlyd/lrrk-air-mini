import unittest
from lrrk_litewing_ai import pilot_operator


class KeyboardTests(unittest.TestCase):
    def make(self):
        cls = getattr(pilot_operator, 'KeyboardInput', None)
        self.assertIsNotNone(cls, 'keyboard adapter missing')
        return cls()

    def test_requires_explicit_arm_and_neutral_start(self):
        keys = self.make()
        self.assertEqual(keys.sample(0), (1000,1500,1500,1500,1500,1500,1500,1500))
        keys.press('w'); keys.press('d')
        self.assertEqual(keys.sample(20_000)[:4], (1000,1500,1500,1500))
        keys.press('space')
        self.assertEqual(keys.sample(40_000)[:4], (1000,1500,1500,2000))

    def test_release_centers_axes_and_throttle_holds(self):
        keys = self.make()
        keys.sample(0); keys.press('space'); keys.sample(20_000); keys.release('space')
        keys.press('w'); keys.press('Right'); keys.press('Up'); keys.press('a')
        values = keys.sample(40_000)
        self.assertEqual(values[:4], (1005,2000,1000,1000))
        for key in ('w','Right','Up','a'): keys.release(key)
        self.assertEqual(keys.sample(60_000)[:4], (1005,1500,1500,1500))

    def test_opposed_keys_cancel_and_throttle_clamps(self):
        keys = self.make(); keys.sample(0)
        keys.press('space'); keys.sample(20_000); keys.release('space')
        keys.press('w'); keys.press('s'); keys.press('Left'); keys.press('Right')
        self.assertEqual(keys.sample(40_000)[:2], (1000,1500))
        keys.release('s')
        for tick in range(3, 303): values = keys.sample(tick * 20_000)
        self.assertEqual(values[0], 2000)

    def test_escape_and_focus_loss_permanently_retire_input(self):
        for action in ('escape','focus'):
            keys = self.make(); keys.sample(0)
            if action == 'escape': keys.press('Escape')
            else: keys.stop()
            keys.press('space')
            with self.assertRaises(ValueError): keys.sample(20_000)

    def test_clock_regression_or_stall_retires_input(self):
        for now in (-1,100_000,True,1.5):
            keys = self.make(); keys.sample(0)
            with self.assertRaises(ValueError): keys.sample(now)
            with self.assertRaises(ValueError): keys.sample(20_000)

    def test_modifier_changes_release_the_same_letter(self):
        for letter in ('w','s','a','d'):
            keys = self.make(); keys.sample(0)
            keys.press('space'); keys.sample(20_000); keys.release('space')
            keys.press(letter); keys.sample(40_000); keys.release(letter.upper())
            previous = keys.sample(60_000)
            self.assertEqual(keys.sample(80_000), previous)
            self.assertEqual(previous[3],1500)

    def test_ordinary_yaw_at_minimum_never_requests_rearm(self):
        keys = self.make(); keys.sample(0)
        keys.press('space'); self.assertEqual(keys.sample(20_000)[3],2000)
        keys.release('space'); keys.press('d')
        self.assertEqual(keys.sample(40_000)[3],1500)
        keys.press('space'); self.assertEqual(keys.sample(60_000)[3],2000)
        keys.release('space'); self.assertEqual(keys.sample(80_000)[3],1500)

    def test_yaw_rearm_guard_covers_entire_negative_throttle_range(self):
        keys = self.make(); keys.sample(0)
        keys.press('space'); keys.sample(20_000); keys.release('space')
        keys.press('W'); keys.press('D')
        for tick in range(2,101):
            values = keys.sample(tick*20_000)
            self.assertLess(values[0],1500)
            self.assertEqual(values[3],1500)
        self.assertEqual(keys.sample(2_020_000)[:4],(1500,1500,1500,2000))
        keys.release('W'); keys.press('s')
        self.assertEqual(keys.sample(2_040_000)[3],1500)
