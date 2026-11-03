"""Atomic sessions, fail-closed locks, append/fsync terminal records."""
import json
import os
import threading
import uuid
from pathlib import Path

from common import atomic_json, canonical, digest, read_json
from deadline import timestamp


class Ledger:
    def __init__(self, path, pid_alive=None):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.results = self.path / "results.jsonl"
        self.sessions_path = self.path / "sessions.json"
        self.lock_path = self.path / "run.lock"
        self.pid_alive = pid_alive or (lambda pid: True)
        self.locked, self.seq = False, 0
        self.commit_lock = threading.Lock()
        self.sessions = read_json(self.sessions_path) if self.sessions_path.exists() else {}

    def acquire(self):
        if self.lock_path.exists():
            old = read_json(self.lock_path)
            if self.pid_alive(old["pid"]):
                raise ValueError("run.lock belongs to a live or unverifiable process")
            os.replace(self.lock_path, self.path / ("run.lock.stale-" + uuid.uuid4().hex))
        with self.lock_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical({"pid": os.getpid()}) + "\n")
        self.locked = True

    def release(self):
        if self.locked:
            self.lock_path.unlink()
            self.locked = False

    def recover_sessions(self):
        for row in self.sessions.values():
            if row["state"] == "open":
                row.update(state="invalid", reason="unclosed session")
        atomic_json(self.sessions_path, self.sessions)

    def load(self, repair=False):
        if not self.results.exists():
            return []
        raw = self.results.read_bytes()
        lines = raw.splitlines(keepends=True)
        parsed, seen, previous_seq = [], set(), 0
        for idx, line in enumerate(lines):
            try:
                row = json.loads(line.decode("utf-8"))
                if not line.endswith(b"\n"):
                    raise ValueError("incomplete terminal line")
            except (ValueError, UnicodeError):
                if idx == len(lines) - 1 and repair:
                    corrupt = self.results.with_name(self.results.name + ".corrupt-" + uuid.uuid4().hex)
                    corrupt.write_bytes(line)
                    tmp = self.results.with_name("results.repaired.tmp")
                    tmp.write_bytes(b"".join(lines[:idx]))
                    os.replace(tmp, self.results)
                    atomic_json(self.path / "repair_log.json", {"quarantined": corrupt.name, "written_at": timestamp()})
                    break
                raise ValueError(f"corrupt ledger line {idx + 1}")
            if not isinstance(row, dict) or type(row.get("commit_seq")) is not int or row["commit_seq"] <= previous_seq:
                raise ValueError(f"invalid commit_seq at line {idx + 1}")
            previous_seq = row["commit_seq"]
            self.seq = previous_seq
            session = self.sessions.get(row["session_id"])
            if not session:
                raise ValueError("record references unknown session")
            if session["state"] in ("invalid", "open"):
                continue
            key = row["unit_key"]
            if key in seen:
                raise ValueError("duplicate terminal unit in valid sessions")
            seen.add(key)
            parsed.append(row)
        return parsed

    def begin(self, run_id):
        sid = uuid.uuid4().hex
        self.sessions[sid] = {"state": "open", "run_id": run_id, "started_at": timestamp()}
        atomic_json(self.sessions_path, self.sessions)
        return sid

    def finish(self, sid, reason):
        self.sessions[sid].update(state="closed", reason=reason, ended_at=timestamp())
        atomic_json(self.sessions_path, self.sessions)

    def commit(self, row, guard, hook=None):
        with self.commit_lock:
            if hook:
                hook("locked")
            if guard.poll():
                return False
            self.seq += 1
            row["commit_seq"] = self.seq
            line = canonical(row) + "\n"
            if hook:
                hook("authorized")
            with self.results.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            if hook:
                hook("written")
            return True


def ledger_digest(records):
    return digest(sorted(records, key=lambda r: r["unit_key"]))
