"""Additive dev runner; original stimuli, parsers and statistical engines stay frozen."""
import sys
import os
sys.dont_write_bytecode = True
import argparse
from copy import deepcopy
import hashlib
import http.client
import json
import math
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.request
from configs_p167 import CONFIGS, TEMPERATURE, TOP_P, ZH_SUPPLEMENT_MODELS
from api_adapter_p167 import (build_request_payload, load_keys_env, KEY_NAMES,
                              parse_api_response)
from stimuli_p167 import HERE, ROOT, COUNTS, build_slice, upstream_modules, verify_upstream
from run_p167_slice import parse_record, synthetic_response

ADDENDUM_CONFIGS = deepcopy(CONFIGS)
ADDENDUM_CONFIGS["aistudio:gemma-4-31b-it"].update(rpm=24, min_interval_sec=60.0 / 24)
for model in ("gpt-4o-mini", "gpt-4.1-mini"):
    ADDENDUM_CONFIGS["openai:" + model] = dict(patrol_provider="openai", provider_type="openai",
        model_id=model, scale_label="Mini", family="OpenAI GPT-" + ("4o" if model == "gpt-4o-mini" else "4.1"),
        enable_thinking=False, supports_logprobs=True, top_logprobs=20,
        max_tokens=1024, rpm=90, min_interval_sec=60.0 / 90)
OPENAI_KEY_NAMES = ["OPENAI_API_KEY"] + [f"OPENAI_API_KEY_{i}" for i in range(2, 11)]
RATE_HEADERS = ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
                "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "retry-after")
PROBE_4_UNIT_KEYS = tuple("E3/011__NI_OCC/" + x for x in ("L/Z", "L/CoT", "P/Z", "M/Z"))
PROBE_12_UNIT_KEYS = PROBE_4_UNIT_KEYS + tuple("E2/A_plan_01__NI_COMP/" + x for x in
    ("L/CoT", "P/Z", "M/Z")) + tuple("E4/002__DUAL_MOORE/" + x for x in
    ("L/CoT", "P/Z", "P/CoT", "M/Z", "M/CF"))
PERSISTENT = Path(os.environ.get("P167_RESULTS_DIR", "<LOCAL_PATH>/imperfective_p167_results"))


def ensure_upstream_files():
    return verify_upstream()

def build_addendum_payload(cfg, messages, max_tokens_override=None):
    cfg = dict(cfg, max_tokens=max_tokens_override or cfg["max_tokens"])
    if cfg["provider_type"] == "openai":
        assert TEMPERATURE == 0.0 and TOP_P == 1.0
        return dict(model=cfg["model_id"], messages=messages, temperature=TEMPERATURE,
                    top_p=TOP_P, max_tokens=cfg["max_tokens"], logprobs=True, top_logprobs=20)
    return build_request_payload(cfg, messages)


class DailyQuotaExhaustedError(RuntimeError):
    pass


