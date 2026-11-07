"""Locked Statistical Engine for Experiment 4 (English Moorean Paradox) (`exp4-moore/PLAN-E4.md` §4).

Implements the two candidate confirmatory families evaluated in Stage S4 calibration
and bound into Stage S5 `freeze.json` / Stage S7 formal analysis on all `n = 80` formal
clusters (`n = 20` on dev, with 4-domain fixed quota: 20 per domain formal, 5 per domain dev):
1. Candidate 1 (`hybrid_pct_tango_e4`):
   - Continuous paired contrasts `E4_H1`, `E4_H2`, `E4_H3`: Cluster-level equal-weight
     multinomial bootstrap (`B = 5000`) on a single shared PCG64 stream (`seed = 2026110601`
     for formal, `seed = 2026110602` for dev), using uninterpolated order-statistic 98.75% CIs
     (`idx_lo = 31, idx_hi = 4968`, 0-based) and 95% companion CIs (`idx_lo = 124, idx_hi = 4875`),
     plus one-sided p-values `(1 + #{theta* <= 0}) / (B + 1)` when point_lower > 0 else `1.0`.
   - Discrete paired proportion contrast `E4_H4` (`DUAL_EXPLICIT` vs `DUAL_MOORE` True rate on `L/CoT`):
     Certified exact unconditional Tango (1998) score test and 98.75% CI via `exact_tango_e4`.
2. Candidate 2 / Companion (`hybrid_bessel_t_tango_e4`):
   - Same exact Tango test/CI for `E4_H4`, and order-preserving Bessel-t center-expanded
     bootstrap CIs (`c_80 = 1.0298684039340296`, `c_20 = 1.1331397732007173`,
     `c_5 = 1.9313454535930072`) for `E4_H1..E4_H3`.

Enforces all 4 pre-clipping degeneracy rules (`PLAN-E4.md` §4.2(2)), worst-case bounds for
`status != "ok"` (`PLAN-E4.md` §4.2(4)), Holm step-down (`m = 4, alpha_fam = 0.05`) with
fixed tie-break order `E4_H1..E4_H4`, mandatory parallel 4-domain breakdown (`D1_safety`,
`D2_project`, `D3_medical`, `D4_institutional`), and Layer 3 descriptive and reasoning mechanism tables.
"""
from __future__ import annotations

from decimal import Decimal, getcontext
import math
import re
from typing import Any

import numpy as np

import exact_tango_e4
from prompts_e4 import COMBINATIONS

FORMAL_ANALYSIS_SEED_E4 = 2026110601
DEV_ANALYSIS_SEED_E4 = 2026110602
B_DEFAULT = 5000
ALPHA_FAMILY = 0.05
ALPHA_IND = 0.0125  # 0.05 / 4

E4_SLOT_ORDER: tuple[str, ...] = ("E4_H1", "E4_H2", "E4_H3", "E4_H4")
CONTINUOUS_SLOTS: tuple[str, ...] = ("E4_H1", "E4_H2", "E4_H3")
DISCRETE_SLOTS: tuple[str, ...] = ("E4_H4",)
MAIN_SLOTS: tuple[str, ...] = ("PURE_MOORE", "DUAL_MOORE", "DUAL_EXPLICIT", "PURE_READ")
DOMAIN_SUBCLASSES: tuple[str, ...] = ("D1_safety", "D2_project", "D3_medical", "D4_institutional")

MIN_DISTINCT_DRAWS = 20
TOL_DUST = 1e-12


def _compute_bessel_t_factors_high_precision(
    ns: tuple[int, ...] = (5, 20, 80),
) -> dict[int, float]:
    """Compute c_n = sqrt(n/(n-1)) * t_{n-1, 0.99375} / z_{0.99375} in 80-digit Decimal arithmetic.

    Uses exact beta function identities for integer and half-integer arguments and 400 continued
    fraction iterations in regularized incomplete beta function, achieving 0 ULP error.
    """
    getcontext().prec = 100
    pi_d = Decimal("3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628034825342117067982148086513282306647093844609550582231725359408128")

    def dec_exp(x: Decimal) -> Decimal:
        return x.exp()

    def dec_ln(x: Decimal) -> Decimal:
        return x.ln()

    def dec_sqrt(x: Decimal) -> Decimal:
        return x.sqrt()

    def exact_beta_half(df_int: int) -> Decimal:
        if df_int % 2 == 0:
            k = df_int // 2
            num = Decimal(1)
            for j in range(1, k):
                num *= Decimal(j)
            den = Decimal(1)
            for j in range(1, k + 1):
                den *= (Decimal(j) - Decimal("0.5"))
            return num / den
        else:
            k = df_int // 2
            prod = Decimal(1)
            for j in range(1, k + 1):
                prod *= (Decimal(j) - Decimal("0.5"))
            fact = Decimal(1)
            for j in range(1, k + 1):
                fact *= Decimal(j)
            return (prod / fact) * pi_d

    def erf_dec(x: Decimal) -> Decimal:
        s = Decimal(0)
        x2 = x * x
        term = x
        for n in range(350):
            if n > 0:
                term = -term * x2 / Decimal(n)
            contrib = term / Decimal(2 * n + 1)
            s += contrib
            if abs(contrib) < Decimal("1e-90"):
                break
        return s * Decimal(2) / dec_sqrt(pi_d)

    def norm_cdf_dec(z: Decimal) -> Decimal:
        return Decimal("0.5") * (Decimal(1) + erf_dec(z / dec_sqrt(Decimal(2))))

    def betainc_reg_dec(df_int: int, x: Decimal) -> Decimal:
        a = Decimal(df_int) / Decimal(2)
        b = Decimal("0.5")
        beta_val = exact_beta_half(df_int)
        front = (dec_exp(a * dec_ln(x) + b * dec_ln(Decimal(1) - x)) / beta_val) / a
        d = Decimal(1) - (a + b) * x / (a + Decimal(1))
        if abs(d) < Decimal("1e-90"):
            d = Decimal("1e-90")
        d = Decimal(1) / d
        c = Decimal(1)
        h = d
        for m in range(1, 400):
            m_d = Decimal(m)
            num1 = m_d * (b - m_d) * x / ((a + Decimal(2) * m_d - Decimal(1)) * (a + Decimal(2) * m_d))
            d = Decimal(1) + num1 * d
            if abs(d) < Decimal("1e-90"):
                d = Decimal("1e-90")
            c = Decimal(1) + num1 / c
            if abs(c) < Decimal("1e-90"):
                c = Decimal("1e-90")
            d = Decimal(1) / d
            h *= d * c
            num2 = -(a + m_d) * (a + b + m_d) * x / ((a + Decimal(2) * m_d) * (a + Decimal(2) * m_d + Decimal(1)))
            d = Decimal(1) + num2 * d
            if abs(d) < Decimal("1e-90"):
                d = Decimal("1e-90")
            c = Decimal(1) + num2 / c
            if abs(c) < Decimal("1e-90"):
                c = Decimal("1e-90")
            d = Decimal(1) / d
            delta = d * c
            h *= delta
            if abs(delta - Decimal(1)) < Decimal("1e-85"):
                break
        return front * h

    def t_cdf_pos(t_val: Decimal, df_int: int) -> Decimal:
        df_d = Decimal(df_int)
        x = df_d / (df_d + t_val * t_val)
        ib = betainc_reg_dec(df_int, x)
        return Decimal(1) - Decimal("0.5") * ib

    target = Decimal("0.99375")  # 1 - 0.0125 / 2
    lo, hi = Decimal("2.4"), Decimal("2.6")
    for _ in range(300):
        mid = (lo + hi) / Decimal(2)
        if norm_cdf_dec(mid) < target:
            lo = mid
        else:
            hi = mid
    z_q = (lo + hi) / Decimal(2)

    out: dict[int, float] = {}
    for n in ns:
        df = n - 1
        lo_t, hi_t = Decimal("2.0"), Decimal("6.0")
        for _ in range(300):
            mid_t = (lo_t + hi_t) / Decimal(2)
            if t_cdf_pos(mid_t, df) < target:
                lo_t = mid_t
            else:
                hi_t = mid_t
        t_q = (lo_t + hi_t) / Decimal(2)
        c_n = dec_sqrt(Decimal(n) / Decimal(n - 1)) * (t_q / z_q)
        out[n] = float(c_n)
    return out


EXPECTED_BESSEL_T_FACTORS: dict[int, float] = {
    80: 1.0298684039340296,
    20: 1.1331397732007173,
    5: 1.9313454535930072,
}

BESSEL_T_FACTORS_BY_N: dict[int, float] = _compute_bessel_t_factors_high_precision()
for _n_k, _exp_c in EXPECTED_BESSEL_T_FACTORS.items():
    if abs(BESSEL_T_FACTORS_BY_N[_n_k] - _exp_c) > 1e-15:
        raise RuntimeError(
            f"Bessel-t factor mismatch for n={_n_k}: {BESSEL_T_FACTORS_BY_N[_n_k]} != {_exp_c}"
        )


def _order_stat_indices(b: int, alpha_two_sided: float) -> tuple[int, int]:
    """Uninterpolated 0-based order-statistic indices (PLAN-E4.md §4.2(2)).

    For B=5000:
      - alpha_two_sided = 0.0125 (98.75% CI): idx_lo = 31, idx_hi = 4968
      - alpha_two_sided = 0.05   (95.00% CI): idx_lo = 124, idx_hi = 4875
    """
    half_alpha = 0.5 * float(alpha_two_sided)
    k_one_based = max(1, int(math.ceil(b * half_alpha)))
    idx_lo = k_one_based - 1
    idx_hi = b - k_one_based
    if not (0 <= idx_lo <= idx_hi < b):
        raise ValueError(f"Invalid order-statistic indices ({idx_lo}, {idx_hi}) for B={b}, alpha={alpha_two_sided}")
    return idx_lo, idx_hi


def _greedy_distinct_1d_sorted(sorted_arr: np.ndarray, tol: float = TOL_DUST) -> int:
    """Count distinct values in a 1D sorted array using greedy anchor scan (`tol = 1e-12`)."""
    if sorted_arr.size == 0 or not np.all(np.isfinite(sorted_arr)):
        return 0
    cnt = 1
    anchor = float(sorted_arr[0])
    for x in sorted_arr[1:]:
        xf = float(x)
        if xf - anchor > tol:
            cnt += 1
            anchor = xf
    return cnt


def draw_cluster_bootstrap_weights_e4(
    n: int,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E4,
) -> np.ndarray:
    """Draw equal-weight multinomial cluster bootstrap weight matrix `w` (`(B, n)`) on a single PCG64 stream."""
    rng = np.random.Generator(np.random.PCG64(seed))
    return rng.multinomial(n, np.full(n, 1.0 / n), size=b).astype(np.float64) / float(n)


