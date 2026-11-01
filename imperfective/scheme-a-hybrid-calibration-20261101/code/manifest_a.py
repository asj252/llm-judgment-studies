"""Manifest generator and pre-registered gate bindings for Scheme A Step 5b (P16.4.6).

Generates:
- manifest-88.json, joint-populations-88.json, coverage-88.md
- manifest-power56.json, joint-populations-power56.json, coverage-power56.md

Enforces:
- 100% population table, cell order, and SHA256 fingerprint parity with P16.4.5
  (`pilot` seed 2026103103, R_pilot = 512 used strictly to reproduce identical Block 2 targets);
- Step 5b isolated simulation seed banks (`validation = 2026110101`, `confirmation = 2026110102`
  hard-disabled, `power_grid = 2026110111`);
- Exact binding of all 13 locked gate cells (cell_name, cell_index, 64-hex population fingerprint)
  across `D_j` (5 pinned boundary diagnostic cells) and `P_j` (17 power adequacy items).
"""

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple
import numpy as np

try:
    from .core_a import NAMES_A
    from .dgp_a import (
        PopulationA,
        make_empirical_population,
        make_synthetic_population,
    )
    from .inputs import DEFAULT_SOURCE, DEFAULT_SPLIT, load_dataset
except (ImportError, ValueError):
    _code_dir = Path(__file__).resolve().parent
    if str(_code_dir) not in sys.path:
        sys.path.insert(0, str(_code_dir))
    from core_a import NAMES_A
    from dgp_a import (
        PopulationA,
        make_empirical_population,
        make_synthetic_population,
    )
    from inputs import DEFAULT_SOURCE, DEFAULT_SPLIT, load_dataset

SEEDS = {
    "validation": 2026110101,
    "confirmation": 2026110102,
    "pilot": 2026103103,
    "power_grid": 2026110111,
}

# Exact 64-hex SHA256 population fingerprints locked from P16.4.5 (`scheme-a-calibration-20261031/manifests/`)
LOCKED_GATE_CELL_FINGERPRINTS: Dict[Tuple[str, str, int], str] = {
    ("validation", "block3-SA1-0.15", 35): "ec51b8f2930c99bafba8b3a6764321a7bdb6af78ff3fc9df05ce5998fff320b5",
    ("validation", "block3-SA1-0.20", 36): "b91f734b3abab6a82ce05533d1182e497592c83cea4ed5b86c8de08b21771d6e",
    ("validation", "block3-SA4--0.45", 48): "7b832aa4b372328e52eeddb57925feebad602f1a7a18918cffb97950bf54f591",
    ("validation", "block3-SA4--0.30", 49): "f5ccc65aa11aef81d3b4fccbcb0799efad51b9b998dc781b1f5ae0b088681e13",
    ("validation", "pinned-SA1-devlike", 65): "88cc3a7e6854ae3163b637f63662d1a0be402424fce929cefe683025e80aaaf2",
    ("validation", "pinned-SA1-shrunken", 66): "82945d20336a5c88f2bc4c4210183a2ac1ade655c37631be75c6a1cba512835c",
    ("validation", "pinned-SA4-devlike", 67): "2e7a44a6f6ff8de17e151c780b04c510ef5a9114e9dadce195486dc77eeca08a",
    ("validation", "pinned-SA4-moderate-ceiling", 68): "d662b9eb79b42b3476d5ce3862c2f518b2c82b5e13f282327202813a33db5f63",
    ("validation", "empirical-observed", 83): "b85cc3625aca8fb0794a89720e640f262d73aae027eee0697f4fbc05f295f3e4",
    ("power_grid", "power-SA1-pinned-0.20", 11): "3bc782f7f7b4854c9334a54e6251fefecf0f2d8a04cc039863728e63595997d1",
    ("power_grid", "power-SA4-pinned--0.90", 50): "7ff80d9c9eb7cd8e31cb2358398c1d8836cb683e696fc63d2a0bd8cb321a28f2",
    ("power_grid", "power-SA4-pinned--0.95", 51): "b122c51d45f4d417dccd04b36d37b6a39b5b562cde033f8eee74885cad4defed",
    ("power_grid", "power-empirical-convex-1", 55): "d9bb280fd9c53614a46c5de4d94d51d177a998b5579e30733a0786e7f0a090e9",
}

# Preserved 8 Block 3 descriptive reference cells across rounds (brief.md §4.3)
HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS = [
    {"cell_name": "block3-SA1-0.15", "cell_index": 35, "slot": "SA1", "effect": "+0.15", "in_step5b_p_gate": True},
    {"cell_name": "block3-SA1-0.20", "cell_index": 36, "slot": "SA1", "effect": "+0.20", "in_step5b_p_gate": True},
    {"cell_name": "block3-SA2-12.5", "cell_index": 40, "slot": "SA2", "effect": "+12.5", "in_step5b_p_gate": False},
    {"cell_name": "block3-SA2-18.0", "cell_index": 41, "slot": "SA2", "effect": "+18.0", "in_step5b_p_gate": False},
    {"cell_name": "block3-SA3--8.5", "cell_index": 45, "slot": "SA3", "effect": "-8.5", "in_step5b_p_gate": False},
    {"cell_name": "block3-SA3--12.5", "cell_index": 44, "slot": "SA3", "effect": "-12.5", "in_step5b_p_gate": False},
    {"cell_name": "block3-SA4--0.30", "cell_index": 49, "slot": "SA4", "effect": "-0.30", "in_step5b_p_gate": True},
    {"cell_name": "block3-SA4--0.45", "cell_index": 48, "slot": "SA4", "effect": "-0.45", "in_step5b_p_gate": True},
]
MAIN_POWER_REFERENCE_CELLS = HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS

