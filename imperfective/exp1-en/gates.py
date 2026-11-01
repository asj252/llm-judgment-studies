"""Planned denominators and irreversible early PAUSE thresholds."""
from collections import Counter, defaultdict


def compute(stage, plan, records):
    planned = Counter((u["task"], u["prompt"]) for u in plan)
    counts, forms, reasons, qs, seconds = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), defaultdict(list)
    seen = set()
    for r in records:
        if r["unit_key"] in seen:
            raise ValueError("duplicate gate unit")
        seen.add(r["unit_key"])
        cell = (r["task"], r["prompt"])
        counts[cell]["executed"] += 1
        counts[cell]["usable" if r["status"] == "ok" else "missing"] += 1
        counts[cell]["truncated"] += bool(r.get("truncated"))
        phases = r.get("phases", {})
        counts[cell]["generation_ok"] += phases.get("generation") == "ok"
        counts[cell]["parse_ok"] += phases.get("parse") == "ok" and not r.get("truncated", False)
        counts[cell]["scoring_usable"] += cell[0] == "L" and (r.get("q") or {}).get("q_status") in ("full", "bounded")
        p = r.get("parsed") or {}
        if p.get("form"):
            forms[cell][p["form"]] += 1
        for f in p.get("forms", []):
            forms[cell][f] += 1
        reasons[cell].update((r.get("protocol") or {}).get("reasons", []))
        qs[cell][(r.get("q") or {}).get("q_status", "not_attempted" if cell[0] == "L" else "not_applicable")] += 1
        seconds[cell].append(r.get("seconds", 0))
    pause = []
    for cell, n in planned.items():
        c = counts[cell]
        if stage == "smoke" and c["missing"]:
            pause.append(f"{cell}: smoke unusable")
        if stage == "dev" and c["missing"] * 10 > n:
            pause.append(f"{cell}: usable below 90%")
        if stage == "dev" and cell[0] in ("P", "M") and cell[1] in ("CoT", "CF") and c["truncated"] * 20 > n:
            pause.append(f"{cell}: truncation above 5%")
    missing = sum(c["missing"] for c in counts.values())
    if stage == "dev" and missing * 50 > len(plan):
        pause.append("configuration missing above 2%")
    complete = len(records) == len(plan) and seen == {u["unit_key"] for u in plan}
    def availability(cell):
        c = counts[cell]
        # All rates use executed terminal units, including upstream failures.
        # Unexecuted units never enter a failure denominator.
        return {phase: {"available": c[key], "denominator": c["executed"],
                       "rate": c[key] / c["executed"] if c["executed"] else None}
                if phase != "scoring" or cell[0] == "L" else
                {"available": None, "denominator": 0, "rate": None, "status": "not_applicable"}
                for phase, key in (("generation", "generation_ok"), ("parse", "parse_ok"), ("scoring", "scoring_usable"))}
    cells = {"-".join(cell): {"planned": n, **dict(counts[cell]), "forms": dict(forms[cell]),
        "availability": availability(cell),
        "protocol_reasons": dict(reasons[cell]), "q_status": dict(qs[cell]),
        "truncation_rate": counts[cell]["truncated"] / n,
        "mean_seconds": sum(seconds[cell]) / len(seconds[cell]) if seconds[cell] else None}
        for cell, n in planned.items()}
    return {"status": "pass" if complete and not pause else "fail", "complete": complete,
            "pause": "PAUSE" if pause else None, "pause_reasons": pause, "cells": cells,
            "executed": len(records), "planned": len(plan), "missing": missing}
