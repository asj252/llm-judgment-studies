"""Read-only PLAN 7/7.1 development power run. Requires NumPy; no subject calls.

The narrowly scoped guard exception below is authorized for development power
only. All admission, identity, session and raw integrity checks remain enabled.
Bootstrap uses NumPy's RNG (not random.Random), with the same percentile/tail
and Holm rules as analysis_psych3. No freeze entry is read or written.
"""
import argparse
import copy
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np
import analyse_psych3 as L
import analysis_psych3 as A
import power_psych3 as P

HERE = Path(__file__).resolve().parent
START = dict(A=50, B=90, C=20, D=20, E=32)
CONFIGS = ('qwen3-off', 'codex', 'agy:gpt-oss-120b-medium',
           'agy:claude-sonnet-5-5-medium', 'agy:gemini-3.8-flash-low',
           'agy:gemini-3.8-flash-high')
# HEAD's two-configuration artifact retains the entire D/E expansion grid,
# even where its complete-subset recommendations already pass at the start.
# Preserve those numeric scenarios as well as their unchanged recommendations.
LEGACY_GRID = {'D': 40, 'E': 40}


def load_development(base, cfg, manifest, index, include_records=False):
    base = Path(base)
    name = L.R.config_name(cfg)
    rp, mp = base/f'results_dev_{name}.jsonl', base/f'run_meta_dev_{name}.json'
    meta = L.read(mp)
    if cfg.startswith('agy:'):
        import agy_night
        meta = agy_night.checkpoint_meta(mp)
    good = [s for s in meta['sessions'] if s.get('closed_ok') and not s.get('invalid')]
    fids = {s['fingerprint_id'] for s in good}
    if len(fids) != 1:
        raise L.Mismatch('exactly one valid development fingerprint required')
    fid = next(iter(fids))
    for s in good:
        if L.R.sha(json.dumps(s['fingerprint'], sort_keys=True, ensure_ascii=False).encode()) != fid:
            raise L.Mismatch('development fingerprint hash mismatch')
    original_guard = L.guard
    def power_guard(path):
        p = Path(path).resolve()
        raw = (base/f'raw/run_dev_{name}').resolve()
        if p in (rp.resolve(), mp.resolve()) or raw in p.parents:
            return
        original_guard(path)
    with patch.object(L, 'guard', power_guard):
        # Analysis is stricter than agy_night.checked_records: unregistered or
        # corrupt rows must stop for human review, never be silently skipped.
        # The four real agy configurations admit exactly the same valid records.
        records, admission = L.load_valid(rp, mp, fid, cfg)
        items = L.build_items(manifest, records, index, 'dev', cfg)
    source = dict(admission=admission, accounting=L.accounting(manifest, records, 'dev'),
                      inputs={p.name: L.sha(p) for p in (rp, mp)}, fingerprint_id=fid)
    return (items, source, records) if include_records else (items, source)


def parse_configs(value):
    configs = tuple(v.strip() for v in value.split(','))
    if not configs or any(c not in CONFIGS for c in configs) or len(set(configs)) != len(configs):
        raise argparse.ArgumentTypeError('configs must be unique supported configuration names')
    return configs


def output_paths(prefix, base=HERE):
    prefix = Path(prefix)
    if not prefix.is_absolute():
        prefix = Path(base)/prefix
    return [prefix.with_name(prefix.name+'_results.json'), prefix.with_name(prefix.name+'_summary.md')]


def targets_for(exp):
    names = [n for n in A.SPECS if n.startswith(exp)]
    targets = {str(k): {n: k*A.SPECS[n]['threshold'] for n in names} for k in (0, 1, 2)}
    if exp == 'C':
        # Perfect Bayes responses: slopes=1 in both formats/asks, errors=0.
        targets['ceiling'] = dict.fromkeys(names, 0.)
    return targets


def sample_limits(manifest):
    maximum = dict(A=50, D=40, E=40)
    for exp in ('B', 'C'):
        maximum[exp] = len({r['cluster'] for r in manifest
                            if r['exp'] == exp and r['split'] == 'formal' and r['round'] == 'r0'})
        if maximum[exp] < START[exp]:
            raise ValueError(f'{exp}: formal material below planned starting size')
    return maximum


def contribution_export(items, names):
    plan = P.prepare(items, names)
    return dict(mode=plan['mode'], note=plan['note'], insufficient=plan['insufficient'],
                means=plan['means'], pools=plan['pools'], contributions=plan['samples'],
                sd={n: statistics.stdev([plan['samples'][n][c]['value'] for c in plan['pools'][n]])
                    if len(plan['pools'][n]) >= 2 else None for n in names})


