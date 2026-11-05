"""Absolute deadline: watchdog never waits for the commit lock."""
from datetime import datetime, timedelta, timezone
import threading
import time

SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")


def timestamp():
    return datetime.now(SHANGHAI).isoformat()


def deadline_epoch(value, now=None):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("ISO deadline must include a timezone")
        return parsed.timestamp()
    local = datetime.fromtimestamp(time.time() if now is None else now, SHANGHAI)
    return local.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0).timestamp()


class Interrupted(Exception):
    pass


class Deadline:
    def __init__(self, at=None, now=time.time):
        self.at, self.now = at, now
        self.expired, self.done = threading.Event(), threading.Event()
        self.subject, self.thread, self.exit_code = None, None, None

    def attach(self, subject):
        self.subject = subject
        subject.deadline = self
        self.poll()
        if self.expired.is_set():
            self._terminate()

    def _terminate(self):
        if self.subject is not None and self.subject.proc is not None:
            self.exit_code = self.subject.host.terminate(self.subject.proc)

    def poll(self):
        if self.at is not None and self.now() >= self.at:
            self.expired.set()
            self._terminate()
        return self.expired.is_set()

    def start(self):
        if self.at is None:
            return

        def watch():
            while not self.done.is_set():
                if self.poll():
                    return
                self.done.wait(min(0.05, max(0, self.at - self.now())))

        self.thread = threading.Thread(target=watch, daemon=True)
        self.thread.start()

    def check(self):
        if self.poll():
            raise Interrupted("deadline interruption")

    def timeout(self):
        self.check()
        return 600.0 if self.at is None else min(600.0, max(0, self.at - self.now()))

    def can_start(self):
        self.check()
        return self.at is None or self.now() < self.at - 900

    def close(self):
        self.done.set()
        if self.thread:
            self.thread.join(timeout=31)
