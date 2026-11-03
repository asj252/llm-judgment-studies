#!/Volumes/2026General_Space/imperfective/venv/bin/python -I
"""Queue preflight; only an explicitly idle Mac host is accepted."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_macos import make_host


def main():
    try:
        ok, detail = make_host("macmini-m6").busy_check()
        accepted = ok is True
        print(json.dumps({"ok": accepted, "detail": detail}, ensure_ascii=False))
        return 0 if accepted else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "detail": {"reason": f"{type(exc).__name__}: {exc}"}},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
