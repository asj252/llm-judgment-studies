"""Experiment A: verbatim PLAN 2.5 templates and mechanical quantity metadata."""
import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

NO_TOOLS = "Do not use any tools; answer directly."
ASK_DIRECT = (
    "On the last line of your answer, give the answer strictly in the following format:\n"
    "Estimate: N\n"
    "where N is a single positive number (decimals or scientific notation such as 1.2e6 allowed) "
    "in the unit the question asks for, without commas or ranges."
)
ASK_MULTI = (
    "Give 5 estimates, each with a weight for how likely you think that estimate is; the weights sum to 1.\n\n"
    "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
    + "".join(f"Estimate {k}: N | Weight: W\n" for k in range(1, 6))
    + "where each N is a single positive number (decimals or scientific notation allowed) in the unit "
    "the question asks for, without commas or ranges, and each W is a number from 0 to 1 "
    "(decimals allowed); the five weights sum to 1."
)
ASKS = {"direct": ASK_DIRECT, "multi": ASK_MULTI}
CONDITIONS = (("none", None), ("irrelevant", "low"), ("irrelevant", "high"),
              ("informative", "low"), ("informative", "high"))


def load_questions(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("raw_data") / "synanchors/Qsemantic.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 60:
        raise ValueError("Expected 60 semantic questions")
    for row in data:
        if not all(k in row for k in ("question", "true_value", "requirement", "topic")):
            raise ValueError("Missing semantic field")
    return data


def mechanical_check(row):
    """Conservative literal checks, never an eligibility decision. No source anchor used."""
    text = row["question"] + " " + row["requirement"]
    unit = None
    # Parentheses elsewhere in a question may describe a meal rather than a unit.
    for m in re.finditer(r"\(\s*(?:in\s+)?([^()]*)\)", row["question"], re.I):
        candidate = m.group(1).strip()
        if re.fullmatch(r"(?:(?:million|billion|trillion|thousand|square|cubic|metric)\s+)*"
                        r"(?:USD|US dollars|dollars|yuan|tons|kilometers|meters|liters|gallons|miles|bales|km|%|terawatt-hours)"
                        r"(?:\s+per\s+night)?", candidate, re.I):
            unit = candidate
    if unit is None:
        m = re.search(r"\b(?:in |many )?((?:(?:million|billion|trillion|thousand|square|cubic|metric) )*"
                      r"(?:minutes|kilometers|miles|gallons|USD|US dollars|pieces))\b", text, re.I)
        if m:
            unit = m.group(1)
        elif re.search(r'how many (?:distinct )?fjords\b', text, re.I):
            unit = 'fjords'
    value = row["true_value"]
    valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    years = re.findall(r"\b(?:19|20)\d{2}\b", row["question"])
    relative = re.findall(r"\b(?:current|annually|annual|daily|each year|per month|each month|per night)\b", row["question"], re.I)
    return {"finite_positive": valid, "unit": unit, "unit_parsed": unit is not None,
            "years": years, "has_year_or_timepoint": bool(years), "relative_time_mentions": relative}


VALID_SELFWRITTEN_STATUS = ("verified", "verified_after_rewrite")


def anchors(index, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("True value must be finite and positive")
    d = Decimal(str(value))
    if not d.is_finite() or d <= 0:
        raise ValueError("True value must be finite and positive")
    if d >= 1000:
        rule = "3 significant digits (each anchor); ROUND_HALF_UP"
        def rounded(x):
            return x.quantize(Decimal(1).scaleb(x.adjusted() - 2), rounding=ROUND_HALF_UP)
    else:
        quantum = Decimal(1) if d == d.to_integral_value() else Decimal(1).scaleb(d.as_tuple().exponent)
        rule = f"quantum={quantum}; ROUND_HALF_UP"
        def rounded(x):
            return x.quantize(quantum, rounding=ROUND_HALF_UP)
    low, high = rounded(d / Decimal("1.5")), rounded(d * Decimal("1.5"))
    if not 0 < low < high:
        raise ValueError("Rounding does not yield positive ordered anchors")
    def number(x):
        return int(x) if x == x.to_integral_value() else float(x)
    return {"index": index, "true_value": value, "low": number(low), "high": number(high), "rounding_rule": rule}


def validate_selfwritten(data):
    if not isinstance(data, list) or len(data) != 24:
        raise ValueError("Expected 24 self-written questions")
    seen_ids = set()
    for row in data:
        if not isinstance(row, dict):
            raise ValueError("Each self-written item must be a dict")
        item_id = row.get("id")
        if (not isinstance(item_id, str) or item_id != item_id.strip()
                or not item_id.startswith("S") or len(item_id) < 2):
            raise ValueError(f"Invalid self-written item id: {item_id!r}")
        if item_id in seen_ids:
            raise ValueError(f"Duplicate self-written item id: {item_id}")
        seen_ids.add(item_id)
        question = row.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Missing or empty question for {item_id}")
        value = row.get("true_value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid true_value for {item_id}: {value!r}")
        anchors(item_id, value)
        unit = row.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f"Missing or empty unit for {item_id}")
        status = row.get("status")
        if status not in VALID_SELFWRITTEN_STATUS:
            raise ValueError(f"Invalid status for {item_id}: {status!r}")
    return data


def load_selfwritten(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("a_selfwritten_items.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_selfwritten(data)


def render(question, condition, ask, anchor=None):
    if ask not in ASKS or condition not in {c for c, _ in CONDITIONS}:
        raise ValueError("Unknown condition or ask")
    if (condition == "none") != (anchor is None):
        raise ValueError("Anchor required exactly for anchored conditions")
    frame = f"Here is a question: {question}"
    if condition == "none":
        parts = [frame, "Give your best estimate."]
    else:
        x = str(anchor)
        source = (f"A random number generator just produced the number {x}. The generator does not use the question "
                  "or its answer in any way; the number has nothing to do with the question below.") if condition == "irrelevant" else (
                  f"A reliable reference source gives a value of about {x} for the question below.")
        comparison = f"First, say whether the answer is higher than, lower than, or equal to {x}. Then give your own best estimate"
        parts = [source, frame, comparison + (", taking this information into account." if condition == "informative" else ".")]
    return "\n\n".join(parts + [ASKS[ask], NO_TOOLS])
