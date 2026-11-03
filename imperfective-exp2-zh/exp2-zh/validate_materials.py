"""Strict mechanical & morphological validator for Experiment 2 (Chinese) minimal-pair clusters."""
import json
from pathlib import Path
import sys

REQUIRED_KEYS = (
    "cluster_id",
    "macro_class",
    "subclass",
    "vp_label",
    "verb_root",
    "comp_marker",
    "temporal_anchor",
    "agent",
    "p_no_int",
    "p_int",
    "h_comp",
    "h_bare",
    "p_diag_pos",
    "p_diag_neg",
)

VALID_SUBCLASSES = {
    "telic": {"Creation", "Change of State", "Consumption", "Motion to Goal"},
    "atelic": {"Pure Unbounded Activity", "Goal-Prone / Planned Activity"},
}

FORBIDDEN_RESTART_WORDS = ("重做", "重来", "买漆", "找备用拍")

ALL_COMP_MARKERS = (
    "完", "好", "干净", "熟", "光", "够", "足", "上", "下",
    "进", "出", "开", "碎", "满", "透", "通", "穿", "掉", "成",
    "干", "断", "平整", "锋利",
)


def validate_clusters(clusters: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_vps: set[str] = set()
    seen_agents: set[str] = set()

    for idx, c in enumerate(clusters):
        cid = c.get("cluster_id", f"index_{idx}")
        cluster_errs: list[str] = []
        for k in REQUIRED_KEYS:
            if k not in c or not isinstance(c[k], str) or not c[k].strip():
                cluster_errs.append(f"{cid}: missing or empty key {k!r}")
        if cluster_errs:
            errors.extend(cluster_errs)
            continue

        if cid in seen_ids:
            errors.append(f"{cid}: duplicate cluster_id")
        seen_ids.add(cid)

        vp = c["vp_label"].strip()
        if vp in seen_vps:
            errors.append(f"{cid}: duplicate vp_label {vp!r}")
        seen_vps.add(vp)

        agent = c["agent"].strip()
        if agent in seen_agents:
            errors.append(f"{cid}: duplicate agent {agent!r}")
        seen_agents.add(agent)

        mc = c["macro_class"]
        sc = c["subclass"]
        if mc not in VALID_SUBCLASSES:
            errors.append(f"{cid}: invalid macro_class {mc!r}")
        elif sc not in VALID_SUBCLASSES[mc]:
            errors.append(f"{cid}: invalid subclass {sc!r} for {mc!r}")

        v_root = c["verb_root"]
        c_mark = c["comp_marker"]
        anchor = c["temporal_anchor"]

        # Subclass-specific complement rules
        if sc == "Pure Unbounded Activity" and c_mark not in ("够", "足"):
            errors.append(f"{cid}: Pure Unbounded Activity must use satiation complement ('够' or '足'), got {c_mark!r}")
        if sc == "Goal-Prone / Planned Activity" and c_mark != "完":
            errors.append(f"{cid}: Goal-Prone / Planned Activity must use task-completion complement '完', got {c_mark!r}")
        if sc == "Motion to Goal" and c_mark != "完":
            errors.append(f"{cid}: Motion to Goal must use path-completion complement '完', got {c_mark!r}")

        for field in ("p_no_int", "p_int", "h_comp", "h_bare", "p_diag_pos", "p_diag_neg"):
            val = c[field]
            if not val.startswith(anchor + "，"):
                errors.append(f"{cid}.{field}: must start with '{anchor}，'")
            if agent not in val:
                errors.append(f"{cid}.{field}: must contain agent {agent!r}")
            if not val.endswith("。"):
                errors.append(f"{cid}.{field}: must end with '。'")

        # Progressive premise checks
        p0 = c["p_no_int"]
        if "正在" not in p0:
            errors.append(f"{cid}.p_no_int: must contain progressive '正在'")
        if v_root not in p0:
            errors.append(f"{cid}.p_no_int: must contain verb_root {v_root!r}")
        if (v_root + c_mark) in p0:
            errors.append(f"{cid}.p_no_int: must NOT leak verb+complement '{v_root}{c_mark}' into progressive premise")
        for leaked_m in ALL_COMP_MARKERS:
            if (v_root + leaked_m) in p0:
                errors.append(f"{cid}.p_no_int: must NOT leak resultative/completion marker '{v_root}{leaked_m}' into progressive premise")

        # Interruption premise checks: strict prefix + window closure + no restart/resume words
        p1 = c["p_int"]
        prefix = p0[:-1] + "，"
        if not p1.startswith(prefix):
            errors.append(f"{cid}.p_int: must start with p_no_int stem '{prefix}'")
        expected_closure = f"，且直到{anchor}结束都没再继续。"
        if not p1.endswith(expected_closure):
            errors.append(f"{cid}.p_int: must end with explicit window closure '{expected_closure}'")
        for bad_w in FORBIDDEN_RESTART_WORDS:
            if bad_w in p1:
                errors.append(f"{cid}.p_int: contains forbidden restart/resume word {bad_w!r}")

        # Hypothesis checks: strict insertion minimal pair
        hc = c["h_comp"]
        hb = c["h_bare"]
        for h_field, h_val in (("h_comp", hc), ("h_bare", hb)):
            if "正在" in h_val:
                errors.append(f"{cid}.{h_field}: must not contain '正在'")
            if "过" in h_val:
                errors.append(f"{cid}.{h_field}: must not contain experiential '过'")
            if "了" not in h_val:
                errors.append(f"{cid}.{h_field}: must contain '了'")

        target_comp = f"{v_root}{c_mark}了"
        target_bare = f"{v_root}了"
        if target_comp not in hc:
            errors.append(f"{cid}.h_comp: must contain '{target_comp}'")
        if target_bare not in hb:
            errors.append(f"{cid}.h_bare: must contain '{target_bare}'")
        if (v_root + c_mark) in hb:
            errors.append(f"{cid}.h_bare: must NOT contain complement '{v_root}{c_mark}'")
        for leaked_m in ALL_COMP_MARKERS:
            if (v_root + leaked_m + "了") in hb:
                errors.append(f"{cid}.h_bare: leaked resultative/completion marker '{v_root}{leaked_m}了'")

        # Character-for-character minimal pair equality after removing comp_marker once
        reconstructed_hb = hc.replace(target_comp, target_bare, 1)
        if reconstructed_hb != hb:
            errors.append(
                f"{cid}: h_comp minus comp_marker does not equal h_bare ({reconstructed_hb!r} != {hb!r})"
            )

        # Diagnostic context checks: exact deterministic derivation from p_no_int and h_comp predicate
        hc_prefix = f"{anchor}，{agent}"
        if not hc.startswith(hc_prefix):
            errors.append(f"{cid}.h_comp: must start with '{hc_prefix}'")
        else:
            hc_pred = hc[len(hc_prefix):]
            hc_pred_neg = hc_pred.replace(target_comp, f"{v_root}{c_mark}", 1)
            expected_diag_pos = f"{p0[:-1]}，并且在{anchor}结束前就{hc_pred}"
            expected_diag_neg = f"{p0[:-1]}，但直到{anchor}结束都还没有{hc_pred_neg}"
            if c["p_diag_pos"] != expected_diag_pos:
                errors.append(
                    f"{cid}.p_diag_pos: must equal deterministic template {expected_diag_pos!r}, got {c['p_diag_pos']!r}"
                )
            if c["p_diag_neg"] != expected_diag_neg:
                errors.append(
                    f"{cid}.p_diag_neg: must equal deterministic template {expected_diag_neg!r}, got {c['p_diag_neg']!r}"
                )

    return errors


def run_negative_self_tests(base_cluster: dict) -> list[str]:
    """Verify that negative mutations are deterministically caught by validate_clusters."""
    failures: list[str] = []

    # 1. Leaked directional/resultative complement in h_bare ("爬上了")
    m1 = dict(base_cluster)
    m1["h_bare"] = m1["h_bare"].replace(f"{m1['verb_root']}了", f"{m1['verb_root']}上了", 1)
    if not validate_clusters([m1]):
        failures.append("Negative test 1 failed: leaked '上了' in h_bare was not caught")

    # 2. Motion to Goal using '上' instead of '完'
    m2 = dict(base_cluster, macro_class="telic", subclass="Motion to Goal", comp_marker="上")
    if not validate_clusters([m2]):
        failures.append("Negative test 2 failed: Motion to Goal with comp_marker='上' was not caught")

    # 3. Non-minimal pair (extra word in h_comp)
    m3 = dict(base_cluster)
    m3["h_comp"] = m3["h_comp"][:-1] + "任务。"
    if not validate_clusters([m3]):
        failures.append("Negative test 3 failed: non-minimal pair h_comp vs h_bare was not caught")

    # 4. Missing observation window closure in p_int
    m4 = dict(base_cluster)
    m4["p_int"] = m4["p_no_int"][:-1] + "，但中途停了下来。"
    if not validate_clusters([m4]):
        failures.append("Negative test 4 failed: missing window closure in p_int was not caught")

    # 5. Cross-window temporal expression in p_diag_pos
    m5 = dict(base_cluster)
    m5["p_diag_pos"] = m5["p_no_int"][:-1] + "，并且到了傍晚顺利完成了。"
    if not validate_clusters([m5]):
        failures.append("Negative test 5 failed: cross-window p_diag_pos was not caught")

    # 6. Leaked alternative complement ('完' when comp_marker='好') into p_no_int + derived sentences
    m6 = dict(base_cluster)
    v_r = m6["verb_root"]
    old_p0 = m6["p_no_int"]
    new_p0 = old_p0.replace(v_r, v_r + "完", 1)
    m6["p_no_int"] = new_p0
    m6["p_int"] = m6["p_int"].replace(old_p0[:-1], new_p0[:-1], 1)
    m6["p_diag_pos"] = m6["p_diag_pos"].replace(old_p0[:-1], new_p0[:-1], 1)
    m6["p_diag_neg"] = m6["p_diag_neg"].replace(old_p0[:-1], new_p0[:-1], 1)
    if not validate_clusters([m6]):
        failures.append("Negative test 6 failed: leaked alternative complement in p_no_int was not caught")

    # 7. Positive diagnostic predicate replaced by unrelated predicate ("...结束前就回家了。")
    m7 = dict(base_cluster)
    m7["p_diag_pos"] = f"{m7['p_no_int'][:-1]}，并且在{m7['temporal_anchor']}结束前就回家了。"
    if not validate_clusters([m7]):
        failures.append("Negative test 7 failed: mutated predicate in p_diag_pos was not caught")

    # 8. Negative diagnostic predicate replaced by unrelated predicate ("...结束都还没有回家。")
    m8 = dict(base_cluster)
    m8["p_diag_neg"] = f"{m8['p_no_int'][:-1]}，但直到{m8['temporal_anchor']}结束都还没有回家。"
    if not validate_clusters([m8]):
        failures.append("Negative test 8 failed: mutated predicate in p_diag_neg was not caught")

    # 9. Multi-error (within-cluster + cross-cluster) collection with no early skip
    bad_a = dict(base_cluster, cluster_id="BAD_A", vp_label="")
    bad_b = dict(base_cluster, cluster_id="BAD_B", agent="测试施事B", vp_label="测试动作B")
    bad_b["p_no_int"] = bad_b["p_no_int"].replace(bad_b["verb_root"], bad_b["verb_root"] + "完", 1)
    bad_b["p_diag_pos"] = f"{bad_b['p_no_int'][:-1]}，并且在{bad_b['temporal_anchor']}结束前就回家了。"
    errs_ab = validate_clusters([bad_a, bad_b])
    has_a = any("BAD_A" in e for e in errs_ab)
    has_b_p0 = any("BAD_B.p_no_int" in e for e in errs_ab)
    has_b_diag = any("BAD_B.p_diag_pos" in e for e in errs_ab)
    if not (has_a and has_b_p0 and has_b_diag):
        failures.append("Negative test 9 failed: multi-error collection missed within-cluster or cross-cluster error")

    return failures


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] or [
        Path(__file__).resolve().parent / "data" / "clusters_100_curated.json"
    ]
    all_clusters: list[dict] = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        all_clusters.extend(data)
    errs = validate_clusters(all_clusters)
    if errs:
        for e in errs:
            print("ERROR:", e)
        return 1
    neg_failures = run_negative_self_tests(all_clusters[0])
    if neg_failures:
        for nf in neg_failures:
            print("SELF-TEST ERROR:", nf)
        return 1
    print(f"OK: {len(all_clusters)} clusters validated with 0 errors (and 9/9 negative self-tests passed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
