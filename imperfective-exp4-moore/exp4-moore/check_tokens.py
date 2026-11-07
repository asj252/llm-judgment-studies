"""Offline CPU tokenizer verification for Experiment 4 (English Moore's Paradox). No weights, server, download or cache writes."""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_ROOT, ROOT, read_json, sha256, write_json, write_text
from prompts_e4 import SLOTS, render_unit
from provenance import load_items, verify_sources

LABELS = ("True", "False", "Unknown")


class _ReadOnlyFastTokenizer:
    """Zero-tempdir fallback wrapper around `tokenizers.Tokenizer.from_file` + `jinja2` for read-only sandboxes."""

    def __init__(self, snapshot_dir: Path):
        from tokenizers import Tokenizer
        self._tok = Tokenizer.from_file(str(snapshot_dir / "tokenizer.json"))
        cfg = read_json(snapshot_dir / "tokenizer_config.json")
        self.chat_template = cfg.get("chat_template", "")
        eos_tok = cfg.get("eos_token")
        if isinstance(eos_tok, dict):
            eos_tok = eos_tok.get("content")
        self.eos_token_id = self._tok.token_to_id(eos_tok) if isinstance(eos_tok, str) else 151645
        self.unk_token_id = None
        self._bos_token = cfg.get("bos_token") or ""
        self._eos_token = eos_tok or "<|im_end|>"

    def convert_tokens_to_ids(self, tokens):
        if isinstance(tokens, str):
            return self._tok.token_to_id(tokens)
        return [self._tok.token_to_id(t) for t in tokens]

    def convert_ids_to_tokens(self, ids):
        if isinstance(ids, int):
            return self._tok.id_to_token(ids)
        return [self._tok.id_to_token(int(i)) for i in ids]

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(self._tok.encode(text, add_special_tokens=add_special_tokens).ids)

    def decode(
        self,
        ids: list[int],
        skip_special_tokens: bool = False,
        clean_up_tokenization_spaces: bool = False,
    ) -> str:
        return self._tok.decode(list(ids), skip_special_tokens=skip_special_tokens)

    def apply_chat_template(
        self,
        messages: list[dict],
        tokenize: bool = False,
        add_generation_prompt: bool = True,
        enable_thinking: bool = False,
    ):
        from jinja2.sandbox import ImmutableSandboxedEnvironment
        env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
        rendered = env.from_string(self.chat_template).render(
            messages=messages,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=enable_thinking,
            bos_token=self._bos_token,
            eos_token=self._eos_token,
        )
        return self.encode(rendered, add_special_tokens=False) if tokenize else rendered


def load_tokenizer(model_cfg=None):
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise RuntimeError("STOP: HF_HUB_OFFLINE=1 required")
    cfg = model_cfg if model_cfg is not None else read_json(ROOT / "config_models.json")["qwen3-8b"]
    path = Path(os.environ["HF_HOME"]) / "hub" / ("models--" + cfg["repo"].replace("/", "--")) / "snapshots" / cfg["commit"]
    if not all((path / name).is_file() for name in ("tokenizer.json", "tokenizer_config.json")):
        raise RuntimeError("STOP: tokenizer not cached; downloads prohibited")
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    except OSError as exc:
        if "No usable temporary directory" in str(exc) or getattr(exc, "errno", None) in (1, 13, 30):
            tok = _ReadOnlyFastTokenizer(path)
        else:
            raise
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
    split_obj = read_json(ROOT / "split.json")
    dev_cids = split_obj["dev"]["cluster_ids"]
    dev_ids = [f"{slot_name}_{cid}" for cid in dev_cids for slot_name, _, _ in SLOTS]
    reference, checks, failures, na_total = None, [], [], 0
    for iid in dev_ids:
        item = items[iid]
        for prompt in ("Z", "DAP", "CoT", "CF"):
            chat = render_chat(tok, render_unit(item["premise"], item["hypothesis"], "L", prompt))
            suffixes = ("", '"') if prompt in ("Z", "DAP") else ((
                '{"reasoning": "The speaker evaluates the situation across two distinct standards.", "label": "' if prompt == "CoT" else
                '{"possible_interruptions": ["literal single-standard conflict", "dual evaluation standards", "non-assertive script reading"], "label": "'),)
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
    write_json(RAW_ROOT / "check_tokens.json", result)
    if result["status"] != "pass":
        raise SystemExit("STOP: frozen token sets differ, overlap, have not_applicable > 0, or are empty; see data/raw/check_tokens.json")
    write_json(ROOT / "label_tokens_qwen3-8b.json", {k: result[k] for k in ("model", "sets", "tokenizer_sha256", "not_applicable", "context_count", "status")})
    write_text(RAW_ROOT / "check_tokens_summary.md", "# 首 token 离线核对（实验 4 英文摩尔悖论版）\n\n状态：{status}。\n\n覆盖开发集全部 20 簇 × 4 主槽 = 80 条主实验题 × 6 个 L 任务上下文（`L/Z` 空后缀与 `\"` 后缀共 160 个、`L/DAP` 空后缀与 `\"` 后缀共 160 个、`L/CoT` JSON 标签前缀 80 个、`L/CF` JSON 标签前缀 80 个），合计核对 {count} 个上下文；True、False、Unknown 的首 token 数依次为 {sizes}。所有上下文集合相同，三集合两两不相交且非空。不适用变体总数：{na}。\n".format(status=result["status"], count=result["context_count"], sizes=[len(v) for v in result["sets"].values()], na=result["not_applicable"]))
    print(f"TOKEN CHECK PASS: {result['context_count']} contexts; sizes={[len(v) for v in result['sets'].values()]}; not_applicable={result['not_applicable']}")
