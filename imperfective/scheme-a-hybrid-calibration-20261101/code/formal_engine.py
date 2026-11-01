"""Unified formal statistical engine for S5 formal review and development dry-run (Step 5b / P16.4.6).

Enforces:
- `S5_FROZEN = False` hard gate (strictly forbids execution on any non-`dev` split);
- Mandatory verification on load (`verify_sealed_identity=True` by default) of all 8 sealed core modules,
  `manifests/exact-tango-tables.npz` file & payload SHA256, all 6 `Fraction`-certified left cutpoints,
  and read-only input SHA256s against `manifests/sealed-run-identity.json`;
- Full preservation and execution of legacy V4 `m=10` exact algorithm;
- Execution of Scheme A `m=4` confirmatory family across `hybrid_pct_tango` (Candidate 1),
  `hybrid_bessel_t_tango` (Candidate 2), `percentile` (historical pure-resampling baseline),
  and historical `studentized`;
- Pre-specified Scheme A observation profile in the exact shared paired-cluster bootstrap stream,
  reconciling all 1,459 point estimates and `[125, 4875]` 95% intervals while symmetrically attaching
  certified unconditional exact Tango `95%`, `98.75%`, and `99.5%` intervals to all single-stratum
  paired trinary observation contrasts (`d_i in {-1, 0, +1}^n`, including `M_U` and `M_W` paired
  endpoint contrasts, `M_W - M_U` paired differences, `L/CoT - L/Z` group contrasts, and single-group
  paired failure-rate contrasts).
"""

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from .core_a import (
        DOMAINS_A,
        NAMES_A,
        RANK_MAIN_HI,
        RANK_MAIN_LO,
        TOL_DUST,
        bootstrap_a,
        compute_bessel_t_constants_decimal,
        compute_observed_a,
        count_distinct_tol,
        extract_slot_contrasts,
        infer_hybrid_bessel_t_tango_a,
        infer_hybrid_pct_tango_a,
        infer_percentile_a,
        infer_studentized_a,
        prepare_sorted_boot_stats,
        weight_batches,
    )
    from .exact_tango import (
        DEFAULT_TABLES_NPZ,
        infer_exact_tango_slot,
        load_certified_tango_tables,
    )
    from .inputs import (
        CONDITIONS_13,
        DEFAULT_SOURCE,
        DEFAULT_SPLIT,
        L_GOLD_STANDARDS,
        load_dataset,
    )
    from .run_sim import (
        DEFAULT_SEALED_IDENTITY,
        verify_sealed_code_and_tables,
    )
except (ImportError, ValueError):
    _code_dir = Path(__file__).resolve().parent
    if str(_code_dir) not in sys.path:
        sys.path.insert(0, str(_code_dir))
    from core_a import (
        DOMAINS_A,
        NAMES_A,
        RANK_MAIN_HI,
        RANK_MAIN_LO,
        TOL_DUST,
        bootstrap_a,
        compute_bessel_t_constants_decimal,
        compute_observed_a,
        count_distinct_tol,
        extract_slot_contrasts,
        infer_hybrid_bessel_t_tango_a,
        infer_hybrid_pct_tango_a,
        infer_percentile_a,
        infer_studentized_a,
        prepare_sorted_boot_stats,
        weight_batches,
    )
    from exact_tango import (
        DEFAULT_TABLES_NPZ,
        infer_exact_tango_slot,
        load_certified_tango_tables,
    )
    from inputs import (
        CONDITIONS_13,
        DEFAULT_SOURCE,
        DEFAULT_SPLIT,
        L_GOLD_STANDARDS,
        load_dataset,
    )
    from run_sim import (
        DEFAULT_SEALED_IDENTITY,
        verify_sealed_code_and_tables,
    )

S5_FROZEN = False
DEFAULT_DRY_RUN_SEED = 2026110199


def inverse_ecdf_index(q: float, b_reps: int) -> int:
    """Unified no-interpolation inverse-ECDF 0-based rank index: ceil(q * B) - 1."""
    if b_reps <= 0:
        raise ValueError(f"b_reps must be positive, got {b_reps}")
    return min(b_reps - 1, max(0, math.ceil(q * b_reps) - 1))


RANK_95_LO = inverse_ecdf_index(0.025, 5000)  # 0-based 124 (1-based 125)
RANK_95_HI = inverse_ecdf_index(0.975, 5000)  # 0-based 4874 (1-based 4875)


def load_v4_legacy_modules():
    """Dynamically load legacy V4 stats_validation core and studentized modules.

    Strictly isolates the V4 m=10 exact legacy path from any tolerance or modified arithmetic.
    """
    repo_root = Path(__file__).resolve().parents[2]  # imperfective root
    exp1_dir = repo_root / "exp1-en"
    if str(exp1_dir) not in sys.path:
        sys.path.insert(0, str(exp1_dir))

    try:
        from stats_validation import core as v4_core
        from stats_validation import studentized as v4_studentized
        return v4_core, v4_studentized
    except ImportError as e:
        raise ImportError(f"Could not import legacy V4 modules from {exp1_dir}: {e}")


def compute_auc(d_scores: np.ndarray, c_scores: np.ndarray) -> float:
    """Compute AUC of D scores versus C scores."""
    d = np.asarray(d_scores, dtype=np.float64)
    c = np.asarray(c_scores, dtype=np.float64)
    diff = d[:, None] - c[None, :]
    k = (diff > 0.0).astype(float) + 0.5 * (diff == 0.0).astype(float)
    return float(np.mean(k))


