"""S4 Pre-Freeze 16-Cell Statistical Calibration & Candidate Selection for Experiment 2 (PLAN-E2.md §4.2.6).

Implements:
- Exact 16-cell calibration matrix (4 DGPs x 4 Truth/Missingness Configs), `CALIB_SEED_E2 = 2026110311`,
  `R = 2000` Monte Carlo replications per cell, `B = 5000` bootstrap draws per replication;
- Joint 3-unit generator `(P_bare, P_comp, M_comp)` on telic clusters (`n_T = 48`, quotas `21, 14, 8, 5`),
  preserving the shared experimental unit `P_comp = NI_COMP(P/Z)` and its shared missingness mask
  between `E2_H1` and `E2_H2`;
- 2-unit generator on atelic clusters (`n_A = 32`, quotas `16, 16`) for `E2_H3` and `E2_H4`;
- Both Candidate 1 (`hybrid_pct_tango_e2`) and Candidate 2 (`hybrid_bessel_t_tango_e2`) evaluated on the
  identical simulated datasets and identical bootstrap weight streams `(w_T, w_A)`;
- All 4 hard gates (`fwer_passed`, `simultaneous_coverage_9875_passed`, `individual_coverage_9875_passed`,
  `screen05_passed`) required across all 16 cells (including 2% missingness `CfgD_all_null_miss2`);
- Deterministic candidate selection order (`Candidate 1 -> Candidate 2 -> single-pass continuous slot
  demotion with m=4 preserved -> calibration_failed_stop_s5` with non-zero exit code).
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
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import numpy as np

from common import ROOT, read_json, sha256, write_json, write_text
from core_e2 import (
    ALPHA_FAM,
    B_DEFAULT,
    CONT_SLOT_ORDER,
    E2_SLOT_ORDER,
    M_SLOTS,
    draw_macro_bootstrap_weights_e2,
    extract_unit_continuous_bounds,
    extract_unit_label_true_bounds,
    holm_step_down_e2,
    infer_continuous_slot_e2,
    infer_discrete_slot_e2,
)
from exact_tango_e2 import DEFAULT_TABLES_NPZ, load_certified_tango_tables, verify_ieee754_rn_and_subnormals
from ledger import Ledger, ledger_digest

CALIB_SEED_E2 = 2026110311
R_DEFAULT = 2000

N_TELIC_FORMAL = 48
TELIC_QUOTAS_FORMAL = (21, 14, 8, 5)  # Creation, Change of State, Consumption, Motion to Goal
TELIC_HET_SHIFTS = (8.0, -12.0, 7.5, -12.0)  # 21*8 + 14*(-12) + 8*7.5 + 5*(-12) == 0.0

N_ATELIC_FORMAL = 32
ATELIC_QUOTAS_FORMAL = (16, 16)  # A_plan, A_pure
ATELIC_HET_SHIFTS = (12.0, -12.0)  # 16*12 + 16*(-12) == 0.0

DGP_NAMES: Tuple[str, ...] = (
    "DGP1_emp",
    "DGP2_skew",
    "DGP3_ties",
    "DGP4_het",
)

CFG_SPECS: Dict[str, Dict[str, Any]] = {
    "CfgA_all_null_comp": {
        "theta": {"E2_H1": 0.0, "E2_H2": 0.0, "E2_H3": 0.0, "E2_H4": 0.0},
        "null_slots": ("E2_H1", "E2_H2", "E2_H3", "E2_H4"),
        "unit_miss_prob": 0.0,
    },
    "CfgB_half_null_comp": {
        "theta": {"E2_H1": 20.0, "E2_H2": 0.0, "E2_H3": 25.0, "E2_H4": 0.0},
        "null_slots": ("E2_H2", "E2_H4"),
        "unit_miss_prob": 0.0,
    },
    "CfgC_alt_null_comp": {
        "theta": {"E2_H1": 0.0, "E2_H2": 15.0, "E2_H3": 0.0, "E2_H4": 0.35},
        "null_slots": ("E2_H1", "E2_H3"),
        "unit_miss_prob": 0.0,
    },
    "CfgD_all_null_miss2": {
        "theta": {"E2_H1": 0.0, "E2_H2": 0.0, "E2_H3": 0.0, "E2_H4": 0.0},
        "null_slots": ("E2_H1", "E2_H2", "E2_H3", "E2_H4"),
        "unit_miss_prob": 0.01,
    },
}

DEFAULT_DEV_EMP_PROFILE: Dict[str, Any] = {
    "source": "synthetic_dev_default",
    "telic_e1": [-18.0, -12.0, -8.0, -4.0, -2.0, 0.0, 2.0, 4.0, 8.0, 12.0, 18.0, 24.0],
    "telic_e2": [-15.0, -10.0, -6.0, -3.0, 0.0, 0.0, 3.0, 5.0, 7.0, 11.0, 14.0, 20.0],
    "atelic_e3": [-16.0, -9.0, -4.0, 0.0, 2.0, 5.0, 10.0, 18.0],
    "tau_dev_h4": 0.375,
}


def _norm_cdf_vec(z: np.ndarray) -> np.ndarray:
    """Standard normal CDF Phi(z) in pure IEEE-754 float64."""
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    return np.array([0.5 * (1.0 + math.erf(float(val) * inv_sqrt2)) for val in z.ravel()], dtype=np.float64).reshape(
        z.shape
    )


def _beta28_ppf_vec(p: np.ndarray) -> np.ndarray:
    """Exact inverse CDF of Beta(2, 8) via vectorized Newton-Raphson + bisection bracket on F(u) = 1 - (1-u)^8*(1+8u)."""
    p_arr = np.clip(np.asarray(p, dtype=np.float64), 0.0, 1.0)
    lo = np.zeros_like(p_arr)
    hi = np.ones_like(p_arr)
    u = np.full_like(p_arr, 0.2)
    for _ in range(28):
        om = 1.0 - u
        om7 = om ** 7
        cdf = 1.0 - om7 * om * (1.0 + 8.0 * u)
        diff = cdf - p_arr
        lo = np.where(diff < 0.0, u, lo)
        hi = np.where(diff >= 0.0, u, hi)
        pdf = 72.0 * u * om7
        cand = np.where(pdf > 1e-14, u - diff / np.maximum(pdf, 1e-14), 0.5 * (lo + hi))
        in_bracket = (cand > lo) & (cand < hi)
        u = np.where(in_bracket, cand, 0.5 * (lo + hi))
    u = np.where(p_arr <= 0.0, 0.0, np.where(p_arr >= 1.0, 1.0, u))
    return u


def compute_calibration_code_hashes() -> Dict[str, str]:
    """Compute SHA-256 digests of S2/S4 inference & calibration code and certified Tango tables."""
    return {
        "core_e2.py": sha256(ROOT / "core_e2.py"),
        "calibrate_e2.py": sha256(ROOT / "calibrate_e2.py"),
        "exact_tango_e2.py": sha256(ROOT / "exact_tango_e2.py"),
        "exact-tango-tables-e2.npz": sha256(DEFAULT_TABLES_NPZ),
    }


def build_dev_profile_from_rows(
    dev_rows: Sequence[Dict[str, Any]],
    *,
    dev_run_id: Optional[str] = None,
    dev_ledger_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract empirical cluster residuals and H4 discordant rate from real S3 development-set rows."""
    clusters = read_json(ROOT / "data" / "clusters_100_curated.json")
    cluster_by_id = {c["cluster_id"]: c for c in clusters}
    dev_cids = sorted(set(read_json(ROOT / "split.json")["dev_cluster_ids"]))
    telic_cids = sorted(cid for cid in dev_cids if cluster_by_id[cid]["macro_class"] == "telic")
    atelic_cids = sorted(cid for cid in dev_cids if cluster_by_id[cid]["macro_class"] == "atelic")
    if len(telic_cids) != 12 or len(atelic_cids) != 8:
        raise ValueError(f"Expected 12 telic and 8 atelic dev clusters, got ({len(telic_cids)}, {len(atelic_cids)})")

    by_unit = {r["unit_key"]: r for r in dev_rows if isinstance(r, dict) and "unit_key" in r}
    required_keys = [
        f"{cid}__{slot}/{task}/{prompt}"
        for cid in telic_cids
        for slot, task, prompt in (("NI_BARE", "P", "Z"), ("NI_COMP", "P", "Z"), ("NI_COMP", "M", "Z"))
    ] + [
        f"{cid}__{slot}/{task}/{prompt}"
        for cid in atelic_cids
        for slot, task, prompt in (("INT_BARE", "P", "Z"), ("INT_COMP", "P", "Z"), ("NI_BARE", "L", "CoT"), ("NI_COMP", "L", "CoT"))
    ]
    missing_keys = [k for k in required_keys if k not in by_unit]
    if missing_keys:
        raise ValueError(f"Dev rows missing {len(missing_keys)} required calibration units (e.g. {missing_keys[0]})")

    non_ok_keys = [k for k in required_keys if by_unit[k].get("status") != "ok"]
    if non_ok_keys:
        k0 = non_ok_keys[0]
        raise ValueError(
            f"Dev calibration requires status=='ok' on all 68 primary dev units; "
            f"{len(non_ok_keys)} unit(s) non-ok (e.g. {k0} has status={by_unit[k0].get('status')!r})"
        )

    def _exact_point(uk: str, bounds: Tuple[float, float]) -> float:
        lo, hi = float(bounds[0]), float(bounds[1])
        if not (math.isfinite(lo) and math.isfinite(hi) and abs(lo - hi) <= 1e-12):
            raise ValueError(f"Required dev calibration unit {uk} produced non-point bounds {(lo, hi)}")
        return lo

    telic_e1: List[float] = []
    telic_e2: List[float] = []
    for cid in telic_cids:
        uk_pb = f"{cid}__NI_BARE/P/Z"
        uk_pc = f"{cid}__NI_COMP/P/Z"
        uk_mc = f"{cid}__NI_COMP/M/Z"
        pb = _exact_point(uk_pb, extract_unit_continuous_bounds(by_unit[uk_pb], "value"))
        pc = _exact_point(uk_pc, extract_unit_continuous_bounds(by_unit[uk_pc], "value"))
        mc = _exact_point(uk_mc, extract_unit_continuous_bounds(by_unit[uk_mc], "M_U"))
        telic_e1.append(pb - pc)
        telic_e2.append(pc - mc)

    atelic_e3: List[float] = []
    discordant_h4 = 0.0
    for cid in atelic_cids:
        uk_ib = f"{cid}__INT_BARE/P/Z"
        uk_ic = f"{cid}__INT_COMP/P/Z"
        uk_lb = f"{cid}__NI_BARE/L/CoT"
        uk_lc = f"{cid}__NI_COMP/L/CoT"
        ib = _exact_point(uk_ib, extract_unit_continuous_bounds(by_unit[uk_ib], "value"))
        ic = _exact_point(uk_ic, extract_unit_continuous_bounds(by_unit[uk_ic], "value"))
        atelic_e3.append(ib - ic)
        lb = _exact_point(uk_lb, extract_unit_label_true_bounds(by_unit[uk_lb], False))
        lc = _exact_point(uk_lc, extract_unit_label_true_bounds(by_unit[uk_lc], False))
        if abs(lb - lc) > 0.5:
            discordant_h4 += 1.0

    dev_run_ids = sorted({str(r["run_id"]) for r in dev_rows if isinstance(r, dict) and r.get("run_id")})
    if dev_run_id is not None and dev_run_ids and dev_run_id not in dev_run_ids and dev_run_id != ",".join(dev_run_ids):
        raise ValueError(f"Explicit dev_run_id={dev_run_id!r} not found in dev ledger run_ids {dev_run_ids!r}")
    inferred_run_id = dev_run_id or (
        dev_run_ids[0] if len(dev_run_ids) == 1 else (",".join(dev_run_ids) if dev_run_ids else None)
    )
    dev_ledger_dig = ledger_digest(list(dev_rows)) if dev_rows else None
    return {
        "source": "dev_ledger",
        "dev_run_id": inferred_run_id,
        "dev_run_ids": dev_run_ids,
        "dev_ledger_sha256": dev_ledger_sha256,
        "dev_ledger_digest": dev_ledger_dig,
        "telic_e1": telic_e1,
        "telic_e2": telic_e2,
        "atelic_e3": atelic_e3,
        "tau_dev_h4": discordant_h4 / float(len(atelic_cids)),
    }


