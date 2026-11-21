#!/usr/bin/env python3
"""Canonical Multi-Candidate Verbalization (MCV) Prompt & Parser Standard Library.

Single source of truth for all MCV experiments in `anonymous/research` (`connecting-dots/`,
`vs-llm-psych/`). Consolidates the frozen, battle-tested templates and v2 parsers from:
  - Single-item readout (`K=1`): `connecting-dots/dnli/prompts.py` & `dnli/parse.py` (v2)
  - Joint multi-item readout (`K>=2`): `connecting-dots/psych3/prompts_d.py` & `psych3/parse_d.py`
  - CoT-augmented variants (`D_CoT`, `M_CoT`): `dnli-api/ablation_vs_format.py` & `imperfective/exp1-en/prompts.py`
  - Unicode Zs whitespace normalization: `dnli-api/run_api.py`

DO NOT invent ad-hoc JSON or custom MCV formats in new subprojects. Always import
prompts and parsers from this module.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

PARSE_VERSION = 2
N_ESTIMATES = 5
WSUM_LO, WSUM_HI = 0.95, 1.05
ENDPOINT_LO, ENDPOINT_HI = 5.0, 95.0
NO_TOOLS = "Do not use any tools; answer directly."

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"

# ============================================================================
# 1. Canonical Prompt Templates (K = 1 Single Statement)
# ============================================================================

ASK_DIRECT = (
    "What is the probability that the statement is true?\n\n"
    "On the last line of your answer, give the answer strictly in the following format:\n"
    "Probability: NN%\n"
    "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
)

ASK_MULTI = (
    "Give 5 probability estimates that the statement is true, each with a weight for how likely you think "
    "that estimate is; the weights sum to 1.\n\n"
    "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
    + "".join(f"Estimate {k}: NN% | Weight: W\n" for k in range(1, N_ESTIMATES + 1))
    + "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a "
    "number from 0 to 1 (decimals allowed); the five weights sum to 1."
)

DEFAULT_COT_SINGLE = (
    "First, think step by step (in 1 to 3 brief sentences) about the situation, any new information, "
    "and alternative possibilities. Then give your answer."
)


def render_single_ask(ask: str, cot_instruction: Optional[str] = None) -> str:
    """Return the canonical single-statement tail ('direct', 'direct_cot', 'multi', 'multi_cot')."""
    if ask == "direct":
        return ASK_DIRECT
    if ask == "direct_cot":
        cot = cot_instruction or DEFAULT_COT_SINGLE
        return f"{cot}\n\n{ASK_DIRECT}"
    if ask == "multi":
        return ASK_MULTI
    if ask == "multi_cot":
        cot = cot_instruction or DEFAULT_COT_SINGLE
        return f"{cot}\n\n{ASK_MULTI}"
    raise ValueError(f"Unknown single ask mode: {ask!r}")


# ============================================================================
# 2. Canonical Prompt Templates (K >= 2 Joint Statements / Partition Options)
# ============================================================================

DEFAULT_COT_JOINT_ELIMINATION = (
    "First, state in one brief sentence which options remain valid and which option (if any) "
    "has been ruled out, while preserving the relative preference ratio between the remaining valid options."
)


def render_joint_direct(
    k: int = 4,
    *,
    item_noun: str = "statement",
    line_label: str = "Statement",
    partition_sum_100: bool = False,
    cot_instruction: Optional[str] = None,
) -> str:
    """Render the canonical JOINT_DIRECT tail (generalized from `psych3/prompts_d.py` for any K >= 2).

    When `k=4, item_noun='statement', line_label='Statement', partition_sum_100=False, cot_instruction=None`,
    this produces the byte-for-byte identical string to `psych3/prompts_d.py::JOINT_DIRECT`.
    """
    if k < 2:
        raise ValueError("k must be >= 2 for joint prompts")
    num_words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    k_word = num_words.get(k, str(k))
    sum_clause = " (the probabilities across all options must sum to 100%)" if partition_sum_100 else ""
    lead = f"Give a probability for each {item_noun}{sum_clause}."
    if cot_instruction:
        lead = f"{cot_instruction}\n\n{lead}"
    body = (
        f"On the last {k_word} lines of your answer, give the answers strictly in the following format, one per line:\n"
        + "".join(f"{line_label} {i}: NN%\n" for i in range(1, k + 1))
        + "where each NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
    )
    return f"{lead}\n\n{body}"


def render_joint_multi(
    k: int = 4,
    *,
    item_noun: str = "statements",
    short_prefix: str = "S",
    partition_sum_100: bool = False,
    cot_instruction: Optional[str] = None,
    n_estimates: int = N_ESTIMATES,
) -> str:
    """Render the canonical JOINT_MULTI tail (generalized from `psych3/prompts_d.py` for any K >= 2).

    When `k=4, item_noun='statements', short_prefix='S', partition_sum_100=False, cot_instruction=None`,
    this produces the byte-for-byte identical string to `psych3/prompts_d.py::JOINT_MULTI`.
    """
    if k < 2:
        raise ValueError("k must be >= 2 for joint prompts")
    num_words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    k_word = num_words.get(k, str(k))
    sum_clause = " (summing to 100% within each estimate)" if partition_sum_100 else ""
    lead = (
        f"Give {n_estimates} estimates, each estimate being a set of probabilities for all {k_word} "
        f"{item_noun}{sum_clause}, and give each estimate a weight for how likely you think that estimate is; "
        f"the weights sum to 1."
    )
    if cot_instruction:
        lead = f"{cot_instruction}\n\n{lead}"
    row_template = " | ".join(f"{short_prefix}{i} NN%" for i in range(1, k + 1))
    body = (
        f"At the end of your answer, give the {n_estimates} estimates strictly in the following format, one per line:\n"
        + "".join(f"Estimate {e}: {row_template} | Weight: W\n" for e in range(1, n_estimates + 1))
        + "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a "
        "number from 0 to 1 (decimals allowed); the five weights sum to 1."
    )
    return f"{lead}\n\n{body}"


# Exact byte-identical constants for K=4 (psych3 Experiment D) and K=3 (consistency 3-option partition)
JOINT_DIRECT_4 = render_joint_direct(4)
JOINT_MULTI_4 = render_joint_multi(4)

JOINT_DIRECT_3_PARTITION = render_joint_direct(
    3, item_noun="option", line_label="Statement", partition_sum_100=True
)
JOINT_DIRECT_3_PARTITION_COT = render_joint_direct(
    3,
    item_noun="option",
    line_label="Statement",
    partition_sum_100=True,
    cot_instruction=DEFAULT_COT_JOINT_ELIMINATION,
)
JOINT_MULTI_3_PARTITION = render_joint_multi(
    3, item_noun="options", short_prefix="S", partition_sum_100=True
)
JOINT_MULTI_3_PARTITION_COT = render_joint_multi(
    3,
    item_noun="options",
    short_prefix="S",
    partition_sum_100=True,
    cot_instruction=DEFAULT_COT_JOINT_ELIMINATION,
)


# ============================================================================
# 3. Canonical v2 Parsers (Single & Joint, with M_W, M_U, Top-1, and Spread)
# ============================================================================

_FIELD = re.compile(r"(?P<pre>[*_]*)(?P<key>probability)(?P<post>[*_]*)[ \t]*(?P<colon>[:：])", re.IGNORECASE)
_VALUE = re.compile(r"[ \t*_]*(?P<num>[-+]?\d+(?:\.\d+)?)(?P<sp> ?)%")
_BAD_NUM = re.compile(r"[ \t*_]*[-+]?(?:\d*\.\d*|\d+)(?:[eE][-+]?\d+)?[ \t]?%")
_DIGIT_OR_PCT = re.compile(r"[\d%]")
_EST_FIELD = re.compile(r"[*_]*(?<![A-Za-z])estimate[*_]*[ \t]*(?P<k>\d+)[*_]*[ \t]*[:：]", re.IGNORECASE)
_EST_LOOSE = re.compile(r"[*_]*(?<![A-Za-z])estimate[*_]*[ \t]*(?P<k>\d+)", re.IGNORECASE)
_W_FIELD = re.compile(r"[*_]*(?<![A-Za-z])weight[*_]*[ \t]*[:：]", re.IGNORECASE)
_W_VALUE = re.compile(r"[ \t*_]*(?P<num>[-+]?(?:\d+(?:\.\d+)?|\.\d+))")
_W_BAD = re.compile(r"[ \t*_]*[-+]?(?:\d*\.\d*|\d+)(?:[eE][-+]?\d+|/\d+)?")
_NUMBER = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"


def normalize_unicode_spaces(text: str) -> str:
    """Normalize Unicode category Zs spaces (e.g., U+202F, U+00A0) to ASCII space."""
    return "".join(" " if unicodedata.category(ch) == "Zs" else ch for ch in text)


def is_endpoint(v: float) -> bool:
    return v <= ENDPOINT_LO or v >= ENDPOINT_HI


def strip_thinking(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Strip `<think>...</think>` blocks; fail closed on unterminated `<think>`."""
    if text is None:
        return None, "no_text"
    text = normalize_unicode_spaces(text)
    if THINK_CLOSE in text:
        return text.rsplit(THINK_CLOSE, 1)[1], None
    if THINK_OPEN in text:
        return None, "thinking_unterminated"
    return text, None


