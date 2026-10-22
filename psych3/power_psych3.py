"""PLAN 7.1 power: shift cluster hypothesis contributions, resample families.

Input contains explicitly exported or synthetic development items. No model
calls or live runner input. Targets map hypothesis IDs to statistic means.
"""
import argparse
import copy
import json
import random
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis_psych3 as A


def groups(item):
    return item.get('unit_groups') or [[k] for k in item['cells']]


def failure_rate(dev_items):
    units = [all(i['cells'].get(k) is not None for k in g) for i in dev_items for g in groups(i)]
    return max(.02, 1-sum(units)/len(units)) if units else .02


def confirms_target(row, target):
    """Count recovery of the injected sign; use positive-side size at zero.

    A two-sided rejection in the opposite direction is not recovered power.
    """
    return bool(row['directional'] and row['sign'] == (-1 if target < 0 else 1))


def prepare(dev_items, names):
    """Use joint complete contributions at >=4 clusters, otherwise marginal pools."""
    samples = {n: A.cluster_values(dev_items, n) for n in names}
    joint = sorted(set.intersection(*[{c for c, r in samples[n].items() if r['value'] is not None}
                                      for n in names]))
    mode = 'joint' if len(joint)>=4 else 'independent'
    pools = {n: joint if mode=='joint' else [c for c, r in samples[n].items() if r['value'] is not None]
             for n in names}
    return dict(samples=samples, pools=pools, mode=mode,
                insufficient=[n for n in names if len(pools[n])<2],
                means={n: A.mean(samples[n][c]['value'] for c in pools[n]) for n in names},
                note='保留家族内相关' if mode=='joint' else '各假设分别重抽，失去家族内相关')


def draw_clusters(dev_items, names, n_clusters, targets, sd_scale, missing, rng, prepared=None):
    """Shift statistics only. Apply unit failure masks to source raw cells.

    Observed contributions shift to the target. A simulated missing contribution
    uses the statistic's full legal bounds (all required cells absent), without
    translation. A has no protected missing inference.
    """
    if n_clusters<1 or sd_scale<=0 or not 0<=missing<=1:
        raise ValueError('invalid sampling parameters')
    if set(targets)!=set(names):
        raise ValueError('targets must cover the frozen hypothesis family exactly')
    plan = prepare(dev_items, names) if prepared is None else prepared
    by_cluster = defaultdict(list)
    for i in dev_items:
        by_cluster[str(i['cluster'])].append(i)
    samples = {n: {} for n in names if n not in plan['insufficient']}
    latent = {n: [] for n in samples}
    def masked(cl):
        rows = copy.deepcopy(by_cluster[cl])
        for item in rows:
            for g in groups(item):
                if rng.random()<missing:
                    for k in g:
                        item['cells'].pop(k, None)
        return rows
    for j in range(n_clusters):
        shared = rng.choice(plan['pools'][names[0]]) if plan['mode']=='joint' else None
        shared_rows = masked(shared) if shared is not None else None
        for n in samples:
            cl = shared if shared is not None else rng.choice(plan['pools'][n])
            original = plan['samples'][n][cl]['value']
            value = targets[n]+sd_scale*(original-plan['means'][n])
            latent[n].append(value)
            source_rows = shared_rows if shared_rows is not None else masked(cl)
            row = A.cluster_values(source_rows, n)[cl]
            if row['value'] is not None:
                row.update(value=value, lower=value, upper=value)
            else:
                absent = [dict(i, cells={}) for i in by_cluster[cl]]
                bounds = A.cluster_values(absent, n)[cl]
                row.update(lower=bounds['lower'], upper=bounds['upper'])
            samples[n][str(j)] = row
    return samples, latent