def draw_all_bootstrap_weights_e4(
    n_all: int,
    domain_counts: dict[str, int],
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E4,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Draw `w_all` and domain weights sequentially on a single shared PCG64 stream (`PLAN-E4.md` §4.2(1))."""
    rng = np.random.Generator(np.random.PCG64(seed))
    w_all = rng.multinomial(n_all, np.full(n_all, 1.0 / n_all), size=b).astype(np.float64) / float(n_all)
    w_dom: dict[str, np.ndarray] = {}
    for dom in DOMAIN_SUBCLASSES:
        n_sub = int(domain_counts.get(dom, 0))
        if n_sub > 0:
            w_dom[dom] = rng.multinomial(n_sub, np.full(n_sub, 1.0 / n_sub), size=b).astype(np.float64) / float(n_sub)
        else:
            w_dom[dom] = np.zeros((b, 0), dtype=np.float64)
    return w_all, w_dom


def infer_continuous_slot_e4(
    d_lower: np.ndarray,
    d_upper: np.ndarray,
    w_mat: np.ndarray,
    method: str = "pct",
    domain_bounds: tuple[float, float] = (-100.0, 100.0),
) -> dict[str, Any]:
    """Evaluate one-sided (`H0: theta <= 0` vs `H1: theta > 0`) continuous paired contrast (`E4_H1..E4_H3`).

    Enforces all 4 pre-clipping degeneracy rules from `PLAN-E4.md` §4.2(2):
      1. `u_low < 20 or u_high < 20` (`insufficient_distinct_draws`)
      2. `|s_low[idx_hi] - s_low[idx_lo]| <= 1e-12` or `|s_high[idx_hi] - s_high[idx_lo]| <= 1e-12` (`zero_quantile_span`)
      3. Non-finite or inverted raw CI endpoints `raw_ci_lo > raw_ci_hi` (`invalid_or_inverted_ci`)
      4. For `bessel_t`, unclipped `[raw_ci_lo, raw_ci_hi]` has empty intersection with `domain_bounds` (`out_of_domain_unclipped_ci`)
    Any triggered degeneracy forces `p = 1.0`, `ci_9875 = [-100.0, 100.0]`, `ci_95 = [-100.0, 100.0]`.
    """
    if method not in ("pct", "bessel_t"):
        raise ValueError(f"Unsupported continuous inference method: {method!r}")
    d_lo = np.asarray(d_lower, dtype=np.float64)
    d_hi = np.asarray(d_upper, dtype=np.float64)
    n = int(d_lo.size)
    b = int(w_mat.shape[0])
    dom_lo, dom_hi = float(domain_bounds[0]), float(domain_bounds[1])

    if n == 0 or d_hi.size != n or w_mat.shape[1] != n:
        return {
            "method": method,
            "n": n,
            "point_lower": float("nan"),
            "point_upper": float("nan"),
            "p": 1.0,
            "ci_9875": [dom_lo, dom_hi],
            "ci_95": [dom_lo, dom_hi],
            "u_low": 0,
            "u_high": 0,
            "degenerate": True,
            "degeneracy_reasons": ["empty_or_mismatched_sample"],
        }

    pt_lo = float(np.mean(d_lo))
    pt_hi = float(np.mean(d_hi))

    boot_lo_raw = w_mat @ d_lo
    boot_hi_raw = w_mat @ d_hi

    if method == "bessel_t":
        if n not in BESSEL_T_FACTORS_BY_N:
            raise ValueError(f"Unsupported sample size n={n} for Bessel-t factor")
        c_n = BESSEL_T_FACTORS_BY_N[n]
        boot_lo = np.minimum(boot_lo_raw, pt_lo + c_n * (boot_lo_raw - pt_lo))
        boot_hi = np.maximum(boot_hi_raw, pt_hi + c_n * (boot_hi_raw - pt_hi))
    else:
        c_n = 1.0
        boot_lo = boot_lo_raw
        boot_hi = boot_hi_raw

    s_low = np.sort(boot_lo)
    s_high = np.sort(boot_hi)

    u_low = _greedy_distinct_1d_sorted(s_low, TOL_DUST)
    u_high = _greedy_distinct_1d_sorted(s_high, TOL_DUST)

    idx_lo_9875, idx_hi_9875 = _order_stat_indices(b, ALPHA_IND)
    idx_lo_95, idx_hi_95 = _order_stat_indices(b, ALPHA_FAMILY)

    raw_lo_9875 = float(s_low[idx_lo_9875])
    raw_hi_9875 = float(s_high[idx_hi_9875])
    raw_lo_95 = float(s_low[idx_lo_95])
    raw_hi_95 = float(s_high[idx_hi_95])

    span_low_9875 = abs(float(s_low[idx_hi_9875]) - float(s_low[idx_lo_9875]))
    span_high_9875 = abs(float(s_high[idx_hi_9875]) - float(s_high[idx_lo_9875]))

    reasons: list[str] = []
    if u_low < MIN_DISTINCT_DRAWS or u_high < MIN_DISTINCT_DRAWS:
        reasons.append("insufficient_distinct_draws")
    if (
        not math.isfinite(span_low_9875)
        or not math.isfinite(span_high_9875)
        or span_low_9875 <= TOL_DUST
        or span_high_9875 <= TOL_DUST
    ):
        reasons.append("zero_quantile_span")
    if (
        not math.isfinite(pt_lo)
        or not math.isfinite(pt_hi)
        or not math.isfinite(raw_lo_9875)
        or not math.isfinite(raw_hi_9875)
        or not math.isfinite(raw_lo_95)
        or not math.isfinite(raw_hi_95)
        or raw_lo_9875 > raw_hi_9875
        or raw_lo_95 > raw_hi_95
    ):
        reasons.append("invalid_or_inverted_ci")
    if method == "bessel_t":
        if math.isfinite(raw_lo_9875) and math.isfinite(raw_hi_9875):
            if raw_hi_9875 < dom_lo or raw_lo_9875 > dom_hi:
                reasons.append("out_of_domain_unclipped_ci")
        if math.isfinite(raw_lo_95) and math.isfinite(raw_hi_95):
            if raw_hi_95 < dom_lo or raw_lo_95 > dom_hi:
                if "out_of_domain_unclipped_ci" not in reasons:
                    reasons.append("out_of_domain_unclipped_ci")

    if reasons:
        return {
            "method": method,
            "c_n": c_n,
            "n": n,
            "point_lower": pt_lo,
            "point_upper": pt_hi,
            "p": 1.0,
            "ci_9875": [dom_lo, dom_hi],
            "ci_95": [dom_lo, dom_hi],
            "raw_ci_9875": [raw_lo_9875, raw_hi_9875],
            "raw_ci_95": [raw_lo_95, raw_hi_95],
            "u_low": u_low,
            "u_high": u_high,
            "span_low_9875": span_low_9875,
            "span_high_9875": span_high_9875,
            "degenerate": True,
            "degeneracy_reasons": reasons,
        }

    if method == "bessel_t":
        ci_9875 = [max(dom_lo, raw_lo_9875), min(dom_hi, raw_hi_9875)]
        ci_95 = [max(dom_lo, raw_lo_95), min(dom_hi, raw_hi_95)]
    else:
        ci_9875 = [raw_lo_9875, raw_hi_9875]
        ci_95 = [raw_lo_95, raw_hi_95]

    if pt_lo <= 0.0:
        p_val = 1.0
    else:
        non_pos = int(np.sum(boot_lo <= 0.0))
        p_val = float((1 + non_pos) / (b + 1))

    return {
        "method": method,
        "c_n": c_n,
        "n": n,
        "point_lower": pt_lo,
        "point_upper": pt_hi,
        "p": p_val,
        "ci_9875": ci_9875,
        "ci_95": ci_95,
        "raw_ci_9875": [raw_lo_9875, raw_hi_9875],
        "raw_ci_95": [raw_lo_95, raw_hi_95],
        "u_low": u_low,
        "u_high": u_high,
        "span_low_9875": span_low_9875,
        "span_high_9875": span_high_9875,
        "degenerate": False,
        "degeneracy_reasons": [],
    }


def infer_discrete_slot_e4(
    d_lower: np.ndarray,
    d_upper: np.ndarray,
    one_sided: bool = True,
) -> dict[str, Any]:
    """Evaluate `E4_H4` (`Pr(True on DUAL_EXPLICIT; L/CoT) - Pr(True on DUAL_MOORE; L/CoT)`) via certified exact Tango."""
    res = exact_tango_e4.infer_exact_tango_slot(
        np.asarray(d_lower, dtype=np.int64),
        np.asarray(d_upper, dtype=np.int64),
        one_sided=one_sided,
    )
    return {
        **res,
        "method": "exact_tango_1998",
        "n": int(res["n"]),
        "point_lower": float(res["point_lower"]),
        "point_upper": float(res["point_upper"]),
        "point_lower_pct": 100.0 * float(res["point_lower"]),
        "point_upper_pct": 100.0 * float(res["point_upper"]),
        "p": float(res["p"]),
        "ci_9875": [float(res["ci_9875"][0]), float(res["ci_9875"][1])],
        "ci_95": [float(res["ci_95"][0]), float(res["ci_95"][1])],
        "ci_9875_pct": [100.0 * float(res["ci_9875"][0]), 100.0 * float(res["ci_9875"][1])],
        "ci_95_pct": [100.0 * float(res["ci_95"][0]), 100.0 * float(res["ci_95"][1])],
        "low_counts": res["counts_lower"],
        "high_counts": res["counts_upper"],
        "degenerate": bool(res["degenerate_9875"]),
        "degeneracy_reasons": ["tango_ci_covers_full_domain"] if res["degenerate_9875"] else [],
    }


def holm_step_down_e4(
    p_values: dict[str, float],
    alpha_family: float = ALPHA_FAMILY,
    slot_order: tuple[str, ...] = E4_SLOT_ORDER,
) -> dict[str, dict[str, Any]]:
    """Holm step-down (`m = 4, alpha_fam = 0.05`) with deterministic tie-breaking by `E4_H1..E4_H4`."""
    m = len(slot_order)
    order_idx = {slot: i for i, slot in enumerate(slot_order)}
    sorted_slots = sorted(
        slot_order,
        key=lambda s: (float(p_values.get(s, 1.0)), order_idx[s]),
    )
    out: dict[str, dict[str, Any]] = {}
    still_rejecting = True
    running_adj = 0.0
    for step_idx, slot in enumerate(sorted_slots):
        denom = m - step_idx
        thresh = alpha_family / float(denom)
        raw_p = float(p_values.get(slot, 1.0))
        running_adj = max(running_adj, min(1.0, raw_p * float(denom)))
        if still_rejecting and raw_p <= thresh:
            rejected = True
        else:
            still_rejecting = False
            rejected = False
        out[slot] = {
            "step": step_idx + 1,
            "raw_p": raw_p,
            "threshold": thresh,
            "p_holm": running_adj,
            "rejected": rejected,
        }
    return out


def evaluate_four_slot_family_e4(
    inputs: dict[str, tuple[np.ndarray, np.ndarray]],
    w_all: np.ndarray,
    continuous_method: str = "pct",
    demoted_slots: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Run all 4 confirmatory slots (`E4_H1..E4_H4`) and Holm step-down (`m = 4`).

    If any continuous slot is in `demoted_slots`, it is demoted from confirmatory
    to descriptive while keeping `m = 4` denominator (`alpha_ind = 0.0125`, Holm
    denominators 4, 3, 2, 1 with demoted slot fixed at `p = 1.0`).
    """
    demoted_set = set(demoted_slots)
    slots_out: dict[str, dict[str, Any]] = {}
    for slot in CONTINUOUS_SLOTS:
        d_lo, d_hi = inputs[slot]
        res = infer_continuous_slot_e4(d_lo, d_hi, w_all, method=continuous_method)
        if slot in demoted_set:
            res["descriptive_ci_9875"] = list(res["ci_9875"])
            res["descriptive_ci_95"] = list(res["ci_95"])
            res["descriptive_p"] = float(res["p"])
            res["demoted_to_descriptive"] = True
            res["p"] = 1.0
            res["ci_9875"] = [-100.0, 100.0]
        else:
            res["demoted_to_descriptive"] = False
        slots_out[slot] = res

    d4_lo, d4_hi = inputs["E4_H4"]
    res_h4 = infer_discrete_slot_e4(d4_lo, d4_hi, one_sided=True)
    res_h4["demoted_to_descriptive"] = False
    slots_out["E4_H4"] = res_h4

    p_map = {s: slots_out[s]["p"] for s in E4_SLOT_ORDER}
    holm = holm_step_down_e4(p_map, alpha_family=ALPHA_FAMILY, slot_order=E4_SLOT_ORDER)
    for s in E4_SLOT_ORDER:
        slots_out[s]["holm"] = holm[s]

    return {
        "family_name": "hybrid_pct_tango_e4" if continuous_method == "pct" else "hybrid_bessel_t_tango_e4",
        "continuous_method": continuous_method,
        "demoted_slots": sorted(demoted_set),
        "slots": slots_out,
        "holm_summary": holm,
    }


def _lookup_record(
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]],
    by_uk: dict[str, dict[str, Any]],
    cid: str,
    slot: str,
    task: str,
    prompt: str,
) -> dict[str, Any] | None:
    rec = by_tuple.get((cid, slot, task, prompt))
    if rec is not None:
        return rec
    rec = by_uk.get(f"{cid}__{slot}/{task}/{prompt}")
    if rec is not None:
        return rec
    return by_uk.get(f"{slot}_{cid}/{task}/{prompt}")


