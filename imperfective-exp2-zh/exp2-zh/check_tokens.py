"""Offline CPU tokenizer verification for Experiment 2 (Chinese). No weights, server, download or cache writes."""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, read_json, sha256, write_json, write_text
from prompts_zh import SLOTS, render_unit
from provenance import load_items, verify_sources

LABELS = ("True", "False", "Unknown")


def load_tokenizer(model_cfg=None):
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise RuntimeError("STOP: HF_HUB_OFFLINE=1 required")
    cfg = model_cfg if model_cfg is not None else read_json(ROOT / "config_models.json")["qwen3-8b"]
    path = Path(os.environ["HF_HOME"]) / "hub" / ("models--" + cfg["repo"].replace("/", "--")) / "snapshots" / cfg["commit"]
    if not all((path / name).is_file() for name in ("tokenizer.json", "tokenizer_config.json")):
        raise RuntimeError("STOP: tokenizer not cached; downloads prohibited")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    return tok, {name: sha256(path / name) for name in ("tokenizer.json", "tokenizer_config.json")}


def validate_frozen_structure(frozen, model="qwen3-8b", assets=None):
    """Validate structure, disjointness, and hashes of frozen label_tokens_<model>.json."""
    if frozen.get("model") != model or frozen.get("status") != "pass" or frozen.get("not_applicable", 0) != 0:
        raise ValueError("frozen token model/status/not_applicable mismatch")
    tok_hashes = frozen.get("tokenizer_sha256", {})
    if set(tok_hashes) != {"tokenizer.json", "tokenizer_config.json"}:
        raise ValueError("frozen tokenizer_sha256 keys mismatch")
    if assets is not None and tok_hashes != assets.get("tokenizer_sha256"):
        raise ValueError("frozen/asset tokenizer hashes mismatch")
    sets = frozen.get("sets", {})
    if (set(sets) != set(LABELS) or any(not isinstance(v, list) or not v or
            any(type(t) is not int for t in v) or len(v) != len(set(v)) for v in sets.values()) or
            any(set(sets[a]) & set(sets[b]) for a, b in (("True", "False"), ("True", "Unknown"), ("False", "Unknown")))):
        raise ValueError("invalid frozen candidates")
    return True


def validate_frozen(tok, hashes, frozen, model, assets):
    validate_frozen_structure(frozen, model, assets)
    if hashes != frozen.get("tokenizer_sha256") or hashes != assets.get("tokenizer_sha256"):
        raise ValueError("loaded/frozen/asset tokenizer hashes mismatch")
    template = tok.chat_template
    if not isinstance(template, str) or hashlib.sha256(template.encode("utf-8")).hexdigest() != assets.get("chat_template_sha256"):
        raise ValueError("loaded chat template hash mismatch")


def render_chat(tok, messages):
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)


def context_sets(tok, context):
    prefix = tok.encode(context, add_special_tokens=False)
    result, na = {}, 0
    for label in LABELS:
        ids = set()
        for case in (label, label.lower(), label.upper()):
            for lead in ("", " "):
                encoded = tok.encode(context + lead + case, add_special_tokens=False)
                if encoded[:len(prefix)] != prefix:
                    na += 1
                    continue
                for tid in encoded[len(prefix):]:
                    if any(c.isalpha() for c in tok.decode([tid], skip_special_tokens=False, clean_up_tokenization_spaces=False)):
                        ids.add(tid)
                        break
                else:
                    na += 1
        result[label] = sorted(ids)
    return result, na


def check_all(tok, file_hashes):
    items = {i["id"]: i for i in load_items()}
    dev_cids = read_json(ROOT / "split.json")["dev_cluster_ids"]
    dev_ids = [f"{cid}__{slot_name}" for cid in dev_cids for slot_name, _, _ in SLOTS]
    reference, checks, failures, na_total = None, [], [], 0
    for iid in dev_ids:
        item = items[iid]
        for prompt in ("Z", "DAP", "CoT", "CF"):
            chat = render_chat(tok, render_unit(item["premise"], item["hypothesis"], "L", prompt))
            suffixes = ("", '"') if prompt in ("Z", "DAP") else ((
                '{"reasoning": "该动作为终结性事件，正在盖并不保证盖好。", "label": "' if prompt == "CoT" else
                '{"possible_interruptions": ["中途停工", "材料不足", "临时离开"], "label": "'),)
            for suffix in suffixes:
                sets, na = context_sets(tok, chat + suffix)
                na_total += na
                if reference is None:
                    reference = sets
                bad = na > 0 or sets != reference or any(not ids for ids in sets.values()) or any(
                    set(sets[a]) & set(sets[b]) for a, b in (("True", "False"), ("True", "Unknown"), ("False", "Unknown")))
                row = {"id": iid, "prompt": prompt, "suffix": suffix, "sets": sets, "not_applicable": na, "pass": not bad}
                checks.append(row)
                if bad:
                    failures.append(row)
    record = {"status": "fail" if (failures or na_total > 0) else "pass", "model": "qwen3-8b", "context_count": len(checks),
              "not_applicable": na_total, "tokenizer_sha256": file_hashes, "sets": reference, "failures": failures, "checks": checks}
    return record


if __name__ == "__main__":
    verify_sources()
    tok, hashes = load_tokenizer()
    result = check_all(tok, hashes)
    write_json(ROOT / "raw" / "check_tokens.json", result)
    if result["status"] != "pass":
        raise SystemExit("STOP: frozen token sets differ, overlap, have not_applicable > 0, or are empty; see raw/check_tokens.json")
    write_json(ROOT / "label_tokens_qwen3-8b.json", {k: result[k] for k in ("model", "sets", "tokenizer_sha256", "not_applicable", "context_count", "status")})
    write_text(ROOT / "raw" / "check_tokens_summary.md", "# 首 token 离线核对（实验 2 中文版）\n\n状态：{status}。\n\n覆盖开发集全部 20 簇 × 4 主槽 = 80 条主实验题 × 6 个 L 任务上下文（`L/Z` 空后缀与 `\"` 后缀共 160 个、`L/DAP` 空后缀与 `\"` 后缀共 160 个、`L/CoT` JSON 标签前缀 80 个、`L/CF` JSON 标签前缀 80 个），合计核对 {count} 个上下文；True、False、Unknown 的首 token 数依次为 {sizes}。所有上下文集合相同，三集合两两不相交且非空。不适用变体总数：{na}。\n".format(status=result["status"], count=result["context_count"], sizes=[len(v) for v in result["sets"].values()], na=result["not_applicable"]))
    print(f"TOKEN CHECK PASS: {result['context_count']} contexts; sizes={[len(v) for v in result['sets'].values()]}; not_applicable={result['not_applicable']}")