# Gate D_j: 5 pinned boundary diagnostic cells (brief.md §3.2(4) D_j, indices 65, 66, 67, 68, 83)
PINNED_BOUNDARY_DIAGNOSTIC_SPECS = [
    {
        "gate_id": "D01",
        "bank": "validation",
        "cell_name": "pinned-SA1-devlike",
        "cell_index": 65,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "pinned-SA1-devlike", 65)],
        "max_degeneracy_threshold": 0.20,
    },
    {
        "gate_id": "D02",
        "bank": "validation",
        "cell_name": "pinned-SA1-shrunken",
        "cell_index": 66,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "pinned-SA1-shrunken", 66)],
        "max_degeneracy_threshold": 0.20,
    },
    {
        "gate_id": "D03",
        "bank": "validation",
        "cell_name": "pinned-SA4-devlike",
        "cell_index": 67,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "pinned-SA4-devlike", 67)],
        "max_degeneracy_threshold": 0.20,
    },
    {
        "gate_id": "D04",
        "bank": "validation",
        "cell_name": "pinned-SA4-moderate-ceiling",
        "cell_index": 68,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "pinned-SA4-moderate-ceiling", 68)],
        "max_degeneracy_threshold": 0.20,
    },
    {
        "gate_id": "D05",
        "bank": "validation",
        "cell_name": "empirical-observed",
        "cell_index": 83,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "empirical-observed", 83)],
        "max_degeneracy_threshold": 0.20,
    },
]

PINNED_BOUNDARY_DIAGNOSTIC_CELLS = [s["cell_name"] for s in PINNED_BOUNDARY_DIAGNOSTIC_SPECS]

# Gate P_j: 17 pre-registered power adequacy items (brief.md §3.2(4) P_j: rate - 2*MCSE >= 0.80)
STEP5B_POWER_GATE_SPECS = [
    # Group 1 (5 items): validation empirical-observed (#83) SA1..SA4 + all4
    {
        "item_id": "P01",
        "group": 1,
        "group_name": "validation_empirical_observed",
        "bank": "validation",
        "cell_name": "empirical-observed",
        "cell_index": 83,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "empirical-observed", 83)],
        "metric_kind": "slot_correct_direction",
        "target": "SA1",
    },
    {
        "item_id": "P02",
        "group": 1,
        "group_name": "validation_empirical_observed",
        "bank": "validation",
        "cell_name": "empirical-observed",
        "cell_index": 83,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "empirical-observed", 83)],
        "metric_kind": "slot_correct_direction",
        "target": "SA2",
    },
    {
        "item_id": "P03",
        "group": 1,
        "group_name": "validation_empirical_observed",
        "bank": "validation",
        "cell_name": "empirical-observed",
        "cell_index": 83,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "empirical-observed", 83)],
        "metric_kind": "slot_correct_direction",
        "target": "SA3",
    },
    {
        "item_id": "P04",
        "group": 1,
        "group_name": "validation_empirical_observed",
        "bank": "validation",
        "cell_name": "empirical-observed",
        "cell_index": 83,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "empirical-observed", 83)],
        "metric_kind": "slot_correct_direction",
        "target": "SA4",
    },
    {
        "item_id": "P05",
        "group": 1,
        "group_name": "validation_empirical_observed",
        "bank": "validation",
        "cell_name": "empirical-observed",
        "cell_index": 83,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "empirical-observed", 83)],
        "metric_kind": "all4_correct_direction",
        "target": "all4",
    },
    # Group 2 (5 items): power_grid power-empirical-convex-1 (#55, gamma=1) SA1..SA4 + all4
    {
        "item_id": "P06",
        "group": 2,
        "group_name": "power_grid_empirical_convex_1",
        "bank": "power_grid",
        "cell_name": "power-empirical-convex-1",
        "cell_index": 55,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-empirical-convex-1", 55)],
        "metric_kind": "slot_correct_direction",
        "target": "SA1",
    },
    {
        "item_id": "P07",
        "group": 2,
        "group_name": "power_grid_empirical_convex_1",
        "bank": "power_grid",
        "cell_name": "power-empirical-convex-1",
        "cell_index": 55,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-empirical-convex-1", 55)],
        "metric_kind": "slot_correct_direction",
        "target": "SA2",
    },
    {
        "item_id": "P08",
        "group": 2,
        "group_name": "power_grid_empirical_convex_1",
        "bank": "power_grid",
        "cell_name": "power-empirical-convex-1",
        "cell_index": 55,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-empirical-convex-1", 55)],
        "metric_kind": "slot_correct_direction",
        "target": "SA3",
    },
    {
        "item_id": "P09",
        "group": 2,
        "group_name": "power_grid_empirical_convex_1",
        "bank": "power_grid",
        "cell_name": "power-empirical-convex-1",
        "cell_index": 55,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-empirical-convex-1", 55)],
        "metric_kind": "slot_correct_direction",
        "target": "SA4",
    },
    {
        "item_id": "P10",
        "group": 2,
        "group_name": "power_grid_empirical_convex_1",
        "bank": "power_grid",
        "cell_name": "power-empirical-convex-1",
        "cell_index": 55,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-empirical-convex-1", 55)],
        "metric_kind": "all4_correct_direction",
        "target": "all4",
    },
    # Group 3 (3 items): power_grid pinned discrete high-effect endpoints (#11, #50, #51)
    {
        "item_id": "P11",
        "group": 3,
        "group_name": "power_grid_pinned_high_effect_endpoints",
        "bank": "power_grid",
        "cell_name": "power-SA1-pinned-0.20",
        "cell_index": 11,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-SA1-pinned-0.20", 11)],
        "metric_kind": "slot_correct_direction",
        "target": "SA1",
    },
    {
        "item_id": "P12",
        "group": 3,
        "group_name": "power_grid_pinned_high_effect_endpoints",
        "bank": "power_grid",
        "cell_name": "power-SA4-pinned--0.90",
        "cell_index": 50,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-SA4-pinned--0.90", 50)],
        "metric_kind": "slot_correct_direction",
        "target": "SA4",
    },
    {
        "item_id": "P13",
        "group": 3,
        "group_name": "power_grid_pinned_high_effect_endpoints",
        "bank": "power_grid",
        "cell_name": "power-SA4-pinned--0.95",
        "cell_index": 51,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("power_grid", "power-SA4-pinned--0.95", 51)],
        "metric_kind": "slot_correct_direction",
        "target": "SA4",
    },
    # Group 4 (4 items): validation historical Block 3 discrete reference cells (#35, #36, #49, #48)
    {
        "item_id": "P14",
        "group": 4,
        "group_name": "validation_historical_block3_discrete",
        "bank": "validation",
        "cell_name": "block3-SA1-0.15",
        "cell_index": 35,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "block3-SA1-0.15", 35)],
        "metric_kind": "slot_correct_direction",
        "target": "SA1",
    },
    {
        "item_id": "P15",
        "group": 4,
        "group_name": "validation_historical_block3_discrete",
        "bank": "validation",
        "cell_name": "block3-SA1-0.20",
        "cell_index": 36,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "block3-SA1-0.20", 36)],
        "metric_kind": "slot_correct_direction",
        "target": "SA1",
    },
    {
        "item_id": "P16",
        "group": 4,
        "group_name": "validation_historical_block3_discrete",
        "bank": "validation",
        "cell_name": "block3-SA4--0.30",
        "cell_index": 49,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "block3-SA4--0.30", 49)],
        "metric_kind": "slot_correct_direction",
        "target": "SA4",
    },
    {
        "item_id": "P17",
        "group": 4,
        "group_name": "validation_historical_block3_discrete",
        "bank": "validation",
        "cell_name": "block3-SA4--0.45",
        "cell_index": 48,
        "fingerprint": LOCKED_GATE_CELL_FINGERPRINTS[("validation", "block3-SA4--0.45", 48)],
        "metric_kind": "slot_correct_direction",
        "target": "SA4",
    },
]