def _extract_continuous_bounds(
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]],
    by_uk: dict[str, dict[str, Any]],
    cid: str,
    slot: str,
    task: str,
    prompt: str,
    use_unweighted_m: bool = False,
) -> tuple[float, float, bool]:
    """Return `(low, high, is_ok)` for a continuous probability unit (`P`, `Ps`, `M_W`, or `M_U`)."""
    rec = _lookup_record(by_tuple, by_uk, cid, slot, task, prompt)
    if rec is None or rec.get("status") != "ok":
        return 0.0, 100.0, False
    if use_unweighted_m:
        parsed = rec.get("parsed") or {}
        ests = parsed.get("estimates")
        if isinstance(ests, list) and len(ests) == 5:
            val = float(sum(float(x) for x in ests) / 5.0)
            return val, val, True
        return 0.0, 100.0, False
    val = rec.get("value")
    if val is None or not math.isfinite(float(val)):
        return 0.0, 100.0, False
    vf = float(val)
    return vf, vf, True


def _extract_label_true_bounds(
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]],
    by_uk: dict[str, dict[str, Any]],
    cid: str,
    slot: str,
    task: str,
    prompt: str,
    allow_missing_score: bool = False,
) -> tuple[int, int, bool]:
    """Return `(low_ind, high_ind, is_ok)` for `I(label == 'True')` on task `L`."""
    rec = _lookup_record(by_tuple, by_uk, cid, slot, task, prompt)
    if rec is None:
        return 0, 1, False
    allowed = ("ok", "missing_score") if allow_missing_score else ("ok",)
    if rec.get("status") not in allowed:
        return 0, 1, False
    lbl = rec.get("label")
    if lbl not in ("True", "False", "Unknown"):
        return 0, 1, False
    ind = 1 if lbl == "True" else 0
    return ind, ind, True


def extract_primary_inputs_from_records_e4(
    records: list[dict[str, Any]],
    cluster_ids: list[str],
    allow_missing_score_for_h4: bool = False,
) -> dict[str, Any]:
    """Extract worst-case bounded cluster difference vectors for `E4_H1..E4_H4` on a sorted cluster subset.

    Primary contrasts:
      - E4_H1: DUAL_MOORE(M_U/CF) - DUAL_MOORE(P/CoT)
      - E4_H2: DUAL_MOORE(M_U/Z) - PURE_MOORE(M_U/Z)
      - E4_H3: DUAL_EXPLICIT(P/Z) - DUAL_MOORE(P/Z)
      - E4_H4: I(DUAL_EXPLICIT == True; L/CoT) - I(DUAL_MOORE == True; L/CoT)
    """
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    by_uk: dict[str, dict[str, Any]] = {}
    for r in records:
        if "unit_key" in r:
            by_uk[r["unit_key"]] = r
        cid = r.get("cluster_id")
        slot = r.get("slot")
        task = r.get("task")
        prompt = r.get("prompt")
        if cid and slot and task and prompt:
            by_tuple[(cid, slot, task, prompt)] = r

    cids_sorted = sorted(cluster_ids)
    n = len(cids_sorted)

    h1_lo = np.zeros(n, dtype=np.float64)
    h1_hi = np.zeros(n, dtype=np.float64)
    h2_lo = np.zeros(n, dtype=np.float64)
    h2_hi = np.zeros(n, dtype=np.float64)
    h3_lo = np.zeros(n, dtype=np.float64)
    h3_hi = np.zeros(n, dtype=np.float64)
    h4_lo = np.zeros(n, dtype=np.int64)
    h4_hi = np.zeros(n, dtype=np.int64)

    complete_masks = {s: np.zeros(n, dtype=bool) for s in E4_SLOT_ORDER}
    missing_units = {s: 0 for s in E4_SLOT_ORDER}

    for i, cid in enumerate(cids_sorted):
        # E4_H1: DUAL_MOORE(M_U/CF) - DUAL_MOORE(P/CoT)
        m_cf_lo, m_cf_hi, ok_m_cf = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "DUAL_MOORE", "M", "CF", use_unweighted_m=True
        )
        p_cot_lo, p_cot_hi, ok_p_cot = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "DUAL_MOORE", "P", "CoT", use_unweighted_m=False
        )
        h1_lo[i] = m_cf_lo - p_cot_hi
        h1_hi[i] = m_cf_hi - p_cot_lo
        complete_masks["E4_H1"][i] = ok_m_cf and ok_p_cot
        missing_units["E4_H1"] += int(not ok_m_cf) + int(not ok_p_cot)

        # E4_H2: DUAL_MOORE(M_U/Z) - PURE_MOORE(M_U/Z)
        dual_mz_lo, dual_mz_hi, ok_dual_mz = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "DUAL_MOORE", "M", "Z", use_unweighted_m=True
        )
        pure_mz_lo, pure_mz_hi, ok_pure_mz = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "PURE_MOORE", "M", "Z", use_unweighted_m=True
        )
        h2_lo[i] = dual_mz_lo - pure_mz_hi
        h2_hi[i] = dual_mz_hi - pure_mz_lo
        complete_masks["E4_H2"][i] = ok_dual_mz and ok_pure_mz
        missing_units["E4_H2"] += int(not ok_dual_mz) + int(not ok_pure_mz)

        # E4_H3: DUAL_EXPLICIT(P/Z) - DUAL_MOORE(P/Z)
        exp_pz_lo, exp_pz_hi, ok_exp_pz = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "DUAL_EXPLICIT", "P", "Z", use_unweighted_m=False
        )
        dual_pz_lo, dual_pz_hi, ok_dual_pz = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "DUAL_MOORE", "P", "Z", use_unweighted_m=False
        )
        h3_lo[i] = exp_pz_lo - dual_pz_hi
        h3_hi[i] = exp_pz_hi - dual_pz_lo
        complete_masks["E4_H3"][i] = ok_exp_pz and ok_dual_pz
        missing_units["E4_H3"] += int(not ok_exp_pz) + int(not ok_dual_pz)

        # E4_H4: I(DUAL_EXPLICIT == True; L/CoT) - I(DUAL_MOORE == True; L/CoT)
        l_exp_lo, l_exp_hi, ok_l_exp = _extract_label_true_bounds(
            by_tuple, by_uk, cid, "DUAL_EXPLICIT", "L", "CoT", allow_missing_score=allow_missing_score_for_h4
        )
        l_dual_lo, l_dual_hi, ok_l_dual = _extract_label_true_bounds(
            by_tuple, by_uk, cid, "DUAL_MOORE", "L", "CoT", allow_missing_score=allow_missing_score_for_h4
        )
        h4_lo[i] = l_exp_lo - l_dual_hi
        h4_hi[i] = l_exp_hi - l_dual_lo
        complete_masks["E4_H4"][i] = ok_l_exp and ok_l_dual
        missing_units["E4_H4"] += int(not ok_l_exp) + int(not ok_l_dual)

    return {
        "cluster_ids": cids_sorted,
        "inputs": {
            "E4_H1": (h1_lo, h1_hi),
            "E4_H2": (h2_lo, h2_hi),
            "E4_H3": (h3_lo, h3_hi),
            "E4_H4": (h4_lo, h4_hi),
        },
        "complete_masks": complete_masks,
        "complete_cluster_counts": {s: int(np.sum(complete_masks[s])) for s in E4_SLOT_ORDER},
        "missing_units": missing_units,
    }


def _paired_summary_ci95(lo_vec: np.ndarray, hi_vec: np.ndarray, w_mat: np.ndarray | None) -> dict[str, Any]:
    if lo_vec.size == 0:
        return {"n": 0, "mean_lower": None, "mean_upper": None, "sd_lower": None, "ci_95": [None, None]}
    m_lo = float(np.mean(lo_vec))
    m_hi = float(np.mean(hi_vec))
    sd_lo = float(np.std(lo_vec, ddof=1)) if lo_vec.size > 1 else 0.0
    if w_mat is not None and w_mat.shape[1] == lo_vec.size:
        b = int(w_mat.shape[0])
        idx_lo_95, idx_hi_95 = _order_stat_indices(b, ALPHA_FAMILY)
        s_lo = np.sort(w_mat @ lo_vec)
        s_hi = np.sort(w_mat @ hi_vec)
        ci_95 = [float(s_lo[idx_lo_95]), float(s_hi[idx_hi_95])]
    else:
        ci_95 = [m_lo, m_hi]
    return {
        "n": int(lo_vec.size),
        "mean_lower": m_lo,
        "mean_upper": m_hi,
        "sd_lower": sd_lo,
        "ci_95": ci_95,
    }


