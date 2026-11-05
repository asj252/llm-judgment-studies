"""Locked Statistical Engine for Experiment 3 (English Atelic B/D Disambiguation) (`exp3-en/PLAN-E3.md` §4).

Implements the two candidate confirmatory families evaluated in Stage S4 calibration
and bound into Stage S5 `freeze.json` / Stage S7 formal analysis on all `n = 80` formal
clusters (`n = 20` on dev, `n = 79` on sensitivity check excluding cluster `095`):
1. Candidate 1 (`hybrid_pct_tango_e3`):
   - Continuous paired contrasts `E3_H1`, `E3_H2`, `E3_H3`: Cluster-level equal-weight
     multinomial bootstrap (`B = 5000`) on a single shared PCG64 stream (`seed = 2026110401`
     for formal, `seed = 2026110402` for dev, `seed = 2026110403` for 79-cluster sensitivity),
     using uninterpolated order-statistic 98.75% CIs (`idx_lo = 31, idx_hi = 4968`, 0-based)
     and 95% companion CIs (`idx_lo = 124, idx_hi = 4875`), plus one-sided p-values
     `(1 + #{theta* <= 0}) / (B + 1)` when point_lower > 0 else `1.0`.
   - Discrete paired proportion contrast `E3_H4` (`NI_OCC` vs `NI_PLAN` True rate on `L/CoT`):
     Certified exact unconditional Tango (1998) score test and 98.75% CI via `exact_tango_e3`.
2. Candidate 2 / Companion (`hybrid_bessel_t_tango_e3`):
   - Same exact Tango test/CI for `E3_H4`, and order-preserving Bessel-t center-expanded
     bootstrap CIs (`c_80 = 1.0298684039340296`, `c_79 = 1.0302596947224958`,
     `c_64 = 1.037660015052903`, `c_20 = 1.1331397732007173`, `c_16 = 1.1729390393815105`,
     `c_12 = 1.2465119462060201`, `c_8 = 1.4275423213691008`) for `E3_H1..E3_H3`.

Enforces all 4 pre-clipping degeneracy rules (`PLAN-E3.md` §4.2(2)), worst-case bounds for
`status != "ok"` (`PLAN-E3.md` §4.2(4)), Holm step-down (`m = 4, alpha_fam = 0.05`) with
fixed tie-break order `E3_H1..E3_H4`, mandatory parallel `A_plan` vs `A_pure` breakdown,
79-cluster sensitivity check excluding `095`, and Layer 3 descriptive tables.
"""
from __future__ import annotations

from decimal import Decimal, getcontext
import math
from typing import Any

import numpy as np

import exact_tango_e3
from prompts_e3 import COMBINATIONS

FORMAL_ANALYSIS_SEED_E3 = 2026110401
DEV_ANALYSIS_SEED_E3 = 2026110402
SENS79_ANALYSIS_SEED_E3 = 2026110403
B_DEFAULT = 5000
ALPHA_FAMILY = 0.05
ALPHA_IND = 0.0125  # 0.05 / 4

E3_SLOT_ORDER: tuple[str, ...] = ("E3_H1", "E3_H2", "E3_H3", "E3_H4")
CONTINUOUS_SLOTS: tuple[str, ...] = ("E3_H1", "E3_H2", "E3_H3")
DISCRETE_SLOTS: tuple[str, ...] = ("E3_H4",)
MAIN_SLOTS: tuple[str, ...] = ("NI_OCC", "NI_PLAN", "INT_OCC", "INT_PLAN")
TEMPLATE_SUBCLASSES: tuple[str, ...] = ("A_plan_task", "A_plan_deg", "A_pure")
MACRO_SUBCLASSES: tuple[str, ...] = ("A_plan", "A_pure")

MIN_DISTINCT_DRAWS = 20
TOL_DUST = 1e-12


