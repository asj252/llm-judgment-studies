"""Experiment 2 (Chinese) prompt renderer and S1 development-set preview generator.

All linguistic contexts, definitions (DAP), reasoning instructions (CoT), and
counterfactual instructions (CF) are in idiomatic Mandarin Chinese, while the
terminal machine-parsed answer formats (`True`/`False`/`Unknown`,
`Probability: NN%`, `Estimate k: NN% | Weight: W`) match Experiment 1 (`PARSE_VERSION = 2`)
to preserve 100% parser compatibility and verified first-token disjointness.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

COMBINATIONS = (
    ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"),
    ("Ps", "Z"),
    ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
    ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
)

SLOTS = (
    ("NI_COMP", "p_no_int", "h_comp"),
    ("NI_BARE", "p_no_int", "h_bare"),
    ("INT_COMP", "p_int", "h_comp"),
    ("INT_BARE", "p_int", "h_bare"),
)

DIAG_SLOTS = (
    ("DIAG_POS_COMP", "p_diag_pos", "h_comp"),
    ("DIAG_NEG_COMP", "p_diag_neg", "h_comp"),
)

DAP_RULE_ZH = (
    "重要语言学规则：请注意区分“终结性动作”与“持续性活动”。\n"
    "- 对于有特定目标或自然终点的动作（例如“正在盖”“正在写”），进行体（“正在……”）并不蕴含该动作最终完成。\n"
    "- 对于无特定自然终点的持续性活动（例如“正在跑”“正在散步”），进行体即蕴含该活动已经发生。"
)

LABEL_DEFS_ZH = (
    "- 如果仅根据所给前提，该假设必然为真，请输出 \"True\"。\n"
    "- 如果该假设与所给前提相矛盾（必然为假），请输出 \"False\"。\n"
    "- 如果该假设可能为真，但并未被所给前提明确保证，请输出 \"Unknown\"。"
)

L_TEMPLATES_ZH = {
    "Z": {
        "system": (
            "你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n"
            + LABEL_DEFS_ZH
            + "\n不要做任何常识性假设，仅使用所提供的文本信息。"
        ),
        "user_format": (
            "输入：前提：{premise} 假设：{hypothesis}\n"
            "请仅回答以下三个选项之一：\"True\"、\"False\" 或 \"Unknown\"。"
        ),
    },
    "DAP": {
        "system": (
            "你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n"
            + LABEL_DEFS_ZH
            + "\n\n"
            + DAP_RULE_ZH
            + "\n\n不要做任何常识性假设，仅使用所提供的文本信息。"
        ),
        "user_format": (
            "输入：前提：{premise} 假设：{hypothesis}\n"
            "请仅回答以下三个选项之一：\"True\"、\"False\" 或 \"Unknown\"。"
        ),
    },
    "CoT": {
        "system": (
            "你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n"
            + LABEL_DEFS_ZH
            + "\n不要做任何常识性假设，仅使用所提供的文本信息。\n"
            "请先分析前提中事件的时间状态：该动作是否有明确的终点？它是否已经完成？然后再给出最终标签。\n"
            "请严格输出一个 JSON 对象，依次包含两个键：\"reasoning\"（你的简短中文分析字符串）和 \"label\"（取值为 \"True\"、\"False\" 或 \"Unknown\" 之一，且 \"label\" 必须作为最后一个键）。"
        ),
        "user_format": "输入：前提：{premise} 假设：{hypothesis}",
    },
    "CF": {
        "system": (
            "你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n"
            + LABEL_DEFS_ZH
            + "\n不要做任何常识性假设，仅使用所提供的文本信息。\n"
            "在判断假设是否必然为真之前，请先列出 3 个现实中可能发生的情境，使得前提中的动作正在发生，但假设中的结果最终未能实现（例如突发中断或意外失败）。然后再判断假设是否必然为真。\n"
            "请严格输出一个 JSON 对象，依次包含两个键：\"possible_interruptions\"（包含 3 个非空中文情境字符串的 JSON 数组）和 \"label\"（取值为 \"True\"、\"False\" 或 \"Unknown\" 之一，且 \"label\" 必须作为最后一个键）。"
        ),
        "user_format": "输入：前提：{premise} 假设：{hypothesis}",
    },
}

PS_USER_ZH = (
    "输入：前提：{premise} 假设：{hypothesis}\n"
    "仅根据前提，该假设必然为真的机率是多少？\n\n"
    "请在回答的最后一行，严格按以下格式给出答案：\n"
    "Probability: NN%\n"
    "其中 NN 是 0 到 100 之间的数字（允许小数），后面必须紧跟百分号 %。"
)

PM_INSTRUCTIONS_ZH = {
    "CoT": "请先简要分析情境中事件的时间状态：该动作是否有明确的终点？它是否已经完成？然后再给出你的答案。",
    "CF": "请先简要列出 3 个现实中可能发生的情境，使得情境中的动作发生了，但陈述中的结果最终没有达成（例如中途被打断或失败）。然后再给出你的答案。",
}

ASK_DIRECT_ZH = (
    "该陈述为真的机率是多少？\n\n"
    "请在回答的最后一行，严格按以下格式给出答案：\n"
    "Probability: NN%\n"
    "其中 NN 是 0 到 100 之间的数字（允许小数），后面必须紧跟百分号 %。"
)

ASK_MULTI_ZH = (
    "请给出该陈述为真的 5 个机率估计值，并为每个估计值附上一个权重（表示你认为该估计值成立的可能性），5 个权重之和为 1。\n\n"
    "请在回答末尾，严格按以下格式逐行给出 5 个估计值：\n"
    "Estimate 1: NN% | Weight: W\n"
    "Estimate 2: NN% | Weight: W\n"
    "Estimate 3: NN% | Weight: W\n"
    "Estimate 4: NN% | Weight: W\n"
    "Estimate 5: NN% | Weight: W\n"
    "其中每个 NN 是 0 到 100 之间的数字（允许小数）并紧跟百分号 %，每个 W 是 0 到 1 之间的数字（允许小数），且五个权重之和为 1。"
)


def render_unit(premise: str, hypothesis: str, task: str, prompt: str) -> list[dict[str, str]]:
    if (task, prompt) not in COMBINATIONS:
        raise ValueError(f"Unsupported (task, prompt): {(task, prompt)!r}")
    if task in ("L", "Ps"):
        tpl = L_TEMPLATES_ZH[prompt]
        user_txt = tpl["user_format"] if task == "L" else PS_USER_ZH
        return [
            {"role": "system", "content": tpl["system"]},
            {"role": "user", "content": user_txt.format(premise=premise, hypothesis=hypothesis)},
        ]
    parts = [f"这里有一个情境：{premise}"]
    if prompt == "DAP":
        parts.append(DAP_RULE_ZH)
    parts.append(f"根据日常常识，下面这句话为真的可能性有多大？\n陈述：{hypothesis}")
    if prompt in PM_INSTRUCTIONS_ZH:
        parts.append(PM_INSTRUCTIONS_ZH[prompt])
    parts.append(ASK_DIRECT_ZH if task == "P" else ASK_MULTI_ZH)
    return [{"role": "user", "content": "\n\n".join(parts)}]


def generate_s1_preview() -> Path:
    clusters = {
        c["cluster_id"]: c
        for c in json.loads((HERE / "data" / "clusters_100_curated.json").read_text(encoding="utf-8"))
    }
    split_obj = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    dev_ids = set(split_obj["dev_cluster_ids"])

    # Pick 3 representative dev clusters: T_01 (telic), A_pure_01 (pure activity), A_plan_01 (planned activity)
    rep_ids = ("T_01", "A_pure_01", "A_plan_01")
    for rid in rep_ids:
        assert rid in dev_ids, f"Preview cluster {rid} must be in dev set!"

    lines = [
        "# 实验 2（中文版）S1 题面与提示全文预览（仅使用开发集簇）",
        "",
        "- 依据：`PLAN.md` 第 5 节 S1 闸门与 `exp2-zh/PLAN-E2.md` 第 3.2 节。",
        "- 铁律：仅使用 `split.json` 中的开发集簇（`T_01`、`A_pure_01`、`A_plan_01`），严禁触碰正式集 80 簇。",
        "",
    ]
    for rid in rep_ids:
        c = clusters[rid]
        lines.append(f"## 1. 代表簇 `{rid}`（{c['macro_class']} / {c['subclass']}：{c['vp_label']}）四槽题面")
        lines.append("")
        for slot_name, p_key, h_key in SLOTS + DIAG_SLOTS:
            lines.append(f"- **`{slot_name}`**：前提 = 「{c[p_key]}」｜假设 = 「{c[h_key]}」")
        lines.append("")

    c0 = clusters["T_01"]
    lines.append("## 2. 13 个（任务 × 提示）组合逐字渲染全文（以 `T_01` 之 `NI_COMP` 槽为例）")
    lines.append("")
    for task, prompt in COMBINATIONS:
        msgs = render_unit(c0["p_no_int"], c0["h_comp"], task, prompt)
        lines.append(f"### `{task}/{prompt}`")
        for m in msgs:
            lines.append(f"**Role: `{m['role']}`**")
            lines.append("```text")
            lines.append(m["content"])
            lines.append("```")
        lines.append("")

    out_path = HERE / "s1_preview_zh.md"
    out_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    out_path.write_bytes(out_bytes)
    print(f"OK: wrote {out_path.name} ({len(out_bytes)} bytes, sha256={hashlib.sha256(out_bytes).hexdigest()[:16]}...).")
    return out_path


def verify_parser_compatibility() -> None:
    import parse as p2

    assert p2.PARSE_VERSION == 2, f"Expected PARSE_VERSION=2, got {p2.PARSE_VERSION}"
    # Check L/Z & L/DAP plain label
    res_lz = p2.parse_label_plain("Unknown")
    assert res_lz["label"] == "Unknown" and res_lz["form"] == "exact"

    # Check L/CoT JSON
    assert '"reasoning"' in L_TEMPLATES_ZH["CoT"]["system"] and '"label"' in L_TEMPLATES_ZH["CoT"]["system"]
    res_cot = p2.parse_label_json('{"reasoning": "该动作为终结性事件，正在盖并不保证盖好。", "label": "Unknown"}', prompt="CoT")
    assert res_cot["label"] == "Unknown" and res_cot["reasoning_ok"] and res_cot["label_last"] and not res_cot["extra_keys"]

    # Check L/CF JSON (Blocker 1 regression test)
    assert '"possible_interruptions"' in L_TEMPLATES_ZH["CF"]["system"] and '"label"' in L_TEMPLATES_ZH["CF"]["system"]
    assert "counterfactuals" not in L_TEMPLATES_ZH["CF"]["system"]
    res_cf = p2.parse_label_json(
        '{"possible_interruptions": ["中途下暴雨停工", "木材不够停下", "木匠临时有事离开"], "label": "Unknown"}',
        prompt="CF",
    )
    assert (
        res_cf["label"] == "Unknown"
        and res_cf["reasoning_ok"]
        and res_cf["label_last"]
        and res_cf["n_interruptions"] == 3
        and not res_cf["extra_keys"]
    )
    # Negative test: old key "counterfactuals" must fail reasoning_ok and label_last
    res_cf_bad = p2.parse_label_json(
        '{"counterfactuals": ["a", "b", "c"], "label": "Unknown"}',
        prompt="CF",
    )
    assert not res_cf_bad["reasoning_ok"] and not res_cf_bad["label_last"] and res_cf_bad["extra_keys"] == ["counterfactuals"]

    # Check Ps/Z and P/* direct probability
    res_dir = p2.parse_direct("分析过程略。\nProbability: 35%")
    assert res_dir["ok"] and res_dir["value"] == 35.0

    # Check M/* multi probability
    res_mul = p2.parse_multi(
        "分析过程略。\n"
        "Estimate 1: 20% | Weight: 0.2\n"
        "Estimate 2: 30% | Weight: 0.2\n"
        "Estimate 3: 40% | Weight: 0.2\n"
        "Estimate 4: 50% | Weight: 0.2\n"
        "Estimate 5: 60% | Weight: 0.2"
    )
    assert res_mul["ok"] and abs(res_mul["value"] - 40.0) < 1e-9
    print("OK: PARSE_VERSION=2 compatibility verified across all 13 (task, prompt) formats.")


if __name__ == "__main__":
    verify_parser_compatibility()
    generate_s1_preview()
