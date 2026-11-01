"""Multi-processing simulation runner for Scheme A Step 5b calibration and power grids.

Enforces:
- Pre-import single-thread BLAS limits (OPENBLAS/OMP/MKL/NUMEXPR/VECLIB_NUM_THREADS=1);
- Combined parent + concurrent workers peak memory monitoring (< 8 GiB guardrail);
- Pre-approved sealed SHA256 identity verification across all 8 SEALED_CORE_MODULES,
  exact-tango-tables.npz (file & payload SHA256 + monotonicity invariants), all 6 Fraction-certified
  left-cut records, input data, and simulation matrices at start, mid-run, and end;
- Shared-stream parallel evaluation (`--method all3`) of `hybrid_pct_tango`, `hybrid_bessel_t_tango`,
  and historical `percentile` on identical outer samples (`purpose = 0`) and bootstrap weights (`purpose = 1`);
- Atomic .npz chunking (chunk_size=200, 10 chunks per cell) with shape/dtype-bound payload SHA256
  and full 22-key entity verification;
- Unconditionally hard-disabled confirmation bank (2026110102) throughout Step 5b (CONFIRMATION_BANK_HARD_DISABLED = True).
"""

import os

# Enforce single-thread BLAS BEFORE importing numpy or any numerical library
SINGLE_THREAD_ENV_VARS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
for _env_k in SINGLE_THREAD_ENV_VARS:
    os.environ[_env_k] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import ctypes
from ctypes import wintypes
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from .core_a import (
        DOMAINS_A,
        bootstrap_a,
        compute_bessel_t_constants_decimal,
        compute_observed_a,
        extract_slot_contrasts,
        infer_hybrid_bessel_t_tango_a,
        infer_hybrid_pct_tango_a,
        infer_percentile_a,
        infer_studentized_a,
        prepare_sorted_boot_stats,
    )
    from .dgp_a import PopulationA, from_table
    from .exact_tango import (
        DEFAULT_TABLES_NPZ,
        certify_all_6_left_cuts,
        load_certified_tango_tables,
        verify_ieee754_rn_and_subnormals,
        verify_sealed_left_cuts,
    )
    from .inputs import DEFAULT_SOURCE, DEFAULT_SPLIT, file_sha256
    from .manifest_a import SEEDS
except (ImportError, ValueError):
    _code_dir = Path(__file__).resolve().parent
    if str(_code_dir) not in sys.path:
        sys.path.insert(0, str(_code_dir))
    from core_a import (
        DOMAINS_A,
        bootstrap_a,
        compute_bessel_t_constants_decimal,
        compute_observed_a,
        extract_slot_contrasts,
        infer_hybrid_bessel_t_tango_a,
        infer_hybrid_pct_tango_a,
        infer_percentile_a,
        infer_studentized_a,
        prepare_sorted_boot_stats,
    )
    from dgp_a import PopulationA, from_table
    from exact_tango import (
        DEFAULT_TABLES_NPZ,
        certify_all_6_left_cuts,
        load_certified_tango_tables,
        verify_ieee754_rn_and_subnormals,
        verify_sealed_left_cuts,
    )
    from inputs import DEFAULT_SOURCE, DEFAULT_SPLIT, file_sha256
    from manifest_a import SEEDS

MAX_RSS_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB hard guardrail (combined parent + active workers)
CONFIRMATION_BANK_HARD_DISABLED = True

SEALED_CORE_MODULES = (
    "inputs.py",
    "exact_tango.py",
    "core_a.py",
    "dgp_a.py",
    "manifest_a.py",
    "run_sim.py",
    "summarize_sim.py",
    "formal_engine.py",
)

SINGLE_METHODS = (
    "hybrid_pct_tango",
    "hybrid_bessel_t_tango",
    "percentile",
    "studentized",
)
ALL3_METHODS = (
    "hybrid_pct_tango",
    "hybrid_bessel_t_tango",
    "percentile",
)

DEFAULT_SEALED_IDENTITY = Path(__file__).resolve().parent.parent / "manifests" / "sealed-run-identity.json"

CHUNK_BOOL_KEYS = (
    "degenerate",
    "degenerate_995",
    "degenerate_tol0",
    "tol_diff",
    "reject",
    "failure_distinct_boot",
    "failure_observed_se",
    "failure_bootstrap_se",
    "failure_studentized_distribution",
    "failure_ci",
)
CHUNK_FLOAT_PROB_KEYS = ("p", "pplus", "pminus")
CHUNK_CI_KEYS = ("ci", "ci_995")
CHUNK_DIR_KEYS = ("direction", "observed_direction")
CHUNK_UNIQUE_KEYS = ("unique_lower", "unique_upper")

EXPECTED_CHUNK_KEYS = frozenset(
    ("rep_indices",)
    + CHUNK_FLOAT_PROB_KEYS
    + CHUNK_CI_KEYS
    + CHUNK_DIR_KEYS
    + CHUNK_UNIQUE_KEYS
    + CHUNK_BOOL_KEYS
)

IDENTITY_BINDING_KEYS = (
    "cell_name",
    "cell_index",
    "population_name",
    "population_fingerprint",
    "missing",
    "missing_rate",
    "method",
    "bank",
    "bank_id",
    "start_rep",
    "end_rep",
    "r_total",
    "b_reps",
    "n_ac",
    "n_bd",
    "code_sha256",
    "exact_tango_tables_sha256",
    "exact_tango_tables_payload_sha256",
    "manifest_sha256",
    "populations_sha256",
    "source_sha256",
    "split_sha256",
)


def verify_single_thread_env() -> Dict[str, str]:
    """Assert single-thread BLAS/OMP environment variables are active in current process."""
    snapshot = {}
    for k in SINGLE_THREAD_ENV_VARS:
        val = os.environ.get(k)
        if val != "1":
            raise RuntimeError(f"Single-thread BLAS guardrail violated: {k}={val!r} (expected '1')")
        snapshot[k] = val
    return snapshot


