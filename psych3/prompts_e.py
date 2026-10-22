"""Experiment E (status quo, default, advisor): standard-library prompt templates.

Rendering and unit enumeration are pure functions; load_items is the file boundary.
Item wording is preserved verbatim.
"""
import json
import re
from pathlib import Path

CELLS = (
    "neutral",
    "status_T",
    "status_O",
    "default_T",
    "default_O",
    "advisor_T",
    "advisor_O",
)

ASK_DIRECT = (
    "What is the probability that Option {T} is the better choice for {name}?\n\n"
    "On the last line of your answer, give the answer strictly in the following format:\n"
    "Probability: NN%\n"
    "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
)

ASK_MULTI = (
    "Give 5 probability estimates that Option {T} is the better choice for {name}, "
    "each with a weight for how likely you think that estimate is; the weights sum to 1.\n\n"
    "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
    "Estimate 1: NN% | Weight: W\n"
    "Estimate 2: NN% | Weight: W\n"
    "Estimate 3: NN% | Weight: W\n"
    "Estimate 4: NN% | Weight: W\n"
    "Estimate 5: NN% | Weight: W\n"
    "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, "
    "and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1."
)

ASKS = {"direct": ASK_DIRECT, "multi": ASK_MULTI}

STATUS_TEMPLATE = (
    "{name} is currently on Option {X}. {name} was assigned to it at random when signing up; "
    "the assignment did not take {name}'s situation or preferences into account."
)
DEFAULT_TEMPLATE = (
    "The sign-up form has Option {X} pre-selected. The pre-selection is set at random by the system "
    "and does not take {name}'s situation or preferences into account."
)
ADVISOR_TEMPLATE = (
    "An independent advisor who reviewed {name}'s situation in detail recommends Option {X}."
)
SHARED_LINE = (
    "Both options are available. Switching between them costs nothing and can be undone at any time."
)
QUESTION_TEMPLATE = "What is the probability that Option {T} is the better choice for {name}?"
NO_TOOLS = "Do not use any tools; answer directly."

REQUIRED_FIELDS = ("id", "domain", "name", "context", "option_P", "option_Q", "target")
TEXT_FIELDS = ("context", "option_P", "option_Q")
_YOU_RE = re.compile(r"\b(?:you|your)\b", re.IGNORECASE)
_MANIPULATION_WORDS_RE = re.compile(
    r"\b(?:"
    r"currently"
    r"|pre-selected"
    r"|preselected"
    r"|default"
    r"|recommend(?:s|ed)?"
    r"|advisor"
    r"|adviser"
    r"|assigned"
    r"|at\s+random"
    r"|sign-up\s+form"
    r")\b",
    re.IGNORECASE,
)
_ID_NUM_RE = re.compile(r"(\d+)$")


def _option_attributes(option_text):
    """Return non-empty semicolon-separated attribute segments."""
    return [part.strip() for part in option_text.split(";") if part.strip()]


def load_items(path=None):
    """Read and validate the 40-item status-quo bank."""
    path = Path(path) if path is not None else Path(__file__).with_name("items_e_draft.json")
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list) or len(items) != 40:
        raise ValueError("Expected a list of exactly 40 items")

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each item must be a dict")
        if any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in REQUIRED_FIELDS
        ):
            raise ValueError("Missing or empty required item fields")

    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Duplicate item IDs")
    if len({item["name"].strip().lower() for item in items}) != len(items):
        raise ValueError("Duplicate item names")

    for idx, item in enumerate(items, start=1):
        target = item["target"]
        if target not in ("P", "Q"):
            raise ValueError(f"Invalid target for {item['id']}: {target}")
        match = _ID_NUM_RE.search(item["id"])
        item_num = int(match.group(1)) if match else idx
        expected_by_idx = "P" if idx % 2 == 1 else "Q"
        expected_by_id = "P" if item_num % 2 == 1 else "Q"
        if target != expected_by_idx or target != expected_by_id:
            raise ValueError(
                f"Target parity mismatch for {item['id']} at index {idx}: got {target}"
            )
        for text_key in TEXT_FIELDS:
            if _YOU_RE.search(item[text_key]):
                raise ValueError(f"Second-person pronoun found in {item['id']}.{text_key}")
            manip_match = _MANIPULATION_WORDS_RE.search(item[text_key])
            if manip_match:
                raise ValueError(
                    f"Forbidden manipulation term {manip_match.group(0)!r} found in {item['id']}.{text_key}"
                )
        for opt_key in ("option_P", "option_Q"):
            attrs = _option_attributes(item[opt_key])
            if len(attrs) not in (2, 3):
                raise ValueError(
                    f"Option {item['id']}.{opt_key} must have 2 or 3 attributes, got {len(attrs)}"
                )

    return items


def _other_option(target):
    if target == "P":
        return "Q"
    if target == "Q":
        return "P"
    raise ValueError(f"Invalid target option: {target}")


def manipulation_line(item, cell):
    """Return the cell-specific manipulation sentence, or None for neutral."""
    if cell not in CELLS:
        raise ValueError(f"Unknown cell: {cell}")
    if cell == "neutral":
        return None
    target = item["target"]
    other = _other_option(target)
    option_x = target if cell.endswith("_T") else other
    name = item["name"]
    if cell.startswith("status_"):
        return STATUS_TEMPLATE.format(name=name, X=option_x)
    if cell.startswith("default_"):
        return DEFAULT_TEMPLATE.format(name=name, X=option_x)
    if cell.startswith("advisor_"):
        return ADVISOR_TEMPLATE.format(name=name, X=option_x)
    raise ValueError(f"Unhandled cell: {cell}")


def render(item, cell, ask):
    """Render the full Experiment E prompt according to PLAN 5b.4."""
    if cell not in CELLS:
        raise ValueError(f"Unknown cell: {cell}")
    if ask not in ASKS:
        raise ValueError(f"Unknown ask: {ask}")
    target = item["target"]
    _other_option(target)
    name = item["name"]
    context = (item.get("context") or "").strip()

    first_para = f"{name} needs to choose between two options."
    if context:
        first_para = f"{first_para} {context}"

    options_block = f"Option P: {item['option_P']}\nOption Q: {item['option_Q']}"
    manip = manipulation_line(item, cell)
    ask_block = ASKS[ask].format(T=target, name=name)

    blocks = [first_para, options_block]
    if manip is not None:
        blocks.append(manip)
    blocks.extend([SHARED_LINE, ask_block, NO_TOOLS])
    return "\n\n".join(blocks)


def units(items, split=None, repeat_ids=None):
    """Return [(item_id, cell, ask, round_id), ...] for the selected split.

    `split` may be None (all items) or a collection of item IDs.
    `repeat_ids` may be None/empty or a collection of item IDs that also get an "r1" round.
    """
    selected_ids = None if split is None else set(split)
    repeat_set = set() if repeat_ids is None else set(repeat_ids)
    result = []
    for item in items:
        item_id = item["id"] if isinstance(item, dict) else str(item)
        if selected_ids is not None and item_id not in selected_ids:
            continue
        rounds = ("r0", "r1") if item_id in repeat_set else ("r0",)
        for round_id in rounds:
            for cell in CELLS:
                for ask in ASKS:
                    result.append((item_id, cell, ask, round_id))
    return result