def _value_after(s: str):
    forms = set()
    m = _VALUE.match(s)
    if not m:
        if _BAD_NUM.match(s):
            return None, forms, "malformed"
        stripped = s.strip(" \t*_")
        if re.match(r"[-+]?(\d+(\.\d*)?|\.\d+)", stripped):
            return None, forms, "no_percent"
        return None, forms, "no_number"
    if m.group("sp"):
        forms.add("space_before_percent")
    if "*" in s[: m.start("num")] or "_" in s[: m.start("num")]:
        forms.add("bold")
    after = s[m.end() :]
    if _DIGIT_OR_PCT.search(after):
        return None, forms, "range_or_extra_number"
    if after.strip(" \t*_.,;:)。，；"):
        forms.add("trailing_text")
    v = float(m.group("num"))
    if not math.isfinite(v):
        return None, forms, "non_finite"
    if not (0.0 <= v <= 100.0):
        return None, forms, "out_of_range"
    return v, forms, None


def _weight_after(s: str):
    m = _W_VALUE.match(s)
    bad = _W_BAD.match(s)
    if not m:
        if bad and re.search(r"\d", bad.group(0)):
            return None, "weight_malformed"
        return None, "weight_no_number"
    after = s[m.end() :]
    if after[:1] in (".", "e", "E", "/") and re.match(r"[./eE]\S*\d", after):
        return None, "weight_malformed"
    if after.lstrip(" \t").startswith("%"):
        return None, "weight_percent"
    if _DIGIT_OR_PCT.search(after):
        return None, "weight_extra_number"
    w = float(m.group("num"))
    if not math.isfinite(w):
        return None, "weight_malformed"
    if not (0.0 <= w <= 1.0):
        return None, "weight_out_of_range"
    return w, None


