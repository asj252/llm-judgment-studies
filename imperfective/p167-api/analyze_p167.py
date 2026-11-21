"""Analyze persisted P16.7 rows with the frozen dev statistical engines."""
import sys
sys.dont_write_bytecode = True
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from stimuli_p167 import HERE, build_slice, clusters_and_ids, upstream_modules, verify_upstream

B = 5000
SEEDS = {"E2": 2026110302, "E3": 2026110402, "E4": 2026110602}


def load_records(paths):
    records = []
    for path in paths:
        records.extend(json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip())
    if len({r["unit_key"] for r in records}) != len(records):
        raise ValueError("Duplicate units: analyze one config and collection per invocation")
    if len({r["config"] for r in records}) > 1 or len({r["dry_run"] for r in records}) > 1:
        raise ValueError("Cannot mix configurations or synthetic/live records")
    planned = {u["unit_key"]: u for u in build_slice("all")}
    for row in records:
        unit = planned[row["unit_key"]]
        for key in ("engine_unit_key", "exp", "cluster_id", "slot", "task", "prompt"):
            if row[key] != unit[key]:
                raise ValueError(f"Unit identity mismatch: {key}")
    return records


def _aliases(value):
    if isinstance(value, dict):
        if "n_valid_text" in value:
            value["n_text_available"] = value["n_valid_text"]
        for v in list(value.values()):
            _aliases(v)
    return value


