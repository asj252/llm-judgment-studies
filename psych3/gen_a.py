"""Generate A review materials; pending rows require explicit preview mode."""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

# Isolated execution admits only this trusted code directory, never raw_data.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompts_a import (
    ASKS,
    CONDITIONS,
    anchors,
    load_questions,
    load_selfwritten,
    mechanical_check,
    render,
    validate_selfwritten,
)

ROOT = Path(__file__).resolve().parent
SEED, REPEAT_SEED = 20261440, 20261441
SELF_SEED, SELF_REPEAT_SEED = 20261442, 20261443
SELFWRITTEN_PREVIEW_SPECS = (
    ("none", None, "direct", "无锚直接 (none, direct)"),
    ("irrelevant", "high", "direct", "无关锚高直接 (irrelevant, high, direct)"),
    ("informative", "low", "multi", "有信息锚低多估计 (informative, low, multi)"),
)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _build_units(item_id, source, question, anchor_info, is_repeat):
    rounds = ("r0", "r1") if is_repeat else ("r0",)
    units = []
    for round_id in rounds:
        for condition, level in CONDITIONS:
            for ask in ASKS:
                prompt = render(question, condition, ask, anchor_info[level] if level else None)
                lvl = level or "none"
                units.append({
                    "unit_id": f"{item_id}|{condition}|{lvl}|{ask}|{round_id}",
                    "id": item_id,
                    "item_id": item_id,
                    "source": source,
                    "condition": condition,
                    "anchor_level": level,
                    "level": lvl,
                    "ask": ask,
                    "round": round_id,
                    "prompt": prompt,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                })
    return units


def generate_items(questions, eligibility, selfwritten=None, preview_all=False,
                   seed=SEED, repeat_seed=REPEAT_SEED,
                   self_seed=SELF_SEED, self_repeat_seed=SELF_REPEAT_SEED):
    if isinstance(selfwritten, bool):
        preview_all, selfwritten = selfwritten, None
    if len(eligibility) != len(questions) or [e['index'] for e in eligibility] != list(range(len(questions))):
        raise ValueError("Eligibility must have exactly one ordered row per question")
    if any(e['status'] not in ('pending', 'eligible', 'ineligible') for e in eligibility):
        raise ValueError("Unknown eligibility status")
    if preview_all and any(e['status'] != 'pending' for e in eligibility):
        raise ValueError("Preview-all is only allowed for an entirely pending skeleton")

    syn_indices = [e['index'] for e in eligibility if preview_all or e['status'] == 'eligible']
    if preview_all:
        self_rows = []
    elif selfwritten is None:
        self_rows = load_selfwritten() if len(syn_indices) == 36 else []
    else:
        self_rows = validate_selfwritten(selfwritten) if selfwritten else []
    syn_dev_k = 6 if self_rows else 10
    syn_repeat_k = 5 if self_rows else 8

    syn_shuffled = syn_indices.copy()
    random.Random(seed).shuffle(syn_shuffled)
    dev_syn = set(syn_shuffled[:min(syn_dev_k, len(syn_shuffled))])
    formal_syn = [i for i in syn_indices if i not in dev_syn]
    repeat_syn = set(random.Random(repeat_seed).sample(formal_syn, min(syn_repeat_k, len(formal_syn))))

    self_ids = [row['id'] for row in self_rows]
    self_shuffled = self_ids.copy()
    random.Random(self_seed).shuffle(self_shuffled)
    dev_self = set(self_shuffled[:min(4, len(self_shuffled))])
    formal_self = [i for i in self_ids if i not in dev_self]
    repeat_self = set(random.Random(self_repeat_seed).sample(formal_self, min(3, len(formal_self))))

    items = []
    for index in syn_indices:
        item_id = f"A{index}"
        q = questions[index]
        a = anchors(index, q['true_value'])
        is_dev = index in dev_syn
        is_repeat = index in repeat_syn
        units = _build_units(item_id, "synanchors", q['question'], a, is_repeat)
        items.append({
            "id": item_id,
            "item_id": item_id,
            "index": index,
            "source": "synanchors",
            "split": "dev" if is_dev else "formal",
            "repeat": is_repeat,
            "true_value": q['true_value'],
            "low": a['low'],
            "high": a['high'],
            "rounding_rule": a['rounding_rule'],
            "unit": mechanical_check(q)['unit'],
            "units": units,
        })

    for row in self_rows:
        item_id = row['id']
        a = anchors(item_id, row['true_value'])
        is_dev = item_id in dev_self
        is_repeat = item_id in repeat_self
        units = _build_units(item_id, "selfwritten", row['question'], a, is_repeat)
        items.append({
            "id": item_id,
            "item_id": item_id,
            "source": "selfwritten",
            "split": "dev" if is_dev else "formal",
            "repeat": is_repeat,
            "question": row['question'],
            "true_value": row['true_value'],
            "low": a['low'],
            "high": a['high'],
            "rounding_rule": a['rounding_rule'],
            "unit": row['unit'],
            "time_ref": row.get('time_ref'),
            "reference_version": row.get('reference_version'),
            "status": row['status'],
            "units": units,
        })

    return {
        "seed": seed,
        "repeat_seed": repeat_seed,
        "selfwritten_seed": self_seed,
        "selfwritten_repeat_seed": self_repeat_seed,
        "preview_only": preview_all,
        "n_items": len(items),
        "n_units": sum(len(i['units']) for i in items),
        "items": items,
    }


