"""Preflight decisions without a real host or queue."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_preflight_macos as preflight


class PreflightTests(unittest.TestCase):
    def invoke(self, factory):
        output = io.StringIO()
        with patch.object(preflight, "make_host", factory), contextlib.redirect_stdout(output):
            result = preflight.main()
        return result, json.loads(output.getvalue())

    def test_only_literal_true_is_accepted(self):
        for ok in (True, False, 1, "yes", None, [], {}):
            with self.subTest(ok=ok):
                host = Mock()
                host.busy_check.return_value = (ok, {"reason": "fixture"})
                factory = Mock(return_value=host)
                code, output = self.invoke(factory)
                self.assertEqual(code, 0 if ok is True else 1)
                self.assertIs(output["ok"], ok is True)
                self.assertEqual(output["detail"], {"reason": "fixture"})
                factory.assert_called_once_with("macmini-m6")
                host.busy_check.assert_called_once_with()

    def test_host_and_busy_check_exceptions_fail_closed(self):
        for at_factory in (True, False):
            with self.subTest(at_factory=at_factory):
                host = Mock()
                host.busy_check.side_effect = RuntimeError("fixture failure")
                factory = Mock(side_effect=RuntimeError("fixture failure")) if at_factory else Mock(return_value=host)
                code, output = self.invoke(factory)
                self.assertEqual(code, 1)
                self.assertFalse(output["ok"])
                self.assertIn("fixture failure", output["detail"]["reason"])


if __name__ == "__main__":
    unittest.main()
