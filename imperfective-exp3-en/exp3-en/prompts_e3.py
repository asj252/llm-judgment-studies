"""Experiment 3 (English B/D Disambiguation) prompt renderer and S1 preview generator.

Uses the exact English prompt templates from Experiment 1 (`exp1-en/prompts.py` +
`data/run_inference.py.txt`, SHA-256 `5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880`)
and verifies 100% compatibility with `exp3-en/parse.py` (`PARSE_VERSION = 2`).
"""
from __future__ import annotations

import ast
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import parse as p2
from prompt_parts import ASK_DIRECT, ASK_MULTI, terminate

HERE = Path(__file__).resolve().parent
RUN_INFERENCE_SHA256 = "5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880"

COMBINATIONS: tuple[tuple[str, str], ...] = (
    ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"),
    ("Ps", "Z"),
    ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
    ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
)

SLOTS: tuple[tuple[str, str, str], ...] = (
    ("NI_OCC", "p_no_int", "h_occ"),
    ("NI_PLAN", "p_no_int", "h_plan"),
    ("INT_OCC", "p_int", "h_occ"),
    ("INT_PLAN", "p_int", "h_plan"),
)

DIAG_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("DIAG_POS", "p_diag_pos", "h_plan"),
    ("DIAG_NEG", "p_diag_neg", "h_plan"),
)

KEYS = {"Z": "zero-shot", "DAP": "dap", "CoT": "cot", "CF": "counterfactual"}

RULE = (
    "Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.\n"
    '- For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.\n'
    '- For activities (e.g., "was running", "was singing"), the process implies the action occurred.'
)

INSTRUCTIONS = {
    "CoT": "First, analyze the temporal status of the event in the situation. Does the action have a defined endpoint? Was it completed? Then give your answer.",
    "CF": "First, list 3 possible real-world scenarios where the action in the situation occurs but the result in the statement is NOT achieved (e.g., interruptions, failures). Then give your answer.",
}

PS = (
    "User Input: Premise: {premise} Hypothesis: {hypothesis}\n"
    "What is the probability that the Hypothesis is necessarily true given only the Premise?\n\n"
    "On the last line of your answer, give the answer strictly in the following format:\n"
    "Probability: NN%\n"
    "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
)


@lru_cache(maxsize=1)
def original_templates() -> dict[str, dict[str, str]]:
    p = HERE / "data" / "run_inference.py.txt"
    actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    if actual_sha != RUN_INFERENCE_SHA256:
        raise ValueError(f"run_inference.py.txt SHA-256 mismatch: {actual_sha}")
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PROMPT_TEMPLATES" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("PROMPT_TEMPLATES dictionary literal not found")


def render_unit(premise: str, hypothesis: str, task: str, prompt: str) -> list[dict[str, str]]:
    if (task, prompt) not in COMBINATIONS:
        raise ValueError(f"Unsupported (task, prompt): {(task, prompt)!r}")
    if task in ("L", "Ps"):
        t = original_templates()[KEYS[prompt]]
        user = t["user_format"] if task == "L" else PS
        return [
            {"role": "system", "content": t["system"]},
            {"role": "user", "content": user.format(premise=premise, hypothesis=hypothesis)},
        ]
    parts = ["Here is a situation: " + terminate(premise)]
    if prompt == "DAP":
        parts.append(RULE)
    parts.append(
        "Using common sense, how likely is it that the following statement is true?\nStatement: "
        + terminate(hypothesis)
    )
    if prompt in INSTRUCTIONS:
        parts.append(INSTRUCTIONS[prompt])
    parts.append(ASK_DIRECT if task == "P" else ASK_MULTI)
    return [{"role": "user", "content": "\n\n".join(parts)}]


def verify_parser_compatibility() -> dict[str, str]:
    assert p2.PARSE_VERSION == 2, f"Expected PARSE_VERSION == 2, got {p2.PARSE_VERSION}"
    tpls = original_templates()
    cot_full = tpls["cot"]["system"] + "\n" + tpls["cot"]["user_format"]
    cf_full = tpls["counterfactual"]["system"] + "\n" + tpls["counterfactual"]["user_format"]
    assert '"reasoning"' in cot_full and '"label"' in cot_full
    assert '"possible_interruptions"' in cf_full and '"label"' in cf_full

    res_lz = p2.parse_label_plain("True")
    assert res_lz["label"] == "True" and res_lz["form"] == "exact"

    res_cot = p2.parse_label_json(
        '{"reasoning": "The action took place briefly before stopping.", "label": "True"}',
        prompt="CoT",
    )
    assert res_cot["label"] == "True" and res_cot["reasoning_ok"] and res_cot["label_last"] and not res_cot["extra_keys"]

    res_cf = p2.parse_label_json(
        '{"possible_interruptions": ["rain", "injury", "alarm"], "label": "Unknown"}',
        prompt="CF",
    )
    assert res_cf["label"] == "Unknown" and res_cf["reasoning_ok"] and res_cf["label_last"] and res_cf["n_interruptions"] == 3 and not res_cf["extra_keys"]

    res_dir = p2.parse_direct("The event occurred briefly.\nProbability: 85%")
    assert res_dir["ok"] and res_dir["value"] == 85.0

    res_mul = p2.parse_multi(
        "Analysis first.\n"
        "Estimate 1: 90% | Weight: 0.2\n"
        "Estimate 2: 85% | Weight: 0.2\n"
        "Estimate 3: 80% | Weight: 0.2\n"
        "Estimate 4: 75% | Weight: 0.2\n"
        "Estimate 5: 70% | Weight: 0.2"
    )
    assert res_mul["ok"] and abs(res_mul["value"] - 80.0) < 1e-9

    status: dict[str, str] = {}
    for task, prompt in COMBINATIONS:
        msgs = render_unit("The subject was V-ing.", "The subject V-ed.", task, prompt)
        assert isinstance(msgs, list) and len(msgs) in (1, 2)
        status[f"{task}/{prompt}"] = "PASS"
    return status


