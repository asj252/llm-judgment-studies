"""Simulation summarizer, screening evaluator, and pre-registered candidate selector for Scheme A Step 5b (P16.4.6).

Computes and enforces:
- Unconditional hard-disable of confirmation bank (`CONFIRMATION_BANK_HARD_DISABLED = True`);
- Sealed run identity verification against `manifests/sealed-run-identity.json` and `manifests/exact-tango-tables.npz`;
- Strict entity verification on every chunk and cell (exact `rep_indices 0..R-1`, array shapes/dtypes,
  finite legal ranges inside `DOMAINS_A` for active 3 methods, shape/dtype-bound `payload_sha256`,
  and full 22-key run/cell/method/bank/table identity);
- Monte Carlo rates and MCSEs across `R=2000` replicates;
- Main `98.75%` screening criteria checks (`screen05`, `screen0125`, `coverage_9875`, `FWER`,
  `family_direction`, `simultaneous_coverage_9875`) and historical `99.5%` checks;
- Non-degenerate conditional coverage (`covered_count`, `nondegenerate_count`, `rate`, conditional MCSE)
  and 5 breakdown degeneracy rates + `tol_diff` diagnostics;
- Preserved historical 8-cell Block 3 reference evaluation (`historical_block3_power_reference_8` /
  `main_power_reference_evaluations`) and 56-cell 7-sequence power curves;
- Fail-closed pre-registered Step 5b eligibility gates `E_j = C_j and D_j and P_j` (`C_j`: 88/88 calibration;
  `D_j`: 5 pinned boundary diagnostic cells `#65, #66, #67, #68, #83`; `P_j`: 17 power adequacy items across
  empirical paired support, pinned discrete high-effect endpoints, and historical Block 3 discrete cells,
  all strictly bound by `(bank, cell_name, cell_index, fingerprint)` raising `KeyError`/`ValueError` on any
  missing or mismatched entry) and deterministic 4-branch `(E_1, E_2)` method selection.
"""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import numpy as np

try:
    from .core_a import DOMAINS_A, NAMES_A
    from .dgp_a import from_table
    from .exact_tango import DEFAULT_TABLES_NPZ
    from .inputs import DEFAULT_SOURCE, DEFAULT_SPLIT
    from .manifest_a import (
        HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS,
        MAIN_POWER_REFERENCE_CELLS,
        PINNED_BOUNDARY_DIAGNOSTIC_CELLS,
        PINNED_BOUNDARY_DIAGNOSTIC_SPECS,
        STEP5B_POWER_GATE_SPECS,
    )
    from .run_sim import (
        ALL3_METHODS,
        DEFAULT_SEALED_IDENTITY,
        IDENTITY_BINDING_KEYS,
        SEEDS,
        SINGLE_METHODS,
        _assert_not_confirmation_bank,
        build_expected_chunk_identity,
        compute_chunk_payload_sha,
        validate_chunk_payload_and_meta,
        validate_payload_arrays,
        verify_integrity_gates,
    )
except (ImportError, ValueError):
    _code_dir = Path(__file__).resolve().parent
    if str(_code_dir) not in sys.path:
        sys.path.insert(0, str(_code_dir))
    from core_a import DOMAINS_A, NAMES_A
    from dgp_a import from_table
    from exact_tango import DEFAULT_TABLES_NPZ
    from inputs import DEFAULT_SOURCE, DEFAULT_SPLIT
    from manifest_a import (
        HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS,
        MAIN_POWER_REFERENCE_CELLS,
        PINNED_BOUNDARY_DIAGNOSTIC_CELLS,
        PINNED_BOUNDARY_DIAGNOSTIC_SPECS,
        STEP5B_POWER_GATE_SPECS,
    )
    from run_sim import (
        ALL3_METHODS,
        DEFAULT_SEALED_IDENTITY,
        IDENTITY_BINDING_KEYS,
        SEEDS,
        SINGLE_METHODS,
        _assert_not_confirmation_bank,
        build_expected_chunk_identity,
        compute_chunk_payload_sha,
        validate_chunk_payload_and_meta,
        validate_payload_arrays,
        verify_integrity_gates,
    )

CONFIRMATION_BANK_HARD_DISABLED = True
SUPPORTED_METHODS = SINGLE_METHODS  # ("hybrid_pct_tango", "hybrid_bessel_t_tango", "percentile", "studentized")

LOCKED_PRODUCTION_REPLICATES = 2000
LOCKED_PRODUCTION_BOOTSTRAP_REPLICATES = 5000
LOCKED_PRODUCTION_N_AC = 80
LOCKED_PRODUCTION_N_BD = 80

DEFAULT_VALIDATION_MANIFEST = DEFAULT_SEALED_IDENTITY.parent / "manifest-88.json"
DEFAULT_VALIDATION_POPULATIONS = DEFAULT_SEALED_IDENTITY.parent / "joint-populations-88.json"
DEFAULT_POWER_GRID_MANIFEST = DEFAULT_SEALED_IDENTITY.parent / "manifest-power56.json"
DEFAULT_POWER_GRID_POPULATIONS = DEFAULT_SEALED_IDENTITY.parent / "joint-populations-power56.json"

POWER_SINGLE_SLOT_SEQUENCES = (
    ("SA1-baseline", "SA1"),
    ("SA1-pinned", "SA1"),
    ("SA2-continuous", "SA2"),
    ("SA3-continuous", "SA3"),
    ("SA4-baseline", "SA4"),
    ("SA4-pinned", "SA4"),
)


def compute_mcse(rate: float, n_denom: int) -> float:
    """Compute Monte Carlo Standard Error for a binomial rate with denominator n_denom."""
    if n_denom <= 0:
        return 0.0
    return math.sqrt(max(0.0, rate * (1.0 - rate) / n_denom))


def classify_power_80(power: float, mcse: float) -> str:
    """Classify power against 0.80 using 2*MCSE confidence band."""
    if not (math.isfinite(power) and math.isfinite(mcse)):
        raise ValueError(f"Non-finite power/mcse in classify_power_80: ({power!r}, {mcse!r})")
    if power < 0.0 or power > 1.0 or mcse < 0.0:
        raise ValueError(f"Out-of-range power/mcse in classify_power_80: ({power!r}, {mcse!r})")
    if power - 2.0 * mcse >= 0.80:
        return "sufficient"
    if power + 2.0 * mcse < 0.80:
        return "insufficient"
    return "uncertain"


def _require_strict_int(val: Any, label: str) -> int:
    """Require a strict Python/NumPy integer (rejecting booleans and floats)."""
    if isinstance(val, bool) or not isinstance(val, (int, np.integer)):
        raise ValueError(f"{label} must be a strict integer, got {val!r}")
    return int(val)


def _require_finite_float(val: Any, label: str) -> float:
    """Require a finite real number (rejecting booleans, NaN, and Inf)."""
    if isinstance(val, bool) or not isinstance(val, (int, float, np.integer, np.floating)):
        raise ValueError(f"{label} must be a finite real number, got {val!r}")
    x = float(val)
    if not math.isfinite(x):
        raise ValueError(f"{label} must be finite, got {val!r}")
    return x


def _validate_rate(val: Any, n_denom: int, label: str, tol: float = 1e-12) -> tuple[float, int]:
    """Validate a binomial proportion in [0, 1] consistent with an integer numerator k / n_denom."""
    if n_denom <= 0:
        raise ValueError(f"Invalid denominator {n_denom} for {label}")
    x = _require_finite_float(val, label)
    if x < 0.0 or x > 1.0:
        raise ValueError(f"{label} out of [0, 1]: {x}")
    k = int(round(x * n_denom))
    if k < 0 or k > n_denom or abs(x - (k / float(n_denom))) > tol:
        raise ValueError(f"{label}={x} inconsistent with integer count k/{n_denom} (nearest k={k})")
    return x, k


def _validate_rate_and_mcse(
    rate_val: Any,
    mcse_val: Any,
    n_denom: int,
    label: str,
    tol: float = 1e-12,
) -> tuple[float, float, int]:
    """Validate (rate, mcse) pair for finiteness, [0, 1] range, k/n_denom grid, and binomial MCSE identity."""
    rate, k = _validate_rate(rate_val, n_denom, f"{label}.rate", tol=tol)
    mcse = _require_finite_float(mcse_val, f"{label}.mcse")
    if mcse < 0.0:
        raise ValueError(f"{label}.mcse < 0: {mcse}")
    exp_mcse = compute_mcse(k / float(n_denom), n_denom)
    if abs(mcse - exp_mcse) > tol:
        raise ValueError(
            f"{label}.mcse={mcse} contradicts binomial MCSE {exp_mcse} for rate={rate} (k={k}, N={n_denom})"
        )
    return rate, mcse, k


def _validate_rate_mcse_obj(obj: Any, n_denom: int, label: str, tol: float = 1e-12) -> tuple[float, float, int]:
    """Validate a {'rate': ..., 'mcse': ...} dictionary."""
    if not isinstance(obj, dict) or "rate" not in obj or "mcse" not in obj:
        raise KeyError(f"Missing required {{'rate', 'mcse'}} dict at {label}")
    return _validate_rate_and_mcse(obj["rate"], obj["mcse"], n_denom, label, tol=tol)


def load_cell_results(
    cell_dir: Path,
    expected_r: int = 2000,
    *,
    cell_spec: Optional[dict] = None,
    pop_fingerprint: Optional[str] = None,
    method: Optional[str] = None,
    bank: Optional[str] = None,
    bank_id: Optional[int] = None,
    b_reps: int = 5000,
    n_ac: int = 80,
    n_bd: int = 80,
    gates: Optional[Dict[str, str]] = None,
    strict_identity: bool = True,
) -> Dict[str, np.ndarray]:
    """Load and concatenate all chunk files for a cell with full entity and identity verification."""
    if expected_r <= 0:
        raise ValueError(f"expected_r must be positive, got {expected_r}")
    if not cell_dir.is_dir():
        raise FileNotFoundError(f"Cell directory missing: {cell_dir}")

    if strict_identity:
        missing_args = [
            name
            for name, val in (
                ("cell_spec", cell_spec),
                ("pop_fingerprint", pop_fingerprint),
                ("method", method),
                ("bank", bank),
                ("bank_id", bank_id),
                ("gates", gates),
            )
            if val is None
        ]
        if missing_args:
            raise ValueError(f"strict_identity=True requires non-None arguments: {missing_args}")
        assert cell_spec is not None
        if cell_dir.name != str(cell_spec["cell_name"]):
            raise ValueError(f"Cell directory name '{cell_dir.name}' != expected '{cell_spec['cell_name']}'")

    chunk_files = sorted(cell_dir.glob("chunk_*.npz"))
    json_files = sorted(cell_dir.glob("chunk_*.json"))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk files found in {cell_dir}")
    if [cf.stem for cf in chunk_files] != [jf.stem for jf in json_files]:
        raise ValueError(f"Chunk .npz/.json file pairing mismatch in {cell_dir}")

    chunks_data: List[Dict[str, np.ndarray]] = []
    current_rep = 0
    invariant_anchor: Optional[Dict[str, Any]] = None
    enforce_domains = method in ALL3_METHODS

    for cf in chunk_files:
        meta_file = cf.with_suffix(".json")
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if "start_rep" not in meta or "end_rep" not in meta:
            raise ValueError(f"Chunk metadata missing start_rep/end_rep in {meta_file}")

        start_rep = int(meta["start_rep"])
        end_rep = int(meta["end_rep"])
        if start_rep != current_rep or end_rep <= start_rep:
            raise ValueError(
                f"Chunk rep discontinuity in {cell_dir}: expected start={current_rep}, got [{start_rep}, {end_rep})"
            )

        expected_stem = f"chunk_{start_rep:04d}_{end_rep:04d}"
        if cf.stem != expected_stem:
            raise ValueError(f"Chunk filename '{cf.stem}' != metadata interval '{expected_stem}'")

        with np.load(cf) as npz:
            chunk_dict = {k: npz[k] for k in npz.files}

        if strict_identity:
            assert cell_spec is not None and pop_fingerprint is not None
            assert method is not None and bank is not None and bank_id is not None and gates is not None
            expected_id = build_expected_chunk_identity(
                cell_spec=cell_spec,
                pop_fingerprint=pop_fingerprint,
                method_label=method,
                bank_name=bank,
                bank_id=bank_id,
                start_rep=start_rep,
                end_rep=end_rep,
                r_total=expected_r,
                b_reps=b_reps,
                n_ac=n_ac,
                n_bd=n_bd,
                gates=gates,
            )
            validate_chunk_payload_and_meta(chunk_dict, meta, expected_id)
        else:
            for req_k in IDENTITY_BINDING_KEYS:
                if req_k not in meta:
                    raise ValueError(f"Chunk metadata missing binding key '{req_k}' in {meta_file}")
            if int(meta["r_total"]) != expected_r or int(meta["b_reps"]) != b_reps:
                raise ValueError(
                    f"Chunk r_total/b_reps mismatch in {meta_file}: "
                    f"meta=({meta['r_total']}, {meta['b_reps']}) vs expected=({expected_r}, {b_reps})"
                )
            if cell_spec is not None:
                if meta["cell_name"] != cell_spec["cell_name"] or int(meta["cell_index"]) != int(cell_spec["cell_index"]):
                    raise ValueError(f"Chunk cell identity mismatch in {meta_file}")
            cur_inv = {k: meta[k] for k in IDENTITY_BINDING_KEYS if k not in ("start_rep", "end_rep")}
            if invariant_anchor is None:
                invariant_anchor = cur_inv
            elif cur_inv != invariant_anchor:
                raise ValueError(f"Cross-chunk metadata inconsistency in {cell_dir}")

            validate_payload_arrays(
                chunk_dict,
                start_rep=start_rep,
                end_rep=end_rep,
                b_reps=b_reps,
                enforce_domains=(meta.get("method") in ALL3_METHODS),
            )
            payload_sha = compute_chunk_payload_sha(chunk_dict)
            if payload_sha != meta.get("payload_sha256"):
                raise ValueError(f"Chunk payload SHA256 mismatch in {cf}")

        chunks_data.append(chunk_dict)
        current_rep = end_rep

    if current_rep != expected_r:
        raise ValueError(f"Incomplete cell data in {cell_dir}: got {current_rep} reps, expected {expected_r}")

    keys = sorted(chunks_data[0].keys())
    merged = {k: np.concatenate([c[k] for c in chunks_data], axis=0) for k in keys}
    validate_payload_arrays(
        merged,
        start_rep=0,
        end_rep=expected_r,
        b_reps=b_reps,
        enforce_domains=enforce_domains,
    )
    return merged