def parse_direct(text: Optional[str]) -> dict:
    """Canonical v2 single-statement `Probability: NN%` parser (`dnli/parse.py`)."""
    final, err = strip_thinking(text)
    if err:
        return {"ok": False, "value": None, "error": err, "forms": []}
    fields = list(_FIELD.finditer(final))
    if not fields:
        return {"ok": False, "value": None, "error": "no_field", "forms": []}
    f = fields[-1]
    forms = set()
    if f.group("pre") or f.group("post"):
        forms.add("bold")
    if f.group("colon") == "：":
        forms.add("fullwidth_colon")
    if f.group("key") != "Probability":
        forms.add("lowercase_key" if f.group("key") == "probability" else "other_case_key")
    line_rest = final[f.end() :].split("\n", 1)[0]
    v, vf, err = _value_after(line_rest)
    forms |= vf
    if err:
        return {"ok": False, "value": None, "error": err, "forms": sorted(forms)}
    return {"ok": True, "value": v, "error": None, "forms": sorted(forms) or ["plain"]}


def _multi_fail(err: str, forms=()) -> dict:
    return {
        "ok": False,
        "value": None,
        "m_w": None,
        "m_u": None,
        "top1": None,
        "error": err,
        "estimates": None,
        "weights": None,
        "normalized_weights": None,
        "weight_sum": None,
        "weight_sum_in_tolerance": None,
        "endpoint_mass": None,
        "weighted_sd": None,
        "unweighted_sd": None,
        "forms": sorted(forms),
    }


