"""Deterministic offline fixtures and freeze-gated online slice collection."""
import sys
sys.dont_write_bytecode = True
import argparse
import json
import math
from pathlib import Path
import re
import time
from api_adapter_p167 import APIAdapter, normalize_answer_text, extract_logprob_metrics
from configs_p167 import CONFIGS, ZH_SUPPLEMENT_MODELS
from stimuli_p167 import HERE, COUNTS, build_slice, upstream_modules


def parse_record(unit, config, generated):
    raw = generated.get("text") if generated is not None else None
    clean, think_error = normalize_answer_text(raw)
    truncated = bool(generated and generated.get("truncated"))
    task, prompt = unit["task"], unit["prompt"]
    row = {k: v for k, v in unit.items() if k != "messages"}
    row.update(config=config, raw_text=raw, clean_text=clean, text=clean, truncated=truncated,
               label=None, value=None, m_w=None, m_u=None, top1=None, weighted_sd=None,
               unweighted_sd=None, endpoint_mass=None, logprob_metrics=None)
    parsed = None
    if generated is None:
        status, error = "missing_transport", "transport_error"
        info = {"protocol_ok": False, "reasons": [error]}
    elif truncated or think_error:
        status, error = "missing_format", think_error or "truncated"
        parsed = dict(ok=False, label=None, value=None, error=error)
        info = {"protocol_ok": False, "reasons": [error]}
    else:
        mods = upstream_modules()
        parser = mods["parse"]
        parsed = (parser.parse_label_plain(clean) if prompt == "Z" else parser.parse_label_json(clean, "CoT")) if task == "L" else (
            parser.parse_direct(clean) if task == "P" else parser.parse_multi(clean))
        info = mods["protocol"].check(clean, task, prompt, parsed)
        semantic = parsed.get("label") if task == "L" else parsed.get("value") if parsed.get("ok") else None
        status = "ok" if semantic is not None else "missing_format"
        error = None if semantic is not None else parsed.get("error") or parsed.get("form") or "parse_failed"
        if status == "ok":
            if task == "L":
                row["label"] = semantic
                row["logprob_metrics"] = extract_logprob_metrics(generated.get("logprobs"), raw, clean, parsed)
            else:
                row["value"] = float(semantic)
                if task == "M":
                    ps, ws = parsed["estimates"], parsed["weights"]
                    mu = sum(ps) / len(ps)
                    row.update(m_w=float(semantic), m_u=mu,
                               top1=ps[max(range(len(ws)), key=lambda i: ws[i])],
                               unweighted_sd=math.sqrt(sum((p - mu) ** 2 for p in ps) / len(ps)),
                               weighted_sd=parsed["weighted_sd"], endpoint_mass=parsed["endpoint_mass"])
    q_available = row["logprob_metrics"] is not None
    row.update(status=status, parse_error=error, parsed=parsed, protocol=info,
               protocol_ok=info["protocol_ok"], protocol_reasons=info["reasons"],
               q_available=q_available,
               status_strict_q="ok" if task != "L" or q_available else "missing_score")
    return row


def synthetic_response(unit):
    """Known non-zero fixture, never interpreted as experimental evidence."""
    exp, slot, task, prompt = (unit[k] for k in ("exp", "slot", "task", "prompt"))
    if exp == "E1":
        p = 98 if task == "P" else 40
        label = "False"
    elif exp == "E3":
        p = {"NI_OCC": 80, "NI_PLAN": 20, "INT_OCC": 70, "INT_PLAN": 10}[slot]
        label = "True" if slot.endswith("OCC") else "False"
    elif exp == "E2":
        p = {"NI_BARE": 80, "NI_COMP": 60, "INT_BARE": 50, "INT_COMP": 20}[slot]
        if task == "M":
            p = max(10, p - 20)
        label = "True" if slot.endswith("BARE") else "False"
    else:
        p = {"PURE_MOORE": 10, "DUAL_MOORE": 50, "DUAL_EXPLICIT": 90, "PURE_READ": 80}[slot]
        if slot == "DUAL_MOORE" and task == "P" and prompt == "CoT":
            p = 20
        if slot == "DUAL_MOORE" and task == "M" and prompt == "CF":
            p = 80
        label = "True" if slot in ("DUAL_EXPLICIT", "PURE_READ") else "False"
    reasoning = "This is Moore's paradox. There are two distinct standards, local and global."
    if task == "L":
        text = label if prompt == "Z" else json.dumps(dict(reasoning=reasoning, label=label))
    elif task == "P":
        text = (reasoning + "\n" if prompt == "CoT" else "") + f"Probability: {p}%"
    else:
        text = (reasoning + "\n" if prompt == "CF" else "") + "\n".join(
            f"Estimate {i}: {p + delta}% | Weight: {weight}"
            for i, delta, weight in zip(range(1, 6), (-4, -2, 0, 2, 4), (.1, .1, .2, .2, .4)))
    return dict(text=text, truncated=False, logprobs=None)


def run(config, slice_name, dry_run=False, limit=None, out_dir=HERE):
    if config in ZH_SUPPLEMENT_MODELS and slice_name != "slice_e2":
        raise ValueError("Tier-2 supplements collect slice_e2 only")
    if limit is not None and limit < 0:
        raise ValueError("limit must be nonnegative")
    out_dir = Path(out_dir).resolve()
    if not out_dir.is_relative_to(HERE):
        raise ValueError("Outputs must remain within p167-api")
    cfg = CONFIGS[config]
    if not dry_run:
        from freeze_p167 import verify_freeze
        verify_freeze()
    units = build_slice(slice_name)
    if limit is not None:
        units = units[:limit]
    adapter = None if dry_run else APIAdapter(cfg)
    slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", config)
    # Keep fixture output separate from live experiment output.
    base = out_dir / ("dry-run" if dry_run else "")
    result = base / "results" / f"results_p167_{slice_name}_{slug}.jsonl"
    result.parent.mkdir(parents=True, exist_ok=True)
    if result.exists():
        raise FileExistsError(f"Refusing to overwrite existing collection: {result}")
    with result.open("w", encoding="utf-8", newline="\n") as handle:
        for i, unit in enumerate(units):
            if dry_run:
                generated = synthetic_response(unit)
            else:
                if i:
                    time.sleep(cfg["min_interval_sec"])
                try:
                    generated = adapter.generate(unit["messages"])
                except Exception as exc:
                    generated = None
                    error_type = type(exc).__name__
                raw_dir = base / "raw" / slug
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"{slice_name}_{i:05d}.json").write_text(
                    json.dumps(generated if generated is not None else {"transport_error_type": error_type},
                               ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
            row = parse_record(unit, config, generated)
            row["dry_run"] = dry_run
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, choices=CONFIGS)
    parser.add_argument("--slice", required=True, choices=COUNTS)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=HERE)
    args = parser.parse_args()
    print(run(args.config, args.slice, args.dry_run, args.limit, args.out_dir))


if __name__ == "__main__":
    main()
