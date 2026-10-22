"""PLAN v0.6.4: pure psych3 statistics, cluster bootstrap and reporting.

An item is {exp, item_id, cluster, cells, ...material metadata}. Cell keys are
tuples beginning with ask: A (ask, frame, level), B (ask, condition, k),
C (ask, format, base_rate), D (ask, presentation, statement), E (ask, cell).
Absent cells are missing. No model, disk, or runner dependencies.
"""
import math
import random
import statistics as st
from collections import defaultdict

B_DEFAULT, SEED, ALPHA = 5000, 2026101903, .05
ASKS = ('direct', 'multi')
BR = (1, 10, 30)
STATEMENTS = ('a', 'b', 'conj', 'disj')
SPECS = {f'{e}{i}': dict(sided=2 if e == 'E' or i >= 3 else 1,
                        threshold=(.1 if e == 'A' else .2 if e == 'C' and i < 4 else 5.))
         for e in 'ABCDE' for i in range(1, 5)}


def mean(xs):
    xs = list(xs)
    return st.fmean(xs) if xs else None


def logit(p, clip=.5):
    p = min(100-clip, max(clip, p))/100
    return math.log(p/(1-p))


def regression(values, clip=.5):
    x, y = [logit(b, 0) for b in BR], [logit(v, clip) for v in values]
    xm, ym = mean(x), mean(y)
    slope = sum((a-xm)*(b-ym) for a, b in zip(x, y))/sum((a-xm)**2 for a in x)
    return dict(slope=slope, intercept=ym-slope*xm)


def slope_limit(clip=.5):
    """Exact finite box bound, rather than rounding +/-3.01 inward."""
    x = [logit(b, 0) for b in BR]
    xm = mean(x)
    return sum(abs(a-xm) for a in x)/sum((a-xm)**2 for a in x)*abs(logit(clip, clip))


def bayes(item, br):
    hit, false = (.9, .1) if item['acc_set'] == 'A' else (.8, .05)
    p = br/100
    return 100*hit*p/(hit*p+false*(1-p))


def expression(exp, name):
    """Constant and coefficients of raw cells or A/C derived components."""
    d, m = ASKS
    def diff(ask, cond):
        if exp == 'A':
            return {(ask, cond): 1}
        if exp == 'B':
            if cond == 'b':
                return {(ask, c, k): s/2 for c, s in [('HI', 1), ('F', -1)] for k in (1, 2)}
            if cond == 'wording':
                return {(ask, c, k): s/2 for c, s in [('HP', 1), ('HI', -1)] for k in (1, 2)}
            return {(ask, 'PO', k): -.5 for k in (1, 2)}
        if exp == 'C':
            return {(ask, cond): 1}
        if exp == 'D':
            return {(ask, cond, 'conj'): 1, (ask, cond, 'b'): -1}
        return {(ask, cond+'_T'): 1, (ask, cond+'_O'): -1}
    def combine(*parts):
        out = defaultdict(float)
        for factor, part in parts:
            for k, v in part.items():
                out[k] += factor*v
        return {k: v for k, v in out.items() if v}
    i = int(name[1:])
    if exp == 'A':
        irr = diff(d, 'irrelevant')
        sel = combine((1, diff(d, 'informative')), (-1, irr))
        terms = [irr, sel, combine((1, diff(m, 'irrelevant')), (-1, irr)),
                 combine((1, diff(m, 'informative')), (-1, diff(m, 'irrelevant')), (-1, sel))][i-1]
    elif exp == 'B':
        terms = [diff(d, 'b'), diff(d, 'wording'),
                 combine((1, diff(m, 'b')), (-1, diff(d, 'b'))),
                 combine((1, diff(m, 'po')), (-1, diff(d, 'po')))][i-1]
    elif exp == 'C':
        terms = [combine((-1, diff(d, 'probability'))),
                 combine((1, diff(d, 'frequency')), (-1, diff(d, 'probability'))),
                 combine((1, diff(m, 'probability')), (-1, diff(d, 'probability'))),
                 combine((1, diff(m, 'error')), (-1, diff(d, 'error')))][i-1]
    elif exp == 'D':
        terms = [diff(d, 'S'), combine((1, diff(d, 'S')), (-1, diff(d, 'J'))),
                 combine((1, diff(m, 'S')), (-1, diff(d, 'S'))),
                 combine((1, diff(m, 'J')), (-1, diff(d, 'J')))][i-1]
    else:
        cond = 'status' if i in (1, 3) else 'default'
        terms = diff(d, cond) if i < 3 else combine((1, diff(m, cond)), (-1, diff(d, cond)))
    return (1. if name == 'C1' else 0.), terms


