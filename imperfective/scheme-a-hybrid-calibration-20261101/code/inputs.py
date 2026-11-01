"""Input loading, split reconstruction, and verification for Scheme A Step 5b calibration.

Reconstructs 20 AC and 20 BD paired clusters from frozen dev split.
Enforces strict task-specific semantics (exact M recomputation, Task L label consistency),
distinguishes strict protocol failures from true missingness, and provides both
bounded interval arrays for m=4 Scheme A and legacy V4 m=10 arrays.
"""

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np

DEFAULT_SOURCE = "E:/Claude/research/connecting-dots/imperfective/exp1-en/raw/stats-validation/preparation-20261030T082415/s4-unit-index-original.json"
DEFAULT_SPLIT = "E:/Claude/research/connecting-dots/imperfective/exp1-en/split.json"

EXPECTED_SOURCE_SHA256 = "fe61db83ecf6cbb3c263f889c9708d038e3bd9fa178c15ed035aae434321ce59"
EXPECTED_SPLIT_SHA256 = "6821a3b3ad2378d51c683b8abc8a5b45d402b9997e3c8957bcda95cd0ef289b7"

ALLOWED_PROTOCOL_REASONS = ("last_line", "estimate_lines", "weight_sum")
L_GOLD_STANDARDS = {"A": "False", "B": "True", "C": "Unknown", "D": "True"}

CONDITIONS_13 = (
    ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"),
    ("Ps", "Z"),
    ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
    ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
)