def prepare_dgp1_residuals(
    dev_profile: Optional[Dict[str, Any]] = None,
    *,
    dev_rows: Optional[Sequence[Dict[str, Any]]] = None,
    dev_ledger_path: Optional[Path | str] = None,
    dev_run_id: Optional[str] = None,
    allow_synthetic: bool = True,
) -> Dict[str, Any]:
    """Center and scale development-set empirical residuals so r_tilde in [-35.0, +35.0] and mean == 0."""
    if dev_ledger_path is not None:
        lpath = Path(dev_ledger_path)
        ns_dir = lpath.parent if lpath.name == "results.jsonl" else lpath
        res_file = ns_dir / "results.jsonl"
        if not res_file.is_file():
            raise FileNotFoundError(f"Development ledger results.jsonl not found: {res_file}")
        valid_rows = Ledger(ns_dir).load(repair=False)
        prof = build_dev_profile_from_rows(
            valid_rows,
            dev_run_id=dev_run_id,
            dev_ledger_sha256=sha256(res_file),
        )
    elif dev_rows is not None:
        prof = build_dev_profile_from_rows(dev_rows, dev_run_id=dev_run_id)
    elif dev_profile is not None:
        prof = dev_profile
    elif allow_synthetic:
        prof = DEFAULT_DEV_EMP_PROFILE
    else:
        raise ValueError(
            "Production S4 calibration requires real S3 development data (--dev-ledger or dev_rows); "
            "synthetic default is only allowed when --allow-synthetic / allow_synthetic=True is set."
        )

    e1 = np.asarray(prof["telic_e1"], dtype=np.float64)
    e2 = np.asarray(prof["telic_e2"], dtype=np.float64)
    e3 = np.asarray(prof["atelic_e3"], dtype=np.float64)
    if len(e1) != 12 or len(e2) != 12 or len(e3) != 8:
        raise ValueError(f"Expected dev residual lengths (12, 12, 8), got ({len(e1)}, {len(e2)}, {len(e3)})")

    def _center_scale(vec: np.ndarray) -> Tuple[np.ndarray, float]:
        r = vec - float(np.mean(vec))
        max_abs = float(np.max(np.abs(r)))
        kappa = min(1.0, 35.0 / max(1e-12, max_abs))
        scaled = r * kappa
        scaled = scaled - float(np.mean(scaled))
        if np.any(np.abs(scaled) > 35.0 + 1e-12):
            raise AssertionError("Scaled empirical residual exceeded [-35.0, +35.0]")
        return scaled, kappa

    r1, k1 = _center_scale(e1)
    r2, k2 = _center_scale(e2)
    r3, k3 = _center_scale(e3)
    tau0 = float(np.clip(float(prof["tau_dev_h4"]), 0.15, 0.80))
    return {
        "source": prof.get("source", "custom"),
        "dev_run_id": prof.get("dev_run_id"),
        "dev_run_ids": list(prof.get("dev_run_ids") or ([prof["dev_run_id"]] if prof.get("dev_run_id") else [])),
        "dev_ledger_sha256": prof.get("dev_ledger_sha256"),
        "dev_ledger_digest": prof.get("dev_ledger_digest"),
        "r1_scaled": r1,
        "r2_scaled": r2,
        "r3_scaled": r3,
        "kappa": {"E2_H1": k1, "E2_H2": k2, "E2_H3": k3},
        "tau0_h4": tau0,
    }