def _weighted_auc_bounds(
    c_lo: np.ndarray,
    c_hi: np.ndarray,
    d_lo: np.ndarray,
    d_hi: np.ndarray,
    wt: np.ndarray,
    wa: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute worst-case lower and upper weighted AUC(D vs C) for batch weights wt, wa."""
    diff_lo = d_lo[:, None] - c_hi[None, :]
    k_lo = (diff_lo > 0.0).astype(np.float64) + 0.5 * (diff_lo == 0.0).astype(np.float64)
    diff_hi = d_hi[:, None] - c_lo[None, :]
    k_hi = (diff_hi > 0.0).astype(np.float64) + 0.5 * (diff_hi == 0.0).astype(np.float64)

    denom = wt.sum(axis=1) * wa.sum(axis=1)
    auc_lo = np.einsum("bi,ij,bj->b", wa, k_lo, wt) / denom
    auc_hi = np.einsum("bi,ij,bj->b", wa, k_hi, wt) / denom
    return auc_lo, auc_hi


def _summarize_exact_tango_trinary(
    d_lo: np.ndarray,
    d_hi: np.ndarray,
    tango_by_n: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute certified unconditional exact Tango 95% / 98.75% / 99.5% CIs and p-values for d in {-1, 0, +1}^n."""
    n = len(d_lo)
    if n not in tango_by_n:
        raise KeyError(f"Stratum size n={n} not present in certified exact Tango tables")
    tbl = tango_by_n[n]
    ex_two = infer_exact_tango_slot(d_lo, d_hi, one_sided=False, tables_for_n=tbl)
    ex_pos = infer_exact_tango_slot(d_lo, d_hi, one_sided=True, tables_for_n=tbl)
    return {
        "n": int(ex_two["n"]),
        "point": ex_two["point"],
        "point_lower": float(ex_two["point_lower"]),
        "point_upper": float(ex_two["point_upper"]),
        "counts_lower": dict(ex_two["counts_lower"]),
        "counts_upper": dict(ex_two["counts_upper"]),
        "observed_direction": int(ex_two["observed_direction"]),
        "p_two_sided": float(ex_two["p"]),
        "p_one_sided_pos": float(ex_pos["p"]),
        "pplus": float(ex_two["pplus"]),
        "pminus": float(ex_two["pminus"]),
        "ci_95": list(ex_two["ci_95"]),
        "ci_9875": list(ex_two["ci_9875"]),
        "ci_995": list(ex_two["ci_995"]),
        "domain": [-1.0, 1.0],
        "degenerate_95": bool(ex_two["degenerate_95"]),
        "degenerate_9875": bool(ex_two["degenerate_9875"]),
        "degenerate_995": bool(ex_two["degenerate_995"]),
    }


def _summarize_boot_interval(
    obs_lo: float,
    obs_hi: float,
    boot_lo: np.ndarray,
    boot_hi: np.ndarray,
    domain: Optional[Tuple[Optional[float], Optional[float]]],
    exact_tango: Optional[Dict[str, Any]] = None,
) -> dict:
    """Summarize point bounds and percentile 95% / 98.75% CIs with optional certified exact Tango interval."""
    b_reps = len(boot_lo)
    s_lo = np.sort(boot_lo)
    s_hi = np.sort(boot_hi)
    u_lo = int(count_distinct_tol(boot_lo, tol=TOL_DUST))
    u_hi = int(count_distinct_tol(boot_hi, tol=TOL_DUST))

    idx95_lo = inverse_ecdf_index(0.025, b_reps)
    idx95_hi = inverse_ecdf_index(0.975, b_reps)
    idx98_lo = inverse_ecdf_index(0.00625, b_reps)
    idx98_hi = inverse_ecdf_index(0.99375, b_reps)

    raw95 = [float(s_lo[idx95_lo]), float(s_hi[idx95_hi])]
    z95 = (abs(s_lo[idx95_hi] - s_lo[idx95_lo]) <= TOL_DUST) or (abs(s_hi[idx95_hi] - s_hi[idx95_lo]) <= TOL_DUST)
    deg95 = (u_lo < 20) or (u_hi < 20) or z95 or (not all(math.isfinite(x) for x in raw95)) or (raw95[0] > raw95[1])

    raw98 = [float(s_lo[idx98_lo]), float(s_hi[idx98_hi])]
    z98 = (abs(s_lo[idx98_hi] - s_lo[idx98_lo]) <= TOL_DUST) or (abs(s_hi[idx98_hi] - s_hi[idx98_lo]) <= TOL_DUST)
    deg98 = (u_lo < 20) or (u_hi < 20) or z98 or (not all(math.isfinite(x) for x in raw98)) or (raw98[0] > raw98[1])

    finite_domain = (
        domain is not None
        and domain[0] is not None
        and domain[1] is not None
    )
    dom_out = (
        [float(domain[0]) if domain[0] is not None else None, float(domain[1]) if domain[1] is not None else None]
        if domain is not None
        else [None, None]
    )

    if deg95:
        ci95 = [float(domain[0]), float(domain[1])] if finite_domain else None  # type: ignore[index,arg-type]
    else:
        ci95 = list(raw95)

    if deg98:
        ci98 = [float(domain[0]), float(domain[1])] if finite_domain else None  # type: ignore[index,arg-type]
    else:
        ci98 = list(raw98)

    out = {
        "point": float(obs_lo) if abs(obs_hi - obs_lo) <= TOL_DUST else [float(obs_lo), float(obs_hi)],
        "point_lower": float(obs_lo),
        "point_upper": float(obs_hi),
        "ci_95": ci95,
        "ci_9875": ci98,
        "raw_band_95": raw95,
        "raw_band_9875": raw98,
        "domain": dom_out,
        "degenerate_95": bool(deg95),
        "degenerate_9875": bool(deg98),
        "unique_lower": u_lo,
        "unique_upper": u_hi,
    }
    if exact_tango is not None:
        out["exact_tango"] = exact_tango
    return out


def _evaluate_cost_and_format_profile(
    unit_map: Dict[str, dict],
    telic_clusters: List[str],
    atelic_clusters: List[str],
    wt_obs: np.ndarray,
    wa_obs: np.ndarray,
    wt_norm: np.ndarray,
    wa_norm: np.ndarray,
    tango_by_n: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute complete 13-condition cost & format observation profile + 19 paired contrasts."""
    group_clusters = {
        "A": (telic_clusters, wt_obs, wt_norm),
        "C": (telic_clusters, wt_obs, wt_norm),
        "B": (atelic_clusters, wa_obs, wa_norm),
        "D": (atelic_clusters, wa_obs, wa_norm),
    }

    by_condition: Dict[str, Any] = {}
    by_cond_raw: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for task, prompt in CONDITIONS_13:
        cond = f"{task}/{prompt}"
        cond_data: Dict[str, Any] = {}
        cond_raw: Dict[str, Dict[str, Any]] = {}

        for grp in ("A", "B", "C", "D"):
            clusters, w_o, w_b = group_clusters[grp]
            rows = [unit_map[f"{grp}_{cid}/{task}/{prompt}"] for cid in clusters]

            toks = np.array([r["n_out_tokens"] for r in rows], dtype=np.float64)
            g_sec = np.array([r["generation_seconds"] for r in rows], dtype=np.float64)
            u_sec = np.array([r["seconds"] for r in rows], dtype=np.float64)
            trunc = np.array([1.0 if r["truncated"] else 0.0 for r in rows], dtype=np.float64)
            parse_fail = np.array([1.0 if r["status"] != "ok" else 0.0 for r in rows], dtype=np.float64)
            proto_fail = np.array([1.0 if not r["protocol_ok"] else 0.0 for r in rows], dtype=np.float64)

            cond_raw[grp] = {
                "rows": rows,
                "trunc_vec": trunc,
                "parse_vec": parse_fail,
                "proto_vec": proto_fail,
                "toks_pt": float((w_o @ toks)[0]),
                "toks_boot": w_b @ toks,
                "g_sec_pt": float((w_o @ g_sec)[0]),
                "g_sec_boot": w_b @ g_sec,
                "u_sec_pt": float((w_o @ u_sec)[0]),
                "u_sec_boot": w_b @ u_sec,
                "trunc_pt": float((w_o @ trunc)[0]),
                "trunc_boot": w_b @ trunc,
                "parse_pt": float((w_o @ parse_fail)[0]),
                "parse_boot": w_b @ parse_fail,
                "proto_pt": float((w_o @ proto_fail)[0]),
                "proto_boot": w_b @ proto_fail,
            }

            reasons_dict: Dict[str, int] = {"last_line": 0, "estimate_lines": 0, "weight_sum": 0}
            for r in rows:
                if not r["protocol_ok"]:
                    for rsn in r["reasons"]:
                        reasons_dict[rsn] = reasons_dict.get(rsn, 0) + 1

            cr = cond_raw[grp]
            grp_summary: Dict[str, Any] = {
                "n": len(rows),
                "n_out_tokens": {
                    "mean": _summarize_boot_interval(cr["toks_pt"], cr["toks_pt"], cr["toks_boot"], cr["toks_boot"], (0.0, 1024.0)),
                    "median": float(np.median(toks)),
                    "q25": float(np.percentile(toks, 25)),
                    "q75": float(np.percentile(toks, 75)),
                    "min": int(np.min(toks)),
                    "max": int(np.max(toks)),
                    "max_ratio_to_1024": float(np.max(toks) / 1024.0),
                },
                "generation_seconds": {
                    "mean": _summarize_boot_interval(cr["g_sec_pt"], cr["g_sec_pt"], cr["g_sec_boot"], cr["g_sec_boot"], (0.0, None)),
                    "median": float(np.median(g_sec)),
                    "q25": float(np.percentile(g_sec, 25)),
                    "q75": float(np.percentile(g_sec, 75)),
                    "min": float(np.min(g_sec)),
                    "max": float(np.max(g_sec)),
                },
                "unit_seconds": {
                    "mean": _summarize_boot_interval(cr["u_sec_pt"], cr["u_sec_pt"], cr["u_sec_boot"], cr["u_sec_boot"], (0.0, None)),
                    "median": float(np.median(u_sec)),
                    "q25": float(np.percentile(u_sec, 25)),
                    "q75": float(np.percentile(u_sec, 75)),
                    "min": float(np.min(u_sec)),
                    "max": float(np.max(u_sec)),
                },
                "truncation": {
                    "count": int(np.sum(trunc)),
                    "n": len(rows),
                    "rate": _summarize_boot_interval(cr["trunc_pt"], cr["trunc_pt"], cr["trunc_boot"], cr["trunc_boot"], (0.0, 1.0)),
                },
                "semantic_parse_fail": {
                    "count": int(np.sum(parse_fail)),
                    "n": len(rows),
                    "rate": _summarize_boot_interval(cr["parse_pt"], cr["parse_pt"], cr["parse_boot"], cr["parse_boot"], (0.0, 1.0)),
                },
                "strict_protocol_fail": {
                    "count": int(np.sum(proto_fail)),
                    "n": len(rows),
                    "rate": _summarize_boot_interval(cr["proto_pt"], cr["proto_pt"], cr["proto_boot"], cr["proto_boot"], (0.0, 1.0)),
                    "reason_counts": reasons_dict,
                },
            }

            if task == "M":
                tol_lo = np.array([
                    (1.0 if r.get("weight_sum_in_tolerance", False) else 0.0) if r["status"] == "ok" else 0.0
                    for r in rows
                ], dtype=np.float64)
                tol_hi = np.array([
                    (1.0 if r.get("weight_sum_in_tolerance", False) else 0.0) if r["status"] == "ok" else 1.0
                    for r in rows
                ], dtype=np.float64)
                tol_pt_lo = float((w_o @ tol_lo)[0])
                tol_pt_hi = float((w_o @ tol_hi)[0])
                tol_boot_lo = w_b @ tol_lo
                tol_boot_hi = w_b @ tol_hi
                in_tol = sum(1 for r in rows if r["status"] == "ok" and r.get("weight_sum_in_tolerance", False))

                cr["tol_pt_lo"] = tol_pt_lo
                cr["tol_pt_hi"] = tol_pt_hi
                cr["tol_boot_lo"] = tol_boot_lo
                cr["tol_boot_hi"] = tol_boot_hi

                grp_summary["strict_protocol_fail"]["weight_sum_in_tolerance_count"] = in_tol
                grp_summary["strict_protocol_fail"]["weight_sum_out_of_tolerance_count"] = len(rows) - in_tol
                grp_summary["strict_protocol_fail"]["weight_sum_in_tolerance_rate"] = _summarize_boot_interval(
                    tol_pt_lo, tol_pt_hi, tol_boot_lo, tol_boot_hi, (0.0, 1.0),
                )
                grp_summary["strict_protocol_fail"]["weight_sum_out_of_tolerance_rate"] = _summarize_boot_interval(
                    1.0 - tol_pt_hi, 1.0 - tol_pt_lo, 1.0 - tol_boot_hi, 1.0 - tol_boot_lo, (0.0, 1.0),
                )

            cond_data[grp] = grp_summary

        all_rows = cond_raw["A"]["rows"] + cond_raw["B"]["rows"] + cond_raw["C"]["rows"] + cond_raw["D"]["rows"]
        all_toks = np.array([r["n_out_tokens"] for r in all_rows], dtype=np.float64)
        all_g_sec = np.array([r["generation_seconds"] for r in all_rows], dtype=np.float64)
        all_u_sec = np.array([r["seconds"] for r in all_rows], dtype=np.float64)
        all_trunc = np.array([1.0 if r["truncated"] else 0.0 for r in all_rows], dtype=np.float64)
        all_parse = np.array([1.0 if r["status"] != "ok" else 0.0 for r in all_rows], dtype=np.float64)
        all_proto = np.array([1.0 if not r["protocol_ok"] else 0.0 for r in all_rows], dtype=np.float64)

        cond_raw["all"] = {}
        for m_prefix in ("toks", "g_sec", "u_sec", "trunc", "parse", "proto"):
            cond_raw["all"][f"{m_prefix}_pt"] = 0.25 * sum(cond_raw[g][f"{m_prefix}_pt"] for g in ("A", "B", "C", "D"))
            cond_raw["all"][f"{m_prefix}_boot"] = 0.25 * sum(cond_raw[g][f"{m_prefix}_boot"] for g in ("A", "B", "C", "D"))

        all_reasons: Dict[str, int] = {"last_line": 0, "estimate_lines": 0, "weight_sum": 0}
        for r in all_rows:
            if not r["protocol_ok"]:
                for rsn in r["reasons"]:
                    all_reasons[rsn] = all_reasons.get(rsn, 0) + 1

        cra = cond_raw["all"]
        cond_data["all"] = {
            "n": len(all_rows),
            "n_out_tokens": {
                "mean": _summarize_boot_interval(cra["toks_pt"], cra["toks_pt"], cra["toks_boot"], cra["toks_boot"], (0.0, 1024.0)),
                "median": float(np.median(all_toks)),
                "q25": float(np.percentile(all_toks, 25)),
                "q75": float(np.percentile(all_toks, 75)),
                "min": int(np.min(all_toks)),
                "max": int(np.max(all_toks)),
                "max_ratio_to_1024": float(np.max(all_toks) / 1024.0),
            },
            "generation_seconds": {
                "mean": _summarize_boot_interval(cra["g_sec_pt"], cra["g_sec_pt"], cra["g_sec_boot"], cra["g_sec_boot"], (0.0, None)),
                "median": float(np.median(all_g_sec)),
                "q25": float(np.percentile(all_g_sec, 25)),
                "q75": float(np.percentile(all_g_sec, 75)),
                "min": float(np.min(all_g_sec)),
                "max": float(np.max(all_g_sec)),
            },
            "unit_seconds": {
                "mean": _summarize_boot_interval(cra["u_sec_pt"], cra["u_sec_pt"], cra["u_sec_boot"], cra["u_sec_boot"], (0.0, None)),
                "median": float(np.median(all_u_sec)),
                "q25": float(np.percentile(all_u_sec, 25)),
                "q75": float(np.percentile(all_u_sec, 75)),
                "min": float(np.min(all_u_sec)),
                "max": float(np.max(all_u_sec)),
            },
            "truncation": {
                "count": int(np.sum(all_trunc)),
                "n": len(all_rows),
                "rate": _summarize_boot_interval(cra["trunc_pt"], cra["trunc_pt"], cra["trunc_boot"], cra["trunc_boot"], (0.0, 1.0)),
            },
            "semantic_parse_fail": {
                "count": int(np.sum(all_parse)),
                "n": len(all_rows),
                "rate": _summarize_boot_interval(cra["parse_pt"], cra["parse_pt"], cra["parse_boot"], cra["parse_boot"], (0.0, 1.0)),
            },
            "strict_protocol_fail": {
                "count": int(np.sum(all_proto)),
                "n": len(all_rows),
                "rate": _summarize_boot_interval(cra["proto_pt"], cra["proto_pt"], cra["proto_boot"], cra["proto_boot"], (0.0, 1.0)),
                "reason_counts": all_reasons,
            },
        }

        if task == "M":
            in_tol_all = sum(1 for r in all_rows if r["status"] == "ok" and r.get("weight_sum_in_tolerance", False))
            tol_pt_lo_all = 0.25 * sum(cond_raw[g]["tol_pt_lo"] for g in ("A", "B", "C", "D"))
            tol_pt_hi_all = 0.25 * sum(cond_raw[g]["tol_pt_hi"] for g in ("A", "B", "C", "D"))
            tol_boot_lo_all = 0.25 * sum(cond_raw[g]["tol_boot_lo"] for g in ("A", "B", "C", "D"))
            tol_boot_hi_all = 0.25 * sum(cond_raw[g]["tol_boot_hi"] for g in ("A", "B", "C", "D"))

            cond_data["all"]["strict_protocol_fail"]["weight_sum_in_tolerance_count"] = in_tol_all
            cond_data["all"]["strict_protocol_fail"]["weight_sum_out_of_tolerance_count"] = len(all_rows) - in_tol_all
            cond_data["all"]["strict_protocol_fail"]["weight_sum_in_tolerance_rate"] = _summarize_boot_interval(
                tol_pt_lo_all, tol_pt_hi_all, tol_boot_lo_all, tol_boot_hi_all, (0.0, 1.0),
            )
            cond_data["all"]["strict_protocol_fail"]["weight_sum_out_of_tolerance_rate"] = _summarize_boot_interval(
                1.0 - tol_pt_hi_all, 1.0 - tol_pt_lo_all, 1.0 - tol_boot_hi_all, 1.0 - tol_boot_lo_all, (0.0, 1.0),
            )

        by_condition[cond] = cond_data
        by_cond_raw[cond] = cond_raw

    contrasts_spec = [
        ("M_Z_minus_P_CoT", "M/Z", "P/CoT"),
        ("M_CoT_minus_P_CoT", "M/CoT", "P/CoT"),
        ("P_CoT_minus_P_Z", "P/CoT", "P/Z"),
        ("M_Z_minus_P_Z", "M/Z", "P/Z"),
        ("M_CoT_minus_P_Z", "M/CoT", "P/Z"),
        ("M_CoT_minus_M_Z", "M/CoT", "M/Z"),
        ("L_CoT_minus_L_Z", "L/CoT", "L/Z"),
        ("P_DAP_minus_P_Z", "P/DAP", "P/Z"),
        ("M_DAP_minus_P_Z", "M/DAP", "P/Z"),
        ("M_DAP_minus_P_DAP", "M/DAP", "P/DAP"),
        ("M_DAP_minus_M_Z", "M/DAP", "M/Z"),
        ("M_Z_minus_P_DAP", "M/Z", "P/DAP"),
        ("L_DAP_minus_L_Z", "L/DAP", "L/Z"),
        ("P_CF_minus_P_Z", "P/CF", "P/Z"),
        ("M_CF_minus_P_Z", "M/CF", "P/Z"),
        ("M_CF_minus_P_CF", "M/CF", "P/CF"),
        ("M_CF_minus_M_Z", "M/CF", "M/Z"),
        ("M_Z_minus_P_CF", "M/Z", "P/CF"),
        ("L_CF_minus_L_Z", "L/CF", "L/Z"),
    ]
    contrasts_res: Dict[str, Any] = {}
    for cname, c1, c2 in contrasts_spec:
        c_grp_dict: Dict[str, Any] = {}
        for target in ("all", "A", "B", "C", "D"):
            r1 = by_cond_raw[c1][target]
            r2 = by_cond_raw[c2][target]
            dtok_pt = r1["toks_pt"] - r2["toks_pt"]
            dtok_bt = r1["toks_boot"] - r2["toks_boot"]
            dg_pt = r1["g_sec_pt"] - r2["g_sec_pt"]
            dg_bt = r1["g_sec_boot"] - r2["g_sec_boot"]
            du_pt = r1["u_sec_pt"] - r2["u_sec_pt"]
            du_bt = r1["u_sec_boot"] - r2["u_sec_boot"]
            dtr_pt = r1["trunc_pt"] - r2["trunc_pt"]
            dtr_bt = r1["trunc_boot"] - r2["trunc_boot"]
            dpa_pt = r1["parse_pt"] - r2["parse_pt"]
            dpa_bt = r1["parse_boot"] - r2["parse_boot"]
            dpr_pt = r1["proto_pt"] - r2["proto_pt"]
            dpr_bt = r1["proto_boot"] - r2["proto_boot"]

            if target in ("A", "B", "C", "D"):
                d_trunc = r1["trunc_vec"] - r2["trunc_vec"]
                d_parse = r1["parse_vec"] - r2["parse_vec"]
                d_proto = r1["proto_vec"] - r2["proto_vec"]
                ex_trunc = _summarize_exact_tango_trinary(d_trunc, d_trunc, tango_by_n)
                ex_parse = _summarize_exact_tango_trinary(d_parse, d_parse, tango_by_n)
                ex_proto = _summarize_exact_tango_trinary(d_proto, d_proto, tango_by_n)
            else:
                ex_trunc = ex_parse = ex_proto = None

            c_grp_dict[target] = {
                "n_out_tokens": _summarize_boot_interval(dtok_pt, dtok_pt, dtok_bt, dtok_bt, (-1024.0, 1024.0)),
                "generation_seconds": _summarize_boot_interval(dg_pt, dg_pt, dg_bt, dg_bt, (None, None)),
                "unit_seconds": _summarize_boot_interval(du_pt, du_pt, du_bt, du_bt, (None, None)),
                "truncation_rate": _summarize_boot_interval(
                    dtr_pt, dtr_pt, dtr_bt, dtr_bt, (-1.0, 1.0), exact_tango=ex_trunc
                ),
                "semantic_parse_fail_rate": _summarize_boot_interval(
                    dpa_pt, dpa_pt, dpa_bt, dpa_bt, (-1.0, 1.0), exact_tango=ex_parse
                ),
                "strict_protocol_fail_rate": _summarize_boot_interval(
                    dpr_pt, dpr_pt, dpr_bt, dpr_bt, (-1.0, 1.0), exact_tango=ex_proto
                ),
            }
        contrasts_res[cname] = c_grp_dict

    return {
        "by_condition": by_condition,
        "contrasts": contrasts_res,
    }


def compute_observation_profile(
    dataset: dict,
    b_reps: int = 5000,
    seed: int = DEFAULT_DRY_RUN_SEED,
    tango_by_n: Optional[Dict[int, Dict[str, Any]]] = None,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> dict:
    """Compute pre-specified Scheme A observation profile with shared bootstrap + symmetric exact Tango trinary CIs."""
    if tango_by_n is None:
        tango_by_n = load_certified_tango_tables(npz_path=exact_tango_npz_path)["by_n"]

    unit_map = dataset["unit_map"]
    split_info = dataset["split_info"]
    telic_clusters = split_info["telic_clusters"]
    atelic_clusters = split_info["atelic_clusters"]
    n_ac = len(telic_clusters)
    n_bd = len(atelic_clusters)

    # Pre-generate the EXACT shared multinomial weight stream [seed, 0]
    rng_obs = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    wt_all = np.empty((b_reps, n_ac), dtype=np.float64)
    wa_all = np.empty((b_reps, n_bd), dtype=np.float64)
    for start, wt, wa in weight_batches(rng_obs, n_ac, n_bd, b=b_reps, batch=256):
        sz = len(wt)
        wt_all[start:start + sz] = wt
        wa_all[start:start + sz] = wa
    wt_norm = wt_all / float(n_ac)
    wa_norm = wa_all / float(n_bd)
    wt_obs = np.full((1, n_ac), 1.0 / n_ac, dtype=np.float64)
    wa_obs = np.full((1, n_bd), 1.0 / n_bd, dtype=np.float64)

    prompts = ["Z", "CoT", "DAP", "CF"]
    reps = ["P", "Ps", "M_U", "M_W"]

    cond_arrays: Dict[str, Dict[str, Tuple[np.ndarray, np.ndarray]]] = {}
    for r_type in reps:
        for p in prompts:
            task = "M" if r_type in ("M_U", "M_W") else ("Ps" if r_type == "Ps" else "P")
            if task == "Ps" and p != "Z":
                continue
            cond_key = f"{r_type}_{p}"
            grp_bounds: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
            for grp, clusters in (("A", telic_clusters), ("C", telic_clusters), ("B", atelic_clusters), ("D", atelic_clusters)):
                lo_arr = np.empty(len(clusters), dtype=np.float64)
                hi_arr = np.empty(len(clusters), dtype=np.float64)
                for idx, cid in enumerate(clusters):
                    row = unit_map[f"{grp}_{cid}/{task}/{p}"]
                    if row["status"] == "ok":
                        v = row["val_u"] if r_type == "M_U" else (row["val_w"] if r_type == "M_W" else row["value"])
                        lo_arr[idx] = hi_arr[idx] = float(v)
                    else:
                        lo_arr[idx], hi_arr[idx] = 0.0, 100.0
                grp_bounds[grp] = (lo_arr, hi_arr)
            cond_arrays[cond_key] = grp_bounds

    def eval_ac_linear(
        lo_vec: np.ndarray,
        hi_vec: np.ndarray,
        domain: Tuple[float, float],
        exact_tango: Optional[Dict[str, Any]] = None,
    ) -> dict:
        o_lo = float((wt_obs @ lo_vec)[0])
        o_hi = float((wt_obs @ hi_vec)[0])
        b_lo = wt_norm @ lo_vec
        b_hi = wt_norm @ hi_vec
        return _summarize_boot_interval(o_lo, o_hi, b_lo, b_hi, domain, exact_tango=exact_tango)

    def eval_bd_linear(
        lo_vec: np.ndarray,
        hi_vec: np.ndarray,
        domain: Tuple[float, float],
        exact_tango: Optional[Dict[str, Any]] = None,
    ) -> dict:
        o_lo = float((wa_obs @ lo_vec)[0])
        o_hi = float((wa_obs @ hi_vec)[0])
        b_lo = wa_norm @ lo_vec
        b_hi = wa_norm @ hi_vec
        return _summarize_boot_interval(o_lo, o_hi, b_lo, b_hi, domain, exact_tango=exact_tango)

    def eval_cross_linear(
        ac_lo: np.ndarray, ac_hi: np.ndarray, ac_w: float,
        bd_lo: np.ndarray, bd_hi: np.ndarray, bd_w: float,
        domain: Tuple[float, float],
    ) -> dict:
        o_lo = float(ac_w * (wt_obs @ ac_lo)[0] + bd_w * (wa_obs @ bd_lo)[0])
        o_hi = float(ac_w * (wt_obs @ ac_hi)[0] + bd_w * (wa_obs @ bd_hi)[0])
        b_lo = ac_w * (wt_norm @ ac_lo) + bd_w * (wa_norm @ bd_lo)
        b_hi = ac_w * (wt_norm @ ac_hi) + bd_w * (wa_norm @ bd_hi)
        return _summarize_boot_interval(o_lo, o_hi, b_lo, b_hi, domain)

    def ep_high_bounds(lo_v: np.ndarray, hi_v: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        return (lo_v >= 95.0).astype(np.float64), (hi_v >= 95.0).astype(np.float64)

    def ep_dual_bounds(lo_v: np.ndarray, hi_v: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        return ((hi_v <= 5.0) | (lo_v >= 95.0)).astype(np.float64), ((lo_v <= 5.0) | (hi_v >= 95.0)).astype(np.float64)

    # 1. Single-condition metrics with shared bootstrap intervals
    conditions_profile: Dict[str, Any] = {}
    cond_auc_boot: Dict[str, Tuple[float, float, np.ndarray, np.ndarray]] = {}
    for cond_key, gb in cond_arrays.items():
        a_lo, a_hi = gb["A"]
        b_lo, b_hi = gb["B"]
        c_lo, c_hi = gb["C"]
        d_lo, d_hi = gb["D"]

        auc_o_lo, auc_o_hi = _weighted_auc_bounds(c_lo, c_hi, d_lo, d_hi, wt_obs * n_ac, wa_obs * n_bd)
        auc_b_lo, auc_b_hi = _weighted_auc_bounds(c_lo, c_hi, d_lo, d_hi, wt_all, wa_all)
        cond_auc_boot[cond_key] = (float(auc_o_lo[0]), float(auc_o_hi[0]), auc_b_lo, auc_b_hi)

        ep_c_lo, ep_c_hi = ep_high_bounds(c_lo, c_hi)
        ep_a_lo, ep_a_hi = ep_high_bounds(a_lo, a_hi)
        ep_b_lo, ep_b_hi = ep_high_bounds(b_lo, b_hi)
        ep_d_lo, ep_d_hi = ep_high_bounds(d_lo, d_hi)

        epd_c_lo, epd_c_hi = ep_dual_bounds(c_lo, c_hi)
        epd_a_lo, epd_a_hi = ep_dual_bounds(a_lo, a_hi)
        epd_b_lo, epd_b_hi = ep_dual_bounds(b_lo, b_hi)
        epd_d_lo, epd_d_hi = ep_dual_bounds(d_lo, d_hi)

        conditions_profile[cond_key] = {
            "mean_A": eval_ac_linear(a_lo, a_hi, (0.0, 100.0)),
            "mean_B": eval_bd_linear(b_lo, b_hi, (0.0, 100.0)),
            "mean_C": eval_ac_linear(c_lo, c_hi, (0.0, 100.0)),
            "mean_D": eval_bd_linear(d_lo, d_hi, (0.0, 100.0)),
            "mean_all": eval_cross_linear(
                0.5 * (a_lo + c_lo), 0.5 * (a_hi + c_hi), 0.5,
                0.5 * (b_lo + d_lo), 0.5 * (b_hi + d_hi), 0.5,
                (0.0, 100.0),
            ),
            "c_minus_a": eval_ac_linear(c_lo - a_hi, c_hi - a_lo, (-100.0, 100.0)),
            "d_minus_b": eval_bd_linear(d_lo - b_hi, d_hi - b_lo, (-100.0, 100.0)),
            "d_minus_c": eval_cross_linear(-c_hi, -c_lo, 1.0, d_lo, d_hi, 1.0, (-100.0, 100.0)),
            "did": eval_cross_linear(c_lo - a_hi, c_hi - a_lo, 1.0, -(d_hi - b_lo), -(d_lo - b_hi), 1.0, (-200.0, 200.0)),
            "auc": _summarize_boot_interval(float(auc_o_lo[0]), float(auc_o_hi[0]), auc_b_lo, auc_b_hi, (0.0, 1.0)),
            "auc_minus_half": _summarize_boot_interval(
                float(auc_o_lo[0] - 0.5), float(auc_o_hi[0] - 0.5), auc_b_lo - 0.5, auc_b_hi - 0.5, (-0.5, 0.5),
            ),
            "ep_high_C": eval_ac_linear(ep_c_lo, ep_c_hi, (0.0, 1.0)),
            "ep_high_all": eval_cross_linear(
                0.5 * (ep_a_lo + ep_c_lo), 0.5 * (ep_a_hi + ep_c_hi), 0.5,
                0.5 * (ep_b_lo + ep_d_lo), 0.5 * (ep_b_hi + ep_d_hi), 0.5,
                (0.0, 1.0),
            ),
            "ep_dual_C": eval_ac_linear(epd_c_lo, epd_c_hi, (0.0, 1.0)),
            "ep_dual_all": eval_cross_linear(
                0.5 * (epd_a_lo + epd_c_lo), 0.5 * (epd_a_hi + epd_c_hi), 0.5,
                0.5 * (epd_b_lo + epd_d_lo), 0.5 * (epd_b_hi + epd_d_hi), 0.5,
                (0.0, 1.0),
            ),
        }

    def eval_condition_diff(lhs_key: str, rhs_key: str) -> Tuple[dict, Dict[str, Any]]:
        """Compute full paired difference profile (lhs - rhs) in shared bootstrap stream + exact Tango trinary CIs."""
        L = cond_arrays[lhs_key]
        R = cond_arrays[rhs_key]
        la_lo, la_hi = L["A"]
        lb_lo, lb_hi = L["B"]
        lc_lo, lc_hi = L["C"]
        ld_lo, ld_hi = L["D"]
        ra_lo, ra_hi = R["A"]
        rb_lo, rb_hi = R["B"]
        rc_lo, rc_hi = R["C"]
        rd_lo, rd_hi = R["D"]

        ca_diff_lo = (lc_lo - la_hi) - (rc_hi - ra_lo)
        ca_diff_hi = (lc_hi - la_lo) - (rc_lo - ra_hi)
        db_diff_lo = (ld_lo - lb_hi) - (rd_hi - rb_lo)
        db_diff_hi = (ld_hi - lb_lo) - (rd_lo - rb_hi)

        lep_c_lo, lep_c_hi = ep_high_bounds(lc_lo, lc_hi)
        rep_c_lo, rep_c_hi = ep_high_bounds(rc_lo, rc_hi)
        lep_a_lo, lep_a_hi = ep_high_bounds(la_lo, la_hi)
        rep_a_lo, rep_a_hi = ep_high_bounds(ra_lo, ra_hi)
        lep_b_lo, lep_b_hi = ep_high_bounds(lb_lo, lb_hi)
        rep_b_lo, rep_b_hi = ep_high_bounds(rb_lo, rb_hi)
        lep_d_lo, lep_d_hi = ep_high_bounds(ld_lo, ld_hi)
        rep_d_lo, rep_d_hi = ep_high_bounds(rd_lo, rd_hi)

        lep_dc_lo, lep_dc_hi = ep_dual_bounds(lc_lo, lc_hi)
        rep_dc_lo, rep_dc_hi = ep_dual_bounds(rc_lo, rc_hi)
        lep_da_lo, lep_da_hi = ep_dual_bounds(la_lo, la_hi)
        rep_da_lo, rep_da_hi = ep_dual_bounds(ra_lo, ra_hi)
        lep_db_lo, lep_db_hi = ep_dual_bounds(lb_lo, lb_hi)
        rep_db_lo, rep_db_hi = ep_dual_bounds(rb_lo, rb_hi)
        lep_dd_lo, lep_dd_hi = ep_dual_bounds(ld_lo, ld_hi)
        rep_dd_lo, rep_dd_hi = ep_dual_bounds(rd_lo, rd_hi)

        ex_ep_high_a = _summarize_exact_tango_trinary(lep_a_lo - rep_a_hi, lep_a_hi - rep_a_lo, tango_by_n)
        ex_ep_high_b = _summarize_exact_tango_trinary(lep_b_lo - rep_b_hi, lep_b_hi - rep_b_lo, tango_by_n)
        ex_ep_high_c = _summarize_exact_tango_trinary(lep_c_lo - rep_c_hi, lep_c_hi - rep_c_lo, tango_by_n)
        ex_ep_high_d = _summarize_exact_tango_trinary(lep_d_lo - rep_d_hi, lep_d_hi - rep_d_lo, tango_by_n)

        ex_ep_dual_a = _summarize_exact_tango_trinary(lep_da_lo - rep_da_hi, lep_da_hi - rep_da_lo, tango_by_n)
        ex_ep_dual_b = _summarize_exact_tango_trinary(lep_db_lo - rep_db_hi, lep_db_hi - rep_db_lo, tango_by_n)
        ex_ep_dual_c = _summarize_exact_tango_trinary(lep_dc_lo - rep_dc_hi, lep_dc_hi - rep_dc_lo, tango_by_n)
        ex_ep_dual_d = _summarize_exact_tango_trinary(lep_dd_lo - rep_dd_hi, lep_dd_hi - rep_dd_lo, tango_by_n)

        l_auc_olo, l_auc_ohi, l_auc_blo, l_auc_bhi = cond_auc_boot[lhs_key]
        r_auc_olo, r_auc_ohi, r_auc_blo, r_auc_bhi = cond_auc_boot[rhs_key]

        diff_out = {
            "mean_A": eval_ac_linear(la_lo - ra_hi, la_hi - ra_lo, (-100.0, 100.0)),
            "mean_B": eval_bd_linear(lb_lo - rb_hi, lb_hi - rb_lo, (-100.0, 100.0)),
            "mean_C": eval_ac_linear(lc_lo - rc_hi, lc_hi - rc_lo, (-100.0, 100.0)),
            "mean_D": eval_bd_linear(ld_lo - rd_hi, ld_hi - rd_lo, (-100.0, 100.0)),
            "mean_all": eval_cross_linear(
                0.5 * ((la_lo - ra_hi) + (lc_lo - rc_hi)),
                0.5 * ((la_hi - ra_lo) + (lc_hi - rc_lo)),
                0.5,
                0.5 * ((lb_lo - rb_hi) + (ld_lo - rd_hi)),
                0.5 * ((lb_hi - rb_lo) + (ld_hi - rd_lo)),
                0.5,
                (-100.0, 100.0),
            ),
            "c_minus_a": eval_ac_linear(ca_diff_lo, ca_diff_hi, (-200.0, 200.0)),
            "d_minus_b": eval_bd_linear(db_diff_lo, db_diff_hi, (-200.0, 200.0)),
            "d_minus_c": eval_cross_linear(
                -(lc_hi - rc_lo), -(lc_lo - rc_hi), 1.0,
                ld_lo - rd_hi, ld_hi - rd_lo, 1.0,
                (-200.0, 200.0),
            ),
            "did": eval_cross_linear(ca_diff_lo, ca_diff_hi, 1.0, -db_diff_hi, -db_diff_lo, 1.0, (-400.0, 400.0)),
            "auc": _summarize_boot_interval(
                l_auc_olo - r_auc_ohi, l_auc_ohi - r_auc_olo,
                l_auc_blo - r_auc_bhi, l_auc_bhi - r_auc_blo,
                (-1.0, 1.0),
            ),
            "ep_high_C": eval_ac_linear(
                lep_c_lo - rep_c_hi, lep_c_hi - rep_c_lo, (-1.0, 1.0), exact_tango=ex_ep_high_c
            ),
            "ep_high_all": eval_cross_linear(
                0.5 * ((lep_a_lo - rep_a_hi) + (lep_c_lo - rep_c_hi)),
                0.5 * ((lep_a_hi - rep_a_lo) + (lep_c_hi - rep_c_lo)),
                0.5,
                0.5 * ((lep_b_lo - rep_b_hi) + (lep_d_lo - rep_d_hi)),
                0.5 * ((lep_b_hi - rep_b_lo) + (lep_d_hi - rep_d_lo)),
                0.5,
                (-1.0, 1.0),
            ),
            "ep_dual_C": eval_ac_linear(
                lep_dc_lo - rep_dc_hi, lep_dc_hi - rep_dc_lo, (-1.0, 1.0), exact_tango=ex_ep_dual_c
            ),
            "ep_dual_all": eval_cross_linear(
                0.5 * ((lep_da_lo - rep_da_hi) + (lep_dc_lo - rep_dc_hi)),
                0.5 * ((lep_da_hi - rep_da_lo) + (lep_dc_hi - rep_dc_lo)),
                0.5,
                0.5 * ((lep_db_lo - rep_db_hi) + (lep_dd_lo - rep_dd_hi)),
                0.5 * ((lep_db_hi - rep_db_lo) + (lep_dd_hi - rep_dd_lo)),
                0.5,
                (-1.0, 1.0),
            ),
        }
        trinary_catalog = {
            "ep_high_A": ex_ep_high_a,
            "ep_high_B": ex_ep_high_b,
            "ep_high_C": ex_ep_high_c,
            "ep_high_D": ex_ep_high_d,
            "ep_dual_A": ex_ep_dual_a,
            "ep_dual_B": ex_ep_dual_b,
            "ep_dual_C": ex_ep_dual_c,
            "ep_dual_D": ex_ep_dual_d,
        }
        return diff_out, trinary_catalog

    def eval_2x2_interaction(m_prefix: str) -> dict:
        """Compute 2x2 interaction (M_CoT - M_Z) - (P_CoT - P_Z) for M_U or M_W."""
        MC = cond_arrays[f"{m_prefix}_CoT"]
        MZ = cond_arrays[f"{m_prefix}_Z"]
        PC = cond_arrays["P_CoT"]
        PZ = cond_arrays["P_Z"]

        def inter_grp(grp: str) -> Tuple[np.ndarray, np.ndarray]:
            mc_lo, mc_hi = MC[grp]
            mz_lo, mz_hi = MZ[grp]
            pc_lo, pc_hi = PC[grp]
            pz_lo, pz_hi = PZ[grp]
            return (mc_lo - mz_hi - pc_hi + pz_lo), (mc_hi - mz_lo - pc_lo + pz_hi)

        ia_lo, ia_hi = inter_grp("A")
        ib_lo, ib_hi = inter_grp("B")
        ic_lo, ic_hi = inter_grp("C")
        id_lo, id_hi = inter_grp("D")

        ica_lo, ica_hi = ic_lo - ia_hi, ic_hi - ia_lo
        idb_lo, idb_hi = id_lo - ib_hi, id_hi - ib_lo

        mc_auc = cond_auc_boot[f"{m_prefix}_CoT"]
        mz_auc = cond_auc_boot[f"{m_prefix}_Z"]
        pc_auc = cond_auc_boot["P_CoT"]
        pz_auc = cond_auc_boot["P_Z"]

        mcep_lo, mcep_hi = ep_high_bounds(*MC["C"])
        mzep_lo, mzep_hi = ep_high_bounds(*MZ["C"])
        pcep_lo, pcep_hi = ep_high_bounds(*PC["C"])
        pzep_lo, pzep_hi = ep_high_bounds(*PZ["C"])

        return {
            "mean_A": eval_ac_linear(ia_lo, ia_hi, (-200.0, 200.0)),
            "mean_B": eval_bd_linear(ib_lo, ib_hi, (-200.0, 200.0)),
            "mean_C": eval_ac_linear(ic_lo, ic_hi, (-200.0, 200.0)),
            "mean_D": eval_bd_linear(id_lo, id_hi, (-200.0, 200.0)),
            "c_minus_a": eval_ac_linear(ica_lo, ica_hi, (-400.0, 400.0)),
            "d_minus_b": eval_bd_linear(idb_lo, idb_hi, (-400.0, 400.0)),
            "did": eval_cross_linear(ica_lo, ica_hi, 1.0, -idb_hi, -idb_lo, 1.0, (-800.0, 800.0)),
            "auc": _summarize_boot_interval(
                mc_auc[0] - mz_auc[1] - pc_auc[1] + pz_auc[0],
                mc_auc[1] - mz_auc[0] - pc_auc[0] + pz_auc[1],
                mc_auc[2] - mz_auc[3] - pc_auc[3] + pz_auc[2],
                mc_auc[3] - mz_auc[2] - pc_auc[2] + pz_auc[3],
                (-2.0, 2.0),
            ),
            "ep_high_C": eval_ac_linear(
                mcep_lo - mzep_hi - pcep_hi + pzep_lo,
                mcep_hi - mzep_lo - pcep_lo + pzep_hi,
                (-2.0, 2.0),
            ),
        }

    # 2. Core Scheme A 2x2 paired comparisons (symmetric M_U & M_W)
    paired_specs = [
        ("P_CoT_minus_M_U_Z", "P_CoT", "M_U_Z"),
        ("P_CoT_minus_M_W_Z", "P_CoT", "M_W_Z"),
        ("M_U_Z_minus_P_CoT", "M_U_Z", "P_CoT"),
        ("M_W_Z_minus_P_CoT", "M_W_Z", "P_CoT"),
        ("M_U_CoT_minus_P_CoT", "M_U_CoT", "P_CoT"),
        ("M_W_CoT_minus_P_CoT", "M_W_CoT", "P_CoT"),
        ("M_U_Z_minus_P_Z", "M_U_Z", "P_Z"),
        ("M_W_Z_minus_P_Z", "M_W_Z", "P_Z"),
        ("P_CoT_minus_P_Z", "P_CoT", "P_Z"),
        ("M_U_CoT_minus_M_U_Z", "M_U_CoT", "M_U_Z"),
        ("M_W_CoT_minus_M_W_Z", "M_W_CoT", "M_W_Z"),
        ("M_U_CoT_minus_P_Z", "M_U_CoT", "P_Z"),
        ("M_W_CoT_minus_P_Z", "M_W_CoT", "P_Z"),
    ]
    paired_comparisons: Dict[str, Any] = {}
    paired_trinary_endpoints: Dict[str, Any] = {}
    for pair_name, lhs_k, rhs_k in paired_specs:
        d_out, tri_out = eval_condition_diff(lhs_k, rhs_k)
        paired_comparisons[pair_name] = d_out
        paired_trinary_endpoints[pair_name] = tri_out

    # 3. Symmetric M_W - M_U differences across prompts
    mw_minus_mu: Dict[str, Any] = {}
    mw_minus_mu_trinary: Dict[str, Any] = {}
    for p in prompts:
        d_out, tri_out = eval_condition_diff(f"M_W_{p}", f"M_U_{p}")
        mw_minus_mu[p] = d_out
        mw_minus_mu_trinary[p] = tri_out

    # 4. 2x2 interactions
    interactions_2x2 = {
        "M_U": eval_2x2_interaction("M_U"),
        "M_W": eval_2x2_interaction("M_W"),
    }

    # 5. Discrete Task L profile (single prompts + paired L_p - L_Z exact Tango & bootstrap intervals)
    task_l_arrays: Dict[str, Dict[str, Any]] = {}
    task_l_profile: Dict[str, Any] = {}
    for p in prompts:
        p_arrs: Dict[str, Any] = {}
        accs_out = {}
        label_counts = {}
        label_rates = {}

        for grp, clusters, eval_fn in (
            ("A", telic_clusters, eval_ac_linear),
            ("C", telic_clusters, eval_ac_linear),
            ("B", atelic_clusters, eval_bd_linear),
            ("D", atelic_clusters, eval_bd_linear),
        ):
            gold = L_GOLD_STANDARDS[grp]
            counts = {"True": 0, "False": 0, "Unknown": 0, "non_ok": 0}
            ind_by_lbl = {lbl: [np.empty(len(clusters)), np.empty(len(clusters))] for lbl in ("True", "False", "Unknown")}
            for idx, cid in enumerate(clusters):
                row = unit_map[f"{grp}_{cid}/L/{p}"]
                if row["status"] == "ok":
                    lbl = row["label"]
                    counts[lbl] += 1
                    for target_lbl in ("True", "False", "Unknown"):
                        v = 1.0 if lbl == target_lbl else 0.0
                        ind_by_lbl[target_lbl][0][idx] = v
                        ind_by_lbl[target_lbl][1][idx] = v
                else:
                    counts["non_ok"] += 1
                    for target_lbl in ("True", "False", "Unknown"):
                        ind_by_lbl[target_lbl][0][idx] = 0.0
                        ind_by_lbl[target_lbl][1][idx] = 1.0

            p_arrs[grp] = ind_by_lbl
            accs_out[f"ACC_{grp}"] = eval_fn(ind_by_lbl[gold][0], ind_by_lbl[gold][1], (0.0, 1.0))
            label_counts[grp] = counts
            label_rates[grp] = {
                target_lbl: eval_fn(ind_by_lbl[target_lbl][0], ind_by_lbl[target_lbl][1], (0.0, 1.0))
                for target_lbl in ("True", "False", "Unknown")
            }

        acc_a_lo, acc_a_hi = p_arrs["A"][L_GOLD_STANDARDS["A"]]
        acc_b_lo, acc_b_hi = p_arrs["B"][L_GOLD_STANDARDS["B"]]
        acc_c_lo, acc_c_hi = p_arrs["C"][L_GOLD_STANDARDS["C"]]
        acc_d_lo, acc_d_hi = p_arrs["D"][L_GOLD_STANDARDS["D"]]
        tbr_c_lo, tbr_c_hi = p_arrs["C"]["True"]

        accs_out["ACC_overall"] = eval_cross_linear(
            0.5 * (acc_a_lo + acc_c_lo),
            0.5 * (acc_a_hi + acc_c_hi),
            0.5,
            0.5 * (acc_b_lo + acc_d_lo),
            0.5 * (acc_b_hi + acc_d_hi),
            0.5,
            (0.0, 1.0),
        )

        delta_aa_out = eval_cross_linear(
            -tbr_c_hi,
            -tbr_c_lo,
            1.0,
            acc_d_lo,
            acc_d_hi,
            1.0,
            (-1.0, 1.0),
        )

        task_l_arrays[p] = p_arrs
        task_l_profile[p] = {
            "accuracies": accs_out,
            "tbr_c": label_rates["C"]["True"],
            "tbr_a": label_rates["A"]["True"],
            "delta_aa": delta_aa_out,
            "label_counts": label_counts,
            "label_rates": label_rates,
        }

    def eval_task_l_diff(lhs_p: str, rhs_p: str) -> Tuple[dict, Dict[str, Any]]:
        l_arr = task_l_arrays[lhs_p]
        r_arr = task_l_arrays[rhs_p]
        da_lo = l_arr["A"][L_GOLD_STANDARDS["A"]][0] - r_arr["A"][L_GOLD_STANDARDS["A"]][1]
        da_hi = l_arr["A"][L_GOLD_STANDARDS["A"]][1] - r_arr["A"][L_GOLD_STANDARDS["A"]][0]
        db_lo = l_arr["B"][L_GOLD_STANDARDS["B"]][0] - r_arr["B"][L_GOLD_STANDARDS["B"]][1]
        db_hi = l_arr["B"][L_GOLD_STANDARDS["B"]][1] - r_arr["B"][L_GOLD_STANDARDS["B"]][0]
        dc_lo = l_arr["C"][L_GOLD_STANDARDS["C"]][0] - r_arr["C"][L_GOLD_STANDARDS["C"]][1]
        dc_hi = l_arr["C"][L_GOLD_STANDARDS["C"]][1] - r_arr["C"][L_GOLD_STANDARDS["C"]][0]
        dd_lo = l_arr["D"][L_GOLD_STANDARDS["D"]][0] - r_arr["D"][L_GOLD_STANDARDS["D"]][1]
        dd_hi = l_arr["D"][L_GOLD_STANDARDS["D"]][1] - r_arr["D"][L_GOLD_STANDARDS["D"]][0]
        dtbr_c_lo = l_arr["C"]["True"][0] - r_arr["C"]["True"][1]
        dtbr_c_hi = l_arr["C"]["True"][1] - r_arr["C"]["True"][0]
        dtbr_a_lo = l_arr["A"]["True"][0] - r_arr["A"]["True"][1]
        dtbr_a_hi = l_arr["A"]["True"][1] - r_arr["A"]["True"][0]

        ex_acc_a = _summarize_exact_tango_trinary(da_lo, da_hi, tango_by_n)
        ex_acc_b = _summarize_exact_tango_trinary(db_lo, db_hi, tango_by_n)
        ex_acc_c = _summarize_exact_tango_trinary(dc_lo, dc_hi, tango_by_n)
        ex_acc_d = _summarize_exact_tango_trinary(dd_lo, dd_hi, tango_by_n)
        ex_tbr_c = _summarize_exact_tango_trinary(dtbr_c_lo, dtbr_c_hi, tango_by_n)
        ex_tbr_a = _summarize_exact_tango_trinary(dtbr_a_lo, dtbr_a_hi, tango_by_n)

        out = {
            "ACC_A": eval_ac_linear(da_lo, da_hi, (-1.0, 1.0), exact_tango=ex_acc_a),
            "ACC_B": eval_bd_linear(db_lo, db_hi, (-1.0, 1.0), exact_tango=ex_acc_b),
            "ACC_C": eval_ac_linear(dc_lo, dc_hi, (-1.0, 1.0), exact_tango=ex_acc_c),
            "ACC_D": eval_bd_linear(dd_lo, dd_hi, (-1.0, 1.0), exact_tango=ex_acc_d),
            "ACC_overall": eval_cross_linear(
                0.5 * (da_lo + dc_lo),
                0.5 * (da_hi + dc_hi),
                0.5,
                0.5 * (db_lo + dd_lo),
                0.5 * (db_hi + dd_hi),
                0.5,
                (-1.0, 1.0),
            ),
            "TBR_C": eval_ac_linear(dtbr_c_lo, dtbr_c_hi, (-1.0, 1.0), exact_tango=ex_tbr_c),
            "TBR_A": eval_ac_linear(dtbr_a_lo, dtbr_a_hi, (-1.0, 1.0), exact_tango=ex_tbr_a),
            "Delta_AA": eval_cross_linear(-dtbr_c_hi, -dtbr_c_lo, 1.0, dd_lo, dd_hi, 1.0, (-2.0, 2.0)),
        }
        tri_dict = {
            "ACC_A": ex_acc_a,
            "ACC_B": ex_acc_b,
            "ACC_C": ex_acc_c,
            "ACC_D": ex_acc_d,
            "TBR_C": ex_tbr_c,
            "TBR_A": ex_tbr_a,
        }
        return out, tri_dict

    task_l_cot_minus_z, tri_l_cot_z = eval_task_l_diff("CoT", "Z")
    task_l_dap_minus_z, tri_l_dap_z = eval_task_l_diff("DAP", "Z")
    task_l_cf_minus_z, tri_l_cf_z = eval_task_l_diff("CF", "Z")

    # 6. Complete shared-bootstrap cost, runtime, truncation, and strict protocol format profile
    cost_and_format = _evaluate_cost_and_format_profile(
        unit_map=unit_map,
        telic_clusters=telic_clusters,
        atelic_clusters=atelic_clusters,
        wt_obs=wt_obs,
        wa_obs=wa_obs,
        wt_norm=wt_norm,
        wa_norm=wa_norm,
        tango_by_n=tango_by_n,
    )

    return {
        "conditions": conditions_profile,
        "paired_comparisons": paired_comparisons,
        "mw_minus_mu_paired_diff": mw_minus_mu,
        "interactions_2x2": interactions_2x2,
        "diff_interruption_contrast_cot": paired_comparisons["M_U_CoT_minus_P_CoT"]["c_minus_a"],
        "task_l": task_l_profile,
        "task_l_cot_minus_z": task_l_cot_minus_z,
        "task_l_paired_contrasts": {
            "CoT_minus_Z": task_l_cot_minus_z,
            "DAP_minus_Z": task_l_dap_minus_z,
            "CF_minus_Z": task_l_cf_minus_z,
        },
        "paired_trinary_exact_tango": {
            "paired_comparisons_endpoints": paired_trinary_endpoints,
            "mw_minus_mu_endpoints": mw_minus_mu_trinary,
            "task_l_paired_contrasts": {
                "CoT_minus_Z": tri_l_cot_z,
                "DAP_minus_Z": tri_l_dap_z,
                "CF_minus_Z": tri_l_cf_z,
            },
        },
        "cost_and_format": cost_and_format,
    }


def run_formal_engine(
    source_path: str | Path = DEFAULT_SOURCE,
    split_path: str | Path = DEFAULT_SPLIT,
    split_name: str = "dev",
    b_reps: int = 5000,
    seed: int = DEFAULT_DRY_RUN_SEED,
    sealed_identity_path: str | Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: str | Path = DEFAULT_TABLES_NPZ,
    verify_sealed_identity: bool = True,
    code_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute formal statistical engine with `S5_FROZEN` gate and mandatory sealed identity/table verification."""
    if split_name != "dev" and not S5_FROZEN:
        raise PermissionError(
            f"Execution on split '{split_name}' forbidden: S5 is not frozen (S5_FROZEN == False). "
            "Formal split execution is strictly prohibited until S5 freeze gate is signed."
        )

    src_p = Path(source_path)
    spl_p = Path(split_path)
    npz_p = Path(exact_tango_npz_path)

    if verify_sealed_identity:
        sealed_gates = verify_sealed_code_and_tables(
            sealed_identity_path=Path(sealed_identity_path),
            exact_tango_npz_path=npz_p,
            source_path=src_p,
            split_path=spl_p,
            code_dir=code_dir,
        )
        tango_bundle = load_certified_tango_tables(
            npz_path=npz_p,
            expected_file_sha256=sealed_gates["exact_tango_tables_sha256"],
            expected_payload_sha256=sealed_gates["exact_tango_tables_payload_sha256"],
        )
    else:
        sealed_gates = None
        tango_bundle = load_certified_tango_tables(npz_path=npz_p)

    tango_by_n = tango_bundle["by_n"]

    print(
        f"Running formal engine on split '{split_name}' "
        f"(S5_FROZEN={S5_FROZEN}, seed={seed}, verify_sealed_identity={verify_sealed_identity})...",
        flush=True,
    )
    dataset = load_dataset(src_p, spl_p, allow_non_ok=False)

    # 1. Scheme A m=4 inference across Candidate 1, Candidate 2, Percentile, and historical Studentized
    sample_a = dataset["sample_a"]
    contrasts = extract_slot_contrasts(sample_a)
    n_ac = len(contrasts["d1_lower"])
    n_bd = len(contrasts["d4_lower"])

    rng_boot = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    (obs_lo, obs_hi), (obs_se_lo, obs_se_hi) = compute_observed_a(contrasts)
    (boot_lo, boot_hi), (boot_se_lo, boot_se_hi) = bootstrap_a(contrasts, rng_boot, b=b_reps)
    pre_boot = prepare_sorted_boot_stats(boot_lo, boot_hi, tol=TOL_DUST)

    m4_hybrid_pct_tango = infer_hybrid_pct_tango_a(
        contrasts,
        boot_lo,
        boot_hi,
        obs_lo,
        obs_hi,
        tango_tables=tango_by_n,
        precomputed_boot=pre_boot,
    )
    m4_hybrid_bessel_t_tango = infer_hybrid_bessel_t_tango_a(
        contrasts,
        boot_lo,
        boot_hi,
        obs_lo,
        obs_hi,
        tango_tables=tango_by_n,
        precomputed_boot=pre_boot,
    )
    m4_percentile = infer_percentile_a(
        boot_lo,
        boot_hi,
        obs_lo,
        obs_hi,
        precomputed_boot=pre_boot,
    )
    m4_studentized = infer_studentized_a(
        boot_lo,
        boot_hi,
        boot_se_lo,
        boot_se_hi,
        obs_lo,
        obs_hi,
        obs_se_lo,
        obs_se_hi,
        precomputed_boot=pre_boot,
    )

    ex_sa1_detail = infer_exact_tango_slot(
        contrasts["d1_lower"],
        contrasts["d1_upper"],
        one_sided=True,
        tables_for_n=tango_by_n[n_ac],
    )
    ex_sa4_detail = infer_exact_tango_slot(
        contrasts["d4_lower"],
        contrasts["d4_upper"],
        one_sided=False,
        tables_for_n=tango_by_n[n_bd],
    )

    # 2. Legacy V4 m=10 inference (pure exact V4 algorithm)
    v4_core, v4_studentized = load_v4_legacy_modules()
    rng_v4 = np.random.default_rng(np.random.SeedSequence([seed, 0]))

    v4_lo = dataset["v4_lower"]
    v4_hi = dataset["v4_upper"]
    kernel_v4 = v4_core.JointKernel(v4_lo, v4_hi)

    wt_obs_v4 = np.ones((1, len(v4_lo)), dtype=float)
    wa_obs_v4 = np.ones((1, len(v4_hi)), dtype=float) if hasattr(v4_core, "NAMES") else np.ones((1, 20), dtype=float)
    # In legacy V4, v4_lo and v4_hi are dicts/arrays handled by JointKernel with n_ac, n_bd cluster counts
    wt_obs_v4 = np.ones((1, n_ac), dtype=float)
    wa_obs_v4 = np.ones((1, n_bd), dtype=float)
    (v4_obs_lo, v4_obs_hi), (v4_obs_se_lo, v4_obs_se_hi) = v4_studentized.statistics_and_se(
        kernel_v4, wt_obs_v4, wa_obs_v4
    )
    (v4_boot_m_lo, v4_boot_m_hi), (v4_boot_se_lo, v4_boot_se_hi) = v4_studentized.bootstrap(
        v4_lo, v4_hi, rng_v4, b=b_reps
    )

    v4_stud_inf = v4_studentized.infer(
        v4_boot_m_lo, v4_boot_m_hi, v4_boot_se_lo, v4_boot_se_hi,
        v4_obs_lo[0], v4_obs_hi[0], v4_obs_se_lo[0], v4_obs_se_hi[0],
    )
    v4_pct_inf = v4_core.infer(v4_boot_m_lo, v4_boot_m_hi, v4_obs_lo[0], v4_obs_hi[0])

    # 3. Observation profile (computed in exact shared bootstrap stream [seed, 0] + certified exact Tango trinary CIs)
    obs_profile = compute_observation_profile(
        dataset,
        b_reps=b_reps,
        seed=seed,
        tango_by_n=tango_by_n,
        exact_tango_npz_path=npz_p,
    )

    def serialize_inf(inf: dict) -> dict:
        out = {}
        for k, v in inf.items():
            if isinstance(v, np.ndarray):
                out[k] = v.tolist()
            else:
                out[k] = v
        return out

    return {
        "split_name": split_name,
        "s5_frozen": S5_FROZEN,
        "bootstrap_replicates": b_reps,
        "seed": seed,
        "sealed_identity_verified": bool(verify_sealed_identity),
        "sealed_integrity_gates": sealed_gates,
        "observation_rank_policy": {
            "formula_0based": "ceil(q * B) - 1",
            "rank_95_0based_at_B5000": [RANK_95_LO, RANK_95_HI],
            "rank_95_1based_at_B5000": [RANK_95_LO + 1, RANK_95_HI + 1],
            "rank_9875_0based_at_B5000": [RANK_MAIN_LO, RANK_MAIN_HI],
            "rank_9875_1based_at_B5000": [RANK_MAIN_LO + 1, RANK_MAIN_HI + 1],
        },
        "provenance": dataset["provenance"],
        "scheme_a_m4": {
            "names": list(NAMES_A),
            "n_ac": n_ac,
            "n_bd": n_bd,
            "hybrid_pct_tango": serialize_inf(m4_hybrid_pct_tango),
            "hybrid_bessel_t_tango": serialize_inf(m4_hybrid_bessel_t_tango),
            "percentile": serialize_inf(m4_percentile),
            "studentized": serialize_inf(m4_studentized),
            "bessel_t_expansion_constants": {
                "active_ac": compute_bessel_t_constants_decimal(n_ac),
                "active_bd": compute_bessel_t_constants_decimal(n_bd),
                "formal_n80_reference": compute_bessel_t_constants_decimal(80),
            },
            "exact_tango_discrete_slots": {
                "SA1": ex_sa1_detail,
                "SA4": ex_sa4_detail,
            },
            "observed_point_lower": obs_lo.tolist(),
            "observed_point_upper": obs_hi.tolist(),
            "observed_se_lower": obs_se_lo.tolist(),
            "observed_se_upper": obs_se_hi.tolist(),
        },
        "legacy_v4_m10": {
            "names": list(v4_core.NAMES),
            "studentized": serialize_inf(v4_stud_inf),
            "percentile": serialize_inf(v4_pct_inf),
            "observed_point_lower": v4_obs_lo[0].tolist(),
            "observed_point_upper": v4_obs_hi[0].tolist(),
            "observed_se_lower": v4_obs_se_lo[0].tolist(),
            "observed_se_upper": v4_obs_se_hi[0].tolist(),
        },
        "observation_profile": obs_profile,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run Scheme A Step 5b unified formal engine (dev dry-run only while S5_FROZEN=False)."
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--split-name", default="dev")
    parser.add_argument("--b-reps", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=DEFAULT_DRY_RUN_SEED)
    parser.add_argument("--sealed-identity", default=str(DEFAULT_SEALED_IDENTITY))
    parser.add_argument("--exact-tango-tables", default=str(DEFAULT_TABLES_NPZ))
    parser.add_argument(
        "--out",
        default="E:/Claude/research/connecting-dots/imperfective/scheme-a-hybrid-calibration-20261101/results/dev-dry-run.json",
    )
    args = parser.parse_args()

    res = run_formal_engine(
        source_path=args.source,
        split_path=args.split,
        split_name=args.split_name,
        b_reps=args.b_reps,
        seed=args.seed,
        sealed_identity_path=args.sealed_identity,
        exact_tango_npz_path=args.exact_tango_tables,
        verify_sealed_identity=True,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"Wrote formal engine output to {out_path}", flush=True)


if __name__ == "__main__":
    main()
