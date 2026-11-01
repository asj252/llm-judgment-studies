"""Absolute queue deadline and exec handoff, without loading the runner."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_s3_stage_macos as stage

DEADLINE = "2026-10-29T23:55:00+08:00"


class StageTests(unittest.TestCase):
    def invoke(self, current, deadline=DEADLINE, name="smoke"):
        execute = Mock()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = stage.main(["--stage", name, "--deadline-at", deadline],
                              now=lambda: datetime.fromisoformat(current), execv=execute)
        return code, execute, output.getvalue()

    def test_success_for_both_stages_exact_exec(self):
        for name in ("smoke", "verify"):
            with self.subTest(stage=name):
                code, execute, _ = self.invoke("2026-10-29T23:39:59.999999+08:00", name=name)
                self.assertEqual(code, 0)
                execute.assert_called_once_with(sys.executable, [sys.executable, "-I", "-X", "utf8", "-B",
                    str(stage.ROOT / "run.py"), name, "qwen3-8b@macmini-m6", "--deadline", DEADLINE])

    def test_rejected_times_never_exec(self):
        for current in ("2026-10-29T23:40:00+08:00", "2026-10-29T23:55:00+08:00",
                        "2026-10-29T23:59:00+08:00", "2026-10-30T00:00:00+08:00",
                        "2026-10-29T12:00:00"):
            with self.subTest(current=current):
                code, execute, output = self.invoke(current)
                self.assertEqual(code, 1)
                execute.assert_not_called()
                self.assertFalse(json.loads(output)["ok"])

    def test_invalid_deadlines_never_exec(self):
        for value in ("bad", "23:55", "2026-10-29T23:55:00", "2026-10-29T15:55:00Z",
                      "2026-10-29T23:55:00+09:00", "2026-10-29T23:55:00+0800",
                      "2026-10-29 23:55:00+08:00", "2026-02-30T23:55:00+08:00",
                      "2026-10-29T24:55:00+08:00"):
            with self.subTest(value=value):
                code, execute, _ = self.invoke("2026-10-29T12:00:00+08:00", deadline=value)
                self.assertEqual(code, 1)
                execute.assert_not_called()

    def test_now_is_compared_in_shanghai(self):
        code, execute, _ = self.invoke("2026-10-29T15:39:59+00:00")
        self.assertEqual(code, 0)
        execute.assert_called_once()

    def test_future_cross_midnight_deadline_is_forwarded_in_full(self):
        deadline = "2026-10-30T01:30:01.123456+08:00"
        for name in ("smoke", "verify"):
            with self.subTest(stage=name):
                code, execute, _ = self.invoke("2026-10-29T23:59:59+08:00", deadline=deadline, name=name)
                self.assertEqual(code, 0)
                self.assertEqual(execute.call_args.args[1][-2:], ["--deadline", deadline])

    def test_cross_midnight_cutoff_boundaries(self):
        deadline = "2026-10-30T01:30:00+08:00"
        for current, accepted in (("2026-10-30T01:14:59.999999+08:00", True),
                                  ("2026-10-30T01:15:00+08:00", False),
                                  ("2026-10-30T01:30:00+08:00", False),
                                  ("2026-10-31T00:00:00+08:00", False)):
            with self.subTest(current=current):
                code, execute, _ = self.invoke(current, deadline=deadline)
                self.assertEqual(code, 0 if accepted else 1)
                self.assertEqual(execute.call_count, int(accepted))

    def test_invalid_stage_and_missing_arguments(self):
        for args in ([], ["--stage", "dev", "--deadline-at", DEADLINE], ["--stage", "smoke"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), patch.object(stage.os, "execv") as execute:
                with self.assertRaises(SystemExit) as caught:
                    stage.main(args)
                self.assertEqual(caught.exception.code, 2)
                execute.assert_not_called()

    def test_inheritable_lock_descriptor_is_untouched(self):
        with tempfile.TemporaryFile() as lock:
            fd = lock.fileno()
            os.set_inheritable(fd, True)
            execute = Mock(side_effect=lambda *_: self.assertTrue(os.get_inheritable(fd)))
            with patch.object(stage.os, "close") as close:
                self.assertEqual(stage.main(["--stage", "smoke", "--deadline-at", DEADLINE],
                    now=lambda: datetime.fromisoformat("2026-10-29T12:00:00+08:00"), execv=execute), 0)
                close.assert_not_called()
            execute.assert_called_once()
            self.assertTrue(os.get_inheritable(fd))


if __name__ == "__main__":
    unittest.main()
