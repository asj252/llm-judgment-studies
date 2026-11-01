"""Experiment 1 runner, adapted structurally from dnli/run.py (2026-10-26).

Retains item-interleaved scheduling, sessions, resume, fingerprints and admission.
Removes codex-specific logic, resampling and thread pools. Single active unit;
only transport retries, raw-ID q prefixes and an independent deadline watchdog.
"""
import argparse
import importlib.util
import json
import os
import random
import socket
import sys
import time
import uuid
from pathlib import Path
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, atomic_json, digest, read_json, sha256, write_json
import admission
import gates
import parse
import protocol
import score
from deadline import Deadline, Interrupted, deadline_epoch, timestamp
from host import FakeHost
from ledger import Ledger, ledger_digest
from prompts import COMBINATIONS, render_unit
from provenance import load_items, verify_sources
from subject import MAX_TOKENS, SAMPLING

TRANSPORT = (OSError, URLError, ConnectionError, TimeoutError)
FILES = ("common.py", "provenance.py", "split.py", "prompts.py", "prompt_parts.py", "parse.py", "protocol.py", "score.py", "run.py",
         "subject.py", "host.py", "admission.py", "ledger.py", "gates.py", "deadline.py", "dry_stub.py", "check_tokens.py", "split.json")


class Context:
    def __init__(self, cfg, *, dry=False, base=None, host=None, host_file=None, read_only=False):
        self.cfg, self.dry = cfg, dry
        if cfg.count("@") != 1:
            raise ValueError("config must be <model_key>@<host_id>")
        self.model, self.host_id = cfg.split("@")
        if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in self.model + self.host_id) or not self.model or not self.host_id:
            raise ValueError("invalid config name")
        self.base = Path(base or (ROOT / "raw" / "dry" if dry else ROOT))
        if dry and not self.base.resolve().is_relative_to((ROOT / "raw" / "dry").resolve()):
            raise ValueError("dry base outside raw/dry")
        self.raw = self.base if dry else self.base / "raw"
        self.run_id = ("E1-DRY-" if dry else "E1-") + uuid.uuid4().hex
        self.model_cfg = read_json(ROOT / "config_models.json")[self.model]
        self.host_file, self.host = host_file, host
        if dry and self.host is None:
            self.host = FakeHost(self.host_id)
        asset_path = self.base / ("config_assets_" + self.host_id + ".json")
        self.asset_path = asset_path
        if dry and not asset_path.exists():
            if read_only:
                raise ValueError("read-only context requires existing dry assets")
            write_json(asset_path, {"host_id": self.host_id, "models": {self.model: self.host.identity}, "run_id": self.run_id})
        asset_config = read_json(asset_path)
        if asset_config["host_id"] != self.host_id:
            raise ValueError("host identity mismatch")
        self.assets = asset_config["models"][self.model]
        verify_sources()
        self.items = {i["id"]: i for i in load_items()}
        self.split = read_json(ROOT / "split.json")
        if self.split["data_sha256"] != sha256(ROOT / "data" / "imperfectiveNLI.json"):
            raise ValueError("split data identity mismatch")
        if dry:
            self.candidates = {"True": [1], "False": [2], "Unknown": [3]}
            token_path = self.base / ("label_tokens_" + self.model + ".json")
            if not token_path.exists():
                if read_only:
                    raise ValueError("read-only context requires existing dry candidates")
                write_json(token_path, {"sets": self.candidates, "run_id": self.run_id})
        else:
            token_path = ROOT / ("label_tokens_" + self.model + ".json")
            self.candidates = read_json(token_path)["sets"]
        self.token_path = token_path
        material = [(u["unit_key"], digest(render_unit(self.items[u["id"]], u["task"], u["prompt"]))) for s in ("dev", "formal") for u in self.plan(s)]
        self.fingerprint = {"files": {f: sha256(ROOT / f) for f in FILES}, "model": self.model_cfg,
            "host_id": self.host_id, "assets": self.assets, "tokens": sha256(token_path),
            "host_implementation": sha256(host_file) if host_file else "FakeHost" if dry else None,
            "materials": digest(material), "sampling": SAMPLING, "max_tokens": MAX_TOKENS,
            "rules": {"topN": score.TOP_N, "score_version": score.VERSION, "parse_version": parse.PARSE_VERSION,
                      "protocol_version": protocol.VERSION}, "dry": dry}
        self.fp = digest(self.fingerprint)
        self.admission_dir = self.raw / "admission" / cfg / self.fp[:8]
        self.freeze_dir = self.base / "freeze" / cfg / self.fp[:8]

    def assert_current(self):
        verify_sources()
        if read_json(self.asset_path)["host_id"] != self.host_id:
            raise ValueError("asset file host_id changed")
        current = {**self.fingerprint,
            "files": {f: sha256(ROOT / f) for f in FILES},
            "model": read_json(ROOT / "config_models.json")[self.model],
            "assets": read_json(self.asset_path)["models"][self.model],
            "tokens": sha256(self.token_path),
            "host_implementation": sha256(self.host_file) if self.host_file else "FakeHost" if self.dry else None}
        if digest(current) != self.fp:
            raise ValueError("fingerprint changed before call")

    def plan(self, stage):
        ids = sorted(self.split[stage]["ids"])
        random.Random(20261091).shuffle(ids)
        return [{"id": iid, "task": t, "prompt": p, "unit_key": f"{iid}/{t}/{p}", "gold_label": self.items[iid]["label"]}
                for iid in ids for t, p in COMBINATIONS]

    def namespace(self, stage):
        return self.raw / stage / self.cfg / self.fp[:8]

    def valid_records(self, stage):
        ns = self.namespace(stage)
        if not ns.exists():
            return []
        return self.validate_records(stage, Ledger(ns).load())

    def validate_records(self, stage, records):
        planned = {u["unit_key"]: u for u in self.plan(stage)}
        for row in records:
            unit = planned.get(row.get("unit_key"))
            if (unit is None or any(row.get(k) != v for k, v in unit.items()) or
                    row.get("stage") != stage or row.get("config") != self.cfg or
                    row.get("fingerprint_id") != self.fp):
                raise ValueError("ledger stage/config/fingerprint/plan mismatch")
            if not self.dry and (str(row.get("run_id", "")).startswith("E1-DRY-") or row.get("dry") is True):
                raise ValueError("dry ledger forbidden in real runs")
        return records

    def closed_stage(self, stage):
        path = self.namespace(stage) / "sessions.json"
        return path.is_file() and not any(s["state"] == "open" for s in read_json(path).values())

    def source_binding(self, stage):
        return digest(self.plan(stage)), ledger_digest(self.valid_records(stage))

    def gate(self, stage, records=None):
        records = self.valid_records(stage) if records is None else self.validate_records(stage, records)
        stats = gates.compute(stage, self.plan(stage), records)
        if not self.closed_stage(stage) or (self.namespace(stage) / "PAUSED.json").exists():
            stats["status"] = "fail"
        if stage == "formal":
            return {**stats, "stage": stage, "config": self.cfg, "fingerprint_id": self.fp, "written_at": timestamp()}
        return admission.record(self, "gate", stage, status=stats["status"], **{k: v for k, v in stats.items() if k != "status"})

    def subject(self, guard, scenarios=None, evidence=None):
        if self.dry:
            from dry_stub import DrySubject
            return DrySubject(self.host, scenarios, timeout=guard.timeout)
        from check_tokens import load_tokenizer, validate_frozen
        from subject import LlamaServerSubject
        tok, hashes = load_tokenizer(self.model_cfg)
        validate_frozen(tok, hashes, read_json(self.token_path), self.model, self.assets)
        port = self.assets.get("port")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("real host asset configuration requires a frozen port in [1, 65535]")
        return LlamaServerSubject({**self.model_cfg, "port": port}, self.host, tok, port, timeout=guard.timeout,
                                  logdir=self.raw / "llama_server", evidence=evidence)


