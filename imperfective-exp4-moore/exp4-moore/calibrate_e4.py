"""Stage S4 Statistical Calibration Engine for Experiment 4 (`exp4-moore/PLAN-E4.md` §4.2(5)).

Runs the pre-registered 20-cell Monte Carlo calibration matrix (`5 DGPs x 4 Truth/Missingness
configs`, `R = 2000` replicates per cell, `B = 5000` bootstrap draws per replicate, fixed
seed `CALIB_SEED_E4 = 2026110611`) before Stage S5 freeze.

Key properties:
1. 8 pairwise disjoint underlying condition readings (`E4_H1..E4_H4`):
   - For each simulated cluster `i in 1..80` and continuous slot `j in 1..3`, given target
     `theta_j` and bounded perturbation `eps_{j,i} in [-35.0, +35.0]`, generates symmetrically
     centered paired readings `X_{j,i} = 50 + (theta_j + eps_{j,i})/2 in [20, 80]` and
     `Y_{j,i} = 50 - (theta_j + eps_{j,i})/2 in [20, 80]` so `X_{j,i} - Y_{j,i} = theta_j + eps_{j,i}`.
   - For `E4_H4`, uses simplex parameterization `tau(theta_4) = max(tau_0, |theta_4| + 0.10)`.
2. `DGP1_emp` complete-cluster filtering & hard pre-gate (`PLAN-E4.md` §4.2(5) item 1):
   - Filters each slot `j in 1..4` to complete dev clusters `K_{ok, j}` where both paired
     units have `status == "ok"`.
   - Enforces `|K_{ok, j}| >= 15` for all 4 slots; if any `< 15`, raises/stops with
     `insufficient_complete_dev_clusters_stop_s5`.
   - Uses `K_{ok, joint} = K_{ok, 1} cap K_{ok, 2} cap K_{ok, 3}` when `|K_{ok, joint}| >= 15`
     (else per-slot `K_{ok, j}`) for centering and scaling `[-35, +35]`.
3. 5 DGPs (`DGP1_emp`, `DGP2_skew`, `DGP3_ties`, `DGP4_het`, `DGP5_endpt`) x 4 Cfg (`CfgA..CfgD`) = 20 cells.
   `DGP4_het` uses 4-domain fixed quota (20 clusters per domain) with continuous shifts
   `(+12.0, +4.0, -4.0, -12.0)` and discrete shifts `(+0.15, +0.05, -0.05, -0.15)`.
4. Enforces the 4 hard gates across all 20 cells and deterministic Step 1 -> Step 2 -> Step 3 -> Step 4 rule.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

from common import RAW_ROOT, ROOT, atomic_json, digest, read_json, sha256, utc_now
import core_e4
from ledger import Ledger, ledger_digest

CALIB_SEED_E4 = 2026110611
R_DEFAULT = 2000
B_DEFAULT = 5000
N_FORMAL = 80
N_PER_DOMAIN = 20
MIN_COMPLETE_DEV_CLUSTERS = 15

# Hard Gate Constants (PLAN-E4.md §4.2(5), R=2000, SE_sim = sqrt(0.05*0.95/2000) ~= 0.0048734)
FWER_CAP = 0.059747
SIMULTANEOUS_COV_FLOOR = 0.940253
INDIVIDUAL_COV_FLOOR = 0.975
SCREEN05_CAP = 0.075

DGP_NAMES: tuple[str, ...] = (
    "DGP1_emp",
    "DGP2_skew",
    "DGP3_ties",
    "DGP4_het",
    "DGP5_endpt",
)

CFG_SPECS: dict[str, dict[str, Any]] = {
    "CfgA_all_null_comp": {
        "theta": {"E4_H1": 0.0, "E4_H2": 0.0, "E4_H3": 0.0, "E4_H4": 0.0},
        "null_slots": ("E4_H1", "E4_H2", "E4_H3", "E4_H4"),
        "missing_prob": 0.0,
    },
    "CfgB_half_null_comp": {
        "theta": {"E4_H1": 20.0, "E4_H2": 0.0, "E4_H3": 15.0, "E4_H4": 0.0},
        "null_slots": ("E4_H2", "E4_H4"),
        "missing_prob": 0.0,
    },
    "CfgC_alt_null_comp": {
        "theta": {"E4_H1": 0.0, "E4_H2": 25.0, "E4_H3": 0.0, "E4_H4": 0.35},
        "null_slots": ("E4_H1", "E4_H3"),
        "missing_prob": 0.0,
    },
    "CfgD_all_null_miss2": {
        "theta": {"E4_H1": 0.0, "E4_H2": 0.0, "E4_H3": 0.0, "E4_H4": 0.0},
        "null_slots": ("E4_H1", "E4_H2", "E4_H3", "E4_H4"),
        "missing_prob": 0.01,
    },
}

EXPECTED_CELL_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (dgp, cfg) for dgp in DGP_NAMES for cfg in CFG_SPECS
)
EXPECTED_TOTAL_CELLS = len(EXPECTED_CELL_PAIRS)  # 20


class InsufficientCompleteDevClustersError(ValueError):
    """Raised when any confirmatory slot has fewer than 15 complete dev clusters (`PLAN-E4.md` §4.2(5))."""


def _beta28_ppf_vec(p_arr: np.ndarray) -> np.ndarray:
    """Exact IEEE-754 double-precision inverse CDF of Beta(2, 8) via 64-step convergence-preserving Newton-Raphson."""
    p_clamped = np.clip(np.asarray(p_arr, dtype=np.float64), 0.0, 1.0)
    lo = np.zeros_like(p_clamped)
    hi = np.ones_like(p_clamped)
    u = np.full_like(p_clamped, 0.2)
    for _ in range(64):
        om = 1.0 - u
        om7 = np.power(om, 7)
        cdf = 1.0 - om7 * om * (1.0 + 8.0 * u)
        diff = cdf - p_clamped
        converged = np.abs(diff) <= 1e-16
        lo = np.where(diff < 0.0, u, lo)
        hi = np.where(diff > 0.0, u, hi)
        lo = np.where(converged, u, lo)
        hi = np.where(converged, u, hi)
        pdf = 72.0 * u * om7
        cand = np.where(pdf > 1e-14, u - diff / np.maximum(pdf, 1e-14), 0.5 * (lo + hi))
        in_bracket = (cand > lo) & (cand < hi)
        u_next = np.where(in_bracket, cand, 0.5 * (lo + hi))
        u = np.where(converged, u, u_next)
    return np.where(p_clamped <= 0.0, 0.0, np.where(p_clamped >= 1.0, 1.0, u))


_ERF_VEC = np.vectorize(math.erf, otypes=[np.float64])


def _norm_cdf_vec(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + _ERF_VEC(z / math.sqrt(2.0)))


def _correlated_beta_2_8(rng: np.random.Generator, n: int, rho: float = 0.5) -> np.ndarray:
    """Draw (n, 3) correlated Beta(2, 8) variables via Gaussian copula (`rho = 0.5`)."""
    cov = np.array([[1.0, rho, rho], [rho, 1.0, rho], [rho, rho, 1.0]], dtype=np.float64)
    chol = np.linalg.cholesky(cov)
    z = rng.standard_normal(size=(n, 3)) @ chol.T
    u_norm = _norm_cdf_vec(z)
    return _beta28_ppf_vec(u_norm)


def compute_calibration_code_hashes() -> dict[str, str]:
    """Compute SHA-256 digests of S2/S4 inference & calibration code and certified Tango tables."""
    return {
        "core_e4.py": sha256(ROOT / "core_e4.py"),
        "calibrate_e4.py": sha256(ROOT / "calibrate_e4.py"),
        "exact_tango_e4.py": sha256(ROOT / "exact_tango_e4.py"),
        "exact-tango-tables-e4.npz": sha256(ROOT / "manifests" / "exact-tango-tables-e4.npz"),
    }


def build_dev_profile_from_rows(
    dev_rows: list[dict[str, Any]],
    dev_cids: list[str] | None = None,
    *,
    dev_run_id: str | None = None,
    dev_ledger_sha256: str | None = None,
) -> dict[str, Any]:
    """Extract empirical S4 dev residuals for `DGP1_emp` with complete-cluster filtering (`PLAN-E4.md` §4.2(5))."""
    if dev_cids is None:
        split_obj = read_json(ROOT / "split.json")
        dev_cids = sorted(split_obj["dev"]["cluster_ids"])
    else:
        dev_cids = sorted(dev_cids)

    ext = core_e4.extract_primary_inputs_from_records_e4(
        dev_rows, dev_cids, allow_missing_score_for_h4=False
    )
    complete_counts = ext["complete_cluster_counts"]
    failing_slots = [s for s in core_e4.E4_SLOT_ORDER if complete_counts[s] < MIN_COMPLETE_DEV_CLUSTERS]
    if failing_slots:
        raise InsufficientCompleteDevClustersError(
            f"insufficient_complete_dev_clusters_stop_s5: complete dev cluster counts {complete_counts} "
            f"below minimum {MIN_COMPLETE_DEV_CLUSTERS} on slots {failing_slots}"
        )

    masks = ext["complete_masks"]
    joint_mask_123 = masks["E4_H1"] & masks["E4_H2"] & masks["E4_H3"]
    joint_count_123 = int(np.sum(joint_mask_123))

    d1_raw = ext["inputs"]["E4_H1"][0]
    d2_raw = ext["inputs"]["E4_H2"][0]
    d3_raw = ext["inputs"]["E4_H3"][0]
    d4_raw = ext["inputs"]["E4_H4"][0]

    mask4 = masks["E4_H4"]
    d4_ok = d4_raw[mask4]
    tau_emp = float(np.mean(d4_ok != 0))
    tau_0 = float(np.clip(tau_emp, 0.15, 0.80))

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
        "dev_cluster_ids": dev_cids,
        "complete_cluster_counts": complete_counts,
        "joint_complete_123_count": joint_count_123,
        "joint_mode": "joint_123" if joint_count_123 >= MIN_COMPLETE_DEV_CLUSTERS else "marginal_per_slot",
        "d1_dev_all": [float(x) for x in d1_raw],
        "d2_dev_all": [float(x) for x in d2_raw],
        "d3_dev_all": [float(x) for x in d3_raw],
        "d4_dev_all": [int(x) for x in d4_raw],
        "mask_h1": [bool(x) for x in masks["E4_H1"]],
        "mask_h2": [bool(x) for x in masks["E4_H2"]],
        "mask_h3": [bool(x) for x in masks["E4_H3"]],
        "mask_h4": [bool(x) for x in masks["E4_H4"]],
        "mask_joint_123": [bool(x) for x in joint_mask_123],
        "tau_emp": tau_emp,
        "tau_0": tau_0,
    }


def prepare_dgp1_residuals(
    dev_profile: dict[str, Any] | None = None,
    dev_ledger_path: Path | None = None,
    allow_synthetic: bool = False,
    *,
    dev_rows: list[dict[str, Any]] | None = None,
    dev_run_id: str | None = None,
) -> dict[str, Any]:
    """Prepare centered, scaled `[-35, +35]` empirical residual pool for `DGP1_emp`."""
    if dev_profile is None and dev_rows is not None:
        dev_profile = build_dev_profile_from_rows(list(dev_rows), dev_run_id=dev_run_id)
    elif dev_profile is None:
        if dev_ledger_path is not None:
            lpath = Path(dev_ledger_path)
        else:
            candidates = sorted((RAW_ROOT / "dev").glob("*/*/results.jsonl")) if (RAW_ROOT / "dev").is_dir() else []
            lpath = candidates[0] if len(candidates) == 1 else (RAW_ROOT / "dev" / "results.jsonl")
        ns_dir = lpath.parent if lpath.name == "results.jsonl" else lpath
        res_file = ns_dir / "results.jsonl"
        if res_file.is_file():
            if (ns_dir / "sessions.json").is_file():
                valid_rows = Ledger(ns_dir).load(repair=False)
            else:
                valid_rows = [
                    json.loads(line)
                    for line in res_file.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            dev_profile = build_dev_profile_from_rows(
                valid_rows,
                dev_run_id=dev_run_id,
                dev_ledger_sha256=sha256(res_file),
            )
            dev_profile["dev_ledger_path"] = str(res_file)
        elif not allow_synthetic:
            raise ValueError(
                f"Production S4 calibration requires a completed S4 dev ledger at {res_file} "
                "(or pass allow_synthetic=True for offline S2 unit tests)."
            )

    if dev_profile is not None:
        if not isinstance(dev_profile, dict) or "mask_h4" not in dev_profile:
            raise ValueError("dev_profile must be a dict containing mask_h1..mask_h4")
        d1_all = np.asarray(dev_profile["d1_dev_all"], dtype=np.float64)
        d2_all = np.asarray(dev_profile["d2_dev_all"], dtype=np.float64)
        d3_all = np.asarray(dev_profile["d3_dev_all"], dtype=np.float64)
        m1 = np.asarray(dev_profile["mask_h1"], dtype=bool)
        m2 = np.asarray(dev_profile["mask_h2"], dtype=bool)
        m3 = np.asarray(dev_profile["mask_h3"], dtype=bool)
        m4 = np.asarray(dev_profile["mask_h4"], dtype=bool)
        if any(arr.shape != (20,) for arr in (d1_all, d2_all, d3_all, m1, m2, m3, m4)):
            raise ValueError("dev_profile arrays and masks must have exact shape (20,)")
        recomputed_counts = {
            "E4_H1": int(np.sum(m1)),
            "E4_H2": int(np.sum(m2)),
            "E4_H3": int(np.sum(m3)),
            "E4_H4": int(np.sum(m4)),
        }
        if dev_profile.get("complete_cluster_counts") is not None and dev_profile["complete_cluster_counts"] != recomputed_counts:
            raise ValueError(
                f"dev_profile complete_cluster_counts={dev_profile['complete_cluster_counts']} "
                f"disagrees with masks {recomputed_counts}"
            )
        failing_slots = [s for s in core_e4.E4_SLOT_ORDER if recomputed_counts[s] < MIN_COMPLETE_DEV_CLUSTERS]
        if failing_slots:
            raise InsufficientCompleteDevClustersError(
                f"insufficient_complete_dev_clusters_stop_s5: complete dev cluster counts {recomputed_counts} "
                f"below minimum {MIN_COMPLETE_DEV_CLUSTERS} on slots {failing_slots}"
            )
        m_joint = m1 & m2 & m3
        if "mask_joint_123" in dev_profile and not np.array_equal(np.asarray(dev_profile["mask_joint_123"], dtype=bool), m_joint):
            raise ValueError("dev_profile mask_joint_123 disagrees with mask_h1 & mask_h2 & mask_h3")
        if "joint_complete_123_count" in dev_profile and int(dev_profile["joint_complete_123_count"]) != int(np.sum(m_joint)):
            raise ValueError("dev_profile joint_complete_123_count disagrees with mask_joint_123")
        tau_0 = float(dev_profile["tau_0"])
        if not (0.15 - 1e-12 <= tau_0 <= 0.80 + 1e-12):
            raise ValueError(f"dev_profile tau_0={tau_0} outside [0.15, 0.80]")
        source = str(dev_profile.get("source", "dev_ledger"))
        meta = {
            "dev_run_id": dev_profile.get("dev_run_id"),
            "dev_run_ids": dev_profile.get("dev_run_ids", []),
            "dev_ledger_path": dev_profile.get("dev_ledger_path"),
            "dev_ledger_sha256": dev_profile.get("dev_ledger_sha256"),
            "dev_ledger_digest": dev_profile.get("dev_ledger_digest"),
            "complete_cluster_counts": recomputed_counts,
            "joint_complete_123_count": int(np.sum(m_joint)),
        }
    else:
        rng_fb = np.random.Generator(np.random.PCG64(2026110600))
        d1_all = rng_fb.uniform(-25.0, 25.0, size=20)
        d2_all = rng_fb.uniform(-20.0, 20.0, size=20)
        d3_all = rng_fb.uniform(-25.0, 25.0, size=20)
        m1 = np.ones(20, dtype=bool)
        m2 = np.ones(20, dtype=bool)
        m3 = np.ones(20, dtype=bool)
        m_joint = np.ones(20, dtype=bool)
        tau_0 = 0.50
        source = "synthetic_fallback"
        meta = {
            "dev_run_id": None,
            "dev_run_ids": [],
            "dev_ledger_path": None,
            "dev_ledger_sha256": None,
            "dev_ledger_digest": None,
            "complete_cluster_counts": {"E4_H1": 20, "E4_H2": 20, "E4_H3": 20, "E4_H4": 20},
            "joint_complete_123_count": 20,
        }

    def _center_and_scale(vec: np.ndarray) -> tuple[np.ndarray, float]:
        r = vec - float(np.mean(vec))
        max_abs = max(1e-12, float(np.max(np.abs(r))))
        kappa = min(1.0, 35.0 / max_abs)
        return r * kappa, float(kappa)

    if int(np.sum(m_joint)) >= MIN_COMPLETE_DEV_CLUSTERS:
        eps1_pool, k1 = _center_and_scale(d1_all[m_joint])
        eps2_pool, k2 = _center_and_scale(d2_all[m_joint])
        eps3_pool, k3 = _center_and_scale(d3_all[m_joint])
        joint_mode = "joint_123"
    else:
        eps1_pool, k1 = _center_and_scale(d1_all[m1])
        eps2_pool, k2 = _center_and_scale(d2_all[m2])
        eps3_pool, k3 = _center_and_scale(d3_all[m3])
        joint_mode = "marginal_per_slot"

    return {
        "source": source,
        "joint_mode": joint_mode,
        "eps1_pool": eps1_pool,
        "eps2_pool": eps2_pool,
        "eps3_pool": eps3_pool,
        "kappa": {"E4_H1": k1, "E4_H2": k2, "E4_H3": k3},
        "tau_0": tau_0,
        **meta,
    }


def _draw_discrete_pairs(
    rng: np.random.Generator,
    n: int,
    theta4: float,
    tau_0: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw paired binary indicators `(I_exp, I_dual) in {(1,0), (0,1), (0,0)}` with `E[I_exp - I_dual] = theta4`."""
    tau = max(float(tau_0), abs(float(theta4)) + 0.10)
    tau = min(0.80, max(0.15, tau))
    pi_pos = (tau + float(theta4)) / 2.0
    pi_neg = (tau - float(theta4)) / 2.0
    u = rng.random(size=n)
    i_exp = (u < pi_pos).astype(np.int64)
    i_dual = ((u >= pi_pos) & (u < pi_pos + pi_neg)).astype(np.int64)
    return i_exp, i_dual