def _summarize_condition_main_slots(
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]],
    by_uk: dict[str, dict[str, Any]],
    cids: list[str],
    task: str,
    prompt: str,
    w_mat: np.ndarray | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    slot_bounds: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for slot in MAIN_SLOTS:
        if task == "L":
            counts = {"True": 0, "False": 0, "Unknown": 0, "missing": 0}
            t_lo_list, t_hi_list = [], []
            for cid in cids:
                rec = _lookup_record(by_tuple, by_uk, cid, slot, task, prompt)
                if rec is None or rec.get("status") != "ok":
                    counts["missing"] += 1
                    t_lo_list.append(0.0)
                    t_hi_list.append(100.0)
                else:
                    lbl = rec.get("label")
                    if lbl in ("True", "False", "Unknown"):
                        counts[lbl] += 1
                        v = 100.0 if lbl == "True" else 0.0
                        t_lo_list.append(v)
                        t_hi_list.append(v)
                    else:
                        counts["missing"] += 1
                        t_lo_list.append(0.0)
                        t_hi_list.append(100.0)
            n = len(cids)
            lo_arr = np.array(t_lo_list, dtype=np.float64)
            hi_arr = np.array(t_hi_list, dtype=np.float64)
            slot_bounds[slot] = (lo_arr, hi_arr)
            s_ci = _paired_summary_ci95(lo_arr, hi_arr, w_mat)
            out[slot] = {
                "n": n,
                "counts": counts,
                "true_rate_lower": (counts["True"] / n) if n else 0.0,
                "true_rate_upper": ((counts["True"] + counts["missing"]) / n) if n else 1.0,
                "true_pct_ci_95": s_ci["ci_95"],
            }
        else:
            lo_vals, hi_vals, ok_vals = [], [], []
            lo_u, hi_u, ok_u = [], [], []
            for cid in cids:
                lo_v, hi_v, is_ok = _extract_continuous_bounds(
                    by_tuple, by_uk, cid, slot, task, prompt, use_unweighted_m=False
                )
                lo_vals.append(lo_v)
                hi_vals.append(hi_v)
                if is_ok:
                    ok_vals.append(lo_v)
                if task == "M":
                    u_lo, u_hi, u_ok = _extract_continuous_bounds(
                        by_tuple, by_uk, cid, slot, task, prompt, use_unweighted_m=True
                    )
                    lo_u.append(u_lo)
                    hi_u.append(u_hi)
                    if u_ok:
                        ok_u.append(u_lo)
            lo_arr = np.array(lo_vals, dtype=np.float64)
            hi_arr = np.array(hi_vals, dtype=np.float64)
            slot_bounds[slot] = (lo_arr, hi_arr)
            s_ci = _paired_summary_ci95(lo_arr, hi_arr, w_mat)
            entry: dict[str, Any] = {
                "n": len(cids),
                "ok": len(ok_vals),
                "mean_lower": s_ci["mean_lower"],
                "mean_upper": s_ci["mean_upper"],
                "ci_95": s_ci["ci_95"],
                "ok_mean": float(np.mean(ok_vals)) if ok_vals else None,
                "ok_sd": float(np.std(ok_vals, ddof=1)) if len(ok_vals) > 1 else 0.0,
            }
            if task == "M":
                lo_u_arr = np.array(lo_u, dtype=np.float64)
                hi_u_arr = np.array(hi_u, dtype=np.float64)
                u_ci = _paired_summary_ci95(lo_u_arr, hi_u_arr, w_mat)
                entry["mu_mean_lower"] = u_ci["mean_lower"]
                entry["mu_mean_upper"] = u_ci["mean_upper"]
                entry["mu_ci_95"] = u_ci["ci_95"]
                entry["mu_ok_mean"] = float(np.mean(ok_u)) if ok_u else None
                entry["mu_ok_sd"] = float(np.std(ok_u, ddof=1)) if len(ok_u) > 1 else 0.0
            out[slot] = entry

    if len(cids) > 0:
        pure_m_lo, pure_m_hi = slot_bounds["PURE_MOORE"]
        dual_m_lo, dual_m_hi = slot_bounds["DUAL_MOORE"]
        dual_e_lo, dual_e_hi = slot_bounds["DUAL_EXPLICIT"]
        pure_r_lo, pure_r_hi = slot_bounds["PURE_READ"]
        out["paired_contrasts"] = {
            "DUAL_MOORE_minus_PURE_MOORE": _paired_summary_ci95(dual_m_lo - pure_m_hi, dual_m_hi - pure_m_lo, w_mat),
            "DUAL_EXPLICIT_minus_DUAL_MOORE": _paired_summary_ci95(dual_e_lo - dual_m_hi, dual_e_hi - dual_m_lo, w_mat),
            "PURE_READ_minus_PURE_MOORE": _paired_summary_ci95(pure_r_lo - pure_m_hi, pure_r_hi - pure_m_lo, w_mat),
            "PURE_READ_minus_DUAL_MOORE": _paired_summary_ci95(pure_r_lo - dual_m_hi, pure_r_hi - dual_m_lo, w_mat),
        }
    return out


def _summarize_diagnostic_contexts(
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]],
    by_uk: dict[str, dict[str, Any]],
    by_cid: dict[str, dict[str, Any]],
    cids: list[str],
) -> dict[str, Any]:
    """Summarize diagnostic context performance (`DIAG_POS` vs `DIAG_NEG` on `L/Z`, `P/Z`, `M/Z`) overall and by `domain_subclass`."""
    def _eval_group(group_cids: list[str]) -> dict[str, Any]:
        pos_pz, neg_pz, per_cluster = [], [], []
        for cid in group_cids:
            r_pos_p = _lookup_record(by_tuple, by_uk, cid, "DIAG_POS", "P", "Z")
            r_neg_p = _lookup_record(by_tuple, by_uk, cid, "DIAG_NEG", "P", "Z")
            r_pos_l = _lookup_record(by_tuple, by_uk, cid, "DIAG_POS", "L", "Z")
            r_neg_l = _lookup_record(by_tuple, by_uk, cid, "DIAG_NEG", "L", "Z")
            r_pos_m = _lookup_record(by_tuple, by_uk, cid, "DIAG_POS", "M", "Z")
            r_neg_m = _lookup_record(by_tuple, by_uk, cid, "DIAG_NEG", "M", "Z")
            v_pos_p = float(r_pos_p["value"]) if r_pos_p and r_pos_p.get("status") == "ok" and r_pos_p.get("value") is not None else None
            v_neg_p = float(r_neg_p["value"]) if r_neg_p and r_neg_p.get("status") == "ok" and r_neg_p.get("value") is not None else None
            if v_pos_p is not None:
                pos_pz.append(v_pos_p)
            if v_neg_p is not None:
                neg_pz.append(v_neg_p)
            if any(x is not None for x in (r_pos_p, r_neg_p, r_pos_l, r_neg_l, r_pos_m, r_neg_m)):
                per_cluster.append({
                    "cluster_id": cid,
                    "domain_subclass": by_cid[cid]["domain_subclass"],
                    "DIAG_POS_P_Z": v_pos_p,
                    "DIAG_NEG_P_Z": v_neg_p,
                    "DIAG_POS_L_Z": r_pos_l.get("label") if r_pos_l else None,
                    "DIAG_NEG_L_Z": r_neg_l.get("label") if r_neg_l else None,
                    "DIAG_POS_M_W_Z": float(r_pos_m["value"]) if r_pos_m and r_pos_m.get("status") == "ok" and r_pos_m.get("value") is not None else None,
                    "DIAG_NEG_M_W_Z": float(r_neg_m["value"]) if r_neg_m and r_neg_m.get("status") == "ok" and r_neg_m.get("value") is not None else None,
                })
        return {
            "n_clusters": len(group_cids),
            "pos_pz_ok": len(pos_pz),
            "neg_pz_ok": len(neg_pz),
            "pos_mean_pz": float(np.mean(pos_pz)) if pos_pz else None,
            "neg_mean_pz": float(np.mean(neg_pz)) if neg_pz else None,
            "per_cluster": per_cluster,
        }

    return {
        "overall": _eval_group(cids),
        "by_domain_subclass": {
            dom: _eval_group([c for c in cids if by_cid[c]["domain_subclass"] == dom])
            for dom in DOMAIN_SUBCLASSES
        },
    }


# Layer 3 Reasoning Mechanism Classifier (Zheng et al. 2026 Table 4 & 5 benchmark alignment)
_RE_CLAUSE_SPLIT = re.compile(
    r"[.;!?\n]+|\b(?:but|however|yet|whereas|nevertheless|nonetheless|instead|because|since|so|therefore|thus|hence)\b",
    re.IGNORECASE,
)

_RE_CONCESSIVE_OR_TENTATIVE = re.compile(
    r"\b(?:although|though|even\s+though|despite|in\s+spite\s+of)\b|"
    r"\bwhile\s+(?:it\s+|this\s+|the\s+\w+\s+)?(?:may\b|might\b|can\b|could\b|resembles?\b|looks?\b|sounds?\b|appears?\b|seems?\b|superficially\b)|"
    r"\b(?:resembles?|looks?\s+like|sounds?\s+like|appears?\s+to\s+be|seems?\s+to\s+be|superficially|at\s+first\s+glance|on\s+the\s+surface)\b",
    re.IGNORECASE,
)

_RE_FUNCTIONAL_NEG_TOKEN = re.compile(
    r"\b(?:no|not|never|without|neither|none|nothing|hardly|scarcely|barely|"
    r"isn't|aren't|wasn't|weren't|doesn't|don't|didn't|won't|wouldn't|can't|cannot|couldn't|shouldn't)\b",
    re.IGNORECASE,
)

_RE_LEXICAL_META_NEG_TOKEN = re.compile(
    r"\bnothing\s+like\b|"
    r"\bnon-(?=contradict\w*|self-contradict\w*|paradox\w*|moorean|polysem\w*)|"
    r"\b(?:avoids?|avoided|avoiding|resolves?|resolved|resolving|eliminates?|eliminated|"
    r"dispel\w*|preclude\w*|exclude\w*|rule[sd]?\s+out|ruling\s+out|"
    r"reject\w*|deni\w*|deny\w*|refut\w*|rebut\w*|dismiss\w*|disput\w*|negat\w*|"
    r"lack\w*|absent|nonexistent|free\s+of|devoid\s+of|rather\s+than|instead\s+of|far\s+from|contrary\s+to|"
    r"fails?\b|failed\b|failure\b|"
    r"false|wrong\w*|incorrect\w*|mistaken\w*|untrue|invalid\w*|flawed|misleading|misguided|inaccurate|unfounded|untenable|"
    r"fallacious|implausible|unlikely|doubtful|dubious|inapplicable|irrelevant|disappears?|vanishes?|dissolved|"
    r"misconception|misreading|misinterpretation|misclassification|misdiagnosis|"
    r"monosemous|unambiguous)\b",
    re.IGNORECASE,
)

