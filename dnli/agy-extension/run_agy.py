"""Copied pure scheduling/material/parse helpers from ../dnli/run.py.
Changed config scheduling, fingerprinting and execution to per-unit agy checkpoints.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import uuid
import unicodedata
import prompts
import parse
from configs import CONFIGS, file_config, validate_rate_patterns
from agy_subject import AgySubject, SnapshotError
HERE = Path(__file__).resolve().parent
MAIN = HERE.parent / 'dnli'
SPLIT_FILE = '../dnli/split.json'
ITEMS_TEXT = '../dnli/raw/items_text.json'
ASKS = ('direct', 'multi')
PRES_POST = ('stated', 'reported')
TYPES = ('S', 'W')
ROUNDS = ('r0', 'r1')
LOCAL = ()
DEFAULT_BLOCKS = 'A'
BASE_SEED = {'dev': 20261080, 'formal': 20261081}
CONFIG_OFFSET = {c: i for i, c in enumerate(CONFIGS)}
PARSE_RULES = {'version': parse.PARSE_VERSION, 'wsum': [parse.WSUM_LO, parse.WSUM_HI], 'n_estimates': parse.N_ESTIMATES,
               'endpoint': [parse.ENDPOINT_LO, parse.ENDPOINT_HI]}
class Stop(Exception):
    def __init__(self, reason, units=()):
        super().__init__(reason)
        self.units = tuple(units)

class Pause(Exception):
    """Queue interruption: preserve retry state without invalidating a unit."""
    def __init__(self, reason, code=4):
        super().__init__(reason)
        self.code = code

def persist_stop(meta_path, meta, exc, now):
    stamp = now.isoformat()
    units = list(dict.fromkeys(exc.units)) or ([meta['active_unit']] if meta.get('active_unit') else [])
    for session in meta['sessions']:
        if session.get('unit') in units:
            session.update(invalid=True, invalid_reason=str(exc), invalid_at=stamp)
    meta['stopped'] = meta.get('stopped') or {
        'unit': units[0] if len(units) == 1 else None, 'units': units,
        'reason': str(exc), 'datetime': stamp}
    save_json(meta_path, meta)
    save_json(str(meta_path) + '.stop.json', meta['stopped'])

class ModelLock:
    def __init__(self, path):
        self.path = Path(path)
    def __enter__(self):
        self.file = self.path.open('a+b')
        try:
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.file.write(b'0')
                    self.file.flush()
                    self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise Stop('model process already holds lock: ' + str(self.path))
        return self
    def __exit__(self, *args):
        if os.name == 'nt':
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()

def planned_items(items, which, cfg, blocks=None):
    blocks = blocks or DEFAULT_BLOCKS
    if cfg not in CONFIGS:
        raise ValueError(cfg)
    return {k: it for k, it in items.items() if it['use'] == which
            and (which != 'formal' or it.get('formal_block') in blocks)}

def make_schedule(items, which, cfg, split, blocks=None):
    rng = random.Random(BASE_SEED[which] * 10 + CONFIG_OFFSET[cfg])
    keys = sorted(planned_items(items, which, cfg, blocks))
    rng.shuffle(keys)
    schedule = []
    for key in keys:
        units = units_for(items[key], which, split)
        rng.shuffle(units)
        schedule.extend(units)
    return schedule

def fingerprint(base, cfg, all_items, split, blocks='A', policy=None):
    base = Path(base)
    files = (SPLIT_FILE, ITEMS_TEXT, 'prompts.py', 'parse.py', 'run_agy.py', 'agy_subject.py', 'configs.py', 'workspace_temp.py', 'brief-e-agy.md', 'agent/dnli-subject.md')
    fp = {f: _sha((base / f).read_bytes()) for f in files}
    fp['templates'] = _sha(json.dumps(prompts.templates(), sort_keys=True, ensure_ascii=False).encode('utf-8'))
    fp['parse_rules'] = _sha(json.dumps(PARSE_RULES, sort_keys=True).encode('utf-8'))
    fp['materials_digest'], fp['n_units_all'] = materials_digest(all_items, split)
    # A -> AB is an approved plan extension, not a change to prompt/material rules.
    fp.update(config=cfg, policy=policy or {})
    return fp, _sha(json.dumps(fp, sort_keys=True).encode('utf-8'))

def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def record_hash(record):
    return _sha(json.dumps(record, sort_keys=True, ensure_ascii=False).encode('utf-8'))

def valid_records(records, sessions, fp_id):
    by_id = {s['session_id']: s for s in sessions if s.get('closed_ok') and not s.get('invalid')
             and s.get('fingerprint_id') == fp_id}
    keep = {}
    found = set()
    for r in records:
        s = by_id.get(r.get('session_id'))
        if s and r.get('fingerprint_id') == fp_id:
            if s.get('unit') != r.get('unit') or s.get('record_sha256') != record_hash(r):
                raise Stop('checkpoint integrity: ' + str(s['unit']), (s['unit'],))
            for attempt in r.get('attempts', []):
                m = attempt.get('meta', {})
                for suffix, digest in m.get('raw_sha256', {}).items():
                    p = Path(m['raw_prefix'] + suffix)
                    if not p.is_file() or _sha(p.read_bytes()) != digest:
                        raise Stop('raw attempt integrity: ' + r['unit'], (r['unit'],))
            keep[r['unit']] = r
            found.add(r['session_id'])
    if set(by_id) - found:
        raise Stop('registered checkpoint result missing', [by_id[sid]['unit'] for sid in set(by_id) - found])
    return keep

class RetryPolicy:
    def __init__(self, initial=300, cap=3600, max_continuous=21600, sleep=time.sleep, now=None, max_unit=259200):
        if initial <= 0 or cap < initial or max_continuous <= 0 or max_unit <= 0:
            raise ValueError('invalid backoff policy')
        self.initial, self.cap, self.max_continuous = initial, cap, max_continuous
        self.max_unit = max_unit
        self.sleep, self.now = sleep, now or (lambda: dt.datetime.now().astimezone())
        self.state = {'rate_since': None, 'delay': initial, 'wake_at': None, 'daily': {},
                      'unit_rate_since': None, 'retry_count': 0}

    def wait(self, seconds, progress):
        # Persist target before sleeping so a reboot preserves the next eligible call time.
        target = self.now() + dt.timedelta(seconds=seconds)
        self.state['wake_at'] = target.isoformat()
        progress()
        self.resume_wait(progress)

    def resume_wait(self, progress):
        wake = self.state.get('wake_at')
        if not wake:
            return
        target = dt.datetime.fromisoformat(wake)
        while self.now() < target:
            part = min(60, (target - self.now()).total_seconds())
            before = self.now()
            self.sleep(part)
            day = before.date().isoformat()
            row = self.state['daily'].setdefault(day, {'rate_count': 0, 'wait_seconds': 0})
            row['wait_seconds'] += max(0, (self.now() - before).total_seconds())
            progress()
        self.state['wake_at'] = None
        progress()

    def limited(self, progress):
        now = self.now()
        if self.state.get('unit_rate_since') is None:
            self.state['unit_rate_since'] = now.isoformat()
        if (now - dt.datetime.fromisoformat(self.state['unit_rate_since'])).total_seconds() >= self.max_unit:
            raise Stop('unit continuous rate limit duration exceeded')
        day = now.date().isoformat()
        self.state['daily'].setdefault(day, {'rate_count': 0, 'wait_seconds': 0})['rate_count'] += 1
        if self.state['rate_since'] is None:
            self.state['rate_since'] = now.isoformat()
        elapsed = (now - dt.datetime.fromisoformat(self.state['rate_since'])).total_seconds()
        if elapsed >= self.max_continuous:
            tomorrow = (now + dt.timedelta(days=1)).date()
            target = dt.datetime.combine(tomorrow, dt.time(0, 10), tzinfo=now.tzinfo)
            self.state['rate_since'] = None
            self.state['delay'] = self.initial
            self.wait((target - now).total_seconds(), progress)
        else:
            delay = self.state['delay']
            self.state['delay'] = min(delay * 2, self.cap)
            self.wait(delay, progress)

    def check_unit_duration(self):
        since = self.state.get('unit_rate_since')
        if since and (self.now() - dt.datetime.fromisoformat(since)).total_seconds() >= self.max_unit:
            raise Stop('unit continuous rate limit duration exceeded')

    def clear(self):
        self.state.update(rate_since=None, unit_rate_since=None, delay=self.initial)

def run_unit(cfg, which, item, u, subj, policy, progress, check_snapshot):
    prompt = render_unit(item, u)
    wait_before = sum(row['wait_seconds'] for row in policy.state['daily'].values())
    attempts, streak_state, streak, parse_failures = [], None, 0, 0
    while True:
        policy.check_unit_duration()
        if hasattr(policy, 'before_attempt'):
            policy.before_attempt(subj)
        n = len(attempts)
        r = subj.attempt(u[3], prompt, _safe(unit_id(u)) + '_a' + str(n), call_seed(cfg, u, n, which))
        check_snapshot(r['meta']['snapshot'], unit_id(u))
        if hasattr(policy, 'after_attempt'):
            policy.after_attempt(r)
        fin = r['final']
        att = {'state': fin['state'], 'reasons': fin.get('reasons', []), 'meta': r['meta'],
               'truncated': r.get('truncated'), 'parsed': None}
        attempts.append(att)
        if fin['state'] == 'rate_limited':
            policy.limited(progress)
            continue
        policy.clear()
        if fin.get('stop'):
            raise Stop(unit_id(u) + ': ' + str(fin))
        if fin.get('resample'):
            streak = streak + 1 if streak_state == fin['state'] else 1
            streak_state = fin['state']
            if streak >= 3:
                raise Stop(unit_id(u) + ': 3 consecutive ' + streak_state)
            policy.state['retry_count'] = policy.state.get('retry_count', 0) + 1
            progress()
            continue
        streak, streak_state = 0, None
        ok, result = judge_text(u[3], r['text'])
        att.update(parsed=ok, parse=result)
        if ok:
            status = 'ok'
            break
        parse_failures += 1
        if parse_failures < 2:
            policy.state['retry_count'] = policy.state.get('retry_count', 0) + 1
            progress()
        if parse_failures >= 2:
            status, result = 'missing', None
            break
    return {'unit': unit_id(u), 'key': u[0], 'pres': u[1], 'utype': u[2], 'ask': u[3], 'round': u[4],
            'update_id': update_id(item, u), 'cluster': item['cluster'], 'use': item['use'], 'config': cfg,
            'status': status, 'result': result, 'n_attempts': len(attempts), 'attempts': attempts,
            'n_retries': max(0, sum(a['state'] != 'rate_limited' for a in attempts) - 1),
            'rate_wait_seconds': sum(row['wait_seconds'] for row in policy.state['daily'].values()) - wait_before,
            'prompt_sha256': _sha(prompt.encode('utf-8'))}

def execute(which, cfg, items, split, subj, fp, fp_id, results_path, meta_path, policy=None, log=print, blocks='A'):
    policy = policy or RetryPolicy()
    meta = load_json(meta_path, {'sessions': []})
    if meta.get('stopped') or Path(str(meta_path) + '.stop.json').exists():
        log('STOP pending a review: persistent stop')
        return 3
    try:
        return _execute(which, cfg, items, split, subj, fp, fp_id, results_path, meta_path, policy, log, blocks)
    except (Stop, SnapshotError) as exc:
        snapshot_failed = isinstance(exc, SnapshotError)
        if isinstance(exc, SnapshotError):
            exc = Stop(str(exc))
        meta = load_json(meta_path, {'sessions': []})
        if not snapshot_failed and not exc.units:
            exc.units = tuple(s['unit'] for s in meta['sessions'] if s.get('closed_ok') and not s.get('invalid'))
        persist_stop(meta_path, meta, exc, policy.now())
        log('STOP ' + str(exc))
        return 3

def _execute(which, cfg, items, split, subj, fp, fp_id, results_path, meta_path, policy=None, log=print, blocks='A'):
    policy = policy or RetryPolicy()
    required_baseline = getattr(subj, 'required_baseline', None)
    meta = load_json(meta_path, {'sessions': [], 'baseline': required_baseline})
    if required_baseline and meta.get('baseline') not in (None, required_baseline):
        raise Stop('development/formal environment baselines differ')
    sessions = meta['sessions']
    if any(s.get('closed_ok') and not s.get('invalid') and s.get('fingerprint') != fp for s in sessions):
        raise Stop('checkpoint fingerprint details changed')
    if meta.get('fingerprint_id') not in (None, fp_id):
        raise Stop('fingerprint changed; a must review')
    meta['fingerprint_id'] = fp_id
    if meta.get('retry_state'):
        policy.state = meta['retry_state']
    records = load_records(results_path)
    done = valid_records(records, sessions, fp_id)
    expected = {s['session_id'] for s in sessions if s.get('closed_ok') and not s.get('invalid')}
    if expected - {r.get('session_id') for r in records}:
        raise Stop('checkpoint result missing')
    schedule = make_schedule(items, which, cfg, split, blocks)
    meta['blocks'] = blocks
    planned = {unit_id(u) for u in schedule}
    if set(done) - planned:
        raise Stop('existing checkpoints outside requested plan')
    def persist():
        meta['retry_state'] = policy.state
        save_json(meta_path, meta)
    last_day = None
    def progress():
        nonlocal last_day
        day = policy.now().date().isoformat()
        persist()
        if day != last_day:
            if last_day is not None:
                log('DAILY_CLOSED ' + json.dumps({'day': last_day, 'config': cfg, 'completed': len(done),
                     **policy.state['daily'].get(last_day, {'rate_count': 0, 'wait_seconds': 0}), 'model_changed': False}))
            last_day = day
            row = policy.state['daily'].get(day, {'rate_count': 0, 'wait_seconds': 0})
            log('DAILY ' + json.dumps({'day': day, 'config': cfg, 'completed': len(done), **row,
                                     'model_changed': False}, ensure_ascii=False))
    def check_snapshot(snap, unit):
        baseline = meta.get('baseline')
        if baseline is None:
            meta['baseline'] = snap
            persist()
        elif baseline.get('reported_model') is None and snap.get('reported_model') is not None:
            if any(snap.get(k) != baseline.get(k) for k in ('agy_version', 'permissions_sha256', 'settings_keys', 'agent_sha256')):
                raise Stop('environment changed before first reported model from ' + unit)
            baseline['reported_model'] = snap['reported_model']
            for field in ('tools_sha256', 'permission_mode'):
                if field in snap:
                    baseline[field] = snap[field]
            persist()
        elif any(snap.get(k) is not None and snap.get(k) != baseline.get(k) for k in baseline):
            meta['stopped'] = {'unit': unit, 'reason': 'environment_changed', 'snapshot': snap}
            persist()
            log('STOP environment_changed from ' + unit + ': ' + json.dumps(snap))
            raise Stop('environment changed from ' + unit)
    if meta.get('stopped'):
        raise Stop('pending a review: ' + str(meta['stopped']))
    try:
        policy.resume_wait(progress)
        for u in schedule:
            uid = unit_id(u)
            if uid in done:
                continue
            if hasattr(policy, 'before_unit'):
                policy.before_unit()
            snap = subj.snapshot((meta.get('baseline') or {}).get('reported_model'))
            check_snapshot(snap, uid)
            meta['active_unit'] = uid
            meta['active_snapshot'] = snap
            progress()
            rec = run_unit(cfg, which, items[u[0]], u, subj, policy, progress, check_snapshot)
            sid = uuid.uuid4().hex
            rec.update(session_id=sid, fingerprint_id=fp_id)
            Path(results_path).parent.mkdir(parents=True, exist_ok=True)
            with open(results_path, 'a', encoding='utf-8', newline='\n') as f:
                if Path(results_path).stat().st_size and not Path(results_path).read_bytes().endswith(b'\n'):
                    f.write('\n')
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            # Read-back before atomically closing the independent unit checkpoint.
            if record_hash(load_records(results_path)[-1]) != record_hash(rec):
                raise Stop('result read-back failed: ' + uid)
            sessions.append({'session_id': sid, 'unit': uid, 'fingerprint': fp, 'fingerprint_id': fp_id,
                             'closed_ok': True, 'invalid': False, 'status': 'finished',
                             'snapshot': meta['baseline'], 'record_sha256': record_hash(rec)})
            sessions[-1]['plan_blocks'] = blocks
            meta['active_unit'] = None
            done[uid] = rec
            persist()
            log('[%d/%d] %s -> %s' % (len(done), len(schedule), uid, rec['status']))
        log('DAILY_FINAL ' + json.dumps({'config': cfg, 'completed': len(done), 'days': policy.state['daily'],
                                       'retry_count': policy.state.get('retry_count', 0)}))
        return 0
    except Pause as exc:
        persist()
        log('PAUSE ' + str(exc))
        return exc.code
    except Stop as exc:
        meta['retry_state'] = policy.state
        persist_stop(meta_path, meta, exc, policy.now())
        log('STOP ' + str(exc))
        return 3

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('which', choices=('dev', 'formal'))
    ap.add_argument('config', choices=CONFIGS)
    ap.add_argument('--blocks', choices=('A', 'AB'), default='A')
    ap.add_argument('--agy', default='agy')
    ap.add_argument('--settings', default=str(__import__('agy_subject').DEFAULT_SETTINGS))
    ap.add_argument('--timeout', type=float, default=600)
    ap.add_argument('--backoff-initial', type=float, default=300)
    ap.add_argument('--backoff-cap', type=float, default=3600)
    ap.add_argument('--rate-max-hours', type=float, default=6)
    ap.add_argument('--rate-unit-max-days', type=float, default=3)
    ap.add_argument('--rate-patterns', help='UTF-8 JSON array; probe-approved diagnostic patterns')
    a = ap.parse_args()
    cfgfile = file_config(a.config)
    paths = lambda w: (HERE / ('results_%s_%s.jsonl' % (w, cfgfile)), HERE / ('run_meta_%s_%s.json' % (w, cfgfile)))
    try:
        with ModelLock(HERE / (cfgfile + '.lock')):
            patterns = json.loads(Path(a.rate_patterns).read_text(encoding='utf-8')) if a.rate_patterns else __import__('agy_subject').RATE_PATTERNS
            patterns = validate_rate_patterns(patterns)
            policy_spec = {'initial': a.backoff_initial, 'cap': a.backoff_cap, 'max_continuous': a.rate_max_hours * 3600,
                           'max_unit': a.rate_unit_max_days * 86400,
                           'rate_patterns': list(patterns), 'timeout': a.timeout}
            items, split = load_all_items()
            fp, fp_id = fingerprint(HERE, a.config, items, split, a.blocks, policy_spec)
            if a.which == 'formal':
                rp, mp = paths('dev')
                dev_meta = load_json(mp, {'sessions': []})
                if dev_meta.get('stopped') or Path(str(mp) + '.stop.json').exists():
                    raise Stop('development has persistent stop; a must review')
                try:
                    dev = valid_records(load_records(rp), dev_meta['sessions'], fp_id)
                except Stop as exc:
                    persist_stop(mp, dev_meta, exc, dt.datetime.now().astimezone())
                    raise
                expected = {unit_id(u) for u in make_schedule(items, 'dev', a.config, split)}
                if set(dev) != expected:
                    raise Stop('complete matching development checkpoints required')
            raw = HERE / 'raw' / ('run_' + a.which + '_' + cfgfile)
            subj = AgySubject(a.config[4:], raw, (a.agy,), a.settings, a.timeout, patterns)
            try:
                if a.which == 'formal':
                    subj.required_baseline = dev_meta.get('baseline')
                rp, mp = paths(a.which)
                # OS lock survives abrupt termination without leaving a stale exclusive-create lock.
                return execute(a.which, a.config, items, split, subj, fp, fp_id, rp, mp,
                                   RetryPolicy(a.backoff_initial, a.backoff_cap, a.rate_max_hours * 3600,
                                               max_unit=a.rate_unit_max_days * 86400), blocks=a.blocks)
            finally:
                subj.close()
    except (Stop, RuntimeError, OSError, ValueError) as exc:
        print('REFUSED:', exc)
        return 2


def _sha(b):
    return hashlib.sha256(b).hexdigest()

def base_units(key, rnd="r0"):
    """一对题的 10 个 unit（先验 2 ＋ 后验 2 类型 × 2 呈现 × 2 问法）。"""
    out = [(key, "prior", "-", a, rnd) for a in ASKS]
    out += [(key, p, t, a, rnd) for p in PRES_POST for t in TYPES for a in ASKS]
    return out

def units_for(item, which, split):
    k = item["key"]
    out = base_units(k, "r0")
    if which == "formal" and k in split["repeat_subset"]:
        out += base_units(k, "r1")
    return out

def unit_id(u):
    return "|".join(u)

def call_seed(cfg, u, attempt, which):
    s = "%s|%s|%s|a%d|%d" % (which, cfg, unit_id(u), attempt, BASE_SEED[which])
    return int(_sha(s.encode("utf-8"))[:8], 16)

def render_unit(item, u):
    _, pres, utype, ask, _ = u
    return prompts.render_item(item, pres, utype, ask)

def update_id(item, u):
    return None if u[1] == "prior" else item[u[2] + "_id"]

def materials_digest(all_items, split):
    """全部题（dev＋正式；正式含重复轮）每个 unit 的渲染提示哈希的摘要。与配置、与 which 无关（dev 与正式共用同一指纹）。"""
    rows = []
    for k in sorted(all_items):
        it = all_items[k]
        for u in units_for(it, it["use"], split):
            rows.append([unit_id(u), update_id(it, u), _sha(render_unit(it, u).encode("utf-8"))])
    return _sha(json.dumps(rows, ensure_ascii=False).encode("utf-8")), len(rows)

def judge_text(ask, text):
    raw = parse.PARSERS[ask](text)
    normalized = ''.join(' ' if unicodedata.category(ch) == 'Zs' else ch for ch in text)
    r = parse.PARSERS[ask](normalized)
    out = {k: r.get(k) for k in ("value", "error", "forms")}
    out.update(parse_raw_ok=raw['ok'], normalized=normalized != text)
    if ask == "multi":
        out.update({k: r.get(k) for k in ("estimates", "weights", "weight_sum", "weight_sum_in_tolerance", "endpoint_mass", "weighted_sd")})
    return r["ok"], out

def _safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)[:120]

def load_json(p, default):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def load_records(p):
    p = Path(p)
    if not p.exists():
        return []
    records = []
    for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            # Incomplete append after power loss is unregistered crash debris.
            # Registered checkpoint completeness is checked by execute/load_valid.
            continue
    return records

def load_all_items(base=HERE):
    """清单里全部题（dev＋正式）及其题面；题面缺题或多题就拒绝。"""
    split = json.loads((Path(base) / SPLIT_FILE).read_text(encoding="utf-8"))
    text = json.loads((Path(base) / ITEMS_TEXT).read_text(encoding="utf-8"))
    keys = {it["key"] for it in split["items"]}
    if set(text) != keys:
        raise Stop("题面与清单的题不一致：%d 对 %d" % (len(text), len(keys)))
    items = {}
    for it in split["items"]:
        t = text[it["key"]]
        if t["S_id"] != it["S"]["id"] or t["W_id"] != it["W"]["id"]:
            raise Stop("题面的选句 ID 与清单不符：%s" % it["key"])
        items[it["key"]] = dict(t, key=it["key"], use=it["use"], cluster=it["cluster"],
                                formal_block=it.get('formal_block') if it['use'] == 'formal' else None)
    return items, split

def load_items(which, base=HERE):
    all_items, split = load_all_items(base)
    return {k: v for k, v in all_items.items() if v["use"] == which}, split, all_items

if __name__ == '__main__':
    sys.exit(main())