def analyze(paths):
    verify_upstream()
    rows = load_records(paths)
    mods = upstream_modules()
    out = dict(b=B, seeds=SEEDS, dry_run=rows[0]["dry_run"] if rows else None,
               config=rows[0]["config"] if rows else None, engines={}, diagnostics={})
    engine_rows = [{**r, "unit_key": r["engine_unit_key"], "text": r["clean_text"], "parsed": r["parsed"]} for r in rows]
    for exp in ("E2", "E3", "E4"):
        records = [r for r in engine_rows if r["exp"] == exp]
        if not records:
            continue
        clusters, ids = clusters_and_ids(exp)
        core = mods["core_" + exp.lower()]
        kwargs = dict(stage="dev", b=B, seed=SEEDS[exp])
        if exp == "E3":
            kwargs["demoted_slots"] = ("E3_H3",)
        result = getattr(core, "analyze_stage_records_" + exp.lower())(records, clusters, ids, **kwargs)
        for family_key in ("primary_family", "companion_family"):
            family = result[family_key]
            family["holm_results"] = family.get("holm", family.get("holm_summary"))
        if exp == "E3":
            result["primary_family"]["slots"]["E3_H3"]["slice_note"] = "not_collected_in_p167_slice"
        out["engines"][exp] = result
        by_key = {(r["cluster_id"], r["slot"], r["task"], r["prompt"]): r for r in records}
        cluster_by_id = {c["cluster_id"]: c for c in clusters}

        def bounds(cids, slot, task, prompt, metric=None, threshold=False):
            values, valid = [], []
            for cid in cids:
                r = by_key.get((cid, slot, task, prompt))
                v = None
                if r and r["status"] == "ok":
                    v = float(r["label"] == "True") if task == "L" else r.get(metric or "value")
                valid.append(v is not None)
                if threshold and v is not None:
                    v = float(v >= 95)
                values.append((v, v) if v is not None else (0, 1 if task == "L" or threshold else 100))
            return np.array(values, dtype=float), valid

        def contrast(name, cids, left, right, discrete=False, threshold=False):
            a, av = bounds(cids, *left, threshold=threshold)
            b, bv = bounds(cids, *right, threshold=threshold)
            lo, hi = a[:, 0] - b[:, 1], a[:, 1] - b[:, 0]
            if discrete or threshold:
                result = mods["tango_" + exp.lower()].infer_exact_tango_slot(lo, hi, one_sided=True)
            else:
                weights = np.random.Generator(np.random.PCG64(SEEDS[exp])).multinomial(
                    len(cids), np.full(len(cids), 1 / len(cids)), size=B)
                result = getattr(core, "infer_continuous_slot_" + exp.lower())(lo, hi, weights, method="pct")
            result["missing_units"] = sum(not x for x in av) + sum(not x for x in bv)
            result["point_bounds"] = [float(lo.mean()), float(hi.mean())]
            out["diagnostics"][name] = result

        def trilabel(cids):
            return {f"{slot}/{prompt}": dict(Counter(r["label"] for r in records
                                                   if r["cluster_id"] in cids and r["slot"] == slot
                                                   and r["task"] == "L" and r["prompt"] == prompt
                                                   and r["status"] == "ok"))
                    for slot in sorted({r["slot"] for r in records}) for prompt in ("Z", "CoT")}

        if exp == "E3":
            for prefix in ("NI", "INT"):
                for metric, label in (("m_u", "MU"), ("m_w", "MW")):
                    contrast(f"E3_DIAG_{label}_{prefix}_OCC_MINUS_PLAN", ids,
                             (prefix + "_OCC", "M", "Z", metric), (prefix + "_PLAN", "M", "Z", metric))
            contrast("E3_DIAG_REALIS_PARADOX_LCOT", ids, ("INT_OCC", "L", "CoT"), ("NI_OCC", "L", "CoT"), True)
            out["diagnostics"]["E3_TRILABEL"] = trilabel(ids)
            nv = [r["logprob_metrics"] for r in records if r["task"] == "L" and r["prompt"] == "Z"
                  and r["config"].startswith("nv:") and r.get("logprob_metrics")]
            out["diagnostics"]["NV_LOGPROBS_LZ"] = {
                "n_available": len(nv), "n_planned": 80,
                **{k: float(np.mean([r[k] for r in nv])) if nv else None
                   for k in ("q_true_lower", "q_true_upper", "label_mass_captured")}}
        elif exp == "E2":
            telic = [cid for cid in ids if cluster_by_id[cid]["macro_class"] == "telic"]
            atelic = [cid for cid in ids if cid not in telic]
            for metric, label, task in ((None, "PZ", "P"), ("m_u", "MUZ", "M")):
                contrast(f"E2_DIAG_T_NI_MINUS_INT_COMP_{label}", telic,
                         ("NI_COMP", task, "Z", metric), ("INT_COMP", task, "Z", metric))
                contrast(f"E2_DIAG_A_NI_BARE_MINUS_COMP_{label}", atelic,
                         ("NI_BARE", task, "Z", metric), ("NI_COMP", task, "Z", metric))
            contrast("E2_DIAG_REALIS_PARADOX_LCOT", atelic, ("INT_BARE", "L", "CoT"), ("NI_BARE", "L", "CoT"), True)
            out["diagnostics"]["E2_TRILABEL"] = trilabel(atelic)
            # The E2 engine exposes bounds rather than missing-unit counters.
            pairs = {"E2_H1": (telic, ("NI_BARE", "P", "Z"), ("NI_COMP", "P", "Z")),
                     "E2_H2": (telic, ("NI_COMP", "P", "Z"), ("NI_COMP", "M", "Z", "m_u")),
                     "E2_H3": (atelic, ("INT_BARE", "P", "Z"), ("INT_COMP", "P", "Z")),
                     "E2_H4": (atelic, ("NI_BARE", "L", "CoT"), ("NI_COMP", "L", "CoT"))}
            result["missing_units"] = {}
            for name, (cids, a, b) in pairs.items():
                _, av = bounds(cids, *a)
                _, bv = bounds(cids, *b)
                result["missing_units"][name] = sum(not x for x in av + bv)
        else:
            contrast("E4_DIAG_H1_MW_CF", ids, ("DUAL_MOORE", "M", "CF", "m_w"), ("DUAL_MOORE", "P", "CoT"))
            for metric, label in (("m_u", "MU"), ("m_w", "MW")):
                contrast(f"E4_DIAG_H2_{label}_CF", ids, ("DUAL_MOORE", "M", "CF", metric),
                         ("PURE_MOORE", "M", "CF", metric))
            out["diagnostics"]["E4_MECHANISM"] = _aliases(core.summarize_reasoning_mechanisms_e4(records, ids))
    e1 = [r for r in engine_rows if r["exp"] == "E1"]
    if e1:
        by_key = {(r["cluster_id"], r["task"]): r for r in e1}
        ids = sorted({r["cluster_id"] for r in e1})
        # Use the full planned E1 C subset, even if the collection is incomplete.
        ids = sorted({u["cluster_id"] for u in build_slice("slice_e1_e3") if u["exp"] == "E1"})
        weights = np.random.Generator(np.random.PCG64(SEEDS["E3"])).multinomial(20, np.full(20, .05), size=B)
        for metric, label in (("m_u", "MUZ"), ("m_w", "MWZ")):
            for threshold, name in ((True, "E1_SA1_DEV"), (False, "E1_DIAG_C_PCOT_MINUS")):
                diffs = []
                missing = 0
                for cid in ids:
                    bounds_pair = []
                    for task, field in (("P", "value"), ("M", metric)):
                        row = by_key.get((cid, task))
                        v = row.get(field) if row and row["status"] == "ok" else None
                        missing += v is None
                        if threshold and v is not None:
                            v = float(v >= 95)
                        bounds_pair.append((v, v) if v is not None else (0, 1 if threshold else 100))
                    a, b = bounds_pair
                    diffs.append((a[0] - b[1], a[1] - b[0]))
                lo, hi = np.array(diffs).T
                res = mods["tango_e3"].infer_exact_tango_slot(lo, hi, True) if threshold else mods["core_e3"].infer_continuous_slot_e3(lo, hi, weights)
                res.update(missing_units=missing, point_bounds=[float(lo.mean()), float(hi.mean())])
                out["diagnostics"][name + "_" + label] = res
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if not args.out.resolve().is_relative_to(HERE):
        raise ValueError("Output must remain under p167-api")
    args.out.write_text(json.dumps(analyze(args.paths), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