def generate_s1_previews() -> tuple[str, str]:
    clusters_data = json.loads((HERE / "data" / "clusters_100_e3.json").read_text(encoding="utf-8"))
    clusters = {c["cluster_id"]: c for c in clusters_data["clusters"]}
    split_obj = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    dev_ids: list[str] = split_obj["dev"]["cluster_ids"]
    smoke_ids: list[str] = split_obj["smoke"]["cluster_ids"]

    # 1. Full S1 dev preview (stored in gitignored data/s1_preview_e3.md because it includes upstream D_k/B_k premises)
    lines_full = [
        "# 实验 3（英文活动边界消歧版）S1 开发集 20 簇题面与 13 条件提示全文预览",
        "",
        "- 依据：`PLAN.md` 第 5 节 S1 闸门与 `exp3-en/PLAN-E3.md` 第 2、3 节。",
        "- 铁律：仅使用 `split.json` 中的开发集 20 簇（严禁触碰正式集 80 簇）；因包含上游 `ImperfectiveNLI`（CC BY-NC 4.0）前提文本，本全文预览存放于 `exp3-en/data/s1_preview_e3.md`（git 排除）。",
        "",
        "## 1. 开发集全部 20 簇四主槽 + 二诊断槽完整题面",
        "",
    ]
    for cid in dev_ids:
        c = clusters[cid]
        lines_full.append(
            f"### 簇 `{cid}`（大类子类：`{c['macro_subclass']}` / 模具子类：`{c['template_subclass']}`｜上游原假设：`{c['h_orig']}`）"
        )
        for slot_name, p_key, h_key in SLOTS + DIAG_SLOTS:
            lines_full.append(f"- **`{slot_name}`**：Premise = `{c[p_key]}` ｜ Hypothesis = `{c[h_key]}`")
        lines_full.append("")

    c0 = clusters[smoke_ids[0]]
    lines_full.append(f"## 2. 13 个（任务 × 提示）组合逐字渲染全文（以开发集代表簇 `{smoke_ids[0]}` 之 `NI_OCC` 槽为例）")
    lines_full.append("")
    for task, prompt in COMBINATIONS:
        msgs = render_unit(c0["p_no_int"], c0["h_occ"], task, prompt)
        lines_full.append(f"### `{task}/{prompt}`")
        for m in msgs:
            lines_full.append(f"**Role: `{m['role']}`**")
            lines_full.append("```text")
            lines_full.append(m["content"])
            lines_full.append("```")
        lines_full.append("")

    full_path = HERE / "data" / "s1_preview_e3.md"
    full_bytes = ("\n".join(lines_full) + "\n").encode("utf-8")
    full_path.write_bytes(full_bytes)
    full_sha = hashlib.sha256(full_bytes).hexdigest()

    # 2. Redacted template preview (tracked in git, zero CC BY-NC text)
    lines_tpl = [
        "# 实验 3（英文活动边界消歧版）S1 提示模板与修饰语模具预览（无上游原题文本版）",
        "",
        "- 依据：`PLAN.md` 第 5、10 节（CC BY-NC 4.0 原题不进 git）与 `exp3-en/PLAN-E3.md` 第 2、3 节。",
        f"- 含开发集 20 簇完整句面的本地预览文件路径：`exp3-en/data/s1_preview_e3.md`（SHA-256：`{full_sha}`）。",
        "",
        "## 1. 三类闭集修饰语最小对模具（`SUBCLASS_MODIFIERS`）",
        "",
        "- `A_plan_task`（20 簇：开发集 5 簇、正式集 15 簇）：",
        "  - `h_occ = f\"{h_base} for at least a short time.\"`",
        "  - `h_plan = f\"{h_base} all the way to completion.\"`",
        "- `A_plan_deg`（4 簇：开发集 3 簇、正式集 1 簇）：",
        "  - `h_occ = f\"{h_base} at least partially.\"`",
        "  - `h_plan = f\"{h_base} completely.\"`",
        "- `A_pure`（76 簇：开发集 12 簇、正式集 64 簇）：",
        "  - `h_occ = f\"{h_base} for at least a short time.\"`",
        "  - `h_plan = f\"{h_base} throughout the entire period.\"`",
        "",
        "## 2. 13 个（任务 × 提示）组合逐字模板（占位符 `<PREMISE>` / `<HYPOTHESIS>`）",
        "",
    ]
    for task, prompt in COMBINATIONS:
        msgs = render_unit("<PREMISE>", "<HYPOTHESIS>", task, prompt)
        lines_tpl.append(f"### `{task}/{prompt}`")
        for m in msgs:
            lines_tpl.append(f"**Role: `{m['role']}`**")
            lines_tpl.append("```text")
            lines_tpl.append(m["content"])
            lines_tpl.append("```")
        lines_tpl.append("")

    tpl_path = HERE / "s1_preview_templates_e3.md"
    tpl_bytes = ("\n".join(lines_tpl) + "\n").encode("utf-8")
    tpl_path.write_bytes(tpl_bytes)
    tpl_sha = hashlib.sha256(tpl_bytes).hexdigest()
    return full_sha, tpl_sha


def main() -> int:
    compat = verify_parser_compatibility()
    full_sha, tpl_sha = generate_s1_previews()
    print("Parser compatibility (13/13):", compat)
    print(f"data/s1_preview_e3.md SHA-256       : {full_sha}")
    print(f"s1_preview_templates_e3.md SHA-256  : {tpl_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