def evaluate_cell_summary(
    cell_spec: dict,
    data: Dict[str, np.ndarray],
    r_reps: int = 2000,
    b_reps: int = 5000,
    enforce_domains: bool = False,
) -> Dict[str, Any]:
    """Validate full cell payload arrays (exact 0..r_reps-1 rows) and compute screening summary."""
    validate_payload_arrays(data, start_rep=0, end_rep=r_reps, b_reps=b_reps, enforce_domains=enforce_domains)

    truth = cell_spec["truth"]
    t_vals = [Fraction(truth[name]) for name in NAMES_A]
    numeric_truth = np.array([float(x) for x in t_vals], dtype=np.float64)

    # SA1: composite null theta_1 <= 0; SA2..SA4: point null theta_j == 0
    null_flags = np.array([
        t_vals[0] <= Fraction(0),
        t_vals[1] == Fraction(0),
        t_vals[2] == Fraction(0),
        t_vals[3] == Fraction(0),
    ], dtype=bool)
    signs = np.array([(x > 0) - (x < 0) for x in t_vals], dtype=int)

    p_arr = data["p"]
    reject = data["reject"]
    direction = data["direction"]
    ci_main = data["ci"]
    ci_hist = data["ci_995"]
    degenerate = data["degenerate"]
    degenerate_hist = data["degenerate_995"]

    declared = reject & (direction != 0)
    false_reject = reject & null_flags[None, :]
    wrong_dir = declared & (~null_flags[None, :]) & (direction != signs[None, :])
    correct_dir = declared & (~null_flags[None, :]) & (direction == signs[None, :])

    fwer_arr = np.any(false_reject, axis=1)
    family_dir_err_arr = np.any(false_reject | wrong_dir, axis=1)

    cov_main_arr = (ci_main[:, :, 0] <= numeric_truth[None, :]) & (numeric_truth[None, :] <= ci_main[:, :, 1])
    simult_cov_main_arr = np.all(cov_main_arr, axis=1)

    cov_hist_arr = (ci_hist[:, :, 0] <= numeric_truth[None, :]) & (numeric_truth[None, :] <= ci_hist[:, :, 1])
    simult_cov_hist_arr = np.all(cov_hist_arr, axis=1)

    screen05_arr = (p_arr <= 0.05) & null_flags[None, :]
    screen0125_arr = (p_arr <= 0.0125) & null_flags[None, :]
    screen005_arr = (p_arr <= 0.005) & null_flags[None, :]

    fwer_rate = float(np.mean(fwer_arr))
    family_dir_rate = float(np.mean(family_dir_err_arr))
    simult_cov_main_rate = float(np.mean(simult_cov_main_arr))
    simult_cov_hist_rate = float(np.mean(simult_cov_hist_arr))

    fwer_mcse = compute_mcse(fwer_rate, r_reps)
    family_dir_mcse = compute_mcse(family_dir_rate, r_reps)
    simult_cov_main_mcse = compute_mcse(simult_cov_main_rate, r_reps)
    simult_cov_hist_mcse = compute_mcse(simult_cov_hist_rate, r_reps)

    slots_summary = {}
    for j, name in enumerate(NAMES_A):
        rej_r = float(np.mean(reject[:, j]))
        dir_p1_r = float(np.mean(direction[:, j] == 1))
        dir_m1_r = float(np.mean(direction[:, j] == -1))
        f_rej_r = float(np.mean(false_reject[:, j]))
        w_dir_r = float(np.mean(wrong_dir[:, j]))
        c_dir_r = float(np.mean(correct_dir[:, j]))

        cov_m_r = float(np.mean(cov_main_arr[:, j]))
        cov_h_r = float(np.mean(cov_hist_arr[:, j]))

        degen_r = float(np.mean(degenerate[:, j]))
        degen_h_r = float(np.mean(degenerate_hist[:, j]))
        degen_tol0_r = float(np.mean(data["degenerate_tol0"][:, j]))

        non_degen_mask = ~degenerate[:, j]
        non_degen_count = int(np.sum(non_degen_mask))
        if non_degen_count > 0:
            non_degen_cov_count = int(np.sum(cov_main_arr[non_degen_mask, j]))
            cond_cov_m = non_degen_cov_count / float(non_degen_count)
            cond_cov_m_mcse = compute_mcse(cond_cov_m, non_degen_count)
        else:
            non_degen_cov_count = 0
            cond_cov_m = None
            cond_cov_m_mcse = None

        non_degen_h_mask = ~degenerate_hist[:, j]
        non_degen_h_count = int(np.sum(non_degen_h_mask))
        if non_degen_h_count > 0:
            non_degen_h_cov_count = int(np.sum(cov_hist_arr[non_degen_h_mask, j]))
            cond_cov_h = non_degen_h_cov_count / float(non_degen_h_count)
            cond_cov_h_mcse = compute_mcse(cond_cov_h, non_degen_h_count)
        else:
            non_degen_h_cov_count = 0
            cond_cov_h = None
            cond_cov_h_mcse = None

        if null_flags[j]:
            s05_r = float(np.mean(screen05_arr[:, j]))
            s0125_r = float(np.mean(screen0125_arr[:, j]))
            s005_r = float(np.mean(screen005_arr[:, j]))
        else:
            s05_r = s0125_r = s005_r = None

        fail_boot_r = float(np.mean(data["failure_distinct_boot"][:, j]))
        fail_obs_se_r = float(np.mean(data["failure_observed_se"][:, j]))
        fail_boot_se_r = float(np.mean(data["failure_bootstrap_se"][:, j]))
        fail_t_r = float(np.mean(data["failure_studentized_distribution"][:, j]))
        fail_ci_r = float(np.mean(data["failure_ci"][:, j]))
        tol_diff_count = int(np.sum(data["tol_diff"][:, j]))

        slots_summary[name] = {
            "is_null": bool(null_flags[j]),
            "rejection_rate": rej_r,
            "rejection_mcse": compute_mcse(rej_r, r_reps),
            "direction_positive_rate": dir_p1_r,
            "direction_negative_rate": dir_m1_r,
            "false_reject_rate": f_rej_r,
            "wrong_direction_rate": w_dir_r,
            "correct_direction_rate": c_dir_r,
            "correct_direction_mcse": compute_mcse(c_dir_r, r_reps),
            "coverage_9875": cov_m_r,
            "coverage_9875_mcse": compute_mcse(cov_m_r, r_reps),
            "coverage_995": cov_h_r,
            "coverage_995_mcse": compute_mcse(cov_h_r, r_reps),
            "nondegenerate_covered_count_9875": non_degen_cov_count,
            "nondegenerate_count_9875": non_degen_count,
            "nondegenerate_conditional_coverage_9875": cond_cov_m,
            "nondegenerate_conditional_coverage_9875_mcse": cond_cov_m_mcse,
            "nondegenerate_covered_count_995": non_degen_h_cov_count,
            "nondegenerate_count_995": non_degen_h_count,
            "nondegenerate_conditional_coverage_995": cond_cov_h,
            "nondegenerate_conditional_coverage_995_mcse": cond_cov_h_mcse,
            "screen05_rate": s05_r,
            "screen0125_rate": s0125_r,
            "screen005_rate": s005_r,
            "degeneracy_rate": degen_r,
            "degeneracy_rate_995": degen_h_r,
            "degeneracy_rate_tol0": degen_tol0_r,
            "failure_distinct_boot_rate": fail_boot_r,
            "failure_observed_se_rate": fail_obs_se_r,
            "failure_bootstrap_se_rate": fail_boot_se_r,
            "failure_studentized_distribution_rate": fail_t_r,
            "failure_ci_rate": fail_ci_r,
            "tol_diff_count": tol_diff_count,
        }

    chk_screen05 = all(
        slots_summary[name]["screen05_rate"] <= 0.075
        for name in NAMES_A if slots_summary[name]["is_null"]
    )
    chk_screen0125 = all(
        slots_summary[name]["screen0125_rate"] <= 0.01875
        for name in NAMES_A if slots_summary[name]["is_null"]
    )
    chk_indiv_cov_9875 = all(
        slots_summary[name]["coverage_9875"] >= 0.975
        for name in NAMES_A
    )
    chk_fwer = fwer_rate <= (0.05 + 2.0 * fwer_mcse)
    chk_fam_dir = family_dir_rate <= (0.05 + 2.0 * family_dir_mcse)
    chk_simult_cov_9875 = simult_cov_main_rate >= (0.95 - 2.0 * simult_cov_main_mcse)

    cell_passed_9875 = bool(
        chk_screen05 and chk_screen0125 and chk_indiv_cov_9875
        and chk_fwer and chk_fam_dir and chk_simult_cov_9875
    )

    chk_screen005 = all(
        slots_summary[name]["screen005_rate"] <= 0.0075
        for name in NAMES_A if slots_summary[name]["is_null"]
    )
    chk_indiv_cov_995 = all(
        slots_summary[name]["coverage_995"] >= 0.99
        for name in NAMES_A
    )
    chk_simult_cov_995 = simult_cov_hist_rate >= (0.95 - 2.0 * simult_cov_hist_mcse)
    cell_passed_995 = bool(
        chk_screen05 and chk_screen005 and chk_indiv_cov_995
        and chk_fwer and chk_fam_dir and chk_simult_cov_995
    )

    nonnull_mask = ~null_flags
    if np.any(nonnull_mask):
        all_nonnull_cd_arr = np.all(correct_dir[:, nonnull_mask], axis=1)
        all_nonnull_cd_rate = float(np.mean(all_nonnull_cd_arr))
    else:
        all_nonnull_cd_rate = 0.0
    all4_cd_rate = float(np.mean(np.all(correct_dir, axis=1)))
    sa2_sa3_cd_rate = float(np.mean(correct_dir[:, 1] & correct_dir[:, 2]))
    any_cd_rate = float(np.mean(np.any(correct_dir, axis=1)))

    return {
        "cell_name": str(cell_spec["cell_name"]),
        "cell_index": int(cell_spec["cell_index"]),
        "population_name": str(cell_spec.get("population_name", cell_spec["cell_name"])),
        "fingerprint": str(cell_spec.get("fingerprint", "")),
        "missing": str(cell_spec.get("missing", "none")),
        "missing_rate": str(cell_spec.get("missing_rate", "0")),
        "block": cell_spec.get("block"),
        "category": cell_spec.get("category"),
        "truth": truth,
        "is_null_family": cell_spec.get("is_null_family", False),
        "replicates_verified": r_reps,
        "fwer": {"rate": fwer_rate, "mcse": fwer_mcse},
        "family_direction_error": {"rate": family_dir_rate, "mcse": family_dir_mcse},
        "simultaneous_coverage_9875": {"rate": simult_cov_main_rate, "mcse": simult_cov_main_mcse},
        "simultaneous_coverage_995": {"rate": simult_cov_hist_rate, "mcse": simult_cov_hist_mcse},
        "joint_detection": {
            "all4_correct_direction": {"rate": all4_cd_rate, "mcse": compute_mcse(all4_cd_rate, r_reps)},
            "all_nonnull_correct_direction": {"rate": all_nonnull_cd_rate, "mcse": compute_mcse(all_nonnull_cd_rate, r_reps)},
            "continuous_sa2_sa3_correct_direction": {"rate": sa2_sa3_cd_rate, "mcse": compute_mcse(sa2_sa3_cd_rate, r_reps)},
            "any_correct_direction": {"rate": any_cd_rate, "mcse": compute_mcse(any_cd_rate, r_reps)},
        },
        "slots": slots_summary,
        "checks_9875": {
            "screen05_passed": chk_screen05,
            "screen0125_passed": chk_screen0125,
            "individual_coverage_9875_passed": chk_indiv_cov_9875,
            "fwer_passed": chk_fwer,
            "family_direction_passed": chk_fam_dir,
            "simultaneous_coverage_9875_passed": chk_simult_cov_9875,
            "cell_passed": cell_passed_9875,
        },
        "checks_995": {
            "screen05_passed": chk_screen05,
            "screen005_passed": chk_screen005,
            "individual_coverage_995_passed": chk_indiv_cov_995,
            "fwer_passed": chk_fwer,
            "family_direction_passed": chk_fam_dir,
            "simultaneous_coverage_995_passed": chk_simult_cov_995,
            "cell_passed": cell_passed_995,
        },
    }