def start_subject(context, guard, factory=None, scenarios=None, evidence=None):
    guard.check()
    if context.host.host_id != context.host_id:
        raise ValueError("injected host_id does not match configuration")
    try:
        ok, detail = context.host.busy_check()
    except Exception as exc:
        raise ValueError("busy check failed; startup refused") from exc
    if ok is not True:
        raise ValueError("host busy/unknown: " + str(detail))
    if context.host.asset_identity(context.model_cfg) != context.assets:
        raise ValueError("asset identity mismatch")
    guard.check()
    subject = factory(guard) if factory else context.subject(guard, scenarios, evidence)
    try:
        guard.attach(subject)
        guard.check()
        subject.start(context.assets, context.assets["service"])
        guard.attach(subject)
        guard.check()
        return subject
    except BaseException:
        subject.close()
        raise


def retry(call, guard, phase, errors, evidence, hook=None):
    for n in range(1, 4):
        guard.check()
        aid = uuid.uuid4().hex
        try:
            if hook:
                hook(phase)
            guard.check()
            result = call()
            guard.check()
            evidence(aid, {"phase": phase, "attempt": n, "result": result})
            return result, aid
        except TRANSPORT as exc:
            guard.check()
            error = {"phase": phase, "attempt": n, "attempt_id": aid, "type": type(exc).__name__, "message": str(exc)}
            errors.append(error)
            evidence(aid, error)
    return None, aid