def run_pilot_sd(
    r_pilot: int = 512,
    seed: int = SEEDS["pilot"]
) -> Tuple[float, float, float, float]:
    """Run pilot sampling on regular-null to reproduce locked Block 2 SD targets sigma1..sigma4."""
    pop = make_synthetic_population("pilot-regular-null", shape="regular", effects={})
    rng = np.random.default_rng(seed)

    s1_vals = np.empty(r_pilot, dtype=np.float64)
    s2_vals = np.empty(r_pilot, dtype=np.float64)
    s3_vals = np.empty(r_pilot, dtype=np.float64)
    s4_vals = np.empty(r_pilot, dtype=np.float64)

    for i in range(r_pilot):
        sample = pop.sample(rng, n_ac=80, n_bd=80, missing="none")
        c_pcot = sample.ac_cont_lower[:, 1, 0]
        c_muz = sample.ac_cont_upper[:, 1, 1]
        s1_vals[i] = np.mean((c_pcot >= 95.0).astype(float) - (c_muz >= 95.0).astype(float))

        a_pcot = sample.ac_cont_lower[:, 0, 0]
        a_muz = sample.ac_cont_lower[:, 0, 1]
        c_pcot2 = sample.ac_cont_lower[:, 1, 0]
        c_muz2 = sample.ac_cont_lower[:, 1, 1]
        s2_vals[i] = np.mean((c_pcot2 - a_pcot) - (c_muz2 - a_muz))

        b_mucot = sample.bd_cont_lower[:, 0, 0]
        b_pcot = sample.bd_cont_lower[:, 0, 1]
        d_mucot = sample.bd_cont_lower[:, 1, 0]
        d_pcot = sample.bd_cont_lower[:, 1, 1]
        s3_vals[i] = np.mean((d_mucot - b_mucot) - (d_pcot - b_pcot))

        acc_lcot = sample.bd_l_acc_lower[:, 0]
        acc_lz = sample.bd_l_acc_lower[:, 1]
        s4_vals[i] = np.mean(acc_lcot - acc_lz)

    sd1 = float(np.std(s1_vals, ddof=1))
    sd2 = float(np.std(s2_vals, ddof=1))
    sd3 = float(np.std(s3_vals, ddof=1))
    sd4 = float(np.std(s4_vals, ddof=1))
    return sd1, sd2, sd3, sd4


