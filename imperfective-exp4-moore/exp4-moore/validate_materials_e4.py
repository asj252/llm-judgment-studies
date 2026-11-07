"""Mechanical validation and 17-mutation negative self-test for Experiment 4 (exp4-moore).

Verifies the 5 structural guardrails on all 100 clusters in data/clusters_100_e4.json,
subclasses_e4.json, and split.json.
Runs 17 negative mutation self-tests (M1..M17) covering every structural guardrail
(verified both with and without raw-spec binding) as well as manifest/raw-spec binding.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from typing import Any, Dict, List

from curate_100_clusters_e4 import (
    DOMAIN_SUBCLASSES,
    MAIN_SLOTS,
    DIAG_SLOTS,
    RAW_CLUSTER_SPECS,
    build_clusters_obj,
    build_subclasses_manifest,
    build_split_manifest,
)

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

FORBIDDEN_WORDS = (
    "moore", "moorean", "paradox", "paradoxical", "contradict", "contradiction",
    "contradictory", "coherent", "incoherent", "coherence", "pragmatic",
    "pragmatically", "dual criteria", "polysemy", "polysemous", "entail",
    "entailment"
)

DIGIT_RE = re.compile(r"[0-9]")
DUP_WORD_RE = re.compile(r"\b([A-Za-z]+)\s+\1\b", re.IGNORECASE)


def validate_materials(
    clusters_obj: dict[str, Any],
    subclasses_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    *,
    check_raw_spec_binding: bool = True,
) -> list[str]:
    errors: list[str] = []

    # Manifest schema and deterministic reconstruction checks
    if clusters_obj.get("schema_version") != "e4_clusters_100_v1":
        errors.append(f"Bad clusters_obj schema_version: {clusters_obj.get('schema_version')}")
    if subclasses_manifest.get("schema_version") != "e4_subclasses_v1":
        errors.append(f"Bad subclasses_manifest schema_version: {subclasses_manifest.get('schema_version')}")
    if split_manifest.get("schema_version") != "e4_split_v1":
        errors.append(f"Bad split_manifest schema_version: {split_manifest.get('schema_version')}")

    if check_raw_spec_binding:
        expected_sub_manifest = build_subclasses_manifest()
        if subclasses_manifest != expected_sub_manifest:
            errors.append("subclasses_manifest does not match deterministic build_subclasses_manifest()")

        expected_split_manifest = build_split_manifest()
        if split_manifest != expected_split_manifest:
            errors.append("split_manifest does not match deterministic build_split_manifest()")

    clusters = clusters_obj.get("clusters", [])
    if len(clusters) != 100:
        errors.append(f"Expected 100 clusters in clusters_obj, found {len(clusters)}")
        return errors

    sub_clusters = subclasses_manifest.get("clusters", {})

    # Uniqueness tracking
    seen_cids = set()
    seen_topics = set()
    seen_speakers = set()
    seen_p_cores = set()
    seen_p_atomics = set()

    for idx, c in enumerate(clusters):
        cid = c.get("cluster_id", "")
        expected_cid = f"{idx + 1:03d}"
        if cid != expected_cid:
            errors.append(f"Cluster index {idx}: expected cluster_id {expected_cid}, got {cid}")
        if cid in seen_cids:
            errors.append(f"Duplicate cluster_id: {cid}")
        seen_cids.add(cid)

        if check_raw_spec_binding:
            # Exact binding to RAW_CLUSTER_SPECS[idx] and subclasses_manifest["clusters"][cid]
            raw_spec = RAW_CLUSTER_SPECS[idx]
            for spec_k, spec_v in raw_spec.items():
                if c.get(spec_k) != spec_v:
                    errors.append(f"Cluster {cid}: field {spec_k!r} does not match RAW_CLUSTER_SPECS[{idx}]")
            sub_entry = sub_clusters.get(cid, {})
            for sub_k in ("domain_subclass", "topic_label", "speaker", "local_mod", "global_mod"):
                if c.get(sub_k) != sub_entry.get(sub_k):
                    errors.append(f"Cluster {cid}: field {sub_k!r} does not match subclasses_manifest['clusters'][{cid!r}]")

        topic = c.get("topic_label", "")
        if topic in seen_topics:
            errors.append(f"Duplicate topic_label: {topic}")
        seen_topics.add(topic)

        speaker = c.get("speaker", "")
        if speaker in seen_speakers:
            errors.append(f"Duplicate speaker: {speaker}")
        seen_speakers.add(speaker)

        p_core = c.get("p_core_cap", "")
        if p_core in seen_p_cores:
            errors.append(f"Duplicate p_core_cap: {p_core}")
        seen_p_cores.add(p_core)

        p_atomic = c.get("p_atomic_cap", "")
        if p_atomic in seen_p_atomics:
            errors.append(f"Duplicate p_atomic_cap: {p_atomic}")
        seen_p_atomics.add(p_atomic)

        # Check capitalization and "The "
        if not p_core.startswith("The "):
            errors.append(f"Cluster {cid}: p_core_cap must start with 'The '")
        if not p_atomic.startswith("The "):
            errors.append(f"Cluster {cid}: p_atomic_cap must start with 'The '")

        local_mod = c.get("local_mod", "")
        global_mod = c.get("global_mod", "")
        dual_context = c.get("dual_context", "")
        pure_context = c.get("pure_context", "")
        reading_context = c.get("reading_context", "")
        all_clear_context = c.get("all_clear_context", "")

        # Guardrail 1: Speaker in all 6 premises and hypothesis
        p_pure_moore = c.get("p_pure_moore", "")
        p_dual_moore = c.get("p_dual_moore", "")
        p_dual_explicit = c.get("p_dual_explicit", "")
        p_pure_read = c.get("p_pure_read", "")
        p_diag_pos = c.get("p_diag_pos", "")
        p_diag_neg = c.get("p_diag_neg", "")
        hypothesis = c.get("hypothesis", "")

        for p_name, p_val in (
            ("p_pure_moore", p_pure_moore),
            ("p_dual_moore", p_dual_moore),
            ("p_dual_explicit", p_dual_explicit),
            ("p_pure_read", p_pure_read),
            ("p_diag_pos", p_diag_pos),
            ("p_diag_neg", p_diag_neg),
            ("hypothesis", hypothesis),
        ):
            if speaker not in p_val:
                errors.append(f"Cluster {cid}: speaker {speaker!r} missing from {p_name}")

        # Guardrail 1 prefix check
        expected_dual_prefix = f'{dual_context} Speaking about the situation as a whole, {speaker} sincerely says: "'
        if not p_dual_moore.startswith(expected_dual_prefix):
            errors.append(f"Cluster {cid}: p_dual_moore does not start with expected prefix: {expected_dual_prefix!r}")
        if not p_dual_explicit.startswith(expected_dual_prefix):
            errors.append(f"Cluster {cid}: p_dual_explicit does not start with expected prefix: {expected_dual_prefix!r}")

        # Guardrail 1: Deterministic modifier replacement
        recovered_dual_moore = p_dual_explicit.replace(f" {local_mod}", "", 1).replace(f" {global_mod}", "", 1)
        if recovered_dual_moore != p_dual_moore:
            errors.append(f"Cluster {cid}: p_dual_explicit modifier replacement does not recover p_dual_moore")

        # Guardrail 1: Modifiers do not leak into p_dual_moore
        if f" {local_mod}" in p_dual_moore:
            errors.append(f"Cluster {cid}: local_mod leaked into p_dual_moore")
        if f" {global_mod}" in p_dual_moore:
            errors.append(f"Cluster {cid}: global_mod leaked into p_dual_moore")

        # Guardrail 2: Quoted moore_atomic_quote in p_pure_moore and p_pure_read
        p_atomic_low = p_atomic[0].lower() + p_atomic[1:]
        expected_moore_atomic_quote = f"{p_atomic}, but I do not believe that {p_atomic_low}."
        expected_moore_atomic_quoted = f'"{expected_moore_atomic_quote}"'
        if not p_pure_moore.endswith(expected_moore_atomic_quoted):
            errors.append(f"Cluster {cid}: p_pure_moore does not end with exact moore_atomic_quote")
        if not p_pure_read.endswith(expected_moore_atomic_quoted):
            errors.append(f"Cluster {cid}: p_pure_read does not end with exact moore_atomic_quote")

        # Guardrail 3: Unified hypothesis
        expected_hypothesis = f"{speaker}'s utterance in this context is coherent and does not commit {speaker} to a self-contradiction."
        if hypothesis != expected_hypothesis:
            errors.append(f"Cluster {cid}: hypothesis mismatch:\nExpected: {expected_hypothesis}\nGot: {hypothesis}")

        # Guardrail 4: Forbidden meta-words check on 6 premises and component fields
        for field_name in (
            "pure_context", "reading_context", "dual_context", "all_clear_context",
            "p_atomic_cap", "p_core_cap", "local_mod", "global_mod", "speaker", "topic_label"
        ):
            val = c.get(field_name, "")
            val_lower = val.lower()
            for fw in FORBIDDEN_WORDS:
                if fw in val_lower:
                    errors.append(f"Cluster {cid}: forbidden word {fw!r} found in field {field_name}")

        for p_name, p_val in (
            ("p_pure_moore", p_pure_moore),
            ("p_dual_moore", p_dual_moore),
            ("p_dual_explicit", p_dual_explicit),
            ("p_pure_read", p_pure_read),
            ("p_diag_pos", p_diag_pos),
            ("p_diag_neg", p_diag_neg),
        ):
            p_val_lower = p_val.lower()
            for fw in FORBIDDEN_WORDS:
                if fw in p_val_lower:
                    errors.append(f"Cluster {cid}: forbidden word {fw!r} found in {p_name}")

        # Guardrail 4: Zero digits and zero % in any premise or hypothesis
        for p_name, p_val in (
            ("p_pure_moore", p_pure_moore),
            ("p_dual_moore", p_dual_moore),
            ("p_dual_explicit", p_dual_explicit),
            ("p_pure_read", p_pure_read),
            ("p_diag_pos", p_diag_pos),
            ("p_diag_neg", p_diag_neg),
            ("hypothesis", hypothesis),
        ):
            if DIGIT_RE.search(p_val):
                errors.append(f"Cluster {cid}: digit found in {p_name}: {p_val!r}")
            if "%" in p_val:
                errors.append(f"Cluster {cid}: '%' found in {p_name}: {p_val!r}")
            if DUP_WORD_RE.search(p_val):
                errors.append(f"Cluster {cid}: consecutive duplicate word found in {p_name}: {p_val!r}")

        # Exact deterministic formula checks for all 4 main premises, 2 diagnostic premises, and hypothesis
        p_core_low = p_core[0].lower() + p_core[1:]
        moore_core_quote = f"{p_core}, but I do not believe that {p_core_low}."
        explicit_core_quote = f"{p_core} {local_mod}, but I do not believe that {p_core_low} {global_mod}."
        expected_p_pure_moore = (
            f"{pure_context} Looking directly at that single unambiguous indicator, "
            f'{speaker} sincerely asserts: "{expected_moore_atomic_quote}"'
        )
        expected_p_dual_moore = (
            f"{dual_context} Speaking about the situation as a whole, "
            f'{speaker} sincerely says: "{moore_core_quote}"'
        )
        expected_p_dual_explicit = (
            f"{dual_context} Speaking about the situation as a whole, "
            f'{speaker} sincerely says: "{explicit_core_quote}"'
        )
        expected_p_pure_read = (
            f"{reading_context} While reading a printed drama script line aloud to test the microphone "
            f'(without stating any personal beliefs), {speaker} reads the line: "{expected_moore_atomic_quote}"'
        )
        expected_diag_pos = f'{all_clear_context} Speaking about the situation as a whole, {speaker} sincerely says: "{p_core}, and I fully believe that {p_core_low}."'
        expected_diag_neg = f'{pure_context} Looking directly at that single unambiguous indicator, {speaker} sincerely asserts: "{p_atomic}, and at the exact same time and in the exact same sense it is false that {p_atomic_low}."'
        if p_pure_moore != expected_p_pure_moore:
            errors.append(f"Cluster {cid}: p_pure_moore formula mismatch")
        if p_dual_moore != expected_p_dual_moore:
            errors.append(f"Cluster {cid}: p_dual_moore formula mismatch")
        if p_dual_explicit != expected_p_dual_explicit:
            errors.append(f"Cluster {cid}: p_dual_explicit formula mismatch")
        if p_pure_read != expected_p_pure_read:
            errors.append(f"Cluster {cid}: p_pure_read formula mismatch")
        if p_diag_pos != expected_diag_pos:
            errors.append(f"Cluster {cid}: p_diag_pos template mismatch")
        if p_diag_neg != expected_diag_neg:
            errors.append(f"Cluster {cid}: p_diag_neg template mismatch")

    # Guardrail 5: Split manifest checks
    dev_ids = split_manifest.get("dev", {}).get("cluster_ids", [])
    formal_ids = split_manifest.get("formal", {}).get("cluster_ids", [])
    smoke_ids = split_manifest.get("smoke", {}).get("cluster_ids", [])

    if len(dev_ids) != 20:
        errors.append(f"Expected 20 dev_ids in split_manifest, got {len(dev_ids)}")
    if len(formal_ids) != 80:
        errors.append(f"Expected 80 formal_ids in split_manifest, got {len(formal_ids)}")
    if set(dev_ids).intersection(set(formal_ids)):
        errors.append("Overlap detected between dev_ids and formal_ids")

    # Domain balance checks
    sub_clusters = subclasses_manifest.get("clusters", {})
    dev_dom_counts: dict[str, int] = {}
    for cid in dev_ids:
        dom = sub_clusters.get(cid, {}).get("domain_subclass", "")
        dev_dom_counts[dom] = dev_dom_counts.get(dom, 0) + 1

    formal_dom_counts: dict[str, int] = {}
    for cid in formal_ids:
        dom = sub_clusters.get(cid, {}).get("domain_subclass", "")
        formal_dom_counts[dom] = formal_dom_counts.get(dom, 0) + 1

    for dom in DOMAIN_SUBCLASSES:
        if dev_dom_counts.get(dom, 0) != 5:
            errors.append(f"Domain {dom} has {dev_dom_counts.get(dom, 0)} dev clusters, expected 5")
        if formal_dom_counts.get(dom, 0) != 20:
            errors.append(f"Domain {dom} has {formal_dom_counts.get(dom, 0)} formal clusters, expected 20")

    # Smoke check
    expected_smoke = dev_ids[:3]
    if smoke_ids != expected_smoke:
        errors.append(f"smoke cluster_ids mismatch: expected {expected_smoke}, got {smoke_ids}")

    return errors


def _killed_both_modes(
    m_clusters: dict[str, Any],
    m_sub: dict[str, Any],
    m_split: dict[str, Any],
) -> bool:
    """Verify structural mutations M1..M15 are killed both with and without raw-spec binding."""
    errs_struct = validate_materials(m_clusters, m_sub, m_split, check_raw_spec_binding=False)
    errs_full = validate_materials(m_clusters, m_sub, m_split, check_raw_spec_binding=True)
    return bool(errs_struct) and bool(errs_full)


def run_negative_mutations(
    clean_clusters_obj: dict[str, Any],
    clean_subclasses_manifest: dict[str, Any],
    clean_split_manifest: dict[str, Any],
) -> int:
    mutations_killed = 0

    # M1: Duplicate cluster_id
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][1]["cluster_id"] = "001"
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M1 not killed!")

    # M2: Duplicate topic_label
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][1]["topic_label"] = m_clusters["clusters"][0]["topic_label"]
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M2 not killed!")

    # M3: Duplicate speaker
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][1]["speaker"] = m_clusters["clusters"][0]["speaker"]
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M3 not killed!")

    # M4: Duplicate p_core_cap
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][1]["p_core_cap"] = m_clusters["clusters"][0]["p_core_cap"]
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M4 not killed!")

    # M5: Duplicate p_atomic_cap
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][1]["p_atomic_cap"] = m_clusters["clusters"][0]["p_atomic_cap"]
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M5 not killed!")

    # M6: Speaker missing in premise
    m_clusters = copy.deepcopy(clean_clusters_obj)
    orig_p = m_clusters["clusters"][0]["p_dual_moore"]
    m_clusters["clusters"][0]["p_dual_moore"] = orig_p.replace(m_clusters["clusters"][0]["speaker"], "Someone Else")
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M6 not killed!")

    # M7: p_dual_moore and p_dual_explicit prefix mismatch
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["p_dual_explicit"] = "Tampered prefix: " + m_clusters["clusters"][0]["p_dual_explicit"]
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M7 not killed!")

    # M8: local_mod leaked into p_dual_moore
    m_clusters = copy.deepcopy(clean_clusters_obj)
    local_mod = m_clusters["clusters"][0]["local_mod"]
    m_clusters["clusters"][0]["p_dual_moore"] = m_clusters["clusters"][0]["p_dual_moore"].replace('sincerely says: "', f'sincerely says: " {local_mod}')
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M8 not killed!")

    # M9: p_pure_moore and p_pure_read quote mismatch
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["p_pure_read"] = m_clusters["clusters"][0]["p_pure_read"] + " mismatch."
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M9 not killed!")

    # M10: hypothesis tampered
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["hypothesis"] = "The speaker is completely wrong."
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M10 not killed!")

    # M11: forbidden meta-word injected
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["p_dual_moore"] = m_clusters["clusters"][0]["p_dual_moore"].replace("Speaking about", "Highlighting the paradox of")
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M11 not killed!")

    # M12: digit injected into premise
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["p_pure_moore"] = m_clusters["clusters"][0]["p_pure_moore"] + " 1"
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M12 not killed!")

    # M13: percent sign injected into premise
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["p_pure_read"] = m_clusters["clusters"][0]["p_pure_read"] + " %"
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M13 not killed!")

    # M14: p_diag_pos template tampered
    m_clusters = copy.deepcopy(clean_clusters_obj)
    m_clusters["clusters"][0]["p_diag_pos"] = "Tampered diagnostic positive premise."
    if _killed_both_modes(m_clusters, clean_subclasses_manifest, clean_split_manifest):
        mutations_killed += 1
    else:
        print("FAIL: M14 not killed!")

    # M15: split.json corruption (overlap between dev and formal)
    m_split = copy.deepcopy(clean_split_manifest)
    m_split["formal"]["cluster_ids"][0] = m_split["dev"]["cluster_ids"][0]
    if _killed_both_modes(clean_clusters_obj, clean_subclasses_manifest, m_split):
        mutations_killed += 1
    else:
        print("FAIL: M15 not killed!")

    # M16: subclasses_manifest standalone tamper
    m_sub = copy.deepcopy(clean_subclasses_manifest)
    m_sub["clusters"]["001"]["domain_subclass"] = "D4_institutional"
    errs = validate_materials(clean_clusters_obj, m_sub, clean_split_manifest)
    if errs:
        mutations_killed += 1
    else:
        print("FAIL: M16 not killed!")

    # M17: coordinated replacement of a cluster's fields that satisfies templates but mismatches RAW_CLUSTER_SPECS
    m_coord = copy.deepcopy(clean_clusters_obj)
    c0 = m_coord["clusters"][0]
    c0["speaker"] = "Inspector Synthetic Tester"
    c0["p_core_cap"] = "The synthetic bridge is safe"
    c0["p_core_low"] = "the synthetic bridge is safe"
    c0["p_atomic_cap"] = "The synthetic gauge needle is green"
    c0["p_atomic_low"] = "the synthetic gauge needle is green"
    c0["p_pure_moore"] = (
        f'{c0["pure_context"]} Looking directly at that single unambiguous indicator, '
        f'{c0["speaker"]} sincerely asserts: "{c0["p_atomic_cap"]}, but I do not believe that {c0["p_atomic_low"]}."'
    )
    c0["p_dual_moore"] = (
        f'{c0["dual_context"]} Speaking about the situation as a whole, '
        f'{c0["speaker"]} sincerely says: "{c0["p_core_cap"]}, but I do not believe that {c0["p_core_low"]}."'
    )
    c0["p_dual_explicit"] = (
        f'{c0["dual_context"]} Speaking about the situation as a whole, '
        f'{c0["speaker"]} sincerely says: "{c0["p_core_cap"]} {c0["local_mod"]}, but I do not believe that {c0["p_core_low"]} {c0["global_mod"]}."'
    )
    c0["p_pure_read"] = (
        f'{c0["reading_context"]} While reading a printed drama script line aloud to test the microphone '
        f'(without stating any personal beliefs), {c0["speaker"]} reads the line: "{c0["p_atomic_cap"]}, but I do not believe that {c0["p_atomic_low"]}."'
    )
    c0["p_diag_pos"] = (
        f'{c0["all_clear_context"]} Speaking about the situation as a whole, '
        f'{c0["speaker"]} sincerely says: "{c0["p_core_cap"]}, and I fully believe that {c0["p_core_low"]}."'
    )
    c0["p_diag_neg"] = (
        f'{c0["pure_context"]} Looking directly at that single unambiguous indicator, '
        f'{c0["speaker"]} sincerely asserts: "{c0["p_atomic_cap"]}, and at the exact same time and in the exact same sense it is false that {c0["p_atomic_low"]}."'
    )
    c0["hypothesis"] = f"{c0['speaker']}'s utterance in this context is coherent and does not commit {c0['speaker']} to a self-contradiction."
    errs = validate_materials(m_coord, clean_subclasses_manifest, clean_split_manifest)
    if errs:
        mutations_killed += 1
    else:
        print("FAIL: M17 not killed!")

    return mutations_killed


def main() -> int:
    clusters_path = DATA / "clusters_100_e4.json"
    subclasses_path = HERE / "subclasses_e4.json"
    split_path = HERE / "split.json"

    if not clusters_path.exists():
        print(f"ERROR: {clusters_path} does not exist. Run curate_100_clusters_e4.py first.")
        return 1
    if not subclasses_path.exists():
        print(f"ERROR: {subclasses_path} does not exist. Run curate_100_clusters_e4.py first.")
        return 1
    if not split_path.exists():
        print(f"ERROR: {split_path} does not exist. Run curate_100_clusters_e4.py first.")
        return 1

    clusters_obj = json.loads(clusters_path.read_text(encoding="utf-8"))
    subclasses_manifest = json.loads(subclasses_path.read_text(encoding="utf-8"))
    split_manifest = json.loads(split_path.read_text(encoding="utf-8"))

    # Also verify deterministic recreation matches file contents exactly
    expected_clusters_obj = build_clusters_obj()
    if clusters_obj != expected_clusters_obj:
        print("ERROR: clusters_100_e4.json does not match build_clusters_obj() deterministic output!")
        return 1

    expected_subclasses = build_subclasses_manifest()
    if subclasses_manifest != expected_subclasses:
        print("ERROR: subclasses_e4.json does not match build_subclasses_manifest() deterministic output!")
        return 1

    expected_split = build_split_manifest()
    if split_manifest != expected_split:
        print("ERROR: split.json does not match build_split_manifest() deterministic output!")
        return 1

    errors = validate_materials(clusters_obj, subclasses_manifest, split_manifest)
    if errors:
        print(f"validate_materials_e4 FAILED with {len(errors)} errors:")
        for err in errors[:20]:
            print(f"  - {err}")
        return 1

    mutations_killed = run_negative_mutations(clusters_obj, subclasses_manifest, split_manifest)
    if mutations_killed != 17:
        print(f"ERROR: only {mutations_killed}/17 negative mutations were killed.")
        return 1

    print(f"validate_materials_e4: 100/100 clusters PASS (0 errors); negative mutations killed: {mutations_killed}/17")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
