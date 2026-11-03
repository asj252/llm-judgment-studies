"""Statistical Inference Core for Experiment 2 (Chinese): Scheme E2 (4-Slot Hybrid Bootstrap + Exact Tango).

Implements PLAN-E2.md (v0.6) §4.1–§4.3:
- 2-macro-class (`telic` n_T = 48 formal / 12 dev; `atelic` n_A = 32 formal / 8 dev) multinomial
  cluster bootstrap (B = 5000, FORMAL_ANALYSIS_SEED_E2 = 2026110301, DEV_ANALYSIS_SEED_E2 = 2026110302);
- Candidate 1 (`hybrid_pct_tango_e2`): uninterpolated order-statistic percentile bootstrap
  (`idx_lo = 31, idx_hi = 4968` for 98.75% CI; `124, 4875` for 95% CI) on `E2_H1..E2_H3`
  + certified unconditional exact Tango (1998) score test & CI on `E2_H4`;
- Candidate 2 / Companion (`hybrid_bessel_t_tango_e2`): order-preserving outward Bessel-t
  expansion around observed endpoints by 70-digit Decimal factor c_n on the identical bootstrap
  draw stream for `E2_H1..E2_H3` + certified exact Tango on `E2_H4`;
- Greedy-anchor distinct count (`_greedy_distinct_1d_sorted`, `TOL_DUST = 1e-12`) and all 4
  degeneracy rules evaluated BEFORE clipping to `[-100.0, 100.0]`;
- Worst-case missingness bound propagation (`status == "ok"` primary rule + `label_available`
  companion diagnostic for `E2_H4`) and `m = 4` Holm step-down procedure (alpha_fam = 0.05);
- Layer 3 descriptive & exploratory analyses (`A_plan` vs `A_pure` decomposition, cross-class
  shared-form `h_bare` and `完`-complement comparisons, and 13-condition summary matrix).
"""
import os

SINGLE_THREAD_ENV_VARS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
for _env_k in SINGLE_THREAD_ENV_VARS:
    os.environ.setdefault(_env_k, "1")

from decimal import Decimal, getcontext
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import numpy as np

from exact_tango_e2 import (
    DEFAULT_TABLES_NPZ,
    SUPPORTED_NS,
    infer_exact_tango_slot,
    load_certified_tango_tables,
    verify_ieee754_rn_and_subnormals,
)

B_DEFAULT = 5000
FORMAL_ANALYSIS_SEED_E2 = 2026110301
DEV_ANALYSIS_SEED_E2 = 2026110302

ALPHA_FAM = 0.05
M_SLOTS = 4
ALPHA_IND = ALPHA_FAM / M_SLOTS  # 0.0125 (two-sided 98.75% Bonferroni simultaneous CI)
ALPHA_COMPANION_95 = 0.05

TOL_DUST = 1e-12
MIN_UNIQUE_DRAWS = 20

E2_SLOT_ORDER: Tuple[str, ...] = ("E2_H1", "E2_H2", "E2_H3", "E2_H4")
CONT_SLOT_ORDER: Tuple[str, ...] = ("E2_H1", "E2_H2", "E2_H3")
DISC_SLOT_ORDER: Tuple[str, ...] = ("E2_H4",)

EXPECTED_BESSEL_T_FACTORS = {
    48: 1.0509502165481253,
    32: 1.0787284625848519,
    16: 1.1729390393815105,
    12: 1.2465119462060201,
    8: 1.4275423213691008,
}


def _dec_pi() -> Decimal:
    return Decimal("3.1415926535897932384626433832795028841971693993751058209749445923078164")


def _dec_erf(x: Decimal) -> Decimal:
    if x == 0:
        return Decimal(0)
    sign = -1 if x < 0 else 1
    x = abs(x)
    x2 = x * x
    term = x
    total = x
    n = 0
    while True:
        n += 1
        term = -term * x2 / Decimal(n)
        contrib = term / Decimal(2 * n + 1)
        total += contrib
        if abs(contrib) < Decimal("1e-62"):
            break
    val = sign * total * Decimal(2) / _dec_pi().sqrt()
    return max(Decimal(-1), min(Decimal(1), val))


def _dec_norm_cdf(z: Decimal) -> Decimal:
    return Decimal("0.5") * (Decimal(1) + _dec_erf(z / Decimal(2).sqrt()))