def parse_multi(text: Optional[str]) -> dict:
    """Canonical v2 single-statement 5-estimate parser (`dnli/parse.py`), enriched with `m_w`, `m_u`, `top1`."""
    final, err = strip_thinking(text)
    if err:
        return _multi_fail(err)
    all_lines = final.splitlines()
    starts = [
        i
        for i, line in enumerate(all_lines)
        if any(int(f.group("k")) == 1 for f in _EST_LOOSE.finditer(line))
    ]
    lines = [line for line in all_lines[starts[-1] if starts else 0 :] if _EST_LOOSE.search(line)]
    if len(lines) != N_ESTIMATES:
        return _multi_fail(f"n_estimates_{len(lines)}")
    idx = [int(f.group("k")) for line in lines for f in _EST_LOOSE.finditer(line)]
    if len(idx) != len(lines):
        return _multi_fail("multiple_estimate_fields_in_line")
    if len(set(idx)) != len(idx):
        return _multi_fail("duplicate_index")
    if set(idx) != set(range(1, N_ESTIMATES + 1)):
        return _multi_fail("bad_index")
    rows, forms = [], set()
    for line in lines:
        fields = list(_EST_FIELD.finditer(line))
        if len(fields) != 1:
            return _multi_fail("malformed_estimate_field")
        f = fields[0]
        rest = line[f.end() :]
        wf = list(_W_FIELD.finditer(rest))
        if len(wf) != 1:
            return _multi_fail("missing_weight" if not wf else "multiple_weights")
        v, vf, err = _value_after(rest[: wf[0].start()].rstrip(" \t|,;(["))
        if err:
            return _multi_fail("estimate_" + err)
        w, err = _weight_after(rest[wf[0].end() :])
        if err:
            return _multi_fail(err)
        forms |= vf - {"trailing_text"}
        if "*" in f.group(0) or "_" in f.group(0):
            forms.add("bold")
        if "：" in f.group(0):
            forms.add("fullwidth_colon")
        rows.append((int(f.group("k")), v, w))
    ws = sum(w for _, _, w in rows)
    if not math.isfinite(ws) or ws <= 0.0:
        return _multi_fail(f"weight_sum_not_positive:{ws:.4f}", forms)
    rows.sort()
    ps = [v for _, v, _ in rows]
    raw_w = [w for _, _, w in rows]
    wn = [w / ws for w in raw_w]
    m_w = sum(w * p for w, p in zip(wn, ps))
    m_u = sum(ps) / len(ps)
    best_idx = max(range(len(ps)), key=lambda i: (raw_w[i], -i))
    top1 = ps[best_idx]
    w_sd = math.sqrt(max(0.0, sum(w * (p - m_w) ** 2 for w, p in zip(wn, ps))))
    u_sd = math.sqrt(max(0.0, sum((p - m_u) ** 2 for p in ps) / len(ps)))
    return {
        "ok": True,
        "value": m_w,
        "m_w": m_w,
        "m_u": m_u,
        "top1": top1,
        "error": None,
        "estimates": ps,
        "weights": raw_w,
        "normalized_weights": wn,
        "weight_sum": ws,
        "weight_sum_in_tolerance": WSUM_LO <= ws <= WSUM_HI,
        "endpoint_mass": sum(w for w, p in zip(wn, ps) if is_endpoint(p)),
        "weighted_sd": w_sd,
        "unweighted_sd": u_sd,
        "forms": sorted(forms) or ["plain"],
    }