def validate_and_recompute_cell_summary_metrics(
    cell: Dict[str, Any],
    expected_r: int = LOCKED_PRODUCTION_REPLICATES,
    manifest_cell: Optional[dict] = None,
) -> Dict[str, bool]:
    """Validate finiteness, [0, 1] bounds, count/denominator & binomial MCSE consistency,
    non-degenerate conditional counts, Fréchet family bounds, and independently recompute all
    6 main `checks_9875` (and `checks_995` if present) flags directly from metrics, rejecting
    any contradiction with stored flags (`c-code-r1` B1/B2).
    """
    if not isinstance(cell, dict):
        raise ValueError("Cell summary must be a dictionary")
    if expected_r <= 0:
        raise ValueError(f"expected_r must be > 0, got {expected_r}")

    for req_k in (
        "cell_name",
        "cell_index",
        "fingerprint",
        "truth",
        "replicates_verified",
        "fwer",
        "family_direction_error",
        "simultaneous_coverage_9875",
        "joint_detection",
        "slots",
        "checks_9875",
    ):
        if req_k not in cell:
            raise KeyError(f"Cell '{cell.get('cell_name', '<unknown>')}' missing required key '{req_k}'")

    c_name = str(cell["cell_name"])
    c_idx = _require_strict_int(cell["cell_index"], f"{c_name}.cell_index")
    c_fp = str(cell["fingerprint"])
    if not c_name or not c_fp:
        raise ValueError(f"Empty cell_name or fingerprint at index {c_idx}")

    rep_ver = _require_strict_int(cell["replicates_verified"], f"{c_name}.replicates_verified")
    if rep_ver != expected_r:
        raise ValueError(f"{c_name}.replicates_verified={rep_ver} != expected_r={expected_r}")

    truth = cell["truth"]
    if not isinstance(truth, dict):
        raise ValueError(f"{c_name}.truth must be a dictionary")
    for s_name in NAMES_A:
        if s_name not in truth:
            raise KeyError(f"{c_name}.truth missing slot '{s_name}'")

    if manifest_cell is not None:
        m_idx = _require_strict_int(manifest_cell["cell_index"], "manifest_cell.cell_index")
        m_name = str(manifest_cell["cell_name"])
        m_pop = str(manifest_cell["population_name"])
        m_fp = str(manifest_cell["fingerprint"])
        if c_idx != m_idx or c_name != m_name:
            raise ValueError(
                f"Manifest cell binding mismatch at index {m_idx}: got ({c_idx}, {c_name!r}), expected ({m_idx}, {m_name!r})"
            )
        if "population_name" in cell and str(cell["population_name"]) != m_pop:
            raise ValueError(
                f"{c_name}.population_name={cell['population_name']!r} != manifest population_name={m_pop!r}"
            )
        if c_fp != m_fp:
            raise ValueError(f"{c_name} (#{c_idx}) fingerprint mismatch: got {c_fp!r}, expected {m_fp!r}")
        for s_name in NAMES_A:
            if Fraction(truth[s_name]) != Fraction(manifest_cell["truth"][s_name]):
                raise ValueError(
                    f"{c_name}.truth[{s_name}]={truth[s_name]!r} != manifest truth={manifest_cell['truth'][s_name]!r}"
                )

    t_vals = [Fraction(truth[s_name]) for s_name in NAMES_A]
    expected_nulls = [
        t_vals[0] <= Fraction(0),
        t_vals[1] == Fraction(0),
        t_vals[2] == Fraction(0),
        t_vals[3] == Fraction(0),
    ]

    fwer_rate, fwer_mcse, fwer_k = _validate_rate_mcse_obj(cell["fwer"], expected_r, f"{c_name}.fwer")
    fam_dir_rate, fam_dir_mcse, fam_dir_k = _validate_rate_mcse_obj(
        cell["family_direction_error"], expected_r, f"{c_name}.family_direction_error"
    )
    if fam_dir_k < fwer_k:
        raise ValueError(f"{c_name}: family_direction_error ({fam_dir_rate}) < fwer ({fwer_rate})")

    sim98_rate, sim98_mcse, sim98_k = _validate_rate_mcse_obj(
        cell["simultaneous_coverage_9875"], expected_r, f"{c_name}.simultaneous_coverage_9875"
    )

    has_995 = ("checks_995" in cell) or ("simultaneous_coverage_995" in cell)
    if has_995:
        if "simultaneous_coverage_995" not in cell:
            raise KeyError(f"{c_name} missing simultaneous_coverage_995")
        sim995_rate, sim995_mcse, sim995_k = _validate_rate_mcse_obj(
            cell["simultaneous_coverage_995"], expected_r, f"{c_name}.simultaneous_coverage_995"
        )
    else:
        sim995_rate = sim995_mcse = 0.0
        sim995_k = 0

    jd = cell["joint_detection"]
    if not isinstance(jd, dict):
        raise ValueError(f"{c_name}.joint_detection must be a dictionary")
    _, _, all4_cd_k = _validate_rate_mcse_obj(jd.get("all4_correct_direction"), expected_r, f"{c_name}.all4_cd")
    _, _, all_nn_cd_k = _validate_rate_mcse_obj(
        jd.get("all_nonnull_correct_direction"), expected_r, f"{c_name}.all_nonnull_cd"
    )
    _, _, sa23_cd_k = _validate_rate_mcse_obj(
        jd.get("continuous_sa2_sa3_correct_direction"), expected_r, f"{c_name}.sa2_sa3_cd"
    )
    _, _, any_cd_k = _validate_rate_mcse_obj(jd.get("any_correct_direction"), expected_r, f"{c_name}.any_cd")

    slots = cell["slots"]
    if not isinstance(slots, dict):
        raise ValueError(f"{c_name}.slots must be a dictionary")

    cov98_vals: Dict[str, float] = {}
    cov98_ks: List[int] = []
    cov995_vals: Dict[str, float] = {}
    cov995_ks: List[int] = []
    cd_ks: List[int] = []
    null_rej_ks: List[int] = []
    s05_vals: Dict[str, float] = {}
    s0125_vals: Dict[str, float] = {}
    s005_vals: Dict[str, float] = {}

    for j, s_name in enumerate(NAMES_A):
        if s_name not in slots or not isinstance(slots[s_name], dict):
            raise KeyError(f"{c_name}.slots missing slot dict '{s_name}'")
        so = slots[s_name]
        for sk in (
            "is_null",
            "rejection_rate",
            "rejection_mcse",
            "correct_direction_rate",
            "correct_direction_mcse",
            "coverage_9875",
            "coverage_9875_mcse",
            "degeneracy_rate",
        ):
            if sk not in so:
                raise KeyError(f"{c_name}.slots.{s_name} missing required key '{sk}'")

        if not isinstance(so["is_null"], bool) or so["is_null"] != expected_nulls[j]:
            raise ValueError(
                f"{c_name}.slots.{s_name}.is_null={so['is_null']!r} contradicts truth-derived {expected_nulls[j]}"
            )

        _, _, rej_k = _validate_rate_and_mcse(
            so["rejection_rate"], so["rejection_mcse"], expected_r, f"{c_name}.slots.{s_name}.rejection"
        )
        _, _, cd_k = _validate_rate_and_mcse(
            so["correct_direction_rate"],
            so["correct_direction_mcse"],
            expected_r,
            f"{c_name}.slots.{s_name}.correct_direction",
        )
        cov98_r, _, cov98_k = _validate_rate_and_mcse(
            so["coverage_9875"], so["coverage_9875_mcse"], expected_r, f"{c_name}.slots.{s_name}.coverage_9875"
        )
        _, degen_k = _validate_rate(so["degeneracy_rate"], expected_r, f"{c_name}.slots.{s_name}.degeneracy_rate")

        cov98_vals[s_name] = cov98_r
        cov98_ks.append(cov98_k)
        cd_ks.append(cd_k)

        for opt_r_key in (
            "direction_positive_rate",
            "direction_negative_rate",
            "false_reject_rate",
            "wrong_direction_rate",
            "degeneracy_rate_995",
            "degeneracy_rate_tol0",
            "failure_distinct_boot_rate",
            "failure_observed_se_rate",
            "failure_bootstrap_se_rate",
            "failure_studentized_distribution_rate",
            "failure_ci_rate",
        ):
            if opt_r_key in so:
                _validate_rate(so[opt_r_key], expected_r, f"{c_name}.slots.{s_name}.{opt_r_key}")

        if "nondegenerate_count_9875" in so or "nondegenerate_covered_count_9875" in so:
            nd_cnt = _require_strict_int(so.get("nondegenerate_count_9875"), f"{c_name}.{s_name}.nd_cnt_9875")
            nd_cov = _require_strict_int(so.get("nondegenerate_covered_count_9875"), f"{c_name}.{s_name}.nd_cov_9875")
            if nd_cnt != expected_r - degen_k:
                raise ValueError(f"{c_name}.{s_name}: nd_cnt_9875={nd_cnt} != R - degen_k ({expected_r - degen_k})")
            if nd_cov < 0 or nd_cov > nd_cnt or not (nd_cov <= cov98_k <= nd_cov + degen_k):
                raise ValueError(
                    f"{c_name}.{s_name}: inconsistent nd_cov_9875={nd_cov} vs cov98_k={cov98_k}, degen_k={degen_k}"
                )
            if nd_cnt > 0:
                cc_r, _, cc_k = _validate_rate_and_mcse(
                    so.get("nondegenerate_conditional_coverage_9875"),
                    so.get("nondegenerate_conditional_coverage_9875_mcse"),
                    nd_cnt,
                    f"{c_name}.{s_name}.cond_cov_9875",
                )
                if cc_k != nd_cov or abs(cc_r - (nd_cov / float(nd_cnt))) > 1e-12:
                    raise ValueError(f"{c_name}.{s_name}: cond_cov_9875 numerator mismatch")
            else:
                if (
                    so.get("nondegenerate_conditional_coverage_9875") is not None
                    or so.get("nondegenerate_conditional_coverage_9875_mcse") is not None
                ):
                    raise ValueError(f"{c_name}.{s_name}: cond_cov_9875 must be None when nd_cnt == 0")

        if has_995 or ("coverage_995" in so):
            if "coverage_995" not in so or "coverage_995_mcse" not in so:
                raise KeyError(f"{c_name}.slots.{s_name} missing coverage_995/coverage_995_mcse")
            cov995_r, _, cov995_k = _validate_rate_and_mcse(
                so["coverage_995"], so["coverage_995_mcse"], expected_r, f"{c_name}.slots.{s_name}.coverage_995"
            )
            cov995_vals[s_name] = cov995_r
            cov995_ks.append(cov995_k)

            if "nondegenerate_count_995" in so or "nondegenerate_covered_count_995" in so:
                if "degeneracy_rate_995" not in so:
                    raise KeyError(f"{c_name}.{s_name} missing degeneracy_rate_995")
                _, degen995_k = _validate_rate(so["degeneracy_rate_995"], expected_r, f"{c_name}.{s_name}.degen_995")
                nd_h_cnt = _require_strict_int(so.get("nondegenerate_count_995"), f"{c_name}.{s_name}.nd_cnt_995")
                nd_h_cov = _require_strict_int(
                    so.get("nondegenerate_covered_count_995"), f"{c_name}.{s_name}.nd_cov_995"
                )
                if nd_h_cnt != expected_r - degen995_k:
                    raise ValueError(f"{c_name}.{s_name}: nd_cnt_995 mismatch")
                if nd_h_cov < 0 or nd_h_cov > nd_h_cnt or not (nd_h_cov <= cov995_k <= nd_h_cov + degen995_k):
                    raise ValueError(f"{c_name}.{s_name}: inconsistent nd_cov_995")
                if nd_h_cnt > 0:
                    cc_hr, _, cc_hk = _validate_rate_and_mcse(
                        so.get("nondegenerate_conditional_coverage_995"),
                        so.get("nondegenerate_conditional_coverage_995_mcse"),
                        nd_h_cnt,
                        f"{c_name}.{s_name}.cond_cov_995",
                    )
                    if cc_hk != nd_h_cov or abs(cc_hr - (nd_h_cov / float(nd_h_cnt))) > 1e-12:
                        raise ValueError(f"{c_name}.{s_name}: cond_cov_995 numerator mismatch")
                else:
                    if (
                        so.get("nondegenerate_conditional_coverage_995") is not None
                        or so.get("nondegenerate_conditional_coverage_995_mcse") is not None
                    ):
                        raise ValueError(f"{c_name}.{s_name}: cond_cov_995 must be None when nd_cnt_995 == 0")

        if expected_nulls[j]:
            if cd_k != 0:
                raise ValueError(f"{c_name}.slots.{s_name}: null slot cannot have correct_direction_rate > 0")
            if "screen05_rate" not in so or "screen0125_rate" not in so:
                raise KeyError(f"{c_name}.slots.{s_name}: null slot missing screen05_rate/screen0125_rate")
            s05_r, k05 = _validate_rate(so["screen05_rate"], expected_r, f"{c_name}.slots.{s_name}.screen05_rate")
            s0125_r, k0125 = _validate_rate(
                so["screen0125_rate"], expected_r, f"{c_name}.slots.{s_name}.screen0125_rate"
            )
            if k0125 > k05 or rej_k > k05:
                raise ValueError(
                    f"{c_name}.slots.{s_name}: screen0125 ({k0125}) or rejection ({rej_k}) exceeds screen05 ({k05})"
                )
            s05_vals[s_name] = s05_r
            s0125_vals[s_name] = s0125_r
            null_rej_ks.append(rej_k)
            if has_995 or ("screen005_rate" in so and so["screen005_rate"] is not None):
                if "screen005_rate" not in so or so["screen005_rate"] is None:
                    raise KeyError(f"{c_name}.slots.{s_name}: null slot missing screen005_rate")
                s005_r, k005 = _validate_rate(
                    so["screen005_rate"], expected_r, f"{c_name}.slots.{s_name}.screen005_rate"
                )
                if k005 > k0125:
                    raise ValueError(f"{c_name}.slots.{s_name}: screen005 ({k005}) exceeds screen0125 ({k0125})")
                s005_vals[s_name] = s005_r
        else:
            if cd_k > rej_k:
                raise ValueError(f"{c_name}.slots.{s_name}: correct_direction_rate exceeds rejection_rate")
            if so.get("screen05_rate") is not None or so.get("screen0125_rate") is not None or so.get("screen005_rate") is not None:
                raise ValueError(f"{c_name}.slots.{s_name}: non-null slot must have None screen rates")

    if null_rej_ks:
        if fwer_k < max(null_rej_ks) or fwer_k > sum(null_rej_ks):
            raise ValueError(f"{c_name}: fwer count {fwer_k} violates Fréchet bounds on null rejections {null_rej_ks}")
    else:
        if fwer_k != 0:
            raise ValueError(f"{c_name}: fwer must be 0 when no slot is null, got {fwer_rate}")

    min_cov98_k = min(cov98_ks)
    frechet_lo_98_k = max(0, sum(cov98_ks) - 3 * expected_r)
    if sim98_k > min_cov98_k or sim98_k < frechet_lo_98_k:
        raise ValueError(
            f"{c_name}: simultaneous_coverage_9875 count {sim98_k} outside Fréchet bounds [{frechet_lo_98_k}, {min_cov98_k}]"
        )

    if has_995:
        min_cov995_k = min(cov995_ks)
        frechet_lo_995_k = max(0, sum(cov995_ks) - 3 * expected_r)
        if sim995_k > min_cov995_k or sim995_k < frechet_lo_995_k:
            raise ValueError(
                f"{c_name}: simultaneous_coverage_995 count {sim995_k} outside Fréchet bounds [{frechet_lo_995_k}, {min_cov995_k}]"
            )

    if all4_cd_k > min(cd_ks):
        raise ValueError(f"{c_name}: all4_correct_direction count {all4_cd_k} exceeds min slot count {min(cd_ks)}")
    if sa23_cd_k > min(cd_ks[1], cd_ks[2]):
        raise ValueError(f"{c_name}: continuous_sa2_sa3_correct_direction count exceeds min(SA2, SA3)")
    if any_cd_k < max(cd_ks) or any_cd_k > sum(cd_ks):
        raise ValueError(f"{c_name}: any_correct_direction count {any_cd_k} outside Fréchet bounds")
    nonnull_cd_ks = [cd_ks[j] for j in range(4) if not expected_nulls[j]]
    if nonnull_cd_ks:
        if all_nn_cd_k > min(nonnull_cd_ks):
            raise ValueError(f"{c_name}: all_nonnull_correct_direction count exceeds min non-null slot count")
    else:
        if all_nn_cd_k != 0:
            raise ValueError(f"{c_name}: all_nonnull_correct_direction must be 0 when all slots are null")

    re_screen05 = all(s05_vals[s_name] <= 0.075 for j, s_name in enumerate(NAMES_A) if expected_nulls[j])
    re_screen0125 = all(s0125_vals[s_name] <= 0.01875 for j, s_name in enumerate(NAMES_A) if expected_nulls[j])
    re_indiv_cov_9875 = all(cov98_vals[s_name] >= 0.975 for s_name in NAMES_A)
    re_fwer = fwer_rate <= (0.05 + 2.0 * fwer_mcse)
    re_fam_dir = fam_dir_rate <= (0.05 + 2.0 * fam_dir_mcse)
    re_simult_cov_9875 = sim98_rate >= (0.95 - 2.0 * sim98_mcse)
    re_cell_passed_9875 = bool(
        re_screen05
        and re_screen0125
        and re_indiv_cov_9875
        and re_fwer
        and re_fam_dir
        and re_simult_cov_9875
    )

    recomputed_9875 = {
        "screen05_passed": bool(re_screen05),
        "screen0125_passed": bool(re_screen0125),
        "individual_coverage_9875_passed": bool(re_indiv_cov_9875),
        "fwer_passed": bool(re_fwer),
        "family_direction_passed": bool(re_fam_dir),
        "simultaneous_coverage_9875_passed": bool(re_simult_cov_9875),
        "cell_passed": re_cell_passed_9875,
    }

    chk = cell["checks_9875"]
    if not isinstance(chk, dict):
        raise ValueError(f"{c_name}.checks_9875 must be a dictionary")
    for ck, exp_bool in recomputed_9875.items():
        if ck not in chk or not isinstance(chk[ck], bool):
            raise KeyError(f"{c_name}.checks_9875 missing boolean key '{ck}'")
        if chk[ck] != exp_bool:
            raise ValueError(
                f"{c_name}.checks_9875.{ck}={chk[ck]} contradicts metric-recomputed value {exp_bool}"
            )

    if "checks_995" in cell:
        chk995 = cell["checks_995"]
        if not isinstance(chk995, dict):
            raise ValueError(f"{c_name}.checks_995 must be a dictionary")
        re_screen005 = all(s005_vals[s_name] <= 0.0075 for j, s_name in enumerate(NAMES_A) if expected_nulls[j])
        re_indiv_cov_995 = all(cov995_vals[s_name] >= 0.99 for s_name in NAMES_A)
        re_simult_cov_995 = sim995_rate >= (0.95 - 2.0 * sim995_mcse)
        re_cell_passed_995 = bool(
            re_screen05
            and re_screen005
            and re_indiv_cov_995
            and re_fwer
            and re_fam_dir
            and re_simult_cov_995
        )
        recomputed_995 = {
            "screen05_passed": bool(re_screen05),
            "screen005_passed": bool(re_screen005),
            "individual_coverage_995_passed": bool(re_indiv_cov_995),
            "fwer_passed": bool(re_fwer),
            "family_direction_passed": bool(re_fam_dir),
            "simultaneous_coverage_995_passed": bool(re_simult_cov_995),
            "cell_passed": re_cell_passed_995,
        }
        for ck, exp_bool in recomputed_995.items():
            if ck not in chk995 or not isinstance(chk995[ck], bool):
                raise KeyError(f"{c_name}.checks_995 missing boolean key '{ck}'")
            if chk995[ck] != exp_bool:
                raise ValueError(
                    f"{c_name}.checks_995.{ck}={chk995[ck]} contradicts metric-recomputed value {exp_bool}"
                )

    return recomputed_9875


