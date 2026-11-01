"""Legacy local deadlines and absolute timezone-aware deadlines."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deadline import Deadline, Interrupted, SHANGHAI, deadline_epoch


class DeadlineParsing(unittest.TestCase):
    def test_unset_and_legacy_shanghai_day(self):
        now = datetime.fromisoformat("2026-10-29T23:59:00+08:00").timestamp()
        self.assertIsNone(deadline_epoch(None, now=now))
        expected = datetime.fromisoformat("2026-10-29T01:30:00+08:00").timestamp()
        self.assertEqual(deadline_epoch("01:30", now=now), expected)

    def test_absolute_future_day_and_equivalent_timezone(self):
        now = datetime.fromisoformat("2026-10-29T23:59:00+08:00").timestamp()
        expected = datetime.fromisoformat("2026-10-30T01:30:00+08:00").timestamp()
        self.assertEqual(deadline_epoch("2026-10-30T01:30:00+08:00", now=now), expected)
        self.assertEqual(deadline_epoch("2026-10-29T17:30:00+00:00", now=now), expected)
        self.assertEqual(datetime.fromtimestamp(expected, SHANGHAI).day, 30)

    def test_invalid_and_naive_iso_rejected(self):
        for value in ("bad", "25:00", "2026-10-30", "2026-10-30T01:30:00",
                      "2026-02-30T01:30:00+08:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                deadline_epoch(value)

    def test_absolute_deadline_keeps_dispatch_and_hard_stop_boundaries(self):
        at = deadline_epoch("2026-10-30T01:30:00+08:00")
        now = [at - 900 - .001]
        guard = Deadline(at, now=lambda: now[0])
        self.assertTrue(guard.can_start())
        now[0] = at - 900
        self.assertFalse(guard.can_start())
        now[0] = at
        with self.assertRaises(Interrupted):
            guard.check()


if __name__ == "__main__":
    unittest.main()