def _joint_fail(error: str, keys: Sequence[str]) -> dict:
    return {
        "ok": False,
        "error": error,
        "values": dict.fromkeys(keys),
        "m_w": dict.fromkeys(keys),
        "m_u": dict.fromkeys(keys),
        "top1": dict.fromkeys(keys),
        "m_w_row_norm": dict.fromkeys(keys),
        "estimates": None,
        "weights": None,
        "normalized_weights": None,
        "weight_sum": None,
        "weight_sum_in_tolerance": None,
        "row_sums": None,
        "row_sums_in_tolerance": None,
        "has_all_zero_candidate": None,
        "n_distinct_estimates": None,
        "weighted_sd": dict.fromkeys(keys),
        "unweighted_sd": dict.fromkeys(keys),
        "mean_weighted_sd": None,
        "mean_unweighted_sd": None,
    }


def _clean_line_markdown(line: str) -> str:
    """Strip optional leading list markers (`- `, `* `) and bold/italic markers (`*`, `_`)."""
    s = line.strip()
    s = re.sub(r"^[-*•]\s+", "", s)
    return s.replace("*", "").replace("_", "").strip()


def parse_joint_direct(
    text: Optional[str],
    order: Sequence[str],
    *,
    line_label: str = "Statement",
) -> dict:
    """Canonical joint direct parser for `K = len(order)` statements/options (`psych3/parse_d.py`)."""
    k = len(order)
    if k < 2 or len(set(order)) != k:
        raise ValueError("order must contain >= 2 distinct keys")
    final, error = strip_thinking(text)
    if error:
        return _joint_fail(error, order)
    lines = [_clean_line_markdown(line) for line in final.splitlines() if line.strip()]
    pat = re.compile(rf"{re.escape(line_label)}\s+(\d+)\s*[:：]\s*({_NUMBER})\s*%", re.IGNORECASE)
    rows = [pat.fullmatch(line) for line in lines[-k:]]
    if len(rows) != k or any(row is None for row in rows):
        return _joint_fail("missing_or_malformed_statement", order)
    if {int(row[1]) for row in rows} != set(range(1, k + 1)):
        return _joint_fail("bad_or_duplicate_index", order)
    numbered = {int(row[1]): float(row[2]) for row in rows}
    if any(not math.isfinite(v) or not 0.0 <= v <= 100.0 for v in numbered.values()):
        return _joint_fail("out_of_range", order)
    vals = {s: numbered[i] for i, s in enumerate(order, 1)}
    rsum = sum(vals.values())
    row_in_tol = abs(rsum - 100.0) <= 1.0
    zero_sd = {s: 0.0 for s in order}
    return {
        "ok": True,
        "error": None,
        "values": vals,
        "m_w": dict(vals),
        "m_u": dict(vals),
        "top1": dict(vals),
        "m_w_row_norm": {s: (100.0 * vals[s] / rsum if rsum > 1e-12 else 0.0) for s in order},
        "estimates": None,
        "weights": None,
        "normalized_weights": None,
        "weight_sum": None,
        "weight_sum_in_tolerance": True,
        "row_sums": [rsum],
        "row_sums_in_tolerance": row_in_tol,
        "has_all_zero_candidate": rsum <= 1e-12,
        "n_distinct_estimates": 1,
        "weighted_sd": zero_sd,
        "unweighted_sd": zero_sd,
        "mean_weighted_sd": 0.0,
        "mean_unweighted_sd": 0.0,
    }