def component(item, key):
    """(value or None, feasible lower, feasible upper, missing raw cells)."""
    exp, cells = item['exp'], item['cells']
    if exp == 'A':
        ask, frame = key
        keys = [(ask, frame, level) for level in ('low', 'high')]
        missing = [k for k in keys if cells.get(k) is None]
        if missing:
            return None, None, None, missing
        low, high = [cells[k] for k in keys]
        v = (math.log(high)-math.log(low))/(math.log(item['high'])-math.log(item['low']))
        return v, v, v, []
    if exp == 'C':
        ask, fmt = key
        error = fmt == 'error'
        keys = [(ask, 'probability' if error else fmt, b) for b in BR]
        missing = [k for k in keys if cells.get(k) is None]
        if error:
            lo, hi = [], []
            for k, b in zip(keys, BR):
                truth = bayes(item, b)
                v = cells.get(k)
                lo.append(0 if v is None else abs(v-truth))
                hi.append(max(truth, 100-truth) if v is None else abs(v-truth))
            return (None if missing else mean(lo)), mean(lo), mean(hi), missing
        if missing:
            limit = slope_limit()
            return None, -limit, limit, missing
        v = regression([cells[k] for k in keys])['slope']
        return v, v, v, []
    if exp == 'D' and key[1] == 'J':
        keys = [(key[0], 'J', s) for s in STATEMENTS]
        if any(cells.get(k) is None for k in keys):
            return None, 0., 100., [k for k in keys if cells.get(k) is None]
    v = cells.get(key)
    return (v, 0., 100., [key]) if v is None else (v, v, v, [])


def contribution(item, name):
    constant, terms = expression(item['exp'], name)
    value = lo = hi = constant
    missing = set()
    for key, coef in terms.items():
        v, a, b, absent = component(item, key)
        missing.update(absent)
        value = None if value is None or v is None else value+coef*v
        if a is None:
            lo = hi = None
        elif lo is not None:
            lo += coef*(a if coef > 0 else b)
            hi += coef*(b if coef > 0 else a)
    return dict(value=value, lower=lo, upper=hi, missing=sorted(missing))


def cluster_values(items, name):
    """C: require both accuracy items complete, then average within story."""
    groups = defaultdict(list)
    for item in items:
        if item['exp'] == name[0] and not (name[0] == 'D' and item.get('type') != 'P'):
            groups[str(item['cluster'])].append(item)
    out = {}
    for cl, items_in_cluster in sorted(groups.items()):
        if name[0] == 'C':
            present = {i['acc_set'] for i in items_in_cluster}
            items_in_cluster = items_in_cluster + [dict(items_in_cluster[0], acc_set=acc, cells={})
                                                   for acc in ('A', 'B') if acc not in present]
        rows = [contribution(i, name) for i in items_in_cluster]
        out[cl] = dict(value=mean(r['value'] for r in rows) if all(r['value'] is not None for r in rows) else None,
                       lower=mean(r['lower'] for r in rows) if all(r['lower'] is not None for r in rows) else None,
                       upper=mean(r['upper'] for r in rows) if all(r['upper'] is not None for r in rows) else None,
                       n_items=len(rows), missing_cells=sum(len(r['missing']) for r in rows))
    return out


def bootstrap(values, B=B_DEFAULT, seed=SEED):
    values = list(values)
    if B < 1:
        raise ValueError('B must be positive')
    if not values:
        return []
    rng, n = random.Random(seed), len(values)
    return [sum(values[rng.randrange(n)] for _ in range(n))/n for _ in range(B)]


def interval(reps, alpha=ALPHA, sided=2):
    if not reps:
        return [None, None]
    xs = sorted(reps)
    k = int(math.floor(alpha*len(xs)/(2 if sided == 2 else 1)+1e-9))
    return [xs[k], xs[-1-k] if sided == 2 else None]


