"""Core statistical inference engine for Scheme A Step 5b (m=4 confirmatory family).

Includes:
- Preserved P16.4.5 cluster-paired percentile (`infer_percentile_a`) and studentized (`infer_studentized_a`)
  engines on shared multinomial bootstrap streams (TOL_DUST = 1e-12, 1-based ranks [32, 4969] and [13, 4988]);
- Deterministic 70-digit pure-Python `decimal` solver for finite-sample normal/Student-t quantile expansion
  constants c_n = sqrt(n / (n - 1)) * t_{n - 1, 0.99375} / z_{0.99375} (c_80 = 1.0298684039340295...,
  c_20 = 1.1331397732007173...);
- Candidate 1 (`infer_hybrid_pct_tango_a`): continuous slots SA2, SA3 via cluster-paired percentile +
  discrete trinary slots SA1, SA4 via certified unconditional exact Tango score-ordering lookup;
- Candidate 2 (`infer_hybrid_bessel_t_tango_a`): continuous slots SA2, SA3 via outward Bessel-t expanded
  cluster-paired resampling (complete degeneracy check BEFORE [-200, 200] theoretical domain intersection) +
  discrete trinary slots SA1, SA4 via certified unconditional exact Tango score-ordering lookup;
- Holm step-down testing (`m = 4`, alpha = 0.05) and exact rational truth assessment (`assess_a`).
"""

from decimal import Decimal, localcontext
from fractions import Fraction
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np

try:
    from .exact_tango import DEFAULT_TABLES_NPZ, infer_exact_tango_slot, load_certified_tango_tables
    from .inputs import ClusterSampleA
except (ImportError, ValueError):
    import sys
    _code_dir = Path(__file__).resolve().parent
    if str(_code_dir) not in sys.path:
        sys.path.insert(0, str(_code_dir))
    from exact_tango import DEFAULT_TABLES_NPZ, infer_exact_tango_slot, load_certified_tango_tables
    from inputs import ClusterSampleA

NAMES_A = ("SA1", "SA2", "SA3", "SA4")
ONE_SIDED_A = np.array([True, False, False, False], dtype=bool)
DOMAINS_A = np.array([[-1.0, 1.0], [-200.0, 200.0], [-200.0, 200.0], [-1.0, 1.0]], dtype=np.float64)
TOL_DUST = 1e-12

# Ranks for B=5000 (0-based indices)
# Main 98.75% CI (面向 m=4 Bonferroni 95% 家族同时覆盖目标): 1-based [32, 4969] -> 0-based [31, 4968]
RANK_MAIN_LO = 31
RANK_MAIN_HI = 4968

# Historical 99.5% CI (面向旧 m=10 Bonferroni 95% 家族同时覆盖目标): 1-based [13, 4988] -> 0-based [12, 4987]
RANK_HIST_LO = 12
RANK_HIST_HI = 4987

MAIN_QUANTILE_STR = "0.99375"  # 1 - alpha_ind_main / 2 = 1 - 0.0125 / 2

_BESSEL_T_CACHE: Dict[Tuple[int, str], Dict[str, Any]] = {}


def _decimal_atan_small(x: Decimal, eps: Decimal) -> Decimal:
    """Taylor series atan(x) for |x| <= 0.25 in active Decimal context."""
    x2 = x * x
    term = x
    total = x
    k = 1
    while True:
        term = -term * x2
        denom = Decimal(2 * k + 1)
        contrib = term / denom
        total += contrib
        if abs(contrib) <= eps:
            break
        k += 1
    return total


def _decimal_pi(eps: Decimal) -> Decimal:
    """Compute pi in active Decimal context via Machin's identity pi/4 = 4*atan(1/5) - atan(1/239)."""
    one = Decimal(1)
    a1 = _decimal_atan_small(one / Decimal(5), eps)
    a2 = _decimal_atan_small(one / Decimal(239), eps)
    return Decimal(4) * (Decimal(4) * a1 - a2)


def _decimal_atan_nonneg(u: Decimal, pi_val: Decimal, eps: Decimal) -> Decimal:
    """Compute atan(u) for u >= 0 in active Decimal context using 5 halving steps + Taylor series."""
    if u == 0:
        return Decimal(0)
    one = Decimal(1)
    inv = False
    x = u
    if x > one:
        inv = True
        x = one / x
    for _ in range(5):
        x = x / (one + (one + x * x).sqrt())
    val = Decimal(32) * _decimal_atan_small(x, eps / Decimal(64))
    if inv:
        return (pi_val / Decimal(2)) - val
    return val


def _decimal_normal_cdf_nonneg(z: Decimal, sqrt_2pi: Decimal, eps: Decimal) -> Decimal:
    """Exact alternating power series for standard normal CDF Phi(z) on z >= 0."""
    if z == 0:
        return Decimal("0.5")
    neg_half_z2 = -(z * z) / Decimal(2)
    term_pow = z  # (-z^2/2)^k * z / k!
    total = z
    k = 1
    while True:
        term_pow = term_pow * neg_half_z2 / Decimal(k)
        contrib = term_pow / Decimal(2 * k + 1)
        total += contrib
        if abs(contrib) <= eps and k >= int(z * z) + 4:
            break
        k += 1
    return Decimal("0.5") + total / sqrt_2pi


def _decimal_student_t_cdf_nonneg(t: Decimal, nu: int, pi_val: Decimal, eps: Decimal) -> Decimal:
    """Exact closed-form finite trigonometric recurrence for Student-t CDF F_nu(t) on t >= 0, integer nu >= 1."""
    if nu < 1:
        raise ValueError(f"Degrees of freedom nu must be >= 1, got {nu}")
    if t == 0:
        return Decimal("0.5")
    nu_d = Decimal(nu)
    sqrt_nu = nu_d.sqrt()
    denom_sq = nu_d + t * t
    sqrt_denom = denom_sq.sqrt()
    cos_th = sqrt_nu / sqrt_denom
    sin_th = t / sqrt_denom
    cos2 = nu_d / denom_sq

    if nu % 2 == 1:
        theta = _decimal_atan_nonneg(t / sqrt_nu, pi_val, eps)
        k = (nu - 1) // 2
        if k == 0:
            return Decimal("0.5") + theta / pi_val
        coeff = Decimal(1)
        pow_c2 = Decimal(1)
        poly = Decimal(1)
        for j in range(1, k):
            coeff = coeff * Decimal(2 * j) / Decimal(2 * j + 1)
            pow_c2 = pow_c2 * cos2
            poly += coeff * pow_c2
        return Decimal("0.5") + (theta + sin_th * cos_th * poly) / pi_val

    # Even nu = 2k (k >= 1)
    k = nu // 2
    coeff = Decimal(1)
    pow_c2 = Decimal(1)
    poly = Decimal(1)
    for j in range(1, k):
        coeff = coeff * Decimal(2 * j - 1) / Decimal(2 * j)
        pow_c2 = pow_c2 * cos2
        poly += coeff * pow_c2
    return Decimal("0.5") + (sin_th * poly) / Decimal(2)


