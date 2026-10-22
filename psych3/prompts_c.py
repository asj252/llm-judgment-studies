"""Experiment C: standard-library templates and exact arithmetic.

Rendering and arithmetic are pure functions; load_stories is the file boundary.
Story wording is preserved verbatim.
"""
import json
from fractions import Fraction
from pathlib import Path

BASE_RATES = (1, 10, 30)
ACCURACY_SETS = {"A": (90, 10), "B": (80, 5)}
FORMATS = ("probability", "frequency")
ASK_DIRECT = 'What is the probability that the statement is true?\n\nOn the last line of your answer, give the answer strictly in the following format:\nProbability: NN%\nwhere NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.'
ASK_MULTI = 'Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.\n\nAt the end of your answer, give the 5 estimates strictly in the following format, one per line:\nEstimate 1: NN% | Weight: W\nEstimate 2: NN% | Weight: W\nEstimate 3: NN% | Weight: W\nEstimate 4: NN% | Weight: W\nEstimate 5: NN% | Weight: W\nwhere each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.'
ASKS = {"direct": ASK_DIRECT, "multi": ASK_MULTI}
NO_TOOLS = "Do not use any tools; answer directly."
PROBABILITY = (
    "Among {population}, {br}% {feature_has}. Each one is checked with {test}; "
    "a positive result means that {positive}. "
    "Of those that {feature_has}, {hit}% get a positive result. "
    "Of all the others, {fa}% also get a positive result."
)
FREQUENCY = (
    "Out of every 10,000 {population}, {n_feat} {feature_has}. "
    "Each one is checked with {test}; a positive result means that {positive}. "
    "Of the {n_feat} that {feature_has}, "
    "{n_hit} get a positive result. Of the other {n_other}, "
    "{n_fa} also get a positive result."
)


def load_stories(path=None):
    """Read and validate the supplied 24-story bank."""
    path = Path(path) if path is not None else Path(__file__).with_name("baserate_stories.json")
    stories = json.loads(path.read_text(encoding="utf-8"))["stories"]
    required = ("id", "population", "feature_has", "test", "positive", "subject", "statement")
    if len(stories) != 24:
        raise ValueError("Expected exactly 24 stories")
    for story in stories:
        if any(not isinstance(story.get(key), str) or not story[key].strip()
               for key in required):
            raise ValueError("Missing or empty story fields")
    if len({story["id"] for story in stories}) != len(stories):
        raise ValueError("Duplicate story IDs")
    return stories


def _percent(value):
    result = Fraction(str(value))
    if not 0 <= result <= 100:
        raise ValueError("Percentages must be between 0 and 100")
    return result


def bayes(br, hit, fa):
    """Return P(feature | positive), in percentage points as a float."""
    br, hit, fa = map(_percent, (br, hit, fa))
    numerator = br * hit
    denominator = numerator + (100 - br) * fa
    if denominator == 0:
        raise ValueError("A positive result has zero probability")
    return float(100 * numerator / denominator)


def frequency_counts(br, hit, fa):
    """Exact counts per 10,000; reject any non-integer count."""
    br, hit, fa = map(_percent, (br, hit, fa))
    n_feat = 100 * br
    n_other = 10000 - n_feat
    counts = {"n_feat": n_feat, "n_other": n_other,
              "n_hit": n_feat * hit / 100, "n_fa": n_other * fa / 100}
    if any(value.denominator != 1 for value in counts.values()):
        raise ValueError("Natural-frequency counts must all be integers")
    return {name: int(value) for name, value in counts.items()}


def situation(story, br, hit, fa, format):
    """Render the exact task-brief situation template."""
    for value in (br, hit, fa):
        _percent(value)
    fields = {key: story[key] for key in ("population", "feature_has", "test", "positive")}
    if format == "probability":
        return PROBABILITY.format(**fields, br=br, hit=hit, fa=fa)
    if format == "frequency":
        counts = {key: f"{value:,}" for key, value in
                  frequency_counts(br, hit, fa).items()}
        return FREQUENCY.format(**fields, **counts)
    raise ValueError(f"Unknown format: {format}")


def render(story, br, acc_set, format, ask):
    """Render the full prompt without rewriting story wording."""
    if acc_set not in ACCURACY_SETS:
        raise ValueError(f"Unknown accuracy set: {acc_set}")
    if ask not in ASKS:
        raise ValueError(f"Unknown ask: {ask}")
    hit, fa = ACCURACY_SETS[acc_set]
    text = situation(story, br, hit, fa, format)
    return (
        f"Here is a situation: {text}\n\n"
        "Now one of them is picked at random from all those with a positive result: "
        f"{story['subject']}. Nothing else is known about this case.\n\n"
        "Using the information above, how likely is it that the following statement is true?\n"
        f"Statement: {story['statement']}\n\n"
        f"{ASKS[ask]}\n\n"
        f"{NO_TOOLS}"
    )