def generate_disjoint_units_one_rep(
    rng: np.random.Generator,
    dgp: str,
    cfg_name: str,
    dgp1_prep: dict[str, Any],
) -> dict[str, Any]:
    """Generate one simulated 80-cluster replicate across the 8 pairwise disjoint conditions (`PLAN-E4.md` §4.2(5))."""
    spec = CFG_SPECS[cfg_name]
    th1 = float(spec["theta"]["E4_H1"])
    th2 = float(spec["theta"]["E4_H2"])
    th3 = float(spec["theta"]["E4_H3"])
    th4 = float(spec["theta"]["E4_H4"])
    miss_p = float(spec["missing_prob"])

    if dgp == "DGP1_emp":
        if dgp1_prep.get("joint_mode") == "joint_123":
            pool_size = int(dgp1_prep["eps1_pool"].size)
            idx = rng.integers(0, pool_size, size=N_FORMAL)
            eps1 = dgp1_prep["eps1_pool"][idx]
            eps2 = dgp1_prep["eps2_pool"][idx]
            eps3 = dgp1_prep["eps3_pool"][idx]
        else:
            idx1 = rng.integers(0, int(dgp1_prep["eps1_pool"].size), size=N_FORMAL)
            idx2 = rng.integers(0, int(dgp1_prep["eps2_pool"].size), size=N_FORMAL)
            idx3 = rng.integers(0, int(dgp1_prep["eps3_pool"].size), size=N_FORMAL)
            eps1 = dgp1_prep["eps1_pool"][idx1]
            eps2 = dgp1_prep["eps2_pool"][idx2]
            eps3 = dgp1_prep["eps3_pool"][idx3]
        i_exp, i_dual = _draw_discrete_pairs(rng, N_FORMAL, th4, dgp1_prep["tau_0"])

    elif dgp == "DGP2_skew":
        u_mat = _correlated_beta_2_8(rng, N_FORMAL, rho=0.5)
        eps1 = 40.0 * (u_mat[:, 0] - 0.2)
        eps2 = 40.0 * (u_mat[:, 1] - 0.2)
        eps3 = 40.0 * (u_mat[:, 2] - 0.2)
        i_exp, i_dual = _draw_discrete_pairs(rng, N_FORMAL, th4, 0.50)

    elif dgp == "DGP3_ties":
        vals_3 = np.array([-30.0, 0.0, 30.0], dtype=np.float64)
        probs_3 = np.array([0.30, 0.40, 0.30], dtype=np.float64)
        eps1 = rng.choice(vals_3, size=N_FORMAL, p=probs_3)
        eps2 = rng.choice(vals_3, size=N_FORMAL, p=probs_3)
        eps3 = rng.choice(vals_3, size=N_FORMAL, p=probs_3)
        i_exp, i_dual = _draw_discrete_pairs(rng, N_FORMAL, th4, 0.15)

    elif dgp == "DGP4_het":
        # 4 domains with fixed quota: 20 per domain, offsets (+12, +4, -4, -12), weighted mean = 0
        shifts = np.array([12.0] * 20 + [4.0] * 20 + [-4.0] * 20 + [-12.0] * 20, dtype=np.float64)
        eps1 = shifts + rng.uniform(-20.0, 20.0, size=N_FORMAL)
        eps2 = shifts + rng.uniform(-20.0, 20.0, size=N_FORMAL)
        eps3 = shifts + rng.uniform(-20.0, 20.0, size=N_FORMAL)
        # Discrete E4_H4: tau_sub = 0.70, domain offsets (+0.15, +0.05, -0.05, -0.15)
        i_exp_d1, i_dual_d1 = _draw_discrete_pairs(rng, 20, th4 + 0.15, 0.70)
        i_exp_d2, i_dual_d2 = _draw_discrete_pairs(rng, 20, th4 + 0.05, 0.70)
        i_exp_d3, i_dual_d3 = _draw_discrete_pairs(rng, 20, th4 - 0.05, 0.70)
        i_exp_d4, i_dual_d4 = _draw_discrete_pairs(rng, 20, th4 - 0.15, 0.70)
        i_exp = np.concatenate([i_exp_d1, i_exp_d2, i_exp_d3, i_exp_d4])
        i_dual = np.concatenate([i_dual_d1, i_dual_d2, i_dual_d3, i_dual_d4])

    elif dgp == "DGP5_endpt":
        # 70% extreme boundary endpoint mass at {-35.0, +35.0}: probs (0.35, 0.30, 0.35), E[eps] = 0, Var = 857.5
        vals_5 = np.array([-35.0, 0.0, 35.0], dtype=np.float64)
        probs_5 = np.array([0.35, 0.30, 0.35], dtype=np.float64)
        eps1 = rng.choice(vals_5, size=N_FORMAL, p=probs_5)
        eps2 = rng.choice(vals_5, size=N_FORMAL, p=probs_5)
        eps3 = rng.choice(vals_5, size=N_FORMAL, p=probs_5)
        i_exp, i_dual = _draw_discrete_pairs(rng, N_FORMAL, th4, 0.15)

    else:
        raise ValueError(f"Unknown DGP: {dgp!r}")

    # Symmetrically centered paired readings on 6 disjoint continuous conditions (`PLAN-E4.md` §4.2(5))
    x1 = 50.0 + 0.5 * (th1 + eps1)
    y1 = 50.0 - 0.5 * (th1 + eps1)
    x2 = 50.0 + 0.5 * (th2 + eps2)
    y2 = 50.0 - 0.5 * (th2 + eps2)
    x3 = 50.0 + 0.5 * (th3 + eps3)
    y3 = 50.0 - 0.5 * (th3 + eps3)

    if miss_p > 0.0:
        m_x1 = rng.random(size=N_FORMAL) < miss_p
        m_y1 = rng.random(size=N_FORMAL) < miss_p
        m_x2 = rng.random(size=N_FORMAL) < miss_p
        m_y2 = rng.random(size=N_FORMAL) < miss_p
        m_x3 = rng.random(size=N_FORMAL) < miss_p
        m_y3 = rng.random(size=N_FORMAL) < miss_p
        m_iexp = rng.random(size=N_FORMAL) < miss_p
        m_idual = rng.random(size=N_FORMAL) < miss_p

        x1_lo, x1_hi = np.where(m_x1, 0.0, x1), np.where(m_x1, 100.0, x1)
        y1_lo, y1_hi = np.where(m_y1, 0.0, y1), np.where(m_y1, 100.0, y1)
        x2_lo, x2_hi = np.where(m_x2, 0.0, x2), np.where(m_x2, 100.0, x2)
        y2_lo, y2_hi = np.where(m_y2, 0.0, y2), np.where(m_y2, 100.0, y2)
        x3_lo, x3_hi = np.where(m_x3, 0.0, x3), np.where(m_x3, 100.0, x3)
        y3_lo, y3_hi = np.where(m_y3, 0.0, y3), np.where(m_y3, 100.0, y3)

        iexp_lo, iexp_hi = np.where(m_iexp, 0, i_exp), np.where(m_iexp, 1, i_exp)
        idual_lo, idual_hi = np.where(m_idual, 0, i_dual), np.where(m_idual, 1, i_dual)

        d1_lo, d1_hi = x1_lo - y1_hi, x1_hi - y1_lo
        d2_lo, d2_hi = x2_lo - y2_hi, x2_hi - y2_lo
        d3_lo, d3_hi = x3_lo - y3_hi, x3_hi - y3_lo
        d4_lo, d4_hi = iexp_lo - idual_hi, iexp_hi - idual_lo
    else:
        d1 = x1 - y1
        d2 = x2 - y2
        d3 = x3 - y3
        d4 = i_exp - i_dual
        d1_lo, d1_hi = d1, d1
        d2_lo, d2_hi = d2, d2
        d3_lo, d3_hi = d3, d3
        d4_lo, d4_hi = d4, d4

    return {
        "d1_lo": d1_lo,
        "d1_hi": d1_hi,
        "d2_lo": d2_lo,
        "d2_hi": d2_hi,
        "d3_lo": d3_lo,
        "d3_hi": d3_hi,
        "d4_lo": d4_lo,
        "d4_hi": d4_hi,
    }