class HardenedAPIAdapter:
    def __init__(self, cfg):
        self.cfg, self.env, self.cursor = cfg, load_keys_env(), 0
        names = OPENAI_KEY_NAMES if cfg["provider_type"] == "openai" else KEY_NAMES[cfg["provider_type"]]
        self.keys = list(dict.fromkeys(self.env[n] for n in names if self.env.get(n)))
        if not self.keys:
            raise ValueError("No provider credentials configured")

    def redact(self, text):
        for key in self.keys:
            text = text.replace(key, "[REDACTED]")
        return text

    def request(self, messages, max_tokens_override=None):
        cfg, provider = self.cfg, self.cfg["provider_type"]
        key = self.keys[self.cursor % len(self.keys)]
        self.cursor += 1
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        if provider == "aistudio":
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{cfg["model_id"]}:generateContent'
            headers["x-goog-api-key"] = key
        else:
            headers["Authorization"] = "Bearer " + key
            endpoints = {"openai": "https://api.openai.com/v1/chat/completions",
                "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
                "groq": "https://api.groq.com/openai/v1/chat/completions",
                "modelscope": "https://api-inference.modelscope.cn/v1/chat/completions"}
            if provider == "cloudflare":
                account = self.env.get("CF_ACCOUNT_ID") or self.env.get("CLOUDFLARE_ACCOUNT_ID")
                if not account:
                    raise ValueError("Missing Cloudflare account ID")
                url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{cfg["model_id"]}'
            else:
                url = endpoints[provider]
        return urllib.request.Request(url, data=json.dumps(build_addendum_payload(cfg, messages,
            max_tokens_override), ensure_ascii=False, allow_nan=False).encode("utf-8"), headers=headers, method="POST")

    def complete(self, messages, max_tokens_override=None):
        for attempt in range(1, 7):
            retry_after = None
            try:
                with urllib.request.urlopen(self.request(messages, max_tokens_override), timeout=120) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    headers = {k.lower(): str(v) for k, v in response.headers.items()}
                    selected = {k: self.redact(headers[k]) for k in RATE_HEADERS if k in headers}
                generated = parse_api_response(self.cfg["provider_type"], data)
                generated.update(rate_headers=selected, http_status=200, transport_attempts=attempt)
                return generated
            except urllib.error.HTTPError as exc:
                body = self.redact(exc.read().decode("utf-8", errors="replace")).lower()
                markers = ("tokens per day", "tpd", "requests per day", "rpd", "generaterequestsperday",
                           "insufficient_quota", "insufficient balance", "exceeded your current quota", "neurons")
                if exc.code in (429, 402) and any(m in body for m in markers):
                    raise DailyQuotaExhaustedError(f'{self.cfg["provider_type"]} quota exhausted: {body[:160]}') from None
                if exc.code not in (408, 409, 429, 500, 502, 503, 504) or attempt == 6:
                    # Never propagate response bodies or authenticated URLs to logs.
                    raise RuntimeError(f'HTTP {exc.code} ({self.cfg["provider_type"]})') from None
                try:
                    retry_after = float(exc.headers.get("Retry-After"))
                except (TypeError, ValueError, AttributeError):
                    pass
            except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, ConnectionResetError):
                if attempt == 6:
                    raise RuntimeError("Transient transport attempts exhausted") from None
            time.sleep(min(90.0, max(0.0, retry_after if retry_after is not None else 2.0 ** attempt)))

    generate = complete


def answer_spans(clean_text, task):
    """Mirror v2 terminal-block selection, retaining source character offsets."""
    parser = upstream_modules()["parse"]
    if task == "P":
        fields = list(parser._FIELD.finditer(clean_text))
        if not fields:
            return [], 0
        f = fields[-1]
        m = parser._VALUE.match(clean_text[f.end():].split("\n", 1)[0])
        return ([(1, f.end() + m.start("num"), f.end() + m.end("num"))] if m else []), f.start()
    lines = clean_text.splitlines(keepends=True)
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    starts = [i for i, line in enumerate(lines) if (m := parser._EST_LOOSE.search(line)) and int(m["k"]) == 1]
    start = starts[-1] if starts else 0
    spans, indices = [], []
    for i in range(start, len(lines)):
        if not parser._EST_LOOSE.search(lines[i]):
            continue
        f = parser._EST_FIELD.search(lines[i])
        if not f:
            continue
        rest = lines[i][f.end():]
        wf = list(parser._W_FIELD.finditer(rest))
        if not wf:
            continue
        m = parser._VALUE.match(rest[:wf[0].start()].rstrip(" \t|,;(["))
        if m:
            spans.append((int(f["k"]), offsets[i] + f.end() + m.start("num"), offsets[i] + f.end() + m.end("num")))
            indices.append(i)
    return sorted(spans), offsets[indices[0]] if indices else 0


def draft_metrics(clean_text, task):
    _, offset = answer_spans(clean_text, task)
    n = len(re.findall(r"\d+(?:\.\d+)?\s*%", clean_text[:offset]))
    return dict(pre_block_pct_mentions=n, draft_copy_candidate=n >= 1)