def selfwritten_payload(data):
    items = [i for i in data['items'] if i.get('source') == 'selfwritten']
    return {
        "seed": data['seed'],
        "repeat_seed": data['repeat_seed'],
        "selfwritten_seed": data['selfwritten_seed'],
        "selfwritten_repeat_seed": data['selfwritten_repeat_seed'],
        "n_items": len(items),
        "n_units": sum(len(i['units']) for i in items),
        "items": items,
    }


def split_records(data):
    return [
        {
            "id": item['id'],
            "source": item['source'],
            "split": item['split'],
            "repeat": item['repeat'],
        }
        for item in data['items']
    ]


def preview_selfwritten(selfwritten):
    rows = selfwritten['items'] if isinstance(selfwritten, dict) else selfwritten
    rows = [r for r in rows if r.get('source', 'selfwritten') == 'selfwritten']
    fence = chr(96) * 3
    lines = [
        "# 实验 A 自编 24 题预览",
        "",
        "每题列出三例完整题面：无锚直接（`none` / `direct`）、"
        "无关锚高直接（`irrelevant` / `high` / `direct`）、"
        "有信息锚低多估计（`informative` / `low` / `multi`）。",
        "",
    ]
    for row in rows:
        a = anchors(row['id'], row['true_value'])
        lines.extend([
            f"## {row['id']} (true_value={row['true_value']}, unit={row['unit']}, low={a['low']}, high={a['high']})",
            "",
        ])
        for condition, level, ask, label in SELFWRITTEN_PREVIEW_SPECS:
            prompt = render(row['question'], condition, ask, a[level] if level else None)
            lines.extend([
                f"### {label}",
                "",
                fence + "text",
                prompt,
                fence,
                "",
            ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview-all', action='store_true', help='Trial only: all 60 pending questions')
    args = parser.parse_args()
    questions = load_questions()
    path = ROOT / 'a_eligibility.json'
    # Preserve a's subsequent decisions on every rerun.
    if not path.exists():
        write_json(path, [{'index': i, 'status': 'pending', 'reason': ''} for i in range(len(questions))])
    eligibility = json.loads(path.read_text(encoding='utf-8'))
    write_json(ROOT / 'a_anchors.json', [anchors(i, q['true_value']) for i, q in enumerate(questions)])
    lines = ['# A mechanical eligibility review', '', 'No eligibility decisions are made here. Indices are zero-based.', '']
    for i, q in enumerate(questions):
        lines += [f'## {i}', '', *[f'- {k}: {json.dumps(q[k], ensure_ascii=False)}' for k in
                  ('question', 'true_value', 'requirement', 'topic')],
                  '- mechanical: ' + json.dumps(mechanical_check(q), ensure_ascii=False), '']
    (ROOT / 'raw_a_eligibility.md').write_text('\n'.join(lines), encoding='utf-8')
    selfwritten = None if args.preview_all else load_selfwritten()
    data = generate_items(questions, eligibility, selfwritten=selfwritten, preview_all=args.preview_all)
    write_json(ROOT / 'raw_items_a.json', data)
    lines = ['# A preview', '', f"preview_only={args.preview_all}", '']
    for item in data['items'][:2]:
        for unit in item['units']:
            lines += [f"## {unit['unit_id']}", '', '```text', unit['prompt'], '```', '']
    (ROOT / 'raw_items_a_preview.md').write_text('\n'.join(lines), encoding='utf-8')
    if not args.preview_all and selfwritten is not None:
        write_json(ROOT / 'items_a_selfwritten.json', selfwritten_payload(data))
        (ROOT / 'items_a_selfwritten_preview.md').write_text(preview_selfwritten(selfwritten), encoding='utf-8')
        write_json(ROOT / 'a_split.json', split_records(data))
    print(f"A: {len(questions)} read; {len(data['items'])} items; {sum(len(i['units']) for i in data['items'])} units; preview_only={args.preview_all}")


if __name__ == '__main__':
    main()

