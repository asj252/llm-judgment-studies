"""Positive quantity parsing, with delta-NLI v2 last-field/last-group selection."""
import math
import re

NUMBER = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
FIELD = re.compile(r"(?<![A-Za-z])estimate[*_]*\s*[:：]", re.I)
LOOSE = re.compile(r"(?<![A-Za-z])estimate[*_]*[ \t]*(?P<k>\d+)", re.I)
ROW = re.compile(r"(?<![A-Za-z])estimate[*_]*[ \t]*(?P<k>\d+)[*_]*[ \t]*[:：]", re.I)
WEIGHT = re.compile(r"(?<![A-Za-z])weight[*_]*[ \t]*[:：]", re.I)


def _final(text):
    if text is None:
        return None, "no_text"
    if "</think>" in text:
        return text.rsplit("</think>", 1)[1], None
    if "<think>" in text:
        return None, "thinking_unterminated"
    return text, None


def _quantity(text, unit):
    text = text.strip(" \t*_")
    m = re.match(NUMBER, text)
    if not m:
        return None, "no_number"
    suffix = text[m.end():].strip()
    # A suffix is allowed only when it exactly matches the frozen question unit.
    if suffix and (unit is None or suffix.casefold() != unit.strip().casefold()):
        return None, "invalid_suffix_or_range"
    value = float(m.group())
    if not math.isfinite(value) or value <= 0:
        return None, "not_finite_positive"
    return value, None


def _fail(error):
    return {"ok": False, "value": None, "error": error}


def parse_direct(text, unit=None):
    final, err = _final(text)
    if err:
        return _fail(err)
    fields = list(FIELD.finditer(final))
    if not fields:
        return _fail("no_field")
    value, err = _quantity(final[fields[-1].end():].split("\n", 1)[0], unit)
    return _fail(err) if err else {"ok": True, "value": value, "error": None}


def parse_multi(text, unit=None):
    final, err = _final(text)
    if err:
        return _fail(err)
    lines = final.splitlines()
    starts = [i for i, line in enumerate(lines) if any(int(m['k']) == 1 for m in LOOSE.finditer(line))]
    lines = [line for line in lines[starts[-1] if starts else 0:] if LOOSE.search(line)]
    if len(lines) != 5:
        return _fail(f"n_estimates_{len(lines)}")
    rows = []
    for line in lines:
        loose, fields, weights = list(LOOSE.finditer(line)), list(ROW.finditer(line)), list(WEIGHT.finditer(line))
        if len(loose) != 1 or len(fields) != 1 or len(weights) != 1:
            return _fail("malformed_fields")
        f, w = fields[0], weights[0]
        if w.start() < f.end():
            return _fail("malformed_fields")
        left = line[f.end():w.start()].strip()
        if left.endswith("|"):
            left = left[:-1].rstrip()
        value, err = _quantity(left, unit)
        if err:
            return _fail("estimate_" + err)
        weight_text = line[w.end():].strip(" \t*_")
        if not re.fullmatch(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)", weight_text):
            return _fail("weight_malformed")
        weight = float(weight_text)
        if not math.isfinite(weight) or not 0 <= weight <= 1:
            return _fail("weight_out_of_range")
        rows.append((int(f['k']), value, weight))
    if {k for k, _, _ in rows} != set(range(1, 6)):
        return _fail("bad_or_duplicate_index")
    rows.sort()
    total = sum(w for _, _, w in rows)
    if total <= 0:
        return _fail("weight_sum_not_positive")
    # Normalize before multiplication to avoid overflowing w * estimate sums.
    value = sum((w / total) * v for _, v, w in rows)
    if not math.isfinite(value) or value <= 0:
        return _fail("aggregate_not_finite_positive")
    return {"ok": True, "value": value, "error": None,
            "estimates": [v for _, v, _ in rows], "weights": [w for _, _, w in rows],
            "weight_sum": total, "weight_sum_in_tolerance": 0.95 <= total <= 1.05}


PARSERS = {"direct": parse_direct, "multi": parse_multi}
