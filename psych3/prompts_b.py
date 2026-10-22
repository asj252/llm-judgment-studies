"""Experiment B, verbatim PLAN 3.4 templates, importing delta-NLI wording."""
from prompts_d import _load_dnli

_dnli = _load_dnli('prompts')
ASK_DIRECT, ASK_MULTI, NO_TOOLS = _dnli.ASK_DIRECT, _dnli.ASK_MULTI, _dnli.NO_TOOLS
lower_initial = _dnli.lower_initial
ASKS = {'direct': ASK_DIRECT, 'multi': ASK_MULTI}
CONDITIONS = ('F', 'HI', 'HP', 'PO')
IGNORE = '[Now set aside what you were just told about how things turned out.] '
PROSPECTIVE = 'Using common sense, how likely is it that the following happened as a result?'
RETROSPECTIVE = ('Judging only from the situation described above, how likely would you have said it was '
                 'that the following would happen as a result?')


def render(premise, outcome, condition, ask):
    if condition not in CONDITIONS or ask not in ASKS:
        raise ValueError('Unknown condition or ask')
    parts = [f'Here is a situation: {premise}']
    if condition != 'F':
        lowered = lower_initial(outcome)[0]
        if lowered.endswith('.'):
            lowered = lowered[:-1]
        parts.append(f'Afterwards, it turned out that {lowered}.')
    question = PROSPECTIVE if condition in ('F', 'PO') else (IGNORE if condition == 'HI' else '') + RETROSPECTIVE
    parts += [f'{question}\nStatement: {outcome}', ASKS[ask], NO_TOOLS]
    return '\n\n'.join(parts)