def compute_bessel_t_constants_decimal(
    n: int,
    q_str: str = MAIN_QUANTILE_STR,
    sig_digits: int = 70,
) -> Dict[str, Any]:
    """Deterministically solve z_q, t_{n-1, q}, and c_n to `sig_digits` significant digits in stdlib `decimal`."""
    if n < 2:
        raise ValueError(f"Sample size n must be >= 2, got {n}")
    cache_key = (int(n), str(q_str))
    if sig_digits == 70 and cache_key in _BESSEL_T_CACHE:
        return _BESSEL_T_CACHE[cache_key]

    work_prec = max(92, sig_digits + 22)
    nu = int(n) - 1
    with localcontext() as ctx:
        ctx.prec = work_prec
        q_target = Decimal(q_str)
        if not (Decimal("0.5") < q_target < Decimal(1)):
            raise ValueError(f"Quantile q_str must be in (0.5, 1), got {q_str}")
        eps = Decimal(10) ** (-(work_prec - 4))
        pi_val = _decimal_pi(eps)
        sqrt_2pi = (Decimal(2) * pi_val).sqrt()

        # Monotone bisection for z_q on [0, hi]
        z_lo = Decimal(0)
        z_hi = Decimal(8)
        while _decimal_normal_cdf_nonneg(z_hi, sqrt_2pi, eps) < q_target:
            z_hi *= Decimal(2)
        for _ in range(320):
            z_mid = (z_lo + z_hi) / Decimal(2)
            if _decimal_normal_cdf_nonneg(z_mid, sqrt_2pi, eps) < q_target:
                z_lo = z_mid
            else:
                z_hi = z_mid
        z_q = (z_lo + z_hi) / Decimal(2)

        # Monotone bisection for t_{nu, q} on [0, hi]
        t_lo = Decimal(0)
        t_hi = Decimal(16)
        while _decimal_student_t_cdf_nonneg(t_hi, nu, pi_val, eps) < q_target:
            t_hi *= Decimal(2)
        for _ in range(320):
            t_mid = (t_lo + t_hi) / Decimal(2)
            if _decimal_student_t_cdf_nonneg(t_mid, nu, pi_val, eps) < q_target:
                t_lo = t_mid
            else:
                t_hi = t_mid
        t_q = (t_lo + t_hi) / Decimal(2)

        bessel_factor = (Decimal(n) / Decimal(n - 1)).sqrt()
        c_n_dec = bessel_factor * (t_q / z_q)

    with localcontext() as fmt_ctx:
        fmt_ctx.prec = sig_digits
        z_str = str(+z_q)
        t_str = str(+t_q)
        c_str = str(+c_n_dec)

    out = {
        "n": int(n),
        "df": nu,
        "quantile": str(q_str),
        "significant_digits": int(sig_digits),
        "z_q_decimal70": z_str,
        "t_df_q_decimal70": t_str,
        "c_n_decimal70": c_str,
        "z_q_float": float(Decimal(z_str)),
        "t_df_q_float": float(Decimal(t_str)),
        "c_n_float": float(Decimal(c_str)),
    }
    if sig_digits == 70:
        _BESSEL_T_CACHE[cache_key] = out
    return out


def get_bessel_t_expansion_factor(n: int) -> float:
    """Return binary64 expansion factor c_n = sqrt(n/(n-1)) * t_{n-1, 0.99375} / z_{0.99375}."""
    return float(compute_bessel_t_constants_decimal(n, MAIN_QUANTILE_STR, sig_digits=70)["c_n_float"])


def _greedy_distinct_1d_sorted(col: np.ndarray, tol: float) -> int:
    """Reference greedy anchor distinct count on an already-sorted 1D array."""
    if len(col) == 0:
        return 0
    anchor = col[0]
    c = 1
    for val in col[1:]:
        if val - anchor > tol:
            c += 1
            anchor = val
    return c


def _sorted_distinct_col(col: np.ndarray, tol: float = TOL_DUST) -> Tuple[int, int]:
    """Return (distinct_tol, distinct_tol0) on an already-sorted 1D column (exact match to greedy loop)."""
    n = len(col)
    if n <= 1:
        return n, n
    if not (np.isfinite(col[0]) and np.isfinite(col[-1])):
        return _greedy_distinct_1d_sorted(col, tol), int(len(np.unique(col)))

    diffs = np.diff(col)
    nz = diffs > 0.0
    c_tol0 = 1 + int(np.count_nonzero(nz))
    if tol <= 0.0:
        return c_tol0, c_tol0

    c_gt = int(np.count_nonzero(diffs > tol))
    if c_gt == c_tol0 - 1:
        return c_tol0, c_tol0

    u = np.empty(c_tol0, dtype=col.dtype)
    u[0] = col[0]
    u[1:] = col[1:][nz]
    return _greedy_distinct_1d_sorted(u, tol), c_tol0


def _sorted_distinct_both_2d(sorted_arr: np.ndarray, tol: float = TOL_DUST) -> Tuple[np.ndarray, np.ndarray]:
    """Compute (counts_tol, counts_tol0) across columns of an already-sorted 2D array (B, m)."""
    b_size, m_cols = sorted_arr.shape
    if b_size == 0:
        z = np.zeros(m_cols, dtype=int)
        return z, z.copy()
    c_tol = np.empty(m_cols, dtype=int)
    c_tol0 = np.empty(m_cols, dtype=int)
    for j in range(m_cols):
        ct, ct0 = _sorted_distinct_col(sorted_arr[:, j], tol=tol)
        c_tol[j] = ct
        c_tol0[j] = ct0
    return c_tol, c_tol0


def count_distinct_tol(values: np.ndarray, tol: float = TOL_DUST) -> Union[int, np.ndarray]:
    """Count distinct values within a specified tolerance using greedy anchor span."""
    arr = np.asarray(values)
    is_1d = arr.ndim == 1
    if is_1d:
        arr = arr[:, None]
    if arr.ndim != 2:
        raise ValueError(f"Expected 1D or 2D array, got ndim={arr.ndim}")

    b_size, m_cols = arr.shape
    if b_size == 0:
        return 0 if is_1d else np.zeros(m_cols, dtype=int)

    sorted_arr = np.sort(arr, axis=0)
    counts, _ = _sorted_distinct_both_2d(sorted_arr, tol=tol)
    return int(counts[0]) if is_1d else counts