def get_process_rss_bytes() -> Tuple[int, int]:
    """Return (current_rss_bytes, peak_rss_bytes) for current process on Windows/POSIX."""
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.argtypes = []
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        handle = k32.GetCurrentProcess()
        fn = getattr(k32, "K32GetProcessMemoryInfo", None)
        if fn is None:
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            fn = psapi.GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        if fn(handle, ctypes.byref(pmc), pmc.cb):
            return int(pmc.WorkingSetSize), int(pmc.PeakWorkingSetSize)
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = int(ru * 1024) if sys.platform != "darwin" else int(ru)
        return peak, peak
    except Exception:
        return 0, 0


def atomic_write_npz(path: Path, data: Dict[str, np.ndarray], max_retries: int = 6):
    """Write compressed .npz atomically with Windows WinError 5/32 retry handling."""
    tmp_base = path.with_name(f"{path.stem}.tmp.{os.getpid()}.{time.time_ns()}")
    tmp_npz = tmp_base.with_suffix(".npz")
    np.savez_compressed(tmp_npz, **data)
    for attempt in range(max_retries):
        try:
            tmp_npz.replace(path)
            return
        except OSError:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.05 * (2 ** attempt))


def atomic_write_json(path: Path, data: dict, max_retries: int = 6):
    """Write JSON atomically with Windows WinError 5/32 retry handling."""
    tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{time.time_ns()}")
    serialized = json.dumps(data, indent=2)
    tmp_path.write_text(serialized, encoding="utf-8")
    for attempt in range(max_retries):
        try:
            tmp_path.replace(path)
            return
        except OSError:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.05 * (2 ** attempt))


def compute_chunk_payload_sha(data_dict: Dict[str, np.ndarray]) -> str:
    """Compute deterministic SHA256 binding array keys, dtypes, shapes, and contiguous byte payloads."""
    h = hashlib.sha256()
    for key in sorted(data_dict.keys()):
        arr = np.ascontiguousarray(data_dict[key])
        header = f"{key}|{arr.dtype.str}|{arr.ndim}|{','.join(str(d) for d in arr.shape)}|".encode("utf-8")
        h.update(header)
        h.update(arr.tobytes())
    return h.hexdigest()