_RE_COMBINED_META_NEG_SPAN = re.compile(
    _RE_LEXICAL_META_NEG_TOKEN.pattern + r"|" + _RE_FUNCTIONAL_NEG_TOKEN.pattern,
    re.IGNORECASE,
)

_RE_COORD_CLAUSE_BOUNDARY = re.compile(
    r",\s*(?:and|or|while|whilst|then)\b|"
    r"\b(?:and|or|while|whilst)\b(?=\s+"
    r"(?:this|that|it|there|here|he|she|they|we|one|the\s+\w+|moore|polysem\w*)\s+"
    r"(?:is|are|was|were|isn't|aren't|wasn't|weren't|has|have|had|does|do|did|doesn't|don't|didn't|"
    r"can|cannot|can't|will|won't|would|wouldn't|should|shouldn't|"
    r"uses?|makes?|shows?|involves?|distinguishes?|evaluates?|operates?|applies|commits?|resembles?|looks?|sounds?|lacks?|avoids?|fails?)\b)",
    re.IGNORECASE,
)

_RE_META_APPLICABILITY_VERB = re.compile(
    r"\b(?:apply|applies|applied|applicable|present|exist\w*|hold|holds|held|occur\w*|arise\w*|"
    r"involved|used|needed|required|relevant|valid|true|at\s+play|in\s+play|at\s+issue|the\s+case|here|"
    r"distinct|different|differ\w*|separate\w*|diverg\w*|compet\w*|two|dual|polysem\w*|equivoca\w*|"
    r"contradict\w*|self-contradict\w*|paradox\w*|inconsisten\w*)\b",
    re.IGNORECASE,
)

_RE_PERMISSIBLE_PREDICATE = re.compile(
    r"\b(?:permissible|coherent|consistent|compatible|rational|tenable)\b",
    re.IGNORECASE,
)

_RE_DUAL_COLLAPSE_TOKEN = re.compile(
    r"\b(?:identical|the\s+same|one\s+and\s+the\s+same|indistinguishable|equivalent|undifferentiated|coincide\w*|collapse\w*)\b",
    re.IGNORECASE,
)

_RE_SINGLE_STANDARD_ONLY = re.compile(
    r"\b(?:only|just|merely|strictly|solely)\s+(?:one|a\s+single)\s+"
    r"(?:standard|criterion|metric|sense|meaning|definition|level|perspective)\b",
    re.IGNORECASE,
)

_RE_MOORE_OBJECT_BELIEF_NEG = re.compile(
    r"\b(?:not|never|don't|doesn't|didn't)\s+believ\w*\b"
    r"(?!\s+(?:that\s+)?(?:this|it)\s+is\s+(?:a\s+|an\s+)?(?:moore|paradox|contradict|self-contradict|inconsisten))|"
    r"\bbeliev\w*\s+not\b",
    re.IGNORECASE,
)

_RE_RETRACTION_OR_REFUTATION = re.compile(
    r"\b(?:that|this|such\s+a?)\s+(?:classification|view|reading|diagnosis|label|interpretation|analysis|claim|charge|conclusion|assessment|characterization)\s+"
    r"(?:is|was|would\s+be|turns?\s+out\s+to\s+be)\b[^,.;:!?\n]{0,40}"
    r"\b(?:wrong\w*|incorrect\w*|mistaken\w*|false|invalid\w*|flawed|misleading|inaccurate|unfounded|untenable)\b|"
    r"\b(?:wrongly|mistakenly|incorrectly|falsely|erroneously)\s+(?:classified|labeled|called|treated|viewed|diagnosed|characterized)\b",
    re.IGNORECASE,
)

_RE_SPEECH_ACT_CANCELLATION = re.compile(
    r"\b(?:merely|just|only|simply)\s+(?:reading|reciting|quoting|repeating)\b|"
    r"\breading\s+(?:a\s+|from\s+a\s+|the\s+)?script\b|"
    r"\b(?:unasserted|non-assertive)\s+(?:quote|quotation|reading|recitation|script)\b",
    re.IGNORECASE,
)

_RE_MULTI_INTERP_ENUM = re.compile(
    r"\b(?:first\b.*\bsecond\b|1\s*[\)\.]\s*.*2\s*[\)\.]|interpretation\s*1\b.*\binterpretation\s*2\b|"
    r"candidate\s*1\b.*\bcandidate\s*2\b|reading\s*1\b.*\breading\s*2\b|option\s*1\b.*\boption\s*2\b|"
    r"one\s+(?:interpretation|reading|view|possibility)\b.*\banother\s+(?:interpretation|reading|view|possibility)\b)",
    re.IGNORECASE | re.DOTALL,
)

_RE_MOORE_ASSERT_DISBELIEVE_CLAUSE = re.compile(
    r"\b(?:assert\w*|claim\w*|stat\w*|affirm\w*|say\w*)\b[^,.;!?\n]{0,70}"
    r"\b(?:deny\w*|disbeliev\w*|not\s+believ\w*|believ\w*\s+not|don't\s+believ\w*|doesn't\s+believ\w*|doubt\w*)\b",
    re.IGNORECASE,
)

_RE_AFFIRMATIVE_TEXTBOOK = re.compile(
    r"\bmoore(?:'?s)?\s+paradox\b|\bmoorean\s+(?:paradox|sentence|assertion|statement|contradiction|utterance)\b|"
    r"\b(?:classic|textbook|standard)\s+moorean?\b|"
    r"\b(?:cannot|can't|impossible\s+to|inconsistent\s+to|contradictory\s+to|self-contradictory\s+to|absurd\s+to|irrational\s+to)\b"
    r"[^,.;!?\n]{0,60}\b(?:assert|claim|state|affirm|say)\b[^,.;!?\n]{0,60}\b(?:deny|disbelieve|not\s+believe|believe\s+not|doubt)\b|"
    r"\b(?:direct\s+|pragmatic\s+|logical\s+|outright\s+)?(?:self-contradiction|self-contradictory|"
    r"contradicts?\s+(?:itself|himself|herself|themselves|the\s+(?:first|prior|initial|earlier)\s+(?:clause|claim|assertion|statement)))\b",
    re.IGNORECASE,
)

_RE_TEXTBOOK_PREDICATE_ON_MOORE_PAIR = re.compile(
    r"\b(?:contradict\w*|self-contradict\w*|paradox\w*|inconsisten\w*|absurd\w*|irrational\w*|incoherent|impossible)\b",
    re.IGNORECASE,
)

_LOCAL_TERMS = r"(?:local|technical|formal|procedural|nominal|narrow|static|accounting|bookkeeping|checklist|laboratory|bench|sensor|gauge|surface-level|compliance|regulatory)"
_GLOBAL_TERMS = r"(?:global|substantive|actual|overall|real-world|environmental|systemic|practical|clinical|relapse|operational|structural|holistic|ground-truth|field)"

_RE_LOCAL_VS_GLOBAL = re.compile(
    rf"\b{_LOCAL_TERMS}\b[^\.\n]{{0,100}}\b{_GLOBAL_TERMS}\b|"
    rf"\b{_GLOBAL_TERMS}\b[^\.\n]{{0,100}}\b{_LOCAL_TERMS}\b",
    re.IGNORECASE,
)

_RE_DUAL_CRITERIA_EXPLICIT = re.compile(
    r"\b(?:two|dual|distinct|different|separate|divergent|competing)\b[^\.\n]{0,60}"
    r"\b(?:standard|standards|criterion|criteria|metric|metrics|sense|senses|level|levels|perspective|perspectives|definition|definitions|meaning|meanings|dimension|dimensions)\b|"
    r"\b(?:polysemy|polysemous|equivocation|two\s+senses|dual\s+standard|dual\s+criteria)\b",
    re.IGNORECASE,
)


def _clean_moore_object_belief_neg(s: str) -> str:
    """Mask object-level Moorean belief negation (`not believe`) and correlative `nor`."""
    return re.sub(r"\bnor\b", "or", _RE_MOORE_OBJECT_BELIEF_NEG.sub("__MOORE_BELIEF__", s), flags=re.IGNORECASE)


def _count_neg_parity_in_span(s: str) -> int:
    """Count non-overlapping functional + lexical meta-negation spans in `s`."""
    cleaned = _clean_moore_object_belief_neg(s)
    return len(list(_RE_COMBINED_META_NEG_SPAN.finditer(cleaned)))


def _count_neg_parity_around_match(sub: str, start: int, end: int, *, include_dual_collapse: bool = False) -> int:
    """Count meta-level negation/collapse operators scoping over `sub[start:end]`."""
    prefix_raw = _clean_moore_object_belief_neg(sub[:start])
    coord_bounds_pre = list(_RE_COORD_CLAUSE_BOUNDARY.finditer(prefix_raw))
    prefix = prefix_raw[coord_bounds_pre[-1].end():] if coord_bounds_pre else prefix_raw

    interior = _clean_moore_object_belief_neg(sub[start:end])

    suffix_raw = _clean_moore_object_belief_neg(sub[end:])
    coord_bounds_suf = list(_RE_COORD_CLAUSE_BOUNDARY.finditer(suffix_raw))
    suffix = suffix_raw[:coord_bounds_suf[0].start()] if coord_bounds_suf else suffix_raw

    n_neg = len(list(_RE_COMBINED_META_NEG_SPAN.finditer(prefix)))

    n_suffix_collapse = len(_RE_DUAL_COLLAPSE_TOKEN.findall(suffix)) if include_dual_collapse else 0
    n_interior_collapse = len(_RE_DUAL_COLLAPSE_TOKEN.findall(interior)) if include_dual_collapse else 0

    if (
        n_suffix_collapse > 0
        or _RE_LEXICAL_META_NEG_TOKEN.search(suffix) is not None
        or _RE_META_APPLICABILITY_VERB.search(suffix) is not None
    ):
        n_neg += n_suffix_collapse + len(list(_RE_COMBINED_META_NEG_SPAN.finditer(suffix)))

    if n_interior_collapse > 0:
        n_neg += n_interior_collapse + len(list(_RE_COMBINED_META_NEG_SPAN.finditer(interior)))

    return n_neg


