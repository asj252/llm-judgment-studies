"""Confirmatory and exploratory analysis for dnli-api configurations (pure Python stdlib).

Computes:
1. Sample & completeness (Table 1 / Table 6 format)
2. Confirmatory Holm family {H1, H2, H4a, H4b} using ../dnli/analysis.py (B=5000, seed 20261090)
3. Mean probability change Δ by update type S/W × stated/reported (Table 3 format)
4. Multi-estimate candidate readings: weighted mean, unweighted mean, top-weighted, median (Table 4 format)
5. Candidate spread dynamics: prior SD, stated change, reported minus stated, Spearman ρ (Table 8 format)
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[1] / "code"
sys.path.insert(0, str(MAIN))
sys.path.insert(0, str(HERE))

import analysis as A  # noqa: E402
from configs import CONFIGS, file_config  # noqa: E402
import run_api as R  # noqa: E402


def load_validated_split(cfg: str, which: str = "formal") -> dict[str, dict]:
    suffix = file_config(cfg)
    freeze_path = HERE / "freezes" / f"freeze_{suffix}.json"
    meta_path = HERE / f"run_meta_{which}_{suffix}.json"
    res_path = HERE / f"results_{which}_{suffix}.jsonl"
    if not meta_path.is_file() or not res_path.is_file():
        raise FileNotFoundError(f"Missing {which} results for {cfg}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if freeze_path.is_file():
        frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
        expected_fp = frozen.get(which, {}).get("fingerprint_id")
        if expected_fp and meta.get("fingerprint_id") != expected_fp:
            raise RuntimeError(
                f"Per-model freeze mismatch for {cfg} ({which}): meta={meta.get('fingerprint_id')} != freeze={expected_fp}"
            )
    raw = R.load_records(res_path)
    return R.valid_records(raw, meta["sessions"], meta["fingerprint_id"])


def read_candidate_value(row: dict, reading: str) -> float:
    res = row["result"]
    if reading == "mean":
        return float(res["value"])
    est = [float(x) for x in res["estimates"]]
    w = [float(x) for x in res["weights"]]
    if reading == "unweighted":
        return sum(est) / len(est)
    if reading == "top":
        mx = max(w)
        tied = [e for e, wi in zip(est, w) if wi == mx]
        return sum(tied) / len(tied)
    if reading == "median":
        order = sorted(range(len(est)), key=lambda i: est[i])
        ew = [Fraction(str(x)) for x in res["weights"]]
        tot = sum(ew)
        acc = Fraction(0)
        for idx in order:
            acc += ew[idx]
            if 2 * acc >= tot:
                return est[idx]
    raise ValueError(reading)


def analyze_config(cfg: str, which: str = "formal", B: int = A.B_DEFAULT) -> dict:
    all_items, split = R.load_all_items()
    planned = R.planned_items(all_items, which, blocks="A")
    keys = sorted(planned)
    records = load_validated_split(cfg, which)

    cells = {}
    by_tuple = {}
    for row in records.values():
        if row["round"] == "r0" and row["status"] == "ok":
            val = row["result"].get("value")
            if isinstance(val, (int, float)) and math.isfinite(val) and 0 <= val <= 100:
                cells[(cfg, row["key"], row["pres"], row["utype"], row["ask"])] = float(val)
                by_tuple[(row["key"], row["pres"], row["utype"], row["ask"])] = row

    # 1. Confirmatory tests {H1, H2, H4a, H4b}
    raw_tests = {}
    for t in A.FAMILY_TESTS:
        cc = A.common_complete(t, cells, keys, cfg)
        pt = A.stat(t, cells, cc, cfg)
        reps = A.cluster_bootstrap(t, cells, cc, planned, cfg, B=B, seed=A.SEED) if cc else []
        p = A.p_value(t, reps) if reps else 1.0
        lo95, hi95 = A.order_interval(reps, A.ALPHA) if reps else (None, None)
        raw_tests[t] = {"n": len(cc), "point": pt, "ci95": [lo95, hi95], "p": p, "reps": reps}

    ordered = sorted(A.FAMILY_TESTS, key=lambda t: raw_tests[t]["p"])
    confirmatory = {}
    stopped = False
    for rank, t in enumerate(ordered):
        alpha_k = A.ALPHA / (len(A.FAMILY_TESTS) - rank)
        rt = raw_tests[t]
        j = A.judge(t, rt["point"], rt["reps"], alpha_k)
        if stopped or not j["rejected"]:
            stopped = True
            j["rejected"] = False
        confirmatory[t] = {
            "n": rt["n"],
            "point": rt["point"],
            "ci95": rt["ci95"],
            "p": rt["p"],
            "holm_alpha": alpha_k,
            "bound": j.get("near") if j["rejected"] else None,
            "rejected": j["rejected"],
            "label": j["label"] if j["rejected"] else "Not rejected",
        }

    # 2. Table 3: Mean delta by update type (direct elicitation)
    table3 = {}
    for pres in ("stated", "reported"):
        for ut in ("S", "W"):
            ds = [
                A.delta(cells, cfg, k, pres, ut, "direct")
                for k in keys
                if A.delta(cells, cfg, k, pres, ut, "direct") is not None
            ]
            table3[f"{ut}_{pres}"] = statistics.fmean(ds) if ds else None

    # 3. Table 4: Multi-estimate readings minus direct (stated)
    table4 = {}
    sds = [
        float(by_tuple[(k, "stated", ut, "multi")]["result"]["weighted_sd"])
        for k in keys
        for ut in ("S", "W")
        if (k, "stated", ut, "multi") in by_tuple
        and by_tuple[(k, "stated", ut, "multi")]["result"].get("weighted_sd") is not None
    ]
    table4["candidate_weighted_sd_stated"] = statistics.fmean(sds) if sds else None
    for reading in ("mean", "unweighted", "top", "median"):
        vals = {}
        for k in keys:
            sd = by_tuple.get((k, "stated", "S", "direct"))
            wd = by_tuple.get((k, "stated", "W", "direct"))
            sm = by_tuple.get((k, "stated", "S", "multi"))
            wm = by_tuple.get((k, "stated", "W", "multi"))
            if None in (sd, wd, sm, wm):
                continue
            s_dir = (read_candidate_value(sd, "mean") - read_candidate_value(wd, "mean")) / 2
            s_mul = (read_candidate_value(sm, reading) - read_candidate_value(wm, reading)) / 2
            vals[k] = s_mul - s_dir
        reps = A.boot_values(vals, planned, B=2000, seed=20261490) if vals else []
        xs = sorted(reps)
        table4[reading] = {
            "point": statistics.fmean(vals.values()) if vals else None,
            "ci95": [xs[49], xs[1949]] if len(xs) == 2000 else [None, None],
            "n": len(vals),
        }

    # 4. Table 8: Candidate spread (prior SD, stated posterior minus prior, reported minus stated)
    prior_sds = [
        float(by_tuple[(k, "prior", "-", "multi")]["result"]["weighted_sd"])
        for k in keys
        if (k, "prior", "-", "multi") in by_tuple
    ]
    stated_changes = []
    rep_minus_stated = []
    for k in keys:
        p0 = by_tuple.get((k, "prior", "-", "multi"))
        ss = by_tuple.get((k, "stated", "S", "multi"))
        sw = by_tuple.get((k, "stated", "W", "multi"))
        rs = by_tuple.get((k, "reported", "S", "multi"))
        rw = by_tuple.get((k, "reported", "W", "multi"))
        if None not in (p0, ss, sw):
            stated_changes.append(
                (
                    (float(ss["result"]["weighted_sd"]) - float(p0["result"]["weighted_sd"]))
                    + (float(sw["result"]["weighted_sd"]) - float(p0["result"]["weighted_sd"]))
                )
                / 2
            )
        if None not in (ss, sw, rs, rw):
            rep_minus_stated.append(
                (
                    (float(rs["result"]["weighted_sd"]) - float(ss["result"]["weighted_sd"]))
                    + (float(rw["result"]["weighted_sd"]) - float(sw["result"]["weighted_sd"]))
                )
                / 2
            )
    prior_sd_mean = statistics.fmean(prior_sds) if prior_sds else None
    stated_change_mean = statistics.fmean(stated_changes) if stated_changes else None
    rep_diff_mean = statistics.fmean(rep_minus_stated) if rep_minus_stated else None
    table8 = {
        "prior_sd": prior_sd_mean,
        "stated_minus_prior": stated_change_mean,
        "stated_minus_prior_pct": (100 * stated_change_mean / prior_sd_mean) if prior_sd_mean else None,
        "reported_minus_stated": rep_diff_mean,
        "reported_minus_stated_pct": (
            100 * rep_diff_mean / table4["candidate_weighted_sd_stated"]
            if table4["candidate_weighted_sd_stated"]
            else None
        ),
    }

    # 5. Supplementary Entropy Diagnostics (Proposition binary entropy H2(p) & Candidate weight entropy H(w))
    def _h2(p_pct: float) -> float:
        p = max(0.0, min(1.0, float(p_pct) / 100.0))
        return 0.0 if p <= 0.0 or p >= 1.0 else -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))

    def _hw(weights: list) -> float:
        w = [max(0.0, float(x)) for x in weights]
        s = sum(w)
        if s <= 0:
            return 0.0
        return -sum((x / s) * math.log2(x / s) for x in w if x > 0)

    h2_dir, h2_mul = [], []
    for k in keys:
        cd = [by_tuple.get((k, "prior", "-", "direct")), by_tuple.get((k, "stated", "S", "direct")), by_tuple.get((k, "stated", "W", "direct"))]
        cm = [by_tuple.get((k, "prior", "-", "multi")), by_tuple.get((k, "stated", "S", "multi")), by_tuple.get((k, "stated", "W", "multi"))]
        if None not in cd and None not in cm:
            h2_dir.append(0.5 * _h2(cd[0]["result"]["value"]) + 0.25 * _h2(cd[1]["result"]["value"]) + 0.25 * _h2(cd[2]["result"]["value"]))
            h2_mul.append(0.5 * _h2(cm[0]["result"]["value"]) + 0.25 * _h2(cm[1]["result"]["value"]) + 0.25 * _h2(cm[2]["result"]["value"]))
    hw_by_pres = {
        pres: [
            _hw(r["result"]["weights"])
            for (k, p, u, a), r in by_tuple.items()
            if a == "multi" and p == pres and r["result"].get("weights")
        ]
        for pres in ("prior", "stated", "reported")
    }
    entropy = {
        "proposition_h2_direct_bits": statistics.fmean(h2_dir) if h2_dir else None,
        "proposition_h2_multi_bits": statistics.fmean(h2_mul) if h2_mul else None,
        "proposition_h2_diff_bits": (statistics.fmean(h2_mul) - statistics.fmean(h2_dir)) if h2_dir else None,
        "weight_entropy_hw_prior_bits": statistics.fmean(hw_by_pres["prior"]) if hw_by_pres["prior"] else None,
        "weight_entropy_hw_stated_bits": statistics.fmean(hw_by_pres["stated"]) if hw_by_pres["stated"] else None,
        "weight_entropy_hw_reported_bits": statistics.fmean(hw_by_pres["reported"]) if hw_by_pres["reported"] else None,
    }

    return {
        "config": cfg,
        "which": which,
        "n_planned_units": 300 if which == "dev" else 1400,
        "n_valid_units": sum(1 for r in records.values() if r["status"] == "ok"),
        "confirmatory": confirmatory,
        "table3": table3,
        "table4": table4,
        "table8": table8,
        "entropy": entropy,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("configs", nargs="+", choices=sorted(CONFIGS))
    ap.add_argument("--which", default="formal", choices=("dev", "formal"))
    ap.add_argument("--B", type=int, default=A.B_DEFAULT)
    args = ap.parse_args()
    out = {cfg: analyze_config(cfg, which=args.which, B=args.B) for cfg in args.configs}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