def tails(lower_reps, upper_reps=None):
    upper_reps = lower_reps if upper_reps is None else upper_reps
    if not lower_reps or not upper_reps:
        return 1., 1.
    return (sum(v <= 0 for v in lower_reps)/len(lower_reps),
            sum(v >= 0 for v in upper_reps)/len(upper_reps))


def holm(pvalues, alpha=ALPHA):
    """p ties by hypothesis ID; intervals retain rank alpha even after stop."""
    out, active = {}, True
    for rank, name in enumerate(sorted(pvalues, key=lambda n: (pvalues[n], n)), 1):
        level = alpha/(len(pvalues)-rank+1)
        reject = active and pvalues[name] <= level
        active = reject
        out[name] = dict(rank=rank, alpha=level, rejected=reject)
    return out


def decision(point, near, sign, rejected, threshold, sided=2):
    if point is None or near is None or not rejected or sign*near <= 0:
        return dict(directional=False, strength=None, label='证据不足')
    if sign*near > threshold:
        strength = 'bound_exceeds'
        label = '区间上界低于负阈值' if sign < 0 and sided == 2 else '区间下界超过阈值'
    elif sign*point >= threshold:
        strength, label = 'point_reaches', '点估计达到阈值'
    else:
        strength, label = 'point_below', '点估计未达阈值'
    return dict(directional=True, strength=strength, label=label)


def _family_pass(samples, names, B, seed, conservative=False):
    rows, pvalues = {}, {}
    for name in names:
        allrows = samples[name]
        good = [r for r in allrows.values() if r['value'] is not None]
        lows = [r['lower'] for r in allrows.values()] if conservative else [r['value'] for r in good]
        highs = [r['upper'] for r in allrows.values()] if conservative else lows
        lr, ur = bootstrap(lows, B, seed), bootstrap(highs, B, seed)
        pos, neg = tails(lr, ur)
        sided = SPECS[name]['sided']
        sign = 1 if sided == 1 or pos <= neg else -1
        pvalues[name] = pos if sided == 1 else min(1., 2*min(pos, neg))
        rows[name] = dict(point=mean(lows if sign > 0 else highs), p=pvalues[name], sign=sign,
                          n_clusters=len(lows), n_items=sum(r['n_items'] for r in (allrows.values() if conservative else good)),
                          missing_cells=sum(r['missing_cells'] for r in allrows.values()),
                          _lr=lr, _ur=ur)
    ranks = holm(pvalues)
    for name, row in rows.items():
        row.update(ranks[name])
        sided, sign = SPECS[name]['sided'], row['sign']
        lr, ur = row.pop('_lr'), row.pop('_ur')
        lo = interval(lr, row['alpha'], sided)[0]
        hi = interval(ur, row['alpha'], 2)[1] if sided == 2 else None
        near = lo if sign > 0 else hi
        row.update(interval=[lo, hi], near=near)
        row.update(decision(row['point'], near, sign, row['rejected'], SPECS[name]['threshold'], sided))
        if sided == 1 and ur:
            upper = sorted(ur)[-1-int(math.floor(row['alpha']*len(ur)+1e-9))]
            row['opposite_direction'] = dict(upper=upper, observed=upper < 0,
                                              label='反方向描述，未作确认性拒绝')
    return rows


def analyse_family(items, names, B=B_DEFAULT, seed=SEED):
    names = list(names)
    if not names:
        return dict(complete_subset={}, missing_protection=None, combined=True)
    if len(set(n[0] for n in names)) != 1 or len(set(names)) != len(names):
        raise ValueError('one experiment family with unique IDs required')
    if any(n not in SPECS for n in names):
        raise ValueError('unknown hypothesis')
    samples = {n: cluster_values(items, n) for n in names}
    return analyse_samples(samples, names, B, seed)