def _subclause_textbook_polarity(sub: str) -> str:
    """Return `'affirm'`, `'negate'`, or `'none'` for textbook single-standard reflex in `sub`."""
    matches = list(_RE_AFFIRMATIVE_TEXTBOOK.finditer(sub))
    has_moore_pair = bool(_RE_MOORE_ASSERT_DISBELIEVE_CLAUSE.search(sub))
    if not matches and has_moore_pair:
        matches = list(_RE_TEXTBOOK_PREDICATE_ON_MOORE_PAIR.finditer(sub))
    if not matches:
        if has_moore_pair:
            perm_m = list(_RE_PERMISSIBLE_PREDICATE.finditer(sub))
            if perm_m:
                for pm in perm_m:
                    if (_count_neg_parity_around_match(sub, pm.start(), pm.end()) + 1) % 2 == 0:
                        return "affirm"
                return "negate"
        gen_m = list(_RE_TEXTBOOK_PREDICATE_ON_MOORE_PAIR.finditer(sub))
        if gen_m and any(_count_neg_parity_around_match(sub, m.start(), m.end()) % 2 == 1 for m in gen_m):
            return "negate"
        return "none"
    for m in matches:
        if _count_neg_parity_around_match(sub, m.start(), m.end()) % 2 == 0:
            return "affirm"
    return "negate"


def _subclause_dual_polarity(sub: str) -> str:
    """Return `'affirm'`, `'negate'`, or `'none'` for dual-criteria / polysemy detection in `sub`."""
    single_m = _RE_SINGLE_STANDARD_ONLY.search(sub)
    if single_m and _count_neg_parity_around_match(sub, single_m.start(), single_m.end()) % 2 == 0:
        return "negate"
    matches = list(_RE_DUAL_CRITERIA_EXPLICIT.finditer(sub)) + list(_RE_LOCAL_VS_GLOBAL.finditer(sub))
    if not matches:
        return "none"
    for m in matches:
        if _count_neg_parity_around_match(sub, m.start(), m.end(), include_dual_collapse=True) % 2 == 0:
            return "affirm"
    return "negate"


def classify_reasoning_text_e4(
    text: str,
    task: str = "",
    prompt: str = "",
) -> dict[str, bool]:
    """Classify reasoning text into affirmative textbook single-standard reflex vs dual criteria/polysemy detection."""
    if not isinstance(text, str) or not text.strip():
        return {
            "textbook_single_standard_reflex": False,
            "dual_criteria_or_polysemy_detected": False,
        }

    has_multi_enum = bool(_RE_MULTI_INTERP_ENUM.search(text))
    clauses = [c.strip() for c in _RE_CLAUSE_SPLIT.split(text) if c.strip()]

    tb = False
    for clause in clauses:
        ret_m = _RE_RETRACTION_OR_REFUTATION.search(clause)
        if ret_m and _count_neg_parity_in_span(clause) % 2 == 1:
            tb = False
            continue
        if not has_multi_enum and _RE_SPEECH_ACT_CANCELLATION.search(clause):
            tb = False
            continue
        subclauses = [clause]
        if "," in clause and _RE_CONCESSIVE_OR_TENTATIVE.search(clause.split(",", 1)[0]):
            subclauses = [s.strip() for s in clause.split(",") if s.strip()]
        for sub in subclauses:
            if _RE_CONCESSIVE_OR_TENTATIVE.search(sub):
                continue
            pol = _subclause_textbook_polarity(sub)
            if pol == "affirm":
                tb = True
                break
            if pol == "negate" and not has_multi_enum:
                tb = False

    dc = False
    for clause in clauses:
        ret_m = _RE_RETRACTION_OR_REFUTATION.search(clause)
        if ret_m and not has_multi_enum and _count_neg_parity_in_span(clause) % 2 == 1:
            dc = False
            continue
        subclauses = [clause]
        if "," in clause and _RE_CONCESSIVE_OR_TENTATIVE.search(clause.split(",", 1)[0]):
            subclauses = [s.strip() for s in clause.split(",") if s.strip()]
        for sub in subclauses:
            if _RE_CONCESSIVE_OR_TENTATIVE.search(sub):
                continue
            pol = _subclause_dual_polarity(sub)
            if pol == "affirm":
                dc = True
                break
            if pol == "negate" and not has_multi_enum:
                dc = False

    return {
        "textbook_single_standard_reflex": tb,
        "dual_criteria_or_polysemy_detected": dc,
    }