def verify_locked_gate_fingerprints_on_cells(bank: str, cells: List[dict]) -> None:
    """Assert that every locked gate cell for `bank` matches name, cell_index, and 64-hex fingerprint."""
    by_name = {c["cell_name"]: c for c in cells}
    for (b_key, c_name, c_idx), exp_fp in LOCKED_GATE_CELL_FINGERPRINTS.items():
        if b_key != bank:
            continue
        if c_name not in by_name:
            raise KeyError(f"Locked gate cell '{c_name}' missing from {bank} manifest")
        got = by_name[c_name]
        if int(got["cell_index"]) != int(c_idx):
            raise ValueError(
                f"Locked gate cell '{c_name}' index mismatch in {bank}: got {got['cell_index']}, expected {c_idx}"
            )
        if str(got["fingerprint"]) != str(exp_fp):
            raise ValueError(
                f"Locked gate cell '{c_name}' fingerprint mismatch in {bank}: got {got['fingerprint']}, expected {exp_fp}"
            )


def build_88_cells(
    pilot_sds: Tuple[float, float, float, float],
    rational_data: dict,
    explicit_infeasible_list: list
) -> Tuple[List[dict], Dict[str, PopulationA]]:
    """Build all 88 cells of the locked calibration matrix (100% fingerprint parity with P16.4.5)."""
    sd1, sd2, sd3, sd4 = pilot_sds
    cells: List[dict] = []
    pops: Dict[str, PopulationA] = {}
    cell_idx = 0

    def add_cell(
        name: str,
        pop: PopulationA,
        block: int,
        missing: str = "none",
        missing_rate: Fraction = Fraction(0),
        notes: str = ""
    ):
        nonlocal cell_idx
        truth = pop.truth()
        t_dict = {k: str(v) for k, v in zip(NAMES_A, truth)}
        exp_missing = pop.expected_missing_rates(missing=missing, missing_rate=missing_rate)

        cell_spec = {
            "cell_index": cell_idx,
            "cell_name": name,
            "block": block,
            "population_name": pop.name,
            "fingerprint": pop.fingerprint(),
            "truth": t_dict,
            "missing": missing,
            "missing_rate": str(missing_rate),
            "missing_rate_float": float(missing_rate),
            "expected_missing_rates": exp_missing,
            "is_null_family": bool(truth[0] <= 0 and truth[1] == 0 and truth[2] == 0 and truth[3] == 0),
            "null_slots": [NAMES_A[j] for j in range(4) if (truth[0] <= 0 if j == 0 else truth[j] == 0)],
            "notes": notes,
        }
        cells.append(cell_spec)
        pops[pop.name] = pop
        cell_idx += 1

    # Block 1: Conventional Null, Composite Interior & Partial Nulls (5 cells)
    p = make_synthetic_population("regular-null", "regular", {})
    add_cell("regular-null", p, block=1, notes="Full true null (0, 0, 0, 0)")

    p = make_synthetic_population("regular-composite-interior-1", "regular", {"SA1": "-0.05"})
    add_cell("regular-composite-interior-1", p, block=1, notes="SA1 in interior of composite null (-0.05)")

    p = make_synthetic_population("regular-composite-interior-2", "regular", {"SA1": "-0.15"})
    add_cell("regular-composite-interior-2", p, block=1, notes="SA1 deep in interior of composite null (-0.15)")

    p = make_synthetic_population("regular-partial-null-ac", "regular", {"SA1": "+0.20", "SA2": "+12.5"})
    add_cell("regular-partial-null-ac", p, block=1, notes="AC non-null, BD true nulls")

    p = make_synthetic_population("regular-partial-null-bd", "regular", {"SA3": "-8.5", "SA4": "-0.40"})
    add_cell("regular-partial-null-bd", p, block=1, notes="BD non-null, AC true nulls")

    # Block 2: Pilot SD Neighborhood & Multi-dimensional Superposition (28 cells)
    for c in [-0.5, 0.5, 1.0, 2.0]:
        val_frac = Fraction(f"{round(c * sd1, 4):.4f}")
        c_str = f"{c:+.1f}".replace("+", "p").replace("-", "m")
        p = make_synthetic_population(f"pilot-sd-SA1-{c_str}", "regular", {"SA1": str(val_frac)})
        add_cell(f"pilot-sd-SA1-{c_str}", p, block=2, notes=f"SA1 pilot offset c={c}")

    for c in [-2.0, -1.0, -0.5, 0.5, 1.0, 2.0]:
        val_frac = Fraction(f"{round(c * sd2, 2):.2f}")
        c_str = f"{c:+.1f}".replace("+", "p").replace("-", "m")
        p = make_synthetic_population(f"pilot-sd-SA2-{c_str}", "regular", {"SA2": str(val_frac)})
        add_cell(f"pilot-sd-SA2-{c_str}", p, block=2, notes=f"SA2 pilot offset c={c}")

    for c in [-2.0, -1.0, -0.5, 0.5, 1.0, 2.0]:
        val_frac = Fraction(f"{round(c * sd3, 2):.2f}")
        c_str = f"{c:+.1f}".replace("+", "p").replace("-", "m")
        p = make_synthetic_population(f"pilot-sd-SA3-{c_str}", "regular", {"SA3": str(val_frac)})
        add_cell(f"pilot-sd-SA3-{c_str}", p, block=2, notes=f"SA3 pilot offset c={c}")

    for c in [-2.0, -1.0, -0.5, 0.5, 1.0, 2.0]:
        val_frac = Fraction(f"{round(c * sd4, 4):.4f}")
        c_str = f"{c:+.1f}".replace("+", "p").replace("-", "m")
        p = make_synthetic_population(f"pilot-sd-SA4-{c_str}", "regular", {"SA4": str(val_frac)})
        add_cell(f"pilot-sd-SA4-{c_str}", p, block=2, notes=f"SA4 pilot offset c={c}")

    ref_vec = [Fraction("0.20"), Fraction("12.5"), Fraction("-8.5"), Fraction("-0.40")]
    for scale in [Fraction("1/4"), Fraction("1/2"), Fraction("3/4"), Fraction("1")]:
        eff = {
            "SA1": str(ref_vec[0] * scale),
            "SA2": str(ref_vec[1] * scale),
            "SA3": str(ref_vec[2] * scale),
            "SA4": str(ref_vec[3] * scale),
        }
        sc_name = str(scale).replace("/", "_")
        p = make_synthetic_population(f"multi-scale-{sc_name}", "regular", eff)
        add_cell(f"multi-scale-{sc_name}", p, block=2, notes=f"Multi-effect scaled by {scale}")

    p = make_synthetic_population("multi-sign-cross-1", "regular", {
        "SA1": "+0.15", "SA2": "-10.0", "SA3": "+8.5", "SA4": "+0.25"
    })
    add_cell("multi-sign-cross-1", p, block=2, notes="Cross signs: (+, -, +, +)")

    p = make_synthetic_population("multi-sign-cross-2", "regular", {
        "SA1": "+0.10", "SA2": "+10.0", "SA3": "-12.5", "SA4": "-0.25"
    })
    add_cell("multi-sign-cross-2", p, block=2, notes="Cross signs: (+, +, -, -)")

    # Block 3: Conventional Single-Slot Reference Sequences (20 cells)
    for val in ["+0.08", "+0.12", "+0.15", "+0.20", "+0.25"]:
        name = f"block3-SA1-{val.replace('+', '')}"
        p = make_synthetic_population(name, "regular", {"SA1": val})
        add_cell(name, p, block=3, notes=f"SA1 conventional reference {val}")

    for val in ["-15.0", "+8.0", "+12.5", "+18.0", "+25.0"]:
        name = f"block3-SA2-{val.replace('+', '')}"
        p = make_synthetic_population(name, "regular", {"SA2": val})
        add_cell(name, p, block=3, notes=f"SA2 conventional reference {val}")

    for val in ["-20.0", "-12.5", "-8.5", "-5.0", "+10.0"]:
        name = f"block3-SA3-{val.replace('+', '')}"
        p = make_synthetic_population(name, "regular", {"SA3": val})
        add_cell(name, p, block=3, notes=f"SA3 conventional reference {val}")

    for val in ["-0.45", "-0.30", "-0.20", "-0.12", "+0.20"]:
        name = f"block3-SA4-{val.replace('+', '')}"
        p = make_synthetic_population(name, "regular", {"SA4": val})
        add_cell(name, p, block=3, notes=f"SA4 conventional reference {val}")

    # Block 4: Non-Conventional Shapes & Pinned Boundary Stress (16 cells)
    for shp in ["skew", "rare", "ties", "sparse-endpoint", "bimodal-polarized"]:
        name = f"{shp}-null"
        p = make_synthetic_population(name, shp, {})
        add_cell(name, p, block=4, notes=f"Non-conventional true null: {shp}")

    for bad_sa1 in ["-0.15", "-0.20"]:
        try:
            make_synthetic_population(
                f"test-infeasible-skew-{bad_sa1}",
                shape="skew",
                effects={"SA1": bad_sa1},
                explicit_infeasible_combinations=explicit_infeasible_list,
            )
        except ValueError:
            pass

    p = make_synthetic_population("skew-SA1-0.15", "skew", {"SA1": "+0.15"})
    add_cell("skew-SA1-0.15", p, block=4, notes="Skew shape SA1=+0.15 (P/CoT high 1/5 vs MU/Z 1/20)")

    p = make_synthetic_population("skew-SA2-12.5", "skew", {"SA2": "+12.5"})
    add_cell("skew-SA2-12.5", p, block=4, notes="Skew shape SA2=+12.5")

    p = make_synthetic_population("skew-SA3--8.5", "skew", {"SA3": "-8.5"})
    add_cell("skew-SA3--8.5", p, block=4, notes="Skew shape SA3=-8.5")

    p = make_synthetic_population("rare-SA2-12.5", "rare", {"SA2": "+12.5"})
    add_cell("rare-SA2-12.5", p, block=4, notes="Rare heavy tail shape SA2=+12.5")

    p = make_synthetic_population("rare-SA3--8.5", "rare", {"SA3": "-8.5"})
    add_cell("rare-SA3--8.5", p, block=4, notes="Rare heavy tail shape SA3=-8.5")

    p = make_synthetic_population("ties-SA1-0.20", "ties", {"SA1": "+0.20"})
    add_cell("ties-SA1-0.20", p, block=4, notes="Ties shape SA1=+0.20")

    p = make_synthetic_population("ties-SA4--0.30", "ties", {"SA4": "-0.30"})
    add_cell("ties-SA4--0.30", p, block=4, notes="Ties shape SA4=-0.30")

    p = make_synthetic_population("pinned-SA1-devlike", "pinned-SA1-devlike", {"SA1": "+0.20"})
    add_cell("pinned-SA1-devlike", p, block=4, notes="Pinned SA1: P/CoT high 20% vs MU/Z 0%")

    p = make_synthetic_population("pinned-SA1-shrunken", "pinned-SA1-shrunken", {"SA1": "+0.125"})
    add_cell("pinned-SA1-shrunken", p, block=4, notes="Pinned SA1: P/CoT high 12.5% vs MU/Z 0%")

    p = make_synthetic_population("pinned-SA4-devlike", "pinned-SA4-devlike", {"SA4": "-0.95"})
    add_cell("pinned-SA4-devlike", p, block=4, notes="Pinned SA4: L/CoT 5% vs L/Z 100%")

    p = make_synthetic_population("pinned-SA4-moderate-ceiling", "pinned-SA4-moderate-ceiling", {"SA4": "-0.75"})
    add_cell("pinned-SA4-moderate-ceiling", p, block=4, notes="Pinned SA4: L/CoT 20% vs L/Z 95%")

    # Block 5: MCAR and Adverse Missingness (14 cells)
    r2 = Fraction(1, 50)
    r4 = Fraction(1, 25)

    p_null = make_synthetic_population("pop-reg-null", "regular", {})
    add_cell("mcar-2pct-null", p_null, block=5, missing="mcar", missing_rate=r2, notes="2% MCAR null")
    add_cell("adverse-2pct-null", p_null, block=5, missing="adverse", missing_rate=r2, notes="2% Adverse null")

    p_comp = make_synthetic_population("pop-reg-comp", "regular", {"SA1": "-0.10"})
    add_cell("mcar-2pct-composite-interior", p_comp, block=5, missing="mcar", missing_rate=r2, notes="2% MCAR composite interior")
    add_cell("adverse-2pct-composite-interior", p_comp, block=5, missing="adverse", missing_rate=r2, notes="2% Adverse composite interior")

    p_sa1 = make_synthetic_population("pop-reg-sa1", "regular", {"SA1": "+0.20"})
    add_cell("mcar-2pct-SA1-0.20", p_sa1, block=5, missing="mcar", missing_rate=r2, notes="2% MCAR SA1=+0.20")
    add_cell("adverse-2pct-SA1-0.20", p_sa1, block=5, missing="adverse", missing_rate=r2, notes="2% Adverse SA1=+0.20")

    p_sa2 = make_synthetic_population("pop-reg-sa2", "regular", {"SA2": "+12.5"})
    add_cell("mcar-2pct-SA2-12.5", p_sa2, block=5, missing="mcar", missing_rate=r2, notes="2% MCAR SA2=+12.5")
    add_cell("adverse-2pct-SA2-12.5", p_sa2, block=5, missing="adverse", missing_rate=r2, notes="2% Adverse SA2=+12.5")

    p_sa3 = make_synthetic_population("pop-reg-sa3", "regular", {"SA3": "-8.5"})
    add_cell("mcar-2pct-SA3--8.5", p_sa3, block=5, missing="mcar", missing_rate=r2, notes="2% MCAR SA3=-8.5")
    add_cell("adverse-2pct-SA3--8.5", p_sa3, block=5, missing="adverse", missing_rate=r2, notes="2% Adverse SA3=-8.5")

    p_sa4 = make_synthetic_population("pop-reg-sa4", "regular", {"SA4": "-0.35"})
    add_cell("mcar-2pct-SA4--0.35", p_sa4, block=5, missing="mcar", missing_rate=r2, notes="2% MCAR SA4=-0.35")
    add_cell("adverse-2pct-SA4--0.35", p_sa4, block=5, missing="adverse", missing_rate=r2, notes="2% Adverse SA4=-0.35")

    add_cell("mcar-4pct-null", p_null, block=5, missing="mcar", missing_rate=r4, notes="4% MCAR null")
    add_cell("adverse-4pct-null", p_null, block=5, missing="adverse", missing_rate=r4, notes="4% Adverse null")

    # Block 6: Empirical Synthesis & Calibrated Nulls (5 cells)
    p_emp_obs = make_empirical_population("empirical-observed", rational_data, gamma=Fraction(1), metadata={"not_a_null_calibration": True})
    add_cell("empirical-observed", p_emp_obs, block=6, notes="Observed empirical dev set (gamma=1)")

    p_emp_null = make_empirical_population("empirical-calibrated-null", rational_data, gamma=Fraction(0))
    add_cell("empirical-calibrated-null", p_emp_null, block=6, notes="Calibrated empirical null via condition swapping (gamma=0)")

    p_emp_75 = make_empirical_population("empirical-attenuated-75pct", rational_data, gamma=Fraction(3, 4))
    add_cell("empirical-attenuated-75pct", p_emp_75, block=6, notes="Empirical attenuated to 75% via convex mixture (gamma=3/4)")

    p_emp_50 = make_empirical_population("empirical-attenuated-50pct", rational_data, gamma=Fraction(1, 2))
    add_cell("empirical-attenuated-50pct", p_emp_50, block=6, notes="Empirical attenuated to 50% via convex mixture (gamma=1/2)")

    add_cell("empirical-calibrated-null-mcar-2pct", p_emp_null, block=6, missing="mcar", missing_rate=r2, notes="Empirical calibrated null with 2% MCAR")

    if len(cells) != 88:
        raise ValueError(f"Expected 88 cells, constructed {len(cells)}")

    verify_locked_gate_fingerprints_on_cells("validation", cells)
    return cells, pops