def analyse_samples(samples, names, B=B_DEFAULT, seed=SEED):
    """Shared family inference for raw data and simulated cluster contributions."""
    complete = _family_pass(samples, names, B, seed)
    missing = any(r['value'] is None for rows in samples.values() for r in rows.values())
    protected = None
    if missing and names[0][0] != 'A':
        protected = _family_pass(samples, names, B, seed, True)
    for name in names:
        c = complete[name]
        final = dict(c)
        if names[0][0] == 'A' and any(r['value'] is None for r in samples[name].values()):
            final['label'] += '（完整题子集，缺失未受保护）'
            final['missing_protected'] = False
        elif protected is not None:
            p = protected[name]
            strength = {None: 0, 'point_below': 1, 'point_reaches': 2, 'bound_exceeds': 3}
            passed = (c['directional'] and p['directional'] and c['sign'] == p['sign'] and
                      strength[p['strength']] >= strength[c['strength']])
            if passed:
                final['label'] += '（缺失按最不利值代入）'
            else:
                final['label'] = '完整题子集：'+c['label']+'；缺失保护：未通过'
            final['missing_protected'] = passed
            # Expose the weaker retained level separately, without upgrading main analysis.
            final['retained_strength'] = (min((c['strength'], p['strength']), key=strength.get)
                                          if c['sign'] == p['sign'] and p['directional'] and c['directional'] else None)
            final['strength'] = final['retained_strength']
            final['directional'] = final['retained_strength'] is not None
        c['final'] = final
    return dict(complete_subset=complete, missing_protection=protected, combined=not missing)


def summary(values, B=B_DEFAULT, seed=SEED):
    values = list(values)
    return dict(n=len(values), mean=mean(values), sd=st.stdev(values) if len(values)>1 else None,
                interval=interval(bootstrap(values, B, seed)))


def weighted_mass(result, predicate, statement=None):
    estimates = result.get('estimates')
    if statement and isinstance(estimates, dict):
        estimates = estimates.get(statement)
    weights = result.get('normalized_weights') or result.get('weights')
    if not estimates or not weights or sum(weights) <= 0:
        return None
    return sum(w for v, w in zip(estimates, weights) if predicate(v))/sum(weights)


def _paired(rows, getter, B, seed):
    groups = defaultdict(list)
    expected = _cluster_counts(rows)
    for item in rows:
        d, m = getter(item, 'direct'), getter(item, 'multi')
        if d is not None and m is not None:
            groups[str(item['cluster'])].append((d, m))
    pairs = [(mean(v[0] for v in vs), mean(v[1] for v in vs)) for cl, vs in groups.items()
             if rows[0]['exp'] != 'C' or len(vs) == expected[cl]] if rows else []
    return dict(direct=summary([d for d, m in pairs], B, seed),
                multi=summary([m for d, m in pairs], B, seed),
                difference=summary([m-d for d, m in pairs], B, seed))


def _cluster_counts(rows):
    counts = defaultdict(int)
    for i in rows:
        counts[str(i['cluster'])] += 1
    return counts


def value_of(item, terms, constant=0):
    if any(item['cells'].get(k) is None for k in terms):
        return None
    return constant+sum(item['cells'][k]*v for k, v in terms.items())


def spearman(pairs):
    """Average ranks for ties, no scipy dependency; no test or p value."""
    if len(pairs)<2:
        return None
    def ranks(xs):
        out = [0.]*len(xs)
        order = sorted(range(len(xs)), key=xs.__getitem__)
        start = 0
        while start<len(order):
            end = start+1
            while end<len(order) and xs[order[start]] == xs[order[end]]:
                end += 1
            for j in order[start:end]:
                out[j] = (start+end-1)/2
            start = end
        return out
    x, y = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    xm, ym = mean(x), mean(y)
    denom = math.sqrt(sum((v-xm)**2 for v in x)*sum((v-ym)**2 for v in y))
    return sum((a-xm)*(b-ym) for a, b in zip(x, y))/denom if denom else None