_RE_FINAL_NUM_LINES = re.compile(
    r"^\s*(?:Probability\s*:|Estimate\s+[1-5]\s*:).*$",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_reasoning_segments_from_record_e4(r: dict[str, Any]) -> list[str]:
    """Extract reasoning segments from a record; keeps independent `CF` candidates separate."""
    tk = str(r.get("task") or "")
    pr = str(r.get("prompt") or "")
    parsed = r.get("parsed") or {}
    segments: list[str] = []
    if isinstance(parsed, dict):
        obj = parsed.get("object") if isinstance(parsed.get("object"), dict) else parsed
        if obj.get("reasoning") and str(obj["reasoning"]).strip():
            segments.append(str(obj["reasoning"]).strip())
        if obj.get("possible_interruptions") and isinstance(obj["possible_interruptions"], list):
            for x in obj["possible_interruptions"]:
                if str(x).strip():
                    segments.append(str(x).strip())
        if obj.get("interpretations") and isinstance(obj["interpretations"], list):
            for x in obj["interpretations"]:
                if str(x).strip():
                    segments.append(str(x).strip())
    if tk in ("P", "M") and pr in ("CoT", "CF") and r.get("text"):
        cleaned = _RE_FINAL_NUM_LINES.sub("", str(r["text"])).strip()
        if cleaned:
            if pr == "CF":
                lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
                for ln in (lines if len(lines) >= 2 else [cleaned]):
                    if ln not in segments:
                        segments.append(ln)
            elif cleaned not in segments:
                segments.append(cleaned)
    elif not segments and r.get("text") and tk != "L":
        txt_fallback = str(r["text"]).strip()
        if txt_fallback:
            segments.append(txt_fallback)
    return segments


def _extract_reasoning_text_from_record_e4(r: dict[str, Any]) -> str:
    """Extract pure reasoning text from a record according to `PLAN-E4.md` §4.3(1)."""
    return " ".join(_extract_reasoning_segments_from_record_e4(r)).strip()


def summarize_reasoning_mechanisms_e4(
    records: list[dict[str, Any]],
    cluster_ids: list[str],
    by_cid: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Scan reasoning text for conditions `L/CoT, P/CoT, M/CoT, L/CF, P/CF, M/CF` across slots and domains."""
    target_conditions = (("L", "CoT"), ("P", "CoT"), ("M", "CoT"), ("L", "CF"), ("P", "CF"), ("M", "CF"))

    def _eval_subset(subset_cids: set[str]) -> dict[str, Any]:
        records_by_cond_slot: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in records:
            cid = r.get("cluster_id")
            if cid not in subset_cids:
                continue
            tk = r.get("task")
            pr = r.get("prompt")
            slot = r.get("slot")
            if (tk, pr) in target_conditions and slot in MAIN_SLOTS:
                records_by_cond_slot.setdefault((tk, pr, slot), []).append(r)

        sub_out: dict[str, Any] = {}
        n_planned = len(subset_cids)
        for tk, pr in target_conditions:
            cond_key = f"{tk}/{pr}"
            sub_out[cond_key] = {}
            for slot in MAIN_SLOTS:
                recs = records_by_cond_slot.get((tk, pr, slot), [])
                n_records = len(recs)
                n_valid = 0
                n_tb = 0
                n_dc = 0
                for r in recs:
                    if r.get("status") not in (None, "ok"):
                        continue
                    segs = _extract_reasoning_segments_from_record_e4(r)
                    if not segs:
                        continue
                    n_valid += 1
                    seg_results = [classify_reasoning_text_e4(seg, tk, pr) for seg in segs]
                    if any(res["textbook_single_standard_reflex"] for res in seg_results):
                        n_tb += 1
                    if any(res["dual_criteria_or_polysemy_detected"] for res in seg_results):
                        n_dc += 1
                sub_out[cond_key][slot] = {
                    "n": n_valid,
                    "n_planned": n_planned,
                    "n_records": n_records,
                    "n_valid_text": n_valid,
                    "missing_or_empty_text_count": max(0, n_planned - n_valid),
                    "textbook_single_standard_reflex_count": n_tb,
                    "textbook_single_standard_reflex_rate": (n_tb / n_valid) if n_valid else 0.0,
                    "textbook_single_standard_reflex_rate_over_planned": (n_tb / n_planned) if n_planned else 0.0,
                    "dual_criteria_or_polysemy_detected_count": n_dc,
                    "dual_criteria_or_polysemy_detected_rate": (n_dc / n_valid) if n_valid else 0.0,
                    "dual_criteria_or_polysemy_detected_rate_over_planned": (n_dc / n_planned) if n_planned else 0.0,
                }
        return sub_out

    summary = _eval_subset(set(cluster_ids))
    if by_cid is not None:
        summary["by_domain_subclass"] = {
            dom: _eval_subset({cid for cid in cluster_ids if by_cid.get(cid, {}).get("domain_subclass") == dom})
            for dom in DOMAIN_SUBCLASSES
        }
    return summary


def analyze_stage_records_e4(
    records: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    stage_cluster_ids: list[str],
    stage: str = "formal",
    b: int = B_DEFAULT,
    seed: int | None = None,
    primary_method: str | None = None,
    demoted_slots: tuple[str, ...] | None = None,
    calibration_lock: dict[str, Any] | None = None,
    require_calibration_lock: bool = False,
) -> dict[str, Any]:
    """Run complete confirmatory + companion + Layer 3 analysis for `dev` or `formal` stage (`PLAN-E4.md` §4)."""
    if seed is None:
        seed = FORMAL_ANALYSIS_SEED_E4 if stage == "formal" else DEV_ANALYSIS_SEED_E4
    if calibration_lock is not None:
        if calibration_lock.get("status") != "pass":
            raise ValueError("calibration_lock status must be 'pass'")
        sel_fam = calibration_lock.get("selected_family")
        if sel_fam not in ("hybrid_pct_tango_e4", "hybrid_bessel_t_tango_e4"):
            raise ValueError(f"Invalid selected_family in calibration_lock: {sel_fam!r}")
        if primary_method is None:
            primary_method = "pct" if sel_fam == "hybrid_pct_tango_e4" else "bessel_t"
        if demoted_slots is None:
            demoted_slots = tuple(calibration_lock.get("demoted_slots") or ())
    elif require_calibration_lock:
        raise ValueError("require_calibration_lock=True requires a valid calibration_lock")
    if primary_method is None:
        primary_method = "pct"
    if demoted_slots is None:
        demoted_slots = ()

    by_cid = {c["cluster_id"]: c for c in clusters}
    all_cids = sorted(stage_cluster_ids)
    domain_cids: dict[str, list[str]] = {
        dom: sorted(cid for cid in all_cids if by_cid[cid]["domain_subclass"] == dom)
        for dom in DOMAIN_SUBCLASSES
    }
    domain_counts = {dom: len(domain_cids[dom]) for dom in DOMAIN_SUBCLASSES}

    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    by_uk: dict[str, dict[str, Any]] = {}
    for r in records:
        if "unit_key" in r:
            by_uk[r["unit_key"]] = r
        cid = r.get("cluster_id")
        slot = r.get("slot")
        task = r.get("task")
        prompt = r.get("prompt")
        if cid and slot and task and prompt:
            by_tuple[(cid, slot, task, prompt)] = r

    # 1. Shared RNG stream for all n clusters, followed sequentially by 4 domains (`PLAN-E4.md` §4.2(1))
    w_all, w_dom = draw_all_bootstrap_weights_e4(
        len(all_cids), domain_counts, b=b, seed=seed
    )

    ext_all = extract_primary_inputs_from_records_e4(records, all_cids, allow_missing_score_for_h4=False)
    companion_method = "bessel_t" if primary_method == "pct" else "pct"
    primary_family = evaluate_four_slot_family_e4(
        ext_all["inputs"], w_all, continuous_method=primary_method, demoted_slots=demoted_slots
    )
    companion_family = evaluate_four_slot_family_e4(
        ext_all["inputs"], w_all, continuous_method=companion_method, demoted_slots=demoted_slots
    )

    # E4_H4 companion row using `label_available` (`status in ("ok", "missing_score")`)
    ext_lbl_avail = extract_primary_inputs_from_records_e4(records, all_cids, allow_missing_score_for_h4=True)
    h4_lbl_avail = infer_discrete_slot_e4(*ext_lbl_avail["inputs"]["E4_H4"], one_sided=True)
    h4_lbl_avail["missing_score_units_recovered"] = (
        ext_all["missing_units"]["E4_H4"] - ext_lbl_avail["missing_units"]["E4_H4"]
    )

    # 2. Mandatory parallel 4-domain breakdown (`D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`)
    domain_parallel: dict[str, Any] = {}
    for dom in DOMAIN_SUBCLASSES:
        d_cids = domain_cids[dom]
        ext_dom = extract_primary_inputs_from_records_e4(records, d_cids, allow_missing_score_for_h4=False)
        w_d = w_dom[dom]
        n_sub = len(d_cids)
        slots_sub: dict[str, Any] = {}
        for s_slot in CONTINUOUS_SLOTS:
            d_lo_s, d_hi_s = ext_dom["inputs"][s_slot]
            slots_sub[s_slot] = {
                "pct": infer_continuous_slot_e4(d_lo_s, d_hi_s, w_d, method="pct"),
                "bessel_t": (
                    infer_continuous_slot_e4(d_lo_s, d_hi_s, w_d, method="bessel_t")
                    if n_sub in BESSEL_T_FACTORS_BY_N
                    else None
                ),
            }
        slots_sub["E4_H4"] = (
            infer_discrete_slot_e4(*ext_dom["inputs"]["E4_H4"], one_sided=True)
            if n_sub in exact_tango_e4.SUPPORTED_NS
            else None
        )
        domain_parallel[dom] = {
            "n_clusters": n_sub,
            "cluster_ids": d_cids,
            "complete_cluster_counts": ext_dom["complete_cluster_counts"],
            "missing_units": ext_dom["missing_units"],
            "slots": slots_sub,
            "conditions_13_main_slots": {
                f"{tk}/{pr}": _summarize_condition_main_slots(by_tuple, by_uk, d_cids, tk, pr, w_d)
                for tk, pr in COMBINATIONS
            },
        }

    # 3. Layer 3 Item 2: Non-assertive script reading control (`PURE_READ`) paired contrasts
    pure_read_contrasts: dict[str, Any] = {}
    for tk, pr in (("P", "Z"), ("P", "CoT"), ("M", "Z"), ("M", "CoT"), ("L", "Z"), ("L", "CoT")):
        cond_k = f"{tk}/{pr}"
        pure_r_lo, pure_r_hi = [], []
        pure_m_lo, pure_m_hi = [], []
        dual_m_lo, dual_m_hi = [], []
        for cid in all_cids:
            if tk == "L":
                r_lo, r_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "PURE_READ", tk, pr)
                pm_lo, pm_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "PURE_MOORE", tk, pr)
                dm_lo, dm_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "DUAL_MOORE", tk, pr)
                pure_r_lo.append(100.0 * r_lo)
                pure_r_hi.append(100.0 * r_hi)
                pure_m_lo.append(100.0 * pm_lo)
                pure_m_hi.append(100.0 * pm_hi)
                dual_m_lo.append(100.0 * dm_lo)
                dual_m_hi.append(100.0 * dm_hi)
            else:
                use_u = (tk == "M")
                r_lo, r_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "PURE_READ", tk, pr, use_unweighted_m=use_u)
                pm_lo, pm_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "PURE_MOORE", tk, pr, use_unweighted_m=use_u)
                dm_lo, dm_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "DUAL_MOORE", tk, pr, use_unweighted_m=use_u)
                pure_r_lo.append(r_lo)
                pure_r_hi.append(r_hi)
                pure_m_lo.append(pm_lo)
                pure_m_hi.append(pm_hi)
                dual_m_lo.append(dm_lo)
                dual_m_hi.append(dm_hi)
        arr_r_lo, arr_r_hi = np.array(pure_r_lo), np.array(pure_r_hi)
        arr_pm_lo, arr_pm_hi = np.array(pure_m_lo), np.array(pure_m_hi)
        arr_dm_lo, arr_dm_hi = np.array(dual_m_lo), np.array(dual_m_hi)
        pure_read_contrasts[cond_k] = {
            "PURE_READ_minus_PURE_MOORE": _paired_summary_ci95(arr_r_lo - arr_pm_hi, arr_r_hi - arr_pm_lo, w_all),
            "PURE_READ_minus_DUAL_MOORE": _paired_summary_ci95(arr_r_lo - arr_dm_hi, arr_r_hi - arr_dm_lo, w_all),
        }

    # 4. Layer 3 Item 3 & 4: All 13 conditions main slots, M_W vs M_U, and L trilabel + q table
    all_13_conditions: dict[str, Any] = {}
    for tk, pr in COMBINATIONS:
        cond_key = f"{tk}/{pr}"
        all_13_conditions[cond_key] = {
            "all": _summarize_condition_main_slots(by_tuple, by_uk, all_cids, tk, pr, w_all),
        }
        for dom in DOMAIN_SUBCLASSES:
            all_13_conditions[cond_key][dom] = _summarize_condition_main_slots(
                by_tuple, by_uk, domain_cids[dom], tk, pr, w_dom[dom]
            )

    metalanguage_mw_minus_mu: dict[str, Any] = {}
    for pr in ("Z", "DAP", "CoT", "CF"):
        cond_key = f"M/{pr}"
        metalanguage_mw_minus_mu[cond_key] = {}
        for g_name, g_cids, w_g in [("all", all_cids, w_all)] + [(dom, domain_cids[dom], w_dom[dom]) for dom in DOMAIN_SUBCLASSES]:
            mw_slot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            mu_slot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            within_slot_delta: dict[str, Any] = {}
            candidate_stats: dict[str, Any] = {}
            for slot in MAIN_SLOTS:
                w_lo, w_hi, u_lo, u_hi = [], [], [], []
                med_lo, med_hi, top1_lo, top1_hi, sd_within = [], [], [], [], []
                for cid in g_cids:
                    wl, wh, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, slot, "M", pr, use_unweighted_m=False)
                    ul, uh, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, slot, "M", pr, use_unweighted_m=True)
                    w_lo.append(wl)
                    w_hi.append(wh)
                    u_lo.append(ul)
                    u_hi.append(uh)
                    rec_m = _lookup_record(by_tuple, by_uk, cid, slot, "M", pr)
                    parsed_m = (rec_m.get("parsed") or {}) if rec_m and rec_m.get("status") == "ok" else {}
                    ests = parsed_m.get("estimates")
                    wgts = parsed_m.get("weights")
                    if isinstance(ests, list) and len(ests) == 5:
                        ests_f = [float(x) for x in ests]
                        med_v = float(np.median(ests_f))
                        med_lo.append(med_v)
                        med_hi.append(med_v)
                        sd_within.append(float(np.std(ests_f, ddof=1)))
                        if isinstance(wgts, list) and len(wgts) == 5:
                            best_idx = int(np.argmax([float(w) for w in wgts]))
                            top1_v = ests_f[best_idx]
                        else:
                            top1_v = ests_f[0]
                        top1_lo.append(top1_v)
                        top1_hi.append(top1_v)
                    else:
                        med_lo.append(0.0)
                        med_hi.append(100.0)
                        top1_lo.append(0.0)
                        top1_hi.append(100.0)
                arr_wl = np.array(w_lo, dtype=np.float64)
                arr_wh = np.array(w_hi, dtype=np.float64)
                arr_ul = np.array(u_lo, dtype=np.float64)
                arr_uh = np.array(u_hi, dtype=np.float64)
                mw_slot[slot] = (arr_wl, arr_wh)
                mu_slot[slot] = (arr_ul, arr_uh)
                within_slot_delta[slot] = _paired_summary_ci95(arr_wl - arr_uh, arr_wh - arr_ul, w_g)
                candidate_stats[slot] = {
                    "MW_summary": _paired_summary_ci95(arr_wl, arr_wh, w_g),
                    "MU_summary": _paired_summary_ci95(arr_ul, arr_uh, w_g),
                    "Median_summary": _paired_summary_ci95(np.array(med_lo), np.array(med_hi), w_g),
                    "Top1_summary": _paired_summary_ci95(np.array(top1_lo), np.array(top1_hi), w_g),
                    "within_call_sd_mean": float(np.mean(sd_within)) if sd_within else None,
                }
            dm_wl, dm_wh = mw_slot["DUAL_MOORE"]
            pm_wl, pm_wh = mw_slot["PURE_MOORE"]
            dm_ul, dm_uh = mu_slot["DUAL_MOORE"]
            pm_ul, pm_uh = mu_slot["PURE_MOORE"]
            metalanguage_mw_minus_mu[cond_key][g_name] = {
                "within_slot_MW_minus_MU_summary": within_slot_delta,
                "candidate_summaries": candidate_stats,
                "DUAL_MOORE_minus_PURE_MOORE_MW": _paired_summary_ci95(dm_wl - pm_wh, dm_wh - pm_wl, w_g),
                "DUAL_MOORE_minus_PURE_MOORE_MU": _paired_summary_ci95(dm_ul - pm_uh, dm_uh - pm_ul, w_g),
                "delta_on_DUAL_MOORE_minus_PURE_MOORE": _paired_summary_ci95(
                    (dm_wl - pm_wh) - (dm_uh - pm_ul),
                    (dm_wh - pm_wl) - (dm_ul - pm_uh),
                    w_g,
                ),
            }

    # Layer 3 single-factor companion decompositions (`PLAN-E4.md` §4.1)
    def _vec_cont(slot: str, tk: str, pr: str, use_u: bool) -> tuple[np.ndarray, np.ndarray]:
        lo_l, hi_l = [], []
        for cid in all_cids:
            lv, hv, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, slot, tk, pr, use_unweighted_m=use_u)
            lo_l.append(lv)
            hi_l.append(hv)
        return np.array(lo_l, dtype=np.float64), np.array(hi_l, dtype=np.float64)

    def _vec_lbl_pct(slot: str, pr: str) -> tuple[np.ndarray, np.ndarray]:
        lo_l, hi_l = [], []
        for cid in all_cids:
            lv, hv, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, slot, "L", pr)
            lo_l.append(100.0 * lv)
            hi_l.append(100.0 * hv)
        return np.array(lo_l, dtype=np.float64), np.array(hi_l, dtype=np.float64)

    dm_p_cot_lo, dm_p_cot_hi = _vec_cont("DUAL_MOORE", "P", "CoT", False)
    dm_mu_z_lo, dm_mu_z_hi = _vec_cont("DUAL_MOORE", "M", "Z", True)
    dm_mu_cot_lo, dm_mu_cot_hi = _vec_cont("DUAL_MOORE", "M", "CoT", True)
    dm_p_cf_lo, dm_p_cf_hi = _vec_cont("DUAL_MOORE", "P", "CF", False)
    dm_mw_cf_lo, dm_mw_cf_hi = _vec_cont("DUAL_MOORE", "M", "CF", False)
    dm_mu_cf_lo, dm_mu_cf_hi = _vec_cont("DUAL_MOORE", "M", "CF", True)
    pm_mu_cf_lo, pm_mu_cf_hi = _vec_cont("PURE_MOORE", "M", "CF", True)
    dm_p_z_lo, dm_p_z_hi = _vec_cont("DUAL_MOORE", "P", "Z", False)
    pm_p_z_lo, pm_p_z_hi = _vec_cont("PURE_MOORE", "P", "Z", False)
    pm_p_cot_lo, pm_p_cot_hi = _vec_cont("PURE_MOORE", "P", "CoT", False)
    dm_mw_z_lo, dm_mw_z_hi = _vec_cont("DUAL_MOORE", "M", "Z", False)
    pm_mw_z_lo, pm_mw_z_hi = _vec_cont("PURE_MOORE", "M", "Z", False)
    de_p_cot_lo, de_p_cot_hi = _vec_cont("DUAL_EXPLICIT", "P", "CoT", False)
    de_mu_z_lo, de_mu_z_hi = _vec_cont("DUAL_EXPLICIT", "M", "Z", True)
    de_mu_cf_lo, de_mu_cf_hi = _vec_cont("DUAL_EXPLICIT", "M", "CF", True)
    pr_l_cot_lo, pr_l_cot_hi = _vec_lbl_pct("PURE_READ", "CoT")
    dm_l_cot_lo, dm_l_cot_hi = _vec_lbl_pct("DUAL_MOORE", "CoT")
    dm_l_cf_lo, dm_l_cf_hi = _vec_lbl_pct("DUAL_MOORE", "CF")
    de_l_z_lo, de_l_z_hi = _vec_lbl_pct("DUAL_EXPLICIT", "Z")
    dm_l_z_lo, dm_l_z_hi = _vec_lbl_pct("DUAL_MOORE", "Z")
    de_l_cf_lo, de_l_cf_hi = _vec_lbl_pct("DUAL_EXPLICIT", "CF")

    layer3_primary_companion_contrasts = {
        "E4_H1_decompositions_on_DUAL_MOORE": {
            "M_U_Z_minus_P_CoT": _paired_summary_ci95(dm_mu_z_lo - dm_p_cot_hi, dm_mu_z_hi - dm_p_cot_lo, w_all),
            "M_U_CoT_minus_P_CoT": _paired_summary_ci95(dm_mu_cot_lo - dm_p_cot_hi, dm_mu_cot_hi - dm_p_cot_lo, w_all),
            "P_CF_minus_P_CoT": _paired_summary_ci95(dm_p_cf_lo - dm_p_cot_hi, dm_p_cf_hi - dm_p_cot_lo, w_all),
            "M_W_CF_minus_P_CoT": _paired_summary_ci95(dm_mw_cf_lo - dm_p_cot_hi, dm_mw_cf_hi - dm_p_cot_lo, w_all),
        },
        "E4_H2_decompositions_DUAL_MOORE_minus_PURE_MOORE": {
            "on_M_U_CF": _paired_summary_ci95(dm_mu_cf_lo - pm_mu_cf_hi, dm_mu_cf_hi - pm_mu_cf_lo, w_all),
            "on_P_Z": _paired_summary_ci95(dm_p_z_lo - pm_p_z_hi, dm_p_z_hi - pm_p_z_lo, w_all),
            "on_P_CoT": _paired_summary_ci95(dm_p_cot_lo - pm_p_cot_hi, dm_p_cot_hi - pm_p_cot_lo, w_all),
            "on_M_W_Z": _paired_summary_ci95(dm_mw_z_lo - pm_mw_z_hi, dm_mw_z_hi - pm_mw_z_lo, w_all),
        },
        "E4_H3_decompositions_DUAL_EXPLICIT_minus_DUAL_MOORE": {
            "on_P_CoT": _paired_summary_ci95(de_p_cot_lo - dm_p_cot_hi, de_p_cot_hi - dm_p_cot_lo, w_all),
            "on_M_U_Z": _paired_summary_ci95(de_mu_z_lo - dm_mu_z_hi, de_mu_z_hi - dm_mu_z_lo, w_all),
            "on_M_U_CF": _paired_summary_ci95(de_mu_cf_lo - dm_mu_cf_hi, de_mu_cf_hi - dm_mu_cf_lo, w_all),
        },
        "E4_H4_decompositions_on_L_true_pct": {
            "PURE_READ_minus_DUAL_MOORE_L_CoT": _paired_summary_ci95(pr_l_cot_lo - dm_l_cot_hi, pr_l_cot_hi - dm_l_cot_lo, w_all),
            "DUAL_MOORE_L_CF_minus_L_CoT": _paired_summary_ci95(dm_l_cf_lo - dm_l_cot_hi, dm_l_cf_hi - dm_l_cot_lo, w_all),
            "DUAL_EXPLICIT_minus_DUAL_MOORE_L_Z": _paired_summary_ci95(de_l_z_lo - dm_l_z_hi, de_l_z_hi - dm_l_z_lo, w_all),
            "DUAL_EXPLICIT_minus_DUAL_MOORE_L_CF": _paired_summary_ci95(de_l_cf_lo - dm_l_cf_hi, de_l_cf_hi - dm_l_cf_lo, w_all),
        },
    }

    l_task_trilabel_and_q: dict[str, Any] = {}
    for pr in ("Z", "DAP", "CoT", "CF"):
        cond_key = f"L/{pr}"
        l_task_trilabel_and_q[cond_key] = {}
        for g_name, g_cids, w_g in [("all", all_cids, w_all)] + [(dom, domain_cids[dom], w_dom[dom]) for dom in DOMAIN_SUBCLASSES]:
            l_task_trilabel_and_q[cond_key][g_name] = {}
            for slot in MAIN_SLOTS:
                counts = {"True": 0, "False": 0, "Unknown": 0, "missing": 0}
                q_lo_vals, q_hi_vals = [], []
                t_lo_vals, t_hi_vals = [], []
                q_ok = 0
                for cid in g_cids:
                    rec = _lookup_record(by_tuple, by_uk, cid, slot, "L", pr)
                    if rec is None or rec.get("status") != "ok":
                        counts["missing"] += 1
                        q_lo_vals.append(0.0)
                        q_hi_vals.append(1.0)
                        t_lo_vals.append(0.0)
                        t_hi_vals.append(100.0)
                    else:
                        lbl = rec.get("label")
                        if lbl in ("True", "False", "Unknown"):
                            counts[lbl] += 1
                            tv = 100.0 if lbl == "True" else 0.0
                            t_lo_vals.append(tv)
                            t_hi_vals.append(tv)
                        else:
                            counts["missing"] += 1
                            t_lo_vals.append(0.0)
                            t_hi_vals.append(100.0)
                        q_obj = rec.get("q") or {}
                        if q_obj.get("q_status") in ("full", "bounded") and q_obj.get("q_L") is not None:
                            q_lo_vals.append(float(q_obj["q_L"]))
                            q_hi_vals.append(float(q_obj["q_U"]))
                            q_ok += 1
                        else:
                            q_lo_vals.append(0.0)
                            q_hi_vals.append(1.0)
                n_g = len(g_cids)
                q_summary = _paired_summary_ci95(
                    np.array(q_lo_vals, dtype=np.float64),
                    np.array(q_hi_vals, dtype=np.float64),
                    w_g,
                )
                t_summary = _paired_summary_ci95(
                    np.array(t_lo_vals, dtype=np.float64),
                    np.array(t_hi_vals, dtype=np.float64),
                    w_g,
                )
                l_task_trilabel_and_q[cond_key][g_name][slot] = {
                    "n": n_g,
                    "counts": counts,
                    "rates": {k: (v / n_g if n_g else 0.0) for k, v in counts.items()},
                    "true_pct_ci_95": t_summary["ci_95"],
                    "q_ok_units": q_ok,
                    "q_mean_lower": q_summary["mean_lower"],
                    "q_mean_upper": q_summary["mean_upper"],
                    "q_ci_95": q_summary["ci_95"],
                }

    # 5. Layer 3 Item 1: Reasoning Mechanism Analysis
    reasoning_summary = summarize_reasoning_mechanisms_e4(records, all_cids, by_cid=by_cid)

    return {
        "stage": stage,
        "seed": seed,
        "b": b,
        "n_all": len(all_cids),
        "domain_counts": domain_counts,
        "primary_method": primary_method,
        "demoted_slots": sorted(demoted_slots),
        "complete_cluster_counts": ext_all["complete_cluster_counts"],
        "missing_units": ext_all["missing_units"],
        "primary_family": primary_family,
        "companion_family": companion_family,
        "e4_h4_label_available_companion": h4_lbl_avail,
        "domain_subclass_parallel_breakdown": domain_parallel,
        "diagnostic_context_breakdown": _summarize_diagnostic_contexts(by_tuple, by_uk, by_cid, all_cids),
        "layer3_primary_companion_contrasts": layer3_primary_companion_contrasts,
        "cancel_assertion_pure_read_comparison": pure_read_contrasts,
        "all_13_conditions_main_slots": all_13_conditions,
        "layer3_metalanguage_mw_minus_mu": metalanguage_mw_minus_mu,
        "layer3_l_task_trilabel_and_q_table": l_task_trilabel_and_q,
        "reasoning_mechanisms_summary": reasoning_summary,
    }
