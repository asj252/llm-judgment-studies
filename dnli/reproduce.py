"""Reproduce in a temporary legacy layout without changing frozen evidence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items-text', type=Path, default=ROOT / 'data/items_text.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('--out must be a new file')
    if not args.items_text.is_file():
        parser.error('missing items text: follow README reconstruction instructions')
    with tempfile.TemporaryDirectory(prefix='dnli-reproduce-') as name:
        work = Path(name) / 'dnli'
        shutil.copytree(ROOT / 'code', work)
        (work / 'raw').mkdir()
        shutil.copyfile(args.items_text, work / 'raw/items_text.json')
        shutil.copytree(ROOT / 'vs-pilot', Path(name) / 'vs-pilot')
        target = work / 'reproduced.json'
        subprocess.run([sys.executable, '-X', 'utf8', '-B', str(work / 'analyse.py'),
                        'run', 'formal', str(target), '--final'], cwd=work, check=True)
        expected = json.loads((ROOT / 'code/analysis_formal.json').read_text(encoding='utf-8'))
        actual = json.loads(target.read_text(encoding='utf-8'))
        if actual != expected:
            raise RuntimeError('reproduced analysis differs from the archived analysis')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('xb') as dst:
            dst.write(target.read_bytes())
    print('Full frozen analysis matches the archived JSON.')


if __name__ == '__main__':
    main()