def file_sha256(path: str | Path) -> str:
    """Compute hex SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ClusterSampleA:
    """Cluster sample arrays for Scheme A (m=4) inference.

    ac_cont_lower, ac_cont_upper: shape (n_ac, 2, 2)
        role: 0=A, 1=C
        channel: 0=P_CoT, 1=MU_Z (in [0, 100])
    bd_cont_lower, bd_cont_upper: shape (n_bd, 2, 2)
        role: 0=B, 1=D
        channel: 0=MU_CoT, 1=P_CoT (in [0, 100])
    bd_l_acc_lower, bd_l_acc_upper: shape (n_bd, 2)
        role D discrete L accuracy indicator bounds (in {0.0, 1.0})
        channel: 0=L_CoT, 1=L_Z
    """
    ac_cont_lower: np.ndarray
    ac_cont_upper: np.ndarray
    bd_cont_lower: np.ndarray
    bd_cont_upper: np.ndarray
    bd_l_acc_lower: np.ndarray
    bd_l_acc_upper: np.ndarray

    def __post_init__(self):
        for name, arr, expected_ndim, vmin, vmax in [
            ("ac_cont_lower", self.ac_cont_lower, 3, 0.0, 100.0),
            ("ac_cont_upper", self.ac_cont_upper, 3, 0.0, 100.0),
            ("bd_cont_lower", self.bd_cont_lower, 3, 0.0, 100.0),
            ("bd_cont_upper", self.bd_cont_upper, 3, 0.0, 100.0),
            ("bd_l_acc_lower", self.bd_l_acc_lower, 2, 0.0, 1.0),
            ("bd_l_acc_upper", self.bd_l_acc_upper, 2, 0.0, 1.0),
        ]:
            if arr.ndim != expected_ndim:
                raise ValueError(f"{name} must have ndim={expected_ndim}, got {arr.ndim}")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{name} contains non-finite values")
            if np.any(arr < vmin) or np.any(arr > vmax):
                raise ValueError(f"{name} out of bounds [{vmin}, {vmax}]")

        if np.any(self.ac_cont_lower > self.ac_cont_upper):
            raise ValueError("ac_cont_lower > ac_cont_upper")
        if np.any(self.bd_cont_lower > self.bd_cont_upper):
            raise ValueError("bd_cont_lower > bd_cont_upper")
        if np.any(self.bd_l_acc_lower > self.bd_l_acc_upper):
            raise ValueError("bd_l_acc_lower > bd_l_acc_upper")

        unique_l = np.unique(self.bd_l_acc_lower)
        unique_u = np.unique(self.bd_l_acc_upper)
        if not set(unique_l).issubset({0.0, 1.0}) or not set(unique_u).issubset({0.0, 1.0}):
            raise ValueError("bd_l_acc values must be strictly in {0.0, 1.0}")


def validate_split_structure(split_data: dict) -> Tuple[List[str], List[str], Dict[str, List[str]], set]:
    """Validate frozen split and reconstruct disjoint groups (dev split ONLY)."""
    if not isinstance(split_data, dict) or "dev" not in split_data:
        raise ValueError("SPLIT missing 'dev' section")
    dev = split_data["dev"]
    if not isinstance(dev, dict):
        raise ValueError("SPLIT 'dev' is not a dict")

    telic_clusters = sorted(list(dev.get("telic_clusters", [])))
    atelic_clusters = sorted(list(dev.get("atelic_clusters", [])))

    if len(telic_clusters) != 20 or len(set(telic_clusters)) != 20:
        raise ValueError(f"Expected 20 unique telic clusters, got {len(telic_clusters)}")
    if len(atelic_clusters) != 20 or len(set(atelic_clusters)) != 20:
        raise ValueError(f"Expected 20 unique atelic clusters, got {len(atelic_clusters)}")

    group_items = {
        "A": [f"A_{s}" for s in telic_clusters],
        "C": [f"C_{s}" for s in telic_clusters],
        "B": [f"B_{s}" for s in atelic_clusters],
        "D": [f"D_{s}" for s in atelic_clusters],
    }

    set_a = set(group_items["A"])
    set_c = set(group_items["C"])
    set_b = set(group_items["B"])
    set_d = set(group_items["D"])

    if not (set_a.isdisjoint(set_c) and set_a.isdisjoint(set_b) and set_a.isdisjoint(set_d) and
            set_c.isdisjoint(set_b) and set_c.isdisjoint(set_d) and set_b.isdisjoint(set_d)):
        raise ValueError("Groups A, B, C, D are not pairwise disjoint!")

    all_ids = set_a | set_b | set_c | set_d
    if len(all_ids) != 80:
        raise ValueError(f"Expected 80 total item IDs, got {len(all_ids)}")

    if "ids" not in dev or set(dev["ids"]) != all_ids:
        raise ValueError("SPLIT dev['ids'] does not match reconstructed item IDs")

    return telic_clusters, atelic_clusters, group_items, all_ids


def parse_and_validate_source_units(
    source_rows: list,
    all_ids: set,
    allow_non_ok: bool = False
) -> Tuple[Dict[str, dict], dict]:
    """Parse and validate all source rows with strict task-specific checks."""
    if not isinstance(source_rows, list):
        raise ValueError("SOURCE must be a list of unit dictionaries")

    expected_unit_keys = {
        f"{iid}/{task}/{prompt}"
        for iid in all_ids
        for task, prompt in CONDITIONS_13
    }

    required_keys = {
        "id", "task", "prompt", "unit_key", "group", "status",
        "n_out_tokens", "generation_seconds", "seconds", "truncated",
        "protocol", "parsed"
    }

    unit_map = {}
    status_ok_count = 0
    non_ok_count = 0
    m_rows_checked = 0
    protocol_reasons_count = {r: 0 for r in ALLOWED_PROTOCOL_REASONS}
    protocol_fail_count = 0

    for row in source_rows:
        if not isinstance(row, dict):
            raise ValueError("Row is not a dictionary")
        missing_keys = required_keys - set(row.keys())
        if missing_keys:
            raise ValueError(f"Row missing required keys: {missing_keys}")

        item_id = str(row["id"])
        task = str(row["task"])
        prompt = str(row["prompt"])
        unit_key = str(row["unit_key"])

        if unit_key not in expected_unit_keys:
            raise ValueError(f"Unexpected unit_key '{unit_key}'")
        if unit_key in unit_map:
            raise ValueError(f"Duplicate unit_key '{unit_key}'")

        expected_key = f"{item_id}/{task}/{prompt}"
        if unit_key != expected_key:
            raise ValueError(f"unit_key mismatch: '{unit_key}' != '{expected_key}'")

        status = str(row["status"])
        if status == "ok":
            status_ok_count += 1
        else:
            non_ok_count += 1
            if not allow_non_ok:
                raise ValueError(f"Non-ok status '{status}' in '{unit_key}' rejected by production gate")

        protocol = row["protocol"]
        if not isinstance(protocol, dict):
            raise ValueError(f"protocol must be dict in '{unit_key}'")
        proto_ok = bool(protocol.get("protocol_ok"))
        reasons = list(protocol.get("reasons", []))

        if not proto_ok:
            protocol_fail_count += 1
            if len(reasons) == 0:
                raise ValueError(f"protocol_ok is False but reasons empty in '{unit_key}'")
            for r in reasons:
                if r not in ALLOWED_PROTOCOL_REASONS:
                    raise ValueError(f"Disallowed protocol reason '{r}' in '{unit_key}'")
                protocol_reasons_count[r] += 1
        else:
            if len(reasons) > 0:
                raise ValueError(f"protocol_ok is True but reasons non-empty in '{unit_key}'")

        parsed = row["parsed"]
        if not isinstance(parsed, dict):
            raise ValueError(f"parsed must be dict in '{unit_key}'")

        unit_entry = {
            "id": item_id,
            "task": task,
            "prompt": prompt,
            "unit_key": unit_key,
            "group": str(row["group"]),
            "status": status,
            "n_out_tokens": int(row["n_out_tokens"]),
            "generation_seconds": float(row["generation_seconds"]),
            "seconds": float(row["seconds"]),
            "truncated": bool(row["truncated"]),
            "protocol_ok": proto_ok,
            "reasons": reasons,
            "q": row.get("q"),
        }

        if status == "ok":
            if task == "L":
                lbl_row = row.get("label")
                lbl_parsed = parsed.get("label")
                valid_labels = {"True", "False", "Unknown"}

                if lbl_row not in valid_labels or lbl_parsed not in valid_labels:
                    raise ValueError(f"Task L invalid label in '{unit_key}': row='{lbl_row}', parsed='{lbl_parsed}'")
                if lbl_row != lbl_parsed:
                    raise ValueError(f"Task L label mismatch in '{unit_key}': row='{lbl_row}' != parsed='{lbl_parsed}'")
                if "ok" in parsed:
                    raise ValueError(f"Task L parsed must NOT contain 'ok' key in '{unit_key}'")

                unit_entry["label"] = lbl_row

            elif task in {"P", "Ps"}:
                if parsed.get("ok") is not True:
                    raise ValueError(f"parsed.ok is not True in '{unit_key}'")
                val_row = row.get("value")
                val_parsed = parsed.get("value")
                if not isinstance(val_row, (int, float)) or not isinstance(val_parsed, (int, float)):
                    raise ValueError(f"P value must be numeric in '{unit_key}'")
                v_f = float(val_row)
                vp_f = float(val_parsed)
                if not math.isfinite(v_f) or v_f < 0.0 or v_f > 100.0 or v_f != vp_f:
                    raise ValueError(f"Invalid P value in '{unit_key}': {v_f} vs {vp_f}")
                unit_entry["value"] = v_f

            elif task == "M":
                m_rows_checked += 1
                if parsed.get("ok") is not True:
                    raise ValueError(f"M parsed.ok is not True in '{unit_key}'")
                raw_est = parsed.get("estimates")
                raw_wt = parsed.get("weights")
                if not isinstance(raw_est, list) or len(raw_est) != 5:
                    raise ValueError(f"M estimates must be 5 items in '{unit_key}'")
                if not isinstance(raw_wt, list) or len(raw_wt) != 5:
                    raise ValueError(f"M weights must be 5 items in '{unit_key}'")

                estimates = []
                for e in raw_est:
                    ef = float(e)
                    if not math.isfinite(ef) or ef < 0.0 or ef > 100.0:
                        raise ValueError(f"M estimate out of [0, 100] in '{unit_key}': {ef}")
                    estimates.append(ef)

                weights = []
                for w in raw_wt:
                    wf = float(w)
                    if not math.isfinite(wf) or wf < 0.0 or wf > 1.0:
                        raise ValueError(f"M weight out of [0, 1] in '{unit_key}': {wf}")
                    weights.append(wf)

                w_sum = sum(weights)
                if w_sum <= 0.0:
                    raise ValueError(f"M sum of weights <= 0 in '{unit_key}'")

                w_norm = [w / w_sum for w in weights]
                val_w = sum(w * e for w, e in zip(w_norm, estimates))
                val_u = sum(estimates) / 5.0
                val_u_frac = sum(Fraction(str(e)) for e in estimates) / 5

                val_row = float(row.get("value"))
                val_parsed = float(parsed.get("value"))
                if val_w != val_row or val_w != val_parsed:
                    raise ValueError(
                        f"M exact float equality failed in '{unit_key}': "
                        f"recomputed={val_w}, row={val_row}, parsed={val_parsed}"
                    )

                unit_entry["value"] = val_row
                unit_entry["val_w"] = val_w
                unit_entry["val_u"] = val_u
                unit_entry["val_u_frac"] = val_u_frac
                unit_entry["estimates"] = estimates
                unit_entry["weights"] = weights
                unit_entry["w_norm"] = w_norm
                unit_entry["weight_sum_in_tolerance"] = bool(parsed.get("weight_sum_in_tolerance"))

        unit_map[unit_key] = unit_entry

    if set(unit_map.keys()) != expected_unit_keys:
        raise ValueError("Cartesian completeness failure: mismatch between expected and observed units")

    summary = {
        "status_ok_count": status_ok_count,
        "non_ok_count": non_ok_count,
        "m_rows_checked": m_rows_checked,
        "protocol_fail_count": protocol_fail_count,
        "protocol_reasons_count": protocol_reasons_count,
    }
    return unit_map, summary


def build_cluster_arrays(
    unit_map: Dict[str, dict],
    telic_clusters: List[str],
    atelic_clusters: List[str],
    group_items: Dict[str, List[str]],
    allow_non_ok: bool = False
) -> Tuple[ClusterSampleA, np.ndarray, np.ndarray, dict]:
    """Rebuild cluster-level arrays for Scheme A and V4 m=10."""
    del group_items, allow_non_ok
    n_ac = len(telic_clusters)
    n_bd = len(atelic_clusters)

    ac_cont_lower = np.empty((n_ac, 2, 2), dtype=np.float64)
    ac_cont_upper = np.empty((n_ac, 2, 2), dtype=np.float64)
    ac_cont_frac = [[[Fraction(0) for _ in range(2)] for _ in range(2)] for _ in range(n_ac)]

    bd_cont_lower = np.empty((n_bd, 2, 2), dtype=np.float64)
    bd_cont_upper = np.empty((n_bd, 2, 2), dtype=np.float64)
    bd_cont_frac = [[[Fraction(0) for _ in range(2)] for _ in range(2)] for _ in range(n_bd)]

    bd_l_acc_lower = np.empty((n_bd, 2), dtype=np.float64)
    bd_l_acc_upper = np.empty((n_bd, 2), dtype=np.float64)
    bd_l_acc_frac = [[Fraction(0) for _ in range(2)] for _ in range(n_bd)]

    v4_lower = np.empty((2, 20, 2, 13), dtype=np.float64)
    v4_upper = np.empty((2, 20, 2, 13), dtype=np.float64)

    for i, suffix in enumerate(telic_clusters):
        for role, grp in enumerate(("A", "C")):
            item_id = f"{grp}_{suffix}"
            for j, (task, prompt) in enumerate(CONDITIONS_13):
                key = f"{item_id}/{task}/{prompt}"
                row = unit_map[key]
                st = row["status"]
                q = row.get("q") or {}

                if st == "ok":
                    if task == "L":
                        if q.get("q_status") in ("full", "bounded"):
                            lo, hi = 100.0 * q["q_L"], 100.0 * q["q_U"]
                        else:
                            lo, hi = 0.0, 100.0
                    elif task in ("P", "Ps", "M"):
                        lo = hi = row["value"]
                    else:
                        lo, hi = 0.0, 100.0
                else:
                    lo, hi = 0.0, 100.0
                v4_lower[0, i, role, j] = lo
                v4_upper[0, i, role, j] = hi

            r_pcot = unit_map[f"{item_id}/P/CoT"]
            if r_pcot["status"] == "ok":
                plo = phi = r_pcot["value"]
                p_frac = Fraction(str(r_pcot["value"]))
            else:
                plo, phi = 0.0, 100.0
                p_frac = Fraction(0)
            ac_cont_lower[i, role, 0] = plo
            ac_cont_upper[i, role, 0] = phi
            ac_cont_frac[i][role][0] = p_frac

            r_muz = unit_map[f"{item_id}/M/Z"]
            if r_muz["status"] == "ok":
                mlo = mhi = r_muz["val_u"]
                m_frac = r_muz["val_u_frac"]
            else:
                mlo, mhi = 0.0, 100.0
                m_frac = Fraction(0)
            ac_cont_lower[i, role, 1] = mlo
            ac_cont_upper[i, role, 1] = mhi
            ac_cont_frac[i][role][1] = m_frac

    for i, suffix in enumerate(atelic_clusters):
        for role, grp in enumerate(("B", "D")):
            item_id = f"{grp}_{suffix}"
            for j, (task, prompt) in enumerate(CONDITIONS_13):
                key = f"{item_id}/{task}/{prompt}"
                row = unit_map[key]
                st = row["status"]
                q = row.get("q") or {}

                if st == "ok":
                    if task == "L":
                        if q.get("q_status") in ("full", "bounded"):
                            lo, hi = 100.0 * q["q_L"], 100.0 * q["q_U"]
                        else:
                            lo, hi = 0.0, 100.0
                    elif task in ("P", "Ps", "M"):
                        lo = hi = row["value"]
                    else:
                        lo, hi = 0.0, 100.0
                else:
                    lo, hi = 0.0, 100.0
                v4_lower[1, i, role, j] = lo
                v4_upper[1, i, role, j] = hi

            r_mucot = unit_map[f"{item_id}/M/CoT"]
            if r_mucot["status"] == "ok":
                mclo = mchi = r_mucot["val_u"]
                mc_frac = r_mucot["val_u_frac"]
            else:
                mclo, mchi = 0.0, 100.0
                mc_frac = Fraction(0)
            bd_cont_lower[i, role, 0] = mclo
            bd_cont_upper[i, role, 0] = mchi
            bd_cont_frac[i][role][0] = mc_frac

            r_pcot = unit_map[f"{item_id}/P/CoT"]
            if r_pcot["status"] == "ok":
                plo = phi = r_pcot["value"]
                p_frac = Fraction(str(r_pcot["value"]))
            else:
                plo, phi = 0.0, 100.0
                p_frac = Fraction(0)
            bd_cont_lower[i, role, 1] = plo
            bd_cont_upper[i, role, 1] = phi
            bd_cont_frac[i][role][1] = p_frac

        item_d = f"D_{suffix}"
        gold_d = L_GOLD_STANDARDS["D"]

        r_lcot = unit_map[f"{item_d}/L/CoT"]
        if r_lcot["status"] == "ok":
            acc_val = 1.0 if r_lcot["label"] == gold_d else 0.0
            acc_frac = Fraction(1) if r_lcot["label"] == gold_d else Fraction(0)
            bd_l_acc_lower[i, 0] = acc_val
            bd_l_acc_upper[i, 0] = acc_val
            bd_l_acc_frac[i][0] = acc_frac
        else:
            bd_l_acc_lower[i, 0] = 0.0
            bd_l_acc_upper[i, 0] = 1.0
            bd_l_acc_frac[i][0] = Fraction(0)

        r_lz = unit_map[f"{item_d}/L/Z"]
        if r_lz["status"] == "ok":
            acc_val = 1.0 if r_lz["label"] == gold_d else 0.0
            acc_frac = Fraction(1) if r_lz["label"] == gold_d else Fraction(0)
            bd_l_acc_lower[i, 1] = acc_val
            bd_l_acc_upper[i, 1] = acc_val
            bd_l_acc_frac[i][1] = acc_frac
        else:
            bd_l_acc_lower[i, 1] = 0.0
            bd_l_acc_upper[i, 1] = 1.0
            bd_l_acc_frac[i][1] = Fraction(0)

    sample_a = ClusterSampleA(
        ac_cont_lower=ac_cont_lower,
        ac_cont_upper=ac_cont_upper,
        bd_cont_lower=bd_cont_lower,
        bd_cont_upper=bd_cont_upper,
        bd_l_acc_lower=bd_l_acc_lower,
        bd_l_acc_upper=bd_l_acc_upper,
    )

    rational_data = {
        "ac_cont_frac": ac_cont_frac,
        "bd_cont_frac": bd_cont_frac,
        "bd_l_acc_frac": bd_l_acc_frac,
    }

    return sample_a, v4_lower, v4_upper, rational_data


def load_dataset(
    source_path: str | Path = DEFAULT_SOURCE,
    split_path: str | Path = DEFAULT_SPLIT,
    allow_non_ok: bool = False,
    enforce_hash: bool = True
) -> Dict[str, Any]:
    """Load, verify, and parse SOURCE and SPLIT files."""
    s_path = Path(source_path)
    sp_path = Path(split_path)

    if not s_path.is_file():
        raise FileNotFoundError(f"SOURCE file not found: {s_path}")
    if not sp_path.is_file():
        raise FileNotFoundError(f"SPLIT file not found: {sp_path}")

    s_sha = file_sha256(s_path)
    sp_sha = file_sha256(sp_path)

    if enforce_hash:
        if s_sha != EXPECTED_SOURCE_SHA256:
            raise ValueError(f"SOURCE SHA256 mismatch: got {s_sha}, expected {EXPECTED_SOURCE_SHA256}")
        if sp_sha != EXPECTED_SPLIT_SHA256:
            raise ValueError(f"SPLIT SHA256 mismatch: got {sp_sha}, expected {EXPECTED_SPLIT_SHA256}")

    source_data = json.loads(s_path.read_text(encoding="utf-8"))
    split_data = json.loads(sp_path.read_text(encoding="utf-8"))

    telic_clusters, atelic_clusters, group_items, all_ids = validate_split_structure(split_data)
    unit_map, val_summary = parse_and_validate_source_units(source_data, all_ids, allow_non_ok=allow_non_ok)
    sample_a, v4_lo, v4_hi, rational_data = build_cluster_arrays(
        unit_map, telic_clusters, atelic_clusters, group_items, allow_non_ok=allow_non_ok
    )

    return {
        "sample_a": sample_a,
        "v4_lower": v4_lo,
        "v4_upper": v4_hi,
        "rational_data": rational_data,
        "unit_map": unit_map,
        "split_info": {
            "telic_clusters": telic_clusters,
            "atelic_clusters": atelic_clusters,
            "group_items": group_items,
            "all_ids": all_ids,
        },
        "validation_summary": val_summary,
        "provenance": {
            "source_path": str(s_path),
            "split_path": str(sp_path),
            "source_sha256": s_sha,
            "split_sha256": sp_sha,
            "ignored_source_field": "cluster",
            "enforce_hash": enforce_hash,
            "allow_non_ok": allow_non_ok,
        }
    }