def evaluate(context, unit, subject, guard, evidence, hook=None):
    started = time.monotonic()
    errors = []
    messages = render_unit(context.items[unit["id"]], unit["task"], unit["prompt"])
    generated, aid = retry(lambda: subject.generate(messages, unit=unit), guard, "generation", errors, evidence, hook)
    row = {**unit, "stage": None, "run_id": context.run_id, "attempt_id": aid, "written_at": timestamp(),
           "rendered_prompt_sha256": digest(messages), "messages": messages, "errors": errors,
           "parsed": None, "protocol": None, "q": None, "phases": {"generation": "failed"},
           "prompt_ids": [], "generated_ids": [], "generated_ids_raw": [], "stop_token_id": None, "text": None, "n_out_tokens": 0, "truncated": False, "seconds": 0}
    if generated is None:
        return {**row, "status": "missing_transport", "seconds": time.monotonic() - started}
    row.update(generated)
    row["phases"]["generation"] = "ok"
    if hook:
        hook("parse")
    guard.check()
    task, prompt, text = unit["task"], unit["prompt"], generated["text"]
    parsed = (parse.parse_label_plain(text) if prompt in ("Z", "DAP") else parse.parse_label_json(text, prompt)) if task == "L" else (
        parse.parse_multi(text) if task == "M" else parse.parse_direct(text))
    row["parsed"] = parsed
    row["protocol"] = protocol.check(text, task, prompt, parsed)
    semantic = parsed.get("label") if task == "L" else parsed.get("value")
    row["label" if task == "L" else "value"] = semantic
    row["generation_seconds"] = generated["seconds"]
    row["phases"].update(parse="ok" if semantic is not None else "failed", protocol=row["protocol"]["protocol_ok"],
                         scoring="not_attempted" if task == "L" else "not_applicable")
    if task == "L" and not row["truncated"] and semantic is not None:
        q = score.locate(text, parsed, row["prompt_ids"], row["generated_ids"], subject.tok, context.candidates, prompt)
        if q["q_status"] == "ready":
            if q["j"] == 0:
                top = generated["first_topN"]
            else:
                top, _ = retry(lambda: subject.top_at(q["prefix_ids"]), guard, "scoring", errors, evidence, hook)
            q = {**q, **(score.missing("transport") if top is None else score.score_top(top, context.candidates))}
        row["q"] = q
        row["phases"]["scoring"] = q["q_status"]
    guard.check()
    row["status"] = ("missing_format" if row["truncated"] or semantic is None else
        "missing_score" if task == "L" and (row["q"] or {}).get("q_status") not in ("full", "bounded") else "ok")
    row["seconds"] = time.monotonic() - started
    return row


def persist_pause(context, stage, records):
    stats = gates.compute(stage, context.plan(stage), records)
    if stats["pause"]:
        atomic_json(context.namespace(stage) / "PAUSED.json",
                    {"reasons": stats["pause_reasons"], "written_at": timestamp()})
    return stats