def parse_joint_multi(
    text: Optional[str],
    order: Sequence[str],
    *,
    short_prefix: str = "S",
    n_estimates: int = N_ESTIMATES,
) -> dict:
    """Canonical joint 5-estimate MCV parser for `K = len(order)` statements/options (`psych3/parse_d.py`).

    Returns weighted mean (`values` / `m_w`), uniform mean (`m_u`), highest-weight candidate (`top1`),
    row-normalized weighted mean (`m_w_row_norm`), spread (`weighted_sd`, `unweighted_sd`),
    and per-item candidate vectors (`estimates`).
    """
    k = len(order)
    if k < 2 or len(set(order)) != k:
        raise ValueError("order must contain >= 2 distinct keys")
    final, error = strip_thinking(text)
    if error:
        return _joint_fail(error, order)
    lines = [_clean_line_markdown(line) for line in final.splitlines() if line.strip()]
    starts = [
        i
        for i, line in enumerate(lines)
        if any(int(m.group("k")) == 1 for m in _EST_LOOSE.finditer(line))
    ]
    group = [line for line in lines[starts[-1] if starts else 0 :] if _EST_LOOSE.search(line)]
    multi_pat = re.compile(
        r"Estimate\s+(\d+)\s*[:：]\s*"
        + r"\s*\|\s*".join(
            rf"{re.escape(short_prefix)}{i}\s*[:：]?\s*({_NUMBER})\s*%" for i in range(1, k + 1)
        )
        + rf"\s*\|\s*Weight\s*[:：]\s*({_NUMBER})",
        re.IGNORECASE,
    )
    rows = [multi_pat.fullmatch(line) for line in group]
    if len(rows) != n_estimates or any(row is None for row in rows):
        return _joint_fail("missing_or_malformed_estimate", order)
    if {int(row[1]) for row in rows} != set(range(1, n_estimates + 1)):
        return _joint_fail("bad_or_duplicate_index", order)
    rows.sort(key=lambda row: int(row[1]))
    candidates = [{s: float(row[i + 1]) for i, s in enumerate(order, 1)} for row in rows]
    weights = [float(row[k + 2]) for row in rows]
    if any(not math.isfinite(v) or not 0.0 <= v <= 100.0 for c in candidates for v in c.values()):
        return _joint_fail("out_of_range", order)
    if any(not math.isfinite(w) or not 0.0 <= w <= 1.0 for w in weights):
        return _joint_fail("invalid_weight", order)
    total = sum(weights)
    if not math.isfinite(total) or total <= 0.0:
        return _joint_fail("weight_sum_not_positive_or_finite", order)
    normalized = [w / total for w in weights]
    m_w = {s: sum(w * c[s] for w, c in zip(normalized, candidates)) for s in order}
    m_u = {s: sum(c[s] for c in candidates) / n_estimates for s in order}
    best_idx = max(range(n_estimates), key=lambda i: (weights[i], -i))
    top1 = dict(candidates[best_idx])

    w_sd = {
        s: round(math.sqrt(max(0.0, sum(w * (c[s] - m_w[s]) ** 2 for w, c in zip(normalized, candidates)))), 6)
        for s in order
    }
    u_sd = {
        s: round(math.sqrt(max(0.0, sum((c[s] - m_u[s]) ** 2 for c in candidates) / n_estimates)), 6)
        for s in order
    }
    mean_w_sd = round(sum(w_sd.values()) / k, 6)
    mean_u_sd = round(sum(u_sd.values()) / k, 6)

    row_sums = [round(sum(c[s] for s in order), 6) for c in candidates]
    row_sums_in_tol = all(abs(rs - 100.0) <= 1.0 for rs in row_sums)
    has_all_zero = any(rs <= 1e-12 for rs in row_sums)
    n_distinct = len({tuple(round(c[s], 6) for s in order) for c in candidates})

    # Pre-aggregation row-normalized M_W sensitivity readout:
    # Normalize each positive-sum candidate row to sum to 100% first, and zero out all-zero rows.
    pos_indices = [i for i, rs in enumerate(row_sums) if rs > 1e-12]
    if pos_indices:
        pos_w_sum = sum(weights[i] for i in pos_indices)
        if pos_w_sum > 1e-12:
            pos_wn = {i: weights[i] / pos_w_sum for i in pos_indices}
        else:
            pos_wn = {i: 1.0 / len(pos_indices) for i in pos_indices}
        m_w_row_norm = {
            s: sum(pos_wn[i] * (100.0 * candidates[i][s] / row_sums[i]) for i in pos_indices)
            for s in order
        }
    else:
        m_w_row_norm = {s: 0.0 for s in order}

    return {
        "ok": True,
        "error": None,
        "values": m_w,
        "m_w": m_w,
        "m_u": m_u,
        "top1": top1,
        "m_w_row_norm": m_w_row_norm,
        "estimates": {s: [c[s] for c in candidates] for s in order},
        "weights": weights,
        "normalized_weights": normalized,
        "weight_sum": total,
        "weight_sum_in_tolerance": WSUM_LO <= total <= WSUM_HI,
        "row_sums": row_sums,
        "row_sums_in_tolerance": row_sums_in_tol,
        "has_all_zero_candidate": has_all_zero,
        "n_distinct_estimates": n_distinct,
        "weighted_sd": w_sd,
        "unweighted_sd": u_sd,
        "mean_weighted_sd": mean_w_sd,
        "mean_unweighted_sd": mean_u_sd,
    }