def descriptive_groups(details, items, B, seed):
    """Summaries of preregistered strata, retaining raw item details separately."""
    bins, human = defaultdict(list), defaultdict(list)
    for row, item in zip(details, items):
        exp = row['exp']
        if exp == 'A':
            for key, result in row['values'].items():
                bins[str(('A', row.get('source'), key, 'log_error'))].append(result['log_error'])
        elif exp == 'B':
            for ask in ASKS:
                for k in (1, 2):
                    result = row['values'][ask][str(k)]
                    if result['b'] is not None and result['F_rank'] is not None:
                        bins[str(('B', ask, result['F_rank'], 'b'))].append(result['b'])
                    f, h = item['cells'].get((ask, 'F', k)), item.get('human', {}).get(k)
                    if f is not None and h is not None:
                        for rating, value in h.items():
                            if value is not None:
                                human[(ask, rating)].append((f, value))
        elif exp == 'C':
            for key, result in row['values'].items():
                for metric in ('nonmonotonic', 'clipped_fraction', 'within_one'):
                    if metric in result:
                        bins[str(('C', key, metric))].append(result[metric])
        elif exp == 'D':
            for key, result in row['values'].items():
                for metric in ('violation', 'delta', 'delta_min', 'X', 'disjunction_excess', 'b_below_a', 'candidate_violation_mass'):
                    if result.get(metric) is not None:
                        bins[str(('D', row.get('type'), row.get('dependence'), key, metric))].append(result[metric])
        elif exp == 'E':
            for ask in ASKS:
                r = row['values'][ask]
                for op in ('status', 'default', 'recommend'):
                    v = r[op]['effect']
                    if v is not None:
                        bins[str(('E', row.get('target_position'), ask, op))].append(v)
    return dict(strata={k: summary(v, B, seed) for k, v in sorted(bins.items())},
                B_F_human_spearman={str((ask, rating)): dict(n=len(human[(ask, rating)]), rho=spearman(human[(ask, rating)]), role='primary' if rating=='mean' else 'secondary', descriptive_only=True)
                                     for ask in ASKS for rating in ('mean', 'median')},
                human_note='mean_response 为主，median_response 为辅；均仅描述，无评分时不计算')


