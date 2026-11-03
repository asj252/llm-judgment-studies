"""Stage gate statistics and pause rules for Experiment 2 (PLAN-E2.md section 5).

Covers:
- S3 (`smoke`): any unavailable unit pauses; diagnostic `P/Z` requires `mean(Pos) > mean(Neg)`.
- S4 (`dev`): per-cell first-attempt availability < 90%, per-cell truncation > 5%, or overall
  missingness > 2% pauses; diagnostic `P/Z` requires `mean(Pos) >= 80.0` and `mean(Neg) <= 20.0`.
- S6 (`formal`): per-cell availability < 90%, per-cell truncation > 5%, or overall missingness > 2%.
"""
from prompts_zh import COMBINATIONS


def compute(stage, planned, records):
    by_key = {r["unit_key"]: r for r in records}
    cells, reasons = {}, []

    main_planned = [u for u in planned if not u.get("is_diagnostic", False)]
    diag_planned = [u for u in planned if u.get("is_diagnostic", False)]

    for task, prompt in COMBINATIONS:
        cell_key = f"{task}/{prompt}"
        units = [u for u in main_planned if (u["task"], u["prompt"]) == (task, prompt)]
        done = [by_key[u["unit_key"]] for u in units if u["unit_key"] in by_key]
        avail = sum(r["status"] == "ok" for r in done)
        miss = len(done) - avail
        trunc = sum(bool(r.get("truncated")) for r in done)
        bounded = sum((r.get("q") or {}).get("q_status") == "bounded" for r in done) if task == "L" else 0
        cells[cell_key] = {
            "planned": len(units),
            "executed": len(done),
            "available": avail,
            "missing": miss,
            "truncated": trunc,
            "bounded_q": bounded if task == "L" else "N/A",
            "availability_rate": avail / len(units) if units else 0.0,
            "truncation_rate": trunc / len(units) if units else 0.0,
            "bounded_q_rate": (bounded / len(units) if units else 0.0) if task == "L" else "N/A",
        }
        if stage == "smoke" and miss:
            reasons.append(f"smoke unit unavailable in {cell_key}")
        if stage != "smoke" and units:
            if miss * 100 > 10 * len(units):
                reasons.append(f"cell availability below 90%: {cell_key}")
            if trunc * 100 > 5 * len(units):
                reasons.append(f"cell truncation above 5%: {cell_key}")

    # Diagnostic units tracking (S3 smoke & S4 dev)
    diag_done = [by_key[u["unit_key"]] for u in diag_planned if u["unit_key"] in by_key]
    diag_avail = sum(r["status"] == "ok" for r in diag_done)
    diag_miss = len(diag_done) - diag_avail
    diag_trunc = sum(bool(r.get("truncated")) for r in diag_done)
    if diag_planned:
        if stage == "smoke" and diag_miss:
            reasons.append("smoke diagnostic unit unavailable")
        if stage != "smoke":
            if diag_miss * 100 > 10 * len(diag_planned):
                reasons.append("diagnostic cell availability below 90%")
            if diag_trunc * 100 > 5 * len(diag_planned):
                reasons.append("diagnostic cell truncation above 5%")

    # Diagnostic P/Z directional & threshold gate
    diag_pz_pos_units = [u for u in diag_planned if u.get("slot") == "DIAG_POS_COMP" and (u["task"], u["prompt"]) == ("P", "Z")]
    diag_pz_neg_units = [u for u in diag_planned if u.get("slot") == "DIAG_NEG_COMP" and (u["task"], u["prompt"]) == ("P", "Z")]
    diag_summary = {"applicable": bool(diag_pz_pos_units and diag_pz_neg_units)}
    if diag_summary["applicable"]:
        pos_done = [by_key[u["unit_key"]] for u in diag_pz_pos_units if u["unit_key"] in by_key and by_key[u["unit_key"]]["status"] == "ok"]
        neg_done = [by_key[u["unit_key"]] for u in diag_pz_neg_units if u["unit_key"] in by_key and by_key[u["unit_key"]]["status"] == "ok"]
        diag_summary["pos_planned"] = len(diag_pz_pos_units)
        diag_summary["neg_planned"] = len(diag_pz_neg_units)
        diag_summary["pos_ok"] = len(pos_done)
        diag_summary["neg_ok"] = len(neg_done)
        if len(pos_done) == len(diag_pz_pos_units) and len(neg_done) == len(diag_pz_neg_units):
            pos_mean = sum(float(r["value"]) for r in pos_done) / len(pos_done)
            neg_mean = sum(float(r["value"]) for r in neg_done) / len(neg_done)
            diag_summary["pos_mean_pz"] = pos_mean
            diag_summary["neg_mean_pz"] = neg_mean
            if stage == "smoke":
                diag_ok = pos_mean > neg_mean
                diag_summary["pass"] = diag_ok
                if not diag_ok:
                    reasons.append(f"smoke diagnostic P/Z Pos ({pos_mean:.2f}) <= Neg ({neg_mean:.2f})")
            else:
                diag_ok = (pos_mean >= 80.0) and (neg_mean <= 20.0)
                diag_summary["pass"] = diag_ok
                if not diag_ok:
                    reasons.append(f"dev diagnostic P/Z threshold failed: Pos={pos_mean:.2f} (<80) or Neg={neg_mean:.2f} (>20)")
        else:
            diag_summary["pass"] = False
    else:
        diag_summary["pass"] = True

    total_missing = sum(c["missing"] for c in cells.values()) + diag_miss
    if stage != "smoke" and planned and total_missing * 100 > 2 * len(planned):
        reasons.append("configuration missing above 2%")
    if any(r["status"] == "missing_transport" for r in by_key.values()):
        reasons.append("transport retries exhausted")
    complete = len(by_key) == len(planned)
    passed = complete and not reasons and bool(diag_summary["pass"])
    return {
        "status": "pass" if passed else "fail",
        "complete": complete,
        "pause": bool(reasons),
        "pause_reasons": reasons,
        "planned": len(planned),
        "executed": len(by_key),
        "missing": total_missing,
        "missing_rate": total_missing / len(planned) if planned else 0.0,
        "diagnostic_pz": diag_summary,
        "cells": cells,
    }
