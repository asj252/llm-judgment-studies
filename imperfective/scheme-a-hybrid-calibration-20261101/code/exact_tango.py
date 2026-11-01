"""Certified Unconditional Exact Extension Based on Tango (1998) Score Ordering.

Implements brief.md (r4) §3.1 for discrete paired trinary contrasts d_i in {-1, 0, +1}:
- Target parameter: unconditional paired trinomial mean difference theta = pi_+ - pi_- in [-1, 1]
  over the closed simplex Delta_3 (0^0 == 1, 0^m == 0 for m >= 1);
- Removable singularity continuous extension Z(0; 0, 0) := 0.0;
- Runtime IEEE-754 Round-to-Nearest-Even (RN) and gradual-underflow (non-FTZ/non-DAZ) self-check;
- End-to-end IEEE-754 outward interval arithmetic on Z(theta; u, v) with coordinate-monotone upper
  envelope Z_hi_mono(theta_a; u, v), reducing 2D simplex supremum to 1D s in [s_min, 1] with
  explicit kink node insertion s = theta_b whenever s_min < theta_b < 1;
- Locked-order IEEE-754 outward primitives (mul_up, add_up, sub_up_nonneg) eliminating intermediate
  probability-power underflow amplification (closing c-brief-r2 B2-b);
- Exact Python fractions.Fraction verification of all 6 (n, alpha) left truncation cutpoints and
  rational downward-rounded half-alpha thresholds;
- Single common cosine partition on [theta_cut_min, 1 - 1e-9] + rightmost conservative tail box
  [1 - 1e-9, 1.0] (ub = 1.0), followed by outward coordinate-monotone envelopes over better
  observations {(x', y') in Omega_n : x' >= x, y' <= y} (closing c-brief-r2 B2-a);
- Deterministic sample-path bounding propagation under [0, 1] worst-case missingness (d_lower, d_upper).
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

import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

ALPHA_LEVELS_STR = ("0.0125", "0.005", "0.05")
ALPHA_KEY_SUFFIX = {
    "0.0125": "0125",
    "0.005": "0005",
    "0.05": "0050",
}

DEFAULT_GRID_CONFIGS = {
    80: {"g_nodes": 2000, "m_seg": 2048, "theta_max": 1.0 - 1e-9},
    20: {"g_nodes": 1200, "m_seg": 1024, "theta_max": 1.0 - 1e-9},
}

DEFAULT_TABLES_NPZ = Path(__file__).resolve().parent.parent / "manifests" / "exact-tango-tables.npz"
DEFAULT_TABLES_META = Path(__file__).resolve().parent.parent / "manifests" / "exact-tango-tables-meta.json"

_CACHED_TABLES: Optional[Dict[str, Any]] = None
_CACHED_TABLES_SHA: Optional[str] = None


def _runtime_add_f64(a: float, b: float) -> Tuple[float, float]:
    """Execute runtime float64 additions in both NumPy array and Python float arithmetic (no constant folding)."""
    arr_a = np.empty(1, dtype=np.float64)
    arr_b = np.empty(1, dtype=np.float64)
    arr_a[0] = a
    arr_b[0] = b
    np_sum = float((arr_a + arr_b)[0])
    py_sum = float(arr_a[0]) + float(arr_b[0])
    return np_sum, py_sum


def _runtime_mul_f64(a: float, b: float) -> Tuple[float, float]:
    """Execute runtime float64 multiplications in both NumPy array and Python float arithmetic."""
    arr_a = np.empty(1, dtype=np.float64)
    arr_b = np.empty(1, dtype=np.float64)
    arr_a[0] = a
    arr_b[0] = b
    np_prod = float((arr_a * arr_b)[0])
    py_prod = float(arr_a[0]) * float(arr_b[0])
    return np_prod, py_prod


def verify_ieee754_rn_and_subnormals() -> Dict[str, Any]:
    """Verify runtime IEEE-754 binary64 Round-to-Nearest-Even (RN) and gradual underflow (non-FTZ/non-DAZ).

    Uniquely separates RN from RZ (toward zero), RD (toward -inf), RU (toward +inf), and RNA (ties away)
    on both positive and negative runtime operands, and verifies subnormal preservation down to 2^-1074.
    """
    min_sub_expected = math.ldexp(1.0, -1074)
    min_norm = math.ldexp(1.0, -1022)
    half_min_norm_expected = math.ldexp(1.0, -1023)
    ulp_1 = math.ldexp(1.0, -52)
    half_ulp_1 = math.ldexp(1.0, -53)
    tiny = math.ldexp(1.0, -105)

    min_sub_np = float(np.nextafter(np.float64(0.0), np.float64(np.inf)))
    if min_sub_np != min_sub_expected or not (min_sub_np > 0.0):
        raise RuntimeError(f"IEEE-754 subnormal nextafter(0, +inf) check failed: got {min_sub_np!r}")

    # Gradual underflow (non-FTZ: normal * 0.5 -> subnormal; non-DAZ: subnormal + 0 and subnormal * 1 preserved)
    np_sub_mul, py_sub_mul = _runtime_mul_f64(min_norm, 0.5)
    if np_sub_mul != half_min_norm_expected or py_sub_mul != half_min_norm_expected:
        raise RuntimeError(f"IEEE-754 gradual underflow (FTZ) check failed: np={np_sub_mul!r}, py={py_sub_mul!r}")

    np_daz_add, py_daz_add = _runtime_add_f64(min_sub_np, 0.0)
    np_daz_mul, py_daz_mul = _runtime_mul_f64(min_sub_np, 1.0)
    if not (np_daz_add == min_sub_expected and py_daz_add == min_sub_expected and np_daz_mul == min_sub_expected and py_daz_mul == min_sub_expected):
        raise RuntimeError("IEEE-754 subnormal input preservation (DAZ) check failed")

    # Positive RN checks:
    # 1) Even LSB tie (+1.0 + 2^-53 -> +1.0): excludes RU and RNA (which produce 1.0 + 2^-52)
    if _runtime_add_f64(1.0, half_ulp_1) != (1.0, 1.0):
        raise RuntimeError("IEEE-754 RN check failed on +1.0 + 2^-53 (even tie)")
    # 2) Odd LSB tie ((1.0 + 2^-52) + 2^-53 -> 1.0 + 2*2^-52): excludes RZ and RD (which produce 1.0 + 2^-52)
    odd_pos = 1.0 + ulp_1
    even_up_pos = 1.0 + 2.0 * ulp_1
    if _runtime_add_f64(odd_pos, half_ulp_1) != (even_up_pos, even_up_pos):
        raise RuntimeError("IEEE-754 RN check failed on (1 + 2^-52) + 2^-53 (odd tie)")
    # 3) Strictly above half-ULP (+1.0 + (2^-53 + 2^-105) -> 1.0 + 2^-52): excludes RZ and RD
    above_half = half_ulp_1 + tiny
    if _runtime_add_f64(1.0, above_half) != (odd_pos, odd_pos):
        raise RuntimeError("IEEE-754 RN check failed on +1.0 + (2^-53 + 2^-105)")

    # Negative RN checks:
    # 4) Negative even LSB tie (-1.0 + (-2^-53) -> -1.0): excludes RD and RNA (which produce -(1 + 2^-52))
    if _runtime_add_f64(-1.0, -half_ulp_1) != (-1.0, -1.0):
        raise RuntimeError("IEEE-754 RN check failed on -1.0 - 2^-53 (negative even tie)")
    # 5) Negative odd LSB tie (-(1 + 2^-52) + (-2^-53) -> -(1 + 2*2^-52)): excludes RZ and RU
    if _runtime_add_f64(-odd_pos, -half_ulp_1) != (-even_up_pos, -even_up_pos):
        raise RuntimeError("IEEE-754 RN check failed on -(1 + 2^-52) - 2^-53 (negative odd tie)")
    # 6) Strictly below negative half-ULP (-1.0 - (2^-53 + 2^-105) -> -(1 + 2^-52)): excludes RZ and RU
    if _runtime_add_f64(-1.0, -above_half) != (-odd_pos, -odd_pos):
        raise RuntimeError("IEEE-754 RN check failed on -1.0 - (2^-53 + 2^-105)")

    return {
        "passed": True,
        "rounding_mode_verified": "IEEE-754 binary64 Round-to-Nearest-Even (RN)",
        "excluded_modes": ["RZ", "RD", "RU", "RNA", "FTZ", "DAZ"],
        "min_positive_subnormal_hex": min_sub_np.hex(),
    }


def mul_up(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    """Certified IEEE-754 outward upper bound on a * b for finite non-negative float64 operands."""
    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    if np.any(np.isnan(aa)) or np.any(np.isnan(bb)) or np.any(aa < 0.0) or np.any(bb < 0.0):
        raise ValueError("mul_up requires finite non-negative operands")
    with np.errstate(under="ignore"):
        prod = aa * bb
    up = np.nextafter(prod, np.inf)
    res = np.where((aa == 0.0) | (bb == 0.0), 0.0, up)
    if not np.all(np.isfinite(res)):
        raise OverflowError("mul_up overflowed float64 DBL_MAX")
    return res


def add_up(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    """Certified IEEE-754 outward upper bound on a + b for finite non-negative float64 operands."""
    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    if np.any(np.isnan(aa)) or np.any(np.isnan(bb)) or np.any(aa < 0.0) or np.any(bb < 0.0):
        raise ValueError("add_up requires finite non-negative operands")
    s = aa + bb
    up = np.nextafter(s, np.inf)
    res = np.where(aa == 0.0, bb, np.where(bb == 0.0, aa, up))
    if not np.all(np.isfinite(res)):
        raise OverflowError("add_up overflowed float64 DBL_MAX")
    return res


def signed_add_up_nonneg(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    """Certified IEEE-754 outward upper bound on max(0, a + b) for finite float64 operands.

    By the binary64 2^-1074 integer-lattice property under gradual underflow, fl(a + b) <= 0.0
    if and only if real a + b <= 0.0.
    """
    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    if not (np.all(np.isfinite(aa)) and np.all(np.isfinite(bb))):
        raise ValueError("signed_add_up_nonneg requires finite operands")
    s = aa + bb
    up = np.nextafter(s, np.inf)
    exact_or_up = np.where(aa == 0.0, bb, np.where(bb == 0.0, aa, up))
    return np.where(s <= 0.0, 0.0, np.maximum(0.0, exact_or_up))


def sub_up_nonneg(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    """Certified IEEE-754 outward upper bound on max(0, a - b) for finite float64 operands."""
    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    if not (np.all(np.isfinite(aa)) and np.all(np.isfinite(bb))):
        raise ValueError("sub_up_nonneg requires finite operands")
    diff = aa - bb
    up = np.nextafter(diff, np.inf)
    exact_or_up = np.where(bb == 0.0, aa, np.where(aa == 0.0, -bb, up))
    return np.where(aa <= bb, 0.0, np.maximum(0.0, exact_or_up))


def trinomial_int(n: int, u: int, v: int) -> int:
    """Exact Python arbitrary-precision integer trinomial coefficient n! / (u! v! (n - u - v)!)."""
    w = n - u - v
    if u < 0 or v < 0 or w < 0:
        raise ValueError(f"Invalid trinomial indices ({u}, {v}, {w}) for n={n}")
    return math.factorial(n) // (math.factorial(u) * math.factorial(v) * math.factorial(w))


def int_to_float_up(c_int: int) -> float:
    """Smallest binary64 float >= exact non-negative Python integer c_int."""
    if c_int < 0:
        raise ValueError("c_int must be non-negative")
    f = float(c_int)
    if not math.isfinite(f):
        raise OverflowError("Integer overflow in float64")
    if int(f) < c_int:
        f = float(np.nextafter(f, np.inf))
    if not (math.isfinite(f) and int(f) >= c_int):
        raise AssertionError("int_to_float_up failed exact integer upper bound assertion")
    return f


def frac_to_float_up(fr: Fraction) -> float:
    """Smallest binary64 float >= exact Fraction fr."""
    f = float(fr)
    if not math.isfinite(f):
        raise OverflowError("Fraction overflow in float64")
    if Fraction(f) < fr:
        f = float(np.nextafter(f, np.inf))
    if Fraction(f) < fr:
        raise AssertionError("frac_to_float_up failed exact rational upper bound assertion")
    return f


def frac_to_float_down(fr: Fraction) -> float:
    """Largest binary64 float <= exact Fraction fr."""
    f = float(fr)
    if not math.isfinite(f):
        raise OverflowError("Fraction overflow in float64")
    if Fraction(f) > fr:
        f = float(np.nextafter(f, -np.inf))
    if Fraction(f) > fr:
        raise AssertionError("frac_to_float_down failed exact rational lower bound assertion")
    return f


def build_omega_arrays(n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build flattened Omega_n = {(u, v) : u >= 0, v >= 0, u + v <= n} arrays and 2D index lookup grid."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    u_list: List[int] = []
    v_list: List[int] = []
    idx_grid = np.full((n + 1, n + 1), -1, dtype=np.int64)
    idx = 0
    for u in range(n + 1):
        for v in range(n + 1 - u):
            u_list.append(u)
            v_list.append(v)
            idx_grid[u, v] = idx
            idx += 1
    u_arr = np.array(u_list, dtype=np.int64)
    v_arr = np.array(v_list, dtype=np.int64)
    w_arr = n - u_arr - v_arr
    c_hi_arr = np.array(
        [int_to_float_up(trinomial_int(n, int(u), int(v))) for u, v in zip(u_arr, v_arr)],
        dtype=np.float64,
    )
    return u_arr, v_arr, w_arr, c_hi_arr, idx_grid


def certify_left_cut_fraction(n: int, alpha_str: str) -> Dict[str, Any]:
    """Certify left truncation cut theta_cut in (-1, 0) via exact Python Fraction arithmetic.

    Verifies 1 - (-Fraction(theta_cut))**n <= Fraction(alpha_str) / 2 and computes
    certified downward-rounded half_alpha_lo <= Fraction(alpha_str) / 2.
    """
    alpha_rat = Fraction(alpha_str)
    if alpha_rat <= 0 or alpha_rat >= 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha_str}")
    half_alpha_rat = alpha_rat / 2
    half_alpha_lo = frac_to_float_down(half_alpha_rat)
    half_alpha_f_dn = float(np.nextafter(float(half_alpha_rat), -np.inf))

    delta_cand = 1.0 - (1.0 - float(half_alpha_rat)) ** (1.0 / n)
    theta_cut = -1.0 + delta_cand
    steps = 0
    while True:
        if not (-1.0 < theta_cut < 0.0):
            raise RuntimeError(f"Invalid theta_cut={theta_cut} while certifying (n={n}, alpha={alpha_str})")
        th_rat = Fraction(theta_cut)
        p_cut_rat = Fraction(1) - ((-th_rat) ** n)
        ub_f = frac_to_float_up(p_cut_rat)
        if p_cut_rat <= half_alpha_rat and ub_f <= half_alpha_f_dn and ub_f <= half_alpha_lo:
            break
        theta_cut = float(np.nextafter(theta_cut, -np.inf))
        steps += 1
        if steps > 2048:
            raise RuntimeError(f"Exceeded ULP step budget certifying left cut for (n={n}, alpha={alpha_str})")

    return {
        "n": int(n),
        "alpha": str(alpha_str),
        "theta_cut_float": float(theta_cut),
        "theta_cut_hex": float(theta_cut).hex(),
        "half_alpha_lo_float": float(half_alpha_lo),
        "half_alpha_lo_hex": float(half_alpha_lo).hex(),
        "certified_ub_float": float(ub_f),
        "exact_fraction_verified": bool(Fraction(1) - ((-Fraction(theta_cut)) ** n) <= half_alpha_rat),
        "half_alpha_lo_fraction_verified": bool(Fraction(half_alpha_lo) <= half_alpha_rat),
        "downward_ulp_steps": int(steps),
    }


def certify_all_6_left_cuts() -> Dict[str, Dict[str, Any]]:
    """Certify and return all 6 (n, alpha) left truncation records for n in {20, 80}."""
    records: Dict[str, Dict[str, Any]] = {}
    for n in (20, 80):
        for a_str in ALPHA_LEVELS_STR:
            key = f"n{n}_alpha_{ALPHA_KEY_SUFFIX[a_str]}"
            rec = certify_left_cut_fraction(n, a_str)
            if not (rec["exact_fraction_verified"] and rec["half_alpha_lo_fraction_verified"]):
                raise AssertionError(f"Rational left-cut verification failed for {key}")
            records[key] = rec
    return records


def verify_sealed_left_cuts(records: Dict[str, Dict[str, Any]]) -> None:
    """Re-verify a dict of 6 sealed left-cut records in exact Fraction arithmetic."""
    expected_keys = {f"n{n}_alpha_{ALPHA_KEY_SUFFIX[a]}" for n in (20, 80) for a in ALPHA_LEVELS_STR}
    if set(records.keys()) != expected_keys:
        raise ValueError(f"Sealed left-cut keys mismatch: got {sorted(records.keys())}")
    for key, rec in records.items():
        n = int(rec["n"])
        alpha_str = str(rec["alpha"])
        th_f = float.fromhex(str(rec["theta_cut_hex"]))
        half_lo = float.fromhex(str(rec["half_alpha_lo_hex"]))
        if th_f != float(rec["theta_cut_float"]) or not (-1.0 < th_f < 0.0):
            raise ValueError(f"Corrupted theta_cut float/hex in {key}")
        half_rat = Fraction(alpha_str) / 2
        if Fraction(1) - ((-Fraction(th_f)) ** n) > half_rat:
            raise ValueError(f"Exact Fraction left-cut inequality violated in {key}")
        if Fraction(half_lo) > half_rat:
            raise ValueError(f"half_alpha_lo exceeds exact rational alpha/2 in {key}")


def score_bounds_omega(
    theta: float,
    n: int,
    u_arr: np.ndarray,
    v_arr: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute certified IEEE-754 interval [Z_lo, Z_hi] for all (u, v) in Omega_n at theta in (-1, 1).

    Uses cancellation-free variance factor v = (shat - |theta|) + |theta|*(1 - |theta|),
    exact closed-form boundary roots on n0 == 0 (shat = 1) and u + v == 0 (shat = |theta|),
    and the continuous extension Z(0; 0, 0) := 0.0.
    """
    if not (-1.0 < theta < 1.0):
        raise ValueError(f"theta must be strictly inside (-1, 1), got {theta}")
    k = len(u_arr)
    s_int = u_arr + v_arr
    d_int = u_arr - v_arr
    n0_int = n - s_int

    s_f = s_int.astype(np.float64)
    d_f = d_int.astype(np.float64)
    n0_f = n0_int.astype(np.float64)
    n_f = float(n)
    abs_th = abs(float(theta))

    def iv_add(a_lo: np.ndarray, a_hi: np.ndarray, b_lo: np.ndarray, b_hi: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        s_lo = a_lo + b_lo
        s_hi = a_hi + b_hi
        lo = np.where(a_lo == 0.0, b_lo, np.where(b_lo == 0.0, a_lo, np.nextafter(s_lo, -np.inf)))
        hi = np.where(a_hi == 0.0, b_hi, np.where(b_hi == 0.0, a_hi, np.nextafter(s_hi, np.inf)))
        return lo, hi

    def iv_sub(a_lo: np.ndarray, a_hi: np.ndarray, b_lo: np.ndarray, b_hi: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        return iv_add(a_lo, a_hi, -b_hi, -b_lo)

    def iv_mul_const(arr_f: np.ndarray, c: float) -> Tuple[np.ndarray, np.ndarray]:
        if c == 0.0:
            z = np.zeros_like(arr_f)
            return z, z
        with np.errstate(under="ignore"):
            p = arr_f * c
        lo = np.where(arr_f == 0.0, 0.0, np.nextafter(p, -np.inf))
        hi = np.where(arr_f == 0.0, 0.0, np.nextafter(p, np.inf))
        return lo, hi

    if theta == 0.0:
        th2_lo, th2_hi = 0.0, 0.0
    else:
        with np.errstate(under="ignore"):
            th_sq = theta * theta
        th2_lo = max(0.0, float(np.nextafter(th_sq, -np.inf)))
        th2_hi = float(np.nextafter(th_sq, np.inf))

    dth_lo, dth_hi = iv_mul_const(d_f, theta)
    sp_lo, sp_hi = iv_add(s_f, s_f, dth_lo, dth_hi)
    b_lo, b_hi = -sp_hi, -sp_lo

    with np.errstate(under="ignore"):
        p_n0_lo = n0_f * th2_lo
        p_n0_hi = n0_f * th2_hi
    n0_th2_lo = np.where((n0_f == 0.0) | (th2_lo == 0.0), 0.0, np.maximum(0.0, np.nextafter(p_n0_lo, -np.inf)))
    n0_th2_hi = np.where((n0_f == 0.0) | (th2_hi == 0.0), 0.0, np.nextafter(p_n0_hi, np.inf))
    c_lo, c_hi = iv_sub(dth_lo, dth_hi, n0_th2_lo, n0_th2_hi)

    with np.errstate(under="ignore"):
        b_p1 = b_lo * b_lo
        b_p2 = b_hi * b_hi
    straddle_b = (b_lo <= 0.0) & (0.0 <= b_hi)
    b2_lo = np.where(straddle_b, 0.0, np.maximum(0.0, np.nextafter(np.minimum(b_p1, b_p2), -np.inf)))
    b2_hi = np.where((b_lo == 0.0) & (b_hi == 0.0), 0.0, np.nextafter(np.maximum(b_p1, b_p2), np.inf))

    fnc_lo = iv_mul_const(c_lo, 4.0 * n_f)[0]
    fnc_hi = iv_mul_const(c_hi, 4.0 * n_f)[1]
    disc_lo_raw, disc_hi_raw = iv_sub(b2_lo, b2_hi, fnc_lo, fnc_hi)
    disc_lo = np.maximum(0.0, disc_lo_raw)
    disc_hi = np.maximum(0.0, disc_hi_raw)

    sq_lo = np.where(disc_lo == 0.0, 0.0, np.maximum(0.0, np.nextafter(np.sqrt(disc_lo), -np.inf)))
    sq_hi = np.where(disc_hi == 0.0, 0.0, np.nextafter(np.sqrt(disc_hi), np.inf))

    num_s_lo, num_s_hi = iv_add(-b_hi, -b_lo, sq_lo, sq_hi)
    with np.errstate(under="ignore"):
        q_lo = num_s_lo / (2.0 * n_f)
        q_hi = num_s_hi / (2.0 * n_f)
    shat_lo = np.clip(np.where(num_s_lo == 0.0, 0.0, np.nextafter(q_lo, -np.inf)), abs_th, 1.0)
    shat_hi = np.clip(np.where(num_s_hi == 0.0, 0.0, np.nextafter(q_hi, np.inf)), abs_th, 1.0)

    mask_n0_zero = (n0_int == 0)
    mask_xy_zero = (s_int == 0)
    shat_lo = np.where(mask_n0_zero, 1.0, np.where(mask_xy_zero, abs_th, shat_lo))
    shat_hi = np.where(mask_n0_zero, 1.0, np.where(mask_xy_zero, abs_th, shat_hi))

    if abs_th == 0.0:
        t_term_lo, t_term_hi = 0.0, 0.0
    else:
        one_m_lo = max(0.0, float(np.nextafter(1.0 - abs_th, -np.inf)))
        one_m_hi = float(np.nextafter(1.0 - abs_th, np.inf))
        with np.errstate(under="ignore"):
            p_t_lo = abs_th * one_m_lo
            p_t_hi = abs_th * one_m_hi
        t_term_lo = 0.0 if one_m_lo == 0.0 else max(0.0, float(np.nextafter(p_t_lo, -np.inf)))
        t_term_hi = float(np.nextafter(p_t_hi, np.inf))

    ds_lo = np.where(
        shat_lo <= abs_th,
        0.0,
        np.where(abs_th == 0.0, shat_lo, np.maximum(0.0, np.nextafter(shat_lo - abs_th, -np.inf))),
    )
    ds_hi = np.where(
        shat_hi <= abs_th,
        0.0,
        np.where(abs_th == 0.0, shat_hi, np.nextafter(shat_hi - abs_th, np.inf)),
    )
    v_lo, v_hi = iv_add(ds_lo, ds_hi, np.full(k, t_term_lo), np.full(k, t_term_hi))

    with np.errstate(under="ignore"):
        nv_p_lo = n_f * v_lo
        nv_p_hi = n_f * v_hi
    nv_lo = np.where(v_lo == 0.0, 0.0, np.maximum(0.0, np.nextafter(nv_p_lo, -np.inf)))
    nv_hi = np.where(v_hi == 0.0, 0.0, np.nextafter(nv_p_hi, np.inf))
    w_lo = np.where(nv_lo == 0.0, 0.0, np.maximum(0.0, np.nextafter(np.sqrt(nv_lo), -np.inf)))
    w_hi = np.where(nv_hi == 0.0, 0.0, np.nextafter(np.sqrt(nv_hi), np.inf))

    if theta == 0.0:
        nth_lo, nth_hi = 0.0, 0.0
    else:
        with np.errstate(under="ignore"):
            nth_p = n_f * theta
        nth_lo = float(np.nextafter(nth_p, -np.inf))
        nth_hi = float(np.nextafter(nth_p, np.inf))
    num_lo, num_hi = iv_sub(d_f, d_f, np.full(k, nth_lo), np.full(k, nth_hi))

    z_lo = np.full(k, -np.inf, dtype=np.float64)
    z_hi = np.full(k, np.inf, dtype=np.float64)

    valid_w = w_lo > 0.0
    idx = np.where(valid_w)[0]
    nl, nh = num_lo[idx], num_hi[idx]
    wl, wh = w_lo[idx], w_hi[idx]

    with np.errstate(under="ignore"):
        zl = np.where(
            nl >= 0.0,
            np.where(nl == 0.0, 0.0, np.nextafter(nl / wh, -np.inf)),
            np.nextafter(nl / wl, -np.inf),
        )
        zh = np.where(
            nh <= 0.0,
            np.where(nh == 0.0, 0.0, np.nextafter(nh / wh, np.inf)),
            np.nextafter(nh / wl, np.inf),
        )
    z_lo[idx] = zl
    z_hi[idx] = zh

    if theta == 0.0:
        z_lo[mask_xy_zero] = 0.0
        z_hi[mask_xy_zero] = 0.0

    return z_lo, z_hi


def enforce_z_hi_monotone(z_hi: np.ndarray, n: int, idx_grid: np.ndarray) -> np.ndarray:
    """Enforce coordinate-monotone upper envelope Z_hi_mono(u, v) = max_{u' <= u, v' >= v} Z_hi(u', v')."""
    mat = np.full((n + 1, n + 1), -np.inf, dtype=np.float64)
    valid = idx_grid >= 0
    mat[valid] = z_hi[idx_grid[valid]]
    for u in range(1, n + 1):
        max_v = n - u
        mat[u, :max_v + 1] = np.maximum(mat[u, :max_v + 1], mat[u - 1, :max_v + 1])
    for v in range(n - 1, -1, -1):
        max_u = n - v
        mat[:max_u + 1, v] = np.maximum(mat[:max_u + 1, v], mat[:max_u + 1, v + 1])
    return mat[valid]


def build_s_grid_with_kink(theta_a: float, theta_b: float, m_seg: int = 2048) -> np.ndarray:
    """Construct strictly increasing 1D s-grid on [s_min, 1.0], inserting kink node s = theta_b if interior."""
    if theta_a > theta_b:
        raise ValueError(f"theta_a ({theta_a}) > theta_b ({theta_b})")
    if theta_a <= 0.0 <= theta_b:
        s_min = 0.0
    else:
        s_min = min(abs(float(theta_a)), abs(float(theta_b)))

    raw_nodes = np.linspace(s_min, 1.0, m_seg + 1, dtype=np.float64)
    raw_nodes[0] = s_min
    raw_nodes[-1] = 1.0
    extra = [s_min, 1.0]
    if s_min < theta_b < 1.0:
        extra.append(float(theta_b))
    s_nodes = np.unique(np.concatenate([raw_nodes, np.array(extra, dtype=np.float64)]))
    if s_nodes[0] != s_min or s_nodes[-1] != 1.0 or not np.all(np.diff(s_nodes) > 0.0):
        raise AssertionError("s_nodes monotonicity/endpoint invariant failed")
    if s_min < theta_b < 1.0 and not bool(np.any(s_nodes == float(theta_b))):
        raise AssertionError("Explicit kink node s = theta_b missing from s_nodes")
    return s_nodes


def eval_interval_certified_ub(
    theta_a: float,
    theta_b: float,
    n: int,
    u_arr: np.ndarray,
    v_arr: np.ndarray,
    w_arr: np.ndarray,
    c_hi_arr: np.ndarray,
    idx_grid: np.ndarray,
    m_seg: int = 2048,
) -> np.ndarray:
    """Compute certified upper bound P_bar_{[theta_a, theta_b]}(x, y) for all (x, y) in Omega_n.

    On every kink-free subsegment [s_k, s_{k+1}] of h(s) = Pr_{s, min(theta_b, s)}(E_hat):
    - Branch s <= theta_b has (pi_+', pi_-', pi_0') = (1, 0, -1) => |Delta^2_E| <= 2;
    - Branch s >= theta_b has (pi_+', pi_-', pi_0') = (1/2, 1/2, -1) => |Delta^2_E| <= 2;
    hence |h''(s)| <= 2*n*(n-1) everywhere on [s_k, s_{k+1}] and chord interpolation remainder
    is strictly bounded by (1/8) * 2*n*(n-1) * (s_{k+1} - s_k)^2 = (n*(n-1)/4) * (s_{k+1} - s_k)^2.
    Combined per segment via min(ub_c2_seg, ub_box_seg), evaluated exclusively with mul_up and add_up.
    """
    k_pts = len(u_arr)
    _, z_hi_a_raw = score_bounds_omega(theta_a, n, u_arr, v_arr)
    z_hi_a = enforce_z_hi_monotone(z_hi_a_raw, n, idx_grid)
    z_lo_b, _ = score_bounds_omega(theta_b, n, u_arr, v_arr)

    # Sort Omega_n in descending Z_hi_mono(theta_a) so every E_hat(x, y) = {j : Z_hi_mono[j] >= Z_lo[i]} is a prefix
    order = np.argsort(-z_hi_a, kind="mergesort")
    z_hi_desc = z_hi_a[order]
    ranks = np.searchsorted(-z_hi_desc, -z_lo_b, side="right")

    s_nodes = build_s_grid_with_kink(theta_a, theta_b, m_seg=m_seg)
    n_seg = len(s_nodes) - 1

    # 1. Node probability upper bounds at (s_k, min(theta_b, s_k))
    th_star = np.minimum(float(theta_b), s_nodes)
    sum_st_hi = signed_add_up_nonneg(s_nodes, th_star)
    dif_st_hi = sub_up_nonneg(s_nodes, th_star)
    pp_node_hi = np.minimum(1.0, mul_up(0.5, sum_st_hi))
    pm_node_hi = np.minimum(1.0, mul_up(0.5, dif_st_hi))
    pz_node_hi = np.minimum(1.0, sub_up_nonneg(1.0, s_nodes))

    def build_pow_2d(p_vec: np.ndarray) -> np.ndarray:
        tbl = np.ones((n + 1, len(p_vec)), dtype=np.float64)
        for m in range(1, n + 1):
            tbl[m] = np.minimum(1.0, mul_up(tbl[m - 1], p_vec))
        return tbl

    t_pp_node = build_pow_2d(pp_node_hi)
    t_pm_node = build_pow_2d(pm_node_hi)
    t_pz_node = build_pow_2d(pz_node_hi)

    u_ord = u_arr[order]
    v_ord = v_arr[order]
    w_ord = w_arr[order]
    c_ord = c_hi_arr[order][:, None]

    # Locked left-to-right multiplication order starting from C_hi >= 1 (closes B2-b)
    terms_node = mul_up(mul_up(mul_up(c_ord, t_pp_node[u_ord]), t_pm_node[v_ord]), t_pz_node[w_ord])

    # 2. 2D box probability upper bounds on [s_k, s_{k+1}] x [theta_a, theta_b]
    s_lo_seg = s_nodes[:-1]
    s_hi_seg = s_nodes[1:]
    sum_box_hi = signed_add_up_nonneg(s_hi_seg, float(theta_b))
    dif_box_hi = sub_up_nonneg(s_hi_seg, float(theta_a))
    pp_box_hi = np.minimum(1.0, mul_up(0.5, sum_box_hi))
    pm_box_hi = np.minimum(1.0, mul_up(0.5, dif_box_hi))
    pz_box_hi = np.minimum(1.0, sub_up_nonneg(1.0, s_lo_seg))

    t_pp_box = build_pow_2d(pp_box_hi)
    t_pm_box = build_pow_2d(pm_box_hi)
    t_pz_box = build_pow_2d(pz_box_hi)
    terms_box = mul_up(mul_up(mul_up(c_ord, t_pp_box[u_ord]), t_pm_box[v_ord]), t_pz_box[w_ord])

    c2_coeff_hi = frac_to_float_up(Fraction(n * (n - 1), 4))
    ds_hi = sub_up_nonneg(s_hi_seg, s_lo_seg)
    rem_hi = mul_up(c2_coeff_hi, mul_up(ds_hi, ds_hi))

    unique_ranks, inv_ranks = np.unique(ranks, return_inverse=True)
    res_unique = np.zeros(len(unique_ranks), dtype=np.float64)

    acc_node = np.zeros(len(s_nodes), dtype=np.float64)
    acc_box = np.zeros(n_seg, dtype=np.float64)
    ur_ptr = 0
    if unique_ranks[0] == 0:
        res_unique[0] = 0.0
        ur_ptr = 1

    for row_idx in range(k_pts):
        if ur_ptr >= len(unique_ranks):
            break
        acc_node = add_up(acc_node, terms_node[row_idx])
        acc_box = add_up(acc_box, terms_box[row_idx])
        if (row_idx + 1) == unique_ranks[ur_ptr]:
            ub_c2_seg = add_up(np.maximum(acc_node[:-1], acc_node[1:]), rem_hi)
            ub_seg = np.minimum(ub_c2_seg, acc_box)
            res_unique[ur_ptr] = min(1.0, float(np.max(ub_seg)))
            ur_ptr += 1

    return res_unique[inv_ranks]


def enforce_p_upper_monotone_b2a(p_raw_flat: np.ndarray, n: int, idx_grid: np.ndarray) -> np.ndarray:
    """Enforce F_plus_cert(x, y) = max_{x' >= x, y' <= y} P_raw(x', y') on (n+1, n+1) matrix (NaN off Omega_n)."""
    mat = np.full((n + 1, n + 1), -np.inf, dtype=np.float64)
    valid = idx_grid >= 0
    mat[valid] = np.minimum(1.0, np.maximum(0.0, p_raw_flat[idx_grid[valid]]))
    for x in range(n - 1, -1, -1):
        max_y = n - x
        mat[x, :max_y + 1] = np.maximum(mat[x, :max_y + 1], mat[x + 1, :max_y + 1])
    for y in range(1, n + 1):
        max_x = n - y
        mat[:max_x + 1, y] = np.maximum(mat[:max_x + 1, y], mat[:max_x + 1, y - 1])
    out = np.full((n + 1, n + 1), np.nan, dtype=np.float64)
    out[valid] = np.minimum(1.0, mat[valid])
    return out


def enforce_theta_lower_monotone_b2a(th_raw_flat: np.ndarray, n: int, idx_grid: np.ndarray) -> np.ndarray:
    """Enforce theta_L_cert(x, y) = min_{x' >= x, y' <= y} theta_L_raw(x', y') on (n+1, n+1) matrix."""
    mat = np.full((n + 1, n + 1), np.inf, dtype=np.float64)
    valid = idx_grid >= 0
    mat[valid] = np.clip(th_raw_flat[idx_grid[valid]], -1.0, 1.0)
    for x in range(n - 1, -1, -1):
        max_y = n - x
        mat[x, :max_y + 1] = np.minimum(mat[x, :max_y + 1], mat[x + 1, :max_y + 1])
    for y in range(1, n + 1):
        max_x = n - y
        mat[:max_x + 1, y] = np.minimum(mat[:max_x + 1, y], mat[:max_x + 1, y - 1])
    out = np.full((n + 1, n + 1), np.nan, dtype=np.float64)
    out[valid] = mat[valid]
    return out


def verify_certified_table_invariants_for_n(
    n: int,
    f_plus_zero: np.ndarray,
    theta_l_by_alpha: Dict[str, np.ndarray],
) -> Dict[str, Any]:
    """Assert 0 coordinate monotonicity violations, valid CI bounds, and B2-a extreme-point invariants."""
    if f_plus_zero.shape != (n + 1, n + 1):
        raise ValueError(f"Invalid f_plus_zero shape {f_plus_zero.shape} for n={n}")

    p_viol = 0
    th_viol = {a: 0 for a in theta_l_by_alpha}
    ci_order_viol = {a: 0 for a in theta_l_by_alpha}

    for x in range(n + 1):
        for y in range(n + 1 - x):
            pv = float(f_plus_zero[x, y])
            if not (math.isfinite(pv) and 0.0 <= pv <= 1.0):
                raise ValueError(f"Invalid f_plus_zero[{x}, {y}] = {pv}")
            if x + 1 + y <= n and float(f_plus_zero[x + 1, y]) > pv:
                p_viol += 1
            if x + y + 1 <= n and float(f_plus_zero[x, y + 1]) < pv:
                p_viol += 1

            for a_str, th_mat in theta_l_by_alpha.items():
                tl = float(th_mat[x, y])
                tu = -float(th_mat[y, x])
                if not (math.isfinite(tl) and math.isfinite(tu) and -1.0 <= tl <= tu <= 1.0):
                    ci_order_viol[a_str] += 1
                if x + 1 + y <= n and float(th_mat[x + 1, y]) < tl:
                    th_viol[a_str] += 1
                if x + y + 1 <= n and float(th_mat[x, y + 1]) > tl:
                    th_viol[a_str] += 1

    if p_viol != 0 or any(v != 0 for v in th_viol.values()) or any(v != 0 for v in ci_order_viol.values()):
        raise AssertionError(
            f"Certified table invariant failure for n={n}: p_viol={p_viol}, th_viol={th_viol}, ci_viol={ci_order_viol}"
        )

    p_n0 = float(f_plus_zero[n, 0])
    p_0n = float(f_plus_zero[0, n])
    exact_2mn = math.ldexp(1.0, -n)
    if not (exact_2mn <= p_n0 < 2.0 * exact_2mn):
        raise AssertionError(f"B2-a extreme point (n, 0) invariant failed for n={n}: got {p_n0}, 2^-n={exact_2mn}")
    if p_0n != 1.0:
        raise AssertionError(f"Extreme point (0, n) must equal 1.0 for n={n}, got {p_0n}")
    for a_str, th_mat in theta_l_by_alpha.items():
        if float(th_mat[0, n]) != -1.0:
            raise AssertionError(f"(0, n) lower bound must equal -1.0 for n={n}, alpha={a_str}")

    return {
        "n": int(n),
        "omega_size": (n + 1) * (n + 2) // 2,
        "p_monotonicity_violations": p_viol,
        "theta_L_monotonicity_violations": th_viol,
        "ci_order_violations": ci_order_viol,
        "f_plus_zero_at_n_0": p_n0,
        "exact_two_pow_minus_n": exact_2mn,
        "f_plus_zero_at_0_n": p_0n,
    }


def _worker_eval_chunk(args: Tuple[int, List[Tuple[int, float, float]], int]) -> List[Tuple[int, np.ndarray]]:
    """Worker entry point to evaluate a batch of common-grid intervals [theta_{g-1}, theta_g] for fixed n."""
    for env_k in SINGLE_THREAD_ENV_VARS:
        os.environ[env_k] = "1"
    verify_ieee754_rn_and_subnormals()
    n, interval_specs, m_seg = args
    u_arr, v_arr, w_arr, c_hi_arr, idx_grid = build_omega_arrays(n)
    out: List[Tuple[int, np.ndarray]] = []
    for g_idx, th_a, th_b in interval_specs:
        ub = eval_interval_certified_ub(th_a, th_b, n, u_arr, v_arr, w_arr, c_hi_arr, idx_grid, m_seg=m_seg)
        out.append((g_idx, ub))
    return out


def build_certified_tables_for_n(
    n: int,
    g_nodes: Optional[int] = None,
    m_seg: Optional[int] = None,
    theta_max: Optional[float] = None,
    workers: int = 1,
    alpha_levels: Tuple[str, ...] = ALPHA_LEVELS_STR,
) -> Dict[str, Any]:
    """Build certified exact Tango tables (F_plus(0) and theta_L for all alpha_levels) on Omega_n."""
    verify_ieee754_rn_and_subnormals()
    cfg = DEFAULT_GRID_CONFIGS.get(n, {"g_nodes": 400, "m_seg": 512, "theta_max": 1.0 - 1e-9})
    g_use = int(g_nodes if g_nodes is not None else cfg["g_nodes"])
    m_use = int(m_seg if m_seg is not None else cfg["m_seg"])
    th_max = float(theta_max if theta_max is not None else cfg["theta_max"])
    if g_use < 4 or m_use < 8 or not (0.5 < th_max < 1.0):
        raise ValueError(f"Invalid grid config for n={n}: G={g_use}, M={m_use}, theta_max={th_max}")

    u_arr, v_arr, w_arr, c_hi_arr, idx_grid = build_omega_arrays(n)
    k_pts = len(u_arr)
    idx_0_n = int(idx_grid[0, n])

    cut_records = {a_str: certify_left_cut_fraction(n, a_str) for a_str in alpha_levels}
    theta_cut_min = min(rec["theta_cut_float"] for rec in cut_records.values())

    j = np.arange(g_use, dtype=np.float64)
    u_cos = 0.5 * (1.0 - np.cos(np.pi * j / float(g_use - 1)))
    th_grid = theta_cut_min + (th_max - theta_cut_min) * u_cos
    th_grid[0] = theta_cut_min
    th_grid[-1] = th_max
    if not np.all(np.diff(th_grid) > 0.0):
        raise RuntimeError(f"Non-monotone cosine theta grid for n={n}")

    # 1. Point null theta_0 = 0.0 certified upper tail probability
    p_zero_raw_flat = eval_interval_certified_ub(0.0, 0.0, n, u_arr, v_arr, w_arr, c_hi_arr, idx_grid, m_seg=m_use)
    f_plus_zero_cert = enforce_p_upper_monotone_b2a(p_zero_raw_flat, n, idx_grid)
    f_plus_zero_raw = np.full((n + 1, n + 1), np.nan, dtype=np.float64)
    valid = idx_grid >= 0
    f_plus_zero_raw[valid] = p_zero_raw_flat[idx_grid[valid]]

    # 2. Evaluate all G - 1 common intervals I_g = [th_grid[g-1], th_grid[g]] (g = 1..G-1)
    # plus rightmost conservative tail box I_G = [th_max, 1.0] with P_bar == 1.0
    n_intervals = g_use - 1
    p_ub_matrix = np.empty((n_intervals + 1, k_pts), dtype=np.float64)
    p_ub_matrix[n_intervals, :] = 1.0  # I_G = [th_max, 1.0], conservative ub = 1.0

    all_specs = [(g_idx, float(th_grid[g_idx]), float(th_grid[g_idx + 1])) for g_idx in range(n_intervals)]
    n_workers = min(4, max(1, int(workers)))
    if n_workers == 1 or n_intervals <= 16:
        for g_idx, th_a, th_b in all_specs:
            p_ub_matrix[g_idx] = eval_interval_certified_ub(
                th_a, th_b, n, u_arr, v_arr, w_arr, c_hi_arr, idx_grid, m_seg=m_use
            )
    else:
        batch_sz = max(1, (n_intervals + n_workers * 4 - 1) // (n_workers * 4))
        tasks = [
            (n, all_specs[start:start + batch_sz], m_use)
            for start in range(0, n_intervals, batch_sz)
        ]
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            for batch_out in ex.map(_worker_eval_chunk, tasks):
                for g_idx, ub_vec in batch_out:
                    p_ub_matrix[g_idx] = ub_vec

    # Endpoints array of length G + 1 covering [theta_cut_min, 1.0]: th_ext[0..G-1] = th_grid, th_ext[G] = 1.0
    th_ext = np.concatenate([th_grid, np.array([1.0], dtype=np.float64)])
    th_right_ends = th_ext[1:]   # length G
    th_left_ends = th_ext[:-1]   # length G

    theta_l_cert_by_alpha: Dict[str, np.ndarray] = {}
    theta_l_raw_by_alpha: Dict[str, np.ndarray] = {}

    for a_str in alpha_levels:
        rec = cut_records[a_str]
        th_cut = float(rec["theta_cut_float"])
        half_lo = float(rec["half_alpha_lo_float"])

        # Intervals g in 0..G-1 (corresponding to I_1..I_G) active where right endpoint > th_cut
        eligible_g = th_right_ends > th_cut  # shape (G,)
        exceeds = (p_ub_matrix > half_lo) & eligible_g[:, None]  # shape (G, K), last row I_G is always True!
        if not np.all(exceeds[-1, :]):
            raise AssertionError(f"Rightmost tail box I_G failed to trigger > half_alpha_lo for alpha={a_str}")

        first_g = np.argmax(exceeds, axis=0)  # shape (K,)
        th_raw_flat = np.maximum(th_cut, th_left_ends[first_g])
        th_raw_flat[idx_0_n] = -1.0

        th_raw_mat = np.full((n + 1, n + 1), np.nan, dtype=np.float64)
        th_raw_mat[valid] = th_raw_flat[idx_grid[valid]]
        theta_l_raw_by_alpha[a_str] = th_raw_mat
        theta_l_cert_by_alpha[a_str] = enforce_theta_lower_monotone_b2a(th_raw_flat, n, idx_grid)

    inv_check = verify_certified_table_invariants_for_n(n, f_plus_zero_cert, theta_l_cert_by_alpha)
    return {
        "n": int(n),
        "g_nodes": g_use,
        "m_seg": m_use,
        "theta_max": th_max,
        "th_grid": th_grid,
        "left_cuts": cut_records,
        "f_plus_zero": f_plus_zero_cert,
        "f_plus_zero_raw": f_plus_zero_raw,
        "theta_L": theta_l_cert_by_alpha,
        "theta_L_raw": theta_l_raw_by_alpha,
        "invariants": inv_check,
    }


def compute_npz_payload_sha256(arrays: Dict[str, np.ndarray]) -> str:
    """Compute deterministic SHA256 binding sorted array keys, dtypes, shapes, and byte contents."""
    h = hashlib.sha256()
    for key in sorted(arrays.keys()):
        arr = np.ascontiguousarray(arrays[key])
        header = f"{key}|{arr.dtype.str}|{arr.ndim}|{','.join(str(d) for d in arr.shape)}|".encode("utf-8")
        h.update(header)
        h.update(arr.tobytes())
    return h.hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_and_save_exact_tango_tables(
    npz_path: Path = DEFAULT_TABLES_NPZ,
    meta_path: Path = DEFAULT_TABLES_META,
    workers: int = 4,
) -> Dict[str, Any]:
    """Build and save certified exact Tango lookup tables for n in {20, 80}."""
    t0 = time.perf_counter()
    ieee_info = verify_ieee754_rn_and_subnormals()
    all_cuts = certify_all_6_left_cuts()

    res_n20 = build_certified_tables_for_n(20, workers=workers)
    res_n80 = build_certified_tables_for_n(80, workers=workers)

    arrays: Dict[str, np.ndarray] = {}
    for n, res in ((20, res_n20), (80, res_n80)):
        arrays[f"n{n}_th_grid"] = res["th_grid"]
        arrays[f"n{n}_f_plus_zero"] = res["f_plus_zero"]
        arrays[f"n{n}_f_plus_zero_raw"] = res["f_plus_zero_raw"]
        for a_str in ALPHA_LEVELS_STR:
            sfx = ALPHA_KEY_SUFFIX[a_str]
            arrays[f"n{n}_theta_L_{sfx}"] = res["theta_L"][a_str]
            arrays[f"n{n}_theta_L_{sfx}_raw"] = res["theta_L_raw"][a_str]

    payload_sha = compute_npz_payload_sha256(arrays)
    npz_path = Path(npz_path)
    meta_path = Path(meta_path)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_npz = npz_path.with_name(f"{npz_path.stem}.tmp.{os.getpid()}.npz")
    np.savez_compressed(tmp_npz, **arrays)
    tmp_npz.replace(npz_path)
    file_sha = _file_sha256(npz_path)

    elapsed = time.perf_counter() - t0
    meta = {
        "schema_version": "exact-tango-certified-tables-v1",
        "method_attribution": (
            "Certified Unconditional Exact Extension Based on Tango (1998, Stat. Med. 17:891-908) Score Ordering"
        ),
        "build_wall_seconds": elapsed,
        "workers_used": min(4, max(1, int(workers))),
        "npz_file_name": npz_path.name,
        "npz_file_sha256": file_sha,
        "npz_payload_sha256": payload_sha,
        "ieee754_self_check": ieee_info,
        "grid_configs": {
            "20": {"g_nodes": res_n20["g_nodes"], "m_seg": res_n20["m_seg"], "theta_max": res_n20["theta_max"]},
            "80": {"g_nodes": res_n80["g_nodes"], "m_seg": res_n80["m_seg"], "theta_max": res_n80["theta_max"]},
        },
        "certified_left_cuts_6": all_cuts,
        "invariants": {
            "20": res_n20["invariants"],
            "80": res_n80["invariants"],
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def load_certified_tango_tables(
    npz_path: Path = DEFAULT_TABLES_NPZ,
    expected_file_sha256: Optional[str] = None,
    expected_payload_sha256: Optional[str] = None,
    force_reload: bool = False,
) -> Dict[str, Any]:
    """Load, verify IEEE-754 RN + SHA256 + monotonicity invariants, and cache certified Tango tables."""
    global _CACHED_TABLES, _CACHED_TABLES_SHA
    p = Path(npz_path)
    if not p.is_file():
        raise FileNotFoundError(f"Certified exact Tango tables missing at {p}")

    cur_file_sha = _file_sha256(p)
    if expected_file_sha256 is not None and cur_file_sha != expected_file_sha256:
        raise RuntimeError(
            f"Exact Tango tables file SHA256 mismatch: current={cur_file_sha} != expected={expected_file_sha256}"
        )

    if (not force_reload) and (_CACHED_TABLES is not None) and (_CACHED_TABLES_SHA == cur_file_sha):
        if expected_payload_sha256 is not None and _CACHED_TABLES["payload_sha256"] != expected_payload_sha256:
            raise RuntimeError("Exact Tango cached payload SHA256 mismatch against expected_payload_sha256")
        return _CACHED_TABLES

    verify_ieee754_rn_and_subnormals()
    with np.load(p) as loaded:
        arr_dict = {k: loaded[k] for k in loaded.files}

    payload_sha = compute_npz_payload_sha256(arr_dict)
    if expected_payload_sha256 is not None and payload_sha != expected_payload_sha256:
        raise RuntimeError(
            f"Exact Tango tables payload SHA256 mismatch: current={payload_sha} != expected={expected_payload_sha256}"
        )

    by_n: Dict[int, Dict[str, Any]] = {}
    for n in (20, 80):
        f_plus = arr_dict[f"n{n}_f_plus_zero"]
        th_by_a = {a_str: arr_dict[f"n{n}_theta_L_{ALPHA_KEY_SUFFIX[a_str]}"] for a_str in ALPHA_LEVELS_STR}
        verify_certified_table_invariants_for_n(n, f_plus, th_by_a)
        by_n[n] = {
            "f_plus_zero": f_plus,
            "theta_L": th_by_a,
        }

    bundle = {
        "file_sha256": cur_file_sha,
        "payload_sha256": payload_sha,
        "by_n": by_n,
        "raw_arrays": arr_dict,
    }
    _CACHED_TABLES = bundle
    _CACHED_TABLES_SHA = cur_file_sha
    return bundle


def infer_exact_tango_slot(
    d_lower: np.ndarray,
    d_upper: np.ndarray,
    one_sided: bool,
    tables_for_n: Optional[Dict[str, Any]] = None,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Compute certified unconditional exact Tango p-values and CIs under [0, 1] missingness bounds.

    Args:
        d_lower, d_upper: 1D integer/float arrays of length n with values in {-1, 0, +1} and d_lower <= d_upper.
        one_sided: True for SA1 (H0: theta <= 0 vs H1: theta > 0), False for two-sided (H0: theta == 0).
        tables_for_n: Optional pre-loaded dict {'f_plus_zero': ..., 'theta_L': {...}} for this n.
        npz_path: Path to exact-tango-tables.npz when tables_for_n is None.
    """
    dl = np.asarray(d_lower)
    du = np.asarray(d_upper)
    if dl.ndim != 1 or dl.shape != du.shape or len(dl) < 1:
        raise ValueError(f"d_lower/d_upper shape mismatch: {dl.shape} vs {du.shape}")
    if not (np.all(np.isfinite(dl)) and np.all(np.isfinite(du))):
        raise ValueError("Non-finite values in d_lower/d_upper")

    dl_i = np.rint(dl).astype(np.int64)
    du_i = np.rint(du).astype(np.int64)
    if not (np.array_equal(dl, dl_i) and np.array_equal(du, du_i)):
        raise ValueError("d_lower and d_upper must take exact trinary integer values in {-1, 0, +1}")
    if not (np.all(np.isin(dl_i, (-1, 0, 1))) and np.all(np.isin(du_i, (-1, 0, 1)))):
        raise ValueError("d_lower/d_upper values outside {-1, 0, +1}")
    if np.any(dl_i > du_i):
        raise ValueError("Sample-path ordering violated: d_lower > d_upper")

    n = int(len(dl_i))
    x_l = int(np.count_nonzero(dl_i == 1))
    y_l = int(np.count_nonzero(dl_i == -1))
    x_u = int(np.count_nonzero(du_i == 1))
    y_u = int(np.count_nonzero(du_i == -1))

    if not (0 <= x_l <= x_u <= n and 0 <= y_u <= y_l <= n and x_l + y_l <= n and x_u + y_u <= n):
        raise AssertionError("Invalid trinary count bounds")

    if tables_for_n is None:
        bundle = load_certified_tango_tables(npz_path=npz_path)
        if n not in bundle["by_n"]:
            raise KeyError(f"Sample size n={n} not present in precomputed exact-tango-tables.npz")
        tables_for_n = bundle["by_n"][n]

    f_plus = tables_for_n["f_plus_zero"]
    th_dict = tables_for_n["theta_L"]

    pplus = float(f_plus[x_l, y_l])
    pminus = float(f_plus[y_u, x_u])

    if x_l > y_l:
        obs_dir = 1
    elif x_u < y_u:
        obs_dir = -1
    else:
        obs_dir = 0

    if one_sided:
        p_val = pplus if obs_dir == 1 else 1.0
    else:
        p_val = min(1.0, 2.0 * min(pplus, pminus)) if obs_dir != 0 else 1.0

    def _lookup_ci(alpha_str: str) -> Tuple[List[float], bool]:
        th_mat = th_dict[alpha_str]
        lo = float(th_mat[x_l, y_l])
        hi = -float(th_mat[y_u, x_u])
        invalid = (not math.isfinite(lo)) or (not math.isfinite(hi)) or (lo < -1.0) or (hi > 1.0) or (lo > hi)
        if invalid:
            return [-1.0, 1.0], True
        return [lo, hi], False

    ci_9875, fail_9875 = _lookup_ci("0.0125")
    ci_995, fail_995 = _lookup_ci("0.005")
    ci_95, fail_95 = _lookup_ci("0.05")

    if fail_9875:
        p_val = 1.0

    pt_lo = (x_l - y_l) / float(n)
    pt_hi = (x_u - y_u) / float(n)

    return {
        "n": n,
        "point_lower": pt_lo,
        "point_upper": pt_hi,
        "point": pt_lo if x_l == x_u and y_l == y_u else [pt_lo, pt_hi],
        "counts_lower": {"n_plus": x_l, "n_zero": n - x_l - y_l, "n_minus": y_l},
        "counts_upper": {"n_plus": x_u, "n_zero": n - x_u - y_u, "n_minus": y_u},
        "observed_direction": obs_dir,
        "p": p_val,
        "pplus": pplus,
        "pminus": pminus,
        "ci_9875": ci_9875,
        "ci_995": ci_995,
        "ci_95": ci_95,
        "degenerate_9875": fail_9875,
        "degenerate_995": fail_995,
        "degenerate_95": fail_95,
        "failure_ci": fail_9875,
    }


def main():
    parser = argparse.ArgumentParser(description="Build certified unconditional exact Tango tables for n in {20, 80}.")
    parser.add_argument("--out-npz", default=str(DEFAULT_TABLES_NPZ), help="Output .npz path")
    parser.add_argument("--out-meta", default=str(DEFAULT_TABLES_META), help="Output metadata .json path")
    parser.add_argument("--workers", type=int, default=4, help="Worker processes (max 4)")
    args = parser.parse_args()

    print(f"Building certified exact Tango tables (workers={min(4, max(1, args.workers))})...", flush=True)
    meta = build_and_save_exact_tango_tables(
        npz_path=Path(args.out_npz),
        meta_path=Path(args.out_meta),
        workers=args.workers,
    )
    print(
        f"Built exact Tango tables in {meta['build_wall_seconds']:.2f}s | "
        f"file_sha256={meta['npz_file_sha256']} | payload_sha256={meta['npz_payload_sha256']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