def descriptive(items, B=B_DEFAULT, seed=SEED, dnli_s=None):
    """Raw-scale paired 95% intervals plus pre-registered item diagnostics."""
    cross, detail = {}, []
    for exp in 'ABCDE':
        rows = [i for i in items if i['exp'] == exp and (exp != 'D' or i.get('type') == 'P')]
        quantities = {}
        if exp == 'A':
            for frame in ('irrelevant', 'informative'):
                quantities['AI_'+frame] = lambda i, a, f=frame: component(i, (a, f))[0]
            quantities['S'] = lambda i, a: _subtract(component(i, (a, 'informative'))[0], component(i, (a, 'irrelevant'))[0])
        elif exp == 'B':
            quantities['b'] = lambda i, a: value_of(i, {(a, c, k): s/2 for c, s in [('HI', 1), ('F', -1)] for k in (1, 2)})
            quantities['e_PO'] = lambda i, a: value_of(i, {(a, 'PO', k): -.5 for k in (1, 2)}, 100)
        elif exp == 'C':
            for fmt in ('probability', 'frequency', 'error'):
                quantities[fmt] = lambda i, a, f=fmt: component(i, (a, f))[0]
        elif exp == 'D':
            for pres in ('S', 'J'):
                quantities['delta_'+pres] = lambda i, a, p=pres: _subtract(component(i, (a, p, 'conj'))[0], component(i, (a, p, 'b'))[0])
        else:
            for op in ('status', 'default', 'recommend'):
                quantities['E_'+op] = lambda i, a, o=op: value_of(i, {(a, o+'_T'): 1, (a, o+'_O'): -1})
        cross[exp] = {q: _paired(rows, getter, B, seed) for q, getter in quantities.items()}
    for item in items:
        exp, cells = item['exp'], item['cells']
        results = item.get('results', {})
        row = dict(exp=exp, item_id=item['item_id'], cluster=item['cluster'], values={})
        v = row['values']
        if exp == 'A':
            row['source'] = item.get('source')
            for k, y in cells.items():
                v[str(k)] = dict(log_error=math.log(y)-math.log(item['true_value']))
                if k[1] != 'none':
                    anchor = item[k[2]]
                    v[str(k)]['candidate_below_anchor_mass'] = weighted_mass(results.get(k, {}), lambda x: x<anchor)
                    v[str(k)]['candidate_above_anchor_mass'] = weighted_mass(results.get(k, {}), lambda x: x>anchor)
                    v[str(k)]['candidate_beyond_anchor_mass'] = weighted_mass(results.get(k, {}), lambda x: x>anchor if k[2]=='high' else x<anchor)
                    comparison = results.get(k, {}).get('comparison')
                    v[str(k)]['comparison_consistent'] = None if comparison is None else comparison == ('higher' if y>anchor else 'lower' if y<anchor else 'equal')
        elif exp == 'B':
            for ask in ASKS:
                fs = [cells.get((ask, 'F', k)) for k in (1, 2)]
                v[ask] = dict(c=value_of(item, {(ask, c, k): s/2 for c, s in [('PO', 1), ('F', -1)] for k in (1, 2)}))
                for k in (1, 2):
                    f, hi = cells.get((ask, 'F', k)), cells.get((ask, 'HI', k))
                    v[ask][str(k)] = dict(b=None if f is None or hi is None else hi-f,
                         F_rank=None if None in fs else 'tie' if fs[0] == fs[1] else 'higher' if f == max(fs) else 'lower',
                         candidate_below_F_mass=None if f is None else weighted_mass(results.get((ask, 'HI', k), {}), lambda x: x<f))
        elif exp == 'C':
            for ask in ASKS:
                for fmt in ('probability', 'frequency'):
                    ys = [cells.get((ask, fmt, b)) for b in BR]
                    r = dict(points=[dict(base_rate=b, reported=y, bayes=bayes(item, b)) for b, y in zip(BR, ys)])
                    if None not in ys:
                        r.update(regression(ys), sensitive_clip=regression(ys, .1),
                                 nonmonotonic=any(a>b for a, b in zip(ys, ys[1:])),
                                 clipped_fraction=mean(y<=.5 or y>=99.5 for y in ys),
                                 within_one=mean(abs(y-bayes(item, b))<=1 for y, b in zip(ys, BR)))
                    for point, b in zip(r['points'], BR):
                        parsed = results.get((ask, fmt, b), {})
                        es = parsed.get('estimates') or []
                        distance = min((abs(x-bayes(item, b)) for x in es), default=None)
                        point['closest_candidate_weight'] = None if distance is None else weighted_mass(parsed, lambda x: abs(x-bayes(item, b)) == distance)
                    v[str((ask, fmt))] = r
        elif exp == 'D':
            row.update(type=item.get('type'), dependence=item.get('dependence'))
            for ask in ASKS:
                for pres in ('S', 'J'):
                    ys = {s: component(item, (ask, pres, s))[0] for s in STATEMENTS}
                    delta = _subtract(ys['conj'], ys['b'])
                    r = dict(delta=delta, violation=None if delta is None else delta>0)
                    if all(y is not None for y in ys.values()):
                        r.update(delta_min=ys['conj']-min(ys['a'], ys['b']), X=ys['a']+ys['b']-ys['conj']-ys['disj'],
                                 disjunction_excess=max(ys['a'], ys['b'])-ys['disj'], b_below_a=ys['b']<ys['a'])
                    parsed = results.get((ask, pres, 'conj'), {})
                    if pres == 'J' and isinstance(parsed.get('estimates'), dict):
                        es = parsed['estimates']
                        ws = parsed.get('normalized_weights') or parsed.get('weights')
                        r['candidate_violation_mass'] = sum(w for c, b, w in zip(es['conj'], es['b'], ws) if c>b)/sum(ws)
                    v[str((ask, pres))] = r
        elif exp == 'E':
            row['target_position'] = item.get('target_position')
            for ask in ASKS:
                neutral = cells.get((ask, 'neutral'))
                r = dict(neutral=neutral)
                for op in ('status', 'default', 'recommend'):
                    t, o = cells.get((ask, op+'_T')), cells.get((ask, op+'_O'))
                    r[op] = dict(effect=_subtract(t, o), T_minus_neutral=_subtract(t, neutral), neutral_minus_O=_subtract(neutral, o))
                r['recommend_minus_status'] = _subtract(r['recommend']['effect'], r['status']['effect'])
                r['recommend_minus_default'] = _subtract(r['recommend']['effect'], r['default']['effect'])
                r['status_minus_default'] = _subtract(r['status']['effect'], r['default']['effect'])
                v[ask] = r
            row['candidate_50_mass'] = {str(k): dict(below=weighted_mass(r, lambda x: x<50), above=weighted_mass(r, lambda x: x>50), equal=weighted_mass(r, lambda x: x==50)) for k, r in results.items() if k[0] == 'multi'}
        detail.append(row)
    return dict(cross_experiment=cross, item_details=detail, grouped=descriptive_groups(detail, items, B, seed), dnli_s=dnli_s,
                dnli_note='未提供 δ-NLI s 时留空，不读取其他实验结果',
                language=('与某模式相容', '仍无法区分'))


def _subtract(a, b):
    return None if a is None or b is None else a-b


