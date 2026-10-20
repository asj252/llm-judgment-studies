"""Public offline reproduction: registered raw hashes, not raw-file verification."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def public_valid_records(records, sessions, fp_id):
    """Frozen valid_records checks, with only the raw-file loop replaced.

    Raw hashes must be registered for every attempt. No raw path is opened.
    The frozen analyser still checks materials, planned units and code hashes.
    """
    import run_agy as run
    by_id = {s['session_id']: s for s in sessions if s.get('closed_ok') and not s.get('invalid')
             and s.get('fingerprint_id') == fp_id}
    keep = {}
    found = set()
    for r in records:
        s = by_id.get(r.get('session_id'))
        if s and r.get('fingerprint_id') == fp_id:
            if s.get('unit') != r.get('unit') or s.get('record_sha256') != run.record_hash(r):
                raise run.Stop('checkpoint integrity: ' + str(s['unit']), (s['unit'],))
            for attempt in r.get('attempts', []):
                hashes = attempt.get('meta', {}).get('raw_sha256')
                if not isinstance(hashes, dict) or not hashes or any(
                        not isinstance(suffix, str) or not suffix or
                        not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None
                        for suffix, digest in hashes.items()):
                    raise run.Stop('raw hash registration: ' + r['unit'], (r['unit'],))
            keep[r['unit']] = r
            found.add(r['session_id'])
    if set(by_id) - found:
        raise run.Stop('registered checkpoint result missing', [by_id[sid]['unit'] for sid in set(by_id) - found])
    return keep


def reproduce(target):
    import analyse
    # Scoped replacement in this isolated worker; frozen files stay untouched.
    with patch.object(analyse.run, 'valid_records', public_valid_records):
        actual = analyse.analyse('formal', final=True)
    # Match the frozen entry's JSON serialization (including tuple conversion).
    actual = json.loads(json.dumps(actual, ensure_ascii=False, default=str))
    expected = json.loads((HERE / 'analysis_formal.json').read_text(encoding='utf-8'))
    if actual != expected:
        raise RuntimeError('public reproduction differs from analysis_formal.json')
    with Path(target).open('x', encoding='utf-8') as stream:
        json.dump(actual, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items-text', type=Path, default=HERE.parent / 'data/items_text.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('--out must be a new file')
    if not args.items_text.is_file():
        parser.error('missing items text: follow the top-level README')
    with tempfile.TemporaryDirectory(prefix='dnli-agy-public-') as name:
        root = Path(name)
        shutil.copytree(HERE.parent / 'code', root / 'dnli')
        (root / 'dnli/raw').mkdir()
        shutil.copyfile(args.items_text, root / 'dnli/raw/items_text.json')
        shutil.copytree(HERE, root / 'dnli-agy')
        target = root / 'reproduced.json'
        subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c',
                        'import reproduce_public as p; p.reproduce(' + repr(str(target)) + ')'],
                       cwd=root / 'dnli-agy', check=True)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('xb') as stream:
            stream.write(target.read_bytes())
    print('OK: full frozen analysis matches analysis_formal.json; raw hashes registered, raw files not verified.')


if __name__ == '__main__':
    main()