def extract_addendum_logprobs(logprobs, raw_text, clean_text, task, prompt, parsed):
    content = (logprobs or {}).get("content") or []
    if not content or not clean_text:
        return None
    concat = "".join(t.get("token") or "" for t in content)
    base = concat.find(clean_text)
    if base < 0 and raw_text and len(concat) == len(raw_text):
        base = raw_text.find(clean_text)
    if base < 0:
        return None
    spans, offset = [], 0
    for token in content:
        text, top = token.get("token") or "", token.get("top_logprobs") or []
        h = None
        if top:
            lps = [float(x["logprob"]) for x in top]
            peak = max(lps)
            if math.isfinite(peak):
                exps = [math.exp(lp - peak) for lp in lps]
                z = sum(exps)
                h = -sum((v / z) * math.log2(v / z) for v in exps if v > 0)
        spans.append(dict(start=offset, end=offset + len(text), token=text, entropy_bits=h,
                          n_top_logprobs=len(top), top=top, logprob=token.get("logprob")))
        offset += len(text)
    all_h = [t["entropy_bits"] for t in spans if t["entropy_bits"] is not None]
    mean_h = sum(all_h) / len(all_h) if all_h else None
    if task == "L":
        if not parsed or not parsed.get("label") or parsed.get("char_start") is None:
            return None
        target = base + parsed["char_start"]
        ts = next((t for t in spans if t["start"] <= target < t["end"]), None)
        if ts is None or ts["entropy_bits"] is None:
            return None
        masses = dict.fromkeys(("True", "False", "Unknown"), 0.0)
        for alt in ts["top"]:
            label = alt["token"].strip().strip('"')
            if label in masses:
                masses[label] += math.exp(alt["logprob"])
        captured = min(1.0, sum(masses.values()))
        if not captured:
            return None
        lower = min(1.0, masses["True"])
        return dict(q_true_lower=lower, q_true_upper=min(1.0, lower + 1 - captured),
            label_mass_captured=captured, label_token_entropy_bits=ts["entropy_bits"],
            n_top_logprobs=ts["n_top_logprobs"], min_target_top_logprobs=ts["n_top_logprobs"],
            max_target_top_logprobs=ts["n_top_logprobs"], n_tokens=len(spans), mean_all_token_entropy_bits=mean_h)
    if task not in ("P", "M") or not parsed or not parsed.get("ok"):
        return None
    targets, _ = answer_spans(clean_text, task)
    if [k for k, _, _ in targets] != list(range(1, 2 if task == "P" else 6)):
        return None
    tokens = [next((t for t in spans if t["end"] > base + a and t["start"] < base + b
                    and any(c.isdigit() for c in t["token"])), None) for _, a, b in targets]
    if any(t is None or t["entropy_bits"] is None or not math.isfinite(t["entropy_bits"]) for t in tokens):
        return None
    hs, counts = [t["entropy_bits"] for t in tokens], [t["n_top_logprobs"] for t in tokens]
    return dict(n_tokens=len(spans), n_top_logprobs=max(t["n_top_logprobs"] for t in spans),
        target_n_top_logprobs=counts, min_target_top_logprobs=min(counts), max_target_top_logprobs=max(counts),
        mean_all_token_entropy_bits=mean_h, num_token_entropies_bits=hs,
        first_num_token_entropy_bits=hs[0], mean_num_token_entropy_bits=sum(hs)/len(hs),
        first_num_token_logprob=tokens[0]["logprob"], **draft_metrics(clean_text, task))


def parse_addendum_record(unit, config, generated):
    row = parse_record(unit, config, generated)
    row["logprob_metrics"] = None
    row["token_entropy_metrics"] = None
    if row["status"] == "ok":
        metrics = extract_addendum_logprobs((generated or {}).get("logprobs"), row["raw_text"],
            row["clean_text"], unit["task"], unit["prompt"], row["parsed"])
        row["logprob_metrics" if unit["task"] == "L" else "token_entropy_metrics"] = metrics
        if unit["task"] in ("P", "M"):
            row.update(draft_metrics(row["clean_text"], unit["task"]))
    row.update(q_available=unit["task"] == "L" and row["logprob_metrics"] is not None,
               rate_headers=(generated or {}).get("rate_headers", {}),
               http_status=(generated or {}).get("http_status"))
    row["status_strict_q"] = "ok" if unit["task"] != "L" or row["q_available"] else "missing_score"
    return row


