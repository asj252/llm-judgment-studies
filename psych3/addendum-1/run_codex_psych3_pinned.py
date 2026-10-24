"""Pinned executable and stable metadata; catalog entries are separate session records."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
# Isolated mode (-I) drops the script directory from sys.path.
sys.path.insert(0, str(HERE))
import run_codex_psych3 as legacy
import run_psych3 as legacy_runner

pin_version = legacy.pin_version
recheck_each_call = legacy.recheck_each_call


def executable_config(base=HERE):
    config = json.loads((Path(base) / 'codex_exe.json').read_text(encoding='utf-8'))
    exe = Path(config['exe'])
    if not exe.is_absolute() or not re.fullmatch('[0-9a-f]{64}', config['sha256']):
        raise RuntimeError('codex_exe.json requires an absolute exe and lowercase SHA-256')
    return config


def verified_exe(base=HERE, *, config=None):
    config = executable_config(base) if config is None else config
    exe = Path(config['exe'])
    with exe.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != config['sha256']:
        raise RuntimeError('codex executable SHA-256 mismatch')
    if not exe.with_name('codex-code-mode-host.exe').is_file():
        raise RuntimeError('codex-code-mode-host.exe missing beside pinned executable')
    return exe


@contextmanager
def session_metadata(codex_subject, config, stage, base=HERE):
    """Keep the catalog outside metadata and index it before the first attempt.

    freeze_codex obtains the entry once. The runner's first save of the new
    running session supplies its actual ID/start time, without altering run_meta.
    """
    original_freeze = codex_subject.freeze_codex
    original_save = legacy_runner.save_json
    meta_path = Path(base) / f'run_meta_{stage}_codex.json'
    record = None
    indexed = set()

    def freeze(exe):
        nonlocal record
        meta = dict(original_freeze(exe))
        entry = meta.pop('model_entry')
        text = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if meta.pop('model_entry_sha256') != sha:
            raise RuntimeError('codex model entry SHA-256 mismatch')
        stamp = datetime.now(timezone.utc)
        directory = Path(base) / 'raw/codex_model_entry_sessions'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{stamp:%Y%m%dT%H%M%S%fZ}_{sha[:16]}.json'
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        record = dict(time=stamp.isoformat(), stage=stage, sha256=sha,
                      path=path.relative_to(base).as_posix())
        meta['exe_sha256'] = config['sha256']
        return meta

    def save(path, data):
        if Path(path) == meta_path and record is not None:
            for session in data.get('sessions', []):
                sid = session['session_id']
                if session.get('status') == 'running' and sid not in indexed:
                    line = dict(record, session_id=sid, session_started=session['started'])
                    index = Path(base) / 'raw/codex_model_entry_sessions/index.jsonl'
                    with index.open('a', encoding='utf-8', newline='\n') as stream:
                        stream.write(json.dumps(line, ensure_ascii=False) + '\n')
                    indexed.add(sid)
        return original_save(path, data)

    with patch.object(codex_subject, 'freeze_codex', freeze), \
            patch.object(legacy_runner, 'save_json', save):
        yield


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[1] != 'codex':
        print('REFUSED: run_codex_psych3_pinned.py only supports codex')
        return 2
    try:
        config = executable_config(HERE)
        exe = verified_exe(HERE, config=config)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f'REFUSED: {exc}')
        return 2
    subject = pin_version()
    codex_subject = recheck_each_call(subject)
    with patch.object(subject, 'find_codex', return_value=exe), \
            session_metadata(codex_subject, config, argv[0], HERE):
        return legacy_runner.main(argv)


if __name__ == '__main__':
    sys.exit(main())