def _paired_weighted_mean(
    weights: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """One effective-support anchor per row for ordered interval means."""
    weights = np.atleast_2d(np.asarray(weights, dtype=np.float64))
    lower = np.asarray(lower, dtype=np.float64)
    upper = np.asarray(upper, dtype=np.float64)

    if lower.ndim != 1 or lower.shape != upper.shape or weights.ndim != 2 or weights.shape[1] != len(lower):
        raise ValueError("paired mean shape mismatch")

    total = weights.sum(axis=1)
    if not np.isfinite(weights).all() or np.any(weights < 0) or not np.isfinite(total).all() or np.any(total <= 0):
        raise ValueError("finite nonnegative weights with positive finite sums required")
    if not np.isfinite([lower, upper]).all() or np.any(lower > upper):
        raise ValueError("ordered finite bounds required")

    active = weights > 0
    first = active.argmax(axis=1)
    lr, ur = lower[first], upper[first]
    lc = np.all(~active | (lower == lr[:, None]), axis=1)
    uc = np.all(~active | (upper == ur[:, None]), axis=1)
    anchor = np.where(uc & ~lc, ur, lr)

    def centered(vector: np.ndarray) -> np.ndarray:
        delta = np.zeros_like(weights)
        np.subtract(vector[None, :], anchor[:, None], out=delta, where=active)
        return anchor + np.sum(weights * delta, axis=1) / total

    if np.array_equal(lower, upper):
        val = centered(lower)
        val[lc] = lr[lc]
        return val, val.copy()

    low, high = centered(lower), centered(upper)
    low[lc] = lr[lc]
    high[uc] = ur[uc]
    return low, high


def _active_linear_variance(weights: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Repaired linear variance anchored at the first active support."""
    weights = np.atleast_2d(np.asarray(weights, dtype=np.float64))
    vector = np.asarray(vector, dtype=np.float64)
    if vector.ndim != 1 or weights.ndim != 2 or weights.shape[1] != len(vector):
        raise ValueError("linear variance shape mismatch")

    n = weights.sum(axis=1)
    if np.any(n <= 1):
        raise ValueError("at least 2 units required for variance")

    active = weights > 0
    first = active.argmax(axis=1)
    ref = vector[first]

    delta = np.zeros_like(weights)
    np.subtract(vector[None, :], ref[:, None], out=delta, where=active)
    mean = ref + np.sum(weights * delta, axis=1) / n

    diff = np.zeros_like(weights)
    np.subtract(vector[None, :], mean[:, None], out=diff, where=active)
    var = np.sum(weights * (diff ** 2), axis=1) / (n * (n - 1))

    active_const = np.all(~active | (vector[None, :] == ref[:, None]), axis=1)
    var[active_const] = 0.0
    return np.maximum(0.0, var)


def extract_slot_contrasts(sample: ClusterSampleA) -> Dict[str, Any]:
    """Extract cluster-level contrast vectors for SA1..SA4 from ClusterSampleA."""
    d1_lower = (sample.ac_cont_lower[:, 1, 0] >= 95.0).astype(np.int64) - (sample.ac_cont_upper[:, 1, 1] >= 95.0).astype(np.int64)
    d1_upper = (sample.ac_cont_upper[:, 1, 0] >= 95.0).astype(np.int64) - (sample.ac_cont_lower[:, 1, 1] >= 95.0).astype(np.int64)

    y2_lower = (sample.ac_cont_lower[:, 1, 0] - sample.ac_cont_upper[:, 0, 0]) - (sample.ac_cont_upper[:, 1, 1] - sample.ac_cont_lower[:, 0, 1])
    y2_upper = (sample.ac_cont_upper[:, 1, 0] - sample.ac_cont_lower[:, 0, 0]) - (sample.ac_cont_lower[:, 1, 1] - sample.ac_cont_upper[:, 0, 1])

    y3_lower = (sample.bd_cont_lower[:, 1, 0] - sample.bd_cont_upper[:, 0, 0]) - (sample.bd_cont_upper[:, 1, 1] - sample.bd_cont_lower[:, 0, 1])
    y3_upper = (sample.bd_cont_upper[:, 1, 0] - sample.bd_cont_lower[:, 0, 0]) - (sample.bd_cont_lower[:, 1, 1] - sample.bd_cont_upper[:, 0, 1])

    d4_lower = sample.bd_l_acc_lower[:, 0].astype(np.int64) - sample.bd_l_acc_upper[:, 1].astype(np.int64)
    d4_upper = sample.bd_l_acc_upper[:, 0].astype(np.int64) - sample.bd_l_acc_lower[:, 1].astype(np.int64)

    return {
        "d1_lower": d1_lower, "d1_upper": d1_upper,
        "y2_lower": y2_lower, "y2_upper": y2_upper,
        "y3_lower": y3_lower, "y3_upper": y3_upper,
        "d4_lower": d4_lower, "d4_upper": d4_upper,
    }


def _single_continuous_mean_and_se(
    weights_f64: np.ndarray,
    total_f64: np.ndarray,
    active: np.ndarray,
    first: np.ndarray,
    vector: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Exact single-pass bit-identical equivalent of (_paired_weighted_mean(w, v, v)[0], sqrt(_active_linear_variance(w, v)))."""
    ref = vector[first]
    active_const = np.all(~active | (vector[None, :] == ref[:, None]), axis=1)

    delta = np.zeros_like(weights_f64)
    np.subtract(vector[None, :], ref[:, None], out=delta, where=active)
    mean_raw = ref + np.sum(weights_f64 * delta, axis=1) / total_f64

    val = mean_raw.copy()
    val[active_const] = ref[active_const]

    diff = np.zeros_like(weights_f64)
    np.subtract(vector[None, :], mean_raw[:, None], out=diff, where=active)
    var = np.sum(weights_f64 * (diff ** 2), axis=1) / (total_f64 * (total_f64 - 1.0))
    var[active_const] = 0.0
    se = np.sqrt(np.maximum(0.0, var))
    return val, se


def _discrete_mean_and_se_i64(
    w_i64: np.ndarray,
    n_i64: np.ndarray,
    denom_f64: np.ndarray,
    d_vec: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Exact 64-bit integer mean and SE for discrete contrast d_vec in {-1, 0, 1}."""
    s = w_i64 @ d_vec
    q = w_i64 @ (d_vec * d_vec)
    mean = s / n_i64
    num = n_i64 * q - (s * s)
    num_pos = np.maximum(0, num)
    var = np.where(num_pos > 0, num_pos.astype(np.float64) / denom_f64, 0.0)
    return mean, np.sqrt(var)


def compute_statistics_and_se(
    contrasts: Dict[str, Any],
    weights_ac: np.ndarray,
    weights_bd: np.ndarray
) -> Tuple[Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]:
    """Compute (theta_lower, theta_upper) and (se_lower, se_upper) for SA1..SA4."""
    wt = np.atleast_2d(weights_ac)
    wa = np.atleast_2d(weights_bd)
    k_batch = len(wt)

    wt_i64 = np.asarray(wt, dtype=np.int64)
    wa_i64 = np.asarray(wa, dtype=np.int64)
    nt = wt_i64.sum(axis=1, dtype=np.int64)
    na = wa_i64.sum(axis=1, dtype=np.int64)
    if np.any(nt <= 1) or np.any(na <= 1):
        raise ValueError("At least 2 clusters required per stratum")

    theta_lower = np.empty((k_batch, 4), dtype=np.float64)
    theta_upper = np.empty((k_batch, 4), dtype=np.float64)
    se_lower = np.empty((k_batch, 4), dtype=np.float64)
    se_upper = np.empty((k_batch, 4), dtype=np.float64)

    denom_ac = (nt * nt * (nt - 1)).astype(np.float64)
    denom_bd = (na * na * (na - 1)).astype(np.float64)

    d1_l = contrasts["d1_lower"]
    d1_u = contrasts["d1_upper"]
    theta_lower[:, 0], se_lower[:, 0] = _discrete_mean_and_se_i64(wt_i64, nt, denom_ac, d1_l)
    if np.array_equal(d1_l, d1_u):
        theta_upper[:, 0] = theta_lower[:, 0]
        se_upper[:, 0] = se_lower[:, 0]
    else:
        theta_upper[:, 0], se_upper[:, 0] = _discrete_mean_and_se_i64(wt_i64, nt, denom_ac, d1_u)

    y2_l = contrasts["y2_lower"]
    y2_u = contrasts["y2_upper"]
    wt_f64 = np.asarray(wt, dtype=np.float64)
    if np.array_equal(y2_l, y2_u):
        active_ac = wt_i64 > 0
        first_ac = active_ac.argmax(axis=1)
        m2, s2 = _single_continuous_mean_and_se(wt_f64, nt.astype(np.float64), active_ac, first_ac, y2_l)
        theta_lower[:, 1] = m2
        theta_upper[:, 1] = m2
        se_lower[:, 1] = s2
        se_upper[:, 1] = s2
    else:
        theta_lower[:, 1], theta_upper[:, 1] = _paired_weighted_mean(wt_f64, y2_l, y2_u)
        se_lower[:, 1] = np.sqrt(_active_linear_variance(wt_f64, y2_l))
        se_upper[:, 1] = np.sqrt(_active_linear_variance(wt_f64, y2_u))

    y3_l = contrasts["y3_lower"]
    y3_u = contrasts["y3_upper"]
    wa_f64 = np.asarray(wa, dtype=np.float64)
    if np.array_equal(y3_l, y3_u):
        active_bd = wa_i64 > 0
        first_bd = active_bd.argmax(axis=1)
        m3, s3 = _single_continuous_mean_and_se(wa_f64, na.astype(np.float64), active_bd, first_bd, y3_l)
        theta_lower[:, 2] = m3
        theta_upper[:, 2] = m3
        se_lower[:, 2] = s3
        se_upper[:, 2] = s3
    else:
        theta_lower[:, 2], theta_upper[:, 2] = _paired_weighted_mean(wa_f64, y3_l, y3_u)
        se_lower[:, 2] = np.sqrt(_active_linear_variance(wa_f64, y3_l))
        se_upper[:, 2] = np.sqrt(_active_linear_variance(wa_f64, y3_u))

    d4_l = contrasts["d4_lower"]
    d4_u = contrasts["d4_upper"]
    theta_lower[:, 3], se_lower[:, 3] = _discrete_mean_and_se_i64(wa_i64, na, denom_bd, d4_l)
    if np.array_equal(d4_l, d4_u):
        theta_upper[:, 3] = theta_lower[:, 3]
        se_upper[:, 3] = se_lower[:, 3]
    else:
        theta_upper[:, 3], se_upper[:, 3] = _discrete_mean_and_se_i64(wa_i64, na, denom_bd, d4_u)

    return (theta_lower, theta_upper), (se_lower, se_upper)


def weight_batches(
    rng: np.random.Generator,
    n_ac: int,
    n_bd: int,
    b: int = 5000,
    batch: int = 256
):
    """Shared multinomial weight generator (AC -> BD, batch = 256)."""
    p_ac = np.full(n_ac, 1.0 / n_ac)
    p_bd = np.full(n_bd, 1.0 / n_bd)
    for start in range(0, b, batch):
        size = min(batch, b - start)
        wt = rng.multinomial(n_ac, p_ac, size=size)
        wa = rng.multinomial(n_bd, p_bd, size=size)
        yield start, wt, wa


def bootstrap_a(
    sample: Union[ClusterSampleA, Dict[str, Any]],
    rng: np.random.Generator,
    b: int = 5000,
    batch: int = 256
) -> Tuple[Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]:
    """Compute bootstrap distribution for SA1..SA4 over B replicates."""
    contrasts = extract_slot_contrasts(sample) if isinstance(sample, ClusterSampleA) else sample
    n_ac = len(contrasts["d1_lower"])
    n_bd = len(contrasts["d4_lower"])

    wt_all = np.empty((b, n_ac), dtype=np.int64)
    wa_all = np.empty((b, n_bd), dtype=np.int64)
    for start, wt, wa in weight_batches(rng, n_ac, n_bd, b=b, batch=batch):
        size = len(wt)
        wt_all[start:start + size] = wt
        wa_all[start:start + size] = wa

    return compute_statistics_and_se(contrasts, wt_all, wa_all)


def compute_observed_a(
    sample: Union[ClusterSampleA, Dict[str, Any]]
) -> Tuple[Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]:
    """Compute point observed estimates and standard errors for SA1..SA4."""
    contrasts = extract_slot_contrasts(sample) if isinstance(sample, ClusterSampleA) else sample
    n_ac = len(contrasts["d1_lower"])
    n_bd = len(contrasts["d4_lower"])
    wt = np.ones((1, n_ac), dtype=np.int64)
    wa = np.ones((1, n_bd), dtype=np.int64)
    (t_lo, t_hi), (s_lo, s_hi) = compute_statistics_and_se(contrasts, wt, wa)
    return (t_lo[0], t_hi[0]), (s_lo[0], s_hi[0])


def holm_m4(p: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Holm step-down procedure for m=4 confirmatory hypotheses."""
    p_arr = np.asarray(p, dtype=np.float64)
    if p_arr.shape != (4,) or not np.all(np.isfinite(p_arr)) or np.any((p_arr < 0.0) | (p_arr > 1.0)):
        raise ValueError("Four finite p-values in [0, 1] required")

    reject = np.zeros(4, dtype=bool)
    order = np.argsort(p_arr, kind="stable")
    for j, idx in enumerate(order):
        threshold = alpha / (4 - j)
        if p_arr[idx] <= threshold:
            reject[idx] = True
        else:
            break
    return reject


def _rank_bounds(b_reps: int) -> Tuple[int, int, int, int]:
    """Return 0-based (r_main_lo, r_main_hi, r_hist_lo, r_hist_hi) for given B."""
    if b_reps == 5000:
        return RANK_MAIN_LO, RANK_MAIN_HI, RANK_HIST_LO, RANK_HIST_HI
    if b_reps < 2:
        raise ValueError(f"b_reps must be >= 2, got {b_reps}")
    r_main_lo = max(0, math.ceil(0.00625 * b_reps) - 1)
    r_main_hi = min(b_reps - 1, math.ceil(0.99375 * b_reps) - 1)
    r_hist_lo = max(0, math.ceil(0.0025 * b_reps) - 1)
    r_hist_hi = min(b_reps - 1, math.ceil(0.9975 * b_reps) - 1)
    return r_main_lo, r_main_hi, r_hist_lo, r_hist_hi


def prepare_sorted_boot_stats(
    boot_lower: np.ndarray,
    boot_upper: np.ndarray,
    tol: float = TOL_DUST,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Sort bootstrap point arrays once and compute (tol, tol=0) distinct counts."""
    low = np.asarray(boot_lower, dtype=np.float64)
    high = np.asarray(boot_upper, dtype=np.float64)
    sorted_low = np.sort(low, axis=0)
    unique_low, unique_low_tol0 = _sorted_distinct_both_2d(sorted_low, tol=tol)
    if np.array_equal(low, high):
        return sorted_low, sorted_low, unique_low, unique_low, unique_low_tol0, unique_low_tol0
    sorted_high = np.sort(high, axis=0)
    unique_high, unique_high_tol0 = _sorted_distinct_both_2d(sorted_high, tol=tol)
    return sorted_low, sorted_high, unique_low, unique_high, unique_low_tol0, unique_high_tol0


def infer_percentile_a(
    boot_lower: np.ndarray,
    boot_upper: np.ndarray,
    observed_lower: np.ndarray,
    observed_upper: np.ndarray,
    precomputed_boot: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = None,
) -> Dict[str, Any]:
    """Historical pure cluster-paired percentile bootstrap inference for m=4."""
    low = np.asarray(boot_lower, dtype=np.float64)
    high = np.asarray(boot_upper, dtype=np.float64)
    obs_lo = np.asarray(observed_lower, dtype=np.float64)
    obs_hi = np.asarray(observed_upper, dtype=np.float64)
    b_reps = len(low)
    rm_lo, rm_hi, rh_lo, rh_hi = _rank_bounds(b_reps)

    obs_dir = np.where(obs_lo > 0.0, 1, np.where(obs_hi < 0.0, -1, 0))

    if precomputed_boot is None:
        sorted_low, sorted_high, unique_low, unique_high, unique_low_tol0, unique_high_tol0 = prepare_sorted_boot_stats(low, high, tol=TOL_DUST)
    else:
        sorted_low, sorted_high, unique_low, unique_high, unique_low_tol0, unique_high_tol0 = precomputed_boot

    ql_main = sorted_low[rm_lo]
    qh_main = sorted_high[rm_hi]
    ci_main = np.stack((ql_main, qh_main), axis=1)

    zero_span_main = np.abs(sorted_low[rm_hi] - sorted_low[rm_lo]) <= TOL_DUST
    zero_span_main |= np.abs(sorted_high[rm_hi] - sorted_high[rm_lo]) <= TOL_DUST
    invalid_ci_main = ~np.all(np.isfinite(ci_main), axis=1) | (ci_main[:, 0] > ci_main[:, 1])
    degenerate_main = (unique_low < 20) | (unique_high < 20) | zero_span_main | invalid_ci_main

    zero_span_tol0 = (sorted_low[rm_hi] == sorted_low[rm_lo]) | (sorted_high[rm_hi] == sorted_high[rm_lo])
    degenerate_tol0 = (unique_low_tol0 < 20) | (unique_high_tol0 < 20) | zero_span_tol0 | invalid_ci_main
    tol_diff = degenerate_main != degenerate_tol0

    ql_hist = sorted_low[rh_lo]
    qh_hist = sorted_high[rh_hi]
    ci_hist = np.stack((ql_hist, qh_hist), axis=1)
    zero_span_hist = np.abs(sorted_low[rh_hi] - sorted_low[rh_lo]) <= TOL_DUST
    zero_span_hist |= np.abs(sorted_high[rh_hi] - sorted_high[rh_lo]) <= TOL_DUST
    invalid_ci_hist = ~np.all(np.isfinite(ci_hist), axis=1) | (ci_hist[:, 0] > ci_hist[:, 1])
    degenerate_hist = (unique_low < 20) | (unique_high < 20) | zero_span_hist | invalid_ci_hist

    pplus = (1.0 + np.sum(low <= 0.0, axis=0)) / (b_reps + 1.0)
    pminus = (1.0 + np.sum(high >= 0.0, axis=0)) / (b_reps + 1.0)

    p = np.where(ONE_SIDED_A, pplus, np.minimum(1.0, 2.0 * np.minimum(pplus, pminus)))
    p[(ONE_SIDED_A & (obs_dir != 1)) | (~ONE_SIDED_A & (obs_dir == 0))] = 1.0

    p[degenerate_main] = 1.0
    ci_main[degenerate_main] = DOMAINS_A[degenerate_main]
    ci_hist[degenerate_hist] = DOMAINS_A[degenerate_hist]

    reject = holm_m4(p)
    direction = np.where(reject, obs_dir, 0)

    return {
        "p": p,
        "pplus": pplus,
        "pminus": pminus,
        "ci": ci_main,
        "degenerate": degenerate_main,
        "ci_995": ci_hist,
        "degenerate_995": degenerate_hist,
        "degenerate_tol0": degenerate_tol0,
        "tol_diff": tol_diff,
        "reject": reject,
        "direction": direction,
        "observed_direction": obs_dir,
        "unique_lower": unique_low.copy(),
        "unique_upper": unique_high.copy(),
        "failure_distinct_boot": (unique_low < 20) | (unique_high < 20) | zero_span_main,
        "failure_observed_se": np.zeros(4, dtype=bool),
        "failure_bootstrap_se": np.zeros(4, dtype=bool),
        "failure_studentized_distribution": np.zeros(4, dtype=bool),
        "failure_ci": invalid_ci_main,
    }


def _resolve_tango_tables_by_n(
    tango_tables: Optional[Dict[int, Dict[str, Any]]],
    n_ac: int,
    n_bd: int,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if tango_tables is None:
        by_n = load_certified_tango_tables(npz_path=npz_path)["by_n"]
    elif "by_n" in tango_tables:
        by_n = tango_tables["by_n"]  # type: ignore[assignment]
    else:
        by_n = tango_tables
    if n_ac not in by_n or n_bd not in by_n:
        raise KeyError(f"Sample sizes (n_ac={n_ac}, n_bd={n_bd}) missing from exact Tango tables")
    return by_n[n_ac], by_n[n_bd]


def infer_hybrid_pct_tango_a(
    sample_or_contrasts: Union[ClusterSampleA, Dict[str, Any]],
    boot_lower: np.ndarray,
    boot_upper: np.ndarray,
    observed_lower: np.ndarray,
    observed_upper: np.ndarray,
    tango_tables: Optional[Dict[int, Dict[str, Any]]] = None,
    precomputed_boot: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = None,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Candidate 1 (`hybrid_pct_tango`, brief.md §3.2(2)):
    - Continuous slots SA2, SA3: cluster-paired percentile resampling (TOL_DUST = 1e-12, fallback [-200, 200]);
    - Discrete slots SA1, SA4: certified unconditional exact Tango score-ordering inference (unique_lower/upper
      recorded diagnostically from shared bootstrap stream without triggering discrete fallback).
    """
    contrasts = (
        extract_slot_contrasts(sample_or_contrasts)
        if isinstance(sample_or_contrasts, ClusterSampleA)
        else sample_or_contrasts
    )
    pct_res = infer_percentile_a(
        boot_lower=boot_lower,
        boot_upper=boot_upper,
        observed_lower=observed_lower,
        observed_upper=observed_upper,
        precomputed_boot=precomputed_boot,
    )

    d1_lo, d1_hi = contrasts["d1_lower"], contrasts["d1_upper"]
    d4_lo, d4_hi = contrasts["d4_lower"], contrasts["d4_upper"]
    tbl_ac, tbl_bd = _resolve_tango_tables_by_n(tango_tables, len(d1_lo), len(d4_lo), npz_path=npz_path)

    ex_sa1 = infer_exact_tango_slot(d1_lo, d1_hi, one_sided=True, tables_for_n=tbl_ac)
    ex_sa4 = infer_exact_tango_slot(d4_lo, d4_hi, one_sided=False, tables_for_n=tbl_bd)

    p = pct_res["p"].copy()
    pplus = pct_res["pplus"].copy()
    pminus = pct_res["pminus"].copy()
    ci_main = pct_res["ci"].copy()
    ci_hist = pct_res["ci_995"].copy()
    degenerate_main = pct_res["degenerate"].copy()
    degenerate_hist = pct_res["degenerate_995"].copy()
    degenerate_tol0 = pct_res["degenerate_tol0"].copy()
    tol_diff = pct_res["tol_diff"].copy()
    obs_dir = pct_res["observed_direction"].copy()
    fail_distinct_boot = pct_res["failure_distinct_boot"].copy()
    fail_ci = pct_res["failure_ci"].copy()

    for slot_idx, ex in ((0, ex_sa1), (3, ex_sa4)):
        p[slot_idx] = ex["p"]
        pplus[slot_idx] = ex["pplus"]
        pminus[slot_idx] = ex["pminus"]
        ci_main[slot_idx] = ex["ci_9875"]
        ci_hist[slot_idx] = ex["ci_995"]
        degenerate_main[slot_idx] = ex["degenerate_9875"]
        degenerate_hist[slot_idx] = ex["degenerate_995"]
        degenerate_tol0[slot_idx] = ex["degenerate_9875"]
        tol_diff[slot_idx] = False
        obs_dir[slot_idx] = ex["observed_direction"]
        fail_distinct_boot[slot_idx] = False
        fail_ci[slot_idx] = ex["failure_ci"]

    reject = holm_m4(p)
    direction = np.where(reject, obs_dir, 0)

    return {
        "p": p,
        "pplus": pplus,
        "pminus": pminus,
        "ci": ci_main,
        "degenerate": degenerate_main,
        "ci_995": ci_hist,
        "degenerate_995": degenerate_hist,
        "degenerate_tol0": degenerate_tol0,
        "tol_diff": tol_diff,
        "reject": reject,
        "direction": direction,
        "observed_direction": obs_dir,
        "unique_lower": pct_res["unique_lower"].copy(),
        "unique_upper": pct_res["unique_upper"].copy(),
        "failure_distinct_boot": fail_distinct_boot,
        "failure_observed_se": np.zeros(4, dtype=bool),
        "failure_bootstrap_se": np.zeros(4, dtype=bool),
        "failure_studentized_distribution": np.zeros(4, dtype=bool),
        "failure_ci": fail_ci,
    }


def infer_hybrid_bessel_t_tango_a(
    sample_or_contrasts: Union[ClusterSampleA, Dict[str, Any]],
    boot_lower: np.ndarray,
    boot_upper: np.ndarray,
    observed_lower: np.ndarray,
    observed_upper: np.ndarray,
    tango_tables: Optional[Dict[int, Dict[str, Any]]] = None,
    precomputed_boot: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = None,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Candidate 2 (`hybrid_bessel_t_tango`, brief.md §3.2(3)):
    - Discrete slots SA1, SA4: certified unconditional exact Tango score-ordering inference (identical to Candidate 1);
    - Continuous slots SA2 (n_ac), SA3 (n_bd): outward order-preserving expansion around observed endpoints by
      70-digit Decimal constant c_n = sqrt(n/(n-1)) * t_{n-1, 0.99375} / z_{0.99375}, complete degeneracy checks
      executed BEFORE intersecting valid finite intervals with theoretical domain [-200, 200].
    """
    contrasts = (
        extract_slot_contrasts(sample_or_contrasts)
        if isinstance(sample_or_contrasts, ClusterSampleA)
        else sample_or_contrasts
    )
    low = np.asarray(boot_lower, dtype=np.float64)
    high = np.asarray(boot_upper, dtype=np.float64)
    obs_lo = np.asarray(observed_lower, dtype=np.float64)
    obs_hi = np.asarray(observed_upper, dtype=np.float64)
    b_reps = len(low)
    rm_lo, rm_hi, rh_lo, rh_hi = _rank_bounds(b_reps)

    if precomputed_boot is None:
        _, _, base_unique_low, base_unique_high, _, _ = prepare_sorted_boot_stats(low, high, tol=TOL_DUST)
    else:
        _, _, base_unique_low, base_unique_high, _, _ = precomputed_boot

    d1_lo, d1_hi = contrasts["d1_lower"], contrasts["d1_upper"]
    d4_lo, d4_hi = contrasts["d4_lower"], contrasts["d4_upper"]
    n_ac = len(d1_lo)
    n_bd = len(d4_lo)

    c_ac = get_bessel_t_expansion_factor(n_ac)
    c_bd = get_bessel_t_expansion_factor(n_bd)
    c_cont = np.array([c_ac, c_bd], dtype=np.float64)  # columns [SA2, SA3]

    low_cont = low[:, 1:3]
    high_cont = high[:, 1:3]
    obs_lo_cont = obs_lo[1:3]
    obs_hi_cont = obs_hi[1:3]

    with np.errstate(over="ignore", invalid="ignore"):
        tilde_low_cont = np.minimum(
            low_cont,
            obs_lo_cont[None, :] + c_cont[None, :] * (low_cont - obs_lo_cont[None, :]),
        )
        tilde_high_cont = np.maximum(
            high_cont,
            obs_hi_cont[None, :] + c_cont[None, :] * (high_cont - obs_hi_cont[None, :]),
        )

    s_low_c, s_high_c, u_low_c, u_high_c, u_low_c_tol0, u_high_c_tol0 = prepare_sorted_boot_stats(
        tilde_low_cont, tilde_high_cont, tol=TOL_DUST
    )

    obs_dir_cont = np.where(obs_lo_cont > 0.0, 1, np.where(obs_hi_cont < 0.0, -1, 0))

    raw_ci_main_c = np.stack((s_low_c[rm_lo], s_high_c[rm_hi]), axis=1)  # shape (2, 2)
    zero_span_main_c = (np.abs(s_low_c[rm_hi] - s_low_c[rm_lo]) <= TOL_DUST) | (
        np.abs(s_high_c[rm_hi] - s_high_c[rm_lo]) <= TOL_DUST
    )
    # Complete degeneracy check BEFORE intersecting with [-200.0, 200.0] (also flags empty intersection)
    invalid_ci_main_c = (
        ~np.all(np.isfinite(raw_ci_main_c), axis=1)
        | (raw_ci_main_c[:, 0] > raw_ci_main_c[:, 1])
        | (raw_ci_main_c[:, 0] > 200.0)
        | (raw_ci_main_c[:, 1] < -200.0)
    )
    fail_distinct_c = (u_low_c < 20) | (u_high_c < 20) | zero_span_main_c
    degen_main_c = fail_distinct_c | invalid_ci_main_c

    zero_span_tol0_c = (s_low_c[rm_hi] == s_low_c[rm_lo]) | (s_high_c[rm_hi] == s_high_c[rm_lo])
    degen_tol0_c = (u_low_c_tol0 < 20) | (u_high_c_tol0 < 20) | zero_span_tol0_c | invalid_ci_main_c
    tol_diff_c = degen_main_c != degen_tol0_c

    raw_ci_hist_c = np.stack((s_low_c[rh_lo], s_high_c[rh_hi]), axis=1)
    zero_span_hist_c = (np.abs(s_low_c[rh_hi] - s_low_c[rh_lo]) <= TOL_DUST) | (
        np.abs(s_high_c[rh_hi] - s_high_c[rh_lo]) <= TOL_DUST
    )
    invalid_ci_hist_c = (
        ~np.all(np.isfinite(raw_ci_hist_c), axis=1)
        | (raw_ci_hist_c[:, 0] > raw_ci_hist_c[:, 1])
        | (raw_ci_hist_c[:, 0] > 200.0)
        | (raw_ci_hist_c[:, 1] < -200.0)
    )
    degen_hist_c = (u_low_c < 20) | (u_high_c < 20) | zero_span_hist_c | invalid_ci_hist_c

    # Intersect valid non-degenerate finite intervals with theoretical domain [-200.0, 200.0]
    ci_main_c = np.clip(raw_ci_main_c, -200.0, 200.0)
    ci_main_c[degen_main_c] = DOMAINS_A[1:3][degen_main_c]

    ci_hist_c = np.clip(raw_ci_hist_c, -200.0, 200.0)
    ci_hist_c[degen_hist_c] = DOMAINS_A[1:3][degen_hist_c]

    pplus_c = (1.0 + np.sum(tilde_low_cont <= 0.0, axis=0)) / (b_reps + 1.0)
    pminus_c = (1.0 + np.sum(tilde_high_cont >= 0.0, axis=0)) / (b_reps + 1.0)
    p_c = np.minimum(1.0, 2.0 * np.minimum(pplus_c, pminus_c))
    p_c[obs_dir_cont == 0] = 1.0
    p_c[degen_main_c] = 1.0

    # Discrete slots SA1 and SA4 via certified unconditional exact Tango lookup
    tbl_ac, tbl_bd = _resolve_tango_tables_by_n(tango_tables, n_ac, n_bd, npz_path=npz_path)
    ex_sa1 = infer_exact_tango_slot(d1_lo, d1_hi, one_sided=True, tables_for_n=tbl_ac)
    ex_sa4 = infer_exact_tango_slot(d4_lo, d4_hi, one_sided=False, tables_for_n=tbl_bd)

    p = np.array([ex_sa1["p"], p_c[0], p_c[1], ex_sa4["p"]], dtype=np.float64)
    pplus = np.array([ex_sa1["pplus"], pplus_c[0], pplus_c[1], ex_sa4["pplus"]], dtype=np.float64)
    pminus = np.array([ex_sa1["pminus"], pminus_c[0], pminus_c[1], ex_sa4["pminus"]], dtype=np.float64)

    ci_main = np.empty((4, 2), dtype=np.float64)
    ci_main[0] = ex_sa1["ci_9875"]
    ci_main[1:3] = ci_main_c
    ci_main[3] = ex_sa4["ci_9875"]

    ci_hist = np.empty((4, 2), dtype=np.float64)
    ci_hist[0] = ex_sa1["ci_995"]
    ci_hist[1:3] = ci_hist_c
    ci_hist[3] = ex_sa4["ci_995"]

    degenerate_main = np.array([ex_sa1["degenerate_9875"], degen_main_c[0], degen_main_c[1], ex_sa4["degenerate_9875"]], dtype=bool)
    degenerate_hist = np.array([ex_sa1["degenerate_995"], degen_hist_c[0], degen_hist_c[1], ex_sa4["degenerate_995"]], dtype=bool)
    degenerate_tol0 = np.array([ex_sa1["degenerate_9875"], degen_tol0_c[0], degen_tol0_c[1], ex_sa4["degenerate_9875"]], dtype=bool)
    tol_diff = np.array([False, tol_diff_c[0], tol_diff_c[1], False], dtype=bool)

    obs_dir = np.array([ex_sa1["observed_direction"], obs_dir_cont[0], obs_dir_cont[1], ex_sa4["observed_direction"]], dtype=np.int64)
    unique_low_out = np.array([base_unique_low[0], u_low_c[0], u_low_c[1], base_unique_low[3]], dtype=np.int64)
    unique_high_out = np.array([base_unique_high[0], u_high_c[0], u_high_c[1], base_unique_high[3]], dtype=np.int64)

    fail_distinct_boot = np.array([False, fail_distinct_c[0], fail_distinct_c[1], False], dtype=bool)
    fail_ci = np.array([ex_sa1["failure_ci"], invalid_ci_main_c[0], invalid_ci_main_c[1], ex_sa4["failure_ci"]], dtype=bool)

    reject = holm_m4(p)
    direction = np.where(reject, obs_dir, 0)

    return {
        "p": p,
        "pplus": pplus,
        "pminus": pminus,
        "ci": ci_main,
        "degenerate": degenerate_main,
        "ci_995": ci_hist,
        "degenerate_995": degenerate_hist,
        "degenerate_tol0": degenerate_tol0,
        "tol_diff": tol_diff,
        "reject": reject,
        "direction": direction,
        "observed_direction": obs_dir,
        "unique_lower": unique_low_out,
        "unique_upper": unique_high_out,
        "failure_distinct_boot": fail_distinct_boot,
        "failure_observed_se": np.zeros(4, dtype=bool),
        "failure_bootstrap_se": np.zeros(4, dtype=bool),
        "failure_studentized_distribution": np.zeros(4, dtype=bool),
        "failure_ci": fail_ci,
    }


def infer_studentized_a(
    boot_lower: np.ndarray,
    boot_upper: np.ndarray,
    se_lower: np.ndarray,
    se_upper: np.ndarray,
    observed_lower: np.ndarray,
    observed_upper: np.ndarray,
    observed_se_lower: np.ndarray,
    observed_se_upper: np.ndarray,
    precomputed_boot: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = None,
) -> Dict[str, Any]:
    """Historical studentized bootstrap inference for m=4 (preserved from P16.4.5)."""
    boot = (np.asarray(boot_lower, dtype=np.float64), np.asarray(boot_upper, dtype=np.float64))
    ses = (np.asarray(se_lower, dtype=np.float64), np.asarray(se_upper, dtype=np.float64))
    obs = (np.asarray(observed_lower, dtype=np.float64), np.asarray(observed_upper, dtype=np.float64))
    obs_se = (np.asarray(observed_se_lower, dtype=np.float64), np.asarray(observed_se_upper, dtype=np.float64))
    b_reps = len(boot[0])
    rm_lo, rm_hi, rh_lo, rh_hi = _rank_bounds(b_reps)

    obs_dir = np.where(obs[0] > 0.0, 1, np.where(obs[1] < 0.0, -1, 0))

    if precomputed_boot is None:
        sorted_low, sorted_high, unique_low, unique_high, unique_low_tol0, unique_high_tol0 = prepare_sorted_boot_stats(boot[0], boot[1], tol=TOL_DUST)
    else:
        sorted_low, sorted_high, unique_low, unique_high, unique_low_tol0, unique_high_tol0 = precomputed_boot

    zero_span_boot = np.abs(sorted_low[rm_hi] - sorted_low[rm_lo]) <= TOL_DUST
    zero_span_boot |= np.abs(sorted_high[rm_hi] - sorted_high[rm_lo]) <= TOL_DUST
    zero_span_boot_hist = np.abs(sorted_low[rh_hi] - sorted_low[rh_lo]) <= TOL_DUST
    zero_span_boot_hist |= np.abs(sorted_high[rh_hi] - sorted_high[rh_lo]) <= TOL_DUST

    fail_distinct_boot = (unique_low < 20) | (unique_high < 20) | zero_span_boot
    fail_distinct_boot_hist = (unique_low < 20) | (unique_high < 20) | zero_span_boot_hist

    invalid_obs_se = (~np.isfinite(obs_se[0]) | (obs_se[0] <= TOL_DUST)) | (~np.isfinite(obs_se[1]) | (obs_se[1] <= TOL_DUST))
    invalid_boot_se = np.any(~np.isfinite(ses[0]) | (ses[0] <= TOL_DUST), axis=0) | np.any(~np.isfinite(ses[1]) | (ses[1] <= TOL_DUST), axis=0)

    invalid_obs_se_tol0 = (~np.isfinite(obs_se[0]) | (obs_se[0] <= 0.0)) | (~np.isfinite(obs_se[1]) | (obs_se[1] <= 0.0))
    invalid_boot_se_tol0 = np.any(~np.isfinite(ses[0]) | (ses[0] <= 0.0), axis=0) | np.any(~np.isfinite(ses[1]) | (ses[1] <= 0.0), axis=0)

    sides_identical = (
        (sorted_high is sorted_low)
        and np.array_equal(ses[0], ses[1])
        and np.array_equal(obs[0], obs[1])
        and np.array_equal(obs_se[0], obs_se[1])
    )

    valid_mask_lo = np.isfinite(ses[0]) & (ses[0] > TOL_DUST)
    t_lo = np.zeros_like(boot[0])
    np.divide(boot[0] - obs[0][None, :], ses[0], out=t_lo, where=valid_mask_lo)

    valid_mask_lo0 = np.isfinite(ses[0]) & (ses[0] > 0.0)
    if np.array_equal(valid_mask_lo, valid_mask_lo0):
        t_lo0 = t_lo
    else:
        t_lo0 = np.zeros_like(boot[0])
        np.divide(boot[0] - obs[0][None, :], ses[0], out=t_lo0, where=valid_mask_lo0)

    sorted_t_low = np.sort(t_lo, axis=0)
    distinct_t_low, _dt_lo_same = _sorted_distinct_both_2d(sorted_t_low, tol=TOL_DUST)
    if t_lo0 is t_lo:
        sorted_t_low0 = sorted_t_low
        distinct_t_low_tol0 = _dt_lo_same
    else:
        sorted_t_low0 = np.sort(t_lo0, axis=0)
        _, distinct_t_low_tol0 = _sorted_distinct_both_2d(sorted_t_low0, tol=0.0)

    if sides_identical:
        t_hi = t_lo
        sorted_t_high = sorted_t_low
        sorted_t_high0 = sorted_t_low0
        distinct_t_high = distinct_t_low
        distinct_t_high_tol0 = distinct_t_low_tol0
    else:
        valid_mask_hi = np.isfinite(ses[1]) & (ses[1] > TOL_DUST)
        t_hi = np.zeros_like(boot[1])
        np.divide(boot[1] - obs[1][None, :], ses[1], out=t_hi, where=valid_mask_hi)

        valid_mask_hi0 = np.isfinite(ses[1]) & (ses[1] > 0.0)
        if np.array_equal(valid_mask_hi, valid_mask_hi0):
            t_hi0 = t_hi
        else:
            t_hi0 = np.zeros_like(boot[1])
            np.divide(boot[1] - obs[1][None, :], ses[1], out=t_hi0, where=valid_mask_hi0)

        sorted_t_high = np.sort(t_hi, axis=0)
        distinct_t_high, _dt_hi_same = _sorted_distinct_both_2d(sorted_t_high, tol=TOL_DUST)
        if t_hi0 is t_hi:
            sorted_t_high0 = sorted_t_high
            distinct_t_high_tol0 = _dt_hi_same
        else:
            sorted_t_high0 = np.sort(t_hi0, axis=0)
            _, distinct_t_high_tol0 = _sorted_distinct_both_2d(sorted_t_high0, tol=0.0)

    ts = (t_lo, t_hi)

    zero_span_t_main = np.abs(sorted_t_low[rm_hi] - sorted_t_low[rm_lo]) <= TOL_DUST
    zero_span_t_main |= np.abs(sorted_t_high[rm_hi] - sorted_t_high[rm_lo]) <= TOL_DUST
    fail_t_main = (distinct_t_low < 20) | (distinct_t_high < 20) | zero_span_t_main

    zero_span_t_hist = np.abs(sorted_t_low[rh_hi] - sorted_t_low[rh_lo]) <= TOL_DUST
    zero_span_t_hist |= np.abs(sorted_t_high[rh_hi] - sorted_t_high[rh_lo]) <= TOL_DUST
    fail_t_hist = (distinct_t_low < 20) | (distinct_t_high < 20) | zero_span_t_hist

    qt_low_hi = sorted_t_low[rm_hi]
    qt_high_lo = sorted_t_high[rm_lo]
    with np.errstate(over="ignore", invalid="ignore"):
        ci_main = np.stack((obs[0] - qt_low_hi * obs_se[0], obs[1] - qt_high_lo * obs_se[1]), axis=1)
    fail_ci_main = ~np.all(np.isfinite(ci_main), axis=1) | (ci_main[:, 0] > ci_main[:, 1])

    qt_low_hi_hist = sorted_t_low[rh_hi]
    qt_high_lo_hist = sorted_t_high[rh_lo]
    with np.errstate(over="ignore", invalid="ignore"):
        ci_hist = np.stack((obs[0] - qt_low_hi_hist * obs_se[0], obs[1] - qt_high_lo_hist * obs_se[1]), axis=1)
    fail_ci_hist = ~np.all(np.isfinite(ci_hist), axis=1) | (ci_hist[:, 0] > ci_hist[:, 1])

    degenerate_main = fail_distinct_boot | invalid_obs_se | invalid_boot_se | fail_t_main | fail_ci_main
    degenerate_hist = fail_distinct_boot_hist | invalid_obs_se | invalid_boot_se | fail_t_hist | fail_ci_hist

    with np.errstate(over="ignore", invalid="ignore"):
        ci_tol0 = np.stack((obs[0] - sorted_t_low0[rm_hi] * obs_se[0], obs[1] - sorted_t_high0[rm_lo] * obs_se[1]), axis=1)
    fail_ci_tol0 = ~np.all(np.isfinite(ci_tol0), axis=1) | (ci_tol0[:, 0] > ci_tol0[:, 1])
    zero_span_boot_tol0 = (sorted_low[rm_hi] == sorted_low[rm_lo]) | (sorted_high[rm_hi] == sorted_high[rm_lo])
    zero_span_t_tol0 = (sorted_t_low0[rm_hi] == sorted_t_low0[rm_lo]) | (sorted_t_high0[rm_hi] == sorted_t_high0[rm_lo])
    fail_t_tol0 = (distinct_t_low_tol0 < 20) | (distinct_t_high_tol0 < 20) | zero_span_t_tol0
    degenerate_tol0 = (
        (unique_low_tol0 < 20) | (unique_high_tol0 < 20) | zero_span_boot_tol0 |
        invalid_obs_se_tol0 | invalid_boot_se_tol0 | fail_t_tol0 | fail_ci_tol0
    )
    tol_diff = degenerate_main != degenerate_tol0

    obs_t = [
        np.divide(o, s, out=np.zeros_like(o), where=np.isfinite(s) & (s > TOL_DUST))
        for o, s in zip(obs, obs_se)
    ]
    pplus = (1.0 + np.sum(ts[0] >= obs_t[0][None, :], axis=0)) / (b_reps + 1.0)
    pminus = (1.0 + np.sum(ts[1] <= obs_t[1][None, :], axis=0)) / (b_reps + 1.0)

    p = np.where(ONE_SIDED_A, pplus, np.minimum(1.0, 2.0 * np.minimum(pplus, pminus)))
    p[(ONE_SIDED_A & (obs_dir != 1)) | (~ONE_SIDED_A & (obs_dir == 0))] = 1.0

    p[degenerate_main] = 1.0
    ci_main[degenerate_main] = DOMAINS_A[degenerate_main]
    ci_hist[degenerate_hist] = DOMAINS_A[degenerate_hist]

    reject = holm_m4(p)
    direction = np.where(reject, obs_dir, 0)

    return {
        "p": p,
        "pplus": pplus,
        "pminus": pminus,
        "ci": ci_main,
        "degenerate": degenerate_main,
        "ci_995": ci_hist,
        "degenerate_995": degenerate_hist,
        "degenerate_tol0": degenerate_tol0,
        "tol_diff": tol_diff,
        "reject": reject,
        "direction": direction,
        "observed_direction": obs_dir,
        "unique_lower": unique_low.copy(),
        "unique_upper": unique_high.copy(),
        "unique_t_lower": distinct_t_low.copy(),
        "unique_t_upper": distinct_t_high.copy(),
        "failure_distinct_boot": fail_distinct_boot,
        "failure_observed_se": invalid_obs_se,
        "failure_bootstrap_se": invalid_boot_se,
        "failure_studentized_distribution": fail_t_main,
        "failure_ci": fail_ci_main,
    }


def assess_a(result: Dict[str, Any], truth: Tuple[Fraction, Fraction, Fraction, Fraction]) -> Dict[str, Any]:
    """Assess inference results against certified exact Fraction truth."""
    certified = [x if isinstance(x, Fraction) else Fraction(str(x)) for x in truth]
    if len(certified) != 4:
        raise ValueError("Exactly 4 truth values required")

    numeric = np.array([float(x) for x in certified], dtype=np.float64)

    null = np.array([
        certified[0] <= Fraction(0),
        certified[1] == Fraction(0),
        certified[2] == Fraction(0),
        certified[3] == Fraction(0),
    ], dtype=bool)

    signs = np.array([(x > 0) - (x < 0) for x in certified], dtype=int)
    declared = result["reject"] & (result["direction"] != 0)
    wrong_direction = declared & ~null & (result["direction"] != signs)
    false_reject = result["reject"] & null

    fwer = bool(false_reject.any())
    family_direction_error = bool(false_reject.any() or wrong_direction.any())
    correct_direction = declared & ~null & ~wrong_direction

    ci_main = result["ci"]
    cov_main = (ci_main[:, 0] <= numeric) & (numeric <= ci_main[:, 1])
    simult_cov_main = bool(cov_main.all())

    ci_hist = result["ci_995"]
    cov_hist = (ci_hist[:, 0] <= numeric) & (numeric <= ci_hist[:, 1])
    simult_cov_hist = bool(cov_hist.all())

    screen_false05 = (result["p"] <= 0.05) & null
    screen_false0125 = (result["p"] <= 0.0125) & null
    screen_false005 = (result["p"] <= 0.005) & null

    return {
        "null": null,
        "false_reject": false_reject,
        "fwer": fwer,
        "declared_direction": declared,
        "wrong_direction": wrong_direction,
        "family_direction_error": family_direction_error,
        "correct_direction": correct_direction,
        "coverage_9875": cov_main,
        "simultaneous_coverage_9875": simult_cov_main,
        "coverage_995": cov_hist,
        "simultaneous_coverage_995": simult_cov_hist,
        "screen_false05": screen_false05,
        "screen_false0125": screen_false0125,
        "screen_false005": screen_false005,
    }