def mask_design(items, names, plan):
    """Cache which source units each statistic requires; J stays one unit.

    This reproduces power_psych3.draw_clusters: a failed required unit gives
    the full unshifted legal bounds, while complete statistics are shifted.
    """
    clusters = defaultdict(list)
    for item in items:
        clusters[str(item['cluster'])].append(item)
    out = {}
    for cl, rows in clusters.items():
        units = [(j, g) for j, item in enumerate(rows) for g in P.groups(item)]
        required = {n: [] for n in names}
        for u, (j, group) in enumerate(units):
            masked = copy.deepcopy(rows)
            for key in group:
                masked[j]['cells'].pop(key, None)
            for n in names:
                if A.cluster_values(masked, n)[cl]['value'] is None:
                    required[n].append(u)
        absent = [dict(i, cells={}) for i in rows]
        out[cl] = dict(units=len(units), required=required,
                       bounds={n: A.cluster_values(absent, n)[cl] for n in names})
    return out


def numpy_bootstrap(values, B=A.B_DEFAULT, seed=A.SEED):
    if B < 1:
        raise ValueError('B must be positive')
    if not values:
        return []
    values = np.asarray(values, dtype=float)
    return values[np.random.default_rng(seed).integers(len(values), size=(B, len(values)))].mean(axis=1).tolist()


def fast_draw(plan, design, names, size, targets, scale, missing, rng):
    samples, latent = {n: {} for n in names}, {n: [] for n in names}
    joint = plan['mode'] == 'joint'
    for j in range(size):
        shared = str(rng.choice(plan['pools'][names[0]])) if joint else None
        shared_mask = rng.random(design[shared]['units']) < missing if joint else None
        for n in names:
            if n in plan['insufficient']:
                continue
            cl = shared if joint else str(rng.choice(plan['pools'][n]))
            mask = shared_mask if joint else rng.random(design[cl]['units']) < missing
            value = targets[n]+scale*(plan['samples'][n][cl]['value']-plan['means'][n])
            latent[n].append(value)
            row = dict(plan['samples'][n][cl])
            if mask[design[cl]['required'][n]].any():
                bounds = design[cl]['bounds'][n]
                row.update(value=None, lower=bounds['lower'], upper=bounds['upper'], missing_cells=1)
            else:
                row.update(value=value, lower=value, upper=value, missing_cells=0)
            samples[n][str(j)] = row
    return samples, latent


def simulate(items, names, targets, size, scale, nsim, B, seed, prepared=None):
    plan, design = prepared or (None, None)
    if plan is None:
        plan = P.prepare(items, names)
        design = mask_design(items, names, plan)
    missing = P.failure_rate(items)
    rng = np.random.default_rng(seed)
    counts = {n: dict(direction_confirmed=0, bound_exceeds=0, complete_direction=0,
                      complete_bound=0) for n in names if n not in plan['insufficient']}
    realized = defaultdict(list)
    with patch.object(A, 'bootstrap', numpy_bootstrap):
        for rep in range(nsim):
            samples, latent = fast_draw(plan, design, names, size, targets, scale, missing, rng)
            result = A.analyse_samples(samples, names, B, seed+rep)
            for n, c in counts.items():
                row = result['complete_subset'][n]
                complete_ok = P.confirms_target(row, targets[n])
                final_ok = P.confirms_target(row['final'], targets[n])
                c['complete_direction'] += complete_ok
                c['complete_bound'] += complete_ok and row['strength'] == 'bound_exceeds'
                c['direction_confirmed'] += final_ok
                c['bound_exceeds'] += final_ok and row['final']['strength'] == 'bound_exceeds'
                realized[n].append(A.mean(latent[n]))
    return dict(nsim=nsim, B=B, seed=seed, n_clusters=size, sd_scale=scale,
                targets=targets, missing_rate=missing, resampling=plan['mode'], note=plan['note'],
                hypotheses={n: dict(status='开发资料不足') if n in plan['insufficient'] else
                            dict(status='simulated', **{k: v/nsim for k, v in counts[n].items()},
                                 realized_effect=A.mean(realized[n])) for n in names})


