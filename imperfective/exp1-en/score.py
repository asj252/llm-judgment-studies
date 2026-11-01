"""First-letter token location and log-space, frozen-candidate q bounds."""
import math

LABELS = ("True", "False", "Unknown")
TOP_N = 100
VERSION = 1


def missing(reason, **extra):
    return {"q_status": "missing:" + reason, "q_L": None, "q_U": None, **extra}


def validate_top(top, n=TOP_N):
    if not isinstance(top, list) or len(top) != n:
        return False
    try:
        return (len({v["id"] for v in top}) == n and
                all(type(v["id"]) is int and type(v["rank"]) is int and v["rank"] == i + 1 and
                    isinstance(v["logprob"], (int, float)) and math.isfinite(v["logprob"]) and v["logprob"] <= 0
                    for i, v in enumerate(top)) and
                all(a["logprob"] >= b["logprob"] for a, b in zip(top, top[1:])))
    except (KeyError, TypeError):
        return False


def logsumexp(values):
    values = list(values)
    maximum = max(values, default=-math.inf)
    return maximum if maximum == -math.inf else maximum + math.log(sum(math.exp(v - maximum) for v in values))


def interval_from_logs(low, high):
    dl = logsumexp([low["True"], high["False"], high["Unknown"]])
    du = logsumexp([high["True"], low["False"], low["Unknown"]])
    if dl == -math.inf or du == -math.inf:
        return missing("zero_denominator")
    return {"q_L": math.exp(low["True"] - dl), "q_U": math.exp(high["True"] - du)}


def score_top(top, candidates):
    if not validate_top(top):
        return missing("bad_topN", topN=top)
    observed = {v["id"]: v["logprob"] for v in top}
    if not any(set(candidates[label]) & observed.keys() for label in LABELS):
        return missing("none_in_topN", topN=top)
    low, high, evidence = {}, {}, {}
    full = True
    for label in LABELS:
        ids = sorted(set(candidates[label]))
        evidence[label] = [{"id": tid, "logprob": observed.get(tid)} for tid in ids]
        logs = [observed[tid] for tid in ids if tid in observed]
        n_missing = sum(tid not in observed for tid in ids)
        full = full and n_missing == 0
        low[label] = logsumexp(logs)
        high[label] = logsumexp(logs + [top[-1]["logprob"]] * n_missing)
    bounds = interval_from_logs(low, high)
    return {"q_status": "full" if full else "bounded", **bounds, "candidates": evidence, "topN": top,
            "log_mass_lower": {k: v if math.isfinite(v) else None for k, v in low.items()},
            "log_mass_upper": {k: v if math.isfinite(v) else None for k, v in high.items()}}


def locate(text, parsed, prompt_ids, generated_ids, tok, candidates, prompt):
    if not parsed.get("label"):
        return missing("no_label")
    if prompt in ("CoT", "CF"):
        for field, reason in (("reasoning_ok", "no_reasoning"), ("label_last", "label_first")):
            if not parsed[field]:
                return missing(reason)
        if parsed["escape"]:
            return missing("escape")
    chunks = [tok.decode([tid], skip_special_tokens=False, clean_up_tokenization_spaces=False) for tid in generated_ids]
    if "".join(chunks) != text:
        return missing("decode_mismatch")
    pos, running, j = parsed["char_start"], 0, None
    for k, chunk in enumerate(chunks):
        if running <= pos < running + len(chunk):
            j = k
            break
        running += len(chunk)
    if j is None:
        return missing("decode_mismatch")
    lead = text[:pos]
    extra = {"j": j, "lead": lead, "prefix_ids": list(prompt_ids) + list(generated_ids[:j])}
    if prompt in ("Z", "DAP") and any(c.isalpha() for c in "".join(chunks[:j])):
        return missing("not_initial", **extra)
    if generated_ids[j] not in candidates[parsed["label"]]:
        return missing("offset_token", **extra)
    return {"q_status": "ready", **extra}