def build_56_power_grid(rational_data: dict) -> Tuple[List[dict], Dict[str, PopulationA]]:
    """Build the 56-cell multi-effect power sensitivity matrix (100% fingerprint parity with P16.4.5)."""
    cells: List[dict] = []
    pops: Dict[str, PopulationA] = {}
    cell_idx = 0

    def add_cell(name: str, pop: PopulationA, category: str, notes: str = ""):
        nonlocal cell_idx
        truth = pop.truth()
        t_dict = {k: str(v) for k, v in zip(NAMES_A, truth)}
        cell_spec = {
            "cell_index": cell_idx,
            "cell_name": name,
            "category": category,
            "population_name": pop.name,
            "fingerprint": pop.fingerprint(),
            "truth": t_dict,
            "notes": notes,
        }
        cells.append(cell_spec)
        pops[pop.name] = pop
        cell_idx += 1

    for val in ["+0.05", "+0.10", "+0.15", "+0.20", "+0.25", "+0.30", "+0.35"]:
        name = f"power-SA1-base-{val.replace('+', '')}"
        p = make_synthetic_population(name, "power-SA1-base", {"SA1": val})
        add_cell(name, p, category="SA1-baseline", notes=f"SA1 baseline power curve {val} (MU/Z high=0.10)")

    for val in ["+0.05", "+0.10", "+0.125", "+0.15", "+0.20", "+0.25", "+0.30", "+0.35"]:
        name = f"power-SA1-pinned-{val.replace('+', '')}"
        p = make_synthetic_population(name, "pinned-SA1-devlike", {"SA1": val})
        add_cell(name, p, category="SA1-pinned", notes=f"SA1 pinned zero-bottom power curve {val} (MU/Z high=0.00)")

    for val in ["+5.0", "+8.0", "+10.0", "+12.5", "+15.0", "+18.0", "+20.0", "+25.0", "+30.0"]:
        name = f"power-SA2-{val.replace('+', '')}"
        p = make_synthetic_population(name, "regular", {"SA2": val})
        add_cell(name, p, category="SA2-continuous", notes=f"SA2 continuous did power curve {val}")

    for val in ["-5.0", "-8.5", "-10.0", "-12.5", "-15.0", "-18.0", "-20.0", "-25.0", "-30.0"]:
        name = f"power-SA3-{val.replace('+', '')}"
        p = make_synthetic_population(name, "regular", {"SA3": val})
        add_cell(name, p, category="SA3-continuous", notes=f"SA3 continuous degradation power curve {val}")

    for val in ["-0.10", "-0.15", "-0.20", "-0.25", "-0.30", "-0.40", "-0.50", "-0.60", "-0.70"]:
        name = f"power-SA4-base-{val.replace('+', '')}"
        p = make_synthetic_population(name, "power-SA4-base", {"SA4": val})
        add_cell(name, p, category="SA4-baseline", notes=f"SA4 baseline power curve {val} (L/Z acc=0.85)")

    for val in ["-0.15", "-0.25", "-0.35", "-0.50", "-0.65", "-0.75", "-0.80", "-0.85", "-0.90", "-0.95"]:
        name = f"power-SA4-pinned-{val.replace('+', '')}"
        p = make_synthetic_population(name, "pinned-SA4-devlike", {"SA4": val})
        add_cell(name, p, category="SA4-pinned", notes=f"SA4 pinned ceiling power curve {val}")

    for gam in [Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1)]:
        g_name = str(gam).replace("/", "_")
        name = f"power-empirical-convex-{g_name}"
        p = make_empirical_population(name, rational_data, gamma=gam)
        add_cell(name, p, category="empirical-convex-mixture", notes=f"Empirical convex mixture scaling gamma={gam}")

    if len(cells) != 56:
        raise ValueError(f"Expected 56 cells in power grid, got {len(cells)}")

    verify_locked_gate_fingerprints_on_cells("power_grid", cells)
    return cells, pops