def run_stage(context, stage, *, deadline=None, now=time.time, scenarios=None, factory=None, hook=None, limit=None):
    guard = Deadline(deadline, now)
    if not guard.can_start():
        raise ValueError("past cutoff for new units")
    ns = context.namespace(stage)
    if (ns / "PAUSED.json").exists():
        raise ValueError("namespace PAUSED; resume refused")
    ledger = Ledger(ns, pid_alive=getattr(context.host, "pid_alive", None))
    sid, subject, reason, records = None, None, "exception", []
    ledger.acquire()
    try:
        ledger.recover_sessions()
        records = context.validate_records(stage, ledger.load(repair=True))
        context.assert_current()
        if persist_pause(context, stage, records)["pause"]:
            raise ValueError("namespace PAUSED from recovered ledger; resume refused")
        meta = ns / "fingerprint.json"
        if meta.exists() and read_json(meta)["fingerprint_id"] != context.fp:
            raise ValueError("fingerprint collision/mismatch")
        atomic_json(meta, {"fingerprint_id": context.fp, "fingerprint": context.fingerprint})
        admission.check_stage(context, stage)
        sid = ledger.begin(context.run_id)
        def evidence(aid, data):
            write_json(ns / "calls" / f"{sid}_{aid}.json", data)
        def http_evidence(path, body, raw):
            folder = ns / "calls"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{sid}_{uuid.uuid4().hex}"
            (folder / (name + ".response")).write_bytes(raw)
            write_json(folder / (name + ".request.json"), {"endpoint": path, "body": body})
        guard.start()
        if hook:
            hook("loading")
        subject = start_subject(context, guard, factory, scenarios, http_evidence)
        done, count = {r["unit_key"] for r in records}, 0
        reason = "complete"
        for unit in context.plan(stage):
            if unit["unit_key"] in done:
                continue
            if not guard.can_start():
                reason = "cutoff"
                break
            row = evaluate(context, unit, subject, guard, evidence, hook)
            row.update(stage=stage, session_id=sid, config=context.cfg, fingerprint_id=context.fp)
            if not ledger.commit(row, guard, hook):
                reason = "deadline"
                break
            records.append(row)
            count += 1
            stats = persist_pause(context, stage, records)
            guard.check()
            if stats["pause"]:
                reason = "pause"
                break
            if row["status"] == "missing_transport":
                reason = "transport_exhausted"
                break
            if limit is not None and count >= limit:
                reason = "limit"
                break
    except Interrupted:
        reason = "deadline"
    except BaseException:
        if guard.poll():
            reason = "deadline"
        else:
            raise
    finally:
        if subject:
            subject.close()
        guard.close()
        if sid:
            ledger.finish(sid, reason)
            atomic_json(ns / ("statistics.json" if stage == "formal" else "gate.json"), context.gate(stage))
        ledger.release()
    return {"reason": reason, "terminal_records": len(context.valid_records(stage)), "run_id": context.run_id,
            "session_id": sid, "exit_code": guard.exit_code}


def determinism(context, factory=None, deadline=None, now=time.time):
    context.assert_current()
    admission.check_stage(context, "determinism")
    rows = sorted((r for r in context.valid_records("dev") if r["status"] == "ok"), key=lambda r: r["unit_key"])
    if len(rows) < 20:
        raise ValueError("fewer than 20 eligible determinism units")
    sampled = random.Random(20261092).sample(rows, 20)
    guard, subject, checks = Deadline(deadline, now), None, []
    if not guard.can_start():
        raise ValueError("past cutoff for determinism")
    guard.start()
    try:
        subject = start_subject(context, guard, factory)
        for r in sampled:
            if not guard.can_start():
                break
            errors = []
            output, _ = retry(lambda: subject.generate(r["messages"], unit=r), guard, "generation", errors,
                lambda aid, data: write_json(context.admission_dir / "determinism_calls" / (aid + ".json"), data))
            checks.append({"unit_key": r["unit_key"], "original_sha256": digest(r["generated_ids_raw"]),
                "match": output is not None and output["generated_ids_raw"] == r["generated_ids_raw"], "errors": errors})
    finally:
        if subject:
            subject.close()
        guard.close()
    value = admission.record(context, "determinism", "dev",
        status="pass" if len(checks) == len(sampled) and all(c["match"] for c in checks) else "fail", checks=checks)
    atomic_json(context.admission_dir / "determinism.json", value)
    return value


def prepare_dry(context, freeze=False):
    if not context.dry:
        raise ValueError("prepare-dry requires --dry")
    for kind in ("s1_review", "s2_acceptance"):
        atomic_json(context.admission_dir / (kind + ".json"), admission.record(context, kind))
    if freeze:
        snapshot = context.freeze_dir / "PLAN-E1.frozen.md"
        review = context.freeze_dir / "c-review.md"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            with snapshot.open("x", encoding="utf-8", newline="\n") as f:
                f.write("# Fake frozen plan; E1-DRY evidence only\n")
        if not review.exists():
            with review.open("x", encoding="utf-8", newline="\n") as f:
                f.write("Fake c review: zero blockers; E1-DRY only\n")
        value = admission.record(context, "freeze", "dev", frozen_plan_sha256=sha256(snapshot), c_blockers=0,
            c_review_file=str(review.relative_to(context.base)), user_confirmed=True, confirmed_at=timestamp())
        atomic_json(context.freeze_dir / "freeze.json", value)


def verify(context, deadline=None, now=time.time, factory=None):
    context.assert_current()
    admission.check_stage(context, "smoke")
    guard, subject = Deadline(deadline, now), None
    if not guard.can_start():
        raise ValueError("past cutoff for verification")
    guard.start()
    try:
        subject = start_subject(context, guard, factory)
        item = context.items[context.split["smoke"]["ids"][0]]
        messages = render_unit(item, "L", "Z")
        for kind, call in (("verify_vocab", lambda: subject.verify_vocab([m["content"] for m in messages])),
                           ("verify_probs", lambda: subject.verify_probs(messages)), ("verify_greedy", lambda: subject.verify_greedy(messages))):
            guard.check()
            try:
                result = call()
            except (OSError, ValueError, KeyError) as exc:
                guard.check()
                result = {"status": "fail", "error_type": type(exc).__name__, "error": str(exc)}
            guard.check()
            atomic_json(context.admission_dir / (kind + ".json"), admission.record(context, kind, status=result["status"], evidence=result))
    finally:
        if subject:
            subject.close()
        guard.close()