def simulate_one_cell_worker(
    cell_idx: int,
    dgp: str,
    cfg_name: str,
    r_reps: int,
    b_draws: int,
    seed: int | np.random.SeedSequence,
    dgp1_prep: dict[str, Any],
) -> dict[str, Any]:
    """Execute all R replicates for a single `(DGP, Cfg)` cell."""
    rng = np.random.Generator(np.random.PCG64(seed))
    pct_p = np.zeros((r_reps, 4), dtype=np.float64)
    pct_ci_lo = np.zeros((r_reps, 4), dtype=np.float64)
    pct_ci_hi = np.zeros((r_reps, 4), dtype=np.float64)
    pct_degen = np.zeros((r_reps, 4), dtype=bool)

    bt_p = np.zeros((r_reps, 4), dtype=np.float64)
    bt_ci_lo = np.zeros((r_reps, 4), dtype=np.float64)
    bt_ci_hi = np.zeros((r_reps, 4), dtype=np.float64)
    bt_degen = np.zeros((r_reps, 4), dtype=bool)

    for r in range(r_reps):
        sim = generate_disjoint_units_one_rep(rng, dgp, cfg_name, dgp1_prep)
        w_all = rng.multinomial(N_FORMAL, np.full(N_FORMAL, 1.0 / N_FORMAL), size=b_draws).astype(np.float64) / float(N_FORMAL)

        for s_idx, (d_lo, d_hi) in enumerate((
            (sim["d1_lo"], sim["d1_hi"]),
            (sim["d2_lo"], sim["d2_hi"]),
            (sim["d3_lo"], sim["d3_hi"]),
        )):
            res_p = core_e4.infer_continuous_slot_e4(d_lo, d_hi, w_all, method="pct")
            pct_p[r, s_idx] = res_p["p"]
            pct_ci_lo[r, s_idx] = res_p["ci_9875"][0]
            pct_ci_hi[r, s_idx] = res_p["ci_9875"][1]
            pct_degen[r, s_idx] = res_p["degenerate"]

            res_b = core_e4.infer_continuous_slot_e4(d_lo, d_hi, w_all, method="bessel_t")
            bt_p[r, s_idx] = res_b["p"]
            bt_ci_lo[r, s_idx] = res_b["ci_9875"][0]
            bt_ci_hi[r, s_idx] = res_b["ci_9875"][1]
            bt_degen[r, s_idx] = res_b["degenerate"]

        res_h4 = core_e4.infer_discrete_slot_e4(sim["d4_lo"], sim["d4_hi"], one_sided=True)
        for p_mat, lo_mat, hi_mat, dg_mat in (
            (pct_p, pct_ci_lo, pct_ci_hi, pct_degen),
            (bt_p, bt_ci_lo, bt_ci_hi, bt_degen),
        ):
            p_mat[r, 3] = res_h4["p"]
            lo_mat[r, 3] = res_h4["ci_9875"][0]
            hi_mat[r, 3] = res_h4["ci_9875"][1]
            dg_mat[r, 3] = False

    return {
        "cell_idx": cell_idx,
        "dgp": dgp,
        "cfg": cfg_name,
        "r_reps": r_reps,
        "b_draws": b_draws,
        "pct": {"p": pct_p, "ci_lo": pct_ci_lo, "ci_hi": pct_ci_hi, "degen": pct_degen},
        "bessel_t": {"p": bt_p, "ci_lo": bt_ci_lo, "ci_hi": bt_ci_hi, "degen": bt_degen},
    }