def atomic_rows(path, rows, serialized=None):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            key = row["unit_key"]
            if serialized is None:
                text = json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
            else:
                if key not in serialized or serialized[key][0] is not row:
                    serialized[key] = (row, json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                text = serialized[key][1]
            handle.write(text)
        handle.flush()
        import os
        os.fsync(handle.fileno())
    tmp.replace(path)


def raw_envelope_hash(raw):
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def companion_raw_path(path):
    path = Path(path)
    return path.parent.parent / ("dry-run-raw" if path.parent.name == "dry-run" else "raw") / path.name.replace("results_", "raw_", 1)


def verify_raw_recompute(results_path: Path, raw_path: Path, cfg: dict) -> dict:
    """Reparse only the sanitized raw evidence, without trusting derived results."""
    def read(path):
        return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]
    rows, raws = read(results_path), read(raw_path)
    keys = [r["unit_key"] for r in rows]
    if len(set(keys)) != len(keys) or keys != [r["unit_key"] for r in raws]:
        raise ValueError("Raw/results unit_key correspondence mismatch")
    planned = {u["unit_key"]: u for u in build_slice("all")}
    recomputed = []
    fields = {"unit_key", "config", "dry_run", "attempt_count", "http_status", "rate_headers",
              "finish_reason", "truncated", "raw_text", "logprobs"}
    for row, raw in zip(rows, raws):
        if set(raw) != fields or raw_envelope_hash(raw) != row.get("raw_envelope_sha256"):
            raise ValueError("Raw envelope SHA-256/schema mismatch")
        if ADDENDUM_CONFIGS[raw["config"]] != cfg or any(raw[k] != row[k] for k in
                ("config", "dry_run", "attempt_count", "http_status", "rate_headers", "raw_text", "truncated")):
            raise ValueError("Raw/results metadata mismatch")
        generated = dict(text=raw["raw_text"], logprobs=raw["logprobs"],
                         http_status=raw["http_status"], rate_headers=raw["rate_headers"],
                         finish_reason=raw["finish_reason"], truncated=raw["truncated"])
        if raw["raw_text"] is None and raw["http_status"] is None and raw["logprobs"] is None:
            generated = None
        new = parse_addendum_record(planned[row["unit_key"]], raw["config"], generated)
        for key in ("status", "parsed", "logprob_metrics", "token_entropy_metrics"):
            if new[key] != row[key]:
                raise ValueError("Raw recompute mismatch: " + key)
        new["first_pass_ok"] = row["first_pass_ok"]
        recomputed.append(new)
    summary = probe_summary(recomputed, cfg)
    if summary != probe_summary(rows, cfg):
        raise ValueError("Raw recompute probe_summary mismatch")
    return dict(raw_recompute_verified=True, probe_summary=summary)


