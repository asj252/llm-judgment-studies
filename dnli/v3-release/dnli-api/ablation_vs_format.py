#!/usr/bin/env python3
"""OpenAI 1+4 VS Format & Constraint Equivalence + Token Logprobs Entropy Ablation.

Variants tested on the 30-pair dnli dev split (150 contexts per variant):
  - D0 (direct):      Standard single-probability prompt (`Probability: NN%`)
  - D_CoT (direct_cot): Explicit step-by-step Chain-of-Thought + single-probability prompt (`Probability: NN%`)
  - V0 (multi_std):   Standard 5-estimate prompt (`Estimate k: NN% | Weight: W`, sum(W) = 1)
  - V1 (multi_freew): Unconstrained weights (`Estimate k: NN% | Weight: W`, no sum-to-1 requirement)
  - V2 (multi_now):   Unweighted 5-estimate prompt (`Estimate k: NN%`, no Weight field)
  - V3 (multi_json):  Strict JSON 5-estimate prompt (`{"estimates": [{"probability": NN, "weight": W}, ...]}`)

All calls request `logprobs=True, top_logprobs=20` from the OpenAI Chat Completions API
and extract exact character-aligned token Shannon entropy (in bits) at the probability
number token(s) (`NN`) as well as across the full response.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[1] / "code"
sys.path.insert(0, str(MAIN))
sys.path.insert(0, str(HERE))

import parse  # noqa: E402
import prompts  # noqa: E402

SPLIT_FILE = MAIN / "split.json"
ITEMS_TEXT = HERE.parents[1] / "data" / "items_text.json"

MODELS = {
    "openai:gpt-4o-mini": "gpt-4o-mini-2024-07-18",
    "openai:gpt-4.1-mini": "gpt-4.1-mini-2025-04-14",
}

ASK_DIRECT_COT = (
    "What is the probability that the statement is true?\n"
    "First, think step by step (in 2 to 4 sentences) about the situation, any new information, "
    "and alternative possibilities.\n\n"
    "On the last line of your answer, give the answer strictly in the following format:\n"
    "Probability: NN%\n"
    "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
)

ASK_MULTI_FREEW = (
    "Give 5 probability estimates that the statement is true, each with an independent relative weight "
    "from 0 to 1 for how plausible you think that estimate is (the weights do not need to sum to 1).\n\n"
    "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
    + "".join("Estimate %d: NN%% | Weight: W\n" % k for k in range(1, 6))
    + "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a "
    "number from 0 to 1 (decimals allowed)."
)

ASK_MULTI_NOW = (
    "Give 5 probability estimates that the statement is true.\n\n"
    "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
    + "".join("Estimate %d: NN%%\n" % k for k in range(1, 6))
    + "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign."
)

ASK_MULTI_JSON = (
    "Give 5 probability estimates that the statement is true, each with a weight for how likely you think "
    "that estimate is; the weights sum to 1.\n\n"
    "Respond ONLY with a single raw JSON object strictly in the following format (do not write any explanation, "
    "numbered list, or markdown before or after the JSON object):\n"
    '{"estimates": [{"probability": NN, "weight": W}, {"probability": NN, "weight": W}, '
    '{"probability": NN, "weight": W}, {"probability": NN, "weight": W}, {"probability": NN, "weight": W}]}\n'
    "where each probability NN is a number from 0 to 100 (decimals allowed), and each weight W is a "
    "number from 0 to 1 (decimals allowed); the five weights sum to 1."
)

VARIANT_ASKS = {
    "D0": prompts.ASK_DIRECT,
    "D_CoT": ASK_DIRECT_COT,
    "V0": prompts.ASK_MULTI,
    "V1": ASK_MULTI_FREEW,
    "V2": ASK_MULTI_NOW,
    "V3": ASK_MULTI_JSON,
}

VARIANTS = ("D0", "D_CoT", "V0", "V1", "V2", "V3")
CONTEXTS = (
    ("prior", "-"),
    ("stated", "S"),
    ("stated", "W"),
    ("reported", "S"),
    ("reported", "W"),
)


def render_variant(item: dict, pres: str, utype: str, variant: str) -> str:
    P = item["P"]
    H = item["H"]
    U = None if pres == "prior" else item["U_" + utype]
    lines = [prompts.FRAME_SITUATION.format(P=prompts.terminate(P))]
    if pres != "prior":
        lines.append(prompts.update_line(pres, U))
    return "\n\n".join(
        [
            "\n".join(lines),
            prompts.FRAME_QUESTION.format(H=prompts.terminate(H)),
            VARIANT_ASKS[variant],
            prompts.NO_TOOLS,
        ]
    )


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 == 1 else 0.5 * (s[mid - 1] + s[mid])


def _binary_entropy_bits(p_pct: float) -> float:
    p = max(0.0, min(1.0, p_pct / 100.0))
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def parse_v2_now(text: str) -> dict:
    """Parse V2 (5 lines of `Estimate k: NN%` without Weight) and return character spans of each NN."""
    final, err = parse.strip_thinking(text)
    if err:
        return {"ok": False, "error": err}
    all_lines = final.splitlines(keepends=True)
    # Track line offsets in `final`
    line_offsets = []
    pos = 0
    for line in all_lines:
        line_offsets.append(pos)
        pos += len(line)
    starts = [
        i
        for i, line in enumerate(all_lines)
        if any(int(f.group("k")) == 1 for f in parse._EST_LOOSE.finditer(line))
    ]
    start_idx = starts[-1] if starts else 0
    cand_indices = [
        i for i in range(start_idx, len(all_lines)) if parse._EST_LOOSE.search(all_lines[i])
    ]
    if len(cand_indices) != 5:
        return {"ok": False, "error": f"n_estimates_{len(cand_indices)}"}
    rows = []
    num_spans = []
    for i in cand_indices:
        line = all_lines[i].rstrip("\r\n")
        base_off = line_offsets[i]
        fields = list(parse._EST_FIELD.finditer(line))
        if len(fields) != 1:
            return {"ok": False, "error": "malformed_estimate_field"}
        f = fields[0]
        rest = line[f.end() :]
        rest_off = base_off + f.end()
        m = parse._VALUE.match(rest)
        if not m:
            return {"ok": False, "error": "estimate_no_value"}
        v = float(m.group("num"))
        if not (0.0 <= v <= 100.0):
            return {"ok": False, "error": "estimate_out_of_range"}
        k = int(f.group("k"))
        rows.append((k, v, (rest_off + m.start("num"), rest_off + m.end("num"))))
    idx = [k for k, _, _ in rows]
    if set(idx) != {1, 2, 3, 4, 5}:
        return {"ok": False, "error": "bad_index"}
    rows.sort(key=lambda r: r[0])
    ps = [v for _, v, _ in rows]
    num_spans = [sp for _, _, sp in rows]
    wn = [0.2] * 5
    val = sum(ps) / 5.0
    return {
        "ok": True,
        "value": val,
        "value_unweighted": val,
        "value_median": _median(ps),
        "value_top1": ps[0],
        "error": None,
        "estimates": ps,
        "weights": [1.0] * 5,
        "weight_sum": 5.0,
        "weight_sum_in_tolerance": True,
        "endpoint_mass": sum(0.2 for p in ps if parse.is_endpoint(p)),
        "weighted_sd": math.sqrt(max(0.0, sum(0.2 * (p - val) ** 2 for p in ps))),
        "num_spans": num_spans,
    }


def parse_v3_json(text: str) -> dict:
    """Parse V3 (`{"estimates": [{"probability": NN, "weight": W}, ...]}`) and locate NN spans."""
    final, err = parse.strip_thinking(text)
    if err:
        return {"ok": False, "error": err}
    # Find last JSON object containing "estimates"
    matches = list(re.finditer(r"\{[^{}]*\"estimates\"\s*:\s*\[.*?\]\s*\}", final, re.DOTALL))
    if not matches:
        return {"ok": False, "error": "no_json_object"}
    m_obj = matches[-1]
    raw_json = m_obj.group(0)
    base_off = m_obj.start()
    try:
        obj = json.loads(raw_json)
    except Exception as e:
        return {"ok": False, "error": f"json_decode_error:{e}"}
    ests = obj.get("estimates")
    if not isinstance(ests, list) or len(ests) != 5:
        return {"ok": False, "error": f"json_n_estimates_{len(ests) if isinstance(ests, list) else 'bad'}"}
    ps = []
    ws = []
    for item in ests:
        if not isinstance(item, dict) or "probability" not in item or "weight" not in item:
            return {"ok": False, "error": "json_missing_keys"}
        p_raw = item["probability"]
        w_raw = item["weight"]
        if isinstance(p_raw, str):
            p_raw = p_raw.rstrip("%").strip()
        p = float(p_raw)
        w = float(w_raw)
        if not (0.0 <= p <= 100.0):
            return {"ok": False, "error": "estimate_out_of_range"}
        if not (0.0 <= w <= 1.0):
            return {"ok": False, "error": "weight_out_of_range"}
        ps.append(p)
        ws.append(w)
    wsum = sum(ws)
    if wsum <= 0:
        return {"ok": False, "error": "weight_sum_not_positive"}
    wn = [w / wsum for w in ws]
    val = sum(w * p for w, p in zip(wn, ps))
    # Locate character spans of `"probability": <num>` inside raw_json
    num_spans = []
    for pm in re.finditer(r"\"probability\"\s*:\s*\"?(?P<num>[-+]?\d+(?:\.\d+)?)", raw_json):
        num_spans.append((base_off + pm.start("num"), base_off + pm.end("num")))
    top1_idx = max(range(5), key=lambda i: (ws[i], -i))
    return {
        "ok": True,
        "value": val,
        "value_unweighted": sum(ps) / 5.0,
        "value_median": _median(ps),
        "value_top1": ps[top1_idx],
        "error": None,
        "estimates": ps,
        "weights": ws,
        "weight_sum": wsum,
        "weight_sum_in_tolerance": parse.WSUM_LO <= wsum <= parse.WSUM_HI,
        "endpoint_mass": sum(w for w, p in zip(wn, ps) if parse.is_endpoint(p)),
        "weighted_sd": math.sqrt(max(0.0, sum(w * (p - val) ** 2 for w, p in zip(wn, ps)))),
        "num_spans": num_spans[:5],
    }


def locate_spans_standard(variant: str, text: str) -> list[tuple[int, int]]:
    """Locate character spans of NN in `text` for D0, D_CoT, V0, V1."""
    if variant in ("D0", "D_CoT"):
        fields = list(parse._FIELD.finditer(text))
        if not fields:
            return []
        f = fields[-1]
        rest = text[f.end() :].split("\n", 1)[0]
        m = parse._VALUE.match(rest)
        if not m:
            return []
        return [(f.end() + m.start("num"), f.end() + m.end("num"))]
    # V0 or V1: locate the 5 Estimate lines
    all_lines = text.splitlines(keepends=True)
    line_offsets = []
    pos = 0
    for line in all_lines:
        line_offsets.append(pos)
        pos += len(line)
    starts = [
        i
        for i, line in enumerate(all_lines)
        if any(int(f.group("k")) == 1 for f in parse._EST_LOOSE.finditer(line))
    ]
    start_idx = starts[-1] if starts else 0
    spans = []
    for i in range(start_idx, len(all_lines)):
        line = all_lines[i]
        if not parse._EST_LOOSE.search(line):
            continue
        fields = list(parse._EST_FIELD.finditer(line))
        if len(fields) != 1:
            continue
        f = fields[0]
        rest = line[f.end() :]
        m = parse._VALUE.match(rest)
        if m:
            spans.append((line_offsets[i] + f.end() + m.start("num"), line_offsets[i] + f.end() + m.end("num")))
    return spans[:5]


def parse_variant(variant: str, text: str) -> dict:
    if variant in ("D0", "D_CoT"):
        r = parse.parse_direct(text)
        if not r["ok"]:
            return r
        v = r["value"]
        return {
            "ok": True,
            "value": v,
            "value_unweighted": v,
            "value_median": v,
            "value_top1": v,
            "error": None,
            "estimates": [v],
            "weights": [1.0],
            "weight_sum": 1.0,
            "weight_sum_in_tolerance": True,
            "endpoint_mass": 1.0 if parse.is_endpoint(v) else 0.0,
            "weighted_sd": 0.0,
            "num_spans": locate_spans_standard(variant, text),
        }
    if variant in ("V0", "V1"):
        r = parse.parse_multi(text)
        if not r["ok"]:
            return r
        ps = r["estimates"]
        ws = r["weights"]
        top1_idx = max(range(5), key=lambda i: (ws[i], -i))
        r["value_unweighted"] = sum(ps) / 5.0
        r["value_median"] = _median(ps)
        r["value_top1"] = ps[top1_idx]
        r["num_spans"] = locate_spans_standard(variant, text)
        return r
    if variant == "V2":
        return parse_v2_now(text)
    if variant == "V3":
        return parse_v3_json(text)
    raise ValueError(variant)


def compute_token_entropy(logprobs_content: list[dict], num_spans: list[tuple[int, int]]) -> dict:
    """Compute top-20 normalized Shannon entropy (in bits) across all tokens and at numeric NN spans."""
    if not logprobs_content:
        return {
            "n_tokens": 0,
            "mean_all_token_entropy_bits": None,
            "num_token_entropies_bits": [],
            "first_num_token_entropy_bits": None,
            "mean_num_token_entropy_bits": None,
            "first_num_token_logprob": None,
            "first_num_top5_tokens": [],
        }
    token_spans = []
    pos = 0
    all_entropies = []
    for t_obj in logprobs_content:
        tok_str = t_obj.get("token") or ""
        start = pos
        end = pos + len(tok_str)
        pos = end
        top_list = t_obj.get("top_logprobs") or []
        if top_list:
            max_lp = max(x["logprob"] for x in top_list)
            exps = [math.exp(x["logprob"] - max_lp) for x in top_list]
            Z = sum(exps)
            probs = [e / Z for e in exps]
            h_bits = -sum(p * math.log2(p) for p in probs if p > 0)
        else:
            h_bits = 0.0
        all_entropies.append(h_bits)
        token_spans.append(
            {
                "start": start,
                "end": end,
                "token": tok_str,
                "logprob": t_obj.get("logprob"),
                "entropy_bits": h_bits,
                "top5": [
                    {"token": x["token"], "logprob": round(x["logprob"], 4)}
                    for x in top_list[:5]
                ],
            }
        )
    num_entropies = []
    first_lp = None
    first_top5 = []
    for sp_start, sp_end in num_spans:
        # Find the first token overlapping [sp_start, sp_end) containing a digit
        matched = None
        for ts in token_spans:
            if ts["end"] > sp_start and ts["start"] < sp_end and any(c.isdigit() for c in ts["token"]):
                matched = ts
                break
        if matched is not None:
            num_entropies.append(matched["entropy_bits"])
            if first_lp is None:
                first_lp = matched["logprob"]
                first_top5 = matched["top5"]
    return {
        "n_tokens": len(token_spans),
        "mean_all_token_entropy_bits": sum(all_entropies) / len(all_entropies) if all_entropies else None,
        "num_token_entropies_bits": num_entropies,
        "first_num_token_entropy_bits": num_entropies[0] if num_entropies else None,
        "mean_num_token_entropy_bits": sum(num_entropies) / len(num_entropies) if num_entropies else None,
        "first_num_token_logprob": first_lp,
        "first_num_top5_tokens": first_top5,
    }


def _load_default_env() -> None:
    env_file = Path(os.environ.get("DNLI_KEYS_ENV_FILE", ""))
    if os.environ.get("DNLI_KEYS_ENV_FILE") and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def call_openai_with_logprobs(model_id: str, prompt: str, seed: int) -> dict:
    _load_default_env()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "top_p": 1.0,
        "max_tokens": 512,
        "seed": seed,
        "logprobs": True,
        "top_logprobs": 20,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    t0 = time.monotonic()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            elapsed = time.monotonic() - t0
            choice = (body.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            lp_content = (choice.get("logprobs") or {}).get("content") or []
            usage = body.get("usage") or {}
            return {
                "ok": True,
                "text": msg.get("content") or "",
                "finish_reason": choice.get("finish_reason"),
                "system_fingerprint": body.get("system_fingerprint"),
                "model_returned": body.get("model"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "elapsed_s": round(elapsed, 3),
                "logprobs_content": lp_content,
            }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"ok": False, "error": f"http_{e.code}:{err_body[:200]}", "elapsed_s": round(time.monotonic() - t0, 3)}
        except Exception as e:
            if attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"ok": False, "error": f"exc:{e}", "elapsed_s": round(time.monotonic() - t0, 3)}


def _roc_auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = 0.0
    for x in pos:
        for y in neg:
            if x > y:
                wins += 1.0
            elif x == y:
                wins += 0.5
    return round(wins / (len(pos) * len(neg)), 4)


def summarize_ablation(records: list[dict]) -> dict:
    """Compute per-variant H1, H2, H4a, H4b (M_W, M_U, Median, Top1), ROC-AUC, endpoint mass, and token entropy."""
    by_var = {v: {} for v in VARIANTS}
    for r in records:
        if not r.get("parse_ok"):
            continue
        v = r["variant"]
        if v not in by_var:
            continue
        k = r["key"]
        ctx = (r["pres"], r["utype"])
        by_var[v].setdefault(k, {})[ctx] = r

    out = {}
    # First collect D0 complete keys for H4b comparison
    d0_map = by_var["D0"]
    for v in VARIANTS:
        v_map = by_var[v]
        n_parsed = sum(len(ctx_map) for ctx_map in v_map.values())
        complete_keys = [
            k for k, ctx_map in v_map.items() if all(c in ctx_map for c in CONTEXTS)
        ]
        h1_vals, h2_vals, h4a_vals = [], [], []
        pos_st, neg_st, pos_rep, neg_rep = [], [], [], []
        for k in complete_keys:
            cm = v_map[k]
            p0 = cm[("prior", "-")]["value"]
            ps_s = cm[("stated", "S")]["value"]
            ps_w = cm[("stated", "W")]["value"]
            pr_s = cm[("reported", "S")]["value"]
            pr_w = cm[("reported", "W")]["value"]
            d_ss = ps_s - p0
            d_sw = ps_w - p0
            d_rs = pr_s - p0
            d_rw = pr_w - p0
            h1_vals.append(0.5 * ((d_ss - d_sw) + (d_rs - d_rw)))
            h2_vals.append(0.5 * ((d_ss - d_rs) + (d_sw - d_rw)))
            h4a_vals.append((d_ss - d_sw) - (d_rs - d_rw))
            pos_st.append(d_ss)
            neg_st.append(d_sw)
            pos_rep.append(d_rs)
            neg_rep.append(d_rw)

        auc_st = _roc_auc(pos_st, neg_st)
        auc_rep = _roc_auc(pos_rep, neg_rep)
        auc_all = _roc_auc(pos_st + pos_rep, neg_st + neg_rep)
        delta_auc = round(auc_st - auc_rep, 4) if (auc_st is not None and auc_rep is not None) else None

        # Compare against D0 on keys complete in BOTH D0 and v
        both_keys = [
            k for k in complete_keys if k in d0_map and all(c in d0_map[k] for c in CONTEXTS)
        ]
        m_w_diffs, m_u_diffs, med_diffs, top1_diffs, dh2_diffs = [], [], [], [], []
        for k in both_keys:
            for c in CONTEXTS:
                rv = v_map[k][c]
                rd = d0_map[k][c]
                m_w_diffs.append(rv["value"] - rd["value"])
                m_u_diffs.append(rv["value_unweighted"] - rd["value"])
                med_diffs.append(rv["value_median"] - rd["value"])
                top1_diffs.append(rv["value_top1"] - rd["value"])
                dh2_diffs.append(_binary_entropy_bits(rv["value"]) - _binary_entropy_bits(rd["value"]))

        all_recs = [r for ctx_map in v_map.values() for r in ctx_map.values()]
        w_tol = [r["weight_sum_in_tolerance"] for r in all_recs if r.get("weight_sum_in_tolerance") is not None]
        ep_mass = [r["endpoint_mass"] for r in all_recs if r.get("endpoint_mass") is not None]
        wsd = [r["weighted_sd"] for r in all_recs if r.get("weighted_sd") is not None]
        comp_toks = [
            r["completion_tokens"] for r in all_recs if r.get("completion_tokens") is not None
        ]
        first_num_ent = [
            r["token_entropy"]["first_num_token_entropy_bits"]
            for r in all_recs
            if r.get("token_entropy", {}).get("first_num_token_entropy_bits") is not None
        ]
        mean_num_ent = [
            r["token_entropy"]["mean_num_token_entropy_bits"]
            for r in all_recs
            if r.get("token_entropy", {}).get("mean_num_token_entropy_bits") is not None
        ]
        all_tok_ent = [
            r["token_entropy"]["mean_all_token_entropy_bits"]
            for r in all_recs
            if r.get("token_entropy", {}).get("mean_all_token_entropy_bits") is not None
        ]
        noncopy_first_ent = [x for x in first_num_ent if x >= 0.01]
        noncopy_mean_ent = [
            r["token_entropy"]["mean_num_token_entropy_bits"]
            for r in all_recs
            if (r.get("token_entropy", {}).get("first_num_token_entropy_bits") or 0.0) >= 0.01
            and r.get("token_entropy", {}).get("mean_num_token_entropy_bits") is not None
        ]
        est1_re = re.compile(r"estimate\s*1\s*:", re.I)
        multi_block_rate = [
            1.0 if len(est1_re.findall(r.get("raw_text") or "")) > 1 else 0.0
            for r in all_recs
        ]

        def _avg(xs):
            return round(sum(xs) / len(xs), 4) if xs else None

        out[v] = {
            "n_parsed_units": n_parsed,
            "n_complete_pairs": len(complete_keys),
            "H1_strength": _avg(h1_vals),
            "H2_hedging": _avg(h2_vals),
            "H4a_interaction": _avg(h4a_vals),
            "roc_auc_stated": auc_st,
            "roc_auc_reported": auc_rep,
            "roc_auc_overall": auc_all,
            "delta_auc_st_minus_rep": delta_auc,
            "H4b_M_W_vs_D0": _avg(m_w_diffs),
            "H4b_M_U_vs_D0": _avg(m_u_diffs),
            "H4b_Median_vs_D0": _avg(med_diffs),
            "H4b_Top1_vs_D0": _avg(top1_diffs),
            "delta_binary_entropy_bits_vs_D0": _avg(dh2_diffs),
            "mean_endpoint_mass": _avg(ep_mass),
            "mean_within_call_sd": _avg(wsd),
            "weight_sum_in_tolerance_rate": _avg([1.0 if x else 0.0 for x in w_tol]),
            "multi_block_draft_then_copy_rate": _avg(multi_block_rate),
            "mean_completion_tokens": _avg(comp_toks),
            "first_num_token_entropy_bits": _avg(first_num_ent),
            "mean_num_token_entropy_bits": _avg(mean_num_ent),
            "first_num_token_entropy_noncopy_bits": _avg(noncopy_first_ent),
            "mean_num_token_entropy_noncopy_bits": _avg(noncopy_mean_ent),
            "n_noncopy_units": len(noncopy_first_ent),
            "mean_all_token_entropy_bits": _avg(all_tok_ent),
        }
    return out


def main():
    import concurrent.futures
    import threading

    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=sorted(MODELS.keys()))
    ap.add_argument("--limit-pairs", type=int, default=30, help="Number of dev pairs to run (default: all 30)")
    ap.add_argument("--workers", type=int, default=6, help="Number of concurrent workers (default: 6)")
    ap.add_argument("--smoke", action="store_true", help="Write to smoke output file instead of main ablation file")
    args = ap.parse_args()

    split = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    items_all = json.loads(ITEMS_TEXT.read_text(encoding="utf-8"))
    dev_keys = sorted([it["key"] for it in split["items"] if it["use"] == "dev"])[: args.limit_pairs]
    model_id = MODELS[args.model]
    slug = args.model.replace(":", "_").replace(".", "_")
    tag = "smoke" if args.smoke else "dev"
    out_jsonl = HERE / f"ablation_vs_format_{tag}_{slug}.jsonl"
    out_summary = HERE / f"summary_ablation_vs_format_{tag}_{slug}.json"

    done = {}
    if out_jsonl.exists() and not args.smoke:
        for line in out_jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("parse_ok"):
                done[(r["key"], r["pres"], r["utype"], r["variant"])] = r

    records = list(done.values())
    mode = "w" if args.smoke else "a"
    total_units = len(dev_keys) * len(CONTEXTS) * len(VARIANTS)

    todo_tasks = []
    unit_idx = 0
    for key in dev_keys:
        item = items_all[key]
        for pres, utype in CONTEXTS:
            for variant in VARIANTS:
                unit_idx += 1
                uid = (key, pres, utype, variant)
                if uid in done:
                    continue
                todo_tasks.append((unit_idx, key, item, pres, utype, variant))

    print(
        f"[{args.model} -> {model_id}] total={total_units} done={len(done)} "
        f"todo={len(todo_tasks)} workers={args.workers}",
        flush=True,
    )

    lock = threading.Lock()
    completed_now = 0

    def _run_one(t):
        u_idx, key, item, pres, utype, variant = t
        prompt = render_variant(item, pres, utype, variant)
        seed = 20261105 + u_idx
        resp = call_openai_with_logprobs(model_id, prompt, seed)
        if not resp["ok"]:
            return {
                "key": key,
                "pres": pres,
                "utype": utype,
                "variant": variant,
                "model": args.model,
                "model_id": model_id,
                "api_ok": False,
                "parse_ok": False,
                "error": resp.get("error"),
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        text = resp["text"]
        parsed = parse_variant(variant, text)
        if not parsed.get("ok"):
            resp2 = call_openai_with_logprobs(model_id, prompt, seed + 100000)
            if resp2["ok"]:
                parsed2 = parse_variant(variant, resp2["text"])
                if parsed2.get("ok"):
                    resp = resp2
                    text = resp2["text"]
                    parsed = parsed2
        tok_ent = compute_token_entropy(
            resp.get("logprobs_content") or [],
            parsed.get("num_spans") or [],
        )
        return {
            "key": key,
            "pres": pres,
            "utype": utype,
            "variant": variant,
            "model": args.model,
            "model_id": model_id,
            "api_ok": True,
            "parse_ok": bool(parsed.get("ok")),
            "parse_error": parsed.get("error"),
            "value": parsed.get("value"),
            "value_unweighted": parsed.get("value_unweighted"),
            "value_median": parsed.get("value_median"),
            "value_top1": parsed.get("value_top1"),
            "estimates": parsed.get("estimates"),
            "weights": parsed.get("weights"),
            "weight_sum": parsed.get("weight_sum"),
            "weight_sum_in_tolerance": parsed.get("weight_sum_in_tolerance"),
            "endpoint_mass": parsed.get("endpoint_mass"),
            "weighted_sd": parsed.get("weighted_sd"),
            "token_entropy": tok_ent,
            "prompt_tokens": resp.get("prompt_tokens"),
            "completion_tokens": resp.get("completion_tokens"),
            "elapsed_s": resp.get("elapsed_s"),
            "raw_text": text,
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    with out_jsonl.open(mode, encoding="utf-8") as f_out:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(_run_one, t) for t in todo_tasks]
            for fut in concurrent.futures.as_completed(futures):
                rec = fut.result()
                with lock:
                    completed_now += 1
                    f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f_out.flush()
                    records.append(rec)
                    if completed_now % 50 == 0 or completed_now == len(todo_tasks) or args.smoke:
                        print(
                            f"  [{len(done) + completed_now}/{total_units}] {rec['key']} "
                            f"{rec['pres']}/{rec['utype']} {rec['variant']}: "
                            f"parse_ok={rec['parse_ok']} val={rec.get('value')} "
                            f"H_num={rec.get('token_entropy', {}).get('first_num_token_entropy_bits')}",
                            flush=True,
                        )

    summary = {
        "model": args.model,
        "model_id": model_id,
        "tag": tag,
        "n_pairs_requested": len(dev_keys),
        "total_records": len(records),
        "variants": summarize_ablation(records),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved summary to {out_summary}", flush=True)
    print(json.dumps(summary["variants"], indent=2), flush=True)


if __name__ == "__main__":
    main()
