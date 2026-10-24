"""Snapshot the pinned codex CLI's catalog entry for the subject model (no model call).

Saves raw/codex_model_entry_samples/<YYYYmmdd-HHMMSS>.json and appends one line to index.jsonl
(time, sha256 of the full entry and of each top-level field), so drift between snapshots can be
attributed to specific fields. Used to decide which fields the re-frozen codex fingerprint binds.
"""
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE = json.loads((HERE / 'codex_exe.json').read_text(encoding='utf-8'))['exe']
MODEL = 'gpt-6.1-sol'
OUT = HERE / 'raw' / 'codex_model_entry_samples'


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main():
    proc = subprocess.run([EXE, 'debug', 'models'], capture_output=True, timeout=120)
    data = json.loads(proc.stdout.decode('utf-8').lstrip('﻿'))
    models = data['models'] if isinstance(data, dict) else data
    entries = [m for m in models if isinstance(m, dict) and m.get('slug') == MODEL]
    if len(entries) != 1:
        raise SystemExit('model entry for %s not found exactly once' % MODEL)
    entry = entries[0]
    text = canon(entry)
    stamp = dt.datetime.now().astimezone()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (stamp.strftime('%Y%m%d-%H%M%S') + '.json')).write_text(text, encoding='utf-8', newline='\n')
    line = dict(time=stamp.isoformat(timespec='seconds'), sha256=sha(text),
                fields={k: sha(canon(v)) for k, v in sorted(entry.items())})
    with (OUT / 'index.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(line, ensure_ascii=False) + '\n')
    print(line['time'], line['sha256'][:16])


if __name__ == '__main__':
    main()
