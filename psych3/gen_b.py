"""Read external JSON as data; clean both canary files, pair, and render B."""
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Isolated execution admits only this trusted code directory, never raw_data.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_a import write_json
from prompts_b import ASKS, CONDITIONS, render

ROOT = Path(__file__).resolve().parent
SEED, REPEAT_SEED = 20261450, 20261451


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def clean_canaries(root=ROOT):
    """Keep original non-canary bytes; separate sources, never double human ratings."""
    logs, cleaned = [], {}
    for path in sorted((root / 'raw_data/probcopa').glob('*_CANARY.jsonl')):
        before = path.read_bytes()
        lines = before.splitlines(keepends=True)
        keep = [line for line in lines if json.loads(line).get('type') != 'canary']
        after = b''.join(keep)
        cleaned[path.name] = [json.loads(line) for line in keep]
        output = 'raw_probcopa_clean.jsonl' if path.name == 'probcopa_CANARY.jsonl' else 'raw_probcopa_human_clean.jsonl'
        (root / output).write_bytes(after)
        logs.append({'source': path.name, 'output': output, 'before_rows': len(lines), 'after_rows': len(keep),
                     'removed_rows': len(lines) - len(keep), 'before_sha256': sha(before), 'after_sha256': sha(after)})
    if len(logs) != 2:
        raise ValueError('Expected exactly two canary sources')
    write_json(root / 'b_canary_log.json', {'rule': 'remove type == canary; preserve retained line bytes', 'sources': logs})
    return cleaned, logs


def pair_items(rows):
    by_id = defaultdict(list)
    uid_counts = Counter(row['UID'] for row in rows)
    for row in rows:
        by_id[row['original_id']].append(row)
    pairs, log = [], []
    for original_id, group in sorted(by_id.items()):
        group = sorted(group, key=lambda x: x['UID'])
        reasons = []
        if len(group) != 2:
            reasons.append('not_two_outcomes')
        if len({r['premise'] for r in group}) != 1:
            reasons.append('premise_mismatch')
        if any(uid_counts[r['UID']] != 1 for r in group):
            reasons.append('duplicate_UID')
        if any(r['asks-for'] != 'effect' for r in group):
            reasons.append('not_effect')
        if len({r['hypothesis'] for r in group}) != 2:
            reasons.append('non_distinct_outcomes')
        log.append({'original_id': original_id, 'UIDs': [r['UID'] for r in group],
                    'status': 'failed' if reasons else 'paired', 'reasons': reasons})
        if not reasons:
            pairs.append({'original_id': original_id, 'UIDs': [r['UID'] for r in group],
                          'premise': group[0]['premise'], 'outcomes': [r['hypothesis'] for r in group]})
    return pairs, log


def human_summary(rows, items):
    """Use cleaned annotated ratings once. Expose repeated worker rows and ID drift."""
    by_uid = defaultdict(list)
    item_by_uid = {r['UID']: r for r in items}
    for row in rows:
        if row.get('type') == 'canary':
            raise ValueError('Canary reached human aggregation')
        if row['UID'] not in item_by_uid:
            raise ValueError('Unknown rating UID')
        item = item_by_uid[row['UID']]
        if any(row[k] != item[k] for k in ('premise', 'hypothesis')):
            raise ValueError('Rating text does not match UID')
        value = row['response']
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('Invalid human response')
        by_uid[row['UID']].append(row)
    summaries = []
    for uid in sorted(item_by_uid):
        group = by_uid[uid]
        values = [r['response'] for r in group]
        n_people = len({str(r['workerid']) for r in group})
        summaries.append({'UID': uid, 'n_people': n_people, 'n_ratings': len(group),
                          'duplicate_worker_rows': len(group) - n_people,
                          'mean': statistics.mean(values) if values else None,
                          'median': statistics.median(values) if values else None,
                          'original_id_mismatch_rows': sum(r['original_id'] != item_by_uid[uid]['original_id'] for r in group)})
    return {'source': 'probcopa_human_results_annotated_CANARY.jsonl (cleaned)',
            'rule': 'Each cleaned rating row once, no pooling of overlapping source files; n_people counts unique workerid; no deduplication.',
            'items': summaries}


def generate_items(pairs):
    ids = [p['original_id'] for p in pairs]
    shuffled = ids.copy()
    random.Random(SEED).shuffle(shuffled)
    dev = set(shuffled[:15])
    formal = [i for i in ids if i not in dev]
    repeat = set(random.Random(REPEAT_SEED).sample(formal, min(12, len(formal))))
    raw, manifest = [], []
    for pair in pairs:
        units = []
        for condition in CONDITIONS:
            for k, outcome in enumerate(pair['outcomes'], 1):
                for ask in ASKS:
                    prompt = render(pair['premise'], outcome, condition, ask)
                    units.append({'unit_id': f"B{pair['original_id']}_{condition}_{k}_{ask}",
                                  'condition': condition, 'k': k, 'UID': pair['UIDs'][k - 1], 'ask': ask,
                                  'prompt': prompt, 'prompt_sha256': sha(prompt.encode('utf-8'))})
        meta = {'original_id': pair['original_id'], 'UIDs': pair['UIDs'],
                'split': 'dev' if pair['original_id'] in dev else 'formal', 'repeat': pair['original_id'] in repeat}
        raw.append(dict(meta, units=units))
        manifest.append(dict(meta, units=[{k: v for k, v in unit.items() if k != 'prompt'} for unit in units]))
    return ({'seed': SEED, 'repeat_seed': REPEAT_SEED, 'items': raw},
            {'seed': SEED, 'repeat_seed': REPEAT_SEED, 'items': manifest})


def main():
    cleaned, logs = clean_canaries()
    rows = read_jsonl(ROOT / 'raw_data/probcopa/probcopa_items.jsonl')
    pairs, log = pair_items(rows)
    write_json(ROOT / 'b_pairing.json', log)
    write_json(ROOT / 'raw_b_human.json', human_summary(cleaned['probcopa_human_results_annotated_CANARY.jsonl'], rows))
    raw, manifest = generate_items(pairs)
    write_json(ROOT / 'raw_items_b.json', raw)
    write_json(ROOT / 'b_manifest.json', manifest)
    lines = ['# B preview', '']
    for item in raw['items'][:1]:
        for unit in item['units']:
            lines += [f"## {unit['unit_id']}", '', '```text', unit['prompt'], '```', '']
    (ROOT / 'raw_items_b_preview.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f"B: {len(rows)} rows; {len(pairs)} paired; {sum(x['status'] == 'failed' for x in log)} failed; {sum(len(i['units']) for i in raw['items'])} units")
    for log in logs:
        print(f"{log['source']}: removed {log['removed_rows']}; retained {log['after_rows']}")


if __name__ == '__main__':
    main()
