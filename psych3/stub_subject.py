"""Offline scripted subject for runner tests; contains no model integration."""
from copy import deepcopy


def answer(parser='dnli_v2', ask='direct'):
    if parser == 'parse_d':
        if ask == 'direct':
            return '\n'.join(f'Statement {i}: {i * 10}%' for i in range(1, 5))
        return '\n'.join(f'Estimate {i}: S1 10% | S2 20% | S3 30% | S4 40% | Weight: 0.2'
                         for i in range(1, 6))
    if ask == 'direct':
        return 'Estimate: 1200' if parser == 'parse_a' else 'Probability: 60%'
    value = '1200' if parser == 'parse_a' else '60%'
    return '\n'.join(f'Estimate {i}: {value} | Weight: 0.2' for i in range(1, 6))


class StubSubject:
    def __init__(self, script=(), parser='dnli_v2', snapshot=None):
        self.script, self.parser, self.calls = list(script), parser, []
        self.baseline = snapshot or {'agy_version': 'stub', 'reported_model': 'stub-model',
                                     'permissions_sha256': 'stub', 'settings_keys': [],
                                     'agent_sha256': 'stub', 'tools_sha256': 'stub',
                                     'permission_mode': 'sandbox'}

    def snapshot(self, reported_model=None):
        return deepcopy(self.baseline)

    def attempt(self, ask, prompt, tag, seed):
        self.calls.append(dict(ask=ask, prompt=prompt, tag=tag, seed=seed))
        step = self.script.pop(0) if self.script else 'ok'
        if isinstance(step, Exception):
            raise step
        if isinstance(step, dict):
            return deepcopy(step)
        fin = {'state': step}
        if step in ('quota_exhausted', 'quota_stop', 'check_failed', 'call_error'):
            fin.update(stop=True, invalidate_session=step == 'check_failed')
        if step in ('contaminated', 'contaminated_confirmed', 'contaminated_suspected'):
            fin['resample'] = True
        return dict(text='invalid' if step == 'invalid' else answer(self.parser, ask),
                    truncated=step == 'truncated',
                    final={'state': 'ok'} if step == 'invalid' else fin,
                    meta={'snapshot': self.snapshot()})
