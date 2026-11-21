"""Frozen analysis plus collection integrity and top-K normalized token entropy."""
import sys
sys.dont_write_bytecode = True
import argparse
from collections import Counter, defaultdict
import json
import re
from pathlib import Path
import numpy as np
from analyze_p167 import analyze, load_records, B, SEEDS
from stimuli_p167 import HERE, build_slice, clusters_and_ids, upstream_modules, verify_upstream
from addendum_openai_p167 import ensure_upstream_files


def mean(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def label_cell(rows, n_planned):
    available = [r for r in rows if r["status"] == "ok" and r.get("logprob_metrics")]
    return dict(n_available=len(available), n_planned=n_planned,
        **{k: mean([r["logprob_metrics"].get(k) for r in available]) for k in
           ("q_true_lower", "q_true_upper", "label_mass_captured", "label_token_entropy_bits")},
        argmax_true_rate=mean([float(r["label"] == "True") for r in rows if r["status"] == "ok"]))


def paired_entropy(rows, planned, exp, slot, left_prompt, right_prompt, cids=None):
    by_key = {(r["cluster_id"], r["task"], r["prompt"]): r for r in rows if r["exp"] == exp and r["slot"] == slot}
    ids = sorted({u["cluster_id"] for u in planned if u["exp"] == exp and u["slot"] == slot}) if cids is None else cids
    out = {}
    for metric, suffix in (("first_num_token_entropy_bits", "first_H"), ("mean_num_token_entropy_bits", "mean_H")):
        diffs = []
        for cid in ids:
            pair = [by_key.get((cid, task, prompt)) for task, prompt in (("M", left_prompt), ("P", right_prompt))]
            if any(r is None or r["status"] != "ok" or not r.get("token_entropy_metrics") for r in pair):
                continue
            vals = [r["token_entropy_metrics"].get(metric) for r in pair]
            if all(v is not None and np.isfinite(v) for v in vals):
                diffs.append(vals[0] - vals[1])
        n = len(diffs)
        if n:
            values = np.array(diffs)
            weights = np.random.Generator(np.random.PCG64(SEEDS.get(exp, SEEDS["E3"]))).multinomial(
                n, np.full(n, 1/n), size=B)
            boots = weights @ values / n
            ci = np.percentile(boots, [2.5, 97.5]).tolist()
            p = min(1.0, 2 * min((np.count_nonzero(boots <= 0) + 1)/(B+1),
                                (np.count_nonzero(boots >= 0) + 1)/(B+1)))
        else:
            ci, p = None, None
        out[suffix] = dict(n_paired=n, estimate_bits=mean(diffs), ci95_bits=ci, two_sided_p=p)
    return out


def expected_plan(paths, rows, expected_slice=None):
    order = ("slice_e1_e3", "slice_e2", "slice_e4")
    if expected_slice is not None and expected_slice not in (*order, "all"):
        raise ValueError("Unknown expected slice")
    selected = {expected_slice} if expected_slice else set()
    if not selected:
        for path in paths:
            match = re.search(r"(?:^|_)(slice_e1_e3|slice_e2|slice_e4|all)(?:_|\.|$)", Path(path).name)
            if match:
                selected.add(match.group(1))
    if not selected:
        exps = {r["exp"] for r in rows}
        selected = {s for s in order if exps & {u["exp"] for u in build_slice(s)}} if exps else {"all"}
    slices = ["all"] if "all" in selected or set(order) <= selected else [s for s in order if s in selected]
    planned = [u for s in slices for u in build_slice(s)]
    keys = {u["unit_key"] for u in planned}
    if len({r["unit_key"] for r in rows}) != len(rows) or any(r["unit_key"] not in keys for r in rows):
        raise ValueError("Duplicate or out-of-plan input unit_key")
    return slices, planned


def analyze_addendum(paths, expected_slice=None):
    ensure_upstream_files()
    paths = list(paths)
    rows = load_records(paths)
    expected_slices, planned = expected_plan(paths, rows, expected_slice)
    base_out = analyze(paths)
    target_exps = {u["exp"] for u in planned}
    n = len(rows)
    counts = Counter(r["status"] for r in rows)
    first = [r["first_pass_ok"] for r in rows if "first_pass_ok" in r]
    n_planned = len(planned)
    n_uncollected = n_planned - n
    base_out["collection_integrity"] = dict(expected_slices=expected_slices,
        n_planned=n_planned, n_rows=n, n_uncollected=n_uncollected,
        planned_slice_counts={"slice_e1_e3": 360, "slice_e2": 240, "slice_e4": 400, "all": 1000},
        status_counts={**{s: counts[s] for s in ("ok", "missing_transport", "missing_format")},
                       "uncollected": n_uncollected},
        completion_rate=counts["ok"]/n_planned, missing_rate=(n_planned-counts["ok"])/n_planned,
        present_row_missing_rate=(n-counts["ok"])/n if n else None,
        first_pass_ok_rate=mean(first), protocol_ok_rate=mean([r["protocol_ok"] for r in rows]))
    cells, planned_cells = defaultdict(list), Counter((u["exp"], u["slot"], u["task"], u["prompt"]) for u in planned)
    for r in rows:
        if r["task"] in ("P", "M"):
            cells[(r["exp"], r["slot"], r["task"], r["prompt"])].append(r)
    base_out["draft_copy_diagnostics"] = {"/".join(key): dict(n_available=sum(r["status"] == "ok" for r in rs),
        draft_copy_rate=mean([r.get("draft_copy_candidate") for r in rs if r["status"] == "ok"])) for key, rs in sorted(cells.items())}
    extra = {}
    if any(r.get("logprob_metrics") or r.get("token_entropy_metrics") for r in rows):
        mods = upstream_modules()
        slots = ("NI_OCC", "NI_PLAN", "INT_OCC", "INT_PLAN")
        lz = [r for r in rows if r["exp"] == "E3" and r["task"] == "L" and r["prompt"] == "Z"]
        ltask = dict(LCOT_by_exp_slot={})
        if "E3" in target_exps:
            ltask.update(E3_LZ_by_slot={s: label_cell([r for r in lz if r["slot"] == s], 20) for s in slots},
                         E3_LZ_contrasts={})
            _, ids = clusters_and_ids("E3")
            by_key = {(r["cluster_id"], r["slot"]): r for r in lz}
            weights = np.random.Generator(np.random.PCG64(SEEDS["E3"])).multinomial(len(ids), np.full(len(ids), 1/len(ids)), size=B)
            def bounds(cid, slot):
                r = by_key.get((cid, slot))
                m = r.get("logprob_metrics") if r and r["status"] == "ok" else None
                return (m["q_true_lower"], m["q_true_upper"]) if m else (0.0, 1.0)
            for a, b in (("NI_OCC", "NI_PLAN"), ("INT_OCC", "INT_PLAN"), ("INT_OCC", "NI_OCC")):
                diffs = [(bounds(cid, a)[0] - bounds(cid, b)[1], bounds(cid, a)[1] - bounds(cid, b)[0]) for cid in ids]
                lo, hi = np.array(diffs).T
                result = mods["core_e3"].infer_continuous_slot_e3(lo, hi, weights, method="pct")
                result["point_bounds"] = [float(lo.mean()), float(hi.mean())]
                ltask["E3_LZ_contrasts"][a + "_minus_" + b + "_q_true"] = result
        for exp in ("E2", "E3", "E4"):
            if exp in target_exps:
                ltask["LCOT_by_exp_slot"][exp] = {s: label_cell([r for r in rows if r["exp"] == exp and r["slot"] == s
                    and r["task"] == "L" and r["prompt"] == "CoT"], planned_cells[(exp, s, "L", "CoT")])
                    for s in sorted({u["slot"] for u in planned if u["exp"] == exp})}
        pm = {}
        for key, rs in sorted(cells.items()):
            available = [r["token_entropy_metrics"] for r in rs if r["status"] == "ok" and r.get("token_entropy_metrics")]
            pm["/".join(key)] = dict(n_available=len(available), n_planned=planned_cells[key],
                **{k: mean([m.get(k) for m in available]) for k in ("first_num_token_entropy_bits", "mean_num_token_entropy_bits", "mean_all_token_entropy_bits")},
                num_token_entropies_by_k={str(k+1): mean([m["num_token_entropies_bits"][k] for m in available])
                    for k in range(5 if key[2] == "M" else 1)},
                draft_copy_rate=base_out["draft_copy_diagnostics"]["/".join(key)]["draft_copy_rate"])
        clusters, e2ids = clusters_and_ids("E2")
        classes = {c["cluster_id"]: c["macro_class"] for c in clusters}
        contrasts = {}
        specs = [("E3_NI_OCC_MZ_minus_PZ", "E3", "NI_OCC", "Z", "Z", None),
                 ("E3_INT_OCC_MZ_minus_PZ", "E3", "INT_OCC", "Z", "Z", None),
                 ("E2_TELIC_NI_COMP_MZ_minus_PZ", "E2", "NI_COMP", "Z", "Z", [c for c in e2ids if classes[c] == "telic"]),
                 ("E2_ATELIC_INT_COMP_MZ_minus_PZ", "E2", "INT_COMP", "Z", "Z", [c for c in e2ids if classes[c] != "telic"]),
                 ("E4_DUAL_MOORE_MZ_minus_PZ", "E4", "DUAL_MOORE", "Z", "Z", None),
                 ("E4_DUAL_MOORE_MCF_minus_PCoT", "E4", "DUAL_MOORE", "CF", "CoT", None),
                 ("E1_C_MZ_minus_PCoT", "E1", "C", "Z", "CoT", None)]
        for name, exp, slot, left, right, cids in specs:
            if exp not in target_exps:
                continue
            for suffix, res in paired_entropy(rows, planned, exp, slot, left, right, cids).items():
                contrasts[name + "_" + suffix] = res
        extra = dict(task_L=ltask, task_PM_entropy=pm, paired_entropy_contrasts=contrasts,
                     entropy_definition="top-K truncated-and-renormalized Shannon entropy in bits")
    base_out["addendum_logprobs"] = extra
    return base_out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--expected-slice", choices=("slice_e1_e3", "slice_e2", "slice_e4", "all"))
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if not args.out.resolve().is_relative_to(HERE):
        raise ValueError("Output must remain under p167-api")
    args.out.write_text(json.dumps(analyze_addendum(args.paths, args.expected_slice), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
