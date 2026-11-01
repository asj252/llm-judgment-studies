"""Experiment-local UTF-8/LF persistence and canonical hashing."""
import hashlib
import json
import math
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": repr(value)}
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n"))


def write_json(path, value):
    write_text(path, json.dumps(json_safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    write_json(tmp, value)
    os.replace(tmp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@contextmanager
def scratch(parent=None):
    """Retain unique test evidence; default mkdir permissions work in managed ACLs."""
    path = Path(parent or ROOT / "raw" / "tmp") / uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path