def evaluate_cell_metrics(
    raw_cell: dict[str, Any],
    method_key: str,
    demoted_slots: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Compute FWER, simultaneous 98.75% CI coverage, individual 98.75% CI coverage, and Screen05."""
    cfg_name = raw_cell["cfg"]
    spec = CFG_SPECS[cfg_name]
    theta_vec = np.array([spec["theta"][s] for s in core_e4.E4_SLOT_ORDER], dtype=np.float64)
    null_indices = [i for i, s in enumerate(core_e4.E4_SLOT_ORDER) if s in spec["null_slots"]]
    demoted_indices = [i for i, s in enumerate(core_e4.E4_SLOT_ORDER) if s in demoted_slots]
    active_indices = [i for i in range(4) if i not in demoted_indices]

    data = raw_cell[method_key]
    p_mat = data["p"].copy()
    ci_lo = data["ci_lo"].copy()
    ci_hi = data["ci_hi"].copy()
    degen = data["degen"]
    r_reps = int(p_mat.shape[0])

    for d_idx in demoted_indices:
        p_mat[:, d_idx] = 1.0
        ci_lo[:, d_idx] = -100.0
        ci_hi[:, d_idx] = 100.0

    covers = (ci_lo <= theta_vec[None, :] + 1e-12) & (theta_vec[None, :] - 1e-12 <= ci_hi)
    ind_cov = {
        core_e4.E4_SLOT_ORDER[i]: float(np.mean(covers[:, i]))
        for i in range(4)
    }
    sim_cov = float(np.mean(np.all(covers[:, active_indices], axis=1)))

    false_rej_count = 0
    for r in range(r_reps):
        p_row = {core_e4.E4_SLOT_ORDER[i]: float(p_mat[r, i]) for i in range(4)}
        holm = core_e4.holm_step_down_e4(p_row)
        if any(holm[core_e4.E4_SLOT_ORDER[i]]["rejected"] for i in null_indices if i in active_indices):
            false_rej_count += 1
    fwer = float(false_rej_count / r_reps)

    screen05_by_null = {
        core_e4.E4_SLOT_ORDER[i]: float(np.mean(p_mat[:, i] <= 0.05))
        for i in null_indices
        if i in active_indices
    }
    max_screen05 = max(screen05_by_null.values()) if screen05_by_null else 0.0

    fwer_ok = fwer <= FWER_CAP
    sim_cov_ok = sim_cov >= SIMULTANEOUS_COV_FLOOR
    ind_cov_ok = all(ind_cov[core_e4.E4_SLOT_ORDER[i]] >= INDIVIDUAL_COV_FLOOR for i in active_indices)
    screen05_ok = max_screen05 <= SCREEN05_CAP

    return {
        "dgp": raw_cell["dgp"],
        "cfg": cfg_name,
        "method": method_key,
        "demoted_slots": list(demoted_slots),
        "fwer": fwer,
        "fwer_passed": fwer_ok,
        "simultaneous_coverage_9875": sim_cov,
        "simultaneous_coverage_9875_passed": sim_cov_ok,
        "individual_coverage_9875": ind_cov,
        "individual_coverage_9875_passed": ind_cov_ok,
        "screen05_by_null_slot": screen05_by_null,
        "max_screen05": max_screen05,
        "screen05_passed": screen05_ok,
        "degeneracy_rates": {
            core_e4.E4_SLOT_ORDER[i]: float(np.mean(degen[:, i])) for i in range(4)
        },
        "cell_passed": bool(fwer_ok and sim_cov_ok and ind_cov_ok and screen05_ok),
    }


def _validate_raw_cells_integrity(
    raw_cells: list[dict[str, Any]],
    expected_r_reps: int | None = None,
    expected_b_draws: int | None = None,
) -> tuple[int, int]:
    if not isinstance(raw_cells, list) or len(raw_cells) != EXPECTED_TOTAL_CELLS:
        raise ValueError(
            f"Expected exactly {EXPECTED_TOTAL_CELLS} calibration cells, got {len(raw_cells) if isinstance(raw_cells, list) else type(raw_cells)}"
        )
    seen_pairs: list[tuple[str, str]] = []
    r_vals: set[int] = set()
    b_vals: set[int] = set()
    for cell in raw_cells:
        pair = (cell.get("dgp"), cell.get("cfg"))
        seen_pairs.append(pair)
        r_c = int(cell.get("r_reps", 0))
        b_c = int(cell.get("b_draws", 0))
        if r_c <= 0 or b_c <= 0:
            raise ValueError(f"Non-positive r_reps={r_c} or b_draws={b_c} in cell {pair}")
        for m_key in ("pct", "bessel_t"):
            m_data = cell.get(m_key, {})
            for arr_key in ("p", "ci_lo", "ci_hi", "degen"):
                arr = m_data.get(arr_key)
                if not isinstance(arr, np.ndarray) or arr.shape != (r_c, 4):
                    raise ValueError(f"Invalid shape for {m_key}.{arr_key} in cell {pair}: expected {(r_c, 4)}")
        r_vals.add(r_c)
        b_vals.add(b_c)
    if set(seen_pairs) != set(EXPECTED_CELL_PAIRS) or len(seen_pairs) != len(set(seen_pairs)):
        raise ValueError("Calibration cells do not match the exact 20 (DGP, Cfg) pairs without duplicates")
    if len(r_vals) != 1 or len(b_vals) != 1:
        raise ValueError(f"Inconsistent r_reps={r_vals} or b_draws={b_vals} across calibration cells")
    r_reps = next(iter(r_vals))
    b_draws = next(iter(b_vals))
    if expected_r_reps is not None and r_reps != expected_r_reps:
        raise ValueError(f"r_reps={r_reps} does not match expected_r_reps={expected_r_reps}")
    if expected_b_draws is not None and b_draws != expected_b_draws:
        raise ValueError(f"b_draws={b_draws} does not match expected_b_draws={expected_b_draws}")
    return r_reps, b_draws


def _verify_cell_summary_consistency(
    cell: dict[str, Any],
    *,
    expected_method: str | None = None,
    expected_demoted: tuple[str, ...] | list[str] | None = None,
) -> None:
    cfg_name = cell.get("cfg")
    if cfg_name not in CFG_SPECS:
        raise ValueError(f"Unknown cfg in calibration cell: {cfg_name!r}")
    if cell.get("dgp") not in DGP_NAMES:
        raise ValueError(f"Unknown dgp in calibration cell: {cell.get('dgp')!r}")
    if expected_method is not None and cell.get("method") != expected_method:
        raise ValueError(
            f"Cell ({cell.get('dgp')}, {cfg_name}) method={cell.get('method')!r} != expected {expected_method!r}"
        )
    cell_demoted_list = list(cell.get("demoted_slots") or [])
    if expected_demoted is not None and cell_demoted_list != list(expected_demoted):
        raise ValueError(
            f"Cell ({cell.get('dgp')}, {cfg_name}) demoted_slots={cell_demoted_list!r} != expected {list(expected_demoted)!r}"
        )
    demoted = set(cell_demoted_list)
    if any(s not in core_e4.CONTINUOUS_SLOTS for s in demoted) or len(demoted) >= 3:
        raise ValueError(f"Cell ({cell.get('dgp')}, {cfg_name}) has illegal demoted_slots={cell_demoted_list!r}")
    active_slots = [s for s in core_e4.E4_SLOT_ORDER if s not in demoted]
    null_active = [s for s in CFG_SPECS[cfg_name]["null_slots"] if s not in demoted]

    fwer = float(cell["fwer"])
    sim_cov = float(cell["simultaneous_coverage_9875"])
    ind_cov = cell.get("individual_coverage_9875")
    scr_map = cell.get("screen05_by_null_slot")
    max_scr = float(cell["max_screen05"])

    if not (0.0 <= fwer <= 1.0 and 0.0 <= sim_cov <= 1.0):
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) fwer or simultaneous_coverage_9875 out of [0, 1]")
    if not isinstance(ind_cov, dict) or set(ind_cov.keys()) != set(core_e4.E4_SLOT_ORDER):
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) invalid individual_coverage_9875 keys")
    for s_k, s_v in ind_cov.items():
        fv = float(s_v)
        if not (0.0 <= fv <= 1.0):
            raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) slot {s_k} individual_coverage_9875={fv} out of [0, 1]")
        if s_k in demoted and abs(fv - 1.0) > 1e-12:
            raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) demoted slot {s_k} must have coverage 1.0, got {fv}")
    if not isinstance(scr_map, dict) or set(scr_map.keys()) != set(null_active):
        raise ValueError(
            f"Cell ({cell['dgp']}, {cfg_name}) screen05_by_null_slot keys != {set(null_active)}"
        )
    for s_k, s_v in scr_map.items():
        fv = float(s_v)
        if not (0.0 <= fv <= 1.0):
            raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) slot {s_k} screen05={fv} out of [0, 1]")

    exp_fwer_ok = fwer <= FWER_CAP
    exp_sim_ok = sim_cov >= SIMULTANEOUS_COV_FLOOR
    exp_ind_ok = all(float(ind_cov[s]) >= INDIVIDUAL_COV_FLOOR for s in active_slots)
    exp_max_scr = max((float(scr_map[s]) for s in null_active), default=0.0)
    if abs(max_scr - exp_max_scr) > 1e-12:
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) max_screen05={max_scr} != {exp_max_scr}")
    exp_scr_ok = max_scr <= SCREEN05_CAP
    exp_cell_ok = bool(exp_fwer_ok and exp_sim_ok and exp_ind_ok and exp_scr_ok)

    if cell.get("fwer_passed") is not exp_fwer_ok:
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) fwer_passed inconsistent with fwer={fwer}")
    if cell.get("simultaneous_coverage_9875_passed") is not exp_sim_ok:
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) simultaneous_coverage_9875_passed inconsistent")
    if cell.get("individual_coverage_9875_passed") is not exp_ind_ok:
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) individual_coverage_9875_passed inconsistent")
    if cell.get("screen05_passed") is not exp_scr_ok:
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) screen05_passed inconsistent")
    if cell.get("cell_passed") is not exp_cell_ok:
        raise ValueError(f"Cell ({cell['dgp']}, {cfg_name}) cell_passed={cell.get('cell_passed')} != {exp_cell_ok}")


def validate_calibration_artifact(
    cal: dict[str, Any],
    require_production: bool = True,
    expected_dev_run_ids: list[str] | None = None,
    expected_dev_ledger_sha256: str | None = None,
    expected_dev_ledger_digest: str | None = None,
    expected_dev_complete_cluster_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Validate a `calibration-e4.json` artifact before Stage S5 freeze or Stage S6 formal admission."""
    if not isinstance(cal, dict) or cal.get("schema_version") != "e4_calibration_v1":
        raise ValueError(f"Invalid or missing schema_version in calibration-e4.json: {cal.get('schema_version') if isinstance(cal, dict) else type(cal)}")
    if cal.get("status") != "pass":
        raise ValueError(f"calibration-e4.json status is not 'pass': {cal.get('status')}")
    if cal.get("selected_family") not in ("hybrid_pct_tango_e4", "hybrid_bessel_t_tango_e4"):
        raise ValueError(f"Invalid selected_family in calibration-e4.json: {cal.get('selected_family')}")

    for int_key in (
        "seed",
        "r_reps",
        "b_draws",
        "n_formal",
        "n_per_domain",
        "total_cells",
        "selected_step",
        "candidate_1_passed_cells",
        "candidate_2_passed_cells",
    ):
        if type(cal.get(int_key)) is not int:
            raise ValueError(f"calibration-e4.json field {int_key!r} must be a strict int, got {cal.get(int_key)!r}")

    if cal["seed"] != CALIB_SEED_E4:
        raise ValueError(f"Invalid calibration seed: {cal['seed']!r} != {CALIB_SEED_E4}")
    if (
        cal["n_formal"] != N_FORMAL
        or cal["n_per_domain"] != N_PER_DOMAIN
        or cal["total_cells"] != EXPECTED_TOTAL_CELLS
    ):
        raise ValueError(
            f"Invalid calibration quota/cell metadata: n_formal={cal.get('n_formal')}, "
            f"n_per_domain={cal.get('n_per_domain')}, total_cells={cal.get('total_cells')}"
        )

    r_reps = cal["r_reps"]
    b_draws = cal["b_draws"]
    if r_reps < 1 or b_draws < 1:
        raise ValueError(f"Invalid calibration (r_reps, b_draws)=({r_reps}, {b_draws})")

    dev_counts = cal.get("dev_complete_cluster_counts")
    if require_production or dev_counts is not None or expected_dev_complete_cluster_counts is not None:
        if not isinstance(dev_counts, dict) or set(dev_counts.keys()) != set(core_e4.E4_SLOT_ORDER):
            raise ValueError(
                f"calibration-e4.json missing or invalid dev_complete_cluster_counts: {dev_counts!r}"
            )
        for s_slot in core_e4.E4_SLOT_ORDER:
            cnt_v = dev_counts.get(s_slot)
            if type(cnt_v) is not int or cnt_v > 20 or cnt_v < 0:
                raise ValueError(f"Invalid dev_complete_cluster_counts[{s_slot!r}]={cnt_v!r}")
        failing_dev_slots = [s for s in core_e4.E4_SLOT_ORDER if dev_counts[s] < MIN_COMPLETE_DEV_CLUSTERS]
        if failing_dev_slots:
            raise InsufficientCompleteDevClustersError(
                f"insufficient_complete_dev_clusters_stop_s5: dev_complete_cluster_counts {dev_counts} "
                f"below minimum {MIN_COMPLETE_DEV_CLUSTERS} on slots {failing_dev_slots}"
            )
        if expected_dev_complete_cluster_counts is not None and dev_counts != expected_dev_complete_cluster_counts:
            raise ValueError(
                f"calibration-e4.json dev_complete_cluster_counts={dev_counts} != expected {expected_dev_complete_cluster_counts}"
            )

    if require_production:
        if r_reps != R_DEFAULT or b_draws != B_DEFAULT:
            raise ValueError(
                f"Production calibration requires exact r_reps=={R_DEFAULT}, b_draws=={B_DEFAULT}, got {r_reps}, {b_draws}"
            )
        if cal.get("dev_source") != "dev_ledger" or cal.get("production_eligible") is not True:
            raise ValueError("Production calibration must be derived from real S4 dev_ledger (not synthetic_fallback)")
        if cal.get("code_hashes") != compute_calibration_code_hashes():
            raise ValueError("Production calibration code_hashes mismatch with current core_e4/calibrate_e4/exact_tango_e4/tables")
        if not cal.get("dev_ledger_sha256"):
            raise ValueError("Production calibration missing dev_ledger_sha256")
        if not cal.get("dev_ledger_digest"):
            raise ValueError("Production calibration missing dev_ledger_digest")
        cal_run_ids = [str(x) for x in (cal.get("dev_run_ids") or []) if x]
        if not cal_run_ids or any(x.startswith("E4-DRY-") or not x.startswith("E4-") for x in cal_run_ids):
            raise ValueError(f"Production calibration has missing or non-production dev_run_ids: {cal_run_ids!r}")
        if expected_dev_run_ids is not None and sorted(set(cal_run_ids)) != sorted(set(str(x) for x in expected_dev_run_ids if x)):
            raise ValueError(
                f"calibration-e4.json dev_run_ids={cal_run_ids} != expected {sorted(expected_dev_run_ids)}"
            )
        if expected_dev_ledger_sha256 and cal.get("dev_ledger_sha256") != expected_dev_ledger_sha256:
            raise ValueError("calibration-e4.json dev_ledger_sha256 mismatch with dev/results.jsonl")
        if expected_dev_ledger_digest and cal.get("dev_ledger_digest") != expected_dev_ledger_digest:
            raise ValueError("calibration-e4.json dev_ledger_digest mismatch with dev valid records")

    c1_cells = cal.get("candidate_1_cells") or []
    c2_cells = cal.get("candidate_2_cells") or []
    if len(c1_cells) != EXPECTED_TOTAL_CELLS or len(c2_cells) != EXPECTED_TOTAL_CELLS:
        raise ValueError(f"calibration-e4.json must contain all {EXPECTED_TOTAL_CELLS} cells for candidate_1 and candidate_2")
    if {(c.get("dgp"), c.get("cfg")) for c in c1_cells} != set(EXPECTED_CELL_PAIRS):
        raise ValueError("candidate_1_cells do not cover all 20 (DGP, Cfg) pairs")
    if {(c.get("dgp"), c.get("cfg")) for c in c2_cells} != set(EXPECTED_CELL_PAIRS):
        raise ValueError("candidate_2_cells do not cover all 20 (DGP, Cfg) pairs")
    for c in c1_cells:
        _verify_cell_summary_consistency(c, expected_method="pct", expected_demoted=())
    for c in c2_cells:
        _verify_cell_summary_consistency(c, expected_method="bessel_t", expected_demoted=())

    c1_pass_cnt = sum(1 for c in c1_cells if c["cell_passed"])
    c2_pass_cnt = sum(1 for c in c2_cells if c["cell_passed"])
    if cal["candidate_1_passed_cells"] != c1_pass_cnt:
        raise ValueError(f"candidate_1_passed_cells={cal['candidate_1_passed_cells']} != {c1_pass_cnt}")
    if cal["candidate_2_passed_cells"] != c2_pass_cnt:
        raise ValueError(f"candidate_2_passed_cells={cal['candidate_2_passed_cells']} != {c2_pass_cnt}")

    step = cal["selected_step"]
    demoted = cal.get("demoted_slots")
    if not isinstance(demoted, list):
        raise ValueError(f"demoted_slots must be a list, got {type(demoted)}")
    if step == 1:
        if (
            cal["selected_family"] != "hybrid_pct_tango_e4"
            or cal.get("selected_continuous_method") != "pct"
            or demoted != []
            or cal.get("step3_demoted_cells") is not None
            or cal.get("step3_passed_cells") is not None
        ):
            raise ValueError("Step 1 selection must use hybrid_pct_tango_e4 with empty demoted_slots and no step3_demoted_cells/step3_passed_cells")
        if c1_pass_cnt != EXPECTED_TOTAL_CELLS:
            raise ValueError("Step 1 selected, but not all 20 candidate_1_cells passed")
    elif step == 2:
        if (
            cal["selected_family"] != "hybrid_bessel_t_tango_e4"
            or cal.get("selected_continuous_method") != "bessel_t"
            or demoted != []
            or cal.get("step3_demoted_cells") is not None
            or cal.get("step3_passed_cells") is not None
        ):
            raise ValueError("Step 2 selection must use hybrid_bessel_t_tango_e4 with empty demoted_slots and no step3_demoted_cells/step3_passed_cells")
        if c1_pass_cnt == EXPECTED_TOTAL_CELLS:
            raise ValueError("Step 2 selected, but candidate_1_cells already passed all 20 cells")
        if c2_pass_cnt != EXPECTED_TOTAL_CELLS:
            raise ValueError("Step 2 selected, but not all 20 candidate_2_cells passed")
    elif step == 3:
        if cal["selected_family"] != "hybrid_bessel_t_tango_e4" or cal.get("selected_continuous_method") != "bessel_t":
            raise ValueError("Step 3 selection must use hybrid_bessel_t_tango_e4 / bessel_t")
        if not (1 <= len(demoted) <= 2) or not set(demoted).issubset(set(core_e4.CONTINUOUS_SLOTS)):
            raise ValueError(f"Step 3 demoted_slots must be 1-2 continuous slots, got {demoted}")
        if c1_pass_cnt == EXPECTED_TOTAL_CELLS or c2_pass_cnt == EXPECTED_TOTAL_CELLS:
            raise ValueError("Step 3 selected, but Step 1 or Step 2 already passed all 20 cells")

        h4_failed = any(
            float(c["individual_coverage_9875"]["E4_H4"]) < INDIVIDUAL_COV_FLOOR
            or float(c["screen05_by_null_slot"].get("E4_H4", 0.0)) > SCREEN05_CAP
            for c in c2_cells
        )
        if h4_failed:
            raise ValueError("Step 3 invalid: E4_H4 failed under Candidate 2 (must stop S5)")
        failing_cont: list[str] = []
        for s in core_e4.CONTINUOUS_SLOTS:
            s_failed = any(
                float(c["individual_coverage_9875"][s]) < INDIVIDUAL_COV_FLOOR
                or float(c["screen05_by_null_slot"].get(s, 0.0)) > SCREEN05_CAP
                for c in c2_cells
            )
            if s_failed:
                failing_cont.append(s)
        if len(failing_cont) == 3:
            raise ValueError("Step 3 invalid: all 3 continuous slots failed under Candidate 2 (must stop S5)")
        if len(failing_cont) == 0:
            tie_order = {"E4_H3": 0, "E4_H2": 1, "E4_H1": 2}
            worst_slot = min(
                core_e4.CONTINUOUS_SLOTS,
                key=lambda s: (
                    min(float(c["individual_coverage_9875"][s]) for c in c2_cells),
                    tie_order[s],
                ),
            )
            expected_demoted = [worst_slot]
        else:
            expected_demoted = failing_cont
        if list(demoted) != expected_demoted:
            raise ValueError(
                f"Step 3 demoted_slots={list(demoted)} does not match deterministic rule {expected_demoted}"
            )

        s3_cells = cal.get("step3_demoted_cells") or []
        if len(s3_cells) != EXPECTED_TOTAL_CELLS or {(c.get("dgp"), c.get("cfg")) for c in s3_cells} != set(EXPECTED_CELL_PAIRS):
            raise ValueError("Step 3 requires 20 valid step3_demoted_cells")
        c2_by_pair = {(c["dgp"], c["cfg"]): c for c in c2_cells}
        active_cont = [s for s in core_e4.CONTINUOUS_SLOTS if s not in demoted]
        for c in s3_cells:
            _verify_cell_summary_consistency(c, expected_method="bessel_t", expected_demoted=expected_demoted)
            c2_orig = c2_by_pair[(c["dgp"], c["cfg"])]
            for s in active_cont + ["E4_H4"]:
                if abs(float(c["individual_coverage_9875"][s]) - float(c2_orig["individual_coverage_9875"][s])) > 1e-12:
                    raise ValueError(f"Step 3 cell ({c['dgp']}, {c['cfg']}) altered individual_coverage_9875 on active slot {s}")
                if s in c2_orig["screen05_by_null_slot"]:
                    if abs(float(c["screen05_by_null_slot"].get(s, -1.0)) - float(c2_orig["screen05_by_null_slot"][s])) > 1e-12:
                        raise ValueError(f"Step 3 cell ({c['dgp']}, {c['cfg']}) altered screen05 on active null slot {s}")
            if float(c["fwer"]) > float(c2_orig["fwer"]) + 1e-12:
                raise ValueError(f"Step 3 cell ({c['dgp']}, {c['cfg']}) FWER increased after demotion")
            if float(c["simultaneous_coverage_9875"]) + 1e-12 < float(c2_orig["simultaneous_coverage_9875"]):
                raise ValueError(f"Step 3 cell ({c['dgp']}, {c['cfg']}) simultaneous_coverage_9875 decreased after demotion")
        s3_pass_cnt = sum(1 for c in s3_cells if c["cell_passed"])
        if type(cal.get("step3_passed_cells")) is not int or cal["step3_passed_cells"] != s3_pass_cnt:
            raise ValueError(f"Step 3 requires integer step3_passed_cells == {s3_pass_cnt}, got {cal.get('step3_passed_cells')!r}")
        if s3_pass_cnt != EXPECTED_TOTAL_CELLS:
            raise ValueError(f"Step 3 selected, but not all 20 step3_demoted_cells passed ({s3_pass_cnt}/{EXPECTED_TOTAL_CELLS})")
    else:
        raise ValueError(f"Invalid selected_step={step}")

    return cal


def select_candidate_deterministic(
    raw_cells: list[dict[str, Any]],
    *,
    expected_r_reps: int | None = None,
    expected_b_draws: int | None = None,
) -> dict[str, Any]:
    """Deterministic candidate selection & single-pass demotion rule (`PLAN-E4.md` §4.2(5)).

    Step 1: If Candidate 1 (`hybrid_pct_tango_e4`) passes all 20 cells, lock `hybrid_pct_tango_e4`.
    Step 2: Else if Candidate 2 (`hybrid_bessel_t_tango_e4`) passes all 20 cells, lock `hybrid_bessel_t_tango_e4`.
    Step 3: Else if under Candidate 2 `E4_H4` passes all 20 cells and <= 2 continuous slots fail,
            perform a single-pass demotion of the failing continuous slot(s) (or worst-coverage
            continuous slot if failure is only simultaneous coverage, tie-breaking `E4_H3 -> E4_H2 -> E4_H1`)
            to descriptive while keeping `m = 4` (`alpha_ind = 0.0125`).
    Step 4: If Step 3 still fails or `E4_H4` fails or all 3 continuous slots fail, stop Stage S5
            (`calibration_failed_stop_s5`).
    """
    _validate_raw_cells_integrity(
        raw_cells, expected_r_reps=expected_r_reps, expected_b_draws=expected_b_draws
    )
    c1_evals = [evaluate_cell_metrics(c, "pct", demoted_slots=()) for c in raw_cells]
    c2_evals = [evaluate_cell_metrics(c, "bessel_t", demoted_slots=()) for c in raw_cells]

    if all(e["cell_passed"] for e in c1_evals):
        return {
            "status": "pass",
            "selected_step": 1,
            "selected_family": "hybrid_pct_tango_e4",
            "selected_continuous_method": "pct",
            "companion_family": "hybrid_bessel_t_tango_e4",
            "demoted_slots": [],
            "candidate_1_passed_cells": sum(1 for e in c1_evals if e["cell_passed"]),
            "candidate_2_passed_cells": sum(1 for e in c2_evals if e["cell_passed"]),
            "step3_passed_cells": None,
            "candidate_1_cells": c1_evals,
            "candidate_2_cells": c2_evals,
            "step3_demoted_cells": None,
        }

    if all(e["cell_passed"] for e in c2_evals):
        return {
            "status": "pass",
            "selected_step": 2,
            "selected_family": "hybrid_bessel_t_tango_e4",
            "selected_continuous_method": "bessel_t",
            "companion_family": "hybrid_pct_tango_e4",
            "demoted_slots": [],
            "candidate_1_passed_cells": sum(1 for e in c1_evals if e["cell_passed"]),
            "candidate_2_passed_cells": sum(1 for e in c2_evals if e["cell_passed"]),
            "step3_passed_cells": None,
            "candidate_1_cells": c1_evals,
            "candidate_2_cells": c2_evals,
            "step3_demoted_cells": None,
        }

    # Step 3: Single-pass demotion of 1-2 failing continuous slots under Candidate 2
    h4_failed = any(
        float(e["individual_coverage_9875"]["E4_H4"]) < INDIVIDUAL_COV_FLOOR
        or float(e["screen05_by_null_slot"].get("E4_H4", 0.0)) > SCREEN05_CAP
        for e in c2_evals
    )
    failing_cont: list[str] = []
    for s in core_e4.CONTINUOUS_SLOTS:
        s_failed = any(
            float(e["individual_coverage_9875"][s]) < INDIVIDUAL_COV_FLOOR
            or float(e["screen05_by_null_slot"].get(s, 0.0)) > SCREEN05_CAP
            for e in c2_evals
        )
        if s_failed:
            failing_cont.append(s)

    c3_evals_attempted: list[dict[str, Any]] | None = None
    c3_pass_cnt: int | None = None
    if not h4_failed and len(failing_cont) < 3:
        if len(failing_cont) == 0:
            tie_order = {"E4_H3": 0, "E4_H2": 1, "E4_H1": 2}
            worst_slot = min(
                core_e4.CONTINUOUS_SLOTS,
                key=lambda s: (
                    min(float(e["individual_coverage_9875"][s]) for e in c2_evals),
                    tie_order[s],
                ),
            )
            demoted = (worst_slot,)
        else:
            demoted = tuple(failing_cont)

        if 1 <= len(demoted) <= 2:
            c3_evals = [evaluate_cell_metrics(c, "bessel_t", demoted_slots=demoted) for c in raw_cells]
            c3_evals_attempted = c3_evals
            c3_pass_cnt = sum(1 for e in c3_evals if e["cell_passed"])
            if c3_pass_cnt == EXPECTED_TOTAL_CELLS:
                return {
                    "status": "pass",
                    "selected_step": 3,
                    "selected_family": "hybrid_bessel_t_tango_e4",
                    "selected_continuous_method": "bessel_t",
                    "companion_family": "hybrid_pct_tango_e4",
                    "demoted_slots": list(demoted),
                    "candidate_1_passed_cells": sum(1 for e in c1_evals if e["cell_passed"]),
                    "candidate_2_passed_cells": sum(1 for e in c2_evals if e["cell_passed"]),
                    "step3_passed_cells": c3_pass_cnt,
                    "candidate_1_cells": c1_evals,
                    "candidate_2_cells": c2_evals,
                    "step3_demoted_cells": c3_evals,
                }

    # Step 4: Hard Stop Rule (`calibration_failed_stop_s5`)
    return {
        "status": "calibration_failed_stop_s5",
        "selected_step": 4,
        "selected_family": None,
        "selected_continuous_method": None,
        "companion_family": None,
        "demoted_slots": [],
        "candidate_1_passed_cells": sum(1 for e in c1_evals if e["cell_passed"]),
        "candidate_2_passed_cells": sum(1 for e in c2_evals if e["cell_passed"]),
        "step3_passed_cells": c3_pass_cnt,
        "candidate_1_cells": c1_evals,
        "candidate_2_cells": c2_evals,
        "step3_demoted_cells": c3_evals_attempted,
    }


def _run_single_cell_worker(args: tuple[Any, ...]) -> dict[str, Any]:
    cell_idx, dgp, cfg_name, r_reps, b_draws, child_seed, dgp1_prep = args
    return simulate_one_cell_worker(cell_idx, dgp, cfg_name, r_reps, b_draws, child_seed, dgp1_prep)


def run_calibration_matrix_e4(
    r_reps: int = R_DEFAULT,
    b_draws: int = B_DEFAULT,
    seed: int = CALIB_SEED_E4,
    dev_profile: dict[str, Any] | None = None,
    dev_ledger_path: Path | None = None,
    dev_run_id: str | None = None,
    allow_synthetic: bool = False,
    workers: int = 1,
    *,
    dev_rows: list[dict[str, Any]] | None = None,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Execute the full 20-cell simulation matrix and build the calibration artifact."""
    if type(r_reps) is not int or type(b_draws) is not int or type(seed) is not int:
        raise ValueError("r_reps, b_draws, and seed must be strict Python ints")
    eff_workers = int(max_workers) if max_workers is not None else int(workers)
    t0 = time.time()
    dgp1_prep = prepare_dgp1_residuals(
        dev_profile=dev_profile,
        dev_ledger_path=dev_ledger_path,
        allow_synthetic=allow_synthetic,
        dev_rows=dev_rows,
        dev_run_id=dev_run_id,
    )

    ss = np.random.SeedSequence(seed)
    child_seeds = ss.spawn(EXPECTED_TOTAL_CELLS)

    tasks = [
        (i, dgp, cfg, r_reps, b_draws, child_seeds[i], dgp1_prep)
        for i, (dgp, cfg) in enumerate(EXPECTED_CELL_PAIRS)
    ]

    if eff_workers > 1:
        with ProcessPoolExecutor(max_workers=eff_workers) as executor:
            raw_cells = list(executor.map(_run_single_cell_worker, tasks))
    else:
        raw_cells = [_run_single_cell_worker(t) for t in tasks]

    raw_cells.sort(key=lambda c: c["cell_idx"])
    selection = select_candidate_deterministic(
        raw_cells, expected_r_reps=r_reps, expected_b_draws=b_draws
    )
    elapsed = round(time.time() - t0, 3)

    dev_run_ids = dgp1_prep.get("dev_run_ids") or ([dev_run_id] if dev_run_id else [])
    is_prod_run_id = bool(dev_run_ids) and all(
        str(rid).startswith("E4-") and not str(rid).startswith("E4-DRY-") for rid in dev_run_ids
    )
    now_iso = utc_now()
    cal_artifact = {
        "schema_version": "e4_calibration_v1",
        "created_at": now_iso,
        "calibrated_at": now_iso,
        "seed": int(seed),
        "r_reps": int(r_reps),
        "b_draws": int(b_draws),
        "n_formal": N_FORMAL,
        "n_per_domain": N_PER_DOMAIN,
        "domain_quotas": {"D1_safety": 20, "D2_project": 20, "D3_medical": 20, "D4_institutional": 20},
        "total_cells": EXPECTED_TOTAL_CELLS,
        "elapsed_sec": elapsed,
        "elapsed_seconds": elapsed,
        "dev_source": dgp1_prep["source"],
        "dev_joint_mode": dgp1_prep["joint_mode"],
        "dev_complete_cluster_counts": dgp1_prep.get("complete_cluster_counts"),
        "dev_joint_complete_123_count": dgp1_prep.get("joint_complete_123_count"),
        "dev_run_id": dev_run_id or dgp1_prep.get("dev_run_id") or (dev_run_ids[0] if len(dev_run_ids) == 1 else None),
        "dev_run_ids": dev_run_ids,
        "dev_ledger_path": dgp1_prep.get("dev_ledger_path"),
        "dev_ledger_sha256": dgp1_prep.get("dev_ledger_sha256"),
        "dev_ledger_digest": dgp1_prep.get("dev_ledger_digest"),
        "code_hashes": compute_calibration_code_hashes(),
        "production_eligible": bool(
            dgp1_prep["source"] == "dev_ledger"
            and dgp1_prep.get("dev_ledger_sha256")
            and dgp1_prep.get("dev_ledger_digest")
            and int(r_reps) == R_DEFAULT
            and int(b_draws) == B_DEFAULT
            and int(seed) == CALIB_SEED_E4
            and is_prod_run_id
        ),
        "dgp1_kappa": dgp1_prep["kappa"],
        "dgp1_tau_0": dgp1_prep["tau_0"],
        "hard_gates": {
            "fwer_cap": FWER_CAP,
            "simultaneous_coverage_9875_floor": SIMULTANEOUS_COV_FLOOR,
            "individual_coverage_9875_floor": INDIVIDUAL_COV_FLOOR,
            "screen05_cap": SCREEN05_CAP,
        },
        **selection,
    }

    if cal_artifact["status"] == "pass":
        validate_calibration_artifact(cal_artifact, require_production=cal_artifact["production_eligible"])
    return cal_artifact


run_full_calibration_simulation = run_calibration_matrix_e4


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 4 S4 20-cell statistical calibration.")
    parser.add_argument("--r-reps", type=int, default=R_DEFAULT, help="Replicates per cell (default: 2000)")
    parser.add_argument("--b-draws", type=int, default=B_DEFAULT, help="Bootstrap draws per replicate (default: 5000)")
    parser.add_argument("--seed", type=int, default=CALIB_SEED_E4, help="Calibration seed (default: 2026110611)")
    parser.add_argument("--workers", type=int, default=6, help="Parallel worker processes")
    parser.add_argument("--dev-ledger", default=None, help="Path to S4 dev results.jsonl")
    parser.add_argument("--dev-run-id", default=None, help="Run ID associated with S4 dev stage")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic fallback residuals for offline testing")
    parser.add_argument(
        "--out",
        default=str(RAW_ROOT / "calibration_e4.json"),
        help="Output JSON path (default data/raw/calibration_e4.json, matching run.py freeze default)",
    )
    args = parser.parse_args()

    res = run_calibration_matrix_e4(
        r_reps=args.r_reps,
        b_draws=args.b_draws,
        seed=args.seed,
        dev_ledger_path=Path(args.dev_ledger) if args.dev_ledger else None,
        dev_run_id=args.dev_run_id,
        allow_synthetic=args.allow_synthetic,
        workers=args.workers,
    )
    out_path = atomic_json(Path(args.out), res)
    print(
        f"[calibrate_e4] status={res['status']} step={res['selected_step']} "
        f"family={res['selected_family']} demoted={res['demoted_slots']} "
        f"c1_pass={res['candidate_1_passed_cells']}/20 c2_pass={res['candidate_2_passed_cells']}/20 "
        f"elapsed={res['elapsed_sec']}s -> {out_path}"
    )
    if res["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