def write_freeze(context, plan_path, review_path, confirmed_at, *, c_blockers=0, user_confirmed=False, status="fail"):
    """Auxiliary author command; never overwrites an immutable snapshot."""
    admission.check_stage(context, "determinism")
    admission.require(context, context.admission_dir / "determinism.json", "determinism", "dev")
    if type(c_blockers) is not int or c_blockers != 0 or user_confirmed is not True or not confirmed_at:
        raise ValueError("freeze requires zero blockers and explicit user confirmation/date")
    paths = [Path(p).resolve() for p in (plan_path, review_path)]
    if not all(p.is_relative_to(context.base.resolve()) and p.is_file() for p in paths):
        raise ValueError("freeze sources must be experiment-local files")
    context.freeze_dir.mkdir(parents=True, exist_ok=True)
    for source, name in zip(paths, ("PLAN-E1.frozen.md", "c-review.md")):
        target = context.freeze_dir / name
        content = source.read_text(encoding="utf-8").replace("\r\n", "\n")
        if target.exists():
            if target.read_text(encoding="utf-8") != content:
                raise ValueError("immutable freeze snapshot already exists with different content")
        else:
            with target.open("x", encoding="utf-8", newline="\n") as f:
                f.write(content)
    value = admission.record(context, "freeze", "dev", status=status,
        frozen_plan_sha256=sha256(context.freeze_dir / "PLAN-E1.frozen.md"), c_blockers=c_blockers,
        c_review_file=str((context.freeze_dir / "c-review.md").relative_to(context.base)),
        user_confirmed=True, confirmed_at=confirmed_at)
    atomic_json(context.freeze_dir / "freeze.json", value)
    return value


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("command", choices=("smoke", "dev", "formal", "gates", "verify", "determinism", "prepare-dry", "record", "freeze"))
    parser.add_argument("arguments", nargs="+")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--host-id")
    parser.add_argument("--host-module", default="host_macos.py")
    parser.add_argument("--deadline")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--status", choices=("pass", "fail"), default="fail")
    parser.add_argument("--plan")
    parser.add_argument("--review")
    parser.add_argument("--confirmed-at")
    parser.add_argument("--c-blockers", type=int, default=0)
    parser.add_argument("--user-confirmed", action="store_true")
    args = parser.parse_args()
    cfg = args.arguments[-1]
    if "@" not in cfg and args.host_id:
        cfg += "@" + args.host_id
    if args.host_id and cfg.split("@")[-1] != args.host_id:
        raise ValueError("--host-id disagrees with configuration")
    host, host_file = None, None
    if not args.dry:
        host_file = ROOT / args.host_module
        if not host_file.resolve().is_relative_to(ROOT) or not host_file.is_file():
            raise ValueError("S2m host adapter is required for real runs")
        spec = importlib.util.spec_from_file_location("experiment_host", host_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        host = module.make_host(cfg.split("@")[-1])
    context = Context(cfg, dry=args.dry, host=host, host_file=host_file)
    if args.command in ("smoke", "dev", "formal"):
        result = run_stage(context, args.command, deadline=deadline_epoch(args.deadline))
    elif args.command == "prepare-dry":
        prepare_dry(context, args.freeze)
        result = {"prepared": True, "fingerprint_id": context.fp}
    elif args.command == "verify":
        verify(context, deadline=deadline_epoch(args.deadline))
        result = {"verified": True}
    elif args.command == "determinism":
        result = determinism(context, deadline=deadline_epoch(args.deadline))
    elif args.command == "gates":
        stage = args.arguments[0]
        result = context.gate(stage)
        atomic_json(context.namespace(stage) / ("statistics.json" if stage == "formal" else "gate.json"), result)
    elif args.command == "freeze":
        result = write_freeze(context, args.plan, args.review, args.confirmed_at,
            c_blockers=args.c_blockers, user_confirmed=args.user_confirmed, status=args.status)
    else:
        kind = args.arguments[0]
        if kind not in ("s1_review", "s2_acceptance"):
            raise ValueError("record supports a-authored S1/S2 evidence only; freeze requires reviewed immutable snapshot")
        result = admission.record(context, kind, status=args.status)
        atomic_json(context.admission_dir / (kind + ".json"), result)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