def _compute_bessel_t_factors_high_precision(
    ns: tuple[int, ...] = (8, 12, 16, 20, 64, 79, 80),
) -> dict[int, float]:
    """Compute c_n = sqrt(n/(n-1)) * t_{n-1, 0.99375} / z_{0.99375} in 70-digit Decimal arithmetic."""
    getcontext().prec = 70
    pi_d = Decimal("3.1415926535897932384626433832795028841971693993751058209749445923078164")

    def dec_exp(x: Decimal) -> Decimal:
        return x.exp()

    def dec_ln(x: Decimal) -> Decimal:
        return x.ln()

    def dec_sqrt(x: Decimal) -> Decimal:
        return x.sqrt()

    def erf_dec(x: Decimal) -> Decimal:
        s = Decimal(0)
        x2 = x * x
        term = x
        for n in range(220):
            if n > 0:
                term = -term * x2 / Decimal(n)
            contrib = term / Decimal(2 * n + 1)
            s += contrib
            if abs(contrib) < Decimal("1e-62"):
                break
        return s * Decimal(2) / dec_sqrt(pi_d)

    def norm_cdf_dec(z: Decimal) -> Decimal:
        return Decimal("0.5") * (Decimal(1) + erf_dec(z / dec_sqrt(Decimal(2))))

    g_coef = [
        Decimal("0.99999999999980993227684700473478"),
        Decimal("676.520368121885098567009190444019"),
        Decimal("-1259.13921672240287047156078755283"),
        Decimal("771.3234287776530788486528258894"),
        Decimal("-176.61502916214059906584551354"),
        Decimal("12.507343278686904814458936853"),
        Decimal("-0.13857109526572011689554707"),
        Decimal("9.984369578019570859563e-6"),
        Decimal("1.50563273514931155834e-7"),
    ]

    def lgamma_dec(z: Decimal) -> Decimal:
        z_m1 = z - Decimal(1)
        x = g_coef[0]
        for i in range(1, len(g_coef)):
            x += g_coef[i] / (z_m1 + Decimal(i))
        t = z_m1 + Decimal("7.5")
        return Decimal("0.5") * dec_ln(Decimal(2) * pi_d) + (z_m1 + Decimal("0.5")) * dec_ln(t) - t + dec_ln(x)

    def betainc_reg_dec(a: Decimal, b: Decimal, x: Decimal) -> Decimal:
        ln_beta = lgamma_dec(a) + lgamma_dec(b) - lgamma_dec(a + b)
        front = dec_exp(a * dec_ln(x) + b * dec_ln(Decimal(1) - x) - ln_beta) / a
        f = Decimal(1)
        c = Decimal(1)
        d = Decimal(1) - (a + b) * x / (a + Decimal(1))
        if abs(d) < Decimal("1e-60"):
            d = Decimal("1e-60")
        d = Decimal(1) / d
        h = d
        for m in range(1, 250):
            m_d = Decimal(m)
            num1 = m_d * (b - m_d) * x / ((a + Decimal(2) * m_d - Decimal(1)) * (a + Decimal(2) * m_d))
            d = Decimal(1) + num1 * d
            if abs(d) < Decimal("1e-60"):
                d = Decimal("1e-60")
            c = Decimal(1) + num1 / c
            if abs(c) < Decimal("1e-60"):
                c = Decimal("1e-60")
            d = Decimal(1) / d
            h *= d * c
            num2 = -(a + m_d) * (a + b + m_d) * x / ((a + Decimal(2) * m_d) * (a + Decimal(2) * m_d + Decimal(1)))
            d = Decimal(1) + num2 * d
            if abs(d) < Decimal("1e-60"):
                d = Decimal("1e-60")
            c = Decimal(1) + num2 / c
            if abs(c) < Decimal("1e-60"):
                c = Decimal("1e-60")
            d = Decimal(1) / d
            delta = d * c
            h *= delta
            if abs(delta - Decimal(1)) < Decimal("1e-55"):
                break
        return front * h

    def t_cdf_pos(t_val: Decimal, df_int: int) -> Decimal:
        df_d = Decimal(df_int)
        x = df_d / (df_d + t_val * t_val)
        ib = betainc_reg_dec(df_d / Decimal(2), Decimal("0.5"), x)
        return Decimal(1) - Decimal("0.5") * ib

    target = Decimal("0.99375")  # 1 - 0.0125 / 2
    lo, hi = Decimal("2.4"), Decimal("2.6")
    for _ in range(200):
        mid = (lo + hi) / Decimal(2)
        if norm_cdf_dec(mid) < target:
            lo = mid
        else:
            hi = mid
    z_q = (lo + hi) / Decimal(2)

    out: dict[int, float] = {}
    for n in ns:
        df = n - 1
        lo_t, hi_t = Decimal("2.0"), Decimal("5.0")
        for _ in range(200):
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
    79: 1.0302596947224958,
    64: 1.037660015052903,
    20: 1.1331397732007173,
    16: 1.1729390393815105,
    12: 1.2465119462060201,
    8: 1.4275423213691008,
}

BESSEL_T_FACTORS_BY_N: dict[int, float] = _compute_bessel_t_factors_high_precision()
for _n_k, _exp_c in EXPECTED_BESSEL_T_FACTORS.items():
    if abs(BESSEL_T_FACTORS_BY_N[_n_k] - _exp_c) > 1e-15:
        raise RuntimeError(
            f"Bessel-t factor mismatch for n={_n_k}: {BESSEL_T_FACTORS_BY_N[_n_k]} != {_exp_c}"
        )


def _order_stat_indices(b: int, alpha_two_sided: float) -> tuple[int, int]:
    """Uninterpolated 0-based order-statistic indices (PLAN-E3.md §4.2(2)).

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


def draw_cluster_bootstrap_weights_e3(
    n: int,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E3,
) -> np.ndarray:
    """Draw equal-weight multinomial cluster bootstrap weight matrix `w` (`(B, n)`) on a single PCG64 stream."""
    rng = np.random.Generator(np.random.PCG64(seed))
    return rng.multinomial(n, np.full(n, 1.0 / n), size=b).astype(np.float64) / float(n)


def draw_all_bootstrap_weights_e3(
    n_all: int,
    n_aplan: int,
    n_apure: int,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Draw `w_all`, `w_aplan`, and `w_apure` sequentially on a single shared PCG64 stream (`PLAN-E3.md` §4.2(1))."""
    rng = np.random.Generator(np.random.PCG64(seed))
    w_all = rng.multinomial(n_all, np.full(n_all, 1.0 / n_all), size=b).astype(np.float64) / float(n_all)
    w_aplan = (
        rng.multinomial(n_aplan, np.full(n_aplan, 1.0 / n_aplan), size=b).astype(np.float64) / float(n_aplan)
        if n_aplan > 0
        else np.zeros((b, 0), dtype=np.float64)
    )
    w_apure = (
        rng.multinomial(n_apure, np.full(n_apure, 1.0 / n_apure), size=b).astype(np.float64) / float(n_apure)
        if n_apure > 0
        else np.zeros((b, 0), dtype=np.float64)
    )
    return w_all, w_aplan, w_apure


