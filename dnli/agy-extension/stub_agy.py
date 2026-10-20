"""Test-only subprocess agy; never calls a model."""
import json
import os
from pathlib import Path
import sys
if '--version' in sys.argv:
    print('stub-agy 1.3.3')
    sys.exit(0)
payload = json.loads(sys.stdin.readline())
prompt = payload['message']['content']
agent = Path.cwd() / '.agents' / 'agents' / 'dnli-subject.md'
assert {str(f.relative_to(Path.cwd())) for f in Path.cwd().rglob('*') if f.is_file()} == {str(agent.relative_to(Path.cwd()))}
assert agent.read_bytes() == (Path(__file__).resolve().parent / 'agent' / 'dnli-subject.md').read_bytes()
assert sys.argv[sys.argv.index('--agent') + 1] == 'dnli-subject'
assert '--sandbox' in sys.argv and '--model' in sys.argv and '--print' in sys.argv
assert '--continue' not in sys.argv and '--conversation' not in sys.argv
mode = os.environ.get('DNLI_STUB_MODE', 'ok')
cid = 'stub-conversation'
if mode not in ('empty', 'rate', 'timeout'):
    print(json.dumps({'event': 'init', 'conversation_id': cid, 'init': {
        'model': os.environ.get('DNLI_STUB_MODEL', sys.argv[sys.argv.index('--model') + 1]),
        'cwd': str(Path.cwd()), 'agent': 'dnli-subject', 'tools': ['search_web', 'read_url'], 'permission_mode': 'request-review'}}))
if mode == 'timeout':
    import time
    time.sleep(10)
if mode == 'empty':
    sys.exit(0)
if mode == 'rate':
    print('RESOURCE_EXHAUSTED 429', file=sys.stderr)
    sys.exit(1)
if mode in ('search_web', 'read_url'):
    print(json.dumps({'event': 'step_update', 'step_update': {'conversation_id': cid,
        'step_index': 1, 'step_type': 'tool', 'tool_name': mode, 'state': 'DONE'}}))
response = ('\n'.join('Estimate %d: 50%% | Weight: 0.2' % i for i in range(1, 6))
            if 'Give 5 probability estimates' in prompt else 'Probability: 50%')
print(json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': response,
                                             'conversation_id': cid, 'num_turns': 1, 'duration_seconds': 0.1,
                                             'usage': {'input_tokens': 10, 'output_tokens': 20}}}))
