#!/Volumes/2026General_Space/imperfective/venv/bin/python -I
"""Check the queue window immediately before replacing this process with S3."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEADLINE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+08:00")


def main(argv=None, *, now=None, execv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("smoke", "verify"))
    parser.add_argument("--deadline-at", required=True)
    args = parser.parse_args(argv)
    try:
        if not DEADLINE_FORMAT.fullmatch(args.deadline_at):
            raise ValueError("deadline-at must be a full ISO datetime with +08:00 timezone")
        deadline = datetime.fromisoformat(args.deadline_at)
        current = datetime.now(SHANGHAI) if now is None else now()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("current time must have a timezone")
        current = current.astimezone(SHANGHAI)
        if current >= deadline - timedelta(seconds=900):
            raise ValueError("deadline has less than the required 15-minute margin")
    except (ValueError, OverflowError) as exc:
        print(json.dumps({"ok": False, "detail": {"reason": str(exc)}}, ensure_ascii=False))
        return 1
    command = [sys.executable, "-I", "-X", "utf8", "-B", str(ROOT / "run.py"),
               args.stage, "qwen3-8b@macmini-m6", "--deadline", args.deadline_at]
    # execv keeps this process and its inheritable queue lock descriptors alive.
    (os.execv if execv is None else execv)(sys.executable, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
