#!/usr/bin/env python3
"""
Stage 2C Cross-Model Aggregation & Interaction Analysis (`analyze_stage2c.py`)
=============================================================================
Reads all available `summary_2c_*.json` and `results_2c_*.jsonl` in `stage2c-crossover-20261105/`
and produces:
  1. `summary_2c_all_models.json`
  2. Console Markdown tables of:
     - Scale Grid (M in {7, 13, 15, 23, 100}) x Structural Organization (single, multi_repeat, 1p5_asc_repeat, posterior_focus)
     - Task 1 (Bayesian Narrative MAE & Input-Number Echo Rate)
     - Task 3 (Matched Attribute Framing Objective MAE & Signed/Absolute Framing Asymmetry)
"""

import json
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
SCALE_GRIDS = [7, 13, 15, 23, 100]
ORGANIZATIONS = ["single", "multi_repeat", "1p5_asc_repeat", "posterior_focus"]


def main() -> None:
    summaries: Dict[str, Any] = {}
    for p in sorted(SCRIPT_DIR.glob("summary_2c_*.json")):
        if p.name == "summary_2c_all_models.json":
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        summaries[data["model_spec"]] = data

    if not summaries:
        print("No completed summary_2c_*.json files found yet.")
        return

    out_all = SCRIPT_DIR / "summary_2c_all_models.json"
    out_all.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Loaded {len(summaries)} model summaries -> {out_all.name}\n")

    for model_spec, s in summaries.items():
        print(f"### Model: `{model_spec}` ({s['valid_units']}/{s['total_units']} valid)")
        print("| Scale $M$ | `single` MAE (Bayes / Frame / FA) | `multi_repeat` MAE (Bayes / Frame / FA) | `1p5_asc_repeat` MAE (Bayes / Frame / FA) | `posterior_focus` MAE (Bayes / Frame / FA) |")
        print("|---|---:|---:|---:|---:|")
        for M in SCALE_GRIDS:
            row_cells: List[str] = []
            for org in ORGANIZATIONS:
                cell = s["by_cell"].get(f"M{M}__{org}", {})
                b_mae = cell.get("bayes_narrative", {}).get("mae")
                f_mae = cell.get("attribute_framing", {}).get("mae")
                fa_abs = cell.get("attribute_framing", {}).get("framing_asymmetry_abs_mean")
                if b_mae is not None and f_mae is not None:
                    row_cells.append(f"{b_mae:.1f} / {f_mae:.1f} / {fa_abs if fa_abs is not None else 0.0:.1f}")
                else:
                    row_cells.append("-")
            print(f"| $M={M}$ | " + " | ".join(row_cells) + " |")
        print()


if __name__ == "__main__":
    main()
