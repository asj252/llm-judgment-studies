"""Sequential local-night queue; no scheduler registration or model discovery."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import time
import run_agy as R
from agy_subject import AgySubject, DEFAULT_SETTINGS, RATE_PATTERNS
from configs import file_config, validate_rate_patterns
from probe_agy import MODELS

def next_monday(now):
    days = (7 - now.weekday()) % 7 or 7
    return dt.datetime.combine(now.date() + dt.timedelta(days=days), dt.time(), now.tzinfo)

def deadline_today(now, value):
    return dt.datetime.combine(now.date(), dt.time.fromisoformat(value), now.tzinfo)

class NightPolicy(R.RetryPolicy):
    def __init__(self, deadline, quota_hours=2, now=None, sleep=time.sleep,
                 exhausted_patterns=(), initial=300, cap=3600, timeout=600):
        super().__init__(initial, cap, quota_hours*3600, sleep, now)
        self.deadline, self.timeout = deadline, timeout
        self.exhausted_patterns = exhausted_patterns

    def before_unit(self):
        if self.now() >= self.deadline:
            raise R.Pause('night deadline')

    def check_unit_duration(self):
        since = self.state.get('rate_since')
        if since and (self.now()-dt.datetime.fromisoformat(since)).total_seconds() > self.max_continuous:
            raise R.Pause('quota skip threshold', 5)

    def before_attempt(self, subj):
        self.check_unit_duration()
        remaining = (self.deadline + dt.timedelta(minutes=15)-self.now()).total_seconds()
        if remaining <= 0:
            raise R.Pause('deadline grace exceeded')
        subj.timeout = min(self.timeout, remaining)
        subj.call_deadline = self.deadline + dt.timedelta(minutes=15)
        subj.deadline_now = self.now

    def after_attempt(self, r):
        # A cleanup failure is a STOP, even at the deadline.
        if r['meta'].get('kill_tree_error'):
            raise R.Stop('timeout tree cleanup failed')
        if r['final'].get('stop'):
            raise R.Stop('attempt STOP: ' + str(r['final']))
        if self.now() >= self.deadline + dt.timedelta(minutes=15):
            raise R.Pause('deadline grace exceeded; redo unfinished unit')
        if r['final']['state'] == 'rate_limited' and self.exhausted_patterns:
            prefix = r['meta'].get('raw_prefix')
            if prefix:
                from agy_subject import parse_stream
                diagnostic = Path(prefix+'.stderr.txt').read_text(encoding='utf-8')
                errors = parse_stream(Path(prefix+'.stream.jsonl').read_text(encoding='utf-8'))['errors']
                # Only registered diagnostic patterns, never response/usage.
                def error_text(obj):
                    parts = []
                    for key in ('message', 'error', 'code', 'status', 'detail', 'details'):
                        value = obj.get(key)
                        if isinstance(value, str):
                            parts.append(value)
                        elif isinstance(value, dict):
                            parts.append(error_text(value))
                    return '\n'.join(parts)
                diagnostic += '\n' + '\n'.join(error_text(e) for e in errors)
                if any(re.search(p, diagnostic, re.I) for p in self.exhausted_patterns):
                    raise R.Pause('probe-approved quota exhaustion', 5)

    def resume_wait(self, progress):
        wake = self.state.get('wake_at')
        if not wake:
            return
        target = dt.datetime.fromisoformat(wake)
        while self.now() < target:
            self.check_unit_duration()
            self.before_unit()
            part = min(60, (target-self.now()).total_seconds(),
                       (self.deadline-self.now()).total_seconds())
            before = self.now()
            self.sleep(part)
            day = before.date().isoformat()
            row = self.state['daily'].setdefault(day, {'rate_count': 0, 'wait_seconds': 0})
            row['wait_seconds'] += max(0, (self.now()-before).total_seconds())
            progress()
        self.state['wake_at'] = None
        progress()

    def limited(self, progress):
        now = self.now()
        if self.state.get('rate_since') is None:
            self.state['rate_since'] = now.isoformat()
        self.check_unit_duration()
        row = self.state['daily'].setdefault(now.date().isoformat(), {'rate_count': 0, 'wait_seconds': 0})
        row['rate_count'] += 1
        delay = self.state['delay']
        self.state['delay'] = min(delay*2, self.cap)
        self.wait(delay, progress)

def acceptance(records, expected, stopped=False):
    rows = [r for uid, r in records.items() if uid in expected]
    def first_ok(r):
        a = (r.get('attempts') or [{}])[0]
        return a.get('state') == 'ok' and not a.get('truncated') and a.get('parsed') is True
    first = sum(first_ok(r) for r in rows)/len(rows) if rows else None
    missing = sum(r['status'] != 'ok' for r in rows)/len(expected) if expected else None
    return {'passed': bool(expected) and set(records) == expected and not stopped
            and first is not None and first >= .9 and missing <= .02,
            'first_success_rate_attempted': first, 'missing_rate_planned': missing,
            'attempted': len(rows), 'planned': len(expected), 'stopped': stopped}

class Queue:
    def __init__(self, root=R.HERE, models=MODELS, now=None, sleep=time.sleep,
                 deadline='08:00', quota_hours=2, factory=AgySubject, log=print,
                 command=('agy',), settings=DEFAULT_SETTINGS, timeout=600,
                 exhausted_patterns=(), rate_patterns=RATE_PATTERNS):
        self.root, self.models = Path(root), tuple(models)
        self.now = now or (lambda: dt.datetime.now().astimezone())
        self.sleep, self.factory, self.log = sleep, factory, log
        self.deadline = deadline_today(self.now(), deadline)
        self.quota_hours, self.timeout = quota_hours, timeout
        self.command, self.settings = command, settings
        self.exhausted_patterns, self.rate_patterns = exhausted_patterns, rate_patterns
        self.state_path = self.root/'raw'/'queue_state.json'
        self.state = R.load_json(self.state_path, {'models': {}, 'nights': []})
        for model in self.models:
            self.state['models'].setdefault(model, {'stage': 'dev', 'completed': {'dev': 0, 'formal': 0},
                                                  'skipped_until': None, 'needs_review': None})

    def save(self):
        R.save_json(self.state_path, self.state)

    def paths(self, model, stage):
        cfg = file_config('agy:'+model)
        return (self.root/('results_%s_%s.jsonl' % (stage, cfg)),
                self.root/('run_meta_%s_%s.json' % (stage, cfg)))

    def eligible(self, row):
        until = row.get('skipped_until')
        return row['stage'] != 'done' and not row.get('needs_review') and (
            not until or dt.datetime.fromisoformat(until) <= self.now())

    def run(self, items, split):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with R.ModelLock(self.root/'raw'/'queue.lock'):
            # Reload only under lock: another night's updates must not be overwritten.
            self.state = R.load_json(self.state_path, self.state)
            night = {'started': self.now().isoformat(), 'completed': {}, 'wait_seconds': {}}
            self.state['nights'].append(night)
            self.save()
            try:
                for model in self.models:
                    row = self.state['models'][model]
                    if self.now() >= self.deadline:
                        break
                    if not self.eligible(row):
                        continue
                    try:
                        with R.ModelLock(self.root/(file_config('agy:'+model)+'.lock')):
                            if row.get('skipped_until'):
                                for stage in ('dev', 'formal'):
                                    mp = self.paths(model, stage)[1]
                                    meta = R.load_json(mp, {})
                                    if meta.get('retry_state'):
                                        meta['retry_state'].update(rate_since=None, unit_rate_since=None, delay=300)
                                        R.save_json(mp, meta)
                            row['skipped_until'] = None
                            self.run_model(model, row, items, split, night)
                    except (R.Stop, RuntimeError, OSError, ValueError) as exc:
                        row['needs_review'] = {'reason': str(exc), 'datetime': self.now().isoformat()}
                    self.save()
            finally:
                night['ended'] = self.now().isoformat()
                self.save()
                self.log('NIGHT_SUMMARY ' + json.dumps(night, ensure_ascii=False))
        return self.state

    def run_model(self, model, row, items, split, night):
        cfg = 'agy:'+model
        spec = {'queue': True, 'quota_skip_hours': self.quota_hours, 'timeout': self.timeout,
                'rate_patterns': list(self.rate_patterns), 'exhausted_patterns': list(self.exhausted_patterns),
                'night_queue_sha256': R._sha(Path(__file__).read_bytes())}
        fp, fp_id = R.fingerprint(self.root, cfg, items, split, 'A', spec)
        for stage in ('dev', 'formal'):
            # Always revalidate development before entering or resuming formal.
            rp, mp = self.paths(model, stage)
            if stage == 'formal' and row['stage'] != 'formal':
                break
            policy = NightPolicy(self.deadline, self.quota_hours, self.now, self.sleep,
                                 self.exhausted_patterns, timeout=self.timeout)
            subj = self.factory(model, self.root/'raw'/('run_'+stage+'_'+file_config(cfg)),
                                command=self.command, settings=self.settings, timeout=self.timeout,
                                rate_patterns=self.rate_patterns)
            try:
                if stage == 'formal':
                    subj.required_baseline = R.load_json(self.paths(model, 'dev')[1], {}).get('baseline')
                before_meta = R.load_json(mp, {})
                before_count = row['completed'].get(stage, 0)
                before_wait = sum(v['wait_seconds'] for v in before_meta.get('retry_state', {}).get('daily', {}).values())
                code = R.execute(stage, cfg, items, split, subj, fp, fp_id, rp, mp, policy, self.log, 'A')
            finally:
                if hasattr(subj, 'close'):
                    subj.close()
            meta = R.load_json(mp, {'sessions': []})
            records = R.valid_records(R.load_records(rp), meta['sessions'], fp_id)
            row['completed'][stage] = len(records)
            night['completed'][model] = night['completed'].get(model, 0) + len(records)-before_count
            total_wait = sum(v['wait_seconds'] for v in meta.get('retry_state', {}).get('daily', {}).values())
            night['wait_seconds'][model] = night['wait_seconds'].get(model, 0) + total_wait-before_wait
            if code == 5:
                row['skipped_until'] = next_monday(self.now()).isoformat()
                # Leave all retry state intact; expired wake_at is cleared naturally next week.
                return
            if code == 4:
                return
            if code != 0:
                raise R.Stop(str(meta.get('stopped') or 'run STOP'))
            expected = {R.unit_id(u) for u in R.make_schedule(items, stage, cfg, split, 'A')}
            if stage == 'dev':
                row['acceptance'] = acceptance(records, expected, bool(meta.get('stopped')))
                if not row['acceptance']['passed']:
                    raise R.Stop('development acceptance failed: '+json.dumps(row['acceptance']))
                row['stage'] = 'formal'
                self.save()
                if self.now() >= self.deadline:
                    return
            else:
                if set(records) != expected:
                    raise R.Stop('formal plan incomplete')
                row['stage'] = 'done'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deadline', default='08:00')
    ap.add_argument('--quota-skip-hours', type=float, default=2)
    ap.add_argument('--models', nargs='+', choices=MODELS, default=MODELS)
    ap.add_argument('--agy', default='agy')
    ap.add_argument('--settings', default=str(DEFAULT_SETTINGS))
    ap.add_argument('--timeout', type=float, default=600)
    ap.add_argument('--exhausted-patterns', help='probe-approved UTF-8 JSON regex list; unset by default')
    ap.add_argument('--rate-patterns', help='UTF-8 JSON regex list')
    a = ap.parse_args()
    exhausted = validate_rate_patterns(R.load_json(a.exhausted_patterns, [])) if a.exhausted_patterns else ()
    patterns = validate_rate_patterns(R.load_json(a.rate_patterns, [])) if a.rate_patterns else RATE_PATTERNS
    items, split = R.load_all_items()
    Queue(deadline=a.deadline, quota_hours=a.quota_skip_hours, command=(a.agy,),
          settings=a.settings, timeout=a.timeout, exhausted_patterns=exhausted,
          rate_patterns=patterns, models=a.models).run(items, split)

if __name__ == '__main__':
    main()
