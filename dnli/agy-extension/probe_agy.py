"""Neutral schema probes. Running this entry point requires a's probe approval."""
import argparse
import json
import os
from pathlib import Path
from agy_subject import AgySubject, final_inclusion, parse_stream, validate_model_name
from run_agy import HERE, save_json

MODELS = ('gpt-oss-120b-medium', 'claude-sonnet-5-5-medium',
          'gemini-3.8-flash-low', 'gemini-3.8-flash-high')
# Literal prompts: no experiment materials are read by this module.
PROMPTS = (
    'What is 17 + 25? Reply with just the number.',
    'Here is a situation: A man is walking down a dry street on a sunny afternoon.\n\n'
    'Using common sense, how likely is it that the following statement is true?\n'
    'Statement: It rained earlier today.\n\n'
    'What is the probability that the statement is true?\n\n'
    'On the last line of your answer, give the answer strictly in the following format:\n'
    'Probability: NN%\n'
    'where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.\n\n'
    'Do not use any tools; answer directly.',
    'Here is a situation: A man is walking down a dry street on a sunny afternoon.\n\n'
    'Using common sense, how likely is it that the following statement is true?\n'
    'Statement: It rained earlier today.\n\n'
    'Give 5 probability estimates that the statement is true, each with a weight for how likely you think '
    'that estimate is; the weights sum to 1.\n\n'
    'At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n'
    'Estimate 1: NN% | Weight: W\nEstimate 2: NN% | Weight: W\n'
    'Estimate 3: NN% | Weight: W\nEstimate 4: NN% | Weight: W\nEstimate 5: NN% | Weight: W\n'
    'where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a '
    'number from 0 to 1 (decimals allowed); the five weights sum to 1.\n\n'
    'Do not use any tools; answer directly.',
    "Use your web search tool to find today's date, then tell me the date.",
    "List the exact names of every tool or function you can call in this conversation. If none, say NONE. Do not call any.",
)

def inspect_stream(stdout):
    out = {'event_types': [], 'step_types': [], 'field_paths': [],
           'models_versions': [], 'usage_tokens': [], 'errors': [], 'tool_steps': []}
    def walk(v, path='$'):
        if isinstance(v, dict):
            for k, child in v.items():
                p = path + '.' + k
                out['field_paths'].append(p)
                if k in ('step_type', 'type', 'kind', 'message_type', 'content_type'):
                    out['step_types'].append(child)
                if 'model' in k.lower() or 'version' in k.lower():
                    out['models_versions'].append({'path': p, 'value': child})
                if 'usage' in k.lower() or 'token' in k.lower():
                    out['usage_tokens'].append({'path': p, 'value': child})
                if 'error' in k.lower():
                    out['errors'].append({'path': p, 'value': child})
                walk(child, p)
        elif isinstance(v, list):
            for child in v:
                walk(child, path + '[]')
    for line in stdout.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            out['errors'].append({'raw_line': line})
            continue
        walk(obj)
        if isinstance(obj, dict):
            out['event_types'].append(obj.get('event'))
            if obj.get('event') == 'error':
                out['errors'].append(obj)
    out['tool_steps'] = parse_stream(stdout)['tools']
    for k in ('event_types', 'step_types', 'field_paths'):
        out[k] = sorted(set(str(v) for v in out[k]))
    return out

def probe(models=MODELS, output=HERE/'raw'/'probe', factory=AgySubject, **kwargs):
    models = tuple(validate_model_name(model) for model in models)
    output = Path(output)
    summary = {'models': {}}
    for model in models:
        options = dict(kwargs)
        if options.get('workroot') is None:
            local = os.environ.get('LOCALAPPDATA')
            if not local:
                raise RuntimeError('LOCALAPPDATA is required for the agy probe work directory')
            options['workroot'] = Path(local) / 'dnli-agy-work' / 'probe' / model
        subj = factory(model, output/model, **options)
        try:
            rows = []
            for i, prompt in enumerate(PROMPTS, 1):
                r = subj.attempt('multi' if i == 3 else 'direct', prompt, 'probe_%d' % i, 0)
                prefix = r['meta']['raw_prefix']
                stdout = Path(prefix+'.stream.jsonl').read_text(encoding='utf-8')
                stderr = Path(prefix+'.stderr.txt').read_text(encoding='utf-8')
                info = inspect_stream(stdout)
                info.update(prompt=prompt, meta=r['meta'], stderr=stderr,
                            inclusion=final_inclusion({'events': parse_stream(stdout), 'stderr': stderr,
                                                      'returncode': r['meta']['returncode'],
                                                      'timed_out': r['meta']['timed_out']}))
                if i == 5:
                    results = parse_stream(stdout, expected_agent='dnli-subject')['results']
                    info['answer'] = results[0].get('response') if len(results) == 1 else None
                    info['record_only'] = True
                if i != 4:
                    info.pop('tool_steps')
                rows.append(info)
            summary['models'][model] = {
                'calls': rows,
                'tool_list_answer': rows[4]['answer'],
                **{k: sorted(set(v for row in rows for v in row[k]))
                   for k in ('event_types', 'step_types', 'field_paths')}}
        finally:
            subj.close()
    save_json(output/'summary.json', summary)
    return summary

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--models', nargs='+', type=validate_model_name, default=MODELS)
    ap.add_argument('--output', type=Path, default=HERE/'raw'/'probe')
    ap.add_argument('--agy', default='agy')
    ap.add_argument('--settings', default=str(__import__('agy_subject').DEFAULT_SETTINGS))
    a = ap.parse_args()
    probe(a.models, a.output, command=(a.agy,), settings=a.settings)

if __name__ == '__main__':
    main()