def run_addendum_slice(config, slice_name, dry_run=False, limit=None, out_dir=PERSISTENT,
                       resume=False, probe_mode=False, unit_keys=None):
    cfg = ADDENDUM_CONFIGS[config]
    if config in ZH_SUPPLEMENT_MODELS and slice_name != "slice_e2":
        raise ValueError("Tier-2 supplements collect slice_e2 only")
    if limit is not None and limit < 0:
        raise ValueError("limit must be nonnegative")
    out_dir = Path(out_dir).resolve()
    allowed = out_dir.is_relative_to(HERE) or out_dir.is_relative_to(PERSISTENT)
    if dry_run or probe_mode:
        allowed |= out_dir.is_relative_to(Path(tempfile.gettempdir()).resolve())
    if not allowed:
        raise ValueError("Output directory outside authorized roots")
    ensure_upstream_files()
    if not dry_run and not probe_mode:
        from freeze_p167_addendum import verify_addendum_freeze
        verify_addendum_freeze()
    units = build_slice(slice_name)
    if unit_keys is not None:
        if not probe_mode:
            raise ValueError("unit_keys requires probe mode")
        planned = {u["unit_key"]: u for u in units}
        if tuple(unit_keys) not in (PROBE_12_UNIT_KEYS, PROBE_4_UNIT_KEYS):
            raise ValueError("Unregistered probe keys")
        units = [planned[k] for k in unit_keys]
    if limit is not None:
        units = units[:limit]
    slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", config)
    path = out_dir / ("dry-run" if dry_run else "results") / f"results_p167_addendum_{slice_name}_{slug}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = companion_raw_path(path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    rows, raw_rows = {}, {}
    if resume and raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            if raw["unit_key"] in raw_rows:
                raise ValueError("Resume duplicate raw identity")
            raw_rows[raw["unit_key"]] = raw
    if path.exists():
        if not resume:
            raise FileExistsError("Refusing to overwrite existing collection")
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["config"] != config or r["dry_run"] != dry_run:
                raise ValueError("Resume config/dry_run mismatch")
            if r["unit_key"] in rows or r["unit_key"] not in {u["unit_key"] for u in units}:
                raise ValueError("Resume duplicate/unplanned identity")
            u = next(u for u in units if u["unit_key"] == r["unit_key"])
            if any(r[k] != u[k] for k in ("exp", "cluster_id", "slot", "task", "prompt", "engine_unit_key")):
                raise ValueError("Resume identity mismatch")
            rows[r["unit_key"]] = r
    adapter, last_req_start = None, None
    serialized, raw_serialized = {}, {}
    def flush():
        atomic_rows(raw_path, [raw_rows[u["unit_key"]] for u in units if u["unit_key"] in rows and u["unit_key"] in raw_rows], raw_serialized)
        atomic_rows(path, [rows[u["unit_key"]] for u in units if u["unit_key"] in rows], serialized)
    def call(unit, override=None):
        nonlocal last_req_start, adapter
        if adapter is None:
            adapter = HardenedAPIAdapter(cfg)
        if last_req_start is not None:
            time.sleep(max(0.0, cfg["min_interval_sec"] - (time.monotonic() - last_req_start)))
        last_req_start = time.monotonic()
        return adapter.complete(unit["messages"], max_tokens_override=override)
    for unit in units:
        old, raw = rows.get(unit["unit_key"], {}), raw_rows.get(unit["unit_key"])
        if (old.get("status") == "ok" and raw is not None
                and old.get("raw_envelope_sha256") == raw_envelope_hash(raw)
                and raw.get("config") == config and raw.get("dry_run") == dry_run):
            continue
        attempts, first_ok, generated, error_type = 1, False, None, None
        try:
            generated = synthetic_response(unit) if dry_run else call(unit)
            first_ok = parse_addendum_record(unit, config, generated)["status"] == "ok"
            if not dry_run and generated.get("truncated"):
                attempts = 2
                generated = call(unit, min(4096, cfg["max_tokens"] * 2))
        except DailyQuotaExhaustedError:
            flush()
            raise
        except Exception as exc:
            generated, error_type = None, type(exc).__name__
        row = parse_addendum_record(unit, config, generated)
        row.update(dry_run=dry_run, first_pass_ok=first_ok, attempt_count=attempts,
                   transport_error_type=error_type)
        g = generated or {}
        raw = dict(unit_key=unit["unit_key"], config=config, dry_run=dry_run,
            attempt_count=attempts, http_status=g.get("http_status"), rate_headers=g.get("rate_headers", {}),
            finish_reason=g.get("finish_reason"), truncated=bool(g.get("truncated")),
            raw_text=g.get("text"), logprobs=g.get("logprobs"))
        if adapter is not None and getattr(adapter, "keys", None):
            raw = json.loads(adapter.redact(json.dumps(raw, ensure_ascii=False, allow_nan=False)))
        row["raw_envelope_sha256"] = raw_envelope_hash(raw)
        raw_rows[unit["unit_key"]] = raw
        rows[unit["unit_key"]] = row
        flush()
    flush()
    return path


