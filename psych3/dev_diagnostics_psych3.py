"""冻结前开发集诊断；只读既有记录，不调用模型。"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import power_from_dev as P

HERE = Path(__file__).resolve().parent
NO_DATA = '无此资料'


def rates(rows):
    """Unit missing rates and attempt failure rates have separate denominators."""
    records = [r for r in rows if r is not None]
    attempts = [a for r in records for a in r.get('attempts', [])]
    parsed = [r.get('result') or {} for r in records
              if r.get('status') == 'ok' and r.get('ask') == 'multi']
    weights = [r['weight_sum'] for r in parsed if r.get('weight_sum') is not None]
    truncated = [a['truncated'] for a in attempts if 'truncated' in a]
    # An ordinary parse/state failure does not establish refusal or its absence.
    refusals = sum(a.get('state') in ('refusal', 'refused') for a in attempts)
    count = len(rows)
    missing = sum(r is None or r.get('status') != 'ok' for r in rows)
    failed = sum(a.get('parsed') is not True for a in attempts)
    return dict(planned=count, missing=missing, missing_rate=missing/count if count else None,
                attempts=len(attempts), failed_attempts=failed,
                failed_attempt_rate=failed/len(attempts) if attempts else None,
                truncation_observed=len(truncated), truncated=sum(bool(v) for v in truncated),
                truncation_rate=sum(bool(v) for v in truncated)/len(truncated) if truncated else None,
                refusal_marked=refusals, refusal_rate=None,
                parsed_multi=len(parsed), weight_observed=len(weights),
                weights_compliant=sum(.95 <= w <= 1.05 for w in weights),
                weight_compliance_rate=sum(.95 <= w <= 1.05 for w in weights)/len(weights) if weights else None)


def breakdown(manifest, records, index):
    by_unit = {r['unit']: r for r in records}
    experiments, conditions = defaultdict(list), defaultdict(list)
    for row in manifest:
        if row['split'] != 'dev':
            continue
        unit = index[row['unit_id']][2]
        context = {k: unit[k] for k in ('condition', 'level', 'k', 'format', 'br', 'pres', 'stmt', 'cell') if k in unit}
        label = json.dumps(dict(exp=row['exp'], ask=row['ask'], round=row['round'], **context),
                           ensure_ascii=False, sort_keys=True)
        record = by_unit.get(row['unit_id'])
        experiments[row['exp']].append(record)
        conditions[label].append(record)
    return dict(by_experiment={k: rates(v) for k, v in sorted(experiments.items())},
                by_condition={k: rates(v) for k, v in sorted(conditions.items())})


def run(base=HERE, configs=P.CONFIGS):
    manifest = P.L.R.build_manifest(base)
    index = P.L.material_index(base)
    by_config, results = {}, {}
    for cfg in configs:
        items, source, records = P.load_development(base, cfg, manifest, index, include_records=True)
        by_config[cfg] = items
        results[cfg] = dict(source=source, acceptance=P.L.accounting(manifest, records, 'dev', index),
                            development=P.A.development_diagnostics(items),
                            **breakdown(manifest, records, index))
    return dict(configurations=results, neutral=P.A.neutral_across_configs(by_config),
                notes=['仅计既有规则选出的有效记录；排除会话和被替代重试不重复计数。',
                       '失败率按尝试计；缺失率按计划 unit 计；截断率按有截断字段的尝试计。',
                       '拒答无统一标记，拒答率记无此资料；另列明确标记数，不把解析失败当拒答。',
                       '权重遵从率按成功多估计且有 weight_sum 的 unit 计，同页四值仍为一个 unit。'])


def fmt(value):
    return NO_DATA if value is None else f'{value:.2%}'


def render(doc):
    lines = ['# 六配置开发集诊断', '', *doc['notes'], '',
             '| 配置 | 首次可解析 | 重试后缺失 | 验收 | A 已知真值（比例/格数） | C 天花板（比例/格数） | D1 预期不成立 |',
             '|---|---|---|---|---|---|---|']
    for cfg, data in doc['configurations'].items():
        acc, dev = data['acceptance'], data['development']
        lines.append(f"| {cfg} | {fmt(acc['first_rate'])} | {fmt(acc['missing_rate'])} | "
                     f"{'通过' if acc['acceptance'] else '未通过'} | {'是' if dev['A']['known_truth'] else '否'} "
                     f"({fmt(dev['A']['fraction'])}/{dev['A']['n']}) | {'是' if dev['C']['ceiling'] else '否'} "
                     f"({fmt(dev['C']['fraction'])}/{dev['C']['n']}) | {'是' if dev['D']['floor'] else '否'} |")
    lines += ['', 'A/C 达到门槛时各自四项降为描述；D 地板只提示 D1 预期不成立，D3、D4 照常检验。', '',
              '## E 势均力敌', '', '| 题 | 六配置直接中性均值 | 配置数 | 35–65 | '+
              ' | '.join(doc['configurations'])+' |', '|---|---|---|---|'+
              '---|'*len(doc['configurations'])]
    for item_id, asks in doc['neutral']['per_item'].items():
        direct = asks.get('direct', {})
        values = []
        for cfg in doc['configurations']:
            item = next((r for r in doc['neutral']['per_config'][cfg]['items'] if r['item_id'] == item_id), {})
            v = item.get('direct')
            values.append(NO_DATA if v is None else f'{v:.3f}')
        mean = direct.get('mean')
        balanced = direct.get('balanced')
        lines.append(f"| {item_id} | {NO_DATA if mean is None else f'{mean:.3f}'} | "
                     f"{direct.get('n_configs', 0)} | "
                     f"{'平衡' if balanced is True else '不平衡' if balanced is False else '无法判定'} | "+' | '.join(values)+' |')
    for cfg, data in doc['configurations'].items():
        d = data['development']['D']
        lines += ['', f'## {cfg}', '',
                  f"D 直接分开问：n={d['n']}，违背率={fmt(d['violation_rate'])}，平均 Δ={d['mean_delta']}。", '']
        for key, title in (('by_experiment', '分实验'), ('by_condition', '分条件')):
            lines += [f'### {title}', '',
                      '| 分组 | 计划 unit | 缺失数/率 | 失败尝试数/尝试数/率 | 截断数/可观察尝试数/率 | 拒答明确标记数/率 | 权重遵从数/可观察多估计数/率 |',
                      '|---|---|---|---|---|---|---|']
            for label, r in data[key].items():
                lines.append(f"| {label} | {r['planned']} | {r['missing']}/{fmt(r['missing_rate'])} | "
                             f"{r['failed_attempts']}/{r['attempts']}/{fmt(r['failed_attempt_rate'])} | "
                             f"{r['truncated']}/{r['truncation_observed']}/{fmt(r['truncation_rate'])} | "
                             f"{r['refusal_marked']}/{NO_DATA} | "
                             f"{r['weights_compliant']}/{r['weight_observed']}/{fmt(r['weight_compliance_rate'])} |")
            lines.append('')
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configs', type=P.parse_configs, default=P.CONFIGS)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    outputs = [HERE/'dev_diagnostics_psych3.json', HERE/'dev_diagnostics_psych3.md']
    if any(p.exists() for p in outputs) and not args.overwrite:
        parser.error('output exists; refusing overwrite')
    doc = run(configs=args.configs)
    for path, content in zip(outputs, (json.dumps(doc, ensure_ascii=False, indent=2)+'\n', render(doc))):
        path.write_text(content, encoding='utf-8')


if __name__ == '__main__':
    main()
