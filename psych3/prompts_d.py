"""Experiment D templates, verbatim PLAN v0.5 section 5.4 wording."""
import importlib.util
import json
from pathlib import Path


def _load_dnli(name):
    path = Path(__file__).resolve().parent.parent / "dnli" / (name + ".py")
    spec = importlib.util.spec_from_file_location("_dnli_d_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_dnli = _load_dnli("prompts")
ASK_DIRECT, ASK_MULTI, NO_TOOLS = _dnli.ASK_DIRECT, _dnli.ASK_MULTI, _dnli.NO_TOOLS
ASKS = {"direct": ASK_DIRECT, "multi": ASK_MULTI}
STATEMENTS = ("a", "b", "conj", "disj")
STRATA = ("positive", "independent", "negative")
JOINT_DIRECT = (
    "Give a probability for each statement.\n\n"
    "On the last four lines of your answer, give the answers strictly in the following format, one per line:\n"
    + "".join(f"Statement {k}: NN%\n" for k in range(1, 5))
    + "where each NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
)
JOINT_MULTI = (
    "Give 5 estimates, each estimate being a set of probabilities for all four statements, and give each estimate a weight for how likely you think that estimate is; the weights sum to 1.\n\n"
    "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
    + "".join(f"Estimate {k}: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W\n" for k in range(1, 6))
    + "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1."
)
JOINT_ASKS = {"direct": JOINT_DIRECT, "multi": JOINT_MULTI}


def load_items(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("conjunction_items.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["version"] != "v0.2":
        raise ValueError("Expected conjunction bank v0.2")
    profiles, events = data["profiles"], data["event_pairs"]
    if len(profiles) != 24 or len(events) != 18:
        raise ValueError("Expected 24 profiles and 18 event pairs")
    items = [dict(item, type="P") for item in profiles] + [dict(item, type="W") for item in events]
    if len({item["id"] for item in items}) != 42:
        raise ValueError("Duplicate item IDs")
    for item in items:
        for key in ("id", "context", *(s + "_statement" for s in STATEMENTS)):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError("Missing item field: " + key)
        if item["type"] == "W" and item.get("stratum") not in STRATA:
            raise ValueError("Unknown stratum")
    if any(sum(i.get("stratum") == s for i in events) != 6 for s in STRATA):
        raise ValueError("Expected six pairs per stratum")
    return items


def validate_order(order):
    if order is None or len(order) != 4 or set(order) != set(STATEMENTS):
        raise ValueError("Order must contain a, b, conj, disj exactly once")


def render(item, pres, ask, stmt=None, order=None):
    if ask not in ASKS:
        raise ValueError("Unknown ask")
    frame = "Here is a situation: " + item["context"]
    if pres == "S":
        if stmt not in STATEMENTS or order is not None:
            raise ValueError("S requires one statement and no order")
        question = ("Using common sense, how likely is it that the following statement is true?\n"
                    "Statement: " + item[stmt + "_statement"])
        tail = ASKS[ask]
    elif pres == "J":
        validate_order(order)
        if stmt is not None:
            raise ValueError("J has no stmt")
        question = "Using common sense, how likely is it that each of the following statements is true?\n"
        question += "\n".join(f"Statement {k}: {item[s + '_statement']}" for k, s in enumerate(order, 1))
        tail = JOINT_ASKS[ask]
    else:
        raise ValueError("Unknown presentation")
    return "\n\n".join((frame, question, tail, NO_TOOLS))
