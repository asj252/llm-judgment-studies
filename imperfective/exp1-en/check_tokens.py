"""Offline CPU tokenizer verification. No weights, server, download or cache writes."""
import os
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, read_json, sha256, write_json, write_text
from prompts import render_unit
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


def validate_frozen(tok, hashes, frozen, model, assets):
    if frozen.get("model") != model or frozen.get("status") != "pass":
        raise ValueError("frozen token model/status mismatch")
    if (set(hashes) != {"tokenizer.json", "tokenizer_config.json"} or
            hashes != frozen.get("tokenizer_sha256") or hashes != assets.get("tokenizer_sha256")):
        raise ValueError("loaded/frozen/asset tokenizer hashes mismatch")
    template = tok.chat_template
    if not isinstance(template, str) or hashlib.sha256(template.encode("utf-8")).hexdigest() != assets.get("chat_template_sha256"):
        raise ValueError("loaded chat template hash mismatch")
    sets = frozen.get("sets", {})
    if (set(sets) != set(LABELS) or any(not isinstance(v, list) or not v or
            any(type(t) is not int for t in v) or len(v) != len(set(v)) for v in sets.values()) or
            any(set(sets[a]) & set(sets[b]) for a, b in (("True", "False"), ("True", "Unknown"), ("False", "Unknown")))):
        raise ValueError("invalid frozen candidates")


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
    dev = read_json(ROOT / "split.json")["dev"]["ids"]
    reference, checks, failures, na_total = None, [], [], 0
    for iid in dev:
        for prompt in ("Z", "DAP", "CoT", "CF"):
            chat = render_chat(tok, render_unit(items[iid], "L", prompt))
            suffixes = ("", '"') if prompt in ("Z", "DAP") else ((
                '{"reasoning": "x", "label": "' if prompt == "CoT" else
                '{"possible_interruptions": ["x", "x", "x"], "label": "'),)
            for suffix in suffixes:
                sets, na = context_sets(tok, chat + suffix)
                na_total += na
                if reference is None:
                    reference = sets
                bad = sets != reference or any(not ids for ids in sets.values()) or any(
                    set(sets[a]) & set(sets[b]) for a, b in (("True", "False"), ("True", "Unknown"), ("False", "Unknown")))
                row = {"id": iid, "prompt": prompt, "suffix": suffix, "sets": sets, "not_applicable": na, "pass": not bad}
                checks.append(row)
                if bad:
                    failures.append(row)
    record = {"status": "fail" if failures else "pass", "model": "qwen3-8b", "context_count": len(checks),
              "not_applicable": na_total, "tokenizer_sha256": file_hashes, "sets": reference, "failures": failures, "checks": checks}
    return record


if __name__ == "__main__":
    verify_sources()
    tok, hashes = load_tokenizer()
    result = check_all(tok, hashes)
    write_json(ROOT / "raw" / "check_tokens.json", result)
    if result["status"] != "pass":
        raise SystemExit("STOP: frozen token sets differ, overlap, or are empty; see raw/check_tokens.json")
    write_json(ROOT / "label_tokens_qwen3-8b.json", {k: result[k] for k in ("model", "sets", "tokenizer_sha256", "not_applicable", "context_count", "status")})
    write_text(ROOT / "raw" / "check_tokens_summary.md", "# \u9996 token \u79bb\u7ebf\u6838\u5bf9\n\n\u72b6\u6001\uff1a{status}\u3002\n\n\u8986\u76d6\u5f00\u53d1\u96c6\u5168\u90e8 80 \u6761\uff0c\u6838\u5bf9 {count} \u4e2a\u4e0a\u4e0b\u6587\uff1bTrue\u3001False\u3001Unknown \u7684\u9996 token \u6570\u4f9d\u6b21\u4e3a {sizes}\u3002\u6240\u6709\u4e0a\u4e0b\u6587\u96c6\u5408\u76f8\u540c\uff0c\u4e09\u96c6\u5408\u4e24\u4e24\u4e0d\u76f8\u4ea4\u4e14\u975e\u7a7a\u3002\u4e0d\u9002\u7528\u53d8\u4f53\u603b\u6570\uff1a{na}\u3002\n\n\u5206\u8bcd\u5668\u6587\u4ef6 sha256\u3001\u5404\u4e0a\u4e0b\u6587\u7684\u5019\u9009\u96c6\u5408\u53ca\u5931\u8d25\u5217\u8868\u89c1 `check_tokens.json`\uff1b\u51bb\u7ed3\u96c6\u5408\u89c1 `../label_tokens_qwen3-8b.json`\u3002\u672c\u6b21\u53ea\u4f7f\u7528\u79bb\u7ebf\u7f13\u5b58\u7684\u5206\u8bcd\u5668\uff08CPU\uff09\uff0c\u672a\u52a0\u8f7d\u6a21\u578b\u6743\u91cd\u3002\n".format(status=result['status'], count=result['context_count'], sizes=[len(v) for v in result['sets'].values()], na=result['not_applicable']))
    print(f"TOKEN CHECK PASS: {result['context_count']} contexts; sizes={[len(v) for v in result['sets'].values()]}; not_applicable={result['not_applicable']}")
