"""Strict format checks, separate from permissive semantic parsing."""
import math
import re
from decimal import Decimal

VERSION = 1
DIRECT = re.compile(r"Probability: \d+(\.\d+)?%")
MULTI = r"Estimate %d: (\d+(?:\.\d+)?)%% \| Weight: (0(?:\.\d+)?|1(?:\.0+)?|\.\d+)"


def check(text, task, prompt, parsed):
    reasons = []
    lines = [s.strip() for s in (text or "").splitlines() if s.strip()]
    if task in ("P", "Ps"):
        if not lines or not DIRECT.fullmatch(lines[-1]):
            reasons.append("last_line")
        elif not 0 <= Decimal(lines[-1][13:-1]) <= 100:
            reasons.append("last_line")
    elif task == "M":
        matches = [re.fullmatch(MULTI % k, line) for k, line in enumerate(lines[-5:], 1)]
        if len(matches) != 5 or not all(matches):
            reasons.append("estimate_lines")
        else:
            if any(not math.isfinite(float(m[1])) or not 0 <= Decimal(m[1]) <= 100 for m in matches):
                reasons.append("estimate_range")
            if not Decimal("0.95") <= sum(Decimal(m[2]) for m in matches) <= Decimal("1.05"):
                reasons.append("weight_sum")
    elif task == "L" and prompt in ("Z", "DAP"):
        label = parsed["label"]
        if not label or (text or "").strip() not in (label, '"' + label + '"'):
            reasons.append(parsed["form"] if parsed["form"] != "exact" else "label_form")
    elif task == "L":
        if parsed["fenced"]:
            reasons.append("fenced")
        if parsed["error"]:
            reasons.append(parsed["error"])
        else:
            if not parsed["label_form"]:
                reasons.append("label_form")
            if not parsed["reasoning_ok"]:
                reasons.append("no_reasoning")
            if not parsed["label_last"]:
                reasons.append("label_first")
            if parsed["extra_keys"]:
                reasons.append("extra_keys")
            if prompt == "CF" and parsed["n_interruptions"] != 3:
                reasons.append("n_interruptions")
    else:
        raise ValueError(task)
    return {"protocol_ok": not reasons, "reasons": reasons}