def trinomial_probs_from_tau0(tau0: float, theta4: float) -> Tuple[float, float, float]:
    """Valid simplex parameterization tau(theta4) = max(tau0, |theta4| + 0.10) per PLAN-E2.md §4.2.6."""
    if not (0.15 - 1e-12 <= tau0 <= 0.80 + 1e-12):
        raise ValueError(f"tau0={tau0} outside [0.15, 0.80]")
    if abs(theta4) > 0.60 + 1e-12:
        raise ValueError(f"|theta4|={abs(theta4)} exceeds 0.60")
    tau = max(float(tau0), abs(float(theta4)) + 0.10)
    pi_plus = 0.5 * (tau + float(theta4))
    pi_minus = 0.5 * (tau - float(theta4))
    pi_zero = 1.0 - tau
    if not (pi_plus >= 0.05 - 1e-12 and pi_minus >= 0.05 - 1e-12 and pi_zero >= 0.20 - 1e-12):
        raise AssertionError(f"Invalid trinomial probabilities ({pi_plus}, {pi_minus}, {pi_zero})")
    return pi_plus, pi_minus, pi_zero


def generate_joint_units_one_rep(
    rng: np.random.Generator,
    dgp_name: str,
    cfg_name: str,
    dgp1_prep: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate underlying cluster units and paired difference bounds for one simulation replication.

    Strictly enforces the joint 3-unit construction `(P_bare, P_comp, M_comp)` on telic clusters
    (`n_T = 48`) so `E2_H1` and `E2_H2` share the exact same `P_comp = NI_COMP(P/Z)` reading and
    its missingness indicator (`PLAN-E2.md` §4.2.6).
    """
    cfg = CFG_SPECS[cfg_name]
    th1 = float(cfg["theta"]["E2_H1"])
    th2 = float(cfg["theta"]["E2_H2"])
    th3 = float(cfg["theta"]["E2_H3"])
    th4 = float(cfg["theta"]["E2_H4"])
    miss_p = float(cfg["unit_miss_prob"])

    if dgp_name == "DGP1_emp":
        idx_t = rng.integers(0, 12, size=N_TELIC_FORMAL)
        eps1 = dgp1_prep["r1_scaled"][idx_t]
        eps2 = dgp1_prep["r2_scaled"][idx_t]
        idx_a = rng.integers(0, 8, size=N_ATELIC_FORMAL)
        eps3 = dgp1_prep["r3_scaled"][idx_a]
        pi_p, pi_m, pi_z = trinomial_probs_from_tau0(dgp1_prep["tau0_h4"], th4)
        h4_probs = np.tile([pi_p, pi_m, pi_z], (N_ATELIC_FORMAL, 1))
    elif dgp_name == "DGP2_skew":
        # Bivariate normal with rho = 0.5 -> Phi -> Beta(2, 8) inverse CDF
        z_ind = rng.standard_normal((N_TELIC_FORMAL, 2))
        z1 = z_ind[:, 0]
        z2 = 0.5 * z_ind[:, 0] + (math.sqrt(3.0) / 2.0) * z_ind[:, 1]
        u1 = _beta28_ppf_vec(_norm_cdf_vec(z1))
        u2 = _beta28_ppf_vec(_norm_cdf_vec(z2))
        eps1 = 40.0 * (u1 - 0.2)
        eps2 = 40.0 * (u2 - 0.2)
        z3 = rng.standard_normal(N_ATELIC_FORMAL)
        u3 = _beta28_ppf_vec(_norm_cdf_vec(z3))
        eps3 = 40.0 * (u3 - 0.2)
        pi_p, pi_m, pi_z = trinomial_probs_from_tau0(0.50, th4)
        h4_probs = np.tile([pi_p, pi_m, pi_z], (N_ATELIC_FORMAL, 1))
    elif dgp_name == "DGP3_ties":
        vals = np.array([-30.0, 0.0, 30.0], dtype=np.float64)
        probs = np.array([0.30, 0.40, 0.30], dtype=np.float64)
        eps1 = rng.choice(vals, size=N_TELIC_FORMAL, p=probs)
        eps2 = rng.choice(vals, size=N_TELIC_FORMAL, p=probs)
        eps3 = rng.choice(vals, size=N_ATELIC_FORMAL, p=probs)
        pi_p, pi_m, pi_z = trinomial_probs_from_tau0(0.15, th4)
        h4_probs = np.tile([pi_p, pi_m, pi_z], (N_ATELIC_FORMAL, 1))
    elif dgp_name == "DGP4_het":
        shifts_t = np.concatenate(
            [np.full(q, s, dtype=np.float64) for q, s in zip(TELIC_QUOTAS_FORMAL, TELIC_HET_SHIFTS)]
        )
        shifts_a = np.concatenate(
            [np.full(q, s, dtype=np.float64) for q, s in zip(ATELIC_QUOTAS_FORMAL, ATELIC_HET_SHIFTS)]
        )
        eps1 = shifts_t + rng.uniform(-20.0, 20.0, size=N_TELIC_FORMAL)
        eps2 = shifts_t + rng.uniform(-20.0, 20.0, size=N_TELIC_FORMAL)
        eps3 = shifts_a + rng.uniform(-20.0, 20.0, size=N_ATELIC_FORMAL)
        # H4 subclass heterogeneity: tau_sub = 0.70, theta4_plan = th4 + 0.25, theta4_pure = th4 - 0.25
        th_plan = th4 + 0.25
        th_pure = th4 - 0.25
        p_plan = [0.5 * (0.70 + th_plan), 0.5 * (0.70 - th_plan), 0.30]
        p_pure = [0.5 * (0.70 + th_pure), 0.5 * (0.70 - th_pure), 0.30]
        h4_probs = np.vstack([np.tile(p_plan, (16, 1)), np.tile(p_pure, (16, 1))])
    else:
        raise ValueError(f"Unknown DGP {dgp_name!r}")

    # Verify bounded perturbation support [-35.0, +35.0]
    if np.any(np.abs(eps1) > 35.0 + 1e-12) or np.any(np.abs(eps2) > 35.0 + 1e-12) or np.any(np.abs(eps3) > 35.0 + 1e-12):
        raise AssertionError("Perturbation exceeded [-35.0, +35.0]")

    # Joint 3-unit construction on telic clusters (i = 0..47)
    p_comp = 50.0 + 0.5 * (th2 - th1) + 0.5 * (eps2 - eps1)
    p_bare = p_comp + th1 + eps1
    m_comp = p_comp - th2 - eps2

    if (
        np.any(p_comp < 5.0 - 1e-12)
        or np.any(p_comp > 95.0 + 1e-12)
        or np.any(p_bare < 5.0 - 1e-12)
        or np.any(p_bare > 95.0 + 1e-12)
        or np.any(m_comp < 5.0 - 1e-12)
        or np.any(m_comp > 95.0 + 1e-12)
    ):
        raise AssertionError("Telic joint unit fell outside [5.0, 95.0]")

    # 2-unit construction on atelic clusters for E2_H3 (i = 0..31)
    x3 = 50.0 + 0.5 * (th3 + eps3)
    y3 = 50.0 - 0.5 * (th3 + eps3)
    if np.any(x3 < 20.0 - 1e-12) or np.any(x3 > 80.0 + 1e-12) or np.any(y3 < 20.0 - 1e-12) or np.any(y3 > 80.0 + 1e-12):
        raise AssertionError("Atelic E2_H3 unit fell outside [20.0, 80.0]")

    # 2-unit construction on atelic clusters for E2_H4 (i = 0..31)
    u_draw = rng.random(N_ATELIC_FORMAL)
    c1 = h4_probs[:, 0]
    c2 = c1 + h4_probs[:, 1]
    # Outcome 0: (I_bare=1, I_comp=0) -> d=+1; Outcome 1: (0, 1) -> d=-1; Outcome 2: (0, 0) -> d=0
    i_bare = np.where(u_draw < c1, 1, 0)
    i_comp = np.where((u_draw >= c1) & (u_draw < c2), 1, 0)

    # Underlying unit-level missingness masks (Bernoulli(miss_p))
    if miss_p > 0.0:
        miss_pbare = rng.random(N_TELIC_FORMAL) < miss_p
        miss_pcomp = rng.random(N_TELIC_FORMAL) < miss_p  # Shared by E2_H1 and E2_H2!
        miss_mcomp = rng.random(N_TELIC_FORMAL) < miss_p
        miss_x3 = rng.random(N_ATELIC_FORMAL) < miss_p
        miss_y3 = rng.random(N_ATELIC_FORMAL) < miss_p
        miss_ibare = rng.random(N_ATELIC_FORMAL) < miss_p
        miss_icomp = rng.random(N_ATELIC_FORMAL) < miss_p
    else:
        miss_pbare = np.zeros(N_TELIC_FORMAL, dtype=bool)
        miss_pcomp = np.zeros(N_TELIC_FORMAL, dtype=bool)
        miss_mcomp = np.zeros(N_TELIC_FORMAL, dtype=bool)
        miss_x3 = np.zeros(N_ATELIC_FORMAL, dtype=bool)
        miss_y3 = np.zeros(N_ATELIC_FORMAL, dtype=bool)
        miss_ibare = np.zeros(N_ATELIC_FORMAL, dtype=bool)
        miss_icomp = np.zeros(N_ATELIC_FORMAL, dtype=bool)

    pbare_lo = np.where(miss_pbare, 0.0, p_bare)
    pbare_hi = np.where(miss_pbare, 100.0, p_bare)
    pcomp_lo = np.where(miss_pcomp, 0.0, p_comp)
    pcomp_hi = np.where(miss_pcomp, 100.0, p_comp)
    mcomp_lo = np.where(miss_mcomp, 0.0, m_comp)
    mcomp_hi = np.where(miss_mcomp, 100.0, m_comp)

    d1_lo = pbare_lo - pcomp_hi
    d1_hi = pbare_hi - pcomp_lo
    d2_lo = pcomp_lo - mcomp_hi
    d2_hi = pcomp_hi - mcomp_lo

    x3_lo = np.where(miss_x3, 0.0, x3)
    x3_hi = np.where(miss_x3, 100.0, x3)
    y3_lo = np.where(miss_y3, 0.0, y3)
    y3_hi = np.where(miss_y3, 100.0, y3)
    d3_lo = x3_lo - y3_hi
    d3_hi = x3_hi - y3_lo

    ibare_lo = np.where(miss_ibare, 0, i_bare)
    ibare_hi = np.where(miss_ibare, 1, i_bare)
    icomp_lo = np.where(miss_icomp, 0, i_comp)
    icomp_hi = np.where(miss_icomp, 1, i_comp)
    d4_lo = ibare_lo - icomp_hi
    d4_hi = ibare_hi - icomp_lo

    return {
        "p_bare": p_bare,
        "p_comp": p_comp,
        "m_comp": m_comp,
        "x3": x3,
        "y3": y3,
        "i_bare": i_bare,
        "i_comp": i_comp,
        "miss_pbare": miss_pbare,
        "miss_pcomp": miss_pcomp,
        "miss_mcomp": miss_mcomp,
        "d1_lo": d1_lo,
        "d1_hi": d1_hi,
        "d2_lo": d2_lo,
        "d2_hi": d2_hi,
        "d3_lo": d3_lo,
        "d3_hi": d3_hi,
        "d4_lo": d4_lo,
        "d4_hi": d4_hi,
    }


def _evaluate_cell_worker(args: Tuple[int, str, str, int, int, int, Dict[str, Any], str]) -> Dict[str, Any]:
    """Worker to simulate one (dgp_name, cfg_name) cell over R replications with B bootstrap draws."""
    for env_k in SINGLE_THREAD_ENV_VARS:
        os.environ[env_k] = "1"
    verify_ieee754_rn_and_subnormals()
    cell_idx, dgp_name, cfg_name, r_reps, b_draws, base_seed, dgp1_prep, npz_path_str = args
    tango_bundle = load_certified_tango_tables(npz_path=Path(npz_path_str))
    tables_n32 = tango_bundle["by_n"][N_ATELIC_FORMAL]

    cell_seed = int(base_seed) + 100000 * (cell_idx + 1)
    rng_data = np.random.Generator(np.random.PCG64(cell_seed))

    # Store per-replication raw slot outputs for both pct and bessel_t so we can evaluate
    # Candidate 1, Candidate 2, and any Step 3 demoted family on the exact same R replications!
    pct_p = np.empty((r_reps, M_SLOTS), dtype=np.float64)
    pct_ci_lo = np.empty((r_reps, M_SLOTS), dtype=np.float64)
    pct_ci_hi = np.empty((r_reps, M_SLOTS), dtype=np.float64)
    pct_degen = np.zeros((r_reps, M_SLOTS), dtype=bool)

    bes_p = np.empty((r_reps, M_SLOTS), dtype=np.float64)
    bes_ci_lo = np.empty((r_reps, M_SLOTS), dtype=np.float64)
    bes_ci_hi = np.empty((r_reps, M_SLOTS), dtype=np.float64)
    bes_degen = np.zeros((r_reps, M_SLOTS), dtype=bool)

    shared_pcomp_missing_count = 0

    for rep in range(r_reps):
        sim = generate_joint_units_one_rep(rng_data, dgp_name, cfg_name, dgp1_prep)
        shared_pcomp_missing_count += int(np.count_nonzero(sim["miss_pcomp"]))

        boot_seed = cell_seed + rep + 1
        w_t, w_a = draw_macro_bootstrap_weights_e2(N_TELIC_FORMAL, N_ATELIC_FORMAL, b=b_draws, seed=boot_seed)

        h4_res = infer_discrete_slot_e2(sim["d4_lo"], sim["d4_hi"], one_sided=True, tables_for_n=tables_n32)

        for method, p_mat, lo_mat, hi_mat, dg_mat in (
            ("pct", pct_p, pct_ci_lo, pct_ci_hi, pct_degen),
            ("bessel_t", bes_p, bes_ci_lo, bes_ci_hi, bes_degen),
        ):
            h1_res = infer_continuous_slot_e2(sim["d1_lo"], sim["d1_hi"], w_t, method=method)
            h2_res = infer_continuous_slot_e2(sim["d2_lo"], sim["d2_hi"], w_t, method=method)
            h3_res = infer_continuous_slot_e2(sim["d3_lo"], sim["d3_hi"], w_a, method=method)

            for s_idx, s_res in enumerate((h1_res, h2_res, h3_res, h4_res)):
                p_mat[rep, s_idx] = float(s_res["p"])
                lo_mat[rep, s_idx] = float(s_res["ci_9875"][0])
                hi_mat[rep, s_idx] = float(s_res["ci_9875"][1])
                dg_mat[rep, s_idx] = bool(s_res["degenerate"])

    return {
        "cell_idx": cell_idx,
        "dgp": dgp_name,
        "cfg": cfg_name,
        "r_reps": r_reps,
        "b_draws": b_draws,
        "shared_pcomp_missing_total": shared_pcomp_missing_count,
        "pct": {
            "p": pct_p,
            "ci_lo": pct_ci_lo,
            "ci_hi": pct_ci_hi,
            "degen": pct_degen,
        },
        "bessel_t": {
            "p": bes_p,
            "ci_lo": bes_ci_lo,
            "ci_hi": bes_ci_hi,
            "degen": bes_degen,
        },
    }


def summarize_candidate_on_cell(
    raw_cell: Dict[str, Any],
    continuous_method: str,
    demoted_slots: Iterable[str] = (),
) -> Dict[str, Any]:
    """Compute the 4 hard gate metrics for a candidate method (and optional demoted slots) on one cell."""
    cfg_name = raw_cell["cfg"]
    cfg = CFG_SPECS[cfg_name]
    r_reps = int(raw_cell["r_reps"])
    se_sim = math.sqrt(ALPHA_FAM * (1.0 - ALPHA_FAM) / float(r_reps))
    fwer_cap = ALPHA_FAM + 2.0 * se_sim
    simult_cov_floor = (1.0 - ALPHA_FAM) - 2.0 * se_sim

    method_data = raw_cell[continuous_method]
    p_mat = method_data["p"].copy()
    lo_mat = method_data["ci_lo"].copy()
    hi_mat = method_data["ci_hi"].copy()
    degen_mat = method_data["degen"].copy()

    demoted_set = set(demoted_slots)
    for s_idx, slot in enumerate(E2_SLOT_ORDER):
        if slot in demoted_set:
            p_mat[:, s_idx] = 1.0
            lo_mat[:, s_idx] = -100.0
            hi_mat[:, s_idx] = 100.0

    theta_vec = np.array([float(cfg["theta"][s]) for s in E2_SLOT_ORDER], dtype=np.float64)
    null_indices = [idx for idx, s in enumerate(E2_SLOT_ORDER) if s in cfg["null_slots"]]

    # Coverage check per slot and simultaneously across all 4 slots
    covered_mat = (lo_mat <= theta_vec[None, :] + 1e-12) & (theta_vec[None, :] <= hi_mat + 1e-12)
    indiv_cov = {
        slot: float(np.mean(covered_mat[:, idx])) for idx, slot in enumerate(E2_SLOT_ORDER)
    }
    simult_cov = float(np.mean(np.all(covered_mat, axis=1)))
    degen_rate = {
        slot: float(np.mean(degen_mat[:, idx])) for idx, slot in enumerate(E2_SLOT_ORDER)
    }

    # Holm step-down across all 4 slots per replication
    any_null_rejected = 0
    slot_reject_counts = {slot: 0 for slot in E2_SLOT_ORDER}
    for rep in range(r_reps):
        p_map = {slot: float(p_mat[rep, idx]) for idx, slot in enumerate(E2_SLOT_ORDER)}
        holm_res = holm_step_down_e2(p_map)
        for slot in E2_SLOT_ORDER:
            if holm_res[slot]["rejected"]:
                slot_reject_counts[slot] += 1
        if any(holm_res[E2_SLOT_ORDER[idx]]["rejected"] for idx in null_indices):
            any_null_rejected += 1

    fwer = float(any_null_rejected) / float(r_reps)
    holm_power_or_type1 = {slot: float(slot_reject_counts[slot]) / float(r_reps) for slot in E2_SLOT_ORDER}
    screen05 = {
        E2_SLOT_ORDER[idx]: float(np.mean(p_mat[:, idx] <= 0.05)) for idx in null_indices
    }
    diag0125 = {
        E2_SLOT_ORDER[idx]: float(np.mean(p_mat[:, idx] <= 0.0125)) for idx in null_indices
    }

    fwer_passed = bool(fwer <= fwer_cap + 1e-12)
    simult_passed = bool(simult_cov + 1e-12 >= simult_cov_floor)
    indiv_passed = bool(all(val + 1e-12 >= 0.975 for val in indiv_cov.values()))
    screen05_passed = bool(all(val <= 0.075 + 1e-12 for val in screen05.values()))
    all_4_passed = bool(fwer_passed and simult_passed and indiv_passed and screen05_passed)

    return {
        "dgp": raw_cell["dgp"],
        "cfg": cfg_name,
        "continuous_method": continuous_method,
        "demoted_slots": sorted(demoted_set),
        "r_reps": r_reps,
        "b_draws": int(raw_cell["b_draws"]),
        "fwer": fwer,
        "fwer_cap": fwer_cap,
        "fwer_passed": fwer_passed,
        "simultaneous_coverage_9875": simult_cov,
        "simultaneous_coverage_floor": simult_cov_floor,
        "simultaneous_coverage_9875_passed": simult_passed,
        "individual_coverage_9875": indiv_cov,
        "individual_coverage_9875_passed": indiv_passed,
        "screen05_null_slots": screen05,
        "screen05_passed": screen05_passed,
        "diagnostic_p0125_null_slots": diag0125,
        "holm_rejection_rate": holm_power_or_type1,
        "degeneracy_rate": degen_rate,
        "cell_passed": all_4_passed,
    }


def validate_raw_cells(
    raw_cells: Sequence[Dict[str, Any]],
    *,
    expected_r_reps: Optional[int] = None,
    expected_b_draws: Optional[int] = None,
) -> None:
    """Validate that raw_cells covers all 16 unique (DGP, Config) cells with consistent parameters and shapes."""
    if not isinstance(raw_cells, (list, tuple)) or len(raw_cells) != 16:
        raise ValueError(f"Expected 16 calibration cells, got {len(raw_cells) if isinstance(raw_cells, (list, tuple)) else type(raw_cells)}")
    expected_pairs = [(d, c) for d in DGP_NAMES for c in CFG_SPECS]
    seen_pairs = set()
    ref_r = None
    ref_b = None
    for cell in raw_cells:
        if not isinstance(cell, dict):
            raise ValueError("Calibration cell must be a dict")
        pair = (cell.get("dgp"), cell.get("cfg"))
        if pair not in expected_pairs:
            raise ValueError(f"Unexpected calibration cell (dgp, cfg) = {pair!r}")
        if pair in seen_pairs:
            raise ValueError(f"Duplicate calibration cell (dgp, cfg) = {pair!r}")
        seen_pairs.add(pair)
        r_reps = int(cell.get("r_reps", 0))
        b_draws = int(cell.get("b_draws", 0))
        if r_reps < 1 or b_draws < 1:
            raise ValueError(f"Invalid r_reps={r_reps} or b_draws={b_draws} in cell {pair}")
        if ref_r is None:
            ref_r, ref_b = r_reps, b_draws
        elif (r_reps, b_draws) != (ref_r, ref_b):
            raise ValueError(f"Inconsistent (r_reps, b_draws) across cells: {(r_reps, b_draws)} != {(ref_r, ref_b)}")
        for method in ("pct", "bessel_t"):
            mdata = cell.get(method)
            if not isinstance(mdata, dict):
                raise ValueError(f"Cell {pair} missing method data {method!r}")
            for arr_key in ("p", "ci_lo", "ci_hi", "degen"):
                arr = mdata.get(arr_key)
                if not isinstance(arr, np.ndarray) or arr.shape != (r_reps, M_SLOTS):
                    raise ValueError(
                        f"Cell {pair} method {method!r} array {arr_key!r} has invalid shape "
                        f"{getattr(arr, 'shape', None)} != {(r_reps, M_SLOTS)}"
                    )
    if seen_pairs != set(expected_pairs):
        raise ValueError("Missing required (dgp, cfg) cells in raw_cells")
    if expected_r_reps is not None and ref_r != int(expected_r_reps):
        raise ValueError(f"raw_cells r_reps={ref_r} != expected_r_reps={expected_r_reps}")
    if expected_b_draws is not None and ref_b != int(expected_b_draws):
        raise ValueError(f"raw_cells b_draws={ref_b} != expected_b_draws={expected_b_draws}")


def _derive_step3_demotion_set(
    cand2_cells: Sequence[Dict[str, Any]],
) -> Tuple[List[str], Optional[str]]:
    """Derive the deterministic Step 3 demotion set D (and optional stop-S5 failure reason) from Candidate 2 cells."""
    h4_indiv_failed = any(
        (float(c["individual_coverage_9875"]["E2_H4"]) + 1e-12 < 0.975)
        or (float(c["screen05_null_slots"].get("E2_H4", 0.0)) > 0.075 + 1e-12)
        for c in cand2_cells
    )
    if h4_indiv_failed:
        return [], "E2_H4 violated individual hard gate under Candidate 2; demotion of E2_H4 forbidden"

    violating_cont: List[str] = []
    for slot in CONT_SLOT_ORDER:
        failed_slot = any(
            (float(c["individual_coverage_9875"][slot]) + 1e-12 < 0.975)
            or (float(c["screen05_null_slots"].get(slot, 0.0)) > 0.075 + 1e-12)
            for c in cand2_cells
        )
        if failed_slot:
            violating_cont.append(slot)

    if len(violating_cont) == 0:
        tie_priority = {"E2_H3": 0, "E2_H2": 1, "E2_H1": 2}
        min_cov_by_slot = {
            slot: min(float(c["individual_coverage_9875"][slot]) for c in cand2_cells) for slot in CONT_SLOT_ORDER
        }
        worst_slot = min(CONT_SLOT_ORDER, key=lambda s: (min_cov_by_slot[s], tie_priority[s]))
        demote_d = [worst_slot]
    else:
        demote_d = sorted(set(violating_cont))

    if len(demote_d) >= 3:
        return demote_d, "All 3 continuous slots violated individual hard gates; demoting all 3 is forbidden"

    return demote_d, None


def select_candidate_deterministic(
    raw_cells: List[Dict[str, Any]],
    *,
    expected_r_reps: Optional[int] = None,
    expected_b_draws: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute the deterministic 4-step candidate selection & stop-S5 rule (PLAN-E2.md §4.2.6).

    Step 1: Evaluate Candidate 1 (`hybrid_pct_tango_e2`). If all 16 cells pass all 4 hard gates -> select Candidate 1.
    Step 2: Else evaluate Candidate 2 (`hybrid_bessel_t_tango_e2`). If all 16 cells pass -> select Candidate 2.
    Step 3: Else if `E2_H4` passes all individual gates across all 16 cells and 1 <= |D| <= 2 continuous slots
            need demotion, demote D once (preserving m=4) and re-evaluate on all 16 cells.
    Step 4: Otherwise return `status = "calibration_failed_stop_s5"`.
    """
    validate_raw_cells(raw_cells, expected_r_reps=expected_r_reps, expected_b_draws=expected_b_draws)
    cand1_cells = [summarize_candidate_on_cell(c, "pct", ()) for c in raw_cells]
    cand2_cells = [summarize_candidate_on_cell(c, "bessel_t", ()) for c in raw_cells]

    cand1_pass = all(c["cell_passed"] for c in cand1_cells)
    cand2_pass = all(c["cell_passed"] for c in cand2_cells)

    if cand1_pass:
        return {
            "status": "pass",
            "selected_step": 1,
            "selected_family": "hybrid_pct_tango_e2",
            "selected_continuous_method": "pct",
            "companion_family": "hybrid_bessel_t_tango_e2",
            "demoted_slots": [],
            "candidate_1_passed_all_16": True,
            "candidate_2_passed_all_16": cand2_pass,
            "candidate_1_cells": cand1_cells,
            "candidate_2_cells": cand2_cells,
            "step3_demoted_cells": None,
        }

    if cand2_pass:
        return {
            "status": "pass",
            "selected_step": 2,
            "selected_family": "hybrid_bessel_t_tango_e2",
            "selected_continuous_method": "bessel_t",
            "companion_family": "hybrid_pct_tango_e2",
            "demoted_slots": [],
            "candidate_1_passed_all_16": False,
            "candidate_2_passed_all_16": True,
            "candidate_1_cells": cand1_cells,
            "candidate_2_cells": cand2_cells,
            "step3_demoted_cells": None,
        }

    demote_d, stop_reason = _derive_step3_demotion_set(cand2_cells)
    if stop_reason is not None:
        return {
            "status": "calibration_failed_stop_s5",
            "selected_step": 4,
            "failure_reason": stop_reason,
            "selected_family": None,
            "selected_continuous_method": None,
            "demoted_slots": demote_d,
            "candidate_1_passed_all_16": False,
            "candidate_2_passed_all_16": False,
            "candidate_1_cells": cand1_cells,
            "candidate_2_cells": cand2_cells,
            "step3_demoted_cells": None,
        }

    step3_cells = [summarize_candidate_on_cell(c, "bessel_t", demote_d) for c in raw_cells]
    step3_pass = all(c["cell_passed"] for c in step3_cells)
    if step3_pass:
        return {
            "status": "pass",
            "selected_step": 3,
            "selected_family": "hybrid_bessel_t_tango_e2",
            "selected_continuous_method": "bessel_t",
            "companion_family": "hybrid_pct_tango_e2",
            "demoted_slots": sorted(demote_d),
            "candidate_1_passed_all_16": False,
            "candidate_2_passed_all_16": False,
            "candidate_1_cells": cand1_cells,
            "candidate_2_cells": cand2_cells,
            "step3_demoted_cells": step3_cells,
        }

    return {
        "status": "calibration_failed_stop_s5",
        "selected_step": 4,
        "failure_reason": f"Step 3 single-pass demotion of {demote_d} failed to pass all 16 cells",
        "selected_family": None,
        "selected_continuous_method": None,
        "demoted_slots": sorted(demote_d),
        "candidate_1_passed_all_16": False,
        "candidate_2_passed_all_16": False,
        "candidate_1_cells": cand1_cells,
        "candidate_2_cells": cand2_cells,
        "step3_demoted_cells": step3_cells,
    }


def _validate_cell_summary_list(
    cells: Any,
    *,
    label: str,
    expected_method: str,
    expected_demoted: Sequence[str],
    expected_r_reps: int,
    expected_b_draws: int,
) -> List[Dict[str, Any]]:
    """Validate that a 16-cell summary list covers all (DGP, Config) pairs and has internally consistent 4 hard gates."""
    if not isinstance(cells, list) or len(cells) != 16:
        raise ValueError(f"{label} must be a list of 16 cells")
    expected_pairs = [(d, c) for d in DGP_NAMES for c in CFG_SPECS]
    seen_pairs = set()
    se_sim = math.sqrt(ALPHA_FAM * (1.0 - ALPHA_FAM) / float(expected_r_reps))
    expected_fwer_cap = ALPHA_FAM + 2.0 * se_sim
    expected_simult_floor = (1.0 - ALPHA_FAM) - 2.0 * se_sim
    demoted_list = sorted(set(expected_demoted))

    for c in cells:
        if not isinstance(c, dict):
            raise ValueError(f"{label} cell must be a dict")
        pair = (c.get("dgp"), c.get("cfg"))
        if pair not in expected_pairs or pair in seen_pairs:
            raise ValueError(f"{label} has invalid or duplicate (dgp, cfg) pair {pair!r}")
        seen_pairs.add(pair)
        if c.get("r_reps") != expected_r_reps or c.get("b_draws") != expected_b_draws:
            raise ValueError(
                f"{label} cell {pair} (r_reps, b_draws)=({c.get('r_reps')}, {c.get('b_draws')}) "
                f"!= ({expected_r_reps}, {expected_b_draws})"
            )
        if c.get("continuous_method") != expected_method:
            raise ValueError(
                f"{label} cell {pair} continuous_method={c.get('continuous_method')!r} != {expected_method!r}"
            )
        if c.get("demoted_slots") != demoted_list:
            raise ValueError(
                f"{label} cell {pair} demoted_slots={c.get('demoted_slots')!r} != {demoted_list!r}"
            )

        try:
            fwer = float(c["fwer"])
            fwer_cap = float(c["fwer_cap"])
            scov = float(c["simultaneous_coverage_9875"])
            sfloor = float(c["simultaneous_coverage_floor"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{label} cell {pair} missing numeric FWER/simultaneous coverage fields") from exc

        if not (0.0 <= fwer <= 1.0 and 0.0 <= scov <= 1.0):
            raise ValueError(f"{label} cell {pair} FWER or simultaneous coverage out of [0, 1]")
        if abs(fwer_cap - expected_fwer_cap) > 1e-12 or abs(sfloor - expected_simult_floor) > 1e-12:
            raise ValueError(f"{label} cell {pair} fwer_cap or simultaneous_coverage_floor mismatch")

        icov = c.get("individual_coverage_9875")
        if not isinstance(icov, dict) or set(icov.keys()) != set(E2_SLOT_ORDER):
            raise ValueError(f"{label} cell {pair} invalid individual_coverage_9875 keys")
        for s_k, s_v in icov.items():
            fv = float(s_v)
            if not (0.0 <= fv <= 1.0):
                raise ValueError(f"{label} cell {pair} slot {s_k} coverage {fv} out of [0, 1]")
            if s_k in demoted_list and abs(fv - 1.0) > 1e-12:
                raise ValueError(f"{label} cell {pair} demoted slot {s_k} must have coverage 1.0, got {fv}")

        null_slots_cfg = set(CFG_SPECS[pair[1]]["null_slots"])
        scr = c.get("screen05_null_slots")
        if not isinstance(scr, dict) or set(scr.keys()) != null_slots_cfg:
            raise ValueError(f"{label} cell {pair} invalid screen05_null_slots keys")
        for s_k, s_v in scr.items():
            fv = float(s_v)
            if not (0.0 <= fv <= 1.0):
                raise ValueError(f"{label} cell {pair} slot {s_k} screen05 {fv} out of [0, 1]")
            if s_k in demoted_list and abs(fv - 0.0) > 1e-12:
                raise ValueError(f"{label} cell {pair} demoted null slot {s_k} must have screen05 0.0, got {fv}")

        fwer_ok = bool(fwer <= expected_fwer_cap + 1e-12)
        simult_ok = bool(scov + 1e-12 >= expected_simult_floor)
        indiv_ok = bool(all(float(icov[s]) + 1e-12 >= 0.975 for s in E2_SLOT_ORDER))
        scr_ok = bool(all(float(scr[s]) <= 0.075 + 1e-12 for s in null_slots_cfg))
        cell_ok = bool(fwer_ok and simult_ok and indiv_ok and scr_ok)

        if (
            c.get("fwer_passed") is not fwer_ok
            or c.get("simultaneous_coverage_9875_passed") is not simult_ok
            or c.get("individual_coverage_9875_passed") is not indiv_ok
            or c.get("screen05_passed") is not scr_ok
            or c.get("cell_passed") is not cell_ok
        ):
            raise ValueError(f"{label} cell {pair} boolean pass flags disagree with recomputed hard gate metrics")

    if seen_pairs != set(expected_pairs):
        raise ValueError(f"{label} missing required (dgp, cfg) pairs")
    return cells


def validate_calibration_artifact(
    cal: Dict[str, Any],
    *,
    require_production: bool = True,
    expected_dev_run_id: Optional[str] = None,
    expected_dev_run_ids: Optional[Sequence[str]] = None,
    expected_dev_ledger_sha256: Optional[str] = None,
    expected_dev_ledger_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate an S4 calibration artifact before S5 freeze or S7 formal analysis."""
    if not isinstance(cal, dict) or cal.get("schema_version") != "exp2-zh-s4-calibration-v1":
        raise ValueError("Invalid or missing calibration schema_version")
    if cal.get("status") != "pass":
        raise ValueError(f"S5 freeze / formal analysis blocked: calibration status is {cal.get('status')!r} != 'pass'")
    fam = cal.get("selected_family")
    if fam not in ("hybrid_pct_tango_e2", "hybrid_bessel_t_tango_e2"):
        raise ValueError(f"Invalid selected_family in calibration artifact: {fam!r}")
    demoted = cal.get("demoted_slots", [])
    if (
        not isinstance(demoted, list)
        or any(s not in CONT_SLOT_ORDER for s in demoted)
        or len(demoted) >= 3
        or demoted != sorted(set(demoted))
    ):
        raise ValueError(f"Invalid demoted_slots in calibration artifact: {demoted!r}")

    r_reps = int(cal.get("r_reps", 0))
    b_draws = int(cal.get("b_draws", 0))
    if r_reps < 1 or b_draws < 1:
        raise ValueError(f"Invalid calibration (r_reps, b_draws)=({r_reps}, {b_draws})")

    c1_cells = _validate_cell_summary_list(
        cal.get("candidate_1_cells"),
        label="candidate_1_cells",
        expected_method="pct",
        expected_demoted=(),
        expected_r_reps=r_reps,
        expected_b_draws=b_draws,
    )
    c2_cells = _validate_cell_summary_list(
        cal.get("candidate_2_cells"),
        label="candidate_2_cells",
        expected_method="bessel_t",
        expected_demoted=(),
        expected_r_reps=r_reps,
        expected_b_draws=b_draws,
    )
    c1_all_pass = all(c["cell_passed"] for c in c1_cells)
    c2_all_pass = all(c["cell_passed"] for c in c2_cells)
    if cal.get("candidate_1_passed_all_16") is not c1_all_pass:
        raise ValueError("candidate_1_passed_all_16 disagrees with candidate_1_cells")
    if cal.get("candidate_2_passed_all_16") is not c2_all_pass:
        raise ValueError("candidate_2_passed_all_16 disagrees with candidate_2_cells")

    step = cal.get("selected_step")
    if step == 1:
        if (
            not c1_all_pass
            or fam != "hybrid_pct_tango_e2"
            or cal.get("selected_continuous_method") != "pct"
            or cal.get("companion_family") != "hybrid_bessel_t_tango_e2"
            or demoted != []
            or cal.get("step3_demoted_cells") is not None
        ):
            raise ValueError("Step 1 calibration selection inconsistent with candidate_1_cells or metadata")
    elif step == 2:
        if (
            c1_all_pass
            or not c2_all_pass
            or fam != "hybrid_bessel_t_tango_e2"
            or cal.get("selected_continuous_method") != "bessel_t"
            or cal.get("companion_family") != "hybrid_pct_tango_e2"
            or demoted != []
            or cal.get("step3_demoted_cells") is not None
        ):
            raise ValueError("Step 2 calibration selection inconsistent with candidate_1/2_cells or metadata")
    elif step == 3:
        if (
            c1_all_pass
            or c2_all_pass
            or fam != "hybrid_bessel_t_tango_e2"
            or cal.get("selected_continuous_method") != "bessel_t"
            or cal.get("companion_family") != "hybrid_pct_tango_e2"
            or not (1 <= len(demoted) <= 2)
        ):
            raise ValueError("Step 3 calibration selection inconsistent with candidate_1/2_cells or demoted_slots")
        expected_d, stop_reason = _derive_step3_demotion_set(c2_cells)
        if stop_reason is not None or demoted != expected_d:
            raise ValueError(
                f"Step 3 demoted_slots {demoted!r} disagrees with candidate_2_cells derived demotion set "
                f"{expected_d!r} (stop_reason={stop_reason!r})"
            )
        s3_cells = _validate_cell_summary_list(
            cal.get("step3_demoted_cells"),
            label="step3_demoted_cells",
            expected_method="bessel_t",
            expected_demoted=demoted,
            expected_r_reps=r_reps,
            expected_b_draws=b_draws,
        )
        if not all(c["cell_passed"] for c in s3_cells):
            raise ValueError("Step 3 selected_step=3 requires all 16 step3_demoted_cells to pass all 4 hard gates")
        c2_by_pair = {(c["dgp"], c["cfg"]): c for c in c2_cells}
        for s3_cell in s3_cells:
            pair = (s3_cell["dgp"], s3_cell["cfg"])
            c2_cell = c2_by_pair[pair]
            for s_slot in E2_SLOT_ORDER:
                if s_slot not in demoted:
                    if abs(float(s3_cell["individual_coverage_9875"][s_slot]) - float(c2_cell["individual_coverage_9875"][s_slot])) > 1e-12:
                        raise ValueError(f"Step 3 cell {pair} non-demoted slot {s_slot} individual_coverage_9875 changed")
                    if s_slot in c2_cell["screen05_null_slots"]:
                        if abs(float(s3_cell["screen05_null_slots"][s_slot]) - float(c2_cell["screen05_null_slots"][s_slot])) > 1e-12:
                            raise ValueError(f"Step 3 cell {pair} non-demoted slot {s_slot} screen05_null_slots changed")
                    if isinstance(c2_cell.get("degeneracy_rate"), dict) and isinstance(s3_cell.get("degeneracy_rate"), dict):
                        if abs(float(s3_cell["degeneracy_rate"][s_slot]) - float(c2_cell["degeneracy_rate"][s_slot])) > 1e-12:
                            raise ValueError(f"Step 3 cell {pair} non-demoted slot {s_slot} degeneracy_rate changed")
            if float(s3_cell["fwer"]) > float(c2_cell["fwer"]) + 1e-12:
                raise ValueError(f"Step 3 cell {pair} FWER increased after slot demotion")
            if float(s3_cell["simultaneous_coverage_9875"]) + 1e-12 < float(c2_cell["simultaneous_coverage_9875"]):
                raise ValueError(f"Step 3 cell {pair} simultaneous_coverage_9875 decreased after slot demotion")
    else:
        raise ValueError(f"Invalid selected_step={step!r} for passing calibration artifact")

    if cal.get("code_hashes") != compute_calibration_code_hashes():
        raise ValueError("Calibration code_hashes do not match current core_e2/calibrate_e2/exact_tango_e2/tables")

    if require_production:
        if not cal.get("production_eligible"):
            raise ValueError("Calibration artifact is not production_eligible (synthetic or reduced R/B)")
        if cal.get("dev_source") != "dev_ledger":
            raise ValueError(f"Production calibration requires dev_source='dev_ledger', got {cal.get('dev_source')!r}")
        if r_reps != R_DEFAULT or b_draws != B_DEFAULT or cal.get("seed") != CALIB_SEED_E2:
            raise ValueError(
                f"Production calibration requires (R={R_DEFAULT}, B={B_DEFAULT}, seed={CALIB_SEED_E2}), "
                f"got ({r_reps}, {b_draws}, {cal.get('seed')})"
            )
        if not cal.get("dev_ledger_sha256"):
            raise ValueError("Production calibration artifact missing dev_ledger_sha256")
        if not cal.get("dev_ledger_digest"):
            raise ValueError("Production calibration artifact missing dev_ledger_digest")
        cal_run_id = str(cal.get("dev_run_id") or "")
        cal_run_ids = [str(x) for x in (cal.get("dev_run_ids") or ([cal_run_id] if cal_run_id else []))]
        if not cal_run_id or cal_run_id.startswith("E2-DRY-") or any(x.startswith("E2-DRY-") for x in cal_run_ids):
            raise ValueError("Production calibration artifact has missing or E2-DRY dev_run_id")
        if expected_dev_run_id is not None and cal_run_id != expected_dev_run_id and expected_dev_run_id not in cal_run_ids:
            raise ValueError(
                f"Calibration dev_run_id {cal_run_id!r} != expected {expected_dev_run_id!r}"
            )
        if expected_dev_run_ids is not None:
            exp_ids = sorted(set(str(x) for x in expected_dev_run_ids if x))
            if sorted(set(cal_run_ids)) != exp_ids:
                raise ValueError(
                    f"Calibration dev_run_ids {cal_run_ids!r} != expected dev stage run_ids {exp_ids!r}"
                )
        if expected_dev_ledger_sha256 is not None and cal.get("dev_ledger_sha256") != expected_dev_ledger_sha256:
            raise ValueError("Calibration dev_ledger_sha256 does not match current dev/results.jsonl")
        if expected_dev_ledger_digest is not None and cal.get("dev_ledger_digest") != expected_dev_ledger_digest:
            raise ValueError("Calibration dev_ledger_digest does not match current dev stage ledger_digest")
    return cal


def run_calibration_matrix_e2(
    *,
    r_reps: int = R_DEFAULT,
    b_draws: int = B_DEFAULT,
    seed: int = CALIB_SEED_E2,
    dev_profile: Optional[Dict[str, Any]] = None,
    dev_rows: Optional[Sequence[Dict[str, Any]]] = None,
    dev_ledger_path: Optional[Path | str] = None,
    dev_run_id: Optional[str] = None,
    allow_synthetic: bool = True,
    workers: int = 4,
    npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Run the 16-cell calibration matrix (4 DGPs x 4 Configs) and deterministic candidate selection."""
    t0 = time.perf_counter()
    verify_ieee754_rn_and_subnormals()
    dgp1_prep = prepare_dgp1_residuals(
        dev_profile,
        dev_rows=dev_rows,
        dev_ledger_path=dev_ledger_path,
        dev_run_id=dev_run_id,
        allow_synthetic=allow_synthetic,
    )

    tasks: List[Tuple[int, str, str, int, int, int, Dict[str, Any], str]] = []
    cell_idx = 0
    for dgp_name in DGP_NAMES:
        for cfg_name in CFG_SPECS:
            tasks.append((cell_idx, dgp_name, cfg_name, int(r_reps), int(b_draws), int(seed), dgp1_prep, str(npz_path)))
            cell_idx += 1

    n_workers = min(4, max(1, int(workers)))
    if n_workers == 1:
        raw_cells = [_evaluate_cell_worker(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            raw_cells = list(ex.map(_evaluate_cell_worker, tasks))
    raw_cells.sort(key=lambda x: x["cell_idx"])

    selection = select_candidate_deterministic(
        raw_cells,
        expected_r_reps=int(r_reps),
        expected_b_draws=int(b_draws),
    )
    elapsed = time.perf_counter() - t0
    dev_source = dgp1_prep["source"]
    dev_run_id_val = str(dgp1_prep.get("dev_run_id") or "")
    dev_run_ids_val = [str(x) for x in (dgp1_prep.get("dev_run_ids") or ([dev_run_id_val] if dev_run_id_val else []))]
    production_eligible = bool(
        dev_source == "dev_ledger"
        and dgp1_prep.get("dev_ledger_sha256")
        and dgp1_prep.get("dev_ledger_digest")
        and dev_run_id_val
        and not dev_run_id_val.startswith("E2-DRY-")
        and not any(x.startswith("E2-DRY-") for x in dev_run_ids_val)
        and int(r_reps) == R_DEFAULT
        and int(b_draws) == B_DEFAULT
        and int(seed) == CALIB_SEED_E2
    )
    return {
        "schema_version": "exp2-zh-s4-calibration-v1",
        "seed": int(seed),
        "r_reps": int(r_reps),
        "b_draws": int(b_draws),
        "n_telic": N_TELIC_FORMAL,
        "n_atelic": N_ATELIC_FORMAL,
        "dev_source": dev_source,
        "dev_run_id": dgp1_prep.get("dev_run_id"),
        "dev_run_ids": dev_run_ids_val,
        "dev_ledger_sha256": dgp1_prep.get("dev_ledger_sha256"),
        "dev_ledger_digest": dgp1_prep.get("dev_ledger_digest"),
        "production_eligible": production_eligible,
        "code_hashes": compute_calibration_code_hashes(),
        "wall_seconds": elapsed,
        "dgp1_empirical_prep": {
            "source": dev_source,
            "dev_run_id": dgp1_prep.get("dev_run_id"),
            "dev_run_ids": dev_run_ids_val,
            "dev_ledger_sha256": dgp1_prep.get("dev_ledger_sha256"),
            "dev_ledger_digest": dgp1_prep.get("dev_ledger_digest"),
            "kappa": dgp1_prep["kappa"],
            "tau0_h4": dgp1_prep["tau0_h4"],
        },
        **selection,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Experiment 2 S4 16-cell statistical calibration matrix.")
    parser.add_argument("--dev-ledger", default=None, help="Path to S3 dev.jsonl ledger (required for production S4 calibration)")
    parser.add_argument("--dev-run-id", default=None, help="Optional S3 run_id to bind into calibration artifact")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic dev profile (smoke/testing only; not production_eligible)")
    parser.add_argument("--r-reps", type=int, default=R_DEFAULT, help="Monte Carlo replications per cell (default 2000)")
    parser.add_argument("--b-draws", type=int, default=B_DEFAULT, help="Bootstrap draws per replication (default 5000)")
    parser.add_argument("--seed", type=int, default=CALIB_SEED_E2, help="Master calibration seed")
    parser.add_argument("--workers", type=int, default=4, help="Worker processes (max 4)")
    parser.add_argument("--out-json", default=str(ROOT / "raw" / "calibration_e2.json"), help="Output JSON path")
    args = parser.parse_args(argv)

    res = run_calibration_matrix_e2(
        r_reps=args.r_reps,
        b_draws=args.b_draws,
        seed=args.seed,
        dev_ledger_path=args.dev_ledger,
        dev_run_id=args.dev_run_id,
        allow_synthetic=bool(args.allow_synthetic),
        workers=args.workers,
    )
    write_json(Path(args.out_json), res)
    print(
        f"CALIBRATION E2: status={res['status']} | selected_step={res['selected_step']} | "
        f"family={res['selected_family']} | production_eligible={res['production_eligible']} | wall={res['wall_seconds']:.2f}s"
    )
    if res["status"] != "pass":
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