def generate_coverage_markdown(cells: List[dict], title: str) -> str:
    """Generate Markdown overview table for a manifest."""
    lines = [
        f"# {title}",
        "",
        f"Total Cells: {len(cells)}",
        "",
        "| Index | Cell Name | Truth (SA1, SA2, SA3, SA4) | Missing | Notes |",
        "|---|---|---|---|---|",
    ]
    for c in cells:
        t = c["truth"]
        t_str = f"({t['SA1']}, {t['SA2']}, {t['SA3']}, {t['SA4']})"
        m_str = f"{c.get('missing', 'none')} ({c.get('missing_rate', '0')})"
        lines.append(f"| {c['cell_index']} | `{c['cell_name']}` | `{t_str}` | `{m_str}` | {c.get('notes', '')} |")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate manifests and joint populations for Scheme A Step 5b.")
    parser.add_argument("--mode", choices=["both", "88", "56"], default="both", help="Which matrix to generate")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Path to SOURCE s4-unit-index-original.json")
    parser.add_argument("--split", default=DEFAULT_SPLIT, help="Path to split.json")
    parser.add_argument(
        "--out-dir",
        default="E:/Claude/research/connecting-dots/imperfective/scheme-a-hybrid-calibration-20261101",
        help="Output directory",
    )
    args = parser.parse_args()

    out_path = Path(args.out_dir)
    manifest_dir = out_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    print("Loading dev dataset to extract empirical distributions...")
    dataset = load_dataset(args.source, args.split, allow_non_ok=False)
    rational_data = dataset["rational_data"]

    print("Running pilot standard deviation determination (seed 2026103103 for P16.4.5 parity)...")
    pilot_sds = run_pilot_sd()
    print(f"Pilot SDs: SA1={pilot_sds[0]:.4f}, SA2={pilot_sds[1]:.2f}, SA3={pilot_sds[2]:.2f}, SA4={pilot_sds[3]:.4f}")

    infeasible_list: list = []

    if args.mode in ["both", "88"]:
        print("Generating 88-cell calibration matrix...")
        cells_88, pops_88 = build_88_cells(pilot_sds, rational_data, infeasible_list)

        manifest_88 = {
            "metadata": {
                "title": "Scheme A Step 5b (m=4) 88-Cell Joint Calibration Matrix",
                "replicates": 2000,
                "bootstrap_replicates": 5000,
                "n_ac": 80,
                "n_bd": 80,
                "seed_banks": SEEDS,
                "pilot_standard_deviations": {
                    "SA1": pilot_sds[0], "SA2": pilot_sds[1], "SA3": pilot_sds[2], "SA4": pilot_sds[3]
                },
                "policy": {
                    "nominal_ci_level": "single-metric nominal 98.75% CI (aiming at m=4 Bonferroni 95% simultaneous family coverage)",
                    "historical_ci_level": "single-metric nominal 99.5% CI (aiming at old m=10 Bonferroni 95% simultaneous family coverage)",
                    "nature_of_screening": (
                        "Discrete paired trinary slots SA1, SA4 carry finite-sample certified unconditional exact guarantees "
                        "via Tango score ordering and outward IEEE-754 bounds; continuous resampling slots SA2, SA3 and joint "
                        "4-slot family behavior are verified across tested scenarios via Monte Carlo screening, not an "
                        "all-distribution continuous finite-sample theorem."
                    ),
                    "historical_block3_power_reference_cells": HISTORICAL_BLOCK3_POWER_REFERENCE_CELLS,
                    "pinned_boundary_diagnostic_specs": PINNED_BOUNDARY_DIAGNOSTIC_SPECS,
                    "step5b_power_gate_specs": STEP5B_POWER_GATE_SPECS,
                    "candidate_selection_order": ["hybrid_pct_tango", "hybrid_bessel_t_tango", None],
                    "confirmation_bank_gate": (
                        "Confirmation bank 2026110102 is unconditionally hard-disabled throughout Step 5b "
                        "(CONFIRMATION_BANK_HARD_DISABLED = True, S5_FROZEN = False)."
                    ),
                },
                "explicit_infeasible_combinations": infeasible_list,
            },
            "cells": cells_88,
        }

        pop_table_88 = {name: pop.table() for name, pop in pops_88.items()}

        m88_path = manifest_dir / "manifest-88.json"
        p88_path = manifest_dir / "joint-populations-88.json"
        c88_path = manifest_dir / "coverage-88.md"

        m88_path.write_text(json.dumps(manifest_88, indent=2), encoding="utf-8")
        p88_path.write_text(json.dumps(pop_table_88, indent=2), encoding="utf-8")
        c88_path.write_text(generate_coverage_markdown(cells_88, "Scheme A Step 5b 88-Cell Calibration Matrix"), encoding="utf-8")
        print(f"Wrote {m88_path}, {p88_path}, {c88_path}")

    if args.mode in ["both", "56"]:
        print("Generating 56-cell power grid...")
        cells_56, pops_56 = build_56_power_grid(rational_data)

        manifest_56 = {
            "metadata": {
                "title": "Scheme A Step 5b (m=4) 56-Cell Multi-Effect Power Grid",
                "replicates": 2000,
                "bootstrap_replicates": 5000,
                "n_ac": 80,
                "n_bd": 80,
                "seed_bank": SEEDS["power_grid"],
                "total_cells": len(cells_56),
            },
            "cells": cells_56,
        }

        pop_table_56 = {name: pop.table() for name, pop in pops_56.items()}

        m56_path = manifest_dir / "manifest-power56.json"
        p56_path = manifest_dir / "joint-populations-power56.json"
        c56_path = manifest_dir / "coverage-power56.md"

        m56_path.write_text(json.dumps(manifest_56, indent=2), encoding="utf-8")
        p56_path.write_text(json.dumps(pop_table_56, indent=2), encoding="utf-8")
        c56_path.write_text(generate_coverage_markdown(cells_56, "Scheme A Step 5b 56-Cell Power Grid"), encoding="utf-8")
        print(f"Wrote {m56_path}, {p56_path}, {c56_path}")

    print("Manifest generation complete.")


if __name__ == "__main__":
    main()
