"""Experiment 4 (Moore's Paradox vs. Verbalized Sampling) prompt renderer and S1 preview generator.

Implements all 13 (task, prompt) conditions for exp4-moore, verifies 100% parser
compatibility with parse.py (PARSE_VERSION = 2) and protocol.py, and generates
the S1 preview file s1_preview_e4.md.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import parse as p2
from prompt_parts import ASK_DIRECT, ASK_MULTI, terminate
import protocol

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

COMBINATIONS: tuple[tuple[str, str], ...] = (
    ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"),
    ("Ps", "Z"),
    ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
    ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
)

SLOTS: tuple[tuple[str, str, str], ...] = (
    ("PURE_MOORE", "p_pure_moore", "hypothesis"),
    ("DUAL_MOORE", "p_dual_moore", "hypothesis"),
    ("DUAL_EXPLICIT", "p_dual_explicit", "hypothesis"),
    ("PURE_READ", "p_pure_read", "hypothesis"),
)

DIAG_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("DIAG_POS", "p_diag_pos", "hypothesis"),
    ("DIAG_NEG", "p_diag_neg", "hypothesis"),
)

DAP_RULE_E4 = (
    "Important Linguistic & Pragmatic Principle: Note the distinction between a single-standard assertion conflict and a multi-criteria or non-assertive utterance.\n"
    '- When a speaker sincerely asserts a single unambiguous atomic fact while simultaneously denying belief in that exact same fact under the same standard, the utterance commits the speaker to a self-contradiction.\n'
    '- When an utterance evaluates a situation across two distinct standards (such as local technical compliance versus broader systemic risk), or when a speaker merely reads a line aloud without asserting personal belief, the utterance can be coherent and does not commit the speaker to a self-contradiction.'
)

STRICT_LOGICIAN_SYSTEM = (
    "System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.\n"
    'If the Hypothesis MUST be true based only on the Premise, output "True".\n'
    'If the Hypothesis is contradicted by the Premise, output "False".\n'
    'If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".\n'
    "Do not use common sense assumptions. Only use the text provided."
)

STRICT_LOGICIAN_SYSTEM_DAP = (
    "System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.\n"
    'If the Hypothesis MUST be true based only on the Premise, output "True".\n'
    'If the Hypothesis is contradicted by the Premise, output "False".\n'
    'If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".\n\n'
    f"{DAP_RULE_E4}\n"
    "Do not use common sense assumptions. Only use the text provided."
)

L_TEMPLATES_E4: dict[str, dict[str, str]] = {
    "Z": {
        "system": STRICT_LOGICIAN_SYSTEM,
        "user_format": (
            "User Input: Premise: {premise} Hypothesis: {hypothesis}\n"
            'Please respond with ONLY one of the following options: "True", "False", or "Unknown".'
        ),
    },
    "DAP": {
        "system": STRICT_LOGICIAN_SYSTEM_DAP,
        "user_format": (
            "User Input: Premise: {premise} Hypothesis: {hypothesis}\n"
            'Please respond with ONLY one of the following options: "True", "False", or "Unknown".'
        ),
    },
    "CoT": {
        "system": STRICT_LOGICIAN_SYSTEM,
        "user_format": (
            "Premise: {premise}\n"
            "Hypothesis: {hypothesis}\n\n"
            "Instruction: First, analyze step by step in a single reasoning chain whether the speaker's utterance in the premise commits a logical or pragmatic contradiction. Then, provide your final label (True, False, or Unknown).\n\n"
            "Output Requirement: You must output your response in strict JSON format containing exactly two keys:\n"
            '1. "reasoning": A string explaining your step-by-step logic.\n'
            '2. "label": The final judgment ("True", "False", or "Unknown").\n\n'
            "Do not include markdown formatting (like ```json). Return ONLY the JSON object.\n"
            "Example Format:\n"
            "{{\n"
            '  "reasoning": "...",\n'
            '  "label": "True" / "False" / "Unknown"\n'
            "}}"
        ),
    },
    "CF": {
        "system": STRICT_LOGICIAN_SYSTEM,
        "user_format": (
            "Premise: {premise}\n"
            "Hypothesis: {hypothesis}\n\n"
            "Instruction: \n"
            "1. First, list 3 distinct competing contextual interpretations or factors (for example, literal single-standard conflict, dual evaluation standards such as local technical compliance versus global crisis risk, or non-assertive reading) that affect whether the speaker's utterance commits a self-contradiction.\n"
            "2. Based on these possibilities, determine if the hypothesis is necessarily true.\n\n"
            "Output Requirement: You must output your response in strict JSON format containing exactly two keys:\n"
            '1. "possible_interruptions": a list of three strings for 3 distinct competing contextual interpretations or factors.\n'
            '2. "label": The final judgment ("True", "False", or "Unknown").\n\n'
            "Do not include markdown formatting (like ```json). Return ONLY the JSON object.\n"
            "Example Format:\n"
            "{{\n"
            '  "possible_interruptions": ["..."],\n'
            '  "label": "True" / "False" / "Unknown"\n'
            "}}"
        ),
    },
}

PS_USER_E4 = (
    "User Input: Premise: {premise} Hypothesis: {hypothesis}\n"
    "What is the probability that the Hypothesis is necessarily true given only the Premise?\n\n"
    "On the last line of your answer, give the answer strictly in the following format:\n"
    "Probability: NN%\n"
    "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
)

INSTRUCTIONS_E4: dict[str, str] = {
    "CoT": (
        "First, analyze step by step in a single reasoning chain whether the speaker's utterance commits a logical or pragmatic contradiction (such as asserting a proposition while denying belief in it). "
        'Do not use the word "Estimate", the word "Probability:", or the "%" sign in your analysis paragraph. '
        "Then leave a blank line and give your final numerical answer."
    ),
    "CF": (
        "Before giving your final answer, write 5 short lines in a separate paragraph listing 5 distinct candidate perspectives on whether the speaker's utterance is coherent in this situation "
        "(such as evaluating the utterance across two distinct standards—local technical compliance versus broader systemic risk—versus treating it as a single-standard conflict, pragmatic hedging, or non-assertive reading), "
        'labeled "Interpretation 1:" through "Interpretation 5:" (do not use the word "Estimate" or the "%" sign in those 5 lines). '
        "Then leave a blank line and give your final answer at the very end strictly in the format requested below "
        "(when giving 5 estimates, each Estimate k: NN% is the conditional probability from 0% to 100% that the Statement is true under Interpretation k—so the five NN% values do NOT sum to 100%—and Weight: W is how plausible Interpretation k is in this situation, with the five weights summing to 1)."
    ),
}


def render_unit(premise: str, hypothesis: str, task: str, prompt: str) -> list[dict[str, str]]:
    if (task, prompt) not in COMBINATIONS:
        raise ValueError(f"Unsupported (task, prompt): {(task, prompt)!r}")

    if task == "L":
        t = L_TEMPLATES_E4[prompt]
        return [
            {"role": "system", "content": t["system"]},
            {"role": "user", "content": t["user_format"].format(premise=premise, hypothesis=hypothesis)},
        ]
    elif task == "Ps":
        return [
            {"role": "system", "content": STRICT_LOGICIAN_SYSTEM},
            {"role": "user", "content": PS_USER_E4.format(premise=premise, hypothesis=hypothesis)},
        ]

    # Tasks P and M
    parts: list[str] = ["Here is a situation: " + terminate(premise)]
    if prompt == "DAP":
        parts.append(DAP_RULE_E4)
    parts.append(
        "Using common sense, how likely is it that the following statement is true?\nStatement: "
        + terminate(hypothesis)
    )
    if prompt in INSTRUCTIONS_E4:
        parts.append(INSTRUCTIONS_E4[prompt])
    parts.append(ASK_DIRECT if task == "P" else ASK_MULTI)
    return [{"role": "user", "content": "\n\n".join(parts)}]


def verify_parser_compatibility() -> dict[str, Any]:
    assert p2.PARSE_VERSION == 2, f"Expected PARSE_VERSION == 2, got {p2.PARSE_VERSION}"

    # Synthetic outputs for all 13 conditions
    synthetic_samples: dict[tuple[str, str], tuple[str, Any]] = {
        ("L", "Z"): (
            "True",
            p2.parse_label_plain("True")
        ),
        ("L", "DAP"): (
            "True",
            p2.parse_label_plain("True")
        ),
        ("L", "CoT"): (
            json.dumps({"reasoning": "The premise evaluates the situation across two distinct standards.", "label": "True"}),
            p2.parse_label_json(json.dumps({"reasoning": "The premise evaluates the situation across two distinct standards.", "label": "True"}), prompt="CoT")
        ),
        ("L", "CF"): (
            json.dumps({
                "possible_interruptions": [
                    "Single-standard assertion conflict",
                    "Dual evaluation standards across local technical compliance versus global crisis",
                    "Non-assertive script reading"
                ],
                "label": "True"
            }),
            p2.parse_label_json(json.dumps({
                "possible_interruptions": [
                    "Single-standard assertion conflict",
                    "Dual evaluation standards across local technical compliance versus global crisis",
                    "Non-assertive script reading"
                ],
                "label": "True"
            }), prompt="CF")
        ),
        ("Ps", "Z"): (
            "Given the premise, here is the assessment.\nProbability: 80%",
            p2.parse_direct("Given the premise, here is the assessment.\nProbability: 80%")
        ),
        ("P", "Z"): (
            "Based on the situation.\nProbability: 85%",
            p2.parse_direct("Based on the situation.\nProbability: 85%")
        ),
        ("P", "DAP"): (
            "Applying pragmatic principles.\nProbability: 85%",
            p2.parse_direct("Applying pragmatic principles.\nProbability: 85%")
        ),
        ("P", "CoT"): (
            "Analysis of the speaker utterance shows a distinction between local compliance and systemic risk.\n\nProbability: 75%",
            p2.parse_direct("Analysis of the speaker utterance shows a distinction between local compliance and systemic risk.\n\nProbability: 75%")
        ),
        ("P", "CF"): (
            "Interpretation 1: Literal single-standard conflict.\n"
            "Interpretation 2: Dual evaluation standards.\n"
            "Interpretation 3: Contextual hedging.\n"
            "Interpretation 4: Non-assertive rehearsal.\n"
            "Interpretation 5: Figurative delivery.\n\n"
            "Probability: 70%",
            p2.parse_direct(
                "Interpretation 1: Literal single-standard conflict.\n"
                "Interpretation 2: Dual evaluation standards.\n"
                "Interpretation 3: Contextual hedging.\n"
                "Interpretation 4: Non-assertive rehearsal.\n"
                "Interpretation 5: Figurative delivery.\n\n"
                "Probability: 70%"
            )
        ),
        ("M", "Z"): (
            "Estimate 1: 90% | Weight: 0.2\n"
            "Estimate 2: 85% | Weight: 0.2\n"
            "Estimate 3: 80% | Weight: 0.2\n"
            "Estimate 4: 75% | Weight: 0.2\n"
            "Estimate 5: 70% | Weight: 0.2",
            p2.parse_multi(
                "Estimate 1: 90% | Weight: 0.2\n"
                "Estimate 2: 85% | Weight: 0.2\n"
                "Estimate 3: 80% | Weight: 0.2\n"
                "Estimate 4: 75% | Weight: 0.2\n"
                "Estimate 5: 70% | Weight: 0.2"
            )
        ),
        ("M", "DAP"): (
            "Estimate 1: 85% | Weight: 0.2\n"
            "Estimate 2: 80% | Weight: 0.2\n"
            "Estimate 3: 75% | Weight: 0.2\n"
            "Estimate 4: 70% | Weight: 0.2\n"
            "Estimate 5: 65% | Weight: 0.2",
            p2.parse_multi(
                "Estimate 1: 85% | Weight: 0.2\n"
                "Estimate 2: 80% | Weight: 0.2\n"
                "Estimate 3: 75% | Weight: 0.2\n"
                "Estimate 4: 70% | Weight: 0.2\n"
                "Estimate 5: 65% | Weight: 0.2"
            )
        ),
        ("M", "CoT"): (
            "First, analyzing step by step the utterance evaluates local versus systemic factors.\n\n"
            "Estimate 1: 80% | Weight: 0.2\n"
            "Estimate 2: 70% | Weight: 0.2\n"
            "Estimate 3: 60% | Weight: 0.2\n"
            "Estimate 4: 50% | Weight: 0.2\n"
            "Estimate 5: 40% | Weight: 0.2",
            p2.parse_multi(
                "First, analyzing step by step the utterance evaluates local versus systemic factors.\n\n"
                "Estimate 1: 80% | Weight: 0.2\n"
                "Estimate 2: 70% | Weight: 0.2\n"
                "Estimate 3: 60% | Weight: 0.2\n"
                "Estimate 4: 50% | Weight: 0.2\n"
                "Estimate 5: 40% | Weight: 0.2"
            )
        ),
        ("M", "CF"): (
            "Interpretation 1: Literal single-standard contradiction where asserting P and denying belief in P directly conflicts.\n"
            "Interpretation 2: Dual evaluation standards where P is met under local criteria but not global criteria (2 criteria).\n"
            "Interpretation 3: Contextual hedging where speaker doubts personal perception.\n"
            "Interpretation 4: Figurative irony expressing frustration with technical metrics.\n"
            "Interpretation 5: Non-assertive dramatic quote testing vocal delivery.\n\n"
            "Estimate 1: 15% | Weight: 0.2\n"
            "Estimate 2: 75% | Weight: 0.2\n"
            "Estimate 3: 40% | Weight: 0.2\n"
            "Estimate 4: 30% | Weight: 0.2\n"
            "Estimate 5: 60% | Weight: 0.2",
            p2.parse_multi(
                "Interpretation 1: Literal single-standard contradiction where asserting P and denying belief in P directly conflicts.\n"
                "Interpretation 2: Dual evaluation standards where P is met under local criteria but not global criteria (2 criteria).\n"
                "Interpretation 3: Contextual hedging where speaker doubts personal perception.\n"
                "Interpretation 4: Figurative irony expressing frustration with technical metrics.\n"
                "Interpretation 5: Non-assertive dramatic quote testing vocal delivery.\n\n"
                "Estimate 1: 15% | Weight: 0.2\n"
                "Estimate 2: 75% | Weight: 0.2\n"
                "Estimate 3: 40% | Weight: 0.2\n"
                "Estimate 4: 30% | Weight: 0.2\n"
                "Estimate 5: 60% | Weight: 0.2"
            )
        ),
    }

    results: dict[str, str] = {}
    for (task, prompt), (raw_text, parsed) in synthetic_samples.items():
        # Verify parse result
        if task in ("P", "Ps", "M"):
            assert parsed["ok"] is True, f"Failed parse for {task}/{prompt}: {parsed}"
        elif task == "L" and prompt in ("Z", "DAP"):
            assert parsed["label"] == "True" and parsed["form"] == "exact", f"Failed parse for {task}/{prompt}: {parsed}"
        elif task == "L" and prompt == "CoT":
            assert parsed["label"] == "True" and parsed["reasoning_ok"] and parsed["label_last"], f"Failed parse for {task}/{prompt}: {parsed}"
        elif task == "L" and prompt == "CF":
            assert parsed["label"] == "True" and parsed["reasoning_ok"] and parsed["label_last"] and parsed["n_interruptions"] == 3, f"Failed parse for {task}/{prompt}: {parsed}"

        # Verify protocol check
        proto = protocol.check(raw_text, task, prompt, parsed)
        assert proto["protocol_ok"] is True, f"Protocol check failed for {task}/{prompt}: {proto}"

        # Verify prompt rendering
        rendered = render_unit("Sample premise text.", "Sample hypothesis statement.", task, prompt)
        assert isinstance(rendered, list) and len(rendered) in (1, 2)
        results[f"{task}/{prompt}"] = "PASS"

    # Negative test: contaminating Estimate line with free text and numbers
    bad_line_multi = (
        "Estimate 1: 15% (2 criteria) | Weight: 0.2\n"
        "Estimate 2: 75% | Weight: 0.2\n"
        "Estimate 3: 40% | Weight: 0.2\n"
        "Estimate 4: 30% | Weight: 0.2\n"
        "Estimate 5: 60% | Weight: 0.2"
    )
    bad_parsed = p2.parse_multi(bad_line_multi)
    assert bad_parsed["ok"] is False, "Expected parse_multi to reject in-line text with numbers!"
    assert bad_parsed.get("error") == "estimate_range_or_extra_number", f"Expected 'estimate_range_or_extra_number', got {bad_parsed.get('error')}"

    return results


def generate_s1_preview() -> str:
    clusters_path = DATA / "clusters_100_e4.json"
    split_path = HERE / "split.json"

    clusters_obj = json.loads(clusters_path.read_text(encoding="utf-8"))
    split_manifest = json.loads(split_path.read_text(encoding="utf-8"))

    clusters_by_id = {c["cluster_id"]: c for c in clusters_obj["clusters"]}
    dev_ids: list[str] = split_manifest["dev"]["cluster_ids"]
    smoke_ids: list[str] = split_manifest["smoke"]["cluster_ids"]

    lines: list[str] = [
        "# `#imperfective` 实验 4（`exp4-moore` 摩尔悖论与多维判准 VS 对照实验）S1 开发集预览 (`s1_preview_e4.md`)",
        "",
        "- **实验版本**：`exp4-moore`（Moore's Paradox vs. Verbalized Sampling）",
        "- **前置依据**：`PLAN-E4.md` §2、§3 与 `PROTOCOL_NOTE_VS_FORMAT_FOR_E3_E4.md` 四大格式防呆准则。",
        "- **切分信息**：种子 `2026110601`，4 大领域子类（`D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`）各 5 个开发簇，共 20 个开发簇（占位编号 `002`..`100`）；正式集 80 簇完全隔离未触碰。",
        "- **槽位结构**：每簇 4 个正交主槽位（`PURE_MOORE`, `DUAL_MOORE`, `DUAL_EXPLICIT`, `PURE_READ`）+ 2 个诊断槽位（`DIAG_POS`, `DIAG_NEG`），共享统一假设句（$H_{\\text{coh}}$）。",
        "",
        "---",
        "",
        "## 1. 开发集全部 20 簇四主槽 + 二诊断槽完整题面",
        "",
    ]

    for cid in dev_ids:
        c = clusters_by_id[cid]
        dom = c["domain_subclass"]
        topic = c["topic_label"]
        speaker = c["speaker"]
        hyp = c["hypothesis"]

        lines.append(f"### 簇 `{cid}`（领域子类：`{dom}` ｜ 议题：`{topic}` ｜ 说话者：`{speaker}`）")
        lines.append(f"- **统一假设句 ($H_{{\\text{{coh}}}}$)**: `{hyp}`")
        lines.append(f"- **`PURE_MOORE` (单维原子事实裸摩尔句 - 地板基线)**:")
        lines.append(f"  `{c['p_pure_moore']}`")
        lines.append(f"- **`DUAL_MOORE` (双重判准危机语境裸摩尔句 - 核心测试槽)**:")
        lines.append(f"  `{c['p_dual_moore']}`")
        lines.append(f"- **`DUAL_EXPLICIT` (双重判准显式消歧句 - 上界锚点)**:")
        lines.append(f"  `{c['p_dual_explicit']}`")
        lines.append(f"- **`PURE_READ` (非断言朗读台词控制槽 - 取消信念断言承诺)**:")
        lines.append(f"  `{c['p_pure_read']}`")
        lines.append(f"- **`DIAG_POS` (正向诊断 - 全局与局部完全达标且真诚相信)**:")
        lines.append(f"  `{c['p_diag_pos']}`")
        lines.append(f"- **`DIAG_NEG` (反向诊断 - 同一标准显式逻辑自相矛盾)**:")
        lines.append(f"  `{c['p_diag_neg']}`")
        lines.append("")

    # Section 2: 13 conditions rendered on first smoke cluster's DUAL_MOORE slot
    smoke_0 = smoke_ids[0]
    c_smoke = clusters_by_id[smoke_0]
    p_smoke = c_smoke["p_dual_moore"]
    h_smoke = c_smoke["hypothesis"]

    lines.append("---")
    lines.append("")
    lines.append(f"## 2. 13 个（任务 × 提示）组合逐字渲染全文（以首个冒烟簇 `{smoke_0}`（`{c_smoke['topic_label']}`）之 `DUAL_MOORE` 槽为例）")
    lines.append("")
    lines.append(f"- **当前槽位**：`DUAL_MOORE_{smoke_0}`")
    lines.append(f"- **前提 ($P$)**：`{p_smoke}`")
    lines.append(f"- **假设 ($H$)**：`{h_smoke}`")
    lines.append("")

    for task, prompt in COMBINATIONS:
        msgs = render_unit(p_smoke, h_smoke, task, prompt)
        lines.append(f"### `{task}/{prompt}`")
        for m in msgs:
            lines.append(f"**Role: `{m['role']}`**")
            lines.append("```text")
            lines.append(m["content"])
            lines.append("```")
        lines.append("")

    out_file = HERE / "s1_preview_e4.md"
    content = "\n".join(lines) + "\n"
    out_file.write_bytes(content.encode("utf-8"))
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return sha


def main() -> int:
    compat = verify_parser_compatibility()
    print("Parser & Protocol compatibility verified for all 13 combinations:")
    for k, v in compat.items():
        print(f"  {k:8s}: {v}")

    sha = generate_s1_preview()
    preview_path = HERE / "s1_preview_e4.md"
    print(f"\nGenerated S1 preview: {preview_path} (SHA-256: {sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
