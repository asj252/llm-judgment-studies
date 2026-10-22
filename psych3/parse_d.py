"""D parsing: S calls ../dnli/parse.py v2; J fails as a whole cell.

Values and estimates are keyed by a/b/conj/disj, in percentage points.
J multi retains raw and normalized common weights. Each weight must be
finite and in [0, 1], matching S; a positive total is normalized.
"""
import math
import re

from prompts_d import STATEMENTS, _load_dnli, validate_order

_dnli = _load_dnli("parse")
parse_direct, parse_multi = _dnli.parse_direct, _dnli.parse_multi
_NUMBER = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
_DIRECT = re.compile(r"Statement\s+(\d+)\s*:\s*(" + _NUMBER + r")\s*%", re.I)
_EST_LOOSE = _dnli._EST_LOOSE
_MULTI = re.compile(r"Estimate\s+(\d+)\s*:\s*"
                    + r"\s*\|\s*".join(r"S" + str(k) + r"\s+(" + _NUMBER + r")\s*%" for k in range(1, 5))
                    + r"\s*\|\s*Weight\s*:\s*(" + _NUMBER + r")", re.I)


def _fail(error):
    return {"ok": False, "error": error, "values": dict.fromkeys(STATEMENTS),
            "estimates": None, "weights": None, "normalized_weights": None, "weight_sum": None}


def _final(text):
    final, error = _dnli.strip_thinking(text)
    return ([line.strip() for line in final.splitlines() if line.strip()] if not error else [], error)


def parse_joint_direct(text, order):
    validate_order(order)
    lines, error = _final(text)
    if error:
        return _fail(error)
    rows = [_DIRECT.fullmatch(line) for line in lines[-4:]]
    if len(rows) != 4 or any(row is None for row in rows):
        return _fail("missing_or_malformed_statement")
    if {int(row[1]) for row in rows} != set(range(1, 5)):
        return _fail("bad_or_duplicate_index")
    numbered = {int(row[1]): float(row[2]) for row in rows}
    if any(not math.isfinite(v) or not 0 <= v <= 100 for v in numbered.values()):
        return _fail("out_of_range")
    return {"ok": True, "error": None, "values": {s: numbered[k] for k, s in enumerate(order, 1)},
            "estimates": None, "weights": None, "normalized_weights": None, "weight_sum": None}


def parse_joint_multi(text, order):
    validate_order(order)
    lines, error = _final(text)
    if error:
        return _fail(error)
    starts = [i for i, line in enumerate(lines)
              if any(int(m.group("k")) == 1 for m in _EST_LOOSE.finditer(line))]
    group = [line for line in lines[starts[-1] if starts else 0:] if _EST_LOOSE.search(line)]
    rows = [_MULTI.fullmatch(line) for line in group]
    if len(rows) != 5 or any(row is None for row in rows):
        return _fail("missing_or_malformed_estimate")
    if {int(row[1]) for row in rows} != set(range(1, 6)):
        return _fail("bad_or_duplicate_index")
    rows.sort(key=lambda row: int(row[1]))
    candidates = [{s: float(row[k + 1]) for k, s in enumerate(order, 1)} for row in rows]
    weights = [float(row[6]) for row in rows]
    if any(not math.isfinite(v) or not 0 <= v <= 100 for c in candidates for v in c.values()):
        return _fail("out_of_range")
    if any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
        return _fail("invalid_weight")
    total = sum(weights)
    if not math.isfinite(total) or total <= 0:
        return _fail("weight_sum_not_positive_or_finite")
    normalized = [w / total for w in weights]
    values = {s: sum(w * c[s] for w, c in zip(normalized, candidates)) for s in STATEMENTS}
    return {"ok": True, "error": None, "values": values,
            "estimates": {s: [c[s] for c in candidates] for s in STATEMENTS},
            "weights": weights, "normalized_weights": normalized, "weight_sum": total}


def parse_response(text, pres, ask, order=None):
    """S returns the unchanged delta-NLI result; J returns a whole-cell result."""
    if pres not in ("S", "J") or ask not in ("direct", "multi"):
        raise ValueError("Unknown presentation/ask")
    if pres == "S":
        return {"direct": parse_direct, "multi": parse_multi}[ask](text)
    return {"direct": parse_joint_direct, "multi": parse_joint_multi}[ask](text, order)
