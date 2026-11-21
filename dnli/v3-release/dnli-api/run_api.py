"""Runner for un-harnessed REST API / Colab δ-NLI experiments (dnli-api).

Usage:
  # 1. Quick 5-unit smoke check (does not write formal/dev checkpoints):
  python3 -B run_api.py smoke aistudio:gemma-4-31b-it --limit 5

  # 2. Run 30-pair development set (300 units):
  python3 -B run_api.py dev aistudio:gemma-4-31b-it

  # 3. Run 120-pair Block-A formal set (1,400 units; requires completed dev set):
  python3 -B run_api.py formal aistudio:gemma-4-31b-it
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import unicodedata
import uuid

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[1] / "code"
sys.path.insert(0, str(MAIN))
sys.path.insert(0, str(HERE))

import parse  # noqa: E402
import prompts  # noqa: E402
from configs import CONFIGS, SAMPLING, file_config  # noqa: E402
from api_subject import ApiSubject  # noqa: E402

SPLIT_FILE = MAIN / "split.json"
ITEMS_TEXT = HERE.parents[1] / "data" / "items_text.json"
ASKS = ("direct", "multi")
PRES_POST = ("stated", "reported")
TYPES = ("S", "W")
BASE_SEED = {"dev": 20261080, "formal": 20261081}
_V1_CONFIGS = [
    "aistudio:gemini-3.5-flash-lite",
    "aistudio:gemini-3.8-flash",
    "aistudio:gemma-4-26b-a4b-it",
    "aistudio:gemma-4-31b-it",
    "cf:gemma-4-26b-a4b-it",
    "cf:gpt-oss-120b",
    "cf:gpt-oss-20b",
    "cf:llama-3.1-8b",
    "cf:llama-3.3-70b",
    "cf:qwen3.8-27b",
    "colab:qwen3.5-9b",
    "colab:qwen3.8-27b",
    "openrouter:gemma-4-31b-free",
    "openrouter:qwen3.6-plus-free",
    "openrouter:qwen3.8-27b-free",
    "or:dots-3-note",
    "or:nemotron-3.5-lightning",
    "or:nemotron-3.5-super-vl",
    "or:north-mini-code",
    "sf:glm-4-9b",
    "sf:qwen2.5-7b",
    "sf:qwen3-8b",
    "sf:qwen3.5-4b",
    "sf:xing4.0-29b",
    "groq:gpt-oss-120b",
    "groq:gpt-oss-20b",
    "mistral:ministral-14b",
    "mistral:ministral-3b",
    "mistral:ministral-8b",
    "mistral:mistral-large-4",
    "ms:deepseek-v4.1-flash",
    "ms:glm-5.2",
    "ms:qwen3.5-27b",
    "sf:glm-z1-9b",
]
CONFIG_OFFSET = {c: 100 + i for i, c in enumerate(_V1_CONFIGS)}
for _c in sorted(CONFIGS):
    if _c not in CONFIG_OFFSET:
        CONFIG_OFFSET[_c] = 100 + len(CONFIG_OFFSET)
PARSE_RULES = {
    "version": parse.PARSE_VERSION,
    "wsum": [parse.WSUM_LO, parse.WSUM_HI],
    "n_estimates": parse.N_ESTIMATES,
    "endpoint": [parse.ENDPOINT_LO, parse.ENDPOINT_HI],
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def normalize_text(text) -> str:
    """Same Unicode space-separator normalization as dnli-agy."""
    if isinstance(text, list):
        text = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in text
            if not (isinstance(b, dict) and b.get("type") in ("thinking", "reasoning"))
        )
    return "".join(" " if unicodedata.category(ch) == "Zs" else ch for ch in str(text or ""))


def judge_text(ask: str, text: str) -> dict:
    norm = normalize_text(text)
    r = parse.PARSERS[ask](norm)
    out = {k: r.get(k) for k in ("value", "error", "forms")}
    if ask == "multi":
        out.update(
            {
                k: r.get(k)
                for k in (
                    "estimates",
                    "weights",
                    "weight_sum",
                    "weight_sum_in_tolerance",
                    "endpoint_mass",
                    "weighted_sd",
                )
            }
        )
    return out


def base_units(key: str, rnd: str = "r0") -> list[tuple[str, str, str, str, str]]:
    out = [(key, "prior", "-", a, rnd) for a in ASKS]
    out += [(key, p, t, a, rnd) for p in PRES_POST for t in TYPES for a in ASKS]
    return out


def units_for(item: dict, which: str, split: dict) -> list[tuple[str, str, str, str, str]]:
    k = item["key"]
    out = base_units(k, "r0")
    if which == "formal" and k in split["repeat_subset"]:
        out += base_units(k, "r1")
    return out


def planned_items(items: dict, which: str, blocks: str = "A") -> dict:
    return {
        k: it
        for k, it in items.items()
        if it["use"] == which and (which != "formal" or it.get("formal_block") in blocks)
    }


def make_schedule(items: dict, which: str, cfg: str, split: dict, blocks: str = "A") -> list[tuple]:
    rng = random.Random(BASE_SEED[which] * 10 + CONFIG_OFFSET[cfg])
    keys = sorted(planned_items(items, which, blocks))
    rng.shuffle(keys)
    sched = []
    for k in keys:
        us = units_for(items[k], which, split)
        rng.shuffle(us)
        sched.extend(us)
    return sched


def unit_id(u: tuple) -> str:
    return "|".join(u)


def call_seed(cfg: str, u: tuple, attempt: int, which: str) -> int:
    s = f"{which}|{cfg}|{unit_id(u)}|a{attempt}|{BASE_SEED[which]}"
    return int(_sha(s.encode("utf-8"))[:8], 16)


def render_unit(item: dict, u: tuple) -> str:
    _, pres, utype, ask, _ = u
    return prompts.render_item(item, pres, utype, ask)


def update_id(item: dict, u: tuple):
    return None if u[1] == "prior" else item[u[2] + "_id"]


def materials_digest(all_items: dict, split: dict) -> tuple[str, int]:
    rows = []
    for k in sorted(all_items):
        it = all_items[k]
        for u in units_for(it, it["use"], split):
            rows.append([unit_id(u), update_id(it, u), _sha(render_unit(it, u).encode("utf-8"))])
    return _sha(json.dumps(rows, ensure_ascii=False).encode("utf-8")), len(rows)


def fingerprint(cfg: str, all_items: dict, split: dict, blocks: str = "A") -> tuple[dict, str]:
    mat_dig, n_units = materials_digest(all_items, split)
    core_invariants = {
        "split.json": _sha(SPLIT_FILE.read_bytes()),
        "items_text.json": _sha(ITEMS_TEXT.read_bytes()),
        "prompts.py": _sha((MAIN / "prompts.py").read_bytes()),
        "parse.py": _sha((MAIN / "parse.py").read_bytes()),
        "templates": _sha(json.dumps(prompts.templates(), sort_keys=True, ensure_ascii=False).encode("utf-8")),
        "parse_rules": _sha(json.dumps(PARSE_RULES, sort_keys=True).encode("utf-8")),
        "sampling": SAMPLING,
        "config": cfg,
        "spec": CONFIGS[cfg],
        "blocks": blocks,
        "materials_digest": mat_dig,
        "n_units_all": n_units,
    }
    freeze_path = HERE / "freezes" / f"freeze_{file_config(cfg)}.json"
    if freeze_path.is_file():
        frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
        frozen_fp = frozen.get("formal", {}).get("fingerprint") or {}
        frozen_id = frozen.get("formal", {}).get("fingerprint_id")
        if frozen_id and all(frozen_fp.get(k) == v for k, v in core_invariants.items()):
            return frozen_fp, frozen_id

    fp = dict(core_invariants)
    fp["configs.py"] = _sha((HERE / "configs.py").read_bytes())
    fp["api_subject.py"] = _sha((HERE / "api_subject.py").read_bytes())
    fp["run_api.py"] = _sha((HERE / "run_api.py").read_bytes())
    return fp, _sha(json.dumps(fp, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def save_json(path: Path, obj: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def record_hash(record: dict) -> str:
    return _sha(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def load_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def valid_records(records: list[dict], sessions: list[dict], fp_id: str) -> dict[str, dict]:
    by_id = {
        s["session_id"]: s
        for s in sessions
        if s.get("closed_ok") and not s.get("invalid") and s.get("fingerprint_id") == fp_id
    }
    keep = {}
    for r in records:
        s = by_id.get(r.get("session_id"))
        if s and r.get("fingerprint_id") == fp_id:
            if s.get("unit") == r.get("unit") and s.get("record_sha256") == record_hash(r):
                keep[r["unit"]] = r
    return keep


def run_unit(cfg: str, which: str, item: dict, u: tuple, subject: ApiSubject, backoff_s: int = 30) -> dict:
    uid = unit_id(u)
    prompt = render_unit(item, u)
    attempts = []
    parse_retries = 0
    disconnect_streak = 0
    rate_retries = 0
    attempt_idx = 0

    while True:
        seed = call_seed(cfg, u, attempt_idx, which)
        att = subject.attempt(which, uid, attempt_idx, prompt, seed)
        state = att["final"]["state"]

        if state == "rate_limited":
            rate_retries += 1
            if rate_retries > 15:
                raise RuntimeError(
                    f"Rate limit / quota persisted after 15 retries on {uid}: {att['final'].get('reason')}"
                )
            wait_s = min(600, backoff_s * (2 ** min(rate_retries - 1, 4)))
            print(f"[{cfg}] Rate limited on {uid}; sleeping {wait_s}s (retry #{rate_retries})...", flush=True)
            subject.sleep(wait_s)
            continue

        if state in ("disconnect", "content_blocked"):
            disconnect_streak += 1
            attempts.append(att)
            attempt_idx += 1
            if disconnect_streak >= 3:
                return {
                    "status": "missing",
                    "missing_reason": state,
                    "result": {"value": None, "error": state},
                    "attempts": attempts,
                    "n_retries": parse_retries,
                }
            subject.sleep(5 * disconnect_streak)
            continue

        disconnect_streak = 0
        if state != "ok":
            attempts.append(att)
            raise RuntimeError(f"Unrecoverable API error on {uid}: {att['final'].get('reason')}")

        judged = judge_text(u[3], att["text"])
        att["judged"] = judged
        attempts.append(att)
        attempt_idx += 1

        if not att["truncated"] and judged["error"] is None:
            return {
                "status": "ok",
                "missing_reason": None,
                "result": judged,
                "attempts": attempts,
                "n_retries": parse_retries,
            }

        if parse_retries < 1:
            parse_retries += 1
            continue

        reason = "truncated" if att["truncated"] else f"parse_error:{judged['error']}"
        return {
            "status": "missing",
            "missing_reason": reason,
            "result": judged,
            "attempts": attempts,
            "n_retries": parse_retries,
        }


def load_all_items() -> tuple[dict, dict]:
    split = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    text = json.loads(ITEMS_TEXT.read_text(encoding="utf-8"))
    keys = {it["key"] for it in split["items"]}
    if set(text) != keys:
        raise RuntimeError(f"items_text.json keys mismatch items_split.json: {len(text)} vs {len(keys)}")
    items = {}
    for it in split["items"]:
        t = text[it["key"]]
        if t["S_id"] != it["S"]["id"] or t["W_id"] != it["W"]["id"]:
            raise RuntimeError(f"S/W id mismatch for {it['key']}")
        items[it["key"]] = dict(
            t,
            key=it["key"],
            use=it["use"],
            cluster=it["cluster"],
            source_split=it.get("source_split"),
            formal_block=it.get("formal_block") if it["use"] == "formal" else None,
        )
    return items, split


def run_split(which: str, cfg: str, blocks: str = "A", limit: int | None = None, skip_dev_gate: bool = False):
    all_items, split = load_all_items()
    if which == "smoke":
        sched = make_schedule(all_items, "dev", cfg, split, blocks)[: (limit or 5)]
        subject = ApiSubject(cfg)
        print(f"Running {len(sched)} smoke units for {cfg}...", flush=True)
        for idx, u in enumerate(sched, 1):
            it = all_items[u[0]]
            res = run_unit(cfg, "dev", it, u, subject)
            print(
                f"  [{idx}/{len(sched)}] {unit_id(u)} -> status={res['status']} "
                f"val={res['result'].get('value')} err={res['result'].get('error')}",
                flush=True,
            )
        return

    fp_obj, fp_id = fingerprint(cfg, all_items, split, blocks)
    suffix = file_config(cfg)

    if which == "formal" and not skip_dev_gate:
        dev_meta_path = HERE / f"run_meta_dev_{suffix}.json"
        dev_res_path = HERE / f"results_dev_{suffix}.jsonl"
        if not dev_meta_path.is_file() or not dev_res_path.is_file():
            raise RuntimeError(f"Dev set must be completed before formal run for {cfg} (or pass --skip-dev-gate).")
        dev_meta = json.loads(dev_meta_path.read_text(encoding="utf-8"))
        dev_done = valid_records(load_records(dev_res_path), dev_meta.get("sessions", []), fp_id)
        dev_sched = make_schedule(all_items, "dev", cfg, split, blocks)
        if len(dev_done) < len(dev_sched):
            raise RuntimeError(f"Dev set incomplete ({len(dev_done)}/{len(dev_sched)} units).")

    meta_path = HERE / f"run_meta_{which}_{suffix}.json"
    res_path = HERE / f"results_{which}_{suffix}.jsonl"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("fingerprint_id") != fp_id:
            raise RuntimeError(f"Fingerprint mismatch in {meta_path}; expected {fp_id}")
    else:
        meta = {
            "config": cfg,
            "which": which,
            "fingerprint_id": fp_id,
            "fingerprint": fp_obj,
            "sessions": [],
        }
        save_json(meta_path, meta)

    done = valid_records(load_records(res_path), meta["sessions"], fp_id)
    sched = make_schedule(all_items, which, cfg, split, blocks)
    todo = [u for u in sched if unit_id(u) not in done]
    if limit is not None:
        todo = todo[:limit]

    print(
        f"[{cfg} | {which}] total={len(sched)} done={len(done)} remaining={len(sched) - len(done)} "
        f"running_now={len(todo)}",
        flush=True,
    )
    if not todo:
        return

    subject = ApiSubject(cfg)
    for idx, u in enumerate(todo, 1):
        uid = unit_id(u)
        it = all_items[u[0]]
        sid = uuid.uuid4().hex
        session_entry = {
            "session_id": sid,
            "unit": uid,
            "fingerprint_id": fp_id,
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "closed_ok": False,
            "invalid": False,
        }
        meta["sessions"].append(session_entry)
        save_json(meta_path, meta)

        unit_out = run_unit(cfg, which, it, u, subject)
        rec = {
            "session_id": sid,
            "fingerprint_id": fp_id,
            "config": cfg,
            "which": which,
            "use": it["use"],
            "unit": uid,
            "key": u[0],
            "pres": u[1],
            "utype": u[2],
            "ask": u[3],
            "round": u[4],
            "cluster": it["cluster"],
            "source_split": it.get("source_split"),
            "update_id": update_id(it, u),
            "status": unit_out["status"],
            "missing_reason": unit_out["missing_reason"],
            "result": unit_out["result"],
            "n_retries": unit_out["n_retries"],
            "attempts": unit_out["attempts"],
        }
        with res_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        session_entry["closed_ok"] = True
        session_entry["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        session_entry["record_sha256"] = record_hash(rec)
        save_json(meta_path, meta)

        if idx % 10 == 0 or idx == len(todo):
            print(
                f"  [{cfg} | {which}] {len(done) + idx}/{len(sched)} "
                f"(last={uid} status={rec['status']} val={rec['result'].get('value')})",
                flush=True,
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("which", choices=("smoke", "dev", "formal"))
    ap.add_argument("config", choices=sorted(CONFIGS))
    ap.add_argument("--blocks", default="A", choices=("A", "AB"))
    ap.add_argument("--limit", type=int, default=None, help="Stop after N units")
    ap.add_argument("--skip-dev-gate", action="store_true", help="Allow formal run without dev set")
    args = ap.parse_args()
    run_split(args.which, args.config, blocks=args.blocks, limit=args.limit, skip_dev_gate=args.skip_dev_gate)


if __name__ == "__main__":
    main()