def verify_bank_summary_against_sealed_identity(
    bank_summary: Dict[str, Any],
    expected_bank: str,
    expected_cells: int,
    expected_method: Optional[str] = None,
    manifest_path: Optional[Path] = None,
    populations_path: Optional[Path] = None,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
    expected_replicates: int = LOCKED_PRODUCTION_REPLICATES,
    expected_bootstrap_replicates: int = LOCKED_PRODUCTION_BOOTSTRAP_REPLICATES,
    expected_n_ac: int = LOCKED_PRODUCTION_N_AC,
    expected_n_bd: int = LOCKED_PRODUCTION_N_BD,
) -> tuple[List[dict], Dict[str, str]]:
    """Bind a bank summary against the live sealed run identity, fixed production run parameters
    (`R=2000, B=5000, n_ac=80, n_bd=80`), complete manifest & population definitions, and per-cell
    metric recomputation (`c-code-r1` B1/B2).
    """
    if not isinstance(bank_summary, dict):
        raise ValueError("bank_summary must be a dictionary")
    _assert_not_confirmation_bank(expected_bank, SEEDS.get(expected_bank, -1))
    if expected_bank not in ("validation", "power_grid"):
        raise ValueError(f"Unsupported expected_bank '{expected_bank}'")

    if manifest_path is None:
        manifest_path = DEFAULT_VALIDATION_MANIFEST if expected_bank == "validation" else DEFAULT_POWER_GRID_MANIFEST
    if populations_path is None:
        populations_path = (
            DEFAULT_VALIDATION_POPULATIONS if expected_bank == "validation" else DEFAULT_POWER_GRID_POPULATIONS
        )

    verified_gates = verify_integrity_gates(
        manifest_path,
        populations_path,
        bank_name=expected_bank,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    if bank_summary.get("bank") != expected_bank:
        raise ValueError(f"Bank mismatch: got {bank_summary.get('bank')!r}, expected {expected_bank!r}")
    got_bank_id = _require_strict_int(bank_summary.get("bank_id"), f"{expected_bank}.bank_id")
    if got_bank_id != int(SEEDS[expected_bank]):
        raise ValueError(f"Bank ID mismatch on {expected_bank}: got {got_bank_id}, expected {SEEDS[expected_bank]}")

    if expected_method is not None and bank_summary.get("method") != expected_method:
        raise ValueError(
            f"Method mismatch on {expected_bank}: got {bank_summary.get('method')!r}, expected {expected_method!r}"
        )
    if bank_summary.get("method") not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported method {bank_summary.get('method')!r} in {expected_bank} summary")

    got_r = _require_strict_int(bank_summary.get("replicates"), f"{expected_bank}.replicates")
    got_b = _require_strict_int(bank_summary.get("bootstrap_replicates"), f"{expected_bank}.bootstrap_replicates")
    got_nac = _require_strict_int(bank_summary.get("n_ac"), f"{expected_bank}.n_ac")
    got_nbd = _require_strict_int(bank_summary.get("n_bd"), f"{expected_bank}.n_bd")
    if (
        got_r != expected_replicates
        or got_b != expected_bootstrap_replicates
        or got_nac != expected_n_ac
        or got_nbd != expected_n_bd
    ):
        raise ValueError(
            f"Production run specification mismatch on {expected_bank}/{bank_summary.get('method')}: "
            f"got (R={got_r}, B={got_b}, n_ac={got_nac}, n_bd={got_nbd}), "
            f"expected (R={expected_replicates}, B={expected_bootstrap_replicates}, n_ac={expected_n_ac}, n_bd={expected_n_bd})"
        )

    got_gates = bank_summary.get("integrity_gates")
    if not isinstance(got_gates, dict):
        raise KeyError(f"{expected_bank} summary missing 'integrity_gates' dict")
    for gk, exp_gv in verified_gates.items():
        if got_gates.get(gk) != exp_gv:
            raise ValueError(
                f"Sealed integrity gate mismatch on {expected_bank}.{gk}: "
                f"summary has {got_gates.get(gk)!r}, live sealed identity requires {exp_gv!r}"
            )

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    pop_table = json.loads(populations_path.read_text(encoding="utf-8"))
    manifest_cells = manifest_data.get("cells", [])
    if len(manifest_cells) != expected_cells:
        raise ValueError(f"Manifest {manifest_path} has {len(manifest_cells)} cells, expected {expected_cells}")

    if "cell_summaries" not in bank_summary or not isinstance(bank_summary["cell_summaries"], list):
        raise KeyError(f"{expected_bank} summary missing 'cell_summaries' list")
    cells = bank_summary["cell_summaries"]
    if len(cells) != expected_cells:
        raise ValueError(f"{expected_bank} summary has {len(cells)} cells, expected {expected_cells}")
    if "total_cells" in bank_summary:
        if _require_strict_int(bank_summary["total_cells"], f"{expected_bank}.total_cells") != expected_cells:
            raise ValueError(f"{expected_bank}.total_cells != {expected_cells}")

    seen_names = set()
    re_passed_9875 = 0
    re_passed_995 = 0
    has_all_995 = True
    for pos, (c_sum, m_spec) in enumerate(zip(cells, manifest_cells)):
        if _require_strict_int(m_spec["cell_index"], "manifest.cell_index") != pos:
            raise ValueError(f"Non-contiguous manifest cell_index at {pos}")
        pop_name = str(m_spec["population_name"])
        if pop_name not in pop_table:
            raise KeyError(f"Population '{pop_name}' missing from {populations_path}")
        cname = str(c_sum.get("cell_name", ""))
        if cname in seen_names:
            raise ValueError(f"Duplicate cell_name '{cname}' in {expected_bank}")
        seen_names.add(cname)

        re_chk = validate_and_recompute_cell_summary_metrics(
            cell=c_sum,
            expected_r=expected_replicates,
            manifest_cell=m_spec,
        )
        if re_chk["cell_passed"]:
            re_passed_9875 += 1
        if "checks_995" in c_sum:
            if c_sum["checks_995"]["cell_passed"]:
                re_passed_995 += 1
        else:
            has_all_995 = False

    if "cells_passed_9875" in bank_summary:
        got_p98 = _require_strict_int(bank_summary["cells_passed_9875"], f"{expected_bank}.cells_passed_9875")
        if got_p98 != re_passed_9875:
            raise ValueError(
                f"{expected_bank}.cells_passed_9875={got_p98} contradicts recomputed count {re_passed_9875}"
            )
    if has_all_995 and "cells_passed_995" in bank_summary:
        got_p995 = _require_strict_int(bank_summary["cells_passed_995"], f"{expected_bank}.cells_passed_995")
        if got_p995 != re_passed_995:
            raise ValueError(
                f"{expected_bank}.cells_passed_995={got_p995} contradicts recomputed count {re_passed_995}"
            )

    return manifest_cells, verified_gates


def evaluate_main_power_reference_cells(
    cell_summaries: Dict[str, dict],
    require_all: bool = True,
) -> List[dict]:
    """Evaluate the 8 historical Block 3 power reference cells (`brief.md` §4.3).

    Missing reference cells raise KeyError when require_all=True; mismatched cell_index or invalid metrics raise ValueError.
    """
    results = []
    for ref in HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS:
        c_name = ref["cell_name"]
        slot = ref["slot"]
        if c_name not in cell_summaries:
            if require_all:
                raise KeyError(f"Missing required historical Block 3 power reference cell: '{c_name}'")
            continue
        c_sum = cell_summaries[c_name]
        if _require_strict_int(c_sum.get("cell_index"), f"{c_name}.cell_index") != int(ref["cell_index"]):
            raise ValueError(
                f"Reference cell '{c_name}' index mismatch: got {c_sum['cell_index']}, expected {ref['cell_index']}"
            )
        r_ver = _require_strict_int(c_sum.get("replicates_verified"), f"{c_name}.replicates_verified")
        validate_and_recompute_cell_summary_metrics(c_sum, expected_r=r_ver)
        slot_info = c_sum["slots"][slot]
        power, mcse, _ = _validate_rate_and_mcse(
            slot_info["correct_direction_rate"],
            slot_info["correct_direction_mcse"],
            r_ver,
            f"{c_name}.slots.{slot}.correct_direction",
        )
        lower_bound = power - 2.0 * mcse
        upper_bound = power + 2.0 * mcse
        status = classify_power_80(power, mcse)

        results.append({
            "cell_name": c_name,
            "cell_index": int(c_sum["cell_index"]),
            "fingerprint": str(c_sum.get("fingerprint", "")),
            "slot": slot,
            "target_effect": ref["effect"],
            "in_step5b_p_gate": bool(ref.get("in_step5b_p_gate", False)),
            "power": power,
            "mcse": mcse,
            "ci_95": [lower_bound, upper_bound],
            "status": status,
        })
    return results


def evaluate_boundary_degeneracy_diagnostics(
    cell_summaries: Dict[str, dict],
    require_all: bool = True,
    strict_fingerprint: bool = False,
) -> List[dict]:
    """Evaluate the 5 pinned boundary degeneracy diagnostic cells (`D01..D05`, indices 65, 66, 67, 68, 83).

    Missing cells raise KeyError when require_all=True; mismatched cell_index, fingerprint, or non-finite rates raise ValueError.
    """
    results = []
    for spec in PINNED_BOUNDARY_DIAGNOSTIC_SPECS:
        c_name = spec["cell_name"]
        if c_name not in cell_summaries:
            if require_all:
                raise KeyError(f"Missing required boundary degeneracy diagnostic cell: '{c_name}'")
            continue
        c_sum = cell_summaries[c_name]
        if _require_strict_int(c_sum.get("cell_index"), f"{c_name}.cell_index") != int(spec["cell_index"]):
            raise ValueError(
                f"Diagnostic cell '{c_name}' index mismatch: got {c_sum['cell_index']}, expected {spec['cell_index']}"
            )
        got_fp = str(c_sum.get("fingerprint", ""))
        if (strict_fingerprint or got_fp != "") and got_fp != str(spec["fingerprint"]):
            raise ValueError(
                f"Diagnostic cell '{c_name}' fingerprint mismatch: got '{got_fp}', expected '{spec['fingerprint']}'"
            )

        r_ver = _require_strict_int(c_sum.get("replicates_verified"), f"{c_name}.replicates_verified")
        validate_and_recompute_cell_summary_metrics(c_sum, expected_r=r_ver)
        slot_degen = {
            name: _validate_rate(
                c_sum["slots"][name]["degeneracy_rate"], r_ver, f"{c_name}.slots.{name}.degeneracy_rate"
            )[0]
            for name in NAMES_A
        }
        max_degen = max(slot_degen.values())
        thresh = _require_finite_float(spec["max_degeneracy_threshold"], f"{c_name}.max_degeneracy_threshold")
        warning = max_degen > thresh
        results.append({
            "gate_id": spec["gate_id"],
            "cell_name": c_name,
            "cell_index": int(c_sum["cell_index"]),
            "fingerprint": got_fp,
            "max_degeneracy_rate": max_degen,
            "max_degeneracy_threshold": thresh,
            "slot_degeneracy_rates": slot_degen,
            "boundary_degeneracy_warning": warning,
            "passed": not warning,
        })
    return results


def evaluate_confirmation_eligibility(
    cell_summaries: List[dict],
    power_ref_evals: List[dict],
    boundary_evals: List[dict],
    expected_validation_cells: int = 88,
) -> Dict[str, Any]:
    """Evaluate single-bank validation diagnostics while keeping confirmation bank unconditionally hard-disabled."""
    n_total = len(cell_summaries)
    n_passed_9875 = sum(
        1
        for c in cell_summaries
        if validate_and_recompute_cell_summary_metrics(
            c, expected_r=_require_strict_int(c.get("replicates_verified"), "replicates_verified")
        )["cell_passed"]
    )

    complete_88 = (n_total == expected_validation_cells)
    all_88_passed = complete_88 and (n_passed_9875 == expected_validation_cells)

    complete_8_refs = len(power_ref_evals) == len(MAIN_POWER_REFERENCE_CELLS)
    all_hist_8_sufficient = bool(
        complete_8_refs and all(p["status"] == "sufficient" for p in power_ref_evals)
    )
    discrete_4_refs = [p for p in power_ref_evals if p.get("in_step5b_p_gate", False)]
    all_discrete_4_refs_sufficient = bool(
        len(discrete_4_refs) == 4 and all(p["status"] == "sufficient" for p in discrete_4_refs)
    )

    complete_5_diag = len(boundary_evals) == len(PINNED_BOUNDARY_DIAGNOSTIC_CELLS)
    all_5_diag_no_warning = bool(
        complete_5_diag and all(not b["boundary_degeneracy_warning"] for b in boundary_evals)
    )
    emp_entries = [b for b in boundary_evals if b["cell_name"] == "empirical-observed"]
    emp_no_warning = bool(
        complete_5_diag and len(emp_entries) == 1 and (not emp_entries[0]["boundary_degeneracy_warning"])
    )

    historical_p16_4_5_3of4_passed = bool(all_88_passed and all_hist_8_sufficient and emp_no_warning)

    # Confirmation bank is unconditionally hard-disabled throughout Step 5b (brief.md §5(3))
    c_approval_verified = False
    confirmation_eligible = bool(
        historical_p16_4_5_3of4_passed
        and c_approval_verified
        and (not CONFIRMATION_BANK_HARD_DISABLED)
    )

    return {
        "complete_88_cells": complete_88,
        "all_88_passed_9875": all_88_passed,
        "all_power_reference_sufficient": all_hist_8_sufficient,
        "all_historical_block3_discrete_4_sufficient": all_discrete_4_refs_sufficient,
        "all_5_boundary_diagnostics_passed": all_5_diag_no_warning,
        "empirical_observed_no_warning": emp_no_warning,
        "statistical_gates_3of4_passed": historical_p16_4_5_3of4_passed,
        "reviewer_c_confirmation_receipt_verified": c_approval_verified,
        "confirmation_bank_hard_disabled": CONFIRMATION_BANK_HARD_DISABLED,
        "confirmation_status": "confirmation_not_run",
        "confirmation_bank_eligible": confirmation_eligible,
    }


def verify_cell_binding(
    bank_summary: Dict[str, Any],
    expected_bank: str,
    expected_cell_name: str,
    expected_cell_index: int,
    expected_fingerprint: str,
    expected_total_cells: Optional[int] = None,
) -> Dict[str, Any]:
    """Fail-closed cell lookup strictly binding (bank, bank_id, production R/B/n_ac/n_bd, cell_name,
    cell_index, fingerprint, and full cell metric integrity).

    Raises KeyError on missing structure/cell_name and ValueError on any bank/index/fingerprint/metric mismatch.
    """
    if not isinstance(bank_summary, dict):
        raise ValueError("bank_summary must be a dictionary")
    _assert_not_confirmation_bank(expected_bank, SEEDS.get(expected_bank, -1))
    if expected_bank not in ("validation", "power_grid"):
        raise ValueError(f"Unsupported expected_bank '{expected_bank}'")

    got_bank = bank_summary.get("bank")
    got_bank_id = _require_strict_int(bank_summary.get("bank_id", -1), f"{expected_bank}.bank_id")
    if got_bank != expected_bank or got_bank_id != int(SEEDS[expected_bank]):
        raise ValueError(
            f"Bank binding mismatch: got ({got_bank!r}, {got_bank_id}), "
            f"expected ({expected_bank!r}, {SEEDS[expected_bank]})"
        )

    expected_r = _require_strict_int(bank_summary.get("replicates", -1), f"{expected_bank}.replicates")
    if expected_r != LOCKED_PRODUCTION_REPLICATES:
        raise ValueError(
            f"Production replicates mismatch on {expected_bank}: got {expected_r}, expected {LOCKED_PRODUCTION_REPLICATES}"
        )
    if "bootstrap_replicates" in bank_summary:
        got_b = _require_strict_int(bank_summary["bootstrap_replicates"], f"{expected_bank}.bootstrap_replicates")
        if got_b != LOCKED_PRODUCTION_BOOTSTRAP_REPLICATES:
            raise ValueError(
                f"Production bootstrap_replicates mismatch on {expected_bank}: got {got_b}, expected {LOCKED_PRODUCTION_BOOTSTRAP_REPLICATES}"
            )
    if "n_ac" in bank_summary:
        if _require_strict_int(bank_summary["n_ac"], f"{expected_bank}.n_ac") != LOCKED_PRODUCTION_N_AC:
            raise ValueError(f"Production n_ac mismatch on {expected_bank}")
    if "n_bd" in bank_summary:
        if _require_strict_int(bank_summary["n_bd"], f"{expected_bank}.n_bd") != LOCKED_PRODUCTION_N_BD:
            raise ValueError(f"Production n_bd mismatch on {expected_bank}")

    if "cell_summaries" not in bank_summary or not isinstance(bank_summary["cell_summaries"], list):
        raise KeyError(f"Missing 'cell_summaries' list in {expected_bank} summary")

    cells = bank_summary["cell_summaries"]
    req_total = expected_total_cells if expected_total_cells is not None else (88 if expected_bank == "validation" else 56)
    if len(cells) != req_total:
        raise ValueError(
            f"Incomplete {expected_bank} cell_summaries: got {len(cells)} cells, expected {req_total}"
        )

    by_name: Dict[str, dict] = {}
    for pos, c in enumerate(cells):
        if "cell_name" not in c or "cell_index" not in c or "fingerprint" not in c:
            raise KeyError(f"Cell entry at position {pos} in {expected_bank} missing required identity keys")
        if _require_strict_int(c["cell_index"], f"{expected_bank}[{pos}].cell_index") != pos:
            raise ValueError(
                f"Non-contiguous cell_index in {expected_bank} at position {pos}: got {c['cell_index']}"
            )
        cname = str(c["cell_name"])
        if cname in by_name:
            raise ValueError(f"Duplicate cell_name '{cname}' in {expected_bank} cell_summaries")
        by_name[cname] = c

    if expected_cell_name not in by_name:
        raise KeyError(
            f"Required locked gate cell '{expected_cell_name}' missing from bank '{expected_bank}'"
        )

    target = by_name[expected_cell_name]
    if _require_strict_int(target["cell_index"], f"{expected_cell_name}.cell_index") != int(expected_cell_index):
        raise ValueError(
            f"Locked gate cell '{expected_cell_name}' in '{expected_bank}' has cell_index={target['cell_index']}, "
            f"expected {expected_cell_index}"
        )
    if str(target.get("fingerprint", "")) != str(expected_fingerprint):
        raise ValueError(
            f"Locked gate cell '{expected_cell_name}' (#{expected_cell_index}) fingerprint mismatch: "
            f"got '{target.get('fingerprint')}', expected '{expected_fingerprint}'"
        )

    validate_and_recompute_cell_summary_metrics(target, expected_r=expected_r)
    return target


def evaluate_step5b_c_gate(
    validation_summary: Dict[str, Any],
    expected_cells: int = 88,
    validation_manifest_path: Path = DEFAULT_VALIDATION_MANIFEST,
    validation_populations_path: Path = DEFAULT_VALIDATION_POPULATIONS,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Evaluate Gate C_j: 88/88 cells in `validation` (bank 2026110101) bound against sealed identity
    & manifest-88.json pass all 6 metric-recomputed main 98.75% criteria.
    """
    manifest_cells, _ = verify_bank_summary_against_sealed_identity(
        bank_summary=validation_summary,
        expected_bank="validation",
        expected_cells=expected_cells,
        manifest_path=validation_manifest_path,
        populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    cells = validation_summary["cell_summaries"]
    n_passed = 0
    failed_cells = []
    for c, m_spec in zip(cells, manifest_cells):
        re_chk = validate_and_recompute_cell_summary_metrics(
            cell=c,
            expected_r=LOCKED_PRODUCTION_REPLICATES,
            manifest_cell=m_spec,
        )
        if re_chk["cell_passed"]:
            n_passed += 1
        else:
            bad = [k.replace("_passed", "") for k, v in re_chk.items() if k != "cell_passed" and not v]
            failed_cells.append({
                "cell_index": int(c["cell_index"]),
                "cell_name": str(c["cell_name"]),
                "failed_checks": bad,
                "fwer": float(c["fwer"]["rate"]),
                "family_direction_error": float(c["family_direction_error"]["rate"]),
                "simultaneous_coverage_9875": float(c["simultaneous_coverage_9875"]["rate"]),
            })

    return {
        "gate": "C_j",
        "passed": bool(n_passed == expected_cells),
        "cells_passed_9875": n_passed,
        "expected_cells": expected_cells,
        "failed_cells": failed_cells,
    }


def evaluate_step5b_d_gate(
    validation_summary: Dict[str, Any],
    specs: List[dict] = PINNED_BOUNDARY_DIAGNOSTIC_SPECS,
    expected_validation_cells: int = 88,
    validation_manifest_path: Path = DEFAULT_VALIDATION_MANIFEST,
    validation_populations_path: Path = DEFAULT_VALIDATION_POPULATIONS,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Evaluate Gate D_j: all 5 locked boundary diagnostic cells (#65, #66, #67, #68, #83) have finite
    validated max degeneracy <= 0.20 under sealed validation identity.
    """
    if len(specs) != 5:
        raise ValueError(f"Gate D_j requires exact 5 diagnostic specs, got {len(specs)}")

    verify_bank_summary_against_sealed_identity(
        bank_summary=validation_summary,
        expected_bank="validation",
        expected_cells=expected_validation_cells,
        manifest_path=validation_manifest_path,
        populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    items = []
    for spec in specs:
        cell = verify_cell_binding(
            bank_summary=validation_summary,
            expected_bank=spec["bank"],
            expected_cell_name=spec["cell_name"],
            expected_cell_index=int(spec["cell_index"]),
            expected_fingerprint=spec["fingerprint"],
            expected_total_cells=expected_validation_cells,
        )
        slot_degen = {}
        for s_name in NAMES_A:
            if s_name not in cell.get("slots", {}) or "degeneracy_rate" not in cell["slots"][s_name]:
                raise KeyError(f"Cell '{spec['cell_name']}' missing slots.{s_name}.degeneracy_rate")
            deg_val, _ = _validate_rate(
                cell["slots"][s_name]["degeneracy_rate"],
                LOCKED_PRODUCTION_REPLICATES,
                f"{spec['cell_name']}.slots.{s_name}.degeneracy_rate",
            )
            slot_degen[s_name] = deg_val

        max_deg = max(slot_degen.values())
        thresh = _require_finite_float(spec["max_degeneracy_threshold"], f"{spec['gate_id']}.threshold")
        if thresh < 0.0 or thresh > 1.0:
            raise ValueError(f"Invalid degeneracy threshold {thresh}")
        item_passed = bool(math.isfinite(max_deg) and max_deg <= thresh)
        items.append({
            "gate_id": str(spec["gate_id"]),
            "bank": str(spec["bank"]),
            "cell_name": str(spec["cell_name"]),
            "cell_index": int(spec["cell_index"]),
            "fingerprint": str(spec["fingerprint"]),
            "max_degeneracy_rate": max_deg,
            "max_degeneracy_threshold": thresh,
            "slot_degeneracy_rates": slot_degen,
            "passed": item_passed,
        })

    n_passed = sum(1 for it in items if it["passed"])
    return {
        "gate": "D_j",
        "passed": bool(n_passed == len(items)),
        "n_passed": n_passed,
        "n_items": len(items),
        "items": items,
    }


def _extract_power_metric(
    cell: Dict[str, Any],
    metric_kind: str,
    target: str,
    r_reps: int = LOCKED_PRODUCTION_REPLICATES,
) -> tuple[float, float]:
    c_name = str(cell.get("cell_name", "<unknown>"))
    if metric_kind == "slot_correct_direction":
        if target not in NAMES_A:
            raise ValueError(f"Invalid slot target '{target}'")
        if target not in cell.get("slots", {}):
            raise KeyError(f"Cell '{c_name}' missing slot '{target}'")
        s_obj = cell["slots"][target]
        rate, mcse, _ = _validate_rate_and_mcse(
            s_obj.get("correct_direction_rate"),
            s_obj.get("correct_direction_mcse"),
            r_reps,
            f"{c_name}.slots.{target}.correct_direction",
        )
        return rate, mcse
    if metric_kind == "all4_correct_direction":
        if target != "all4":
            raise ValueError(f"Expected target='all4' for all4_correct_direction, got '{target}'")
        jd = cell.get("joint_detection", {}).get("all4_correct_direction")
        if not isinstance(jd, dict):
            raise KeyError(f"Cell '{c_name}' missing joint_detection.all4_correct_direction")
        rate, mcse, _ = _validate_rate_mcse_obj(jd, r_reps, f"{c_name}.joint_detection.all4_correct_direction")
        return rate, mcse
    raise ValueError(f"Unsupported metric_kind '{metric_kind}'")


def evaluate_step5b_p_gate(
    validation_summary: Dict[str, Any],
    power_grid_summary: Dict[str, Any],
    specs: List[dict] = STEP5B_POWER_GATE_SPECS,
    expected_validation_cells: int = 88,
    expected_power_grid_cells: int = 56,
    percentile_validation_summary: Optional[Dict[str, Any]] = None,
    percentile_power_grid_summary: Optional[Dict[str, Any]] = None,
    validation_manifest_path: Path = DEFAULT_VALIDATION_MANIFEST,
    validation_populations_path: Path = DEFAULT_VALIDATION_POPULATIONS,
    power_grid_manifest_path: Path = DEFAULT_POWER_GRID_MANIFEST,
    power_grid_populations_path: Path = DEFAULT_POWER_GRID_POPULATIONS,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Evaluate Gate P_j: 17 pre-registered power adequacy items (`rate - 2*MCSE >= 0.80`) with
    fail-closed sealed identity, manifest cell binding, and binomial MCSE verification.
    """
    if len(specs) != 17:
        raise ValueError(f"Gate P_j requires exact 17 pre-registered items, got {len(specs)}")
    if validation_summary.get("method") != power_grid_summary.get("method"):
        raise ValueError(
            f"Method mismatch between validation ({validation_summary.get('method')!r}) "
            f"and power_grid ({power_grid_summary.get('method')!r})"
        )

    verify_bank_summary_against_sealed_identity(
        bank_summary=validation_summary,
        expected_bank="validation",
        expected_cells=expected_validation_cells,
        manifest_path=validation_manifest_path,
        populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    verify_bank_summary_against_sealed_identity(
        bank_summary=power_grid_summary,
        expected_bank="power_grid",
        expected_cells=expected_power_grid_cells,
        manifest_path=power_grid_manifest_path,
        populations_path=power_grid_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    has_pct_ref = (percentile_validation_summary is not None) or (percentile_power_grid_summary is not None)
    if has_pct_ref and (percentile_validation_summary is None or percentile_power_grid_summary is None):
        raise ValueError("Both percentile_validation_summary and percentile_power_grid_summary must be provided together")
    if has_pct_ref:
        assert percentile_validation_summary is not None and percentile_power_grid_summary is not None
        verify_bank_summary_against_sealed_identity(
            bank_summary=percentile_validation_summary,
            expected_bank="validation",
            expected_cells=expected_validation_cells,
            expected_method="percentile",
            manifest_path=validation_manifest_path,
            populations_path=validation_populations_path,
            sealed_identity_path=sealed_identity_path,
            exact_tango_npz_path=exact_tango_npz_path,
        )
        verify_bank_summary_against_sealed_identity(
            bank_summary=percentile_power_grid_summary,
            expected_bank="power_grid",
            expected_cells=expected_power_grid_cells,
            expected_method="percentile",
            manifest_path=power_grid_manifest_path,
            populations_path=power_grid_populations_path,
            sealed_identity_path=sealed_identity_path,
            exact_tango_npz_path=exact_tango_npz_path,
        )

    bank_map = {
        "validation": (validation_summary, expected_validation_cells),
        "power_grid": (power_grid_summary, expected_power_grid_cells),
    }
    pct_bank_map = (
        {
            "validation": (percentile_validation_summary, expected_validation_cells),
            "power_grid": (percentile_power_grid_summary, expected_power_grid_cells),
        }
        if has_pct_ref
        else None
    )

    items = []
    by_group: Dict[str, Dict[str, Any]] = {}

    for spec in specs:
        b_name = str(spec["bank"])
        if b_name not in bank_map:
            raise ValueError(f"Unsupported bank '{b_name}' in P_j spec '{spec.get('item_id')}'")
        b_sum, exp_tot = bank_map[b_name]
        cell = verify_cell_binding(
            bank_summary=b_sum,
            expected_bank=b_name,
            expected_cell_name=str(spec["cell_name"]),
            expected_cell_index=int(spec["cell_index"]),
            expected_fingerprint=str(spec["fingerprint"]),
            expected_total_cells=exp_tot,
        )
        rate, mcse = _extract_power_metric(
            cell, str(spec["metric_kind"]), str(spec["target"]), r_reps=LOCKED_PRODUCTION_REPLICATES
        )
        lower_2mcse = rate - 2.0 * mcse
        upper_2mcse = rate + 2.0 * mcse
        status = classify_power_80(rate, mcse)
        item_passed = bool(lower_2mcse >= 0.80 and status == "sufficient")

        entry: Dict[str, Any] = {
            "item_id": str(spec["item_id"]),
            "group": int(spec["group"]),
            "group_name": str(spec["group_name"]),
            "bank": b_name,
            "cell_name": str(spec["cell_name"]),
            "cell_index": int(spec["cell_index"]),
            "fingerprint": str(spec["fingerprint"]),
            "metric_kind": str(spec["metric_kind"]),
            "target": str(spec["target"]),
            "rate": rate,
            "mcse": mcse,
            "lower_2mcse": lower_2mcse,
            "ci_95": [lower_2mcse, upper_2mcse],
            "status": status,
            "passed": item_passed,
        }

        if pct_bank_map is not None:
            pct_sum, pct_tot = pct_bank_map[b_name]
            assert pct_sum is not None
            pct_cell = verify_cell_binding(
                bank_summary=pct_sum,
                expected_bank=b_name,
                expected_cell_name=str(spec["cell_name"]),
                expected_cell_index=int(spec["cell_index"]),
                expected_fingerprint=str(spec["fingerprint"]),
                expected_total_cells=pct_tot,
            )
            p_rate, p_mcse = _extract_power_metric(
                pct_cell, str(spec["metric_kind"]), str(spec["target"]), r_reps=LOCKED_PRODUCTION_REPLICATES
            )
            entry["shared_stream_percentile_rate"] = p_rate
            entry["shared_stream_percentile_mcse"] = p_mcse
            entry["shared_stream_percentile_status"] = classify_power_80(p_rate, p_mcse)
            entry["delta_vs_shared_stream_percentile"] = rate - p_rate

        items.append(entry)
        g_key = f"group_{spec['group']}_{spec['group_name']}"
        g_rec = by_group.setdefault(g_key, {"group": int(spec["group"]), "group_name": str(spec["group_name"]), "n_items": 0, "n_passed": 0})
        g_rec["n_items"] += 1
        if item_passed:
            g_rec["n_passed"] += 1

    for g_rec in by_group.values():
        g_rec["passed"] = bool(g_rec["n_passed"] == g_rec["n_items"])

    n_passed = sum(1 for it in items if it["passed"])
    return {
        "gate": "P_j",
        "passed": bool(n_passed == len(items)),
        "n_passed": n_passed,
        "n_items": len(items),
        "by_group": by_group,
        "items": items,
    }


def evaluate_historical_block3_comparison(
    validation_summary: Dict[str, Any],
    percentile_validation_summary: Optional[Dict[str, Any]] = None,
    expected_validation_cells: int = 88,
    validation_manifest_path: Path = DEFAULT_VALIDATION_MANIFEST,
    validation_populations_path: Path = DEFAULT_VALIDATION_POPULATIONS,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> List[dict]:
    """Report all 8 historical Block 3 reference cells alongside shared-stream `percentile` (`brief.md` §4.3)."""
    manifest_cells, _ = verify_bank_summary_against_sealed_identity(
        bank_summary=validation_summary,
        expected_bank="validation",
        expected_cells=expected_validation_cells,
        manifest_path=validation_manifest_path,
        populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    manifest_by_name = {str(m["cell_name"]): m for m in manifest_cells}
    if percentile_validation_summary is not None:
        verify_bank_summary_against_sealed_identity(
            bank_summary=percentile_validation_summary,
            expected_bank="validation",
            expected_cells=expected_validation_cells,
            expected_method="percentile",
            manifest_path=validation_manifest_path,
            populations_path=validation_populations_path,
            sealed_identity_path=sealed_identity_path,
            exact_tango_npz_path=exact_tango_npz_path,
        )

    out = []
    for ref in HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS:
        cname = ref["cell_name"]
        cidx = int(ref["cell_index"])
        slot = ref["slot"]
        if cname not in manifest_by_name:
            raise KeyError(f"Missing historical Block 3 cell '{cname}' in manifest")
        exp_fp = str(manifest_by_name[cname]["fingerprint"])
        c = verify_cell_binding(
            validation_summary,
            expected_bank="validation",
            expected_cell_name=cname,
            expected_cell_index=cidx,
            expected_fingerprint=exp_fp,
            expected_total_cells=expected_validation_cells,
        )
        pwr, mcse = _extract_power_metric(c, "slot_correct_direction", slot, r_reps=LOCKED_PRODUCTION_REPLICATES)
        row: Dict[str, Any] = {
            "cell_name": cname,
            "cell_index": cidx,
            "fingerprint": exp_fp,
            "slot": slot,
            "target_effect": ref["effect"],
            "in_step5b_p_gate": bool(ref["in_step5b_p_gate"]),
            "power": pwr,
            "mcse": mcse,
            "ci_95": [pwr - 2.0 * mcse, pwr + 2.0 * mcse],
            "status": classify_power_80(pwr, mcse),
        }
        if percentile_validation_summary is not None:
            pc = verify_cell_binding(
                percentile_validation_summary,
                expected_bank="validation",
                expected_cell_name=cname,
                expected_cell_index=cidx,
                expected_fingerprint=exp_fp,
                expected_total_cells=expected_validation_cells,
            )
            p_pwr, p_mcse = _extract_power_metric(
                pc, "slot_correct_direction", slot, r_reps=LOCKED_PRODUCTION_REPLICATES
            )
            row["shared_stream_percentile_power"] = p_pwr
            row["shared_stream_percentile_mcse"] = p_mcse
            row["shared_stream_percentile_status"] = classify_power_80(p_pwr, p_mcse)
            row["delta_vs_shared_stream_percentile"] = pwr - p_pwr
        out.append(row)
    return out


def evaluate_single_candidate_gates(
    method_name: str,
    validation_summary: Dict[str, Any],
    power_grid_summary: Dict[str, Any],
    expected_validation_cells: int = 88,
    expected_power_grid_cells: int = 56,
    percentile_validation_summary: Optional[Dict[str, Any]] = None,
    percentile_power_grid_summary: Optional[Dict[str, Any]] = None,
    validation_manifest_path: Path = DEFAULT_VALIDATION_MANIFEST,
    validation_populations_path: Path = DEFAULT_VALIDATION_POPULATIONS,
    power_grid_manifest_path: Path = DEFAULT_POWER_GRID_MANIFEST,
    power_grid_populations_path: Path = DEFAULT_POWER_GRID_POPULATIONS,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Evaluate complete eligibility predicate `E_j = C_j and D_j and P_j` for a single method."""
    verify_bank_summary_against_sealed_identity(
        bank_summary=validation_summary,
        expected_bank="validation",
        expected_cells=expected_validation_cells,
        expected_method=method_name,
        manifest_path=validation_manifest_path,
        populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    verify_bank_summary_against_sealed_identity(
        bank_summary=power_grid_summary,
        expected_bank="power_grid",
        expected_cells=expected_power_grid_cells,
        expected_method=method_name,
        manifest_path=power_grid_manifest_path,
        populations_path=power_grid_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    c_gate = evaluate_step5b_c_gate(
        validation_summary,
        expected_cells=expected_validation_cells,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    d_gate = evaluate_step5b_d_gate(
        validation_summary,
        expected_validation_cells=expected_validation_cells,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    p_gate = evaluate_step5b_p_gate(
        validation_summary=validation_summary,
        power_grid_summary=power_grid_summary,
        expected_validation_cells=expected_validation_cells,
        expected_power_grid_cells=expected_power_grid_cells,
        percentile_validation_summary=percentile_validation_summary,
        percentile_power_grid_summary=percentile_power_grid_summary,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        power_grid_manifest_path=power_grid_manifest_path,
        power_grid_populations_path=power_grid_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    hist_block3 = evaluate_historical_block3_comparison(
        validation_summary=validation_summary,
        percentile_validation_summary=percentile_validation_summary,
        expected_validation_cells=expected_validation_cells,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    eligible = bool(c_gate["passed"] and d_gate["passed"] and p_gate["passed"])
    return {
        "method": method_name,
        "eligible": eligible,
        "C_j": c_gate,
        "D_j": d_gate,
        "P_j": p_gate,
        "historical_block3_power_reference_8": hist_block3,
    }


def select_method_from_booleans(
    e1_hybrid_pct_tango: bool,
    e2_hybrid_bessel_t_tango: bool,
) -> Dict[str, Any]:
    """Deterministic 4-branch truth-table selection rule (`brief.md` §3.2(4)).

    Covers all 4 values of `(E_1, E_2) in {True, False}^2`:
    - Branch 1 `(True, True)`  -> `"hybrid_pct_tango"`
    - Branch 2 `(True, False)` -> `"hybrid_pct_tango"`
    - Branch 3 `(False, True)` -> `"hybrid_bessel_t_tango"`
    - Branch 4 `(False, False)`-> `None` (no threshold relaxation permitted; stop and report to user)
    """
    if not isinstance(e1_hybrid_pct_tango, bool) or not isinstance(e2_hybrid_bessel_t_tango, bool):
        raise TypeError("e1_hybrid_pct_tango and e2_hybrid_bessel_t_tango must be strict booleans")

    if e1_hybrid_pct_tango and e2_hybrid_bessel_t_tango:
        return {
            "branch_id": 1,
            "truth_pair": [True, True],
            "E_1_hybrid_pct_tango": True,
            "E_2_hybrid_bessel_t_tango": True,
            "recommended_method": "hybrid_pct_tango",
            "rationale": "Both pre-registered hybrid candidates passed E_j = C_j and D_j and P_j; rank-1 primary candidate hybrid_pct_tango selected without extra tuning.",
        }
    if e1_hybrid_pct_tango and (not e2_hybrid_bessel_t_tango):
        return {
            "branch_id": 2,
            "truth_pair": [True, False],
            "E_1_hybrid_pct_tango": True,
            "E_2_hybrid_bessel_t_tango": False,
            "recommended_method": "hybrid_pct_tango",
            "rationale": "Rank-1 primary candidate hybrid_pct_tango passed E_1 = True while rank-2 candidate failed E_2 = False; hybrid_pct_tango selected.",
        }
    if (not e1_hybrid_pct_tango) and e2_hybrid_bessel_t_tango:
        return {
            "branch_id": 3,
            "truth_pair": [False, True],
            "E_1_hybrid_pct_tango": False,
            "E_2_hybrid_bessel_t_tango": True,
            "recommended_method": "hybrid_bessel_t_tango",
            "rationale": "Rank-1 candidate failed E_1 = False while pre-registered rank-2 candidate hybrid_bessel_t_tango passed E_2 = True; hybrid_bessel_t_tango selected.",
        }
    return {
        "branch_id": 4,
        "truth_pair": [False, False],
        "E_1_hybrid_pct_tango": False,
        "E_2_hybrid_bessel_t_tango": False,
        "recommended_method": None,
        "rationale": "Neither hybrid candidate satisfied E_j = C_j and D_j and P_j; zero threshold relaxation enforced, recommended_method = None, stopping for user adjudication.",
    }


def evaluate_step5b_candidate_selection(
    cand1_validation: Dict[str, Any],
    cand1_power_grid: Dict[str, Any],
    cand2_validation: Dict[str, Any],
    cand2_power_grid: Dict[str, Any],
    pct_validation: Dict[str, Any],
    pct_power_grid: Dict[str, Any],
    expected_validation_cells: int = 88,
    expected_power_grid_cells: int = 56,
    validation_manifest_path: Path = DEFAULT_VALIDATION_MANIFEST,
    validation_populations_path: Path = DEFAULT_VALIDATION_POPULATIONS,
    power_grid_manifest_path: Path = DEFAULT_POWER_GRID_MANIFEST,
    power_grid_populations_path: Path = DEFAULT_POWER_GRID_POPULATIONS,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Evaluate all 3 shared-stream methods on `validation` + `power_grid` under live sealed identity,
    fixed production specs (`R=2000, B=5000, n_ac=80, n_bd=80`), full 88+56 cell manifest binding,
    and metric-level screening recomputation, then execute deterministic Step 5b selection.
    """
    if expected_validation_cells != 88 or expected_power_grid_cells != 56:
        raise ValueError(
            f"Locked production cell counts require (88, 56), got ({expected_validation_cells}, {expected_power_grid_cells})"
        )

    all_summaries = [
        ("hybrid_pct_tango", "validation", cand1_validation, 88, validation_manifest_path, validation_populations_path),
        ("hybrid_pct_tango", "power_grid", cand1_power_grid, 56, power_grid_manifest_path, power_grid_populations_path),
        ("hybrid_bessel_t_tango", "validation", cand2_validation, 88, validation_manifest_path, validation_populations_path),
        ("hybrid_bessel_t_tango", "power_grid", cand2_power_grid, 56, power_grid_manifest_path, power_grid_populations_path),
        ("percentile", "validation", pct_validation, 88, validation_manifest_path, validation_populations_path),
        ("percentile", "power_grid", pct_power_grid, 56, power_grid_manifest_path, power_grid_populations_path),
    ]
    verified_gates_by_bank: Dict[str, Dict[str, str]] = {}
    for m_exp, b_exp, s_obj, exp_cnt, m_p, p_p in all_summaries:
        _, v_gates = verify_bank_summary_against_sealed_identity(
            bank_summary=s_obj,
            expected_bank=b_exp,
            expected_cells=exp_cnt,
            expected_method=m_exp,
            manifest_path=m_p,
            populations_path=p_p,
            sealed_identity_path=sealed_identity_path,
            exact_tango_npz_path=exact_tango_npz_path,
            expected_replicates=LOCKED_PRODUCTION_REPLICATES,
            expected_bootstrap_replicates=LOCKED_PRODUCTION_BOOTSTRAP_REPLICATES,
            expected_n_ac=LOCKED_PRODUCTION_N_AC,
            expected_n_bd=LOCKED_PRODUCTION_N_BD,
        )
        verified_gates_by_bank[b_exp] = v_gates

    eval_cand1 = evaluate_single_candidate_gates(
        method_name="hybrid_pct_tango",
        validation_summary=cand1_validation,
        power_grid_summary=cand1_power_grid,
        expected_validation_cells=expected_validation_cells,
        expected_power_grid_cells=expected_power_grid_cells,
        percentile_validation_summary=pct_validation,
        percentile_power_grid_summary=pct_power_grid,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        power_grid_manifest_path=power_grid_manifest_path,
        power_grid_populations_path=power_grid_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    eval_cand2 = evaluate_single_candidate_gates(
        method_name="hybrid_bessel_t_tango",
        validation_summary=cand2_validation,
        power_grid_summary=cand2_power_grid,
        expected_validation_cells=expected_validation_cells,
        expected_power_grid_cells=expected_power_grid_cells,
        percentile_validation_summary=pct_validation,
        percentile_power_grid_summary=pct_power_grid,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        power_grid_manifest_path=power_grid_manifest_path,
        power_grid_populations_path=power_grid_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )
    eval_pct_baseline = evaluate_single_candidate_gates(
        method_name="percentile",
        validation_summary=pct_validation,
        power_grid_summary=pct_power_grid,
        expected_validation_cells=expected_validation_cells,
        expected_power_grid_cells=expected_power_grid_cells,
        percentile_validation_summary=pct_validation,
        percentile_power_grid_summary=pct_power_grid,
        validation_manifest_path=validation_manifest_path,
        validation_populations_path=validation_populations_path,
        power_grid_manifest_path=power_grid_manifest_path,
        power_grid_populations_path=power_grid_populations_path,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
    )

    decision = select_method_from_booleans(
        e1_hybrid_pct_tango=eval_cand1["eligible"],
        e2_hybrid_bessel_t_tango=eval_cand2["eligible"],
    )

    return {
        "schema_version": "step5b-candidate-selection-v1",
        "replicates": LOCKED_PRODUCTION_REPLICATES,
        "bootstrap_replicates": LOCKED_PRODUCTION_BOOTSTRAP_REPLICATES,
        "n_ac": LOCKED_PRODUCTION_N_AC,
        "n_bd": LOCKED_PRODUCTION_N_BD,
        "sealed_identity_verified": True,
        "verified_integrity_gates": verified_gates_by_bank,
        "seed_banks": {
            "validation": SEEDS["validation"],
            "power_grid": SEEDS["power_grid"],
            "confirmation_reserved_hard_disabled": SEEDS["confirmation"],
            "pilot_reference": SEEDS["pilot"],
        },
        "s5_frozen": False,
        "confirmation_bank_hard_disabled": CONFIRMATION_BANK_HARD_DISABLED,
        "confirmation_status": "confirmation_not_run",
        "selection_decision": decision,
        "candidates": {
            "hybrid_pct_tango": eval_cand1,
            "hybrid_bessel_t_tango": eval_cand2,
        },
        "baseline_comparison": {
            "percentile": eval_pct_baseline,
        },
    }


def evaluate_power_grid_sequences(cell_summaries: List[dict]) -> Dict[str, Any]:
    """Summarize each of the 7 sequences in the 56-cell power grid without assuming monotonicity."""
    by_cat: Dict[str, List[dict]] = {}
    for c in cell_summaries:
        cat = c.get("category")
        if cat:
            by_cat.setdefault(cat, []).append(c)

    sequences: Dict[str, Any] = {}
    for seq_name, slot in POWER_SINGLE_SLOT_SEQUENCES:
        items = by_cat.get(seq_name, [])
        if not items:
            continue
        sorted_items = sorted(items, key=lambda c: abs(Fraction(c["truth"][slot])))
        points = []
        for c in sorted_items:
            s_info = c["slots"][slot]
            eff_str = c["truth"][slot]
            eff_frac = Fraction(eff_str)
            pwr = s_info["correct_direction_rate"]
            mcse = s_info["correct_direction_mcse"]
            status = classify_power_80(pwr, mcse)
            points.append({
                "cell_name": c["cell_name"],
                "cell_index": c["cell_index"],
                "fingerprint": c.get("fingerprint", ""),
                "slot": slot,
                "effect": eff_str,
                "effect_float": float(eff_frac),
                "abs_effect_float": float(abs(eff_frac)),
                "power": pwr,
                "mcse": mcse,
                "power_ci_95": [pwr - 2.0 * mcse, pwr + 2.0 * mcse],
                "status": status,
                "degeneracy_rate": s_info["degeneracy_rate"],
                "failure_distinct_boot_rate": s_info["failure_distinct_boot_rate"],
                "failure_observed_se_rate": s_info["failure_observed_se_rate"],
                "failure_bootstrap_se_rate": s_info["failure_bootstrap_se_rate"],
                "failure_studentized_distribution_rate": s_info["failure_studentized_distribution_rate"],
                "failure_ci_rate": s_info["failure_ci_rate"],
                "coverage_9875": s_info["coverage_9875"],
                "nondegenerate_count_9875": s_info["nondegenerate_count_9875"],
                "nondegenerate_conditional_coverage_9875": s_info["nondegenerate_conditional_coverage_9875"],
            })

        suff_indices = [idx for idx, pt in enumerate(points) if pt["status"] == "sufficient"]
        if suff_indices:
            first_idx = suff_indices[0]
            last_idx = suff_indices[-1]
            smallest_suff = points[first_idx]["effect"]
            largest_suff = points[last_idx]["effect"]
            collapse_cells = [
                {
                    "cell_name": pt["cell_name"],
                    "effect": pt["effect"],
                    "power": pt["power"],
                    "status": pt["status"],
                    "degeneracy_rate": pt["degeneracy_rate"],
                }
                for pt in points[first_idx + 1:]
                if pt["status"] != "sufficient"
            ]
            monotone_sufficient_tail = len(collapse_cells) == 0
        else:
            smallest_suff = None
            largest_suff = None
            collapse_cells = []
            monotone_sufficient_tail = False

        monotone_power = all(
            points[k + 1]["power"] + 1e-12 >= points[k]["power"]
            for k in range(len(points) - 1)
        )

        sequences[seq_name] = {
            "slot": slot,
            "n_points": len(points),
            "smallest_tested_sufficient_effect": smallest_suff,
            "largest_tested_sufficient_effect": largest_suff,
            "sufficient_effects": [points[i]["effect"] for i in suff_indices],
            "is_monotone_nondecreasing_power": monotone_power,
            "is_monotone_sufficient_tail": monotone_sufficient_tail,
            "high_effect_collapse_cells": collapse_cells,
            "points": points,
        }

    emp_items = by_cat.get("empirical-convex-mixture", [])
    if emp_items:
        sorted_emp = sorted(emp_items, key=lambda c: abs(Fraction(c["truth"]["SA1"])))
        emp_points = []
        for c in sorted_emp:
            gamma_frac = Fraction(c["truth"]["SA1"]) / Fraction(1, 5)
            slot_entries = {}
            for name in NAMES_A:
                si = c["slots"][name]
                p_val = si["correct_direction_rate"]
                m_val = si["correct_direction_mcse"]
                slot_entries[name] = {
                    "truth": c["truth"][name],
                    "power": p_val,
                    "mcse": m_val,
                    "status": classify_power_80(p_val, m_val),
                    "degeneracy_rate": si["degeneracy_rate"],
                }
            jd = c["joint_detection"]
            all4_p = jd["all4_correct_direction"]["rate"]
            all4_m = jd["all4_correct_direction"]["mcse"]
            cont_p = jd["continuous_sa2_sa3_correct_direction"]["rate"]
            cont_m = jd["continuous_sa2_sa3_correct_direction"]["mcse"]
            emp_points.append({
                "cell_name": c["cell_name"],
                "cell_index": c["cell_index"],
                "fingerprint": c.get("fingerprint", ""),
                "gamma": str(gamma_frac),
                "gamma_float": float(gamma_frac),
                "all4_joint_power": all4_p,
                "all4_joint_mcse": all4_m,
                "all4_joint_status": classify_power_80(all4_p, all4_m),
                "continuous_sa2_sa3_joint_power": cont_p,
                "continuous_sa2_sa3_joint_mcse": cont_m,
                "continuous_sa2_sa3_joint_status": classify_power_80(cont_p, cont_m),
                "slots": slot_entries,
            })

        smallest_gamma_by_slot = {}
        for name in NAMES_A:
            s_g = [pt["gamma"] for pt in emp_points if pt["slots"][name]["status"] == "sufficient"]
            smallest_gamma_by_slot[name] = s_g[0] if s_g else None
        s_all4 = [pt["gamma"] for pt in emp_points if pt["all4_joint_status"] == "sufficient"]
        s_cont = [pt["gamma"] for pt in emp_points if pt["continuous_sa2_sa3_joint_status"] == "sufficient"]

        sequences["empirical-convex-mixture"] = {
            "n_points": len(emp_points),
            "smallest_tested_sufficient_gamma_by_slot": smallest_gamma_by_slot,
            "smallest_tested_sufficient_gamma_all4": s_all4[0] if s_all4 else None,
            "smallest_tested_sufficient_gamma_continuous_sa2_sa3": s_cont[0] if s_cont else None,
            "points": emp_points,
        }

    return sequences


def generate_executive_markdown(
    overall_summary: dict,
    cell_summaries: List[dict],
    power_ref_evals: List[dict],
    boundary_evals: List[dict],
    power_sequences: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate Markdown report summarizing calibration or power-grid results."""
    lines = [
        f"# Scheme A Step 5b Simulation Executive Summary (`{overall_summary['bank']}` / `{overall_summary['method']}`)",
        "",
        f"- **Bank / Seed**: `{overall_summary['bank']}` (`{overall_summary['bank_id']}`)",
        f"- **Method**: `{overall_summary['method']}`",
        f"- **Replicates per Cell**: {overall_summary['replicates']} (`B = {overall_summary['bootstrap_replicates']}`)",
        f"- **Total Cells Evaluated**: {overall_summary['total_cells']}",
        f"- **Cells Passing Main 98.75% Criteria**: {overall_summary['cells_passed_9875']} / {overall_summary['total_cells']}",
        f"- **Cells Passing Historical 99.5% Criteria**: {overall_summary['cells_passed_995']} / {overall_summary['total_cells']}",
        f"- **Confirmation Bank Hard-Disabled**: `{overall_summary['confirmation_bank_hard_disabled']}`",
        f"- **Confirmation Status**: `{overall_summary['confirmation_status']}`",
        "",
    ]

    if overall_summary["bank"] == "validation":
        lines.extend([
            "## 1. Historical Block 3 8-Cell Reference Evaluation",
            "",
            "| Index | Cell Name | Slot | Effect | In Step 5b P_j? | Power | 95% MCSE Interval | Status |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for p in power_ref_evals:
            ci_str = f"[{p['ci_95'][0]:.4f}, {p['ci_95'][1]:.4f}]"
            in_p = "YES" if p.get("in_step5b_p_gate") else "NO (descriptive)"
            lines.append(
                f"| {p['cell_index']} | `{p['cell_name']}` | {p['slot']} | {p['target_effect']} | "
                f"{in_p} | {p['power']:.4f} | {ci_str} | **{p['status']}** |"
            )

        lines.extend([
            "",
            "## 2. Pinned Boundary Degeneracy Gate D_j Monitoring (Threshold: 0.20)",
            "",
            "| Gate ID | Index | Cell Name | Max Degeneracy Rate | SA1 | SA2 | SA3 | SA4 | Passed? |",
            "|---|---|---|---|---|---|---|---|---|",
        ])
        for b in boundary_evals:
            sd = b["slot_degeneracy_rates"]
            p_str = "PASS" if b.get("passed", not b["boundary_degeneracy_warning"]) else "FAIL"
            lines.append(
                f"| `{b.get('gate_id', '-')}` | {b.get('cell_index', '-')} | `{b['cell_name']}` | {b['max_degeneracy_rate']:.4f} | "
                f"{sd['SA1']:.4f} | {sd['SA2']:.4f} | {sd['SA3']:.4f} | {sd['SA4']:.4f} | **{p_str}** |"
            )

    if power_sequences:
        lines.extend([
            "",
            "## Power & Boundary Degeneracy Sequences",
            "",
            "| Sequence | Slot | Smallest Tested Sufficient Effect | Largest Sufficient Effect | Monotone Tail? | High-Effect Collapse Cells |",
            "|---|---|---|---|---|---|",
        ])
        for seq_name, _ in POWER_SINGLE_SLOT_SEQUENCES:
            if seq_name not in power_sequences:
                continue
            sq = power_sequences[seq_name]
            col_str = ", ".join(
                f"{x['effect']} (pwr={x['power']:.3f}, deg={x['degeneracy_rate']:.3f})"
                for x in sq["high_effect_collapse_cells"]
            ) or "None"
            lines.append(
                f"| `{seq_name}` | {sq['slot']} | `{sq['smallest_tested_sufficient_effect']}` | "
                f"`{sq['largest_tested_sufficient_effect']}` | `{sq['is_monotone_sufficient_tail']}` | {col_str} |"
            )

    lines.extend([
        "",
        "## Failed Cells Under Main 98.75% Criteria",
        "",
    ])
    failed_cells = [c for c in cell_summaries if not c["checks_9875"]["cell_passed"]]
    if not failed_cells:
        lines.append("All cells passed the pre-registered 98.75% screening criteria.")
    else:
        lines.extend([
            "| Index | Cell Name | Failed Checks | Max Degen Rate | Simult Cov 98.75% |",
            "|---|---|---|---|---|",
        ])
        for c in failed_cells:
            chk = c["checks_9875"]
            bad = [k.replace("_passed", "") for k, v in chk.items() if k != "cell_passed" and not v]
            max_deg = max(c["slots"][n]["degeneracy_rate"] for n in NAMES_A)
            lines.append(
                f"| {c['cell_index']} | `{c['cell_name']}` | `{', '.join(bad)}` | {max_deg:.4f} | "
                f"{c['simultaneous_coverage_9875']['rate']:.4f} |"
            )

    lines.extend([
        "",
        f"## Complete Cell Screening Table (All {len(cell_summaries)} Cells)",
        "",
        "| Index | Cell Name | FWER | Fam Dir Err | Simult Cov 98.75% | Max Degen | 98.75% Passed? |",
        "|---|---|---|---|---|---|---|",
    ])
    for c in cell_summaries:
        chk = c["checks_9875"]
        pass_str = "PASS" if chk["cell_passed"] else "FAIL"
        max_deg = max(c["slots"][n]["degeneracy_rate"] for n in NAMES_A)
        lines.append(
            f"| {c['cell_index']} | `{c['cell_name']}` | {c['fwer']['rate']:.4f} | "
            f"{c['family_direction_error']['rate']:.4f} | {c['simultaneous_coverage_9875']['rate']:.4f} | "
            f"{max_deg:.4f} | **{pass_str}** |"
        )
    lines.append("")
    return "\n".join(lines)


def summarize_simulation_run(
    manifest_path: Path,
    populations_path: Path,
    runs_dir: Path,
    bank: str,
    method: str,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
    expected_r: int = 2000,
    b_reps: int = 5000,
    n_ac: int = 80,
    n_bd: int = 80,
    source_path: Path = Path(DEFAULT_SOURCE),
    split_path: Path = Path(DEFAULT_SPLIT),
    code_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verify sealed identity + run metadata + all cell chunks, then compute complete summary."""
    _assert_not_confirmation_bank(bank, SEEDS.get(bank, -1))
    if bank not in ("validation", "power_grid"):
        raise ValueError(f"Unsupported summarization bank '{bank}' (expected 'validation' or 'power_grid')")
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported summarization method '{method}' (expected one of {SUPPORTED_METHODS})")

    gates = verify_integrity_gates(
        manifest_path=manifest_path,
        pop_table_path=populations_path,
        bank_name=bank,
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
        source_path=source_path,
        split_path=split_path,
        code_dir=code_dir,
    )
    sealed = json.loads(Path(sealed_identity_path).read_text(encoding="utf-8"))
    expected_cells = int(sealed["matrices"][bank]["expected_cells"])
    bank_id = SEEDS[bank]

    run_meta_path = Path(runs_dir) / "run_metadata.json"
    if not run_meta_path.is_file():
        raise FileNotFoundError(f"Missing run_metadata.json in {runs_dir}")
    run_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))

    if (
        run_meta.get("bank") != bank
        or int(run_meta.get("bank_id", -1)) != bank_id
        or run_meta.get("saved_method") != method
        or int(run_meta.get("reps", -1)) != expected_r
        or int(run_meta.get("b_reps", -1)) != b_reps
        or int(run_meta.get("n_ac", -1)) != n_ac
        or int(run_meta.get("n_bd", -1)) != n_bd
        or int(run_meta.get("cells_executed", -1)) != expected_cells
        or run_meta.get("integrity_verified") is not True
        or run_meta.get("integrity_gates_start") != gates
        or run_meta.get("integrity_gates_end") != gates
    ):
        raise ValueError(f"run_metadata.json identity/configuration mismatch in {runs_dir}")

    manifest_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    pop_table = json.loads(Path(populations_path).read_text(encoding="utf-8"))
    cells = manifest_data["cells"]
    if len(cells) != expected_cells:
        raise ValueError(f"Manifest cell count {len(cells)} != sealed expected_cells {expected_cells}")

    cell_summaries: List[dict] = []
    cell_sum_dict: Dict[str, dict] = {}
    pop_fp_cache: Dict[str, str] = {}
    enforce_domains = method in ALL3_METHODS

    for expected_idx, c in enumerate(cells):
        if int(c["cell_index"]) != expected_idx:
            raise ValueError(f"Non-contiguous cell_index at position {expected_idx}: {c['cell_index']}")
        c_name = c["cell_name"]
        if c_name in cell_sum_dict:
            raise ValueError(f"Duplicate cell_name '{c_name}' in manifest")
        p_name = c["population_name"]
        if p_name not in pop_fp_cache:
            if p_name not in pop_table:
                raise KeyError(f"Missing population '{p_name}' in populations table")
            pop_fp_cache[p_name] = from_table(pop_table[p_name]).fingerprint()
        pop_fp = pop_fp_cache[p_name]
        if pop_fp != c["fingerprint"]:
            raise ValueError(f"Population fingerprint mismatch for '{c_name}': {pop_fp} != {c['fingerprint']}")

        cell_dir = Path(runs_dir) / c_name
        data = load_cell_results(
            cell_dir=cell_dir,
            expected_r=expected_r,
            cell_spec=c,
            pop_fingerprint=pop_fp,
            method=method,
            bank=bank,
            bank_id=bank_id,
            b_reps=b_reps,
            n_ac=n_ac,
            n_bd=n_bd,
            gates=gates,
            strict_identity=True,
        )
        summary = evaluate_cell_summary(
            c,
            data,
            r_reps=expected_r,
            b_reps=b_reps,
            enforce_domains=enforce_domains,
        )
        cell_summaries.append(summary)
        cell_sum_dict[c_name] = summary

    n_total = len(cell_summaries)
    n_passed_9875 = sum(1 for c in cell_summaries if c["checks_9875"]["cell_passed"])
    n_passed_995 = sum(1 for c in cell_summaries if c["checks_995"]["cell_passed"])

    if bank == "validation":
        power_ref_evals = evaluate_main_power_reference_cells(cell_sum_dict, require_all=True)
        boundary_evals = evaluate_boundary_degeneracy_diagnostics(
            cell_sum_dict,
            require_all=True,
            strict_fingerprint=True,
        )
        elig = evaluate_confirmation_eligibility(
            cell_summaries=cell_summaries,
            power_ref_evals=power_ref_evals,
            boundary_evals=boundary_evals,
            expected_validation_cells=expected_cells,
        )
        power_sequences = {}
    else:
        power_ref_evals = []
        boundary_evals = []
        elig = {
            "complete_88_cells": False,
            "all_88_passed_9875": False,
            "all_power_reference_sufficient": False,
            "all_historical_block3_discrete_4_sufficient": False,
            "all_5_boundary_diagnostics_passed": False,
            "empirical_observed_no_warning": False,
            "statistical_gates_3of4_passed": False,
            "reviewer_c_confirmation_receipt_verified": False,
            "confirmation_bank_hard_disabled": CONFIRMATION_BANK_HARD_DISABLED,
            "confirmation_bank_eligible": False,
            "confirmation_status": "not_applicable_power_grid",
        }
        power_sequences = evaluate_power_grid_sequences(cell_summaries)

    return {
        "manifest_path": str(manifest_path),
        "populations_path": str(populations_path),
        "sealed_identity_path": str(sealed_identity_path),
        "exact_tango_npz_path": str(exact_tango_npz_path),
        "runs_dir": str(runs_dir),
        "bank": bank,
        "bank_id": bank_id,
        "method": method,
        "integrity_gates": gates,
        "total_cells": n_total,
        "replicates": expected_r,
        "bootstrap_replicates": b_reps,
        "n_ac": n_ac,
        "n_bd": n_bd,
        "cells_passed_9875": n_passed_9875,
        "cells_passed_995": n_passed_995,
        "all_power_reference_sufficient": elig["all_power_reference_sufficient"],
        "all_historical_block3_discrete_4_sufficient": elig["all_historical_block3_discrete_4_sufficient"],
        "all_5_boundary_diagnostics_passed": elig["all_5_boundary_diagnostics_passed"],
        "empirical_observed_no_warning": elig["empirical_observed_no_warning"],
        "statistical_gates_3of4_passed": elig["statistical_gates_3of4_passed"],
        "confirmation_bank_hard_disabled": elig["confirmation_bank_hard_disabled"],
        "confirmation_bank_eligible": elig["confirmation_bank_eligible"],
        "confirmation_status": elig["confirmation_status"],
        "confirmation_eligibility_details": elig,
        "historical_block3_power_reference_8": power_ref_evals,
        "main_power_reference_evaluations": power_ref_evals,
        "boundary_degeneracy_evaluations": boundary_evals,
        "power_grid_sequences": power_sequences,
        "cell_summaries": cell_summaries,
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize simulation runs for Scheme A Step 5b.")
    parser.add_argument("--bank", choices=["validation", "power_grid"], required=True, help="Matrix bank name")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), required=True, help="Inference method")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON")
    parser.add_argument("--populations", required=True, help="Path to joint populations JSON")
    parser.add_argument("--sealed-identity", default=str(DEFAULT_SEALED_IDENTITY), help="Path to sealed-run-identity.json")
    parser.add_argument("--exact-tango-tables", default=str(DEFAULT_TABLES_NPZ), help="Path to exact-tango-tables.npz")
    parser.add_argument("--runs-dir", required=True, help="Path to directory containing run chunks")
    parser.add_argument("--out-dir", required=True, help="Output directory for summary files")
    parser.add_argument("--out-json", default=None, help="Optional explicit path for summary JSON")
    parser.add_argument("--out-md", default=None, help="Optional explicit path for summary Markdown")
    parser.add_argument("--reps", type=int, default=2000, help="Expected replicates per cell")
    parser.add_argument("--b-reps", type=int, default=5000, help="Expected bootstrap replicates B")
    parser.add_argument("--n-ac", type=int, default=80, help="Expected AC cluster count")
    parser.add_argument("--n-bd", type=int, default=80, help="Expected BD cluster count")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Summarizing {args.bank}/{args.method} runs from {args.runs_dir}...", flush=True)
    overall_summary = summarize_simulation_run(
        manifest_path=Path(args.manifest),
        populations_path=Path(args.populations),
        runs_dir=Path(args.runs_dir),
        bank=args.bank,
        method=args.method,
        sealed_identity_path=Path(args.sealed_identity),
        exact_tango_npz_path=Path(args.exact_tango_tables),
        expected_r=args.reps,
        b_reps=args.b_reps,
        n_ac=args.n_ac,
        n_bd=args.n_bd,
    )

    sum_json_path = Path(args.out_json) if args.out_json else (out_dir / "summary.json")
    sum_md_path = Path(args.out_md) if args.out_md else (out_dir / "summary.md")
    sum_json_path.parent.mkdir(parents=True, exist_ok=True)
    sum_md_path.parent.mkdir(parents=True, exist_ok=True)

    sum_json_path.write_text(json.dumps(overall_summary, indent=2), encoding="utf-8")
    sum_md_path.write_text(
        generate_executive_markdown(
            overall_summary,
            overall_summary["cell_summaries"],
            overall_summary["main_power_reference_evaluations"],
            overall_summary["boundary_degeneracy_evaluations"],
            overall_summary["power_grid_sequences"],
        ),
        encoding="utf-8",
    )
    print(f"Summary written to {sum_json_path} and {sum_md_path}", flush=True)


if __name__ == "__main__":
    main()