def sanity_summary(doc):
    lines = ['## 健全性检查', '',
             '下表为起始样本量、1.5 倍开发标准差下的最终方向确认率。方向须与注入效应一致，'
             '零效应按正方向计数。递增指单调不减，允许相邻率差在 3 倍二项差标准误内；'
             '三个效应使用相同随机流。高噪声或全域缺失界可使三项均很低，不能据此认定平移失效。', '',
             '| 配置 | 实验 | 簇数 | 假设 | 0 倍 | 1 倍 | 2 倍 | 递增检查 |',
             '|---|---|---|---|---|---|---|---|']
    for cfg, data in doc['configurations'].items():
        for exp, result in data['experiments'].items():
            scenarios = {r['effect']: r for r in result['scenarios']
                         if r['sd_scale'] == 1.5 and r['n_clusters'] == START[exp]
                         and r['effect'] in (0, 1, 2)}
            for n in result['recommendations']:
                values = [scenarios[k]['hypotheses'][n] for k in (0, 1, 2)]
                if any(v['status'] != 'simulated' for v in values):
                    rates, check = ['无法判定']*3, '开发资料不足'
                else:
                    ps = [v['direction_confirmed'] for v in values]
                    check = ('单调不减' if ps == sorted(ps) else
                             '蒙地卡罗误差内' if all(
                                 b >= a-3*((a*(1-a)+b*(1-b))/doc['nsim'])**.5-1/doc['nsim']
                                 for a,b in zip(ps, ps[1:]))
                             else '未通过')
                    rates = [f'{p:.3f}' for p in ps]
                lines.append(f'| {cfg} | {exp} | {START[exp]} | {n} | '+
                             ' | '.join(rates)+f' | {check} |')
    return lines


def recommendations(scenarios, names, start, maximum):
    """PLAN 7.1.9: only complete-subset Holm rates determine advice.

    Reuse the sample-size policy without changing the generic simulator's
    final/protected metrics or mutating the saved scenario rates.
    """
    complete = []
    for row in scenarios:
        hypotheses = {}
        for n, values in row['hypotheses'].items():
            v = dict(status=values['status'])
            for source, target in (('complete_direction', 'direction_confirmed'),
                                   ('complete_bound', 'bound_exceeds')):
                if source in values:
                    v[target] = values[source]
            hypotheses[n] = v
        complete.append(dict(row, hypotheses=hypotheses))
    return P.recommendations(complete, names, start, maximum)


def target_rates(result, name, size):
    """Complete and protected rates at the two 1.5-SD target scenarios."""
    scenarios = {r['effect']: r['hypotheses'][name] for r in result['scenarios']
                 if r['n_clusters'] == size and r['sd_scale'] == 1.5 and r['effect'] in (1, 2)}
    return [scenarios.get(effect, {}).get(metric) for effect, metric in
            ((1, 'complete_direction'), (2, 'complete_bound'),
             (1, 'direction_confirmed'), (2, 'bound_exceeds'))]


def render_summary(doc):
    lines = ['# 开发集功效实跑', '',
             'A 已知真值与 C 天花板的降级见 [dev_diagnostics_psych3.md](dev_diagnostics_psych3.md)；'
             '表中「保留」不是最终冻结名单。', '',
             '| 配置 | 假设 | 建议 | 建议簇数 | 阈值情景完整题方向率 | 两倍情景完整题界越率 | 保护版方向率 | 保护版界越率 |',
             '|---|---|---|---|---|---|---|---|']
    for cfg, data in doc['configurations'].items():
        for exp, result in data['experiments'].items():
            for n, advice in result['recommendations'].items():
                size = advice.get('n_clusters')
                evaluated = size or max(r['n_clusters'] for r in result['scenarios'])
                rates = ['无法判定' if p is None else f'{p:.3f}'
                         for p in target_rates(result, n, evaluated)]
                lines.append(f"| {cfg} | {n} | {advice['action']} | {size or '—'} | "+
                             ' | '.join(rates)+' |')
    lines += ['',
             f"nsim={doc['nsim']}；bootstrap B={doc['B']}；种子={doc['seed']}。采用 NumPy 重抽随机流，"
             '百分位区间、尾部 p 值、家族 Holm 与最终缺失保护判定沿用 analysis_psych3。', '',
             '贡献值按假设统计量平移；两侧假设采用正向阈值情景。C 天花板采用贝叶斯基准对应的零贡献均值，'
             '仍保留开发残差，与零效应共享模拟结果。缺失按 unit 产生，D 同页四值一起失败；'
             '建议依据完整题子集的 Holm 判定：1.5 倍标准差下，阈值情景 complete_direction ≥0.80，'
             '两倍阈值情景 complete_bound ≥0.80。保护版对应两率并列报告，不影响建议；'
             'A 有缺失时仅支持完整题子集解释。总表率取建议簇数，降为描述或无法判定项取末次模拟簇数，'
             '其簇数见下方分实验情景表。', '',
             '扩样逐个整数簇数检查上述两项目标，达到目标即建议该样本量；'
             '初始与所检查扩样量均报告全部情景。建议使用原四项 Holm 家族，降级后缩小家族须另行冻结。'
             'D/E 超出现有正式材料的扩样建议需要新增材料，开发题不回流。', '']
    for cfg, data in doc['configurations'].items():
        lines += [f'## {cfg}', '', f"有效记录 {data['source']['admission']['admitted']}/{data['source']['admission']['total']}；"
                  f"开发验收：{data['source']['accounting']['acceptance']}。", '']
        for exp, result in data['experiments'].items():
            lines += [f'### {exp}', '', f"起点 {START[exp]}，上限 {result['maximum']}；"
                      f"缺失率 {result['missing_rate']:.2%}；{result['development']['note']}。", '',
                      '| 假设 | 建议 | 簇数 |', '|---|---|---|']
            for n, advice in result['recommendations'].items():
                lines.append(f"| {n} | {advice['action']} | {advice.get('n_clusters', '—')} |")
            lines += ['', '| 簇数 | 标准差倍数 | 效应倍数 | 假设 | 完整题方向率 | 完整题界越率 | 保护版方向率 | 保护版界越率 |',
                      '|---|---|---|---|---|---|---|---|']
            for row in result['scenarios']:
                for n, v in row['hypotheses'].items():
                    rates = (' | '.join(f'{v[k]:.3f}' for k in
                             ('complete_direction', 'complete_bound', 'direction_confirmed', 'bound_exceeds'))
                             if v['status']=='simulated' else ' | '.join(['无法判定']*4))
                    lines.append(f"| {row['n_clusters']} | {row['sd_scale']} | {row['effect']} | {n} | {rates} |")
            lines.append('')
    lines += sanity_summary(doc)+['']
    return '\n'.join(lines)+'\n'