def simulate(dev_items, names, targets, n_clusters, sd_scale=1.5, nsim=1000,
             B=A.B_DEFAULT, seed=A.SEED, missing=None, progress=None):
    if nsim<1:
        raise ValueError('nsim must be positive')
    names = list(names)
    if (not names or len(set(names))!=len(names) or any(n not in A.SPECS for n in names)
            or len({n[0] for n in names})!=1 or any(i['exp']!=names[0][0] for i in dev_items)):
        raise ValueError('one experiment and its frozen family required')
    if names[0][0]=='D' and any(i.get('type')!='P' for i in dev_items):
        raise ValueError('D power uses P items only')
    if set(targets)!=set(names):
        raise ValueError('targets must cover the frozen hypothesis family exactly')
    missing = failure_rate(dev_items) if missing is None else missing
    if missing<.02:
        raise ValueError('PLAN minimum per-unit failure rate is 2%')
    plan = prepare(dev_items, names)
    rng = random.Random(seed)
    counts = {n: defaultdict(int) for n in names if n not in plan['insufficient']}
    realized = defaultdict(list)
    for rep in range(nsim):
        samples, latent = draw_clusters(dev_items, names, n_clusters, targets, sd_scale, missing, rng, plan)
        # Insufficient hypotheses remain in the frozen Holm family with p=1.
        full_samples = {n: samples.get(n, {}) for n in names}
        result = A.analyse_samples(full_samples, names, B, seed+rep)
        for n in counts:
            row = result['complete_subset'][n]
            final = row['final']
            complete_ok = confirms_target(row, targets[n])
            final_ok = confirms_target(final, targets[n])
            counts[n]['complete_direction'] += complete_ok
            counts[n]['complete_bound'] += complete_ok and row['strength']=='bound_exceeds'
            counts[n]['direction_confirmed'] += final_ok
            counts[n]['bound_exceeds'] += final_ok and final['strength']=='bound_exceeds'
            realized[n].append(A.mean(latent[n]))
        if progress and (rep+1)%max(1, nsim//10)==0:
            progress(rep+1, nsim)
    return dict(nsim=nsim, B=B, seed=seed, n_clusters=n_clusters, sd_scale=sd_scale,
                missing_rate=missing, resampling=plan['mode'], note=plan['note'],
                development_clusters={n: len(plan['pools'][n]) for n in names},
                hypotheses={n: dict(status='开发资料不足') if n in plan['insufficient'] else
                            dict(status='simulated', **{k: v/nsim for k, v in counts[n].items()},
                                 realized_effect=A.mean(realized[n])) for n in names})


def recommendations(scenarios, names, start, maximum=None):
    """Only advise. Each scenario has effect (0/1/2/ceiling) and simulate output."""
    out = {}
    for n in names:
        if scenarios and all(row['hypotheses'][n].get('status')=='开发资料不足' for row in scenarios):
            out[n] = dict(action='无法判定：开发资料不足')
            continue
        by_n = defaultdict(dict)
        for row in scenarios:
            if row['sd_scale'] == 1.5 and row['effect'] in (1, 2):
                metric = 'direction_confirmed' if row['effect']==1 else 'bound_exceeds'
                if metric in row['hypotheses'][n]:
                    by_n[row['n_clusters']][row['effect']] = row['hypotheses'][n][metric]
        passing = sorted(size for size, rates in by_n.items() if set(rates)=={1, 2} and min(rates.values())>=.8)
        if not by_n or any(set(rates)!={1, 2} for rates in by_n.values()):
            out[n] = dict(action='无法判定：缺少 1.5 倍标准差目标情景')
        elif passing:
            size = passing[0]
            out[n] = dict(action='保留' if size<=start else '建议扩样', n_clusters=size)
        elif maximum is not None and maximum not in by_n:
            out[n] = dict(action='建议继续模拟至材料上限', n_clusters=maximum)
        else:
            out[n] = dict(action='建议降为描述', reason='已模拟样本量未达两项功效目标')
    return out


def run_scenarios(dev_items, names, targets, sizes, maximum=None,
                  nsim=1000, B=A.B_DEFAULT, seed=A.SEED, progress=None):
    expected = {'0', '1', '2'} | ({'ceiling'} if names[0][0]=='C' else set())
    if set(targets)!=expected:
        raise ValueError('explicit targets required for scenarios: '+','.join(sorted(expected)))
    results = []
    for size in sizes:
        for scale in (1., 1.5, 2.):
            for effect, means in targets.items():
                if progress:
                    progress(f'n={size}, sd={scale}, effect={effect}')
                row = simulate(dev_items, names, means, size, scale, nsim, B, seed)
                row['effect'] = int(effect) if effect.isdigit() else effect
                row['target_mismatch'] = ({n: v for n, v in means.items()
                    if abs((abs(v) if A.SPECS[n]['sided']==2 else v)-int(effect)*A.SPECS[n]['threshold'])>1e-9}
                    if effect.isdigit() else {})
                results.append(row)
    usable = [r for r in results if not r['target_mismatch']]
    return dict(scenarios=results, recommendations=recommendations(usable, names, min(sizes), maximum),
                note='仅建议；不改冻结档。按假设贡献值平移；开发簇不足时注明分项重抽或资料不足。')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--nsim', type=int, default=1000)
    parser.add_argument('--B', type=int, default=A.B_DEFAULT)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError('output exists; choose a new output path')
    doc = json.loads(args.input.read_text(encoding='utf-8'))
    for item in doc['dev_items']:
        item['cells'] = {tuple(k): v for k, v in item['cells']}
        if 'unit_groups' in item:
            item['unit_groups'] = [[tuple(k) for k in g] for g in item['unit_groups']]
    targets = doc['targets']
    result = run_scenarios(doc['dev_items'], doc['hypotheses'], targets, doc['sizes'], doc.get('maximum'),
                           nsim=args.nsim, B=args.B, progress=lambda x: print(x, flush=True))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
