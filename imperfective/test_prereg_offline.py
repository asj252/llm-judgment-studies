"""Offline preregistration, statistical engine, and S6/S7 guard tests.

Runs entirely from the published imperfective/ directory without third-party
datasets (exp1-en/data/), raw execution ledgers (exp1-en/raw/), model weights,
or network access.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
EXP1_ROOT = HERE / "exp1-en"
STEP5B_ROOT = HERE / "scheme-a-hybrid-calibration-20261101"
HANDOFF_ROOT = HERE / "s5-mac-handoff-20261101"

for _p in (str(HERE), str(HANDOFF_ROOT), str(STEP5B_ROOT / "code"), str(EXP1_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core_a as step5b_core_a  # noqa: E402
import exact_tango as step5b_exact_tango  # noqa: E402
import gates as exp1_gates  # noqa: E402
import gpu_s6_formal_stage_macos as s6_launcher  # noqa: E402
import parse as exp1_parse  # noqa: E402
import run_s7_formal_analysis as s7_engine  # noqa: E402
import verify_prereg  # noqa: E402


class TestPublicPreregOffline(unittest.TestCase):
    def test_01_verify_prereg_passes_offline(self):
        res = verify_prereg.verify(HERE)
        self.assertTrue(res["ok"], f"verify_prereg failed: {res['errors']}")
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["runner_fingerprint_id"], s7_engine.EXPECTED_RUNNER_FP)
        self.assertEqual(res["frozen_plan_sha256"], verify_prereg.EXPECTED_PLAN_E1_SHA256)
        self.assertEqual(res["step5b_code_sha256"], verify_prereg.EXPECTED_STEP5B_CODE_SHA256)

    def test_02_parse_direct_and_sealed_core_a_degeneracy_invariants(self):
        self.assertFalse(exp1_parse.parse_direct("Probability: 50%\nProbability: invalid")["ok"])
        r_ok = exp1_parse.parse_direct("Probability: 50%\nProbability: 72.5%")
        self.assertTrue(r_ok["ok"])
        self.assertEqual(r_ok["value"], 72.5)
        self.assertTrue(exp1_parse.parse_direct("Probability: **50%**")["ok"])
        self.assertFalse(exp1_parse.parse_direct("Probability: 50\t%")["ok"])
        self.assertFalse(exp1_parse.parse_direct("Probability: 50% plus 2")["ok"])

        self.assertEqual(step5b_core_a.TOL_DUST, 1e-12)
        tango_by_n = step5b_exact_tango.load_certified_tango_tables(
            npz_path=STEP5B_ROOT / "manifests" / "exact-tango-tables.npz"
        )["by_n"]
        self.assertIn(20, tango_by_n)
        self.assertIn(80, tango_by_n)

        boot_const = np.zeros((5000, 4), dtype=np.float64)
        obs_zero = np.zeros(4, dtype=np.float64)
        pct_deg = step5b_core_a.infer_percentile_a(boot_const, boot_const, obs_zero, obs_zero)
        self.assertTrue(bool(pct_deg["degenerate"][2]))
        self.assertEqual(pct_deg["ci"][2].tolist(), [-200.0, 200.0])

        grid_fine = np.linspace(1.0, 1.0 + 2.5e-11, 5000, dtype=np.float64)
        boot_fine = np.column_stack([grid_fine, grid_fine, grid_fine, grid_fine])
        pct_fine = step5b_core_a.infer_percentile_a(boot_fine, boot_fine, np.ones(4), np.ones(4))
        self.assertFalse(bool(pct_fine["degenerate"][1]))
        self.assertFalse(bool(pct_fine["degenerate"][2]))

    def test_03_s7_confirmatory_lock_and_cross_channel_protection(self):
        m_s6 = s6_launcher.load_and_verify_execution_manifest()
        m_s7 = s7_engine.load_and_verify_execution_manifest()
        self.assertEqual(m_s6, m_s7)

        base = dict(
            stage="formal",
            cfg=s7_engine.DEFAULT_CONFIG,
            expected_fp=s7_engine.EXPECTED_RUNNER_FP,
            b_reps=s7_engine.FORMAL_BOOTSTRAP_B,
            seed=s7_engine.FORMAL_ANALYSIS_SEED,
            allow_non_ok=True,
            unit_index_json_path=None,
            out_json_path=Path("results/formal-analysis-results.json"),
            out_report_path=Path("results/report-s7-formal.md"),
            diagnostic_non_confirmatory=False,
            test_on_demand_tango_grid=None,
        )
        s7_engine.enforce_confirmatory_formal_lock(**base)

        for override in (
            {"b_reps": 1000},
            {"seed": 123},
            {"allow_non_ok": False},
            {"unit_index_json_path": Path("x.json")},
            {"results_jsonl_path": Path("alt/results.jsonl")},
        ):
            with self.assertRaises(PermissionError):
                s7_engine.enforce_confirmatory_formal_lock(**{**base, **override})

        diag_base = {
            **base,
            "b_reps": 200,
            "diagnostic_non_confirmatory": True,
            "out_json_path": Path("results/diag-results.json"),
            "out_report_path": Path("results/diag-report.md"),
            "write_unit_index_path": Path("results/diag-index.json"),
        }
        s7_engine.enforce_confirmatory_formal_lock(**diag_base)

        for ch in ("out_json_path", "out_report_path", "write_unit_index_path"):
            for protected in (
                "formal-analysis-results.json",
                "FORMAL-ANALYSIS-RESULTS.JSON",
                "report-s7-formal.md",
                "Report-S7-Formal.MD",
                "formal-unit-index.json",
                "FORMAL-UNIT-INDEX.JSON",
            ):
                with self.assertRaises(PermissionError):
                    s7_engine.enforce_confirmatory_formal_lock(**{**diag_base, ch: Path("results") / protected})

    def test_04_fail_closed_s5_freeze_gate_and_4160_unit_streaming(self):
        split_data = json.loads((EXP1_ROOT / "split.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            empty_exp1 = tmp / "empty_exp1"
            empty_exp1.mkdir()
            (empty_exp1 / "split.json").write_bytes((EXP1_ROOT / "split.json").read_bytes())
            with self.assertRaises(PermissionError):
                s7_engine.run_s7_pipeline(stage="formal", exp1_root=empty_exp1, step5b_root=STEP5B_ROOT)

        # Build synthetic 4,160-unit formal ledger stream in memory and verify closed-whitelist sanitization
        planned = s7_engine.build_planned_units_from_split(split_data, "formal")
        self.assertEqual(len(planned), 4160)
        sid = "1111closed1session11111111111111"
        sessions = {sid: {"state": "closed", "reason": "complete", "run_id": "E1-formal"}}
        buf = io.StringIO()
        valid_rows = []
        for idx, unit in enumerate(planned, 1):
            task = unit["task"]
            if task == "L":
                row = {
                    **unit,
                    "stage": "formal",
                    "config": s7_engine.DEFAULT_CONFIG,
                    "fingerprint_id": s7_engine.EXPECTED_RUNNER_FP,
                    "run_id": "E1-formal",
                    "session_id": sid,
                    "commit_seq": idx,
                    "status": "ok",
                    "phases": {"generation": "ok", "parse": "ok", "protocol": False, "scoring": "bounded"},
                    "parsed": {
                        "label": "Unknown",
                        "form": "exact",
                        "extra_keys": ["LEAKED_PROSE_KEY"],
                        "object": {"secret": "LEAKED_OBJ"},
                    },
                    "protocol": {"protocol_ok": False, "reasons": ["extra_keys"]},
                    "q": {"q_status": "bounded", "q_L": 0.1, "q_U": 0.2, "j": 0, "topN": [{"id": 1, "logprob": -0.1}]},
                    "label": "Unknown",
                    "n_out_tokens": 12,
                    "truncated": False,
                    "seconds": 0.5,
                    "generation_seconds": 0.5,
                    "text": "LEAKED_RAW_MODEL_PROSE",
                }
            elif task in ("P", "Ps"):
                row = {
                    **unit,
                    "stage": "formal",
                    "config": s7_engine.DEFAULT_CONFIG,
                    "fingerprint_id": s7_engine.EXPECTED_RUNNER_FP,
                    "run_id": "E1-formal",
                    "session_id": sid,
                    "commit_seq": idx,
                    "status": "ok",
                    "phases": {"generation": "ok", "parse": "ok", "protocol": True, "scoring": "not_applicable"},
                    "parsed": {"ok": True, "value": 50.0, "form": "exact"},
                    "protocol": {"protocol_ok": True, "reasons": []},
                    "q": None,
                    "value": 50.0,
                    "n_out_tokens": 20,
                    "truncated": False,
                    "seconds": 1.0,
                    "generation_seconds": 1.0,
                    "text": "Probability: 50%",
                }
            else:
                ests = [42.0, 46.0, 50.0, 54.0, 58.0]
                wts = [0.2] * 5
                row = {
                    **unit,
                    "stage": "formal",
                    "config": s7_engine.DEFAULT_CONFIG,
                    "fingerprint_id": s7_engine.EXPECTED_RUNNER_FP,
                    "run_id": "E1-formal",
                    "session_id": sid,
                    "commit_seq": idx,
                    "status": "ok",
                    "phases": {"generation": "ok", "parse": "ok", "protocol": True, "scoring": "not_applicable"},
                    "parsed": {
                        "ok": True,
                        "estimates": ests,
                        "weights": wts,
                        "value": 50.0,
                        "weight_sum_in_tolerance": True,
                        "forms": ["exact"] * 5,
                    },
                    "protocol": {"protocol_ok": True, "reasons": []},
                    "q": None,
                    "value": 50.0,
                    "n_out_tokens": 40,
                    "truncated": False,
                    "seconds": 1.5,
                    "generation_seconds": 1.5,
                    "text": "Estimate 1: 50% | Weight: 0.2",
                }
            valid_rows.append(row)
            buf.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

        saved_gate = {
            **exp1_gates.compute("formal", planned, valid_rows),
            "stage": "formal",
            "config": s7_engine.DEFAULT_CONFIG,
            "fingerprint_id": s7_engine.EXPECTED_RUNNER_FP,
        }
        slim_rows, prov = s7_engine.validate_and_slim_ledger_stream(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            split_data=split_data,
            stage="formal",
            sessions=sessions,
            fingerprint_meta={"fingerprint_id": s7_engine.EXPECTED_RUNNER_FP},
            saved_gate=saved_gate,
        )
        self.assertEqual(len(slim_rows), 4160)
        self.assertEqual(prov["skipped_invalid_session_lines"], 0)
        dumped = json.dumps(slim_rows, ensure_ascii=False)
        for forbidden in ("LEAKED_PROSE_KEY", "LEAKED_OBJ", "LEAKED_RAW_MODEL_PROSE", '"topN"', '"extra_keys":'):
            self.assertNotIn(forbidden, dumped)
        self.assertEqual(slim_rows[0]["parsed"]["extra_key_count"], 1)
        self.assertEqual(
            slim_rows[0]["parsed"]["extra_keys_sha256"],
            hashlib.sha256(b'["LEAKED_PROSE_KEY"]').hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