def probe_summary(rows, cfg):
    n = len(rows)
    good = [r for r in rows if r["status"] == "ok"]
    first = sum(bool(r.get("first_pass_ok")) for r in rows)
    counts, aligned, exact = [], 0, True
    for r in rows:
        m = r.get("logprob_metrics") if r["task"] == "L" else r.get("token_entropy_metrics")
        if r["task"] in ("P", "M"):
            hs = (m or {}).get("num_token_entropies_bits", [])
            valid = len(hs) == (1 if r["task"] == "P" else 5) and all(math.isfinite(h) for h in hs)
            exact &= valid
        else:
            valid = m is not None and math.isfinite(m.get("label_token_entropy_bits", float("nan")))
        if r["status"] == "ok" and valid and m:
            aligned += 1
            counts.extend([m["n_top_logprobs"]] if r["task"] == "L" else m["target_n_top_logprobs"])
    expected = cfg["top_logprobs"] if cfg["supports_logprobs"] else 0
    out = dict(n_units=n, n_first_pass_ok=first, first_pass_parse_rate=first/n if n else 0,
        n_final_ok=len(good), final_parse_rate=len(good)/n if n else 0,
        n_protocol_ok=sum(bool(r["protocol_ok"]) for r in rows), logprobs_expected=bool(expected),
        expected_top_logprobs=expected, n_logprobs_aligned=aligned, n_target_positions_checked=len(counts),
        min_target_top_logprobs=min(counts) if counts else None, max_target_top_logprobs=max(counts) if counts else None,
        all_pm_exact_cardinality=bool(exact), rate_headers_sample=[r["rate_headers"] for r in rows if r.get("rate_headers")][:2],
        http_status_counts={str(code): sum(r.get("http_status") == code for r in rows)
                            for code in sorted({r.get("http_status") for r in rows}, key=str)})
    out["gate_pass"] = (n == 12 and first >= 11 and len(good) == 12 and aligned == 12 and exact
        and len(counts) == 28 and min(counts, default=0) == max(counts, default=0) == 20) if cfg["provider_type"] == "openai" else (
        len(good) == n and (not expected or aligned == n))
    return out


def probe_12():
    ensure_upstream_files()
    all_dev = {r["unit_key"]: r for r in build_slice("all")}
    assert set(PROBE_12_UNIT_KEYS).issubset(all_dev)
    assert len(PROBE_12_UNIT_KEYS) == 12
    assert len({(all_dev[k]["exp"], all_dev[k]["task"], all_dev[k]["prompt"]) for k in PROBE_12_UNIT_KEYS}) == 12
    assert PROBE_4_UNIT_KEYS == PROBE_12_UNIT_KEYS[:4]
    summary = {}
    target = HERE / "summary_probe12_addendum.json"
    for config in ("openai:gpt-4o-mini", "nv:nemotron-3.5-lightning-30b", "groq:gpt-oss-120b", "aistudio:gemma-4-31b-it"):
        keys = PROBE_12_UNIT_KEYS if config.startswith("openai:") else PROBE_4_UNIT_KEYS
        path = run_addendum_slice(config, "all", out_dir=Path("/tmp/p167_probe12"), probe_mode=True, unit_keys=keys)
        rows = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
        cfg = ADDENDUM_CONFIGS[config]
        raw_path = companion_raw_path(path)
        verified = verify_raw_recompute(path, raw_path, cfg)
        summary[config] = verified["probe_summary"]
        summary[config].update(results_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            raw_recompute_verified=verified["raw_recompute_verified"])
        if config.startswith("openai:"):
            summary[config]["gate_pass"] &= summary[config]["raw_recompute_verified"] is True
        target.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(config + ": " + json.dumps(summary[config], ensure_ascii=False), flush=True)
        if config.startswith("openai:") and not summary[config]["gate_pass"]:
            return 1
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe-12", action="store_true")
    p.add_argument("--config", choices=ADDENDUM_CONFIGS)
    p.add_argument("--slice", choices=COUNTS)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--out-dir", type=Path, default=PERSISTENT)
    args = p.parse_args()
    try:
        if args.probe_12:
            return probe_12()
        if not args.config or not args.slice:
            p.error("--config and --slice required")
        print(run_addendum_slice(args.config, args.slice, args.dry_run, args.limit, args.out_dir, args.resume))
    except DailyQuotaExhaustedError as exc:
        print("FATAL: tokens per day (TPD) / daily quota exhausted: " + str(exc), file=sys.stderr)
        return 75
    return 0


if __name__ == "__main__":
    sys.exit(main())
