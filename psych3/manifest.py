"""Normalize frozen material products; never fetch data or call a subject."""
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

import prompts_c

HERE = Path(__file__).resolve().parent
SOURCES = dict(A='raw_items_a.json', B='raw_items_b.json', C='items_c.json',
               D='items_d.json', E='items_e.json')
ID_FIELDS = ('unit_id', 'exp', 'item_id', 'cluster', 'split', 'round', 'ask',
             'parser', 'prompt_sha256')
# New, independent streams for metadata absent from the existing generators.
C_REPEAT_SEED, E_SPLIT_SEED, E_REPEAT_SEED = 20261412, 20261460, 20261461


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ids_only(rows):
    return [{k: row[k] for k in ID_FIELDS} for row in rows]


def build_manifest(base=HERE):
    base = Path(base)
    stories = {s['id']: s for s in prompts_c.load_stories(base / 'baserate_stories.json')}
    rows = []
    for exp, filename in SOURCES.items():
        data = json.loads((base / filename).read_text(encoding='utf-8'))
        items = data['items']
        c_repeat = set(random.Random(C_REPEAT_SEED).sample(
            sorted({i['story'] for i in items if i['use'] == 'formal'}), 4)) if exp == 'C' else set()
        e_ids = sorted(i['item_id'] for i in items) if exp == 'E' else []
        e_dev = set(random.Random(E_SPLIT_SEED).sample(e_ids, 8)) if e_ids else set()
        e_repeat = set(random.Random(E_REPEAT_SEED).sample(
            sorted(set(e_ids) - e_dev), 4)) if e_ids else set()
        for item in items:
            item_id = str(item.get('item_id', item.get('id', item.get('original_id'))))
            split = item.get('split', item.get('use'))
            if exp == 'E':
                split = 'dev' if item_id in e_dev else 'formal'
            cluster = item['story'] if exp == 'C' else item_id
            repeat = (item.get('repeat', False) or cluster in c_repeat or item_id in e_repeat)
            for source in item['units']:
                prompt = source.get('prompt')
                if exp == 'C':
                    prompt = prompts_c.render(stories[item['story']], source['br'],
                                              source['acc_set'], source['format'], source['ask'])
                digest = sha(prompt.encode('utf-8'))
                if source.get('prompt_sha256', digest) != digest:
                    raise ValueError('prompt hash mismatch: ' + item_id)
                original = source.get('unit_id', source.get('unit'))
                rnd = source.get('round', 'r0')
                if not original.endswith(('|r0', '|r1')):
                    original += '|' + rnd
                parser = 'parse_a' if exp == 'A' else (
                    'parse_d' if exp == 'D' and source['pres'] == 'J' else 'dnli_v2')
                row = dict(exp=exp, unit_id=exp + ':' + original, item_id=item_id,
                           cluster=cluster, split=split, round=rnd, ask=source['ask'],
                           parser=parser, prompt=prompt, prompt_sha256=digest)
                if exp == 'A':
                    row['quantity_unit'] = item['unit']
                if parser == 'parse_d':
                    row['order'] = source['order']
                rows.append(row)
                # A already includes r1. Other products only mark repeat membership.
                if exp != 'A' and repeat and split == 'formal' and rnd == 'r0':
                    rows.append(dict(row, unit_id=row['unit_id'][:-2] + 'r1', round='r1'))
    if len({r['unit_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate unit_id')
    if any(r['split'] not in ('dev', 'formal') for r in rows):
        raise ValueError('unknown split')
    return rows


def write_manifest(rows, base=HERE):
    base = Path(base)
    for name, data in [('raw_manifest.json', rows), ('manifest_ids.json', ids_only(rows))]:
        (base / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                                 encoding='utf-8', newline='\n')


def main():
    rows = build_manifest()
    write_manifest(rows)
    for key, count in sorted(Counter((r['exp'], r['split'], r['round']) for r in rows).items()):
        print(*key, count)


if __name__ == '__main__':
    main()
