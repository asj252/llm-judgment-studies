"""Mechanical validator, upstream-isolation byte scanner, and 15-mutation negative self-test for Experiment 3.

Verifies the structural guardrails of `exp3-en/PLAN-E3.md` §2.2 on all 100
clusters in `data/clusters_100_e3.json` against `data/imperfectiveNLI.json`,
`subclasses_e3.json`, and `split.json`, and verifies that zero verbatim upstream
sentences appear in any file inside `exp3-en/` outside `data/` (with zero
directory or file-extension exemptions outside `data/`).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from materials_e3 import (
    ALL_MODIFIERS,
    DEV_CLUSTER_IDS,
    HERE,
    SUBCLASS_MODIFIERS,
    UPSTREAM_SHA256,
    build_split_manifest,
    build_subclasses_manifest,
    lower_clause_initial,
    sha256_file,
)

PROG_RE = re.compile(r"^(.+?)\s+(was|were)\s+(.+)\.$")
FORBIDDEN_MOD_WORDS = ("interruption", "interrupted", "but", "stopped", "halted")


def validate_clusters_obj(
    clusters_obj: dict[str, Any],
    subclasses_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    upstream_items: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if clusters_obj.get("upstream_data_sha256") != UPSTREAM_SHA256:
        errors.append("upstream_data_sha256 mismatch in clusters_obj")

    expected_sub_manifest = build_subclasses_manifest()
    if subclasses_manifest != expected_sub_manifest:
        errors.append("subclasses_manifest does not match deterministic build_subclasses_manifest()")

    expected_split_manifest = build_split_manifest(expected_sub_manifest)
    if split_manifest != expected_split_manifest:
        errors.append("split_manifest does not match deterministic build_split_manifest()")

    d_map = {x["id"].split("_")[1]: x for x in upstream_items if x.get("id", "").startswith("D_")}
    b_map = {x["id"].split("_")[1]: x for x in upstream_items if x.get("id", "").startswith("B_")}
    if len(d_map) != 100 or len(b_map) != 100:
        errors.append(f"Expected 100 D_k and 100 B_k items in upstream, got D={len(d_map)}, B={len(b_map)}")
        return errors

    clusters = clusters_obj.get("clusters", [])
    if len(clusters) != 100:
        errors.append(f"Expected 100 clusters, found {len(clusters)}")
        return errors

    expected_ids = [f"{i:03d}" for i in range(1, 101)]
    actual_ids = [c.get("cluster_id") for c in clusters]
    if actual_ids != expected_ids:
        errors.append("Cluster IDs are not strictly '001'..'100' in ascending order")

    # Verify split partition and expanded unit lists
    dev_ids = split_manifest.get("dev", {}).get("cluster_ids", [])
    formal_ids = split_manifest.get("formal", {}).get("cluster_ids", [])
    if dev_ids != sorted(DEV_CLUSTER_IDS):
        errors.append("dev cluster_ids do not match Experiment 1 atelic_clusters")
    if len(dev_ids) != 20 or len(formal_ids) != 80 or set(dev_ids) & set(formal_ids):
        errors.append("Invalid dev/formal split sizes or overlap")
    if sorted(dev_ids + formal_ids) != expected_ids:
        errors.append("Union of dev and formal cluster_ids does not cover 001..100")

    macro_counts = {"A_plan": 0, "A_pure": 0}
    template_counts = {"A_plan_task": 0, "A_plan_deg": 0, "A_pure": 0}
    sub_clusters = subclasses_manifest.get("clusters", {})

    for c in clusters:
        cid = c["cluster_id"]
        if cid not in d_map or cid not in b_map:
            errors.append(f"[{cid}] Missing from upstream D_k / B_k map")
            continue
        d_item = d_map[cid]
        b_item = b_map[cid]
        sub_entry = sub_clusters.get(cid, {})

        tsub = c.get("template_subclass")
        msub = c.get("macro_subclass")
        if tsub not in SUBCLASS_MODIFIERS:
            errors.append(f"[{cid}] Unknown template_subclass: {tsub!r}")
            continue
        if tsub != sub_entry.get("template_subclass") or msub != sub_entry.get("macro_subclass"):
            errors.append(f"[{cid}] Subclass fields do not match subclasses_manifest['clusters'][{cid!r}]")
        spec = SUBCLASS_MODIFIERS[tsub]
        if msub != spec["macro_subclass"]:
            errors.append(f"[{cid}] macro_subclass {msub!r} != expected {spec['macro_subclass']!r}")
        macro_counts[msub] = macro_counts.get(msub, 0) + 1
        template_counts[tsub] = template_counts.get(tsub, 0) + 1

        occ_mod = c.get("occ_mod", "")
        plan_mod = c.get("plan_mod", "")
        if (
            occ_mod != spec["occ_mod"]
            or plan_mod != spec["plan_mod"]
            or occ_mod != sub_entry.get("occ_mod")
            or plan_mod != sub_entry.get("plan_mod")
        ):
            errors.append(f"[{cid}] Modifier mismatch for subclass {tsub}")

        for w in FORBIDDEN_MOD_WORDS:
            if w in occ_mod.lower().split() or w in plan_mod.lower().split():
                errors.append(f"[{cid}] Forbidden leakage word {w!r} in modifier")

        p_no_int = c.get("p_no_int", "")
        p_int = c.get("p_int", "")
        h_orig = c.get("h_orig", "")
        h_base = c.get("h_base", "")
        h_occ = c.get("h_occ", "")
        h_plan = c.get("h_plan", "")
        p_diag_pos = c.get("p_diag_pos", "")
        p_diag_neg = c.get("p_diag_neg", "")

        # Guardrail 1b: Exact binding to upstream imperfectiveNLI.json record
        if c.get("upstream_d_id") != d_item["id"] or c.get("upstream_b_id") != b_item["id"]:
            errors.append(f"[{cid}] upstream_d_id / upstream_b_id mismatch")
        if p_no_int != d_item["premise"]:
            errors.append(f"[{cid}] p_no_int does not match upstream D_{cid} premise")
        if p_int != b_item["premise"]:
            errors.append(f"[{cid}] p_int does not match upstream B_{cid} premise")
        if h_orig != d_item["hypothesis"] or h_orig != b_item["hypothesis"]:
            errors.append(f"[{cid}] h_orig does not match upstream D_{cid}/B_{cid} hypothesis")

        # Guardrail 2: progressive premise format & interruption prefix
        if not PROG_RE.match(p_no_int):
            errors.append(f"[{cid}] p_no_int does not match progressive regex: {p_no_int!r}")
        if not p_int.startswith(p_no_int[:-1] + ","):
            errors.append(f"[{cid}] p_int does not start with p_no_int[:-1] + ',': {p_int!r}")
        if not p_int.endswith("."):
            errors.append(f"[{cid}] p_int does not end with period: {p_int!r}")
        for m_str in ALL_MODIFIERS:
            if m_str in p_no_int or m_str in p_int:
                errors.append(f"[{cid}] Premise leaks modifier {m_str!r}")

        # Guardrail 3: Stem rule & single-slot substitution minimal pair
        expected_base = h_orig[:-1].removesuffix(" all day") if cid == "095" else h_orig[:-1]
        if h_base != expected_base:
            errors.append(f"[{cid}] h_base {h_base!r} != expected {expected_base!r}")
        if "all day" in h_base:
            errors.append(f"[{cid}] Unstripped 'all day' in h_base: {h_base!r}")

        if h_occ != f"{h_base} {occ_mod}.":
            errors.append(f"[{cid}] h_occ formula mismatch: {h_occ!r}")
        if h_plan != f"{h_base} {plan_mod}.":
            errors.append(f"[{cid}] h_plan formula mismatch: {h_plan!r}")

        # Single-slot suffix substitution check
        if not h_plan.endswith(f" {plan_mod}."):
            errors.append(f"[{cid}] h_plan missing suffix ' {plan_mod}.'")
        else:
            reconstructed_occ = h_plan[: -len(f" {plan_mod}.")] + f" {occ_mod}."
            if reconstructed_occ != h_occ:
                errors.append(f"[{cid}] Single-slot substitution failed: {reconstructed_occ!r} != {h_occ!r}")

        # Ensure h_occ does not contain plan_mod and h_plan does not contain occ_mod
        if plan_mod in h_occ:
            errors.append(f"[{cid}] h_occ leaks plan_mod {plan_mod!r}")
        if occ_mod in h_plan:
            errors.append(f"[{cid}] h_plan leaks occ_mod {occ_mod!r}")

        # Guardrail 5: Deterministic diagnostic contexts
        expected_pos = f"{p_no_int[:-1]}, and {lower_clause_initial(h_plan)}"
        if tsub == "A_plan_deg":
            expected_neg = f"{p_no_int[:-1]}, but that ended early and did not happen {plan_mod}."
        else:
            expected_neg = f"{p_no_int[:-1]}, but that ended early and did not continue {plan_mod}."
        if p_diag_pos != expected_pos:
            errors.append(f"[{cid}] p_diag_pos mismatch: {p_diag_pos!r} != {expected_pos!r}")
        if p_diag_neg != expected_neg:
            errors.append(f"[{cid}] p_diag_neg mismatch: {p_diag_neg!r} != {expected_neg!r}")

    if macro_counts != {"A_plan": 24, "A_pure": 76}:
        errors.append(f"Unexpected macro_counts: {macro_counts}")
    if template_counts != {"A_plan_task": 20, "A_plan_deg": 4, "A_pure": 76}:
        errors.append(f"Unexpected template_counts: {template_counts}")

    return errors


def check_no_upstream_leakage_outside_data(
    upstream_items: list[dict[str, Any]],
    root_dir: Path = HERE,
    extra_virtual_files: dict[str, bytes] | None = None,
) -> list[str]:
    """Scan every file in exp3-en/ outside data/ (with zero directory or extension exemptions) for upstream sentences."""
    upstream_Restricted_bytes = sorted(
        {str(item[k]).encode("utf-8") for item in upstream_items for k in ("premise", "hypothesis") if k in item}
    )
    leak_errors: list[str] = []

    candidates: list[tuple[str, bytes]] = []
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root_dir)
        if rel_path.parts[0] == "data":
            continue
        candidates.append((rel_path.as_posix(), path.read_bytes()))

    if extra_virtual_files:
        for v_rel, v_bytes in sorted(extra_virtual_files.items()):
            norm_parts = Path(v_rel).parts
            if norm_parts and norm_parts[0] == "data":
                continue
            candidates.append((v_rel, v_bytes))

    for rel_str, raw_bytes in candidates:
        for sent_b in upstream_Restricted_bytes:
            if sent_b in raw_bytes:
                preview = sent_b[:24].decode("utf-8", errors="replace")
                leak_errors.append(f"Upstream verbatim sentence leaked in {rel_str}: {preview!r}...")
    return leak_errors


def run_negative_mutation_tests(
    clusters_obj: dict[str, Any],
    subclasses_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    upstream_items: list[dict[str, Any]],
) -> tuple[int, int]:
    mutations = []

    # 1. Premise non-progressive mutation (synthetic string, not in upstream)
    m1 = copy.deepcopy(clusters_obj)
    m1["clusters"][0]["p_no_int"] = "The synthetic agent performed the action."
    mutations.append(("M1_non_progressive_premise", m1, subclasses_manifest, split_manifest, upstream_items))

    # 2. Premise modifier leakage
    m2 = copy.deepcopy(clusters_obj)
    m2["clusters"][0]["p_no_int"] = "The synthetic agent was performing the action all the way to completion."
    mutations.append(("M2_premise_modifier_leak", m2, subclasses_manifest, split_manifest, upstream_items))

    # 3. Broken p_int prefix
    m3 = copy.deepcopy(clusters_obj)
    m3["clusters"][1]["p_int"] = "The synthetic team practiced indoors, but the power failed."
    mutations.append(("M3_broken_p_int_prefix", m3, subclasses_manifest, split_manifest, upstream_items))

    # 4. Single-slot substitution violation between h_occ and h_plan
    m4 = copy.deepcopy(clusters_obj)
    m4["clusters"][2]["h_occ"] = "The synthetic subject walked for at least a short time."
    mutations.append(("M4_minimal_pair_stem_divergence", m4, subclasses_manifest, split_manifest, upstream_items))

    # 5. Unstripped 'all day' in 095
    m5 = copy.deepcopy(clusters_obj)
    m5["clusters"][94]["h_base"] = "The synthetic chef prepared soup all day"
    mutations.append(("M5_unstripped_all_day_095", m5, subclasses_manifest, split_manifest, upstream_items))

    # 6. Wrong subclass modifier assignment
    m6 = copy.deepcopy(clusters_obj)
    m6["clusters"][76]["plan_mod"] = "all the way to completion"
    mutations.append(("M6_wrong_subclass_modifier", m6, subclasses_manifest, split_manifest, upstream_items))

    # 7. Diagnostic positive predicate drift
    m7 = copy.deepcopy(clusters_obj)
    m7["clusters"][10]["p_diag_pos"] = "The synthetic subjects were training, and they left."
    mutations.append(("M7_diag_pos_drift", m7, subclasses_manifest, split_manifest, upstream_items))

    # 8. Diagnostic negative predicate drift
    m8 = copy.deepcopy(clusters_obj)
    m8["clusters"][10]["p_diag_neg"] = "The synthetic subjects were training, but they rested."
    mutations.append(("M8_diag_neg_drift", m8, subclasses_manifest, split_manifest, upstream_items))

    # 9. Split overlap / corrupted dev list
    m9_split = copy.deepcopy(split_manifest)
    m9_split["dev"]["cluster_ids"][0] = "001"
    mutations.append(("M9_corrupted_dev_split", clusters_obj, subclasses_manifest, m9_split, upstream_items))

    # 10. Coordinated replacement of a cluster's premise/hypothesis/diagnostics that passes regex but mismatches upstream
    m10 = copy.deepcopy(clusters_obj)
    c10 = m10["clusters"][0]
    c10["p_no_int"] = "The synthetic runners were sprinting around the oval."
    c10["p_int"] = "The synthetic runners were sprinting around the oval, but a horn sounded."
    c10["h_orig"] = "The synthetic runners sprinted around the oval."
    c10["h_base"] = "The synthetic runners sprinted around the oval"
    c10["h_occ"] = f"{c10['h_base']} {c10['occ_mod']}."
    c10["h_plan"] = f"{c10['h_base']} {c10['plan_mod']}."
    c10["p_diag_pos"] = f"{c10['p_no_int'][:-1]}, and {lower_clause_initial(c10['h_plan'])}"
    c10["p_diag_neg"] = f"{c10['p_no_int'][:-1]}, but that ended early and did not continue {c10['plan_mod']}."
    mutations.append(("M10_upstream_record_swap", m10, subclasses_manifest, split_manifest, upstream_items))

    # 11. Tampering with subclasses_manifest alone
    m11_sub = copy.deepcopy(subclasses_manifest)
    m11_sub["clusters"]["001"]["template_subclass"] = "A_pure"
    mutations.append(("M11_subclasses_manifest_tamper", clusters_obj, m11_sub, split_manifest, upstream_items))

    killed = 0
    for name, c_obj, sub_m, sp_m, up_items in mutations:
        errs = validate_clusters_obj(c_obj, sub_m, sp_m, up_items)
        if errs:
            killed += 1
        else:
            print(f"[FAIL] Mutation {name} was NOT caught!")

    # 12-15. Upstream sentence leakage mutations across markdown, raw/, server_logs/, and binary extension
    sample_upstream_bytes = str(upstream_items[0]["premise"]).encode("utf-8")
    leak_probes = [
        ("M12_leak_in_markdown", {"PLAN-E3.md": b"header\n" + sample_upstream_bytes + b"\n"}),
        ("M13_leak_in_raw_dir", {"raw/probe.txt": sample_upstream_bytes}),
        ("M14_leak_in_server_logs_dir", {"server_logs/probe.log": sample_upstream_bytes}),
        ("M15_leak_in_binary_ext", {"manifests/probe.npz": b"\x00\x01" + sample_upstream_bytes + b"\x00"}),
    ]
    for name, v_files in leak_probes:
        l_errs = check_no_upstream_leakage_outside_data(upstream_items, extra_virtual_files=v_files)
        if l_errs:
            killed += 1
        else:
            print(f"[FAIL] Leak mutation {name} was NOT caught!")

    total_mutations = len(mutations) + len(leak_probes)
    return killed, total_mutations


def main() -> int:
    upstream_path = HERE / "data" / "imperfectiveNLI.json"
    if sha256_file(upstream_path) != UPSTREAM_SHA256:
        raise SystemExit("Upstream imperfectiveNLI.json SHA-256 mismatch!")

    upstream_items = json.loads(upstream_path.read_text(encoding="utf-8"))
    clusters_obj = json.loads((HERE / "data" / "clusters_100_e3.json").read_text(encoding="utf-8"))
    subclasses_manifest = json.loads((HERE / "subclasses_e3.json").read_text(encoding="utf-8"))
    split_manifest = json.loads((HERE / "split.json").read_text(encoding="utf-8"))

    errors = validate_clusters_obj(clusters_obj, subclasses_manifest, split_manifest, upstream_items)
    if errors:
        for e in errors:
            print("ERROR:", e)
        return 1

    leak_errors = check_no_upstream_leakage_outside_data(upstream_items)
    if leak_errors:
        for e in leak_errors:
            print("LEAK_ERROR:", e)
        return 1

    killed, total = run_negative_mutation_tests(
        clusters_obj, subclasses_manifest, split_manifest, upstream_items
    )
    print(
        f"validate_materials_e3: 100/100 clusters PASS (0 errors); "
        f"0 upstream leaks outside data/; negative mutations killed: {killed}/{total}"
    )
    return 0 if killed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