def infer_continuous_slot_e3(
    d_lower: np.ndarray,
    d_upper: np.ndarray,
    w_mat: np.ndarray,
    method: str = "pct",
    domain_bounds: tuple[float, float] = (-100.0, 100.0),
) -> dict[str, Any]:
    """Evaluate one-sided (`H0: theta <= 0` vs `H1: theta > 0`) continuous paired contrast (`E3_H1..E3_H3`).

    Enforces all 4 pre-clipping degeneracy rules from `PLAN-E3.md` §4.2(2):
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


def infer_discrete_slot_e3(
    d_lower: np.ndarray,
    d_upper: np.ndarray,
    one_sided: bool = True,
) -> dict[str, Any]:
    """Evaluate `E3_H4` (`Pr(True on NI_OCC; L/CoT) - Pr(True on NI_PLAN; L/CoT)`) via certified exact Tango."""
    res = exact_tango_e3.infer_exact_tango_slot(
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


def holm_step_down_e3(
    p_values: dict[str, float],
    alpha_family: float = ALPHA_FAMILY,
    slot_order: tuple[str, ...] = E3_SLOT_ORDER,
) -> dict[str, dict[str, Any]]:
    """Holm step-down (`m = 4, alpha_fam = 0.05`) with deterministic tie-breaking by `E3_H1..E3_H4`."""
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


def evaluate_four_slot_family_e3(
    inputs: dict[str, tuple[np.ndarray, np.ndarray]],
    w_all: np.ndarray,
    continuous_method: str = "pct",
    demoted_slots: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Run all 4 confirmatory slots (`E3_H1..E3_H4`) and Holm step-down (`m = 4`).

    If any continuous slot is in `demoted_slots` (per Step 3 of `PLAN-E3.md` §4.2(5)),
    it is demoted from confirmatory to descriptive while keeping `m = 4` denominator
    (`alpha_ind = 0.0125`, `Holm` denominators `4, 3, 2, 1` with demoted slot fixed at `p = 1.0`).
    """
    demoted_set = set(demoted_slots)
    slots_out: dict[str, dict[str, Any]] = {}
    for slot in CONTINUOUS_SLOTS:
        d_lo, d_hi = inputs[slot]
        res = infer_continuous_slot_e3(d_lo, d_hi, w_all, method=continuous_method)
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

    d4_lo, d4_hi = inputs["E3_H4"]
    res_h4 = infer_discrete_slot_e3(d4_lo, d4_hi, one_sided=True)
    res_h4["demoted_to_descriptive"] = False
    slots_out["E3_H4"] = res_h4

    p_map = {s: slots_out[s]["p"] for s in E3_SLOT_ORDER}
    holm = holm_step_down_e3(p_map, alpha_family=ALPHA_FAMILY, slot_order=E3_SLOT_ORDER)
    for s in E3_SLOT_ORDER:
        slots_out[s]["holm"] = holm[s]

    return {
        "family_name": "hybrid_pct_tango_e3" if continuous_method == "pct" else "hybrid_bessel_t_tango_e3",
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


def extract_primary_inputs_from_records_e3(
    records: list[dict[str, Any]],
    cluster_ids: list[str],
    allow_missing_score_for_h4: bool = False,
) -> dict[str, Any]:
    """Extract worst-case bounded cluster difference vectors for `E3_H1..E3_H4` on a sorted cluster subset."""
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

    complete_masks = {s: np.zeros(n, dtype=bool) for s in E3_SLOT_ORDER}
    missing_units = {s: 0 for s in E3_SLOT_ORDER}

    for i, cid in enumerate(cids_sorted):
        # E3_H1: NI_OCC(P/Z) - NI_PLAN(P/Z)
        occ_lo, occ_hi, ok_occ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_OCC", "P", "Z")
        pln_lo, pln_hi, ok_pln = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_PLAN", "P", "Z")
        h1_lo[i] = occ_lo - pln_hi
        h1_hi[i] = occ_hi - pln_lo
        complete_masks["E3_H1"][i] = ok_occ and ok_pln
        missing_units["E3_H1"] += int(not ok_occ) + int(not ok_pln)

        # E3_H2: INT_OCC(P/Z) - INT_PLAN(P/Z)
        iocc_lo, iocc_hi, ok_iocc = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_OCC", "P", "Z")
        ipln_lo, ipln_hi, ok_ipln = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_PLAN", "P", "Z")
        h2_lo[i] = iocc_lo - ipln_hi
        h2_hi[i] = iocc_hi - ipln_lo
        complete_masks["E3_H2"][i] = ok_iocc and ok_ipln
        missing_units["E3_H2"] += int(not ok_iocc) + int(not ok_ipln)

        # E3_H3: NI_PLAN(M_U/CoT) - INT_PLAN(M_U/CoT)
        m_ni_lo, m_ni_hi, ok_m_ni = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "NI_PLAN", "M", "CoT", use_unweighted_m=True
        )
        m_int_lo, m_int_hi, ok_m_int = _extract_continuous_bounds(
            by_tuple, by_uk, cid, "INT_PLAN", "M", "CoT", use_unweighted_m=True
        )
        h3_lo[i] = m_ni_lo - m_int_hi
        h3_hi[i] = m_ni_hi - m_int_lo
        complete_masks["E3_H3"][i] = ok_m_ni and ok_m_int
        missing_units["E3_H3"] += int(not ok_m_ni) + int(not ok_m_int)

        # E3_H4: I(NI_OCC == True; L/CoT) - I(NI_PLAN == True; L/CoT)
        l_occ_lo, l_occ_hi, ok_l_occ = _extract_label_true_bounds(
            by_tuple, by_uk, cid, "NI_OCC", "L", "CoT", allow_missing_score=allow_missing_score_for_h4
        )
        l_pln_lo, l_pln_hi, ok_l_pln = _extract_label_true_bounds(
            by_tuple, by_uk, cid, "NI_PLAN", "L", "CoT", allow_missing_score=allow_missing_score_for_h4
        )
        h4_lo[i] = l_occ_lo - l_pln_hi
        h4_hi[i] = l_occ_hi - l_pln_lo
        complete_masks["E3_H4"][i] = ok_l_occ and ok_l_pln
        missing_units["E3_H4"] += int(not ok_l_occ) + int(not ok_l_pln)

    return {
        "cluster_ids": cids_sorted,
        "inputs": {
            "E3_H1": (h1_lo, h1_hi),
            "E3_H2": (h2_lo, h2_hi),
            "E3_H3": (h3_lo, h3_hi),
            "E3_H4": (h4_lo, h4_hi),
        },
        "complete_masks": complete_masks,
        "complete_cluster_counts": {s: int(np.sum(complete_masks[s])) for s in E3_SLOT_ORDER},
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


def _summarize_condition_four_slots(
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
        nio_lo, nio_hi = slot_bounds["NI_OCC"]
        nip_lo, nip_hi = slot_bounds["NI_PLAN"]
        io_lo, io_hi = slot_bounds["INT_OCC"]
        ip_lo, ip_hi = slot_bounds["INT_PLAN"]
        out["paired_contrasts"] = {
            "NI_OCC_minus_NI_PLAN": _paired_summary_ci95(nio_lo - nip_hi, nio_hi - nip_lo, w_mat),
            "INT_OCC_minus_INT_PLAN": _paired_summary_ci95(io_lo - ip_hi, io_hi - ip_lo, w_mat),
            "NI_PLAN_minus_INT_PLAN": _paired_summary_ci95(nip_lo - ip_hi, nip_hi - ip_lo, w_mat),
            "NI_OCC_minus_INT_OCC": _paired_summary_ci95(nio_lo - io_hi, nio_hi - io_lo, w_mat),
            "interaction_NI_diff_minus_INT_diff": _paired_summary_ci95(
                (nio_lo - nip_hi) - (io_hi - ip_lo),
                (nio_hi - nip_lo) - (io_lo - ip_hi),
                w_mat,
            ),
        }
    return out


def _summarize_diagnostic_contexts(
    by_tuple: dict[tuple[str, str, str, str], dict[str, Any]],
    by_uk: dict[str, dict[str, Any]],
    by_cid: dict[str, dict[str, Any]],
    cids: list[str],
) -> dict[str, Any]:
    """Summarize diagnostic context performance (`DIAG_POS` vs `DIAG_NEG` on `L/Z`, `P/Z`, `M/Z`) overall and by `template_subclass` (`PLAN-E3.md` §2.2(5))."""
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
                    "template_subclass": by_cid[cid]["template_subclass"],
                    "macro_subclass": by_cid[cid]["macro_subclass"],
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
        "by_template_subclass": {
            tsub: _eval_group([c for c in cids if by_cid[c]["template_subclass"] == tsub])
            for tsub in TEMPLATE_SUBCLASSES
        },
        "by_macro_subclass": {
            msub: _eval_group([c for c in cids if by_cid[c]["macro_subclass"] == msub])
            for msub in MACRO_SUBCLASSES
        },
    }


def analyze_stage_records_e3(
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
    exp1_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run complete confirmatory + companion + Layer 3 analysis for `dev` or `formal` stage (`PLAN-E3.md` §4)."""
    if seed is None:
        seed = FORMAL_ANALYSIS_SEED_E3 if stage == "formal" else DEV_ANALYSIS_SEED_E3
    if calibration_lock is not None:
        if calibration_lock.get("status") != "pass":
            raise ValueError("calibration_lock status must be 'pass'")
        sel_fam = calibration_lock.get("selected_family")
        if sel_fam not in ("hybrid_pct_tango_e3", "hybrid_bessel_t_tango_e3"):
            raise ValueError(f"Invalid selected_family in calibration_lock: {sel_fam!r}")
        if primary_method is None:
            primary_method = "pct" if sel_fam == "hybrid_pct_tango_e3" else "bessel_t"
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
    aplan_cids = sorted(cid for cid in all_cids if by_cid[cid]["macro_subclass"] == "A_plan")
    apure_cids = sorted(cid for cid in all_cids if by_cid[cid]["macro_subclass"] == "A_pure")
    aplan_task_cids = sorted(cid for cid in all_cids if by_cid[cid]["template_subclass"] == "A_plan_task")
    aplan_deg_cids = sorted(cid for cid in all_cids if by_cid[cid]["template_subclass"] == "A_plan_deg")

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

    # 1. Shared RNG stream for all n clusters, followed sequentially by A_plan and A_pure (`PLAN-E3.md` §4.2(1))
    w_all, w_aplan, w_apure = draw_all_bootstrap_weights_e3(
        len(all_cids), len(aplan_cids), len(apure_cids), b=b, seed=seed
    )

    ext_all = extract_primary_inputs_from_records_e3(records, all_cids, allow_missing_score_for_h4=False)
    companion_method = "bessel_t" if primary_method == "pct" else "pct"
    primary_family = evaluate_four_slot_family_e3(
        ext_all["inputs"], w_all, continuous_method=primary_method, demoted_slots=demoted_slots
    )
    companion_family = evaluate_four_slot_family_e3(
        ext_all["inputs"], w_all, continuous_method=companion_method, demoted_slots=demoted_slots
    )

    # E3_H4 companion row using `label_available` (`status in ("ok", "missing_score")`) (`PLAN-E3.md` §4.2(4))
    ext_lbl_avail = extract_primary_inputs_from_records_e3(records, all_cids, allow_missing_score_for_h4=True)
    h4_lbl_avail = infer_discrete_slot_e3(*ext_lbl_avail["inputs"]["E3_H4"], one_sided=True)
    h4_lbl_avail["missing_score_units_recovered"] = (
        ext_all["missing_units"]["E3_H4"] - ext_lbl_avail["missing_units"]["E3_H4"]
    )

    # 2. Mandatory parallel A_plan vs A_pure breakdown (`PLAN-E3.md` §2.1 & §4.1 & §4.3(1))
    ext_aplan = extract_primary_inputs_from_records_e3(records, aplan_cids, allow_missing_score_for_h4=False)
    ext_apure = extract_primary_inputs_from_records_e3(records, apure_cids, allow_missing_score_for_h4=False)

    def _eval_sub_family(ext_sub: dict[str, Any], w_sub: np.ndarray) -> dict[str, Any]:
        n_sub = len(ext_sub["cluster_ids"])
        slots_sub: dict[str, Any] = {}
        for s_slot in CONTINUOUS_SLOTS:
            d_lo_s, d_hi_s = ext_sub["inputs"][s_slot]
            slots_sub[s_slot] = {
                "pct": infer_continuous_slot_e3(d_lo_s, d_hi_s, w_sub, method="pct"),
                "bessel_t": (
                    infer_continuous_slot_e3(d_lo_s, d_hi_s, w_sub, method="bessel_t")
                    if n_sub in BESSEL_T_FACTORS_BY_N
                    else None
                ),
            }
        slots_sub["E3_H4"] = (
            infer_discrete_slot_e3(*ext_sub["inputs"]["E3_H4"], one_sided=True)
            if n_sub in exact_tango_e3.SUPPORTED_NS
            else None
        )
        return {
            "n_clusters": n_sub,
            "cluster_ids": ext_sub["cluster_ids"],
            "complete_cluster_counts": ext_sub["complete_cluster_counts"],
            "missing_units": ext_sub["missing_units"],
            "slots": slots_sub,
        }

    aplan_parallel = _eval_sub_family(ext_aplan, w_aplan)
    apure_parallel = _eval_sub_family(ext_apure, w_apure)

    # Between-subclass difference A_plan minus A_pure on E3_H1..E3_H4
    between_subclass_diff: dict[str, Any] = {}
    if len(aplan_cids) > 0 and len(apure_cids) > 0:
        idx_lo_95, idx_hi_95 = _order_stat_indices(b, ALPHA_FAMILY)
        for s_slot in CONTINUOUS_SLOTS:
            ap_lo, ap_hi = ext_aplan["inputs"][s_slot]
            au_lo, au_hi = ext_apure["inputs"][s_slot]
            diff_boot_lo = np.sort((w_aplan @ ap_lo) - (w_apure @ au_hi))
            diff_boot_hi = np.sort((w_aplan @ ap_hi) - (w_apure @ au_lo))
            between_subclass_diff[f"A_plan_minus_A_pure_{s_slot}"] = {
                "point_lower": float(np.mean(ap_lo) - np.mean(au_hi)),
                "point_upper": float(np.mean(ap_hi) - np.mean(au_lo)),
                "ci_95": [float(diff_boot_lo[idx_lo_95]), float(diff_boot_hi[idx_hi_95])],
            }
        ap4_lo, ap4_hi = ext_aplan["inputs"]["E3_H4"]
        au4_lo, au4_hi = ext_apure["inputs"]["E3_H4"]
        diff4_boot_lo = np.sort((w_aplan @ ap4_lo.astype(np.float64)) - (w_apure @ au4_hi.astype(np.float64)))
        diff4_boot_hi = np.sort((w_aplan @ ap4_hi.astype(np.float64)) - (w_apure @ au4_lo.astype(np.float64)))
        between_subclass_diff["A_plan_minus_A_pure_E3_H4"] = {
            "point_lower": float(np.mean(ap4_lo) - np.mean(au4_hi)),
            "point_upper": float(np.mean(ap4_hi) - np.mean(au4_lo)),
            "ci_95": [float(diff4_boot_lo[idx_lo_95]), float(diff4_boot_hi[idx_hi_95])],
        }

    # Template subclass descriptive summaries (A_plan_task, A_plan_deg, A_pure)
    rng_tpl = np.random.Generator(np.random.PCG64(seed + 100))
    template_subclass_summary: dict[str, Any] = {}
    for tsub in TEMPLATE_SUBCLASSES:
        t_cids = sorted(cid for cid in all_cids if by_cid[cid]["template_subclass"] == tsub)
        n_t = len(t_cids)
        w_t = (
            rng_tpl.multinomial(n_t, np.full(n_t, 1.0 / n_t), size=b).astype(np.float64) / float(n_t)
            if n_t > 0
            else None
        )
        ext_t = extract_primary_inputs_from_records_e3(records, t_cids, allow_missing_score_for_h4=False)
        template_subclass_summary[tsub] = {
            "n_clusters": n_t,
            "cluster_ids": t_cids,
            "E3_H1_summary": _paired_summary_ci95(*ext_t["inputs"]["E3_H1"], w_t),
            "E3_H2_summary": _paired_summary_ci95(*ext_t["inputs"]["E3_H2"], w_t),
            "E3_H3_summary": _paired_summary_ci95(*ext_t["inputs"]["E3_H3"], w_t),
            "E3_H4_summary": _paired_summary_ci95(
                ext_t["inputs"]["E3_H4"][0].astype(np.float64),
                ext_t["inputs"]["E3_H4"][1].astype(np.float64),
                w_t,
            ),
            "conditions_13_four_slots": {
                f"{tk}/{pr}": _summarize_condition_four_slots(by_tuple, by_uk, t_cids, tk, pr, w_t)
                for tk, pr in COMBINATIONS
            },
        }

    # 3. Layer 3 Item 3: 79-cluster sensitivity check excluding cluster "095" (`PLAN-E3.md` §4.3(3))
    layer3_sens79_excluding_095: dict[str, Any] | None = None
    if "095" in all_cids:
        cids_79 = [c for c in all_cids if c != "095"]
        if len(cids_79) in BESSEL_T_FACTORS_BY_N and len(cids_79) in exact_tango_e3.SUPPORTED_NS:
            w_79 = draw_cluster_bootstrap_weights_e3(len(cids_79), b=b, seed=SENS79_ANALYSIS_SEED_E3)
            ext_79 = extract_primary_inputs_from_records_e3(records, cids_79, allow_missing_score_for_h4=False)
            layer3_sens79_excluding_095 = {
                "seed": SENS79_ANALYSIS_SEED_E3,
                "n_clusters": len(cids_79),
                "excluded_cluster_id": "095",
                "primary_family": evaluate_four_slot_family_e3(
                    ext_79["inputs"], w_79, continuous_method=primary_method, demoted_slots=demoted_slots
                ),
                "companion_family": evaluate_four_slot_family_e3(
                    ext_79["inputs"], w_79, continuous_method=companion_method, demoted_slots=demoted_slots
                ),
            }

    # 4. Layer 3 Item 2: Within-E3 D_k vs B_k contrasts & optional Experiment 1 same-cluster paired comparison (`PLAN-E3.md` §4.3(2))
    # Compute NI_OCC - INT_OCC (h_occ under D_k vs B_k), NI_PLAN - INT_PLAN (h_plan under D_k vs B_k),
    # and the 2x2 interaction (NI_OCC - NI_PLAN) - (INT_OCC - INT_PLAN) across key conditions.
    within_e3_dk_minus_bk: dict[str, Any] = {}
    for tk, pr, use_u, label_key in (
        ("P", "Z", False, "P/Z"),
        ("P", "CoT", False, "P/CoT"),
        ("M", "Z", True, "M_U/Z"),
        ("M", "CoT", True, "M_U/CoT"),
        ("M", "CoT", False, "M_W/CoT"),
    ):
        nio_lo, nio_hi = [], []
        nip_lo, nip_hi = [], []
        io_lo, io_hi = [], []
        ip_lo, ip_hi = [], []
        for cid in all_cids:
            v1_lo, v1_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_OCC", tk, pr, use_unweighted_m=use_u)
            v2_lo, v2_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_PLAN", tk, pr, use_unweighted_m=use_u)
            v3_lo, v3_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_OCC", tk, pr, use_unweighted_m=use_u)
            v4_lo, v4_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_PLAN", tk, pr, use_unweighted_m=use_u)
            nio_lo.append(v1_lo)
            nio_hi.append(v1_hi)
            nip_lo.append(v2_lo)
            nip_hi.append(v2_hi)
            io_lo.append(v3_lo)
            io_hi.append(v3_hi)
            ip_lo.append(v4_lo)
            ip_hi.append(v4_hi)
        a_nio_lo, a_nio_hi = np.array(nio_lo), np.array(nio_hi)
        a_nip_lo, a_nip_hi = np.array(nip_lo), np.array(nip_hi)
        a_io_lo, a_io_hi = np.array(io_lo), np.array(io_hi)
        a_ip_lo, a_ip_hi = np.array(ip_lo), np.array(ip_hi)
        within_e3_dk_minus_bk[label_key] = {
            "h_occ_NI_OCC_minus_INT_OCC": _paired_summary_ci95(a_nio_lo - a_io_hi, a_nio_hi - a_io_lo, w_all),
            "h_plan_NI_PLAN_minus_INT_PLAN": _paired_summary_ci95(a_nip_lo - a_ip_hi, a_nip_hi - a_ip_lo, w_all),
            "interaction_NI_diff_minus_INT_diff": _paired_summary_ci95(
                (a_nio_lo - a_nip_hi) - (a_io_hi - a_ip_lo),
                (a_nio_hi - a_nip_lo) - (a_io_lo - a_ip_hi),
                w_all,
            ),
        }

    exp1_paired_contrasts: dict[str, Any] = {}
    if exp1_records:
        e1_by_uk = {r["unit_key"]: r for r in exp1_records if "unit_key" in r}
        for tk, pr in COMBINATIONS:
            cond_key = f"{tk}/{pr}"
            if tk == "L":
                d_nio_lo, d_nio_hi, d_nip_lo, d_nip_hi = [], [], [], []
                b_io_lo, b_io_hi, b_ip_lo, b_ip_hi = [], [], [], []
                for cid in all_cids:
                    r_d = e1_by_uk.get(f"D_{cid}/{tk}/{pr}")
                    d_ok = r_d is not None and r_d.get("status") == "ok" and r_d.get("label") in ("True", "False", "Unknown")
                    d_lo = (100.0 if r_d["label"] == "True" else 0.0) if d_ok else 0.0
                    d_hi = (100.0 if r_d["label"] == "True" else 0.0) if d_ok else 100.0

                    r_b = e1_by_uk.get(f"B_{cid}/{tk}/{pr}")
                    b_ok = r_b is not None and r_b.get("status") == "ok" and r_b.get("label") in ("True", "False", "Unknown")
                    b_lo = (100.0 if r_b["label"] == "True" else 0.0) if b_ok else 0.0
                    b_hi = (100.0 if r_b["label"] == "True" else 0.0) if b_ok else 100.0

                    l_nio_lo, l_nio_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "NI_OCC", tk, pr)
                    l_nip_lo, l_nip_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "NI_PLAN", tk, pr)
                    l_io_lo, l_io_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "INT_OCC", tk, pr)
                    l_ip_lo, l_ip_hi, _ = _extract_label_true_bounds(by_tuple, by_uk, cid, "INT_PLAN", tk, pr)

                    d_nio_lo.append(100.0 * l_nio_lo - d_hi)
                    d_nio_hi.append(100.0 * l_nio_hi - d_lo)
                    d_nip_lo.append(100.0 * l_nip_lo - d_hi)
                    d_nip_hi.append(100.0 * l_nip_hi - d_lo)
                    b_io_lo.append(100.0 * l_io_lo - b_hi)
                    b_io_hi.append(100.0 * l_io_hi - b_lo)
                    b_ip_lo.append(100.0 * l_ip_lo - b_hi)
                    b_ip_hi.append(100.0 * l_ip_hi - b_lo)
                exp1_paired_contrasts[cond_key] = {
                    "NI_OCC_minus_D_orig_true_pct": _paired_summary_ci95(np.array(d_nio_lo), np.array(d_nio_hi), w_all),
                    "NI_PLAN_minus_D_orig_true_pct": _paired_summary_ci95(np.array(d_nip_lo), np.array(d_nip_hi), w_all),
                    "INT_OCC_minus_B_orig_true_pct": _paired_summary_ci95(np.array(b_io_lo), np.array(b_io_hi), w_all),
                    "INT_PLAN_minus_B_orig_true_pct": _paired_summary_ci95(np.array(b_ip_lo), np.array(b_ip_hi), w_all),
                }
            else:
                d_nio_lo, d_nio_hi, d_nip_lo, d_nip_hi = [], [], [], []
                b_io_lo, b_io_hi, b_ip_lo, b_ip_hi = [], [], [], []
                d_nio_u_lo, d_nio_u_hi, d_nip_u_lo, d_nip_u_hi = [], [], [], []
                b_io_u_lo, b_io_u_hi, b_ip_u_lo, b_ip_u_hi = [], [], [], []
                for cid in all_cids:
                    r_d = e1_by_uk.get(f"D_{cid}/{tk}/{pr}")
                    d_ok = r_d is not None and r_d.get("status") == "ok" and r_d.get("value") is not None
                    d_lo = float(r_d["value"]) if d_ok else 0.0
                    d_hi = float(r_d["value"]) if d_ok else 100.0

                    r_b = e1_by_uk.get(f"B_{cid}/{tk}/{pr}")
                    b_ok = r_b is not None and r_b.get("status") == "ok" and r_b.get("value") is not None
                    b_lo = float(r_b["value"]) if b_ok else 0.0
                    b_hi = float(r_b["value"]) if b_ok else 100.0

                    nio_lo, nio_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_OCC", tk, pr)
                    nip_lo, nip_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_PLAN", tk, pr)
                    io_lo, io_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_OCC", tk, pr)
                    ip_lo, ip_hi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_PLAN", tk, pr)

                    d_nio_lo.append(nio_lo - d_hi)
                    d_nio_hi.append(nio_hi - d_lo)
                    d_nip_lo.append(nip_lo - d_hi)
                    d_nip_hi.append(nip_hi - d_lo)
                    b_io_lo.append(io_lo - b_hi)
                    b_io_hi.append(io_hi - b_lo)
                    b_ip_lo.append(ip_lo - b_hi)
                    b_ip_hi.append(ip_hi - b_lo)

                    if tk == "M":
                        d_ests = (r_d.get("parsed") or {}).get("estimates") if r_d else None
                        d_mu = (
                            float(r_d["mu_value"])
                            if (r_d and r_d.get("status") == "ok" and r_d.get("mu_value") is not None)
                            else (
                                sum(float(x) for x in d_ests) / 5.0
                                if (r_d and r_d.get("status") == "ok" and isinstance(d_ests, list) and len(d_ests) == 5)
                                else None
                            )
                        )
                        du_lo = d_mu if d_mu is not None else 0.0
                        du_hi = d_mu if d_mu is not None else 100.0

                        b_ests = (r_b.get("parsed") or {}).get("estimates") if r_b else None
                        b_mu = (
                            float(r_b["mu_value"])
                            if (r_b and r_b.get("status") == "ok" and r_b.get("mu_value") is not None)
                            else (
                                sum(float(x) for x in b_ests) / 5.0
                                if (r_b and r_b.get("status") == "ok" and isinstance(b_ests, list) and len(b_ests) == 5)
                                else None
                            )
                        )
                        bu_lo = b_mu if b_mu is not None else 0.0
                        bu_hi = b_mu if b_mu is not None else 100.0

                        nio_ulo, nio_uhi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_OCC", tk, pr, use_unweighted_m=True)
                        nip_ulo, nip_uhi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "NI_PLAN", tk, pr, use_unweighted_m=True)
                        io_ulo, io_uhi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_OCC", tk, pr, use_unweighted_m=True)
                        ip_ulo, ip_uhi, _ = _extract_continuous_bounds(by_tuple, by_uk, cid, "INT_PLAN", tk, pr, use_unweighted_m=True)

                        d_nio_u_lo.append(nio_ulo - du_hi)
                        d_nio_u_hi.append(nio_uhi - du_lo)
                        d_nip_u_lo.append(nip_ulo - du_hi)
                        d_nip_u_hi.append(nip_uhi - du_lo)
                        b_io_u_lo.append(io_ulo - bu_hi)
                        b_io_u_hi.append(io_uhi - bu_lo)
                        b_ip_u_lo.append(ip_ulo - bu_hi)
                        b_ip_u_hi.append(ip_uhi - bu_lo)

                entry_cond: dict[str, Any] = {
                    "NI_OCC_minus_D_orig": _paired_summary_ci95(np.array(d_nio_lo), np.array(d_nio_hi), w_all),
                    "NI_PLAN_minus_D_orig": _paired_summary_ci95(np.array(d_nip_lo), np.array(d_nip_hi), w_all),
                    "INT_OCC_minus_B_orig": _paired_summary_ci95(np.array(b_io_lo), np.array(b_io_hi), w_all),
                    "INT_PLAN_minus_B_orig": _paired_summary_ci95(np.array(b_ip_lo), np.array(b_ip_hi), w_all),
                }
                if tk == "M":
                    entry_cond.update({
                        "NI_OCC_minus_D_orig_MU": _paired_summary_ci95(np.array(d_nio_u_lo), np.array(d_nio_u_hi), w_all),
                        "NI_PLAN_minus_D_orig_MU": _paired_summary_ci95(np.array(d_nip_u_lo), np.array(d_nip_u_hi), w_all),
                        "INT_OCC_minus_B_orig_MU": _paired_summary_ci95(np.array(b_io_u_lo), np.array(b_io_u_hi), w_all),
                        "INT_PLAN_minus_B_orig_MU": _paired_summary_ci95(np.array(b_ip_u_lo), np.array(b_ip_u_hi), w_all),
                    })
                exp1_paired_contrasts[cond_key] = entry_cond

    # 5. Layer 3 Item 4: All 13 conditions 4-slot matrix, M_W - M_U bias, and L tri-label + q table
    all_13_conditions: dict[str, Any] = {}
    for tk, pr in COMBINATIONS:
        cond_key = f"{tk}/{pr}"
        all_13_conditions[cond_key] = {
            "all": _summarize_condition_four_slots(by_tuple, by_uk, all_cids, tk, pr, w_all),
            "A_plan": _summarize_condition_four_slots(by_tuple, by_uk, aplan_cids, tk, pr, w_aplan),
            "A_pure": _summarize_condition_four_slots(by_tuple, by_uk, apure_cids, tk, pr, w_apure),
        }

    metalanguage_mw_minus_mu: dict[str, Any] = {}
    for pr in ("Z", "DAP", "CoT", "CF"):
        cond_key = f"M/{pr}"
        metalanguage_mw_minus_mu[cond_key] = {}
        for g_name, g_cids, w_g in (
            ("all", all_cids, w_all),
            ("A_plan", aplan_cids, w_aplan),
            ("A_pure", apure_cids, w_apure),
        ):
            mw_slot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            mu_slot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            within_slot_delta: dict[str, Any] = {}
            for slot in MAIN_SLOTS:
                w_lo, w_hi, u_lo, u_hi = [], [], [], []
                for cid in g_cids:
                    wl, wh, _ = _extract_continuous_bounds(
                        by_tuple, by_uk, cid, slot, "M", pr, use_unweighted_m=False
                    )
                    ul, uh, _ = _extract_continuous_bounds(
                        by_tuple, by_uk, cid, slot, "M", pr, use_unweighted_m=True
                    )
                    w_lo.append(wl)
                    w_hi.append(wh)
                    u_lo.append(ul)
                    u_hi.append(uh)
                arr_wl = np.array(w_lo, dtype=np.float64)
                arr_wh = np.array(w_hi, dtype=np.float64)
                arr_ul = np.array(u_lo, dtype=np.float64)
                arr_uh = np.array(u_hi, dtype=np.float64)
                mw_slot[slot] = (arr_wl, arr_wh)
                mu_slot[slot] = (arr_ul, arr_uh)
                within_slot_delta[slot] = _paired_summary_ci95(arr_wl - arr_uh, arr_wh - arr_ul, w_g)

            nio_wl, nio_wh = mw_slot["NI_OCC"]
            nip_wl, nip_wh = mw_slot["NI_PLAN"]
            ip_wl, ip_wh = mw_slot["INT_PLAN"]
            nio_ul, nio_uh = mu_slot["NI_OCC"]
            nip_ul, nip_uh = mu_slot["NI_PLAN"]
            ip_ul, ip_uh = mu_slot["INT_PLAN"]

            metalanguage_mw_minus_mu[cond_key][g_name] = {
                "within_slot_MW_minus_MU_summary": within_slot_delta,
                "NI_OCC_minus_NI_PLAN_MW": _paired_summary_ci95(nio_wl - nip_wh, nio_wh - nip_wl, w_g),
                "NI_OCC_minus_NI_PLAN_MU": _paired_summary_ci95(nio_ul - nip_uh, nio_uh - nip_ul, w_g),
                "NI_PLAN_minus_INT_PLAN_MW": _paired_summary_ci95(nip_wl - ip_wh, nip_wh - ip_wl, w_g),
                "NI_PLAN_minus_INT_PLAN_MU": _paired_summary_ci95(nip_ul - ip_uh, nip_uh - ip_ul, w_g),
                "delta_on_NI_PLAN_minus_INT_PLAN": _paired_summary_ci95(
                    (nip_wl - ip_wh) - (nip_uh - ip_ul),
                    (nip_wh - ip_wl) - (nip_ul - ip_uh),
                    w_g,
                ),
            }

    l_task_trilabel_and_q: dict[str, Any] = {}
    for pr in ("Z", "DAP", "CoT", "CF"):
        cond_key = f"L/{pr}"
        l_task_trilabel_and_q[cond_key] = {}
        for g_name, g_cids, w_g in (
            ("all", all_cids, w_all),
            ("A_plan", aplan_cids, w_aplan),
            ("A_pure", apure_cids, w_apure),
        ):
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

    return {
        "stage": stage,
        "seed": seed,
        "b": b,
        "n_all": len(all_cids),
        "n_A_plan": len(aplan_cids),
        "n_A_pure": len(apure_cids),
        "n_A_plan_task": len(aplan_task_cids),
        "n_A_plan_deg": len(aplan_deg_cids),
        "primary_method": primary_method,
        "demoted_slots": sorted(demoted_slots),
        "complete_cluster_counts": ext_all["complete_cluster_counts"],
        "missing_units": ext_all["missing_units"],
        "primary_family": primary_family,
        "companion_family": companion_family,
        "e3_h4_label_available_companion": h4_lbl_avail,
        "macro_subclass_parallel_breakdown": {
            "A_plan": aplan_parallel,
            "A_pure": apure_parallel,
            "between_subclass_differences": between_subclass_diff,
        },
        "diagnostic_context_breakdown": _summarize_diagnostic_contexts(by_tuple, by_uk, by_cid, all_cids),
        "layer3_subclass_decomposition": {
            "A_plan": {
                **aplan_parallel,
                "conditions_13_four_slots": {
                    f"{tk}/{pr}": _summarize_condition_four_slots(by_tuple, by_uk, aplan_cids, tk, pr, w_aplan)
                    for tk, pr in COMBINATIONS
                },
            },
            "A_pure": {
                **apure_parallel,
                "conditions_13_four_slots": {
                    f"{tk}/{pr}": _summarize_condition_four_slots(by_tuple, by_uk, apure_cids, tk, pr, w_apure)
                    for tk, pr in COMBINATIONS
                },
            },
            "template_subclasses": template_subclass_summary,
            "between_subclass_differences": between_subclass_diff,
        },
        "layer3_sens79_excluding_095": layer3_sens79_excluding_095,
        "layer3_exp1_and_dk_bk_comparison": {
            "within_e3_dk_minus_bk": within_e3_dk_minus_bk,
            "exp1_same_cluster_paired_contrasts": exp1_paired_contrasts,
        },
        "layer3_all_13_conditions_four_slots": all_13_conditions,
        "layer3_metalanguage_mw_minus_mu": metalanguage_mw_minus_mu,
        "layer3_l_task_trilabel_and_q_table": l_task_trilabel_and_q,
    }