def run(base=HERE, nsim=1000, B=499, seed=A.SEED, configs=CONFIGS):
    manifest = L.R.build_manifest(base)
    index = L.material_index(base)
    limits = sample_limits(manifest)
    doc = dict(nsim=nsim, B=B, seed=seed, bootstrap='numpy percentile; analysis_psych3 Holm',
               configurations={})
    for cfg in configs:
        items, source = load_development(base, cfg, manifest, index)
        data = doc['configurations'][cfg] = dict(source=source, experiments={})
        for exp in START:
            rows = [i for i in items if i['exp']==exp and (exp!='D' or i.get('type')=='P')]
            names = [n for n in A.SPECS if n.startswith(exp)]
            plan = P.prepare(rows, names)
            prepared = plan, mask_design(rows, names, plan)
            result = data['experiments'][exp] = dict(maximum=limits[exp], missing_rate=P.failure_rate(rows),
                         development=contribution_export(rows, names), scenarios=[])
            targets = targets_for(exp)
            for size in range(START[exp], limits[exp]+1):
                for scale in (1., 1.5, 2.):
                    for effect in ('0', '1', '2'):
                        started = time.perf_counter()
                        # Reset per scenario/configuration, as in the original two-config run.
                        # Common random numbers retain legacy values and never depend on order.
                        row = simulate(rows, names, targets[effect], size, scale, nsim, B, seed, prepared)
                        row.update(effect=int(effect), seconds=time.perf_counter()-started)
                        result['scenarios'].append(row)
                        print(f'{cfg} {exp} n={size} sd={scale} effect={effect}: {row["seconds"]:.1f}s', flush=True)
                    if exp=='C':
                        row = copy.deepcopy(result['scenarios'][-3])
                        row.update(effect='ceiling', equivalent_to='zero effect; all Bayes means', seconds=0.)
                        result['scenarios'].append(row)
                advice = recommendations(result['scenarios'], names, START[exp], limits[exp])
                legacy_pending = cfg in CONFIGS[:2] and size < min(limits[exp], LEGACY_GRID.get(exp, START[exp]))
                if not legacy_pending and all(v['action'] in ('保留', '建议扩样') or n in plan['insufficient'] for n,v in advice.items()):
                    break
            result['recommendations'] = recommendations(result['scenarios'], names, START[exp], limits[exp])
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nsim', type=int, default=1000)
    parser.add_argument('--B', type=int, default=499)
    parser.add_argument('--seed', type=int, default=A.SEED)
    parser.add_argument('--configs', type=parse_configs, default=CONFIGS)
    parser.add_argument('--output-prefix', default='power_dev')
    parser.add_argument('--overwrite', action='store_true', help='replace the two development power outputs')
    args = parser.parse_args()
    if args.nsim<1 or args.B<1:
        parser.error('nsim and B must be positive')
    outputs = output_paths(args.output_prefix)
    if any(p.exists() for p in outputs) and not args.overwrite:
        parser.error('output exists; refusing overwrite')
    started = time.perf_counter()
    doc = run(nsim=args.nsim, B=args.B, seed=args.seed, configs=args.configs)
    doc['elapsed_seconds'] = time.perf_counter()-started
    for path, text in zip(outputs, (json.dumps(doc, ensure_ascii=False, indent=2)+'\n', render_summary(doc))):
        with path.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)


if __name__=='__main__':
    main()