def development_diagnostics(items):
    a, c, d, neutral = [], [], [], []
    for i in items:
        cells = i['cells']
        if i['exp'] == 'A':
            for ask in ASKS:
                y = cells.get((ask, 'none', 'none'))
                if y is not None:
                    a.append(abs(y/i['true_value']-1)<=.05+1e-12)
        elif i['exp'] == 'C':
            c += [abs(y-bayes(i, k[2]))<=1 for k, y in cells.items() if k[0] == 'direct']
        elif i['exp'] == 'D' and i.get('type') == 'P':
            delta = _subtract(cells.get(('direct', 'S', 'conj')), cells.get(('direct', 'S', 'b')))
            if delta is not None:
                d.append(delta)
        elif i['exp'] == 'E':
            neutral.append(dict(item_id=i['item_id'], direct=cells.get(('direct', 'neutral')), multi=cells.get(('multi', 'neutral'))))
    return dict(A=dict(n=len(a), fraction=mean(a), known_truth=bool(a) and mean(a)>=.8,
                       descriptive=['A1', 'A2', 'A3', 'A4'] if a and mean(a)>=.8 else []),
                C=dict(n=len(c), fraction=mean(c), ceiling=bool(c) and mean(c)>=.8,
                       descriptive=['C1', 'C2', 'C3', 'C4'] if c and mean(c)>=.8 else []),
                D=dict(n=len(d), violation_rate=mean(v>0 for v in d), mean_delta=mean(d),
                       floor=bool(d) and max(d)<=0 and mean(d)<=-20,
                       note='D3、D4 照常检验；满足地板条件时注明 D1 预期不成立'),
                E=dict(items=neutral, **{a: summary([r[a] for r in neutral if r[a] is not None], B=200) for a in ASKS},
                       note='势均力敌按全部配置的直接中性报数均值在 35–65 判定；须显式汇总配置'))


def neutral_across_configs(by_config):
    """Per-item across-configuration means, plus each configuration's values."""
    per_item = defaultdict(lambda: defaultdict(list))
    for cfg, items in by_config.items():
        for item in items:
            if item['exp'] == 'E':
                for ask in ASKS:
                    v = item['cells'].get((ask, 'neutral'))
                    if v is not None:
                        per_item[item['item_id']][ask].append(v)
    return dict(per_item={k: {a: dict(mean=mean(v), n_configs=len(v),
                                    balanced=(35<=mean(v)<=65) if a=='direct' and len(v)==len(by_config) else None)
                                 for a, v in asks.items()} for k, asks in sorted(per_item.items())},
                per_config={cfg: development_diagnostics(items)['E'] for cfg, items in by_config.items()})


def recommendation_control(items, B=B_DEFAULT, seed=SEED):
    out = {}
    rows = [i for i in items if i['exp'] == 'E']
    for ask in ASKS:
        vals, lows, highs = [], [], []
        for i in rows:
            t, o = i['cells'].get((ask, 'recommend_T')), i['cells'].get((ask, 'recommend_O'))
            if t is not None and o is not None:
                vals.append(t-o)
            lows.append((t if t is not None else 0)-(o if o is not None else 100))
            highs.append((t if t is not None else 100)-(o if o is not None else 0))
        point = mean(vals)
        out[ask] = dict(complete=summary(vals, B, seed), n_planned=len(rows),
                        missing_bounds=[mean(lows), mean(highs)],
                        conservative_interval=[interval(bootstrap(lows, B, seed))[0], interval(bootstrap(highs, B, seed))[1]],
                        note='无法评估' if point is None else '推荐对照在该问法下未达预设响应门槛' if point<5 else '达到预设响应门槛',
                        interpretation_downgrade=point is None or point<5,
                        affected_hypotheses=['E1', 'E2', 'E3', 'E4'] if ask == 'direct' else ['E3', 'E4'])
    return out


def repeat_description(items, repeats):
    by_id = {(i['exp'], i['item_id']): i for i in items}
    differences = defaultdict(list)
    for rep in repeats:
        first = by_id.get((rep['exp'], rep['item_id']))
        if first:
            for k, v in rep['cells'].items():
                if first['cells'].get(k) is not None:
                    differences[str((rep['exp'],)+k)].append(v-first['cells'][k])
    return {k: dict(n=len(v), differences=v, mean=mean(v),
                    difference_sd=st.stdev(v) if len(v)>1 else None,
                    call_sd=math.sqrt(mean(x*x for x in v)/2)) for k, v in differences.items()}