def compute_core_code_hashes(code_dir: Path) -> Tuple[str, Dict[str, str]]:
    """Compute combined SHA256 and per-file SHA256 across all 8 SEALED_CORE_MODULES."""
    h = hashlib.sha256()
    per_module: Dict[str, str] = {}
    for mod_name in SEALED_CORE_MODULES:
        p = code_dir / mod_name
        if not p.is_file():
            raise FileNotFoundError(f"Required core module missing: {p}")
        raw = p.read_bytes()
        mod_sha = hashlib.sha256(raw).hexdigest()
        per_module[mod_name] = mod_sha
        h.update(mod_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(raw)
        h.update(b"\x00")
    return h.hexdigest(), per_module


def compute_code_sha256(code_dir: Path) -> str:
    """Return combined SHA256 of all 8 SEALED_CORE_MODULES."""
    combined, _ = compute_core_code_hashes(code_dir)
    return combined


def build_sealed_identity_payload(
    code_dir: Path,
    manifest_88_path: Path,
    pop_88_path: Path,
    manifest_56_path: Path,
    pop_56_path: Path,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
    source_path: Path = Path(DEFAULT_SOURCE),
    split_path: Path = Path(DEFAULT_SPLIT),
) -> Dict[str, Any]:
    """Construct sealed run identity payload locking 8 modules, exact Tango tables, left cuts, inputs, and matrices."""
    for req_p in (
        manifest_88_path,
        pop_88_path,
        manifest_56_path,
        pop_56_path,
        exact_tango_npz_path,
        source_path,
        split_path,
    ):
        if not Path(req_p).is_file():
            raise FileNotFoundError(f"Cannot seal identity; required file missing: {req_p}")

    verify_ieee754_rn_and_subnormals()
    code_sha, module_shas = compute_core_code_hashes(code_dir)
    tango_bundle = load_certified_tango_tables(npz_path=exact_tango_npz_path, force_reload=True)
    left_cuts_6 = certify_all_6_left_cuts()
    verify_sealed_left_cuts(left_cuts_6)

    return {
        "schema_version": "scheme-a-step5b-sealed-identity-v1",
        "s5_frozen": False,
        "confirmation_bank_hard_disabled": True,
        "code_sha256": code_sha,
        "module_sha256": module_shas,
        "exact_tango_tables_name": Path(exact_tango_npz_path).name,
        "exact_tango_tables_sha256": tango_bundle["file_sha256"],
        "exact_tango_tables_payload_sha256": tango_bundle["payload_sha256"],
        "certified_left_cuts_6": left_cuts_6,
        "bessel_t_expansion_constants": {
            "80": compute_bessel_t_constants_decimal(80),
            "20": compute_bessel_t_constants_decimal(20),
        },
        "source_sha256": file_sha256(source_path),
        "split_sha256": file_sha256(split_path),
        "matrices": {
            "validation": {
                "bank": "validation",
                "bank_id": SEEDS["validation"],
                "manifest_name": Path(manifest_88_path).name,
                "manifest_sha256": file_sha256(manifest_88_path),
                "populations_name": Path(pop_88_path).name,
                "populations_sha256": file_sha256(pop_88_path),
                "expected_cells": 88,
            },
            "power_grid": {
                "bank": "power_grid",
                "bank_id": SEEDS["power_grid"],
                "manifest_name": Path(manifest_56_path).name,
                "manifest_sha256": file_sha256(manifest_56_path),
                "populations_name": Path(pop_56_path).name,
                "populations_sha256": file_sha256(pop_56_path),
                "expected_cells": 56,
            },
        },
    }


def verify_sealed_code_and_tables(
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
    source_path: Path = Path(DEFAULT_SOURCE),
    split_path: Path = Path(DEFAULT_SPLIT),
    code_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Fail-closed verification of sealed 8-module code_sha256, exact Tango tables, 6 rational left cuts, and inputs."""
    resolved_code_dir = code_dir if code_dir is not None else Path(__file__).resolve().parent
    for label, p in (
        ("sealed_identity", Path(sealed_identity_path)),
        ("exact_tango_tables", Path(exact_tango_npz_path)),
        ("source", Path(source_path)),
        ("split", Path(split_path)),
    ):
        if not p.is_file():
            raise FileNotFoundError(f"Sealed identity check failed: required {label} file missing at {p}")

    verify_ieee754_rn_and_subnormals()
    sealed = json.loads(Path(sealed_identity_path).read_text(encoding="utf-8"))
    if sealed.get("s5_frozen") is not False:
        raise RuntimeError("Sealed identity s5_frozen must be False in Step 5b")
    if sealed.get("confirmation_bank_hard_disabled") is not True:
        raise RuntimeError("Sealed identity confirmation_bank_hard_disabled must be True in Step 5b")

    if "certified_left_cuts_6" not in sealed or not isinstance(sealed["certified_left_cuts_6"], dict):
        raise ValueError("Sealed identity missing 'certified_left_cuts_6'")
    verify_sealed_left_cuts(sealed["certified_left_cuts_6"])
    fresh_cuts = certify_all_6_left_cuts()
    for cut_k, exp_rec in fresh_cuts.items():
        got_rec = sealed["certified_left_cuts_6"].get(cut_k)
        if not isinstance(got_rec, dict) or got_rec.get("theta_cut_hex") != exp_rec["theta_cut_hex"] or got_rec.get("half_alpha_lo_hex") != exp_rec["half_alpha_lo_hex"]:
            raise RuntimeError(f"Sealed left-cut hex mismatch on {cut_k}")

    exp_tbl_sha = sealed.get("exact_tango_tables_sha256")
    exp_tbl_payload_sha = sealed.get("exact_tango_tables_payload_sha256")
    if not exp_tbl_sha or not exp_tbl_payload_sha:
        raise ValueError("Sealed identity missing exact_tango_tables SHA256 fields")

    tango_bundle = load_certified_tango_tables(
        npz_path=exact_tango_npz_path,
        expected_file_sha256=str(exp_tbl_sha),
        expected_payload_sha256=str(exp_tbl_payload_sha),
    )

    code_sha, module_shas = compute_core_code_hashes(resolved_code_dir)
    cur_source_sha = file_sha256(source_path)
    cur_split_sha = file_sha256(split_path)

    mismatches = []
    if code_sha != sealed.get("code_sha256"):
        mismatches.append(f"code_sha256: current={code_sha} != sealed={sealed.get('code_sha256')}")
    if cur_source_sha != sealed.get("source_sha256"):
        mismatches.append(f"source_sha256: current={cur_source_sha} != sealed={sealed.get('source_sha256')}")
    if cur_split_sha != sealed.get("split_sha256"):
        mismatches.append(f"split_sha256: current={cur_split_sha} != sealed={sealed.get('split_sha256')}")

    sealed_mods = sealed.get("module_sha256", {})
    if set(sealed_mods.keys()) != set(SEALED_CORE_MODULES):
        mismatches.append(f"module_sha256 keys: sealed={sorted(sealed_mods.keys())} != expected={sorted(SEALED_CORE_MODULES)}")
    for mod_name, cur_m_sha in module_shas.items():
        if sealed_mods.get(mod_name) != cur_m_sha:
            mismatches.append(f"module[{mod_name}]: current={cur_m_sha} != sealed={sealed_mods.get(mod_name)}")

    if mismatches:
        raise RuntimeError("Sealed run identity mismatch:\n  " + "\n  ".join(mismatches))

    return {
        "code_sha256": code_sha,
        "exact_tango_tables_sha256": tango_bundle["file_sha256"],
        "exact_tango_tables_payload_sha256": tango_bundle["payload_sha256"],
        "source_sha256": cur_source_sha,
        "split_sha256": cur_split_sha,
    }


def verify_integrity_gates(
    manifest_path: Path,
    pop_table_path: Path,
    bank_name: str,
    sealed_identity_path: Path = DEFAULT_SEALED_IDENTITY,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
    source_path: Path = Path(DEFAULT_SOURCE),
    split_path: Path = Path(DEFAULT_SPLIT),
    code_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Strictly verify code, exact Tango tables, left cuts, inputs, and matrix files against sealed-run-identity.json."""
    for label, p in (("manifest", Path(manifest_path)), ("populations", Path(pop_table_path))):
        if not p.is_file():
            raise FileNotFoundError(f"Integrity gate failure: required {label} file missing at {p}")

    base_gates = verify_sealed_code_and_tables(
        sealed_identity_path=sealed_identity_path,
        exact_tango_npz_path=exact_tango_npz_path,
        source_path=source_path,
        split_path=split_path,
        code_dir=code_dir,
    )

    sealed = json.loads(Path(sealed_identity_path).read_text(encoding="utf-8"))
    if bank_name not in sealed.get("matrices", {}):
        raise ValueError(f"Bank '{bank_name}' is not authorized in sealed identity matrices")

    mat_expected = sealed["matrices"][bank_name]
    cur_manifest_sha = file_sha256(manifest_path)
    cur_pop_sha = file_sha256(pop_table_path)

    mismatches = []
    if int(mat_expected.get("bank_id", -1)) != int(SEEDS[bank_name]):
        mismatches.append(f"bank_id: expected={SEEDS[bank_name]} != sealed={mat_expected.get('bank_id')}")
    if cur_manifest_sha != mat_expected.get("manifest_sha256"):
        mismatches.append(f"manifest_sha256: current={cur_manifest_sha} != sealed={mat_expected.get('manifest_sha256')}")
    if cur_pop_sha != mat_expected.get("populations_sha256"):
        mismatches.append(f"populations_sha256: current={cur_pop_sha} != sealed={mat_expected.get('populations_sha256')}")

    if mismatches:
        raise RuntimeError("Sealed matrix identity mismatch:\n  " + "\n  ".join(mismatches))

    return {
        **base_gates,
        "manifest_sha256": cur_manifest_sha,
        "populations_sha256": cur_pop_sha,
    }


def build_expected_chunk_identity(
    cell_spec: dict,
    pop_fingerprint: str,
    method_label: str,
    bank_name: str,
    bank_id: int,
    start_rep: int,
    end_rep: int,
    r_total: int,
    b_reps: int,
    n_ac: int,
    n_bd: int,
    gates: Dict[str, str],
) -> Dict[str, Any]:
    """Build complete 22-key identity record bound to every checkpoint chunk."""
    return {
        "cell_name": str(cell_spec["cell_name"]),
        "cell_index": int(cell_spec["cell_index"]),
        "population_name": str(cell_spec["population_name"]),
        "population_fingerprint": str(pop_fingerprint),
        "missing": str(cell_spec.get("missing", "none")),
        "missing_rate": str(cell_spec.get("missing_rate", "0")),
        "method": str(method_label),
        "bank": str(bank_name),
        "bank_id": int(bank_id),
        "start_rep": int(start_rep),
        "end_rep": int(end_rep),
        "r_total": int(r_total),
        "b_reps": int(b_reps),
        "n_ac": int(n_ac),
        "n_bd": int(n_bd),
        "code_sha256": str(gates["code_sha256"]),
        "exact_tango_tables_sha256": str(gates["exact_tango_tables_sha256"]),
        "exact_tango_tables_payload_sha256": str(gates["exact_tango_tables_payload_sha256"]),
        "manifest_sha256": str(gates["manifest_sha256"]),
        "populations_sha256": str(gates["populations_sha256"]),
        "source_sha256": str(gates["source_sha256"]),
        "split_sha256": str(gates["split_sha256"]),
    }


def validate_payload_arrays(
    chunk_dict: Dict[str, np.ndarray],
    start_rep: int,
    end_rep: int,
    b_reps: int = 5000,
    enforce_domains: bool = False,
) -> None:
    """Strictly validate array keys, shapes, dtypes, exact rep_indices, and legal value domains."""
    if end_rep <= start_rep or start_rep < 0:
        raise ValueError(f"Invalid replicate interval [{start_rep}, {end_rep})")
    n_rows = end_rep - start_rep

    got_keys = frozenset(chunk_dict.keys())
    if got_keys != EXPECTED_CHUNK_KEYS:
        missing_k = sorted(EXPECTED_CHUNK_KEYS - got_keys)
        extra_k = sorted(got_keys - EXPECTED_CHUNK_KEYS)
        raise ValueError(f"Chunk key mismatch: missing={missing_k}, extra={extra_k}")

    rep_idx = chunk_dict["rep_indices"]
    if rep_idx.ndim != 1 or rep_idx.shape != (n_rows,) or not np.issubdtype(rep_idx.dtype, np.signedinteger):
        raise ValueError(f"Invalid rep_indices shape/dtype: shape={rep_idx.shape}, dtype={rep_idx.dtype}, expected ({n_rows},) int64")
    expected_reps = np.arange(start_rep, end_rep, dtype=np.int64)
    if not np.array_equal(rep_idx, expected_reps):
        raise ValueError(f"rep_indices mismatch for interval [{start_rep}, {end_rep})")

    for k in CHUNK_FLOAT_PROB_KEYS:
        arr = chunk_dict[k]
        if arr.shape != (n_rows, 4) or arr.dtype != np.float64:
            raise ValueError(f"Invalid {k} shape/dtype: {arr.shape} {arr.dtype}, expected ({n_rows}, 4) float64")
        if not np.all(np.isfinite(arr)) or np.any((arr < 0.0) | (arr > 1.0)):
            raise ValueError(f"Out-of-range or non-finite probability values in {k}")

    for k in CHUNK_CI_KEYS:
        arr = chunk_dict[k]
        if arr.shape != (n_rows, 4, 2) or arr.dtype != np.float64:
            raise ValueError(f"Invalid {k} shape/dtype: {arr.shape} {arr.dtype}, expected ({n_rows}, 4, 2) float64")
        if not np.all(np.isfinite(arr)) or np.any(arr[:, :, 0] > arr[:, :, 1]):
            raise ValueError(f"Non-finite or inverted CI bounds in {k}")
        if enforce_domains:
            for j in range(4):
                if np.any(arr[:, j, 0] < DOMAINS_A[j, 0]) or np.any(arr[:, j, 1] > DOMAINS_A[j, 1]):
                    raise ValueError(f"CI bounds in {k} on slot {j} exceed legal domain {DOMAINS_A[j].tolist()}")

    for k in CHUNK_DIR_KEYS:
        arr = chunk_dict[k]
        if arr.shape != (n_rows, 4) or not np.issubdtype(arr.dtype, np.signedinteger):
            raise ValueError(f"Invalid {k} shape/dtype: {arr.shape} {arr.dtype}, expected ({n_rows}, 4) signed int")
        if not np.all(np.isin(arr, (-1, 0, 1))):
            raise ValueError(f"Illegal direction values outside {{-1, 0, 1}} in {k}")

    for k in CHUNK_UNIQUE_KEYS:
        arr = chunk_dict[k]
        if arr.shape != (n_rows, 4) or not np.issubdtype(arr.dtype, np.signedinteger):
            raise ValueError(f"Invalid {k} shape/dtype: {arr.shape} {arr.dtype}, expected ({n_rows}, 4) signed int")
        if np.any((arr < 1) | (arr > b_reps)):
            raise ValueError(f"Out-of-range distinct count in {k} (expected 1..{b_reps})")

    for k in CHUNK_BOOL_KEYS:
        arr = chunk_dict[k]
        if arr.shape != (n_rows, 4) or arr.dtype != np.dtype(bool):
            raise ValueError(f"Invalid {k} shape/dtype: {arr.shape} {arr.dtype}, expected ({n_rows}, 4) bool")

    deg = chunk_dict["degenerate"]
    if np.any(deg):
        if not np.all(chunk_dict["p"][deg] == 1.0):
            raise ValueError("Degenerate entries with p != 1.0 detected")
        if np.any(chunk_dict["reject"][deg]):
            raise ValueError("Degenerate entries with reject == True detected")
        if not np.all(chunk_dict["direction"][deg] == 0):
            raise ValueError("Degenerate entries with non-zero declared direction detected")
        for j in range(4):
            d_j = deg[:, j]
            if np.any(d_j):
                if not (
                    np.all(chunk_dict["ci"][d_j, j, 0] == DOMAINS_A[j, 0])
                    and np.all(chunk_dict["ci"][d_j, j, 1] == DOMAINS_A[j, 1])
                ):
                    raise ValueError(f"Degenerate main CI on slot {j} did not fall back to DOMAINS_A")


def validate_chunk_payload_and_meta(
    chunk_dict: Dict[str, np.ndarray],
    meta: Dict[str, Any],
    expected_identity: Dict[str, Any],
) -> None:
    """Validate chunk metadata identity, payload SHA256, and full array entity invariants."""
    for k in IDENTITY_BINDING_KEYS:
        if k not in meta:
            raise ValueError(f"Chunk metadata missing required binding key '{k}'")
        if meta[k] != expected_identity[k]:
            raise ValueError(
                f"Chunk identity mismatch on '{k}': meta={meta[k]!r} != expected={expected_identity[k]!r}"
            )

    start_rep = int(expected_identity["start_rep"])
    end_rep = int(expected_identity["end_rep"])
    b_reps = int(expected_identity["b_reps"])
    enforce_domains = expected_identity.get("method") in ALL3_METHODS
    validate_payload_arrays(
        chunk_dict,
        start_rep=start_rep,
        end_rep=end_rep,
        b_reps=b_reps,
        enforce_domains=enforce_domains,
    )

    payload_sha = compute_chunk_payload_sha(chunk_dict)
    if payload_sha != meta.get("payload_sha256"):
        raise ValueError(
            f"Chunk payload SHA256 mismatch: computed={payload_sha} != meta={meta.get('payload_sha256')}"
        )


def _pack_results(results: List[dict], start_rep: int, end_rep: int) -> Dict[str, np.ndarray]:
    """Pack a list of inference dictionaries into chunk numpy arrays with explicit rep_indices."""
    if len(results) != (end_rep - start_rep):
        raise ValueError(f"Result count {len(results)} != expected {end_rep - start_rep}")
    return {
        "rep_indices": np.arange(start_rep, end_rep, dtype=np.int64),
        "p": np.array([res["p"] for res in results], dtype=np.float64),
        "pplus": np.array([res["pplus"] for res in results], dtype=np.float64),
        "pminus": np.array([res["pminus"] for res in results], dtype=np.float64),
        "ci": np.array([res["ci"] for res in results], dtype=np.float64),
        "degenerate": np.array([res["degenerate"] for res in results], dtype=bool),
        "ci_995": np.array([res["ci_995"] for res in results], dtype=np.float64),
        "degenerate_995": np.array([res["degenerate_995"] for res in results], dtype=bool),
        "degenerate_tol0": np.array([res["degenerate_tol0"] for res in results], dtype=bool),
        "tol_diff": np.array([res["tol_diff"] for res in results], dtype=bool),
        "reject": np.array([res["reject"] for res in results], dtype=bool),
        "direction": np.array([res["direction"] for res in results], dtype=np.int64),
        "observed_direction": np.array([res["observed_direction"] for res in results], dtype=np.int64),
        "unique_lower": np.array([res["unique_lower"] for res in results], dtype=np.int64),
        "unique_upper": np.array([res["unique_upper"] for res in results], dtype=np.int64),
        "failure_distinct_boot": np.array([res["failure_distinct_boot"] for res in results], dtype=bool),
        "failure_observed_se": np.array([res["failure_observed_se"] for res in results], dtype=bool),
        "failure_bootstrap_se": np.array([res["failure_bootstrap_se"] for res in results], dtype=bool),
        "failure_studentized_distribution": np.array([res["failure_studentized_distribution"] for res in results], dtype=bool),
        "failure_ci": np.array([res["failure_ci"] for res in results], dtype=bool),
    }


def _assert_not_confirmation_bank(bank_name: str, bank_id: int) -> None:
    if CONFIRMATION_BANK_HARD_DISABLED and (bank_name == "confirmation" or bank_id == SEEDS["confirmation"]):
        raise PermissionError(
            f"Confirmation bank ({SEEDS['confirmation']}) is unconditionally hard-disabled throughout Step 5b "
            "(CONFIRMATION_BANK_HARD_DISABLED == True, S5_FROZEN == False). "
            "No CLI flag or programmatic bypass is permitted."
        )


def run_single_rep(
    pop: PopulationA,
    cell_spec: dict,
    bank_id: int,
    outer_rep: int,
    method: str = "hybrid_pct_tango",
    b_reps: int = 5000,
    n_ac: int = 80,
    n_bd: int = 80,
    tango_tables: Optional[Dict[str, Any]] = None,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> dict:
    """Execute a single outer replicate of the simulation on the locked SeedSequence stream."""
    _assert_not_confirmation_bank("", bank_id)
    cell_idx = cell_spec["cell_index"]

    ss_outer = np.random.SeedSequence([bank_id, cell_idx, outer_rep, 0])
    ss_boot = np.random.SeedSequence([bank_id, cell_idx, outer_rep, 1])

    rng_outer = np.random.default_rng(ss_outer)
    rng_boot = np.random.default_rng(ss_boot)

    missing = cell_spec.get("missing", "none")
    missing_rate = Fraction(cell_spec.get("missing_rate", "0"))

    sample = pop.sample(rng_outer, n_ac=n_ac, n_bd=n_bd, missing=missing, missing_rate=missing_rate)
    contrasts = extract_slot_contrasts(sample)
    (obs_lo, obs_hi), (obs_se_lo, obs_se_hi) = compute_observed_a(contrasts)
    (boot_lo, boot_hi), (boot_se_lo, boot_se_hi) = bootstrap_a(contrasts, rng_boot, b=b_reps)

    if method == "hybrid_pct_tango":
        return infer_hybrid_pct_tango_a(
            contrasts,
            boot_lo,
            boot_hi,
            obs_lo,
            obs_hi,
            tango_tables=tango_tables,
            npz_path=exact_tango_npz_path,
        )
    if method == "hybrid_bessel_t_tango":
        return infer_hybrid_bessel_t_tango_a(
            contrasts,
            boot_lo,
            boot_hi,
            obs_lo,
            obs_hi,
            tango_tables=tango_tables,
            npz_path=exact_tango_npz_path,
        )
    if method == "percentile":
        return infer_percentile_a(boot_lo, boot_hi, obs_lo, obs_hi)
    if method == "studentized":
        return infer_studentized_a(
            boot_lo, boot_hi, boot_se_lo, boot_se_hi,
            obs_lo, obs_hi, obs_se_lo, obs_se_hi,
        )
    if method == "all3":
        pre_boot = prepare_sorted_boot_stats(boot_lo, boot_hi)
        return {
            "hybrid_pct_tango": infer_hybrid_pct_tango_a(
                contrasts,
                boot_lo,
                boot_hi,
                obs_lo,
                obs_hi,
                tango_tables=tango_tables,
                precomputed_boot=pre_boot,
                npz_path=exact_tango_npz_path,
            ),
            "hybrid_bessel_t_tango": infer_hybrid_bessel_t_tango_a(
                contrasts,
                boot_lo,
                boot_hi,
                obs_lo,
                obs_hi,
                tango_tables=tango_tables,
                precomputed_boot=pre_boot,
                npz_path=exact_tango_npz_path,
            ),
            "percentile": infer_percentile_a(
                boot_lo,
                boot_hi,
                obs_lo,
                obs_hi,
                precomputed_boot=pre_boot,
            ),
        }
    raise ValueError(f"Unknown method: {method}")


def run_chunk(
    pop: PopulationA,
    cell_spec: dict,
    bank_id: int,
    start_rep: int,
    end_rep: int,
    method: str = "hybrid_pct_tango",
    b_reps: int = 5000,
    n_ac: int = 80,
    n_bd: int = 80,
    tango_tables: Optional[Dict[str, Any]] = None,
    exact_tango_npz_path: Path = DEFAULT_TABLES_NPZ,
) -> Dict[str, Any]:
    """Execute a chunk of replicates and pack into validated numpy arrays."""
    _assert_not_confirmation_bank("", bank_id)
    results = [
        run_single_rep(
            pop,
            cell_spec,
            bank_id,
            r,
            method=method,
            b_reps=b_reps,
            n_ac=n_ac,
            n_bd=n_bd,
            tango_tables=tango_tables,
            exact_tango_npz_path=exact_tango_npz_path,
        )
        for r in range(start_rep, end_rep)
    ]
    if method == "all3":
        return {
            m_name: _pack_results([res[m_name] for res in results], start_rep, end_rep)
            for m_name in ALL3_METHODS
        }
    return _pack_results(results, start_rep, end_rep)


def _chunk_is_valid(chunk_file: Path, meta_file: Path, expected_identity: Dict[str, Any]) -> bool:
    if not (chunk_file.is_file() and meta_file.is_file()):
        return False
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        with np.load(chunk_file) as loaded:
            loaded_dict = {k: loaded[k] for k in loaded.files}
        validate_chunk_payload_and_meta(loaded_dict, meta, expected_identity)
        return True
    except Exception:
        return False


def _save_chunk_pair(
    cell_dir: Path,
    expected_identity: Dict[str, Any],
    data: Dict[str, np.ndarray],
):
    start_rep = int(expected_identity["start_rep"])
    end_rep = int(expected_identity["end_rep"])
    b_reps = int(expected_identity["b_reps"])
    enforce_domains = expected_identity.get("method") in ALL3_METHODS
    validate_payload_arrays(
        data,
        start_rep=start_rep,
        end_rep=end_rep,
        b_reps=b_reps,
        enforce_domains=enforce_domains,
    )

    chunk_file = cell_dir / f"chunk_{start_rep:04d}_{end_rep:04d}.npz"
    meta_file = cell_dir / f"chunk_{start_rep:04d}_{end_rep:04d}.json"
    payload_sha = compute_chunk_payload_sha(data)
    atomic_write_npz(chunk_file, data)
    chunk_meta = {
        **expected_identity,
        "payload_sha256": payload_sha,
        "timestamp": time.time(),
    }
    atomic_write_json(meta_file, chunk_meta)


def process_cell(
    cell_spec: dict,
    pop_dict: dict | PopulationA,
    bank_name: str,
    bank_id: int,
    gates: Dict[str, str],
    out_dir_str: str,
    method: str = "hybrid_pct_tango",
    out_dir_bessel_str: Optional[str] = None,
    out_dir_pct_str: Optional[str] = None,
    r_total: int = 2000,
    chunk_size: int = 200,
    b_reps: int = 5000,
    n_ac: int = 80,
    n_bd: int = 80,
    exact_tango_npz_str: str = str(DEFAULT_TABLES_NPZ),
) -> Dict[str, Any]:
    """Execute all chunks for a single cell and save atomically (worker-safe)."""
    verify_single_thread_env()
    _assert_not_confirmation_bank(bank_name, bank_id)

    t0 = time.perf_counter()
    tango_npz_path = Path(exact_tango_npz_str)
    tango_bundle = load_certified_tango_tables(
        npz_path=tango_npz_path,
        expected_file_sha256=gates["exact_tango_tables_sha256"],
        expected_payload_sha256=gates["exact_tango_tables_payload_sha256"],
    )

    pop = pop_dict if isinstance(pop_dict, PopulationA) else from_table(pop_dict)
    pop_fp = pop.fingerprint()
    if pop_fp != cell_spec["fingerprint"]:
        raise ValueError(
            f"Population fingerprint mismatch in {cell_spec['cell_name']}: {pop_fp} != {cell_spec['fingerprint']}"
        )

    cell_name = cell_spec["cell_name"]
    cell_dir_main = Path(out_dir_str) / cell_name
    cell_dir_main.mkdir(parents=True, exist_ok=True)

    cell_dir_bessel: Optional[Path] = None
    cell_dir_pct: Optional[Path] = None
    if method == "all3":
        if not out_dir_bessel_str or not out_dir_pct_str:
            raise ValueError("out_dir_bessel_str and out_dir_pct_str are required when method == 'all3'")
        cell_dir_bessel = Path(out_dir_bessel_str) / cell_name
        cell_dir_pct = Path(out_dir_pct_str) / cell_name
        cell_dir_bessel.mkdir(parents=True, exist_ok=True)
        cell_dir_pct.mkdir(parents=True, exist_ok=True)
    elif method not in SINGLE_METHODS:
        raise ValueError(f"Unsupported method '{method}'")

    n_chunks = (r_total + chunk_size - 1) // chunk_size
    computed_chunks = 0

    for c_idx in range(n_chunks):
        start_rep = c_idx * chunk_size
        end_rep = min(r_total, (c_idx + 1) * chunk_size)
        stem = f"chunk_{start_rep:04d}_{end_rep:04d}"

        if method == "all3":
            assert cell_dir_bessel is not None and cell_dir_pct is not None
            dir_by_m = {
                "hybrid_pct_tango": cell_dir_main,
                "hybrid_bessel_t_tango": cell_dir_bessel,
                "percentile": cell_dir_pct,
            }
            id_by_m = {
                m_lbl: build_expected_chunk_identity(
                    cell_spec, pop_fp, m_lbl, bank_name, bank_id,
                    start_rep, end_rep, r_total, b_reps, n_ac, n_bd, gates,
                )
                for m_lbl in ALL3_METHODS
            }
            if all(
                _chunk_is_valid(dir_by_m[m_lbl] / f"{stem}.npz", dir_by_m[m_lbl] / f"{stem}.json", id_by_m[m_lbl])
                for m_lbl in ALL3_METHODS
            ):
                continue

            all3_data = run_chunk(
                pop,
                cell_spec,
                bank_id,
                start_rep,
                end_rep,
                method="all3",
                b_reps=b_reps,
                n_ac=n_ac,
                n_bd=n_bd,
                tango_tables=tango_bundle,
                exact_tango_npz_path=tango_npz_path,
            )
            for m_lbl in ALL3_METHODS:
                _save_chunk_pair(dir_by_m[m_lbl], id_by_m[m_lbl], all3_data[m_lbl])
            computed_chunks += 1
        else:
            id_single = build_expected_chunk_identity(
                cell_spec, pop_fp, method, bank_name, bank_id,
                start_rep, end_rep, r_total, b_reps, n_ac, n_bd, gates,
            )
            if _chunk_is_valid(cell_dir_main / f"{stem}.npz", cell_dir_main / f"{stem}.json", id_single):
                continue
            data = run_chunk(
                pop,
                cell_spec,
                bank_id,
                start_rep,
                end_rep,
                method=method,
                b_reps=b_reps,
                n_ac=n_ac,
                n_bd=n_bd,
                tango_tables=tango_bundle,
                exact_tango_npz_path=tango_npz_path,
            )
            _save_chunk_pair(cell_dir_main, id_single, data)
            computed_chunks += 1

        cur_rss, peak_rss = get_process_rss_bytes()
        if max(cur_rss, peak_rss) > MAX_RSS_BYTES:
            raise MemoryError(f"Worker exceeded 8 GiB memory guardrail in {cell_name}: peak={peak_rss}")

    cur_rss, peak_rss = get_process_rss_bytes()
    return {
        "cell_name": cell_name,
        "cell_index": cell_spec["cell_index"],
        "computed_chunks": computed_chunks,
        "wall_seconds": time.perf_counter() - t0,
        "worker_peak_rss_bytes": peak_rss,
        "worker_pid": os.getpid(),
    }


def main():
    parser = argparse.ArgumentParser(description="Simulation runner for Scheme A Step 5b calibration.")
    parser.add_argument("--bank", choices=["validation", "confirmation", "power_grid"], default="validation")
    parser.add_argument(
        "--method",
        choices=["hybrid_pct_tango", "hybrid_bessel_t_tango", "percentile", "studentized", "all3"],
        default="all3",
    )
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON")
    parser.add_argument("--populations", required=True, help="Path to joint populations JSON")
    parser.add_argument("--sealed-identity", default=str(DEFAULT_SEALED_IDENTITY), help="Path to sealed-run-identity.json")
    parser.add_argument("--exact-tango-tables", default=str(DEFAULT_TABLES_NPZ), help="Path to exact-tango-tables.npz")
    parser.add_argument("--out-dir", required=True, help="Output directory (hybrid_pct_tango when --method all3)")
    parser.add_argument("--out-dir-bessel", default=None, help="Output directory for hybrid_bessel_t_tango when --method all3")
    parser.add_argument("--out-dir-percentile", default=None, help="Output directory for percentile when --method all3")
    parser.add_argument("--workers", type=int, default=4, help="Worker count (max 4)")
    parser.add_argument("--cells", default=None, help="Comma-separated cell names or indices to filter")
    parser.add_argument("--reps", type=int, default=2000, help="Total outer replicates")
    parser.add_argument("--chunk-size", type=int, default=200, help="Replicates per chunk")
    parser.add_argument("--b-reps", type=int, default=5000, help="Bootstrap replicates B")
    parser.add_argument("--n-ac", type=int, default=80, help="AC stratum cluster count")
    parser.add_argument("--n-bd", type=int, default=80, help="BD stratum cluster count")
    args = parser.parse_args()

    env_snapshot = verify_single_thread_env()
    bank_id = SEEDS[args.bank]
    _assert_not_confirmation_bank(args.bank, bank_id)

    if args.method == "all3" and (not args.out_dir_bessel or not args.out_dir_percentile):
        raise ValueError("--out-dir-bessel and --out-dir-percentile are required when --method all3")

    workers = min(4, max(1, args.workers))
    m_path = Path(args.manifest)
    p_path = Path(args.populations)
    s_path = Path(args.sealed_identity)
    t_npz_path = Path(args.exact_tango_tables)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir_bessel = Path(args.out_dir_bessel) if args.out_dir_bessel else None
    out_dir_pct = Path(args.out_dir_percentile) if args.out_dir_percentile else None
    if out_dir_bessel is not None:
        out_dir_bessel.mkdir(parents=True, exist_ok=True)
    if out_dir_pct is not None:
        out_dir_pct.mkdir(parents=True, exist_ok=True)

    t_start = time.perf_counter()
    gates_start = verify_integrity_gates(
        m_path,
        p_path,
        bank_name=args.bank,
        sealed_identity_path=s_path,
        exact_tango_npz_path=t_npz_path,
    )
    print("Initial sealed integrity gates passed:", gates_start, flush=True)

    manifest_data = json.loads(m_path.read_text(encoding="utf-8"))
    pop_table = json.loads(p_path.read_text(encoding="utf-8"))

    cells = manifest_data["cells"]
    if args.cells:
        filter_set = set(args.cells.split(","))
        cells = [c for c in cells if c["cell_name"] in filter_set or str(c["cell_index"]) in filter_set]

    print(
        f"Executing {len(cells)} cells using bank '{args.bank}' (seed {bank_id}), "
        f"method '{args.method}', workers={workers}",
        flush=True,
    )

    cell_metrics: List[Dict[str, Any]] = []
    max_worker_rss = 0
    peak_by_pid: Dict[int, int] = {}

    def _check_combined_rss(res_item: Dict[str, Any]):
        nonlocal max_worker_rss
        w_peak = int(res_item["worker_peak_rss_bytes"])
        w_pid = int(res_item["worker_pid"])
        max_worker_rss = max(max_worker_rss, w_peak)
        peak_by_pid[w_pid] = max(peak_by_pid.get(w_pid, 0), w_peak)
        _, m_peak = get_process_rss_bytes()
        top_workers_sum = sum(sorted(peak_by_pid.values(), reverse=True)[:workers])
        combined = m_peak + top_workers_sum if workers > 1 else max(m_peak, max_worker_rss)
        if combined > MAX_RSS_BYTES:
            raise MemoryError(
                f"Combined parent+worker peak RSS {combined / (1024**3):.2f} GiB exceeded 8 GiB guardrail!"
            )

    if workers == 1:
        populations = {name: from_table(pop_table[name]) for name in set(c["population_name"] for c in cells)}
        for i, cell in enumerate(cells):
            res = process_cell(
                cell,
                populations[cell["population_name"]],
                args.bank,
                bank_id,
                gates_start,
                str(out_dir),
                method=args.method,
                out_dir_bessel_str=str(out_dir_bessel) if out_dir_bessel else None,
                out_dir_pct_str=str(out_dir_pct) if out_dir_pct else None,
                r_total=args.reps,
                chunk_size=args.chunk_size,
                b_reps=args.b_reps,
                n_ac=args.n_ac,
                n_bd=args.n_bd,
                exact_tango_npz_str=str(t_npz_path),
            )
            cell_metrics.append(res)
            _check_combined_rss(res)
            if (i + 1) % 10 == 0 or (i + 1) == len(cells):
                if verify_integrity_gates(m_path, p_path, bank_name=args.bank, sealed_identity_path=s_path, exact_tango_npz_path=t_npz_path) != gates_start:
                    raise RuntimeError("Integrity violation mid-run: manifest, tables, or code modified!")
                print(f"[{i+1}/{len(cells)}] Completed {cell['cell_name']} ({res['wall_seconds']:.2f}s)", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(
                    process_cell,
                    cell,
                    pop_table[cell["population_name"]],
                    args.bank,
                    bank_id,
                    gates_start,
                    str(out_dir),
                    args.method,
                    str(out_dir_bessel) if out_dir_bessel else None,
                    str(out_dir_pct) if out_dir_pct else None,
                    args.reps,
                    args.chunk_size,
                    args.b_reps,
                    args.n_ac,
                    args.n_bd,
                    str(t_npz_path),
                ): cell
                for cell in cells
            }
            done_count = 0
            for fut in as_completed(futs):
                res = fut.result()
                cell_metrics.append(res)
                _check_combined_rss(res)
                done_count += 1
                if done_count % 10 == 0 or done_count == len(cells):
                    if verify_integrity_gates(m_path, p_path, bank_name=args.bank, sealed_identity_path=s_path, exact_tango_npz_path=t_npz_path) != gates_start:
                        raise RuntimeError("Integrity violation mid-run: manifest, tables, or code modified!")
                    print(
                        f"[{done_count}/{len(cells)}] Completed {res['cell_name']} "
                        f"({res['wall_seconds']:.2f}s, max_worker_rss={max_worker_rss / (1024**2):.1f} MiB)",
                        flush=True,
                    )

    _, main_peak_rss = get_process_rss_bytes()
    top_workers_sum = sum(sorted(peak_by_pid.values(), reverse=True)[:workers])
    combined_peak_rss = main_peak_rss + top_workers_sum if workers > 1 else max(main_peak_rss, max_worker_rss)
    if combined_peak_rss > MAX_RSS_BYTES:
        raise MemoryError(f"Final combined peak RSS {combined_peak_rss / (1024**3):.2f} GiB exceeded 8 GiB guardrail!")

    gates_end = verify_integrity_gates(
        m_path,
        p_path,
        bank_name=args.bank,
        sealed_identity_path=s_path,
        exact_tango_npz_path=t_npz_path,
    )
    if gates_start != gates_end:
        raise RuntimeError("Integrity violation during execution: manifest, tables, or code modified mid-run!")

    wall_total = time.perf_counter() - t_start
    run_meta = {
        "bank": args.bank,
        "bank_id": bank_id,
        "method": args.method,
        "workers": workers,
        "single_thread_blas_env": env_snapshot,
        "reps": args.reps,
        "chunk_size": args.chunk_size,
        "b_reps": args.b_reps,
        "n_ac": args.n_ac,
        "n_bd": args.n_bd,
        "cells_executed": len(cells),
        "wall_seconds": wall_total,
        "main_peak_rss_mib": main_peak_rss / (1024.0 ** 2),
        "max_worker_peak_rss_mib": max_worker_rss / (1024.0 ** 2),
        "combined_parent_and_workers_peak_rss_mib": combined_peak_rss / (1024.0 ** 2),
        "worker_peaks_by_pid_mib": {str(pid): pk / (1024.0 ** 2) for pid, pk in sorted(peak_by_pid.items())},
        "rss_guardrail_gib": 8.0,
        "sealed_identity_path": str(s_path),
        "exact_tango_tables_path": str(t_npz_path),
        "integrity_gates_start": gates_start,
        "integrity_gates_end": gates_end,
        "integrity_verified": gates_start == gates_end,
        "cell_metrics": sorted(cell_metrics, key=lambda x: x["cell_index"]),
    }

    if args.method == "all3":
        assert out_dir_bessel is not None and out_dir_pct is not None
        atomic_write_json(out_dir / "run_metadata.json", {**run_meta, "saved_method": "hybrid_pct_tango"})
        atomic_write_json(out_dir_bessel / "run_metadata.json", {**run_meta, "saved_method": "hybrid_bessel_t_tango"})
        atomic_write_json(out_dir_pct / "run_metadata.json", {**run_meta, "saved_method": "percentile"})
    else:
        atomic_write_json(out_dir / "run_metadata.json", {**run_meta, "saved_method": args.method})

    print(
        f"Execution complete in {wall_total:.2f}s (combined_peak_rss={combined_peak_rss / (1024**2):.1f} MiB). "
        "All chunks saved atomically.",
        flush=True,
    )


if __name__ == "__main__":
    main()
