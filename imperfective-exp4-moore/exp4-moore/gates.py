"""Stage gate statistics and pause rules for Experiment 4 (PLAN-E4.md section 5).

Covers:
- S3 (`smoke`): any unavailable unit pauses; diagnostic `P/Z` requires `mean(Pos) > mean(Neg)`.
- S4 (`dev`): per-cell first-attempt availability < 90%, per-cell truncation > 5%, or overall
  missingness > 2% pauses; diagnostic `P/Z` requires `mean(Pos) >= 80.0` and `mean(Neg) <= 20.0`.
- S6 (`formal`): per-cell availability < 90%, per-cell truncation > 5%, or overall missingness > 2%.
"""
from prompts_e4 import COMBINATIONS

DOMAIN_SUBCLASSES = ("D1_safety", "D2_project", "D3_medical", "D4_institutional")
DIAG_COMBINATIONS = (("L", "Z"), ("P", "Z"), ("M", "Z"))


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
        first_avail = sum(
            r["status"] == "ok" and not bool(r.get("errors")) and (r.get("first_attempt_ok", True) is not False)
            for r in done
        )
        first_miss = len(done) - first_avail
        trunc = sum(bool(r.get("truncated")) for r in done)
        bounded = sum((r.get("q") or {}).get("q_status") == "bounded" for r in done) if task == "L" else 0
        cells[cell_key] = {
            "planned": len(units),
            "executed": len(done),
            "available": avail,
            "missing": miss,
            "first_attempt_available": first_avail,
            "first_attempt_missing": first_miss,
            "truncated": trunc,
            "bounded_q": bounded if task == "L" else "N/A",
            "availability_rate": avail / len(units) if units else 0.0,
            "first_attempt_availability_rate": first_avail / len(units) if units else 0.0,
            "truncation_rate": trunc / len(units) if units else 0.0,
            "bounded_q_rate": (bounded / len(units) if units else 0.0) if task == "L" else "N/A",
        }
        if stage == "smoke" and (miss or first_miss):
            reasons.append(f"smoke unit unavailable in {cell_key}")
        if stage != "smoke" and units:
            if first_miss * 100 > 10 * len(units):
                reasons.append(f"cell first-attempt availability below 90%: {cell_key}")
            if miss * 100 > 10 * len(units):
                reasons.append(f"cell availability below 90%: {cell_key}")
            if trunc * 100 > 5 * len(units):
                reasons.append(f"cell truncation above 5%: {cell_key}")

    # Diagnostic units tracking per (task, prompt) cell (S3 smoke & S4 dev)
    diag_cells = {}
    diag_done = [by_key[u["unit_key"]] for u in diag_planned if u["unit_key"] in by_key]
    diag_avail = sum(r["status"] == "ok" for r in diag_done)
    diag_miss = len(diag_done) - diag_avail
    diag_first_avail = sum(
        r["status"] == "ok" and not bool(r.get("errors")) and (r.get("first_attempt_ok", True) is not False)
        for r in diag_done
    )
    diag_first_miss = len(diag_done) - diag_first_avail
    diag_trunc = sum(bool(r.get("truncated")) for r in diag_done)
    if diag_planned:
        for d_task, d_prompt in DIAG_COMBINATIONS:
            d_key = f"DIAG:{d_task}/{d_prompt}"
            d_units = [u for u in diag_planned if (u["task"], u["prompt"]) == (d_task, d_prompt)]
            if not d_units:
                continue
            d_done = [by_key[u["unit_key"]] for u in d_units if u["unit_key"] in by_key]
            d_avail = sum(r["status"] == "ok" for r in d_done)
            d_miss = len(d_done) - d_avail
            d_first_avail = sum(
                r["status"] == "ok" and not bool(r.get("errors")) and (r.get("first_attempt_ok", True) is not False)
                for r in d_done
            )
            d_first_miss = len(d_done) - d_first_avail
            d_trunc = sum(bool(r.get("truncated")) for r in d_done)
            diag_cells[d_key] = {
                "planned": len(d_units),
                "executed": len(d_done),
                "available": d_avail,
                "missing": d_miss,
                "first_attempt_available": d_first_avail,
                "first_attempt_missing": d_first_miss,
                "truncated": d_trunc,
                "availability_rate": d_avail / len(d_units),
                "first_attempt_availability_rate": d_first_avail / len(d_units),
                "truncation_rate": d_trunc / len(d_units),
            }
            if stage == "smoke" and (d_miss or d_first_miss):
                reasons.append(f"smoke diagnostic unit unavailable in {d_key}")
            if stage != "smoke":
                if d_first_miss * 100 > 10 * len(d_units):
                    reasons.append(f"diagnostic cell first-attempt availability below 90%: {d_key}")
                if d_miss * 100 > 10 * len(d_units):
                    reasons.append(f"diagnostic cell availability below 90%: {d_key}")
                if d_trunc * 100 > 5 * len(d_units):
                    reasons.append(f"diagnostic cell truncation above 5%: {d_key}")

    # Diagnostic P/Z directional & threshold gate
    diag_pz_pos_units = [u for u in diag_planned if u.get("slot") == "DIAG_POS" and (u["task"], u["prompt"]) == ("P", "Z")]
    diag_pz_neg_units = [u for u in diag_planned if u.get("slot") == "DIAG_NEG" and (u["task"], u["prompt"]) == ("P", "Z")]
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
            by_dom = {}
            for dom in DOMAIN_SUBCLASSES:
                d_pos = [float(r["value"]) for r in pos_done if r.get("domain_subclass") == dom]
                d_neg = [float(r["value"]) for r in neg_done if r.get("domain_subclass") == dom]
                by_dom[dom] = {
                    "n_clusters": len(d_pos),
                    "pos_mean_pz": sum(d_pos) / len(d_pos) if d_pos else None,
                    "neg_mean_pz": sum(d_neg) / len(d_neg) if d_neg else None,
                }
            diag_summary["by_domain_subclass"] = by_dom
            pos_by_cid = {r["cluster_id"]: float(r["value"]) for r in pos_done if "cluster_id" in r}
            neg_by_cid = {r["cluster_id"]: float(r["value"]) for r in neg_done if "cluster_id" in r}
            all_diag_cids = sorted(set(pos_by_cid.keys()) | set(neg_by_cid.keys()))
            diag_summary["by_cluster"] = {
                cid: {"pos_pz": pos_by_cid.get(cid), "neg_pz": neg_by_cid.get(cid)}
                for cid in all_diag_cids
            }
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
    total_first_attempt_missing = sum(c["first_attempt_missing"] for c in cells.values()) + diag_first_miss
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
        "first_attempt_missing": total_first_attempt_missing,
        "first_attempt_missing_rate": total_first_attempt_missing / len(planned) if planned else 0.0,
        "diagnostic_pz": diag_summary,
        "diagnostic_cells": diag_cells,
        "cells": cells,
    }
