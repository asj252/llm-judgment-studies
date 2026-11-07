"""Type-bound admission evidence for Experiment 4; source-stage ledgers are always recomputed."""
from datetime import datetime
from pathlib import Path
import random
from typing import Any

from common import atomic_json, digest, read_json, sha256
from deadline import timestamp

STATIC = {"s1_review", "s2_acceptance", "verify_vocab", "verify_probs", "verify_greedy"}
DETERMINISM_SEED_E4 = 2026110692


def _parse_tz_iso(val: Any, field_name: str) -> datetime:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"missing or non-string timestamp for {field_name}")
    try:
        dt = datetime.fromisoformat(val)
    except ValueError as exc:
        raise ValueError(f"unparseable ISO timestamp for {field_name}: {val!r}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"timestamp for {field_name} must include a timezone offset: {val!r}")
    return dt


def record(context, kind, source_stage=None, status="pass", **extra):
    if kind in STATIC:
        source_stage, planned, ledger = None, None, None
    else:
        if source_stage not in ("smoke", "dev"):
            raise ValueError("invalid source stage")
        planned, ledger = context.source_binding(source_stage)
    return {
        "type": kind,
        "status": status,
        "config": context.cfg,
        "fingerprint_id": context.fp,
        "source_stage": source_stage,
        "planned_units_sha256": planned,
        "ledger_digest": ledger,
        "written_at": timestamp(),
        "run_id": context.run_id,
        **extra,
    }


def validate(context, value, kind, source_stage=None):
    required = {
        "type",
        "status",
        "config",
        "fingerprint_id",
        "source_stage",
        "planned_units_sha256",
        "ledger_digest",
        "written_at",
    }
    if not required <= value.keys():
        raise ValueError("admission missing fields")
    if not context.dry and str(value.get("run_id", "")).startswith("E4-DRY-"):
        raise ValueError("dry admission forbidden in real runs")
    expected = record(context, kind, source_stage)
    for key in required - {"written_at"}:
        if value[key] != expected[key]:
            raise ValueError("admission mismatch: " + key)
    if not isinstance(value["written_at"], str) or not value["written_at"]:
        raise ValueError("admission timestamp missing")

    if kind in ("gate", "determinism", "freeze"):
        ns = context.namespace(source_stage)
        if (ns / "PAUSED.json").exists() or not context.closed_stage(source_stage):
            raise ValueError("source stage paused or has an open session")
        if context.gate(source_stage)["status"] != "pass":
            raise ValueError("source-stage gate does not recompute to pass")

    if kind == "determinism":
        rows = sorted((r for r in context.valid_records("dev") if r["status"] == "ok"), key=lambda r: r["unit_key"])
        if len(rows) < 20:
            raise ValueError("insufficient determinism source units")
        selected = random.Random(DETERMINISM_SEED_E4).sample(rows, 20)
        checks = value.get("checks")
        if not isinstance(checks, list) or len(checks) != 20 or any(
            c.get("unit_key") != r["unit_key"] or c.get("original_sha256") != digest(r["generated_ids_raw"]) or c.get("match") is not True
            for c, r in zip(checks, selected)
        ):
            raise ValueError("determinism sample/results mismatch")

    if kind == "freeze":
        from calibrate_e4 import build_dev_profile_from_rows, validate_calibration_artifact
        folder = context.freeze_dir
        plan = folder / "PLAN-E4.frozen.md"
        review = Path(value.get("c_review_file", ""))
        cal_file = folder / "calibration-e4.json"
        if not review.is_absolute():
            review = context.base / review
        if not review.resolve().is_relative_to(context.base.resolve()):
            raise ValueError("review file outside experiment namespace")
        if not plan.is_file() or sha256(plan) != value.get("frozen_plan_sha256") or not review.is_file():
            raise ValueError("freeze snapshot/review mismatch")
        if not cal_file.is_file() or sha256(cal_file) != value.get("calibration_sha256"):
            raise ValueError("freeze calibration artifact missing or sha256 mismatch")

        dev_rows = context.valid_records("dev")
        dev_profile = build_dev_profile_from_rows(dev_rows)
        dev_run_ids = sorted({str(r["run_id"]) for r in dev_rows if r.get("run_id")})
        dev_ledger_file = context.namespace("dev") / "results.jsonl"
        _, dev_ledger_dig = context.source_binding("dev")
        cal = validate_calibration_artifact(
            read_json(cal_file),
            require_production=not context.dry,
            expected_dev_run_ids=dev_run_ids if not context.dry else None,
            expected_dev_ledger_sha256=sha256(dev_ledger_file) if (not context.dry and dev_ledger_file.is_file()) else None,
            expected_dev_ledger_digest=dev_ledger_dig if not context.dry else None,
            expected_dev_complete_cluster_counts=dev_profile["complete_cluster_counts"] if not context.dry else None,
        )
        if value.get("selected_family") != cal.get("selected_family") or value.get("demoted_slots") != cal.get("demoted_slots", []):
            raise ValueError("freeze selected_family or demoted_slots mismatch with calibration artifact")
        if type(value.get("c_blockers")) is not int or value["c_blockers"] != 0 or value.get("user_confirmed") is not True or not value.get("confirmed_at"):
            raise ValueError("freeze lacks review/user confirmation")
        prereg_commit = value.get("prereg_commit")
        if not isinstance(prereg_commit, str) or not prereg_commit.strip():
            raise ValueError("freeze missing public preregistration commit (prereg_commit)")
        if not context.dry and prereg_commit.strip().lower().startswith("e4-dry"):
            raise ValueError("dry prereg_commit forbidden in real runs")
        _parse_tz_iso(value.get("written_at"), "freeze.written_at")
        _parse_tz_iso(value.get("confirmed_at"), "freeze.confirmed_at")
        _parse_tz_iso(value.get("prereg_pushed_at"), "freeze.prereg_pushed_at")

    return value


def require(context, path, kind, source_stage=None):
    if not Path(path).is_file():
        raise ValueError("admission evidence absent: " + str(path))
    return validate(context, read_json(path), kind, source_stage)


def check_stage(context, stage):
    for kind in ("s1_review", "s2_acceptance"):
        require(context, context.admission_dir / (kind + ".json"), kind)
    if stage in ("dev", "formal", "determinism"):
        require(context, context.namespace("smoke") / "gate.json", "gate", "smoke")
        for kind in ("verify_vocab", "verify_probs", "verify_greedy"):
            require(context, context.admission_dir / (kind + ".json"), kind)
    if stage in ("formal", "determinism"):
        dev = context.valid_records("dev")
        if len(dev) != len(context.plan("dev")) or not context.gate("dev", dev)["complete"]:
            raise ValueError("dev incomplete or unclosed")
        require(context, context.namespace("dev") / "gate.json", "gate", "dev")
    if stage == "formal":
        require(context, context.admission_dir / "determinism.json", "determinism", "dev")
        frz = require(context, context.freeze_dir / "freeze.json", "freeze", "dev")
        t_frz_written = _parse_tz_iso(frz.get("written_at"), "freeze.written_at")
        t_prereg_pushed = _parse_tz_iso(frz.get("prereg_pushed_at"), "freeze.prereg_pushed_at")
        t_now = _parse_tz_iso(timestamp(), "current_time")
        if not (t_frz_written < t_now):
            raise ValueError("freeze.written_at must be strictly earlier than current formal admission/start time")
        if not (t_prereg_pushed < t_now):
            raise ValueError("freeze.prereg_pushed_at must be strictly earlier than current formal admission/start time")
        formal_rows = context.valid_records("formal")
        if formal_rows:
            row_dts = [
                _parse_tz_iso(r.get("written_at"), f"formal[{r.get('unit_key')}].written_at")
                for r in formal_rows
            ]
            t_min_formal = min(row_dts)
            if not (t_frz_written < t_min_formal):
                raise ValueError("freeze.written_at must be strictly earlier than earliest formal unit timestamp")
            if not (t_prereg_pushed < t_min_formal):
                raise ValueError("freeze.prereg_pushed_at must be strictly earlier than earliest formal unit timestamp")
