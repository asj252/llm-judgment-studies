"""Read-only analysis of admitted psych3 records; explicit freeze/run commands.

No subject is constructed. Freeze writes a new entry, refusing changed entries.
guard() is the single hook for paths analysis must not open; it blocks nothing since
the Qwen3 development run closed (the block in brief-e-analysis.md expired 2026-10-22).
"""
import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis_psych3 as A
import run_psych3 as R


class Mismatch(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def guard(path):
    p = Path(path).resolve()
    blocked = []
    if any(p == b.resolve() or b.resolve() in p.parents for b in blocked):
        raise Mismatch('blocked analysis artifact')


def code_binding(B, seed):
    paths = [Path(__file__), Path(A.__file__), HERE/'power_psych3.py', Path(R.__file__), HERE/'manifest.py',
             HERE/'agy_night.py', HERE.parent/'dnli/run.py', HERE.parent/'dnli-agy/run_agy.py']
    return dict(files={str(p.relative_to(HERE.parent)): sha(p) for p in paths}, B=B, seed=seed,
                alpha=A.ALPHA, specs=A.SPECS)


def input_bindings(base):
    """Bind material products and all local runner/parser dependencies, without results."""
    base = Path(base)
    names = ['PLAN.md', 'manifest_ids.json', 'raw_manifest.json', *R.SOURCES.values()] if hasattr(R, 'SOURCES') else [
        'PLAN.md', 'manifest_ids.json', 'raw_manifest.json', 'raw_items_a.json', 'raw_items_b.json', 'items_c.json', 'items_d.json', 'items_e.json']
    names += list(R.FROZEN_MATERIALS)+['raw_probcopa_human_clean.jsonl']
    names += [p.name for pattern in ('prompts_*.py', 'parse_*.py', 'gen_*.py') for p in base.glob(pattern)]
    return {n: sha(base/n) for n in sorted(set(names))}


def paths(base, which, cfg):
    rp, mp, _ = R.paths(Path(base), which, cfg)
    guard(rp)
    guard(mp)
    return rp, mp


def load_valid(results_path, metadata_path, fingerprint_id, cfg, strict=False):
    guard(results_path)
    guard(metadata_path)
    meta = read(metadata_path)
    if cfg.startswith('agy:'):
        import agy_night
        meta = agy_night.checkpoint_meta(Path(metadata_path))
    sessions = meta['sessions']
    records = R.load_records(Path(results_path))
    if strict and any(r.get('fingerprint_id') != fingerprint_id for r in records):
        raise Mismatch('formal result fingerprint differs from freeze')
    by_id = {s['session_id']: s for s in sessions}
    if any(r.get('session_id') not in by_id for r in records):
        raise Mismatch('unregistered result')
    for s in sessions:
        if not s.get('closed_ok') or s.get('invalid') or s['fingerprint_id'] != fingerprint_id:
            continue
        registered = [r for r in records if r['session_id'] == s['session_id']]
        digest = R.sha(json.dumps(registered, sort_keys=True, ensure_ascii=False).encode('utf-8'))
        if s.get('records_sha256') != digest:
            raise Mismatch('closed session result integrity failed')
        for r in registered:
            for attempt in r.get('attempts', []):
                raw = Path(attempt['raw_path'])
                guard(raw)
                if not raw.is_file() or sha(raw) != attempt['raw_sha256']:
                    raise Mismatch('raw attempt integrity failed')
    kept = (R.agy_helpers().valid_records(records, sessions, fingerprint_id) if cfg.startswith('agy:')
            else R.valid_records(records, sessions, fingerprint_id))
    return list(kept.values()), dict(total=len(records), admitted=len(kept), excluded=len(records)-len(kept))


def material_index(base):
    """Map normalized unit IDs to existing products, retaining condition metadata."""
    out = {}
    base = Path(base)
    human_path = base/'raw_probcopa_human_clean.jsonl'
    # PLAN 7.1: mean is primary, median secondary; both descriptive.
    human = {}
    if human_path.exists():
        for line in human_path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            human[row['UID']] = {s: row.get(s+'_response') for s in ('mean', 'median')}
    d_bank = read(base/'conjunction_items.json')
    strata = {r['id']: r.get('stratum') for r in d_bank['event_pairs']}
    names = dict(A='raw_items_a.json', B='raw_items_b.json', C='items_c.json', D='items_d.json', E='items_e.json')
    for exp, filename in names.items():
        for item in read(Path(base)/filename)['items']:
            if exp == 'B':
                item['human'] = {k: human.get(uid) for k, uid in enumerate(item['UIDs'], 1)}
            if exp == 'D':
                item['dependence'] = strata.get(item['item_id'])
            for unit in item['units']:
                uid = unit.get('unit_id', unit.get('unit'))
                rnd = unit.get('round', 'r0')
                if not uid.endswith(('|r0', '|r1')):
                    uid += '|'+rnd
                for r in ('r0', 'r1'):
                    out[exp+':'+uid[:-2]+r] = (exp, item, unit)
    return out


def cell_keys(exp, unit):
    a = unit['ask']
    if exp == 'A':
        return [(a, unit['condition'], unit['level'])]
    if exp == 'B':
        return [(a, unit['condition'], unit['k'])]
    if exp == 'C':
        return [(a, unit['format'], unit['br'])]
    if exp == 'D':
        return [(a, unit['pres'], s) for s in A.STATEMENTS] if unit['pres'] == 'J' else [(a, 'S', unit['stmt'])]
    return [(a, unit['cell'].replace('advisor_', 'recommend_'))]


def extract_comparison(text):
    """First whole comparison word in the successful attempt's full response."""
    match = re.search(r'\b(higher|lower|equal)\b', text, re.IGNORECASE)
    return match.group(1).lower() if match else None


def build_items(manifest, records, index, which, cfg, rnd='r0'):
    by_unit = {r['unit']: r for r in records}
    allowed = {r['unit_id']: r for r in manifest}
    for rec in records:
        row = allowed.get(rec['unit'])
        if row is None or rec.get('config') != cfg:
            raise Mismatch('unplanned unit or wrong configuration')
        if any(rec.get(k) != row[k] for k in R.ids_only([row])[0]):
            raise Mismatch('record identity differs from manifest: '+rec['unit'])
    items = {}
    for row in manifest:
        if row['split'] != which or row['round'] != rnd:
            continue
        exp, material, unit = index[row['unit_id']]
        key = (exp, row['item_id'])
        if key not in items:
            obj = {k: copy.deepcopy(v) for k, v in material.items() if k != 'units'}
            obj.update(exp=exp, item_id=row['item_id'], cluster=row['cluster'], cells={}, results={}, unit_groups=[])
            if exp == 'E':
                # Existing E renderer always lists Option P before Q.
                obj['target_position'] = 'first' if material['target'] == 'P' else 'last'
            items[key] = obj
        obj = items[key]
        keys = cell_keys(exp, unit)
        obj['unit_groups'].append(keys)
        rec = by_unit.get(row['unit_id'])
        if rec is None or rec['status'] != 'ok':
            continue
        parsed = copy.deepcopy(rec['result'])
        if not parsed or not parsed.get('ok'):
            raise Mismatch('status ok without a valid parse')
        if exp == 'A' and unit['condition'] != 'none':
            successful = next((a for a in reversed(rec.get('attempts', [])) if a.get('parsed') is True), None)
            text = ''
            if successful is not None:
                raw = Path(successful['raw_path'])
                guard(raw)
                if sha(raw) != successful['raw_sha256']:
                    raise Mismatch('raw attempt integrity failed')
                text = read(raw).get('text', '')
            parsed['comparison'] = extract_comparison(text)
        values = parsed.get('values') if exp == 'D' and unit['pres'] == 'J' else None
        ys = [values.get(k[2]) if values else parsed.get('value') for k in keys]
        if any(y is None or not math.isfinite(y) or (y <= 0 if exp == 'A' else not 0<=y<=100) for y in ys):
            raise Mismatch('invalid admitted numeric value')
        for k, y in zip(keys, ys):
            obj['cells'][k] = y
            obj['results'][k] = parsed
    return list(items.values())


def accounting(manifest, records, which, index=None):
    expected = {r['unit_id']: r for r in manifest if r['split'] == which}
    rows = {r['unit']: r for r in records if r['unit'] in expected}
    first = sum(bool(r.get('attempts')) and r['attempts'][0].get('parsed') is True for r in rows.values())
    missing = sum(uid not in rows or rows[uid]['status'] != 'ok' for uid in expected)
    condition = defaultdict(Counter)
    for uid, row in expected.items():
        rec = rows.get(uid, {})
        unit = index[uid][2] if index else {}
        context = tuple((k, unit[k]) for k in ('condition', 'level', 'k', 'format', 'br', 'pres', 'stmt', 'cell') if k in unit)
        c = condition[str((row['exp'], row['ask'], row['round'], context))]
        c['planned'] += 1
        c['missing'] += rec.get('status') != 'ok'
        for att in rec.get('attempts', []):
            c['failed_attempts'] += att.get('parsed') is not True
            c['truncated'] += bool(att.get('truncated'))
            c['refusal_marked'] += att.get('state') in ('refusal', 'refused')
        parsed = rec.get('result') or {}
        if row['ask'] == 'multi' and rec.get('status') == 'ok':
            c['parsed_multi'] += 1
            c['weights_compliant'] += .95<=(parsed.get('weight_sum') or 0)<=1.05
    return dict(planned=len(expected), admitted=len(rows), first_parsed=first, missing=missing,
                first_rate=first/len(expected) if expected else None,
                missing_rate=missing/len(expected) if expected else None,
                acceptance=bool(expected) and len(rows)==len(expected) and first>=.9*len(expected) and missing<=.02*len(expected),
                by_condition={k: dict(v) for k, v in sorted(condition.items())},
                refusal_note='解析失败不自动视为拒答；外壳无统一拒答标记')


def freeze(which, cfg, base=HERE, freeze_path=None, B=A.B_DEFAULT, seed=A.SEED, names=None):
    if which not in ('dev', 'formal') or B<1 or (which == 'formal' and B != 5000):
        raise Mismatch('formal B must be 5000; valid stage and positive B required')
    fp = Path(freeze_path) if freeze_path else Path(base)/'analysis_freeze_psych3.json'
    guard(fp)
    old = read(fp) if fp.exists() else {}
    if which == 'formal' and cfg not in old.get('formal', {}):
        _, formal_mp = paths(base, 'formal', cfg)
        if formal_mp.exists() and read(formal_mp).get('sessions'):
            raise Mismatch('formal freeze must precede every formal session')
    # Formal freezing uses accepted development evidence, never formal results.
    rp, mp = paths(base, 'dev' if which == 'formal' else which, cfg)
    meta = read(mp)
    sessions = meta['sessions']
    good = [s for s in sessions if s.get('closed_ok') and not s.get('invalid')]
    fids = {s['fingerprint_id'] for s in good}
    if len(fids) != 1:
        raise Mismatch('exactly one valid session fingerprint required')
    fid = next(iter(fids))
    fps = [s['fingerprint'] for s in good]
    if any(R.sha(json.dumps(fp, sort_keys=True, ensure_ascii=False).encode('utf-8')) != fid for fp in fps):
        raise Mismatch('fingerprint hash mismatch')
    names = sorted(A.SPECS if names is None else names)
    if len(set(names)) != len(names) or any(n not in A.SPECS for n in names):
        raise Mismatch('invalid frozen hypothesis list')
    obj = dict(fingerprint_id=fid, fingerprint=fps[0], code=code_binding(B, seed),
               materials=input_bindings(base), hypotheses=names)
    if which == 'formal':
        current = R.build_manifest(base)
        current_fp, _ = R.fingerprint(current, cfg, fps[0]['subject_meta'], base)
        if any(fps[0].get(k) != v for k, v in current_fp.items()):
            raise Mismatch('accepted development fingerprint differs from current materials')
        records, _ = load_valid(rp, mp, fid, cfg)
        verdict = accounting(current, records, 'dev')
        if meta.get('stopped') or not verdict['acceptance']:
            raise Mismatch('development acceptance required before formal freeze')
        obj['development_acceptance'] = verdict
    section = old.setdefault(which, {})
    if cfg in section and section[cfg] != obj:
        raise Mismatch('already frozen: code, B, fingerprint, material or list differs')
    if cfg not in section:
        section[cfg] = obj
        R.save_json(fp, old)
    return obj


def check_formal_freeze(cfg, fingerprint, fingerprint_id, base=HERE):
    """Check launch bindings without opening any development or formal evidence."""
    path = Path(base) / 'analysis_freeze_psych3.json'
    try:
        document = read(path)
        frozen = document.get('formal', {}).get(cfg)
    except (OSError, ValueError, AttributeError) as exc:
        raise Mismatch(f'analysis freeze refused ({cfg}): {path.name}: {exc}') from exc
    if not isinstance(frozen, dict):
        raise Mismatch(f'analysis freeze refused ({cfg}): formal.{cfg} entry required')
    differences = []

    def compare(label, saved, current):
        if isinstance(saved, dict) and isinstance(current, dict):
            for key in sorted(saved.keys() | current.keys()):
                if key not in saved or key not in current:
                    differences.append(label + '.' + key)
                else:
                    compare(label + '.' + key, saved[key], current[key])
        elif saved != current:
            differences.append(label)

    compare('fingerprint.config', fingerprint.get('config'), cfg)
    compare('fingerprint', frozen.get('fingerprint'), fingerprint)
    compare('fingerprint_id', frozen.get('fingerprint_id'), fingerprint_id)
    digest = R.sha(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    compare('fingerprint_id.hash', fingerprint_id, digest)
    code = frozen.get('code')
    if not isinstance(code, dict):
        differences.append('code')
    else:
        compare('code.B', code.get('B'), 5000)
        compare('code', code, code_binding(5000, code.get('seed')))
    compare('materials', frozen.get('materials'), input_bindings(base))
    acceptance = frozen.get('development_acceptance')
    if not isinstance(acceptance, dict) or acceptance.get('acceptance') is not True:
        differences.append('development_acceptance.acceptance')
    if differences:
        raise Mismatch(f'analysis freeze refused ({cfg}): ' + '; '.join(differences))
    return frozen


def run(which, cfg, base=HERE, freeze_path=None, B=None, output=None):
    rp, mp = paths(base, which, cfg)
    fp = Path(freeze_path) if freeze_path else Path(base)/'analysis_freeze_psych3.json'
    frozen = read(fp)[which][cfg]
    count = frozen['code']['B']
    if (B is not None and B != count) or frozen['code'] != code_binding(count, frozen['code']['seed']):
        raise Mismatch('analysis code, settings or B differs from freeze')
    if frozen['materials'] != input_bindings(base):
        raise Mismatch('material binding differs from freeze')
    manifest = read(Path(base)/'manifest_ids.json')
    # Re-render current products to check their relation to the IDs, not just file hashes.
    current = R.build_manifest(base)
    if R.ids_only(current) != manifest:
        raise Mismatch('manifest differs from current products')
    subject = frozen['fingerprint']['subject_meta']
    current_fp, _ = R.fingerprint(current, cfg, subject, base)
    for key, value in current_fp.items():
        if frozen['fingerprint'].get(key) != value:
            raise Mismatch('runner binding differs: '+key)
    night = frozen['fingerprint'].get('psych3_agy_night')
    if night:
        expected = dict(python_sha256=sha(HERE/'agy_night.py'), powershell_sha256=sha(HERE/'agy_night.ps1'),
                        recovery_rules_sha256=sha(HERE.parent/'dnli-agy/auto_clear.py'))
        if any(night.get(k) != value for k, value in expected.items()):
            raise Mismatch('agy night policy code differs from freeze')
    if which == 'formal':
        sessions = read(mp)['sessions']
        if any(s.get('fingerprint_id') != frozen['fingerprint_id'] or
               s.get('fingerprint') != frozen['fingerprint'] for s in sessions):
            raise Mismatch('formal session fingerprint differs from freeze')
    records, filtered = load_valid(rp, mp, frozen['fingerprint_id'], cfg, strict=which=='formal')
    index = material_index(base)
    items = build_items(manifest, records, index, which, cfg)
    repeats = build_items(manifest, records, index, which, cfg, 'r1')
    seed = frozen['code']['seed']
    result = dict(stage=which, config=cfg, freeze=frozen, filter=filtered,
                  accounting=accounting(manifest, records, which, index),
                  families={e: A.analyse_family(items, [n for n in frozen['hypotheses'] if n[0] == e], count, seed) for e in 'ABCDE'},
                  descriptive=A.descriptive(items, count, seed),
                  recommendation_control=A.recommendation_control(items, count, seed),
                  repeats=A.repeat_description(items, repeats))
    if which == 'dev':
        result['development'] = A.development_diagnostics(items)
    if output:
        guard(output)
        if Path(output).exists():
            raise Mismatch('output exists; choose a new output path')
        R.save_json(Path(output), result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['freeze', 'run'])
    parser.add_argument('stage', choices=['dev', 'formal'])
    parser.add_argument('config')
    parser.add_argument('--base', type=Path, default=HERE)
    parser.add_argument('--freeze-file', type=Path)
    parser.add_argument('--B', type=int)
    parser.add_argument('--seed', type=int, default=A.SEED)
    parser.add_argument('--hypotheses', help='explicit comma-separated confirmatory list; empty means descriptive only')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'freeze':
        obj = freeze(args.stage, args.config, args.base, args.freeze_file,
                     args.B if args.B is not None else A.B_DEFAULT, args.seed,
                     args.hypotheses.split(',') if args.hypotheses else [] if args.hypotheses == '' else None)
    else:
        obj = run(args.stage, args.config, args.base, args.freeze_file, args.B, args.output)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