def _dec_student_t_cdf(t_val: Decimal, df: int) -> Decimal:
    if df < 1:
        raise ValueError(f"df must be >= 1, got {df}")
    if t_val == 0:
        return Decimal("0.5")
    sign = -1 if t_val < 0 else 1
    t_abs = abs(t_val)
    df_d = Decimal(df)
    u = t_abs / (t_abs * t_abs + df_d).sqrt()
    one_minus_u2 = df_d / (t_abs * t_abs + df_d)

    if df % 2 == 1:
        theta = Decimal(0)
        if df > 1:
            term = u
            s = term
            for k in range(1, (df - 1) // 2):
                term = term * one_minus_u2 * Decimal(2 * k) / Decimal(2 * k + 1)
                s += term
            integral = one_minus_u2.sqrt() * s
        else:
            integral = Decimal(0)
        # atan(t / sqrt(df)) via series on u = sin(atan(...))
        u2 = u * u
        at_term = u
        atan_val = u
        m = 0
        while True:
            m += 1
            at_term = at_term * u2 * Decimal(2 * m - 1) / Decimal(2 * m)
            contrib = at_term / Decimal(2 * m + 1)
            atan_val += contrib
            if abs(contrib) < Decimal("1e-62"):
                break
        theta = (atan_val + integral) * Decimal(2) / _dec_pi()
    else:
        term = Decimal(1)
        s = term
        for k in range(1, df // 2):
            term = term * one_minus_u2 * Decimal(2 * k - 1) / Decimal(2 * k)
            s += term
        theta = u * s

    p = Decimal("0.5") + Decimal(sign) * Decimal("0.5") * theta
    return max(Decimal(0), min(Decimal(1), p))


def _dec_bisect_quantile(cdf_fn, target_p: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    for _ in range(240):
        mid = Decimal("0.5") * (lo + hi)
        if cdf_fn(mid) < target_p:
            lo = mid
        else:
            hi = mid
    return Decimal("0.5") * (lo + hi)


def compute_bessel_t_expansion_factor(n: int, alpha_ind_str: str = "0.0125") -> float:
    """Compute exact 70-digit Decimal Bessel-t expansion factor c_n = sqrt(n/(n-1)) * t_{n-1, 1-a/2} / z_{1-a/2}."""
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n}")
    getcontext().prec = 70
    alpha_d = Decimal(alpha_ind_str)
    target_q = Decimal(1) - alpha_d / Decimal(2)
    df = n - 1
    z_q = _dec_bisect_quantile(_dec_norm_cdf, target_q, Decimal(0), Decimal(12))
    t_q = _dec_bisect_quantile(lambda x: _dec_student_t_cdf(x, df), target_q, Decimal(0), Decimal(25))
    bessel = (Decimal(n) / Decimal(n - 1)).sqrt()
    c_dec = bessel * (t_q / z_q)
    return float(c_dec)


BESSEL_T_FACTORS_BY_N: Dict[int, float] = {
    n: compute_bessel_t_expansion_factor(n, "0.0125") for n in SUPPORTED_NS
}
for _n_chk, _exp_c in EXPECTED_BESSEL_T_FACTORS.items():
    if abs(BESSEL_T_FACTORS_BY_N[_n_chk] - _exp_c) > 1e-15:
        raise AssertionError(
            f"Bessel-t constant mismatch for n={_n_chk}: got {BESSEL_T_FACTORS_BY_N[_n_chk]!r} != {_exp_c!r}"
        )


def _order_stat_indices(b: int, alpha: float) -> Tuple[int, int]:
    """Uninterpolated 0-based order statistic indices (idx_lo, idx_hi) matching core_a.py & PLAN-E2.md §4.2.2.

    For B = 5000:
    - alpha = 0.0125 (98.75% CI, single tail 0.00625): idx_lo = 31, idx_hi = 4968
    - alpha = 0.05   (95.00% CI, single tail 0.02500): idx_lo = 124, idx_hi = 4875
    """
    half_alpha = 0.5 * float(alpha)
    k_one_based = max(1, int(math.ceil(b * half_alpha)))
    idx_lo = k_one_based - 1
    idx_hi = b - k_one_based
    if not (0 <= idx_lo <= idx_hi < b):
        raise ValueError(f"Invalid order-statistic indices ({idx_lo}, {idx_hi}) for B={b}, alpha={alpha}")
    return idx_lo, idx_hi


def _greedy_distinct_1d_sorted(sorted_vals: np.ndarray) -> int:
    """Count distinct values in a 1D ascending-sorted array using greedy anchor tolerance TOL_DUST = 1e-12."""
    if len(sorted_vals) == 0:
        return 0
    if not np.all(np.isfinite(sorted_vals)):
        return 0
    c = 1
    anchor = float(sorted_vals[0])
    for v in sorted_vals[1:]:
        vf = float(v)
        if vf - anchor > TOL_DUST:
            c += 1
            anchor = vf
    return c


def draw_macro_bootstrap_weights_e2(
    n_t: int,
    n_a: int,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E2,
) -> Tuple[np.ndarray, np.ndarray]:
    """Draw independent multinomial cluster bootstrap weight matrices (w_T, w_A) from a single shared PCG64 stream."""
    if n_t < 1 or n_a < 1 or b < 1:
        raise ValueError(f"Invalid bootstrap dimensions: n_t={n_t}, n_a={n_a}, b={b}")
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    w_t = rng.multinomial(n_t, np.full(n_t, 1.0 / float(n_t)), size=b).astype(np.float64) / float(n_t)
    w_a = rng.multinomial(n_a, np.full(n_a, 1.0 / float(n_a)), size=b).astype(np.float64) / float(n_a)
    return w_t, w_a


def draw_all_bootstrap_weights_e2(
    n_t: int,
    n_a: int,
    n_aplan: int,
    n_apure: int,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E2,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Draw (w_T, w_A, w_A_plan, w_A_pure) sequentially from the single shared PCG64(seed) stream per PLAN-E2.md §4.1."""
    if n_t < 1 or n_a < 1 or b < 1:
        raise ValueError(f"Invalid bootstrap dimensions: n_t={n_t}, n_a={n_a}, b={b}")
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    w_t = rng.multinomial(n_t, np.full(n_t, 1.0 / float(n_t)), size=b).astype(np.float64) / float(n_t)
    w_a = rng.multinomial(n_a, np.full(n_a, 1.0 / float(n_a)), size=b).astype(np.float64) / float(n_a)
    w_aplan = (
        rng.multinomial(n_aplan, np.full(n_aplan, 1.0 / float(n_aplan)), size=b).astype(np.float64) / float(n_aplan)
        if n_aplan >= 1
        else np.zeros((b, 0), dtype=np.float64)
    )
    w_apure = (
        rng.multinomial(n_apure, np.full(n_apure, 1.0 / float(n_apure)), size=b).astype(np.float64) / float(n_apure)
        if n_apure >= 1
        else np.zeros((b, 0), dtype=np.float64)
    )
    return w_t, w_a, w_aplan, w_apure


def infer_continuous_slot_e2(
    d_lower: Sequence[float] | np.ndarray,
    d_upper: Sequence[float] | np.ndarray,
    w_mat: np.ndarray,
    method: str = "pct",
    demoted_to_exploratory: bool = False,
) -> Dict[str, Any]:
    """Evaluate a continuous paired-difference slot (`E2_H1`, `E2_H2`, or `E2_H3`) under `pct` or `bessel_t`.

    All 4 degeneracy checks are evaluated BEFORE clipping to `[-100.0, 100.0]` per PLAN-E2.md §4.2.2:
    1. u_low < 20 or u_high < 20 (via _greedy_distinct_1d_sorted with TOL_DUST = 1e-12);
    2. |s_low[idx_hi] - s_low[idx_lo]| <= 1e-12 or |s_high[idx_hi] - s_high[idx_lo]| <= 1e-12;
    3. Non-finite or inverted raw CI endpoints (`raw_ci_lo > raw_ci_hi`);
    4. For `bessel_t`: unclipped raw CI completely outside `[-100.0, 100.0]` (`raw_ci_lo > 100.0` or `raw_ci_hi < -100.0`).
    """
    if method not in ("pct", "bessel_t"):
        raise ValueError(f"Unsupported continuous method {method!r}; expected 'pct' or 'bessel_t'")
    dl = np.asarray(d_lower, dtype=np.float64)
    du = np.asarray(d_upper, dtype=np.float64)
    if dl.ndim != 1 or du.ndim != 1 or dl.shape != du.shape or len(dl) < 2:
        raise ValueError(f"Invalid d_lower/d_upper shapes: {dl.shape} vs {du.shape}")

    n = int(len(dl))
    b = int(w_mat.shape[0])
    if w_mat.shape != (b, n):
        raise ValueError(f"w_mat shape {w_mat.shape} does not match (B={b}, n={n})")

    pt_lo = float(np.mean(dl))
    pt_hi = float(np.mean(du))

    boot_lo_raw = w_mat @ dl
    boot_hi_raw = w_mat @ du

    if method == "bessel_t":
        c_n = BESSEL_T_FACTORS_BY_N.get(n)
        if c_n is None:
            c_n = compute_bessel_t_expansion_factor(n, "0.0125")
        boot_lo = np.minimum(boot_lo_raw, pt_lo + c_n * (boot_lo_raw - pt_lo))
        boot_hi = np.maximum(boot_hi_raw, pt_hi + c_n * (boot_hi_raw - pt_hi))
    else:
        c_n = 1.0
        boot_lo = boot_lo_raw
        boot_hi = boot_hi_raw

    s_low = np.sort(boot_lo, kind="mergesort")
    s_high = np.sort(boot_hi, kind="mergesort")

    idx_lo_9875, idx_hi_9875 = _order_stat_indices(b, ALPHA_IND)
    idx_lo_95, idx_hi_95 = _order_stat_indices(b, ALPHA_COMPANION_95)

    u_low = _greedy_distinct_1d_sorted(s_low)
    u_high = _greedy_distinct_1d_sorted(s_high)

    raw_lo_9875 = float(s_low[idx_lo_9875])
    raw_hi_9875 = float(s_high[idx_hi_9875])
    raw_lo_95 = float(s_low[idx_lo_95])
    raw_hi_95 = float(s_high[idx_hi_95])

    span_low_9875 = abs(float(s_low[idx_hi_9875]) - float(s_low[idx_lo_9875]))
    span_high_9875 = abs(float(s_high[idx_hi_9875]) - float(s_high[idx_lo_9875]))

    degen_reasons: List[str] = []
    if u_low < MIN_UNIQUE_DRAWS or u_high < MIN_UNIQUE_DRAWS:
        degen_reasons.append("insufficient_distinct_draws")
    if (not math.isfinite(span_low_9875)) or (not math.isfinite(span_high_9875)) or (
        span_low_9875 <= TOL_DUST or span_high_9875 <= TOL_DUST
    ):
        degen_reasons.append("zero_quantile_span")
    if (
        (not (math.isfinite(raw_lo_9875) and math.isfinite(raw_hi_9875) and math.isfinite(raw_lo_95) and math.isfinite(raw_hi_95)))
        or (raw_lo_9875 > raw_hi_9875)
        or (raw_lo_95 > raw_hi_95)
    ):
        degen_reasons.append("invalid_or_inverted_ci")
    if method == "bessel_t" and (raw_lo_9875 > 100.0 or raw_hi_9875 < -100.0):
        degen_reasons.append("out_of_domain_unclipped_ci")

    degenerate = bool(degen_reasons)

    # One-sided p-value (H0: theta <= 0 vs H1: theta > 0) on lower stream
    if (not math.isfinite(pt_lo)) or pt_lo <= 0.0:
        p_computed = 1.0
    else:
        n_le_zero = int(np.count_nonzero(boot_lo <= 0.0))
        p_computed = float(1 + n_le_zero) / float(b + 1)

    if degenerate:
        p_computed = 1.0
        ci_9875_computed = [-100.0, 100.0]
        ci_95_computed = [-100.0, 100.0]
    else:
        if method == "bessel_t":
            ci_9875_computed = [
                float(np.clip(raw_lo_9875, -100.0, 100.0)),
                float(np.clip(raw_hi_9875, -100.0, 100.0)),
            ]
            ci_95_computed = [
                float(np.clip(raw_lo_95, -100.0, 100.0)),
                float(np.clip(raw_hi_95, -100.0, 100.0)),
            ]
        else:
            ci_9875_computed = [raw_lo_9875, raw_hi_9875]
            ci_95_computed = [raw_lo_95, raw_hi_95]

    if demoted_to_exploratory:
        p_confirmatory = 1.0
        ci_9875_confirmatory = [-100.0, 100.0]
    else:
        p_confirmatory = p_computed
        ci_9875_confirmatory = list(ci_9875_computed)

    return {
        "n": n,
        "b": b,
        "method": method,
        "expansion_factor_c_n": float(c_n),
        "point_lower": pt_lo,
        "point_upper": pt_hi,
        "point": pt_lo if (math.isfinite(pt_lo) and math.isfinite(pt_hi) and abs(pt_lo - pt_hi) <= 1e-15) else [pt_lo, pt_hi],
        "p": p_confirmatory,
        "ci_9875": ci_9875_confirmatory,
        "ci_95": list(ci_95_computed),
        "raw_ci_9875_unclipped": [raw_lo_9875, raw_hi_9875],
        "u_low": int(u_low),
        "u_high": int(u_high),
        "span_low_9875": float(span_low_9875),
        "span_high_9875": float(span_high_9875),
        "degenerate": degenerate,
        "degeneracy_reasons": degen_reasons,
        "demoted_to_exploratory": bool(demoted_to_exploratory),
        "exploratory_p_raw": p_computed,
        "exploratory_ci_9875": list(ci_9875_computed),
    }


def infer_discrete_slot_e2(
    d_lower: Sequence[int | float] | np.ndarray,
    d_upper: Sequence[int | float] | np.ndarray,
    one_sided: bool = True,
    tables_for_n: Optional[Dict[str, Any]] = None,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Evaluate discrete paired proportion contrast (`E2_H4`) via certified exact Tango (1998) tables."""
    res = infer_exact_tango_slot(
        d_lower=np.asarray(d_lower),
        d_upper=np.asarray(d_upper),
        one_sided=one_sided,
        tables_for_n=tables_for_n,
        npz_path=npz_path,
    )
    pt_lo = float(res["point_lower"])
    pt_hi = float(res["point_upper"])
    ci_9875 = [float(res["ci_9875"][0]), float(res["ci_9875"][1])]
    ci_95 = [float(res["ci_95"][0]), float(res["ci_95"][1])]
    return {
        **res,
        "method": "exact_tango_1998",
        "point_lower_pct": 100.0 * pt_lo,
        "point_upper_pct": 100.0 * pt_hi,
        "ci_9875_pct": [100.0 * ci_9875[0], 100.0 * ci_9875[1]],
        "ci_95_pct": [100.0 * ci_95[0], 100.0 * ci_95[1]],
        "degenerate": bool(res["degenerate_9875"]),
        "demoted_to_exploratory": False,
    }


def holm_step_down_e2(
    p_raw_by_slot: Dict[str, float],
    slot_order: Sequence[str] = E2_SLOT_ORDER,
    alpha_fam: float = ALPHA_FAM,
) -> Dict[str, Dict[str, Any]]:
    """Run m = 4 Holm step-down procedure with deterministic tie-breaking in E2_SLOT_ORDER."""
    m = len(slot_order)
    if m != M_SLOTS or set(p_raw_by_slot.keys()) != set(slot_order):
        raise ValueError(f"Expected exact slot keys {slot_order}, got {sorted(p_raw_by_slot.keys())}")
    indexed = [(idx, slot, float(p_raw_by_slot[slot])) for idx, slot in enumerate(slot_order)]
    sorted_items = sorted(indexed, key=lambda x: (x[2], x[0]))

    out: Dict[str, Dict[str, Any]] = {}
    running_max = 0.0
    stopped = False
    for step_k, (_, slot, p_val) in enumerate(sorted_items, start=1):
        denom = m - step_k + 1
        threshold = float(alpha_fam) / float(denom)
        adj = min(1.0, max(running_max, float(denom) * p_val))
        running_max = adj
        if p_val > threshold:
            stopped = True
        rejected = not stopped
        out[slot] = {
            "step": step_k,
            "p_raw": p_val,
            "holm_threshold": threshold,
            "p_holm": adj,
            "rejected": rejected,
        }
    return out


def infer_family_from_paired_bounds_e2(
    d1_lower: np.ndarray,
    d1_upper: np.ndarray,
    d2_lower: np.ndarray,
    d2_upper: np.ndarray,
    d3_lower: np.ndarray,
    d3_upper: np.ndarray,
    d4_lower: np.ndarray,
    d4_upper: np.ndarray,
    *,
    continuous_method: str = "pct",
    w_t: Optional[np.ndarray] = None,
    w_a: Optional[np.ndarray] = None,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E2,
    tango_tables_n_a: Optional[Dict[str, Any]] = None,
    demoted_slots: Iterable[str] = (),
) -> Dict[str, Any]:
    """Evaluate the 4-slot confirmatory family (`E2_H1..E2_H4`) from paired cluster difference bounds."""
    n_t = len(d1_lower)
    n_a = len(d3_lower)
    if len(d2_lower) != n_t or len(d4_lower) != n_a:
        raise ValueError("Cluster count mismatch between (E2_H1, E2_H2) or (E2_H3, E2_H4)")
    demoted_set = set(demoted_slots)
    if not demoted_set.issubset(set(CONT_SLOT_ORDER)):
        raise ValueError(f"Only continuous slots in {CONT_SLOT_ORDER} may be demoted; got {sorted(demoted_set)}")

    if w_t is None or w_a is None:
        w_t, w_a = draw_macro_bootstrap_weights_e2(n_t, n_a, b=b, seed=seed)

    h1 = infer_continuous_slot_e2(
        d1_lower, d1_upper, w_t, method=continuous_method, demoted_to_exploratory=("E2_H1" in demoted_set)
    )
    h2 = infer_continuous_slot_e2(
        d2_lower, d2_upper, w_t, method=continuous_method, demoted_to_exploratory=("E2_H2" in demoted_set)
    )
    h3 = infer_continuous_slot_e2(
        d3_lower, d3_upper, w_a, method=continuous_method, demoted_to_exploratory=("E2_H3" in demoted_set)
    )
    h4 = infer_discrete_slot_e2(
        d4_lower, d4_upper, one_sided=True, tables_for_n=tango_tables_n_a
    )

    slots = {"E2_H1": h1, "E2_H2": h2, "E2_H3": h3, "E2_H4": h4}
    p_raw_map = {k: float(v["p"]) for k, v in slots.items()}
    holm = holm_step_down_e2(p_raw_map)
    for k, h_info in holm.items():
        slots[k].update(h_info)

    return {
        "family_name": f"hybrid_{continuous_method}_tango_e2",
        "continuous_method": continuous_method,
        "m": M_SLOTS,
        "alpha_fam": ALPHA_FAM,
        "alpha_ind": ALPHA_IND,
        "b": int(b),
        "seed": int(seed),
        "n_telic": int(n_t),
        "n_atelic": int(n_a),
        "demoted_slots": sorted(demoted_set),
        "slots": slots,
        "holm": holm,
    }


def infer_hybrid_pct_tango_e2(
    d1_lower: np.ndarray,
    d1_upper: np.ndarray,
    d2_lower: np.ndarray,
    d2_upper: np.ndarray,
    d3_lower: np.ndarray,
    d3_upper: np.ndarray,
    d4_lower: np.ndarray,
    d4_upper: np.ndarray,
    *,
    w_t: Optional[np.ndarray] = None,
    w_a: Optional[np.ndarray] = None,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E2,
    tango_tables_n_a: Optional[Dict[str, Any]] = None,
    demoted_slots: Iterable[str] = (),
) -> Dict[str, Any]:
    """Candidate 1: Percentile Bootstrap on `E2_H1..E2_H3` + Certified Exact Tango on `E2_H4`."""
    return infer_family_from_paired_bounds_e2(
        d1_lower, d1_upper, d2_lower, d2_upper, d3_lower, d3_upper, d4_lower, d4_upper,
        continuous_method="pct",
        w_t=w_t,
        w_a=w_a,
        b=b,
        seed=seed,
        tango_tables_n_a=tango_tables_n_a,
        demoted_slots=demoted_slots,
    )


def infer_hybrid_bessel_t_tango_e2(
    d1_lower: np.ndarray,
    d1_upper: np.ndarray,
    d2_lower: np.ndarray,
    d2_upper: np.ndarray,
    d3_lower: np.ndarray,
    d3_upper: np.ndarray,
    d4_lower: np.ndarray,
    d4_upper: np.ndarray,
    *,
    w_t: Optional[np.ndarray] = None,
    w_a: Optional[np.ndarray] = None,
    b: int = B_DEFAULT,
    seed: int = FORMAL_ANALYSIS_SEED_E2,
    tango_tables_n_a: Optional[Dict[str, Any]] = None,
    demoted_slots: Iterable[str] = (),
) -> Dict[str, Any]:
    """Candidate 2 / Companion: Order-preserving Bessel-t Bootstrap on `E2_H1..E2_H3` + Exact Tango on `E2_H4`."""
    return infer_family_from_paired_bounds_e2(
        d1_lower, d1_upper, d2_lower, d2_upper, d3_lower, d3_upper, d4_lower, d4_upper,
        continuous_method="bessel_t",
        w_t=w_t,
        w_a=w_a,
        b=b,
        seed=seed,
        tango_tables_n_a=tango_tables_n_a,
        demoted_slots=demoted_slots,
    )


def extract_unit_continuous_bounds(row: Optional[Dict[str, Any]], metric: str = "value") -> Tuple[float, float]:
    """Extract worst-case `[0.0, 100.0]` bounds for a continuous reading under strict `status == 'ok'`."""
    if row is None or row.get("status") != "ok":
        return 0.0, 100.0
    if metric == "M_U":
        parsed = row.get("parsed") or {}
        ests = parsed.get("estimates")
        if not isinstance(ests, list) or len(ests) != 5:
            return 0.0, 100.0
        val = float(sum(float(x) for x in ests) / 5.0)
    elif metric == "M_W":
        val = float(row["value"])
    elif metric == "value":
        val = float(row["value"])
    else:
        raise ValueError(f"Unknown continuous metric {metric!r}")
    if not (math.isfinite(val) and 0.0 <= val <= 100.0):
        return 0.0, 100.0
    return val, val


def extract_unit_label_true_bounds(
    row: Optional[Dict[str, Any]],
    allow_missing_score: bool = False,
) -> Tuple[int, int]:
    """Extract worst-case `[0, 1]` bounds for `I(label == 'True')`.

    - Primary rule (`allow_missing_score=False`): only `status == 'ok'` uses observed label;
      any `status != 'ok'` (including `missing_score`) maps to `[0, 1]`.
    - Companion diagnostic (`allow_missing_score=True`): `status in ('ok', 'missing_score')`
      (i.e. `label_available == True`) uses observed label.
    """
    if row is None:
        return 0, 1
    status = row.get("status")
    allowed = ("ok", "missing_score") if allow_missing_score else ("ok",)
    if status not in allowed:
        return 0, 1
    lbl = row.get("label")
    if lbl not in ("True", "False", "Unknown"):
        return 0, 1
    ind = 1 if lbl == "True" else 0
    return ind, ind


def _paired_diff_bounds(
    x_bounds: Sequence[Tuple[float, float]],
    y_bounds: Sequence[Tuple[float, float]],
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute cluster-level worst-case difference bounds D_lower = X_lower - Y_upper, D_upper = X_upper - Y_lower."""
    if len(x_bounds) != len(y_bounds):
        raise ValueError("Mismatched cluster sequence lengths in _paired_diff_bounds")
    d_lo = np.array([float(x[0]) - float(y[1]) for x, y in zip(x_bounds, y_bounds)], dtype=np.float64)
    d_hi = np.array([float(x[1]) - float(y[0]) for x, y in zip(x_bounds, y_bounds)], dtype=np.float64)
    return d_lo, d_hi


def _bounds_mean_sd(
    bounds_seq: Sequence[Tuple[float, float]],
    w_mat: Optional[np.ndarray] = None,
) -> Dict[str, List[float]]:
    """Compute missingness identification bounds `mean_bounds`, endpoint path SD `endpoint_path_sd`,
    and (when `w_mat` is supplied) 95% cluster bootstrap percentile CI `ci_95`."""
    if not bounds_seq:
        out = {"mean_bounds": [0.0, 0.0], "endpoint_path_sd": [0.0, 0.0]}
        if w_mat is not None:
            out["ci_95"] = [0.0, 0.0]
        return out
    lo = np.array([float(b[0]) for b in bounds_seq], dtype=np.float64)
    hi = np.array([float(b[1]) for b in bounds_seq], dtype=np.float64)
    ddof = 1 if len(lo) >= 2 else 0
    out = {
        "mean_bounds": [float(np.mean(lo)), float(np.mean(hi))],
        "endpoint_path_sd": [float(np.std(lo, ddof=ddof)), float(np.std(hi, ddof=ddof))],
    }
    if w_mat is not None:
        if w_mat.shape[1] == len(lo) and w_mat.shape[0] >= 1:
            b_draws = int(w_mat.shape[0])
            boot_lo = w_mat @ lo
            boot_hi = w_mat @ hi
            s_lo = np.sort(boot_lo, kind="mergesort")
            s_hi = np.sort(boot_hi, kind="mergesort")
            idx_lo_95, idx_hi_95 = _order_stat_indices(b_draws, ALPHA_COMPANION_95)
            out["ci_95"] = [float(s_lo[idx_lo_95]), float(s_hi[idx_hi_95])]
        else:
            out["ci_95"] = list(out["mean_bounds"])
    return out


def _mann_whitney_auc_bounds(
    x_bounds: Sequence[Tuple[float, float]],
    y_bounds: Sequence[Tuple[float, float]],
    w_x: Optional[np.ndarray] = None,
    w_y: Optional[np.ndarray] = None,
) -> Dict[str, List[float]]:
    """Compute worst-case two-sample mean difference (X - Y) and Mann-Whitney U/(n_X n_Y) AUC bounds
    plus 95% cluster bootstrap percentile CIs (`mean_diff_ci_95`, `auc_ci_95`) when `(w_x, w_y)` are provided."""
    if not x_bounds or not y_bounds:
        return {
            "mean_diff_bounds": [0.0, 0.0],
            "mean_diff_ci_95": [0.0, 0.0],
            "auc_bounds": [0.5, 0.5],
            "auc_ci_95": [0.5, 0.5],
        }
    x_lo = np.array([float(b[0]) for b in x_bounds], dtype=np.float64)
    x_hi = np.array([float(b[1]) for b in x_bounds], dtype=np.float64)
    y_lo = np.array([float(b[0]) for b in y_bounds], dtype=np.float64)
    y_hi = np.array([float(b[1]) for b in y_bounds], dtype=np.float64)

    mean_diff_lo = float(np.mean(x_lo) - np.mean(y_hi))
    mean_diff_hi = float(np.mean(x_hi) - np.mean(y_lo))

    def _pair_kernel(xv: np.ndarray, yv: np.ndarray) -> np.ndarray:
        diff = xv[:, None] - yv[None, :]
        return np.where(diff > 1e-12, 1.0, np.where(np.abs(diff) <= 1e-12, 0.5, 0.0))

    k_lo = _pair_kernel(x_lo, y_hi)
    k_hi = _pair_kernel(x_hi, y_lo)
    auc_lo = float(np.mean(k_lo))
    auc_hi = float(np.mean(k_hi))

    if (
        w_x is not None
        and w_y is not None
        and w_x.shape[1] == len(x_lo)
        and w_y.shape[1] == len(y_lo)
        and w_x.shape[0] == w_y.shape[0]
        and w_x.shape[0] >= 1
    ):
        b_draws = int(w_x.shape[0])
        idx_lo_95, idx_hi_95 = _order_stat_indices(b_draws, ALPHA_COMPANION_95)
        md_boot_lo = np.sort((w_x @ x_lo) - (w_y @ y_hi), kind="mergesort")
        md_boot_hi = np.sort((w_x @ x_hi) - (w_y @ y_lo), kind="mergesort")
        mean_diff_ci_95 = [float(md_boot_lo[idx_lo_95]), float(md_boot_hi[idx_hi_95])]

        auc_boot_lo = np.sort(np.sum((w_x @ k_lo) * w_y, axis=1), kind="mergesort")
        auc_boot_hi = np.sort(np.sum((w_x @ k_hi) * w_y, axis=1), kind="mergesort")
        auc_ci_95 = [float(auc_boot_lo[idx_lo_95]), float(auc_boot_hi[idx_hi_95])]
    else:
        mean_diff_ci_95 = [mean_diff_lo, mean_diff_hi]
        auc_ci_95 = [auc_lo, auc_hi]

    return {
        "mean_diff_bounds": [mean_diff_lo, mean_diff_hi],
        "mean_diff_ci_95": mean_diff_ci_95,
        "auc_bounds": [auc_lo, auc_hi],
        "auc_ci_95": auc_ci_95,
    }


def _infer_two_group_diff_e2(
    x_lo: np.ndarray,
    x_hi: np.ndarray,
    y_lo: np.ndarray,
    y_hi: np.ndarray,
    w_x: np.ndarray,
    w_y: np.ndarray,
) -> Dict[str, Any]:
    """Two-group exploratory bootstrap difference (X - Y) and Mann-Whitney AUC on shared draw streams w_x and w_y."""
    pt_lo = float(np.mean(x_lo) - np.mean(y_hi))
    pt_hi = float(np.mean(x_hi) - np.mean(y_lo))
    boot_lo = (w_x @ x_lo) - (w_y @ y_hi)
    boot_hi = (w_x @ x_hi) - (w_y @ y_lo)
    b = int(len(boot_lo))
    s_lo = np.sort(boot_lo, kind="mergesort")
    s_hi = np.sort(boot_hi, kind="mergesort")
    idx_lo_95, idx_hi_95 = _order_stat_indices(b, ALPHA_COMPANION_95)
    idx_lo_9875, idx_hi_9875 = _order_stat_indices(b, ALPHA_IND)
    xb = list(zip(x_lo.tolist(), x_hi.tolist()))
    yb = list(zip(y_lo.tolist(), y_hi.tolist()))
    mw = _mann_whitney_auc_bounds(xb, yb, w_x=w_x, w_y=w_y)
    return {
        "point_lower": pt_lo,
        "point_upper": pt_hi,
        "mean_diff_bounds": [pt_lo, pt_hi],
        "ci_95_pct": [float(s_lo[idx_lo_95]), float(s_hi[idx_hi_95])],
        "ci_9875_pct": [float(s_lo[idx_lo_9875]), float(s_hi[idx_hi_9875])],
        "auc_bounds": mw["auc_bounds"],
        "auc_ci_95": mw["auc_ci_95"],
    }


ALL_13_COMBINATIONS: Tuple[Tuple[str, str], ...] = (
    ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"),
    ("Ps", "Z"),
    ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
    ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
)
MAIN_4_SLOTS: Tuple[str, ...] = ("NI_COMP", "NI_BARE", "INT_COMP", "INT_BARE")
DIAG_2_SLOTS: Tuple[str, ...] = ("DIAG_POS_COMP", "DIAG_NEG_COMP")
SIX_SUBCLASSES_ORDER: Tuple[Tuple[str, str, str], ...] = (
    ("T_build", "telic", "Creation"),
    ("T_change", "telic", "Change of State"),
    ("T_consume", "telic", "Consumption"),
    ("T_motion", "telic", "Motion to Goal"),
    ("A_pure", "atelic", "Pure Unbounded Activity"),
    ("A_plan", "atelic", "Goal-Prone / Planned Activity"),
)
EXPECTED_SUBCLASS_COUNTS_BY_STAGE: Dict[str, Dict[str, int]] = {
    "formal": {
        "T_build": 21,
        "T_change": 14,
        "T_consume": 8,
        "T_motion": 5,
        "A_pure": 16,
        "A_plan": 16,
    },
    "dev": {
        "T_build": 5,
        "T_change": 4,
        "T_consume": 2,
        "T_motion": 1,
        "A_pure": 4,
        "A_plan": 4,
    },
}


def resolve_calibration_binding(
    calibration_lock: Optional[Dict[str, Any]],
    *,
    default_method: str = "pct",
    default_demoted: Iterable[str] = (),
    require_lock: bool = False,
) -> Dict[str, Any]:
    """Resolve and validate primary_method and demoted_slots from an S4/S5 calibration lock."""
    if calibration_lock is None:
        if require_lock:
            raise ValueError("Formal analysis requires a valid frozen S4/S5 calibration lock")
        if default_method not in ("pct", "bessel_t"):
            raise ValueError(f"Unsupported default_method {default_method!r}")
        demoted = sorted(set(default_demoted))
        if any(s not in CONT_SLOT_ORDER for s in demoted):
            raise ValueError(f"Invalid demoted_slots {demoted!r}")
        return {
            "bound_from_lock": False,
            "selected_family": "hybrid_pct_tango_e2" if default_method == "pct" else "hybrid_bessel_t_tango_e2",
            "primary_method": default_method,
            "demoted_slots": demoted,
        }
    if calibration_lock.get("status") != "pass":
        raise ValueError(
            f"Cannot analyze under calibration lock with status={calibration_lock.get('status')!r} (expected 'pass')"
        )
    fam = calibration_lock.get("selected_family")
    if fam == "hybrid_pct_tango_e2":
        method = "pct"
    elif fam == "hybrid_bessel_t_tango_e2":
        method = "bessel_t"
    else:
        raise ValueError(f"Invalid selected_family in calibration lock: {fam!r}")
    demoted = sorted(set(calibration_lock.get("demoted_slots", ())))
    if any(s not in CONT_SLOT_ORDER for s in demoted) or len(demoted) >= 3:
        raise ValueError(f"Invalid demoted_slots in calibration lock: {demoted!r}")
    return {
        "bound_from_lock": True,
        "selected_family": fam,
        "primary_method": method,
        "demoted_slots": demoted,
        "selected_step": calibration_lock.get("selected_step"),
        "production_eligible": bool(calibration_lock.get("production_eligible", False)),
    }


def _draw_multinomial_weights(rng: np.random.Generator, n: int, b: int) -> np.ndarray:
    if n < 1:
        return np.zeros((b, 0), dtype=np.float64)
    return rng.multinomial(n, np.full(n, 1.0 / float(n)), size=b).astype(np.float64) / float(n)


def analyze_stage_records_e2(
    records: Sequence[Dict[str, Any]],
    clusters: Sequence[Dict[str, Any]],
    cluster_ids: Sequence[str],
    *,
    stage: str = "formal",
    primary_method: str = "pct",
    demoted_slots: Iterable[str] = (),
    calibration_lock: Optional[Dict[str, Any]] = None,
    require_calibration_lock: bool = False,
    b: int = B_DEFAULT,
    seed: Optional[int] = None,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Full Experiment 2 stage analysis (Confirmatory Family + Companion + Layer 3 Exploratory Decomposition)."""
    verify_ieee754_rn_and_subnormals()
    tango_bundle = load_certified_tango_tables(npz_path=npz_path)

    binding = resolve_calibration_binding(
        calibration_lock,
        default_method=primary_method,
        default_demoted=demoted_slots,
        require_lock=require_calibration_lock,
    )
    primary_method = binding["primary_method"]
    demoted_slots = tuple(binding["demoted_slots"])

    if seed is None:
        seed = FORMAL_ANALYSIS_SEED_E2 if stage == "formal" else DEV_ANALYSIS_SEED_E2

    cluster_by_id = {c["cluster_id"]: c for c in clusters}
    stage_cids = sorted(set(cluster_ids))
    telic_cids = sorted(cid for cid in stage_cids if cluster_by_id[cid]["macro_class"] == "telic")
    atelic_cids = sorted(cid for cid in stage_cids if cluster_by_id[cid]["macro_class"] == "atelic")
    a_plan_cids = sorted(
        cid for cid in atelic_cids if cluster_by_id[cid]["subclass"] == "Goal-Prone / Planned Activity"
    )
    a_pure_cids = sorted(
        cid for cid in atelic_cids if cluster_by_id[cid]["subclass"] == "Pure Unbounded Activity"
    )
    telic_wan_cids = sorted(cid for cid in telic_cids if cluster_by_id[cid].get("comp_marker") == "完")
    a_plan_wan_cids = sorted(cid for cid in a_plan_cids if cluster_by_id[cid].get("comp_marker") == "完")
    if a_plan_wan_cids != a_plan_cids:
        raise ValueError("Expected all A_plan clusters to have comp_marker == '完'")

    # Enforce complete, mutually exclusive 6-subclass partition of stage_cids
    subclass_cids_by_code: Dict[str, List[str]] = {}
    partition_seen: List[str] = []
    for sub_code, macro_name, sub_label in SIX_SUBCLASSES_ORDER:
        scids = sorted(
            cid
            for cid in stage_cids
            if cluster_by_id[cid]["macro_class"] == macro_name and cluster_by_id[cid]["subclass"] == sub_label
        )
        subclass_cids_by_code[sub_code] = scids
        partition_seen.extend(scids)
    if len(partition_seen) != len(stage_cids) or sorted(partition_seen) != stage_cids:
        raise ValueError(
            f"SIX_SUBCLASSES_ORDER failed to form a complete partition of stage_cids "
            f"(matched {len(partition_seen)} of {len(stage_cids)})"
        )
    if stage in EXPECTED_SUBCLASS_COUNTS_BY_STAGE and len(stage_cids) == sum(EXPECTED_SUBCLASS_COUNTS_BY_STAGE[stage].values()):
        for sub_code, exp_cnt in EXPECTED_SUBCLASS_COUNTS_BY_STAGE[stage].items():
            got_cnt = len(subclass_cids_by_code[sub_code])
            if got_cnt != exp_cnt:
                raise ValueError(f"Stage {stage} subclass {sub_code} expected {exp_cnt} clusters, got {got_cnt}")
        exp_t_wan = 12 if stage == "formal" else 4
        if len(telic_wan_cids) != exp_t_wan:
            raise ValueError(f"Stage {stage} expected {exp_t_wan} telic '完' clusters, got {len(telic_wan_cids)}")

    n_t = len(telic_cids)
    n_a = len(atelic_cids)
    n_aplan = len(a_plan_cids)
    n_apure = len(a_pure_cids)
    by_unit = {r["unit_key"]: r for r in records}

    def get_row(cid: str, slot: str, task: str, prompt: str) -> Optional[Dict[str, Any]]:
        return by_unit.get(f"{cid}__{slot}/{task}/{prompt}")

    # 1. Extract primary paired bounds for E2_H1..E2_H4
    p_bare_t = [extract_unit_continuous_bounds(get_row(cid, "NI_BARE", "P", "Z"), "value") for cid in telic_cids]
    p_comp_t = [extract_unit_continuous_bounds(get_row(cid, "NI_COMP", "P", "Z"), "value") for cid in telic_cids]
    m_comp_t = [extract_unit_continuous_bounds(get_row(cid, "NI_COMP", "M", "Z"), "M_U") for cid in telic_cids]

    d1_lo, d1_hi = _paired_diff_bounds(p_bare_t, p_comp_t)
    d2_lo, d2_hi = _paired_diff_bounds(p_comp_t, m_comp_t)

    p_int_bare_a = [extract_unit_continuous_bounds(get_row(cid, "INT_BARE", "P", "Z"), "value") for cid in atelic_cids]
    p_int_comp_a = [extract_unit_continuous_bounds(get_row(cid, "INT_COMP", "P", "Z"), "value") for cid in atelic_cids]
    d3_lo, d3_hi = _paired_diff_bounds(p_int_bare_a, p_int_comp_a)

    l_bare_a_ok = [extract_unit_label_true_bounds(get_row(cid, "NI_BARE", "L", "CoT"), False) for cid in atelic_cids]
    l_comp_a_ok = [extract_unit_label_true_bounds(get_row(cid, "NI_COMP", "L", "CoT"), False) for cid in atelic_cids]
    d4_lo, d4_hi = _paired_diff_bounds(l_bare_a_ok, l_comp_a_ok)

    # Shared single RNG stream for macro-classes AND atelic subclasses per PLAN-E2.md §4.1 (line 156)
    w_t, w_a, w_aplan, w_apure = draw_all_bootstrap_weights_e2(n_t, n_a, n_aplan, n_apure, b=b, seed=seed)
    # Deterministic continuation of the same PCG64(seed) stream for Layer 3 exploratory subgroups (telic '完' and telic subclasses)
    rng_cont = np.random.Generator(np.random.PCG64(int(seed)))
    for n_consume in (n_t, n_a, n_aplan, n_apure):
        if n_consume >= 1:
            _ = rng_cont.multinomial(n_consume, np.full(n_consume, 1.0 / float(n_consume)), size=b)
    w_t_wan = _draw_multinomial_weights(rng_cont, len(telic_wan_cids), b)
    w_by_subclass: Dict[str, np.ndarray] = {
        "A_plan": w_aplan,
        "A_pure": w_apure,
    }
    for sub_code, _, _ in SIX_SUBCLASSES_ORDER:
        if sub_code not in w_by_subclass:
            w_by_subclass[sub_code] = _draw_multinomial_weights(rng_cont, len(subclass_cids_by_code[sub_code]), b)

    tables_n_a = tango_bundle["by_n"][n_a]

    pct_family = infer_hybrid_pct_tango_e2(
        d1_lo, d1_hi, d2_lo, d2_hi, d3_lo, d3_hi, d4_lo, d4_hi,
        w_t=w_t, w_a=w_a, b=b, seed=seed, tango_tables_n_a=tables_n_a, demoted_slots=demoted_slots,
    )
    bessel_family = infer_hybrid_bessel_t_tango_e2(
        d1_lo, d1_hi, d2_lo, d2_hi, d3_lo, d3_hi, d4_lo, d4_hi,
        w_t=w_t, w_a=w_a, b=b, seed=seed, tango_tables_n_a=tables_n_a, demoted_slots=demoted_slots,
    )

    primary_family = pct_family if primary_method == "pct" else bessel_family
    companion_family = bessel_family if primary_method == "pct" else pct_family

    # Check if any L/CoT atelic unit has status == "missing_score" for E2_H4 label_available companion diagnostic
    n_missing_score_h4 = sum(
        1
        for cid in atelic_cids
        for slot in ("NI_BARE", "NI_COMP")
        if (get_row(cid, slot, "L", "CoT") or {}).get("status") == "missing_score"
    )
    l_bare_a_lbl = [extract_unit_label_true_bounds(get_row(cid, "NI_BARE", "L", "CoT"), True) for cid in atelic_cids]
    l_comp_a_lbl = [extract_unit_label_true_bounds(get_row(cid, "NI_COMP", "L", "CoT"), True) for cid in atelic_cids]
    d4_lbl_lo, d4_lbl_hi = _paired_diff_bounds(l_bare_a_lbl, l_comp_a_lbl)
    h4_label_available_diag = infer_discrete_slot_e2(
        d4_lbl_lo, d4_lbl_hi, one_sided=True, tables_for_n=tables_n_a
    )
    h4_label_available_diag["missing_score_units_recovered"] = n_missing_score_h4

    # Helper to summarize all 13 (task, prompt) conditions across 4 main slots (+ diagnostic on L/Z & P/Z) and paired contrasts
    def _build_group_13_conditions(group_cids: Sequence[str], w_group: np.ndarray, include_diag: bool) -> Dict[str, Any]:
        out_group: Dict[str, Any] = {}
        for task, prompt in ALL_13_COMBINATIONS:
            cond_key = f"{task}/{prompt}"
            slot_map: Dict[str, Any] = {}
            slots_to_check = MAIN_4_SLOTS + (
                DIAG_2_SLOTS if (include_diag and (task, prompt) in (("L", "Z"), ("P", "Z"))) else ()
            )
            slot_bounds_for_contrasts: Dict[str, List[Tuple[float, float]]] = {}
            for s in slots_to_check:
                rows_s = [get_row(cid, s, task, prompt) for cid in group_cids]
                n_ok = sum(1 for r in rows_s if r is not None and r.get("status") == "ok")
                n_miss = len(group_cids) - n_ok
                if task == "L":
                    tb = [extract_unit_label_true_bounds(r, False) for r in rows_s]
                    slot_bounds_for_contrasts[s] = [(float(x[0]), float(x[1])) for x in tb]
                    tb_sum = _bounds_mean_sd(tb, w_mat=w_group)
                    slot_map[s] = {
                        "n_clusters": len(group_cids),
                        "n_ok": n_ok,
                        "n_missing": n_miss,
                        "true_rate_bounds": tb_sum["mean_bounds"],
                        "true_rate_ci_95": tb_sum["ci_95"],
                        "endpoint_path_sd": tb_sum["endpoint_path_sd"],
                    }
                elif task in ("P", "Ps"):
                    vb = [extract_unit_continuous_bounds(r, "value") for r in rows_s]
                    slot_bounds_for_contrasts[s] = vb
                    slot_map[s] = {
                        "n_clusters": len(group_cids),
                        "n_ok": n_ok,
                        "n_missing": n_miss,
                        **_bounds_mean_sd(vb, w_mat=w_group),
                    }
                else:
                    mu_b = [extract_unit_continuous_bounds(r, "M_U") for r in rows_s]
                    mw_b = [extract_unit_continuous_bounds(r, "M_W") for r in rows_s]
                    slot_bounds_for_contrasts[s] = mu_b
                    mw_minus_mu_lo, mw_minus_mu_hi = _paired_diff_bounds(mw_b, mu_b)
                    mw_minus_mu_b = list(zip(mw_minus_mu_lo.tolist(), mw_minus_mu_hi.tolist()))
                    mu_sum = _bounds_mean_sd(mu_b, w_mat=w_group)
                    mw_sum = _bounds_mean_sd(mw_b, w_mat=w_group)
                    diff_sum = _bounds_mean_sd(mw_minus_mu_b, w_mat=w_group)
                    slot_map[s] = {
                        "n_clusters": len(group_cids),
                        "n_ok": n_ok,
                        "n_missing": n_miss,
                        "M_U_mean_bounds": mu_sum["mean_bounds"],
                        "M_U_ci_95": mu_sum["ci_95"],
                        "M_U_endpoint_path_sd": mu_sum["endpoint_path_sd"],
                        "M_W_mean_bounds": mw_sum["mean_bounds"],
                        "M_W_ci_95": mw_sum["ci_95"],
                        "M_W_endpoint_path_sd": mw_sum["endpoint_path_sd"],
                        "M_W_minus_M_U_mean_bounds": diff_sum["mean_bounds"],
                        "M_W_minus_M_U_ci_95": diff_sum["ci_95"],
                        "M_W_minus_M_U_endpoint_path_sd": diff_sum["endpoint_path_sd"],
                    }
            ni_diff_lo, ni_diff_hi = _paired_diff_bounds(
                slot_bounds_for_contrasts["NI_BARE"], slot_bounds_for_contrasts["NI_COMP"]
            )
            int_diff_lo, int_diff_hi = _paired_diff_bounds(
                slot_bounds_for_contrasts["INT_BARE"], slot_bounds_for_contrasts["INT_COMP"]
            )
            slot_map["paired_contrasts"] = {
                "NI_BARE_minus_NI_COMP": _bounds_mean_sd(
                    list(zip(ni_diff_lo.tolist(), ni_diff_hi.tolist())), w_mat=w_group
                ),
                "INT_BARE_minus_INT_COMP": _bounds_mean_sd(
                    list(zip(int_diff_lo.tolist(), int_diff_hi.tolist())), w_mat=w_group
                ),
            }
            out_group[cond_key] = slot_map
        return out_group

    group_13_trajectories = {
        "telic": _build_group_13_conditions(telic_cids, w_t, include_diag=True),
        "atelic": _build_group_13_conditions(atelic_cids, w_a, include_diag=True),
        "A_plan": _build_group_13_conditions(a_plan_cids, w_aplan, include_diag=False),
        "A_pure": _build_group_13_conditions(a_pure_cids, w_apure, include_diag=False),
    }

    # 2. Layer 3.1: Mandatory subclass decomposition for A_plan and A_pure on E2_H3, E2_H4, and all 13 conditions (shared RNG stream)
    subclass_decomp: Dict[str, Any] = {}
    sub_d3_vectors: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    sub_d4_vectors: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for sub_key, sub_cids, w_sub in (("A_plan", a_plan_cids, w_aplan), ("A_pure", a_pure_cids, w_apure)):
        n_sub = len(sub_cids)
        if n_sub >= 2:
            xb = [extract_unit_continuous_bounds(get_row(cid, "INT_BARE", "P", "Z"), "value") for cid in sub_cids]
            yb = [extract_unit_continuous_bounds(get_row(cid, "INT_COMP", "P", "Z"), "value") for cid in sub_cids]
            sub_d3_lo, sub_d3_hi = _paired_diff_bounds(xb, yb)
            sub_d3_vectors[sub_key] = (sub_d3_lo, sub_d3_hi)
            h3_sub_pct = infer_continuous_slot_e2(sub_d3_lo, sub_d3_hi, w_sub, method="pct")
            h3_sub_bessel = infer_continuous_slot_e2(sub_d3_lo, sub_d3_hi, w_sub, method="bessel_t")

            lb = [extract_unit_label_true_bounds(get_row(cid, "NI_BARE", "L", "CoT"), False) for cid in sub_cids]
            lc = [extract_unit_label_true_bounds(get_row(cid, "NI_COMP", "L", "CoT"), False) for cid in sub_cids]
            sub_d4_lo, sub_d4_hi = _paired_diff_bounds(lb, lc)
            sub_d4_vectors[sub_key] = (sub_d4_lo, sub_d4_hi)
            h4_sub_boot = _bounds_mean_sd(list(zip(sub_d4_lo.tolist(), sub_d4_hi.tolist())), w_mat=w_sub)
            h4_sub = (
                infer_discrete_slot_e2(
                    sub_d4_lo,
                    sub_d4_hi,
                    one_sided=True,
                    tables_for_n=tango_bundle["by_n"][n_sub],
                )
                if n_sub in tango_bundle["by_n"]
                else {
                    "n": n_sub,
                    "method": "bootstrap_pct_fallback_small_n",
                    "point_lower": h4_sub_boot["mean_bounds"][0],
                    "point_upper": h4_sub_boot["mean_bounds"][1],
                    "ci_95": h4_sub_boot["ci_95"],
                    "endpoint_path_sd": h4_sub_boot["endpoint_path_sd"],
                }
            )
            subclass_decomp[sub_key] = {
                "n_clusters": n_sub,
                "cluster_ids": sub_cids,
                "E2_H3_pct": h3_sub_pct,
                "E2_H3_bessel_t": h3_sub_bessel,
                "E2_H4_exact_tango": h4_sub,
                "conditions_13_four_slots": group_13_trajectories[sub_key],
            }
    if "A_plan" in sub_d3_vectors and "A_pure" in sub_d3_vectors:
        ap_lo, ap_hi = sub_d3_vectors["A_plan"]
        au_lo, au_hi = sub_d3_vectors["A_pure"]
        subclass_decomp["A_plan_minus_A_pure_E2_H3"] = _infer_two_group_diff_e2(
            ap_lo, ap_hi, au_lo, au_hi, w_aplan, w_apure
        )
    if "A_plan" in sub_d4_vectors and "A_pure" in sub_d4_vectors:
        ap4_lo, ap4_hi = sub_d4_vectors["A_plan"]
        au4_lo, au4_hi = sub_d4_vectors["A_pure"]
        subclass_decomp["A_plan_minus_A_pure_E2_H4"] = _infer_two_group_diff_e2(
            ap4_lo, ap4_hi, au4_lo, au4_hi, w_aplan, w_apure
        )

    # 3. Layer 3.2: All 6 subclasses descriptive summary (with 95% bootstrap CIs and endpoint_path_sd)
    six_subclasses_summary: Dict[str, Any] = {}
    for sub_code, macro_name, sub_label in SIX_SUBCLASSES_ORDER:
        sub_cids = subclass_cids_by_code[sub_code]
        w_sub_6 = w_by_subclass[sub_code]
        pz_slots = {
            s: _bounds_mean_sd(
                [extract_unit_continuous_bounds(get_row(cid, s, "P", "Z"), "value") for cid in sub_cids],
                w_mat=w_sub_6,
            )
            for s in MAIN_4_SLOTS
        }
        lz_slots_full = {
            s: _bounds_mean_sd(
                [extract_unit_label_true_bounds(get_row(cid, s, "L", "Z"), False) for cid in sub_cids],
                w_mat=w_sub_6,
            )
            for s in MAIN_4_SLOTS
        }
        lcot_slots_full = {
            s: _bounds_mean_sd(
                [extract_unit_label_true_bounds(get_row(cid, s, "L", "CoT"), False) for cid in sub_cids],
                w_mat=w_sub_6,
            )
            for s in MAIN_4_SLOTS
        }
        pb_sub = [extract_unit_continuous_bounds(get_row(cid, "NI_BARE", "P", "Z"), "value") for cid in sub_cids]
        pc_sub = [extract_unit_continuous_bounds(get_row(cid, "NI_COMP", "P", "Z"), "value") for cid in sub_cids]
        mc_sub = [extract_unit_continuous_bounds(get_row(cid, "NI_COMP", "M", "Z"), "M_U") for cid in sub_cids]
        ib_sub = [extract_unit_continuous_bounds(get_row(cid, "INT_BARE", "P", "Z"), "value") for cid in sub_cids]
        ic_sub = [extract_unit_continuous_bounds(get_row(cid, "INT_COMP", "P", "Z"), "value") for cid in sub_cids]
        lb_sub = [extract_unit_label_true_bounds(get_row(cid, "NI_BARE", "L", "CoT"), False) for cid in sub_cids]
        lc_sub = [extract_unit_label_true_bounds(get_row(cid, "NI_COMP", "L", "CoT"), False) for cid in sub_cids]

        s_d1_lo, s_d1_hi = _paired_diff_bounds(pb_sub, pc_sub)
        s_d2_lo, s_d2_hi = _paired_diff_bounds(pc_sub, mc_sub)
        s_d3_lo, s_d3_hi = _paired_diff_bounds(ib_sub, ic_sub)
        s_d4_lo, s_d4_hi = _paired_diff_bounds(lb_sub, lc_sub)

        d1_sum = _bounds_mean_sd(list(zip(s_d1_lo.tolist(), s_d1_hi.tolist())), w_mat=w_sub_6)
        d2_sum = _bounds_mean_sd(list(zip(s_d2_lo.tolist(), s_d2_hi.tolist())), w_mat=w_sub_6)
        d3_sum = _bounds_mean_sd(list(zip(s_d3_lo.tolist(), s_d3_hi.tolist())), w_mat=w_sub_6)
        d4_sum = _bounds_mean_sd(list(zip(s_d4_lo.tolist(), s_d4_hi.tolist())), w_mat=w_sub_6)

        six_subclasses_summary[sub_code] = {
            "subclass": sub_label,
            "macro_class": macro_name,
            "n_clusters": len(sub_cids),
            "cluster_ids": sub_cids,
            "slot_PZ": pz_slots,
            "slot_LZ_true_rate": {s: v["mean_bounds"] for s, v in lz_slots_full.items()},
            "slot_LZ_summary": lz_slots_full,
            "slot_LCoT_true_rate": {s: v["mean_bounds"] for s, v in lcot_slots_full.items()},
            "slot_LCoT_summary": lcot_slots_full,
            "paired_contrasts": {
                "d1_NI_BARE_minus_NI_COMP_PZ": d1_sum["mean_bounds"],
                "d2_NI_COMP_PZ_minus_MU_Z": d2_sum["mean_bounds"],
                "d3_INT_BARE_minus_INT_COMP_PZ": d3_sum["mean_bounds"],
                "d4_NI_BARE_minus_NI_COMP_LCoT": d4_sum["mean_bounds"],
            },
            "paired_contrasts_summary": {
                "d1_NI_BARE_minus_NI_COMP_PZ": d1_sum,
                "d2_NI_COMP_PZ_minus_MU_Z": d2_sum,
                "d3_INT_BARE_minus_INT_COMP_PZ": d3_sum,
                "d4_NI_BARE_minus_NI_COMP_LCoT": d4_sum,
            },
        }

    # 4. Layer 3.3: All 13 (task, prompt) conditions across 4 main slots (+ 2 diagnostic slots for P/Z and L/Z)
    # Includes telic, atelic, A_plan, and A_pure with mean_bounds, ci_95, endpoint_path_sd, and paired_contrasts
    all_13_conditions: Dict[str, Any] = {}
    for task, prompt in ALL_13_COMBINATIONS:
        cond_key = f"{task}/{prompt}"
        all_13_conditions[cond_key] = {
            g_name: group_13_trajectories[g_name][cond_key]
            for g_name in ("telic", "atelic", "A_plan", "A_pure")
        }

    # 5. Layer 3.4: Complete 3-label (True/False/Unknown) & first-token symmetric log-odds q table for L tasks
    l_trilabel_and_q_table: Dict[str, Any] = {}
    for prompt in ("Z", "DAP", "CoT", "CF"):
        cond_key = f"L/{prompt}"
        l_trilabel_and_q_table[cond_key] = {}
        for g_name, m_cids, w_grp in (
            ("telic", telic_cids, w_t),
            ("atelic", atelic_cids, w_a),
            ("A_plan", a_plan_cids, w_aplan),
            ("A_pure", a_pure_cids, w_apure),
        ):
            l_trilabel_and_q_table[cond_key][g_name] = {}
            for s in MAIN_4_SLOTS:
                rows_s = [get_row(cid, s, "L", prompt) for cid in m_cids]
                n_tot = len(m_cids)
                counts_ok = {"True": 0, "False": 0, "Unknown": 0, "missing": 0}
                counts_lbl_avail = {"True": 0, "False": 0, "Unknown": 0, "missing": 0}
                label_bounds_by_cat: Dict[str, List[Tuple[float, float]]] = {
                    "True": [],
                    "False": [],
                    "Unknown": [],
                }
                q_bounds_list: List[Tuple[float, float]] = []
                q_status_counts = {"full": 0, "bounded": 0, "missing": 0}
                for r in rows_s:
                    st = (r or {}).get("status")
                    lbl = (r or {}).get("label")
                    if st == "ok" and lbl in ("True", "False", "Unknown"):
                        counts_ok[lbl] += 1
                        for cat in ("True", "False", "Unknown"):
                            ind = 1.0 if lbl == cat else 0.0
                            label_bounds_by_cat[cat].append((ind, ind))
                    else:
                        counts_ok["missing"] += 1
                        for cat in ("True", "False", "Unknown"):
                            label_bounds_by_cat[cat].append((0.0, 1.0))
                    if st in ("ok", "missing_score") and lbl in ("True", "False", "Unknown"):
                        counts_lbl_avail[lbl] += 1
                    else:
                        counts_lbl_avail["missing"] += 1
                    q_obj = (r or {}).get("q") or {}
                    qs = q_obj.get("q_status", "")
                    ql, qu = q_obj.get("q_L"), q_obj.get("q_U")
                    if st == "ok" and qs in ("full", "bounded") and isinstance(ql, (int, float)) and isinstance(qu, (int, float)):
                        q_status_counts[qs] += 1
                        q_bounds_list.append((float(ql), float(qu)))
                    else:
                        q_status_counts["missing"] += 1
                        q_bounds_list.append((0.0, 1.0))
                q_sum = _bounds_mean_sd(q_bounds_list, w_mat=w_grp)
                true_sum = _bounds_mean_sd(label_bounds_by_cat["True"], w_mat=w_grp)
                false_sum = _bounds_mean_sd(label_bounds_by_cat["False"], w_mat=w_grp)
                unk_sum = _bounds_mean_sd(label_bounds_by_cat["Unknown"], w_mat=w_grp)
                l_trilabel_and_q_table[cond_key][g_name][s] = {
                    "n_clusters": n_tot,
                    "counts_status_ok": counts_ok,
                    "rates_status_ok": {k: float(v) / float(n_tot) for k, v in counts_ok.items()} if n_tot else {},
                    "label_rate_bounds_and_ci95": {
                        "True": true_sum,
                        "False": false_sum,
                        "Unknown": unk_sum,
                    },
                    "counts_label_available": counts_lbl_avail,
                    "q_status_counts": q_status_counts,
                    "q_mean_bounds": q_sum["mean_bounds"],
                    "q_ci_95": q_sum["ci_95"],
                    "q_endpoint_path_sd": q_sum["endpoint_path_sd"],
                }

    # 6. Layer 3.5: Metalanguage channel decomposition M_W - M_U across M/Z, M/DAP, M/CoT, M/CF
    metalanguage_mw_minus_mu: Dict[str, Any] = {}
    for prompt in ("Z", "DAP", "CoT", "CF"):
        cond_key = f"M/{prompt}"
        metalanguage_mw_minus_mu[cond_key] = {}
        for g_name, m_cids, w_grp in (
            ("telic", telic_cids, w_t),
            ("atelic", atelic_cids, w_a),
            ("A_plan", a_plan_cids, w_aplan),
            ("A_pure", a_pure_cids, w_apure),
        ):
            within_slot: Dict[str, List[float]] = {}
            within_slot_summary: Dict[str, Dict[str, List[float]]] = {}
            for s in MAIN_4_SLOTS:
                mu_b = [extract_unit_continuous_bounds(get_row(cid, s, "M", prompt), "M_U") for cid in m_cids]
                mw_b = [extract_unit_continuous_bounds(get_row(cid, s, "M", prompt), "M_W") for cid in m_cids]
                d_lo_m, d_hi_m = _paired_diff_bounds(mw_b, mu_b)
                s_sum = _bounds_mean_sd(list(zip(d_lo_m.tolist(), d_hi_m.tolist())), w_mat=w_grp)
                within_slot[s] = s_sum["mean_bounds"]
                within_slot_summary[s] = s_sum
            mw_ni_bare = [extract_unit_continuous_bounds(get_row(cid, "NI_BARE", "M", prompt), "M_W") for cid in m_cids]
            mu_ni_comp = [extract_unit_continuous_bounds(get_row(cid, "NI_COMP", "M", prompt), "M_U") for cid in m_cids]
            ni_cross_lo, ni_cross_hi = _paired_diff_bounds(mw_ni_bare, mu_ni_comp)
            ni_cross_sum = _bounds_mean_sd(list(zip(ni_cross_lo.tolist(), ni_cross_hi.tolist())), w_mat=w_grp)

            mw_int_bare = [extract_unit_continuous_bounds(get_row(cid, "INT_BARE", "M", prompt), "M_W") for cid in m_cids]
            mu_int_comp = [extract_unit_continuous_bounds(get_row(cid, "INT_COMP", "M", prompt), "M_U") for cid in m_cids]
            int_cross_lo, int_cross_hi = _paired_diff_bounds(mw_int_bare, mu_int_comp)
            int_cross_sum = _bounds_mean_sd(list(zip(int_cross_lo.tolist(), int_cross_hi.tolist())), w_mat=w_grp)

            metalanguage_mw_minus_mu[cond_key][g_name] = {
                "within_slot_MW_minus_MU": within_slot,
                "within_slot_MW_minus_MU_summary": within_slot_summary,
                "cross_slot_MW_NI_BARE_minus_MU_NI_COMP": ni_cross_sum["mean_bounds"],
                "cross_slot_MW_NI_BARE_minus_MU_NI_COMP_summary": ni_cross_sum,
                "cross_slot_MW_INT_BARE_minus_MU_INT_COMP": int_cross_sum["mean_bounds"],
                "cross_slot_MW_INT_BARE_minus_MU_INT_COMP_summary": int_cross_sum,
            }

    # 7. Layer 3.6: Cross-macro-class strictly same-form (T vs A) AUC and interruption drop comparisons
    # Per PLAN-E2.md §4.3 (line 283):
    # - h_comp slots (NI_COMP, INT_COMP, and drop NI_COMP - INT_COMP): restricted to '完'-complement
    #   telic clusters (12 formal / 4 dev) vs A_plan '完'-complement clusters (16 formal / 4 dev).
    # - h_bare slots (NI_BARE, INT_BARE, and drop NI_BARE - INT_BARE): full T (48/12) vs full A (32/8).
    cross_macro_same_form: Dict[str, Any] = {
        "same_form_PZ": {},
        "same_form_LZ": {},
        "same_form_LCoT": {},
        "interruption_drop_PZ": {},
    }
    for s in MAIN_4_SLOTS:
        if s in ("NI_COMP", "INT_COMP"):
            t_sub_cids, w_t_sub = telic_wan_cids, w_t_wan
            a_sub_cids, w_a_sub = a_plan_wan_cids, w_aplan
            comp_scope = "T_wan_vs_A_plan_wan_h_comp"
            comp_key = f"{s}_T_wan_vs_A_plan_wan"
        else:
            t_sub_cids, w_t_sub = telic_cids, w_t
            a_sub_cids, w_a_sub = atelic_cids, w_a
            comp_scope = "T_all_vs_A_all_h_bare"
            comp_key = f"{s}_T_vs_A"

        t_pz = [extract_unit_continuous_bounds(get_row(cid, s, "P", "Z"), "value") for cid in t_sub_cids]
        a_pz = [extract_unit_continuous_bounds(get_row(cid, s, "P", "Z"), "value") for cid in a_sub_cids]
        pz_entry = {
            "comparison_scope": comp_scope,
            "n_telic": len(t_sub_cids),
            "telic_cluster_ids": t_sub_cids,
            "n_atelic": len(a_sub_cids),
            "atelic_cluster_ids": a_sub_cids,
            "telic_summary": _bounds_mean_sd(t_pz, w_mat=w_t_sub),
            "atelic_summary": _bounds_mean_sd(a_pz, w_mat=w_a_sub),
            **_mann_whitney_auc_bounds(t_pz, a_pz, w_x=w_t_sub, w_y=w_a_sub),
        }
        cross_macro_same_form["same_form_PZ"][comp_key] = pz_entry
        cross_macro_same_form["same_form_PZ"][f"{s}_T_vs_A"] = pz_entry

        for l_prompt, dict_key in (("Z", "same_form_LZ"), ("CoT", "same_form_LCoT")):
            t_l = [extract_unit_label_true_bounds(get_row(cid, s, "L", l_prompt), False) for cid in t_sub_cids]
            a_l = [extract_unit_label_true_bounds(get_row(cid, s, "L", l_prompt), False) for cid in a_sub_cids]
            l_entry = {
                "comparison_scope": comp_scope,
                "n_telic": len(t_sub_cids),
                "telic_cluster_ids": t_sub_cids,
                "n_atelic": len(a_sub_cids),
                "atelic_cluster_ids": a_sub_cids,
                "telic_summary": _bounds_mean_sd(t_l, w_mat=w_t_sub),
                "atelic_summary": _bounds_mean_sd(a_l, w_mat=w_a_sub),
                **_mann_whitney_auc_bounds(t_l, a_l, w_x=w_t_sub, w_y=w_a_sub),
            }
            cross_macro_same_form[dict_key][comp_key] = l_entry
            cross_macro_same_form[dict_key][f"{s}_T_vs_A"] = l_entry

    # Interruption drop under identical hypothesis form (NI_COMP - INT_COMP on '完' subset; NI_BARE - INT_BARE on full T vs A)
    for form_tag, ni_slot, int_slot in (("h_comp", "NI_COMP", "INT_COMP"), ("h_bare", "NI_BARE", "INT_BARE")):
        if form_tag == "h_comp":
            t_sub_cids, w_t_sub = telic_wan_cids, w_t_wan
            a_sub_cids, w_a_sub = a_plan_wan_cids, w_aplan
            comp_scope = "T_wan_vs_A_plan_wan_h_comp"
        else:
            t_sub_cids, w_t_sub = telic_cids, w_t
            a_sub_cids, w_a_sub = atelic_cids, w_a
            comp_scope = "T_all_vs_A_all_h_bare"

        t_ni = [extract_unit_continuous_bounds(get_row(cid, ni_slot, "P", "Z"), "value") for cid in t_sub_cids]
        t_int = [extract_unit_continuous_bounds(get_row(cid, int_slot, "P", "Z"), "value") for cid in t_sub_cids]
        t_drop_lo, t_drop_hi = _paired_diff_bounds(t_ni, t_int)
        t_drop_bounds = list(zip(t_drop_lo.tolist(), t_drop_hi.tolist()))
        t_drop_sum = _bounds_mean_sd(t_drop_bounds, w_mat=w_t_sub)

        a_ni = [extract_unit_continuous_bounds(get_row(cid, ni_slot, "P", "Z"), "value") for cid in a_sub_cids]
        a_int = [extract_unit_continuous_bounds(get_row(cid, int_slot, "P", "Z"), "value") for cid in a_sub_cids]
        a_drop_lo, a_drop_hi = _paired_diff_bounds(a_ni, a_int)
        a_drop_bounds = list(zip(a_drop_lo.tolist(), a_drop_hi.tolist()))
        a_drop_sum = _bounds_mean_sd(a_drop_bounds, w_mat=w_a_sub)

        cross_macro_same_form["interruption_drop_PZ"][f"drop_{form_tag}_{ni_slot}_minus_{int_slot}"] = {
            "comparison_scope": comp_scope,
            "n_telic": len(t_sub_cids),
            "telic_cluster_ids": t_sub_cids,
            "n_atelic": len(a_sub_cids),
            "atelic_cluster_ids": a_sub_cids,
            "telic_drop_mean_bounds": t_drop_sum["mean_bounds"],
            "telic_drop_ci_95": t_drop_sum["ci_95"],
            "telic_drop_endpoint_path_sd": t_drop_sum["endpoint_path_sd"],
            "atelic_drop_mean_bounds": a_drop_sum["mean_bounds"],
            "atelic_drop_ci_95": a_drop_sum["ci_95"],
            "atelic_drop_endpoint_path_sd": a_drop_sum["endpoint_path_sd"],
            "T_vs_A": _mann_whitney_auc_bounds(t_drop_bounds, a_drop_bounds, w_x=w_t_sub, w_y=w_a_sub),
        }

    return {
        "stage": stage,
        "seed": int(seed),
        "b": int(b),
        "n_telic": n_t,
        "n_atelic": n_a,
        "calibration_binding": binding,
        "primary_method": primary_method,
        "demoted_slots": list(demoted_slots),
        "primary_family": primary_family,
        "companion_family": companion_family,
        "e2_h4_label_available_companion": h4_label_available_diag,
        "layer3_atelic_subclass_decomposition": subclass_decomp,
        "layer3_six_subclasses_summary": six_subclasses_summary,
        "layer3_all_13_conditions_four_slots": all_13_conditions,
        "layer3_l_task_trilabel_and_q_table": l_trilabel_and_q_table,
        "layer3_metalanguage_mw_minus_mu": metalanguage_mw_minus_mu,
        "layer3_cross_macro_same_form_auc_and_int_drop": cross_macro_same_form,
    }