def _selftest() -> None:
    # 1. Verify exact byte-compatibility with dnli/prompts.py and psych3/prompts_d.py
    from pathlib import Path
    import importlib.util

    here = Path(__file__).resolve().parent
    dnli_spec = importlib.util.spec_from_file_location("_dnli_prompts", here / "dnli" / "prompts.py")
    dnli_mod = importlib.util.module_from_spec(dnli_spec)
    dnli_spec.loader.exec_module(dnli_mod)
    assert ASK_DIRECT == dnli_mod.ASK_DIRECT, "ASK_DIRECT mismatch with dnli/prompts.py"
    assert ASK_MULTI == dnli_mod.ASK_MULTI, "ASK_MULTI mismatch with dnli/prompts.py"

    psych3_spec = importlib.util.spec_from_file_location("_psych3_prompts_d", here / "psych3" / "prompts_d.py")
    psych3_mod = importlib.util.module_from_spec(psych3_spec)
    psych3_spec.loader.exec_module(psych3_mod)
    assert JOINT_DIRECT_4 == psych3_mod.JOINT_DIRECT, "JOINT_DIRECT_4 mismatch with psych3/prompts_d.py"
    assert JOINT_MULTI_4 == psych3_mod.JOINT_MULTI, "JOINT_MULTI_4 mismatch with psych3/prompts_d.py"

    # 2. Verify K=3 Joint Direct & Joint Multi parsing
    order3 = ("Lion", "Tiger", "Leopard")
    sample_jd = (
        "Both Lion and Tiger remain valid while Leopard is ruled out.\n"
        "Statement 1: 60%\n"
        "Statement 2: 40%\n"
        "Statement 3: 0%\n"
    )
    res_jd = parse_joint_direct(sample_jd, order3)
    assert res_jd["ok"] and res_jd["values"] == {"Lion": 60.0, "Tiger": 40.0, "Leopard": 0.0}
    assert res_jd["row_sums_in_tolerance"] is True

    sample_jm = (
        "<think>Leopard is eliminated.</think>\n"
        "Lion and Tiger remain valid; Leopard is ruled out.\n"
        "Estimate 1: S1 60% | S2 40% | S3 0% | Weight: 0.5\n"
        "Estimate 2: S1 50% | S2 50% | S3 0% | Weight: 0.2\n"
        "Estimate 3: S1 70% | S2 30% | S3 0% | Weight: 0.1\n"
        "Estimate 4: S1 55% | S2 45% | S3 0% | Weight: 0.1\n"
        "Estimate 5: S1 65% | S2 35% | S3 0% | Weight: 0.1\n"
    )
    res_jm = parse_joint_multi(sample_jm, order3)
    assert res_jm["ok"], f"parse_joint_multi failed: {res_jm}"
    assert abs(res_jm["m_w"]["Lion"] - 59.0) < 1e-6
    assert abs(res_jm["m_u"]["Lion"] - 60.0) < 1e-6
    assert res_jm["top1"]["Lion"] == 60.0
    assert res_jm["m_w"]["Leopard"] == 0.0
    assert res_jm["weighted_sd"]["Lion"] > 0.0 and res_jm["unweighted_sd"]["Lion"] > 0.0
    assert res_jm["row_sums_in_tolerance"] is True and res_jm["n_distinct_estimates"] == 5
    print("[SELFTEST PASS] mcv_standard.py verified byte-for-byte against dnli & psych3 and K=3 joint parsers.")


if __name__ == "__main__":
    _selftest()
