import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_codex_psych3 as W  # noqa: E402


class CodexPinTests(unittest.TestCase):
    def test_pin_replaces_only_expected_version(self):
        subject = W.pin_version()
        self.assertEqual(subject.EXPECTED_VERSION, json.loads(
            (HERE / "codex_pin.json").read_text(encoding="utf-8"))["version"])
        # codex_subject imports the same module object, so it sees the pinned version.
        sys.path.insert(0, str(HERE.parent / "dnli"))
        import codex_subject
        self.assertIs(codex_subject.subject, subject)

    def test_each_call_rechecks_version(self):
        subject = W.pin_version()
        CS = W.recheck_each_call(subject)
        self.assertIs(W.recheck_each_call(subject), CS)  # idempotent, no double wrap
        fake = CS.CodexSubject.__new__(CS.CodexSubject)
        fake.exe = "codex.exe"
        orig_small, orig_call = subject._run_small, subject.call
        calls = []
        try:
            subject.call = lambda *a, **k: calls.append(a) or "called"
            subject._run_small = lambda exe, args, timeout=120: ("codex-cli 9.9.9", "")
            with self.assertRaises(RuntimeError):
                CS.CodexSubject.call(fake, "p", "t")
            self.assertEqual(calls, [])
        finally:
            subject._run_small, subject.call = orig_small, orig_call

    def test_refuses_non_codex_config(self):
        self.assertEqual(W.main(["dev", "qwen3-off"]), 2)
        self.assertEqual(W.main(["dev"]), 2)


if __name__ == "__main__":
    unittest.main()
