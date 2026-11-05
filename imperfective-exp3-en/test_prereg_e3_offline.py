"""Offline preregistration, parser, Tango metadata, and S4/S5 calibration lock tests for Experiment 3 (English).

Runs entirely from the published imperfective-exp3-en/ directory using only the
Python standard library, without third-party datasets (exp3-en/data/), raw
execution ledgers (exp3-en/data/raw/), model weights, or network access.
"""
import json
import os
from pathlib import Path
import sys
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
EXP3_ROOT = HERE / "exp3-en"

for _p in (str(HERE), str(EXP3_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_tokens  # noqa: E402
import materials_e3  # noqa: E402
import parse as exp3_parse  # noqa: E402
import verify_prereg_e3  # noqa: E402


class TestPublicPreregE3Offline(unittest.TestCase):
    def test_01_verify_prereg_e3_passes_offline(self):
        res = verify_prereg_e3.verify(HERE)
        self.assertTrue(res["ok"], f"verify_prereg_e3 failed: {res['errors']}")
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["runner_fingerprint_id"], verify_prereg_e3.EXPECTED_RUNNER_FP)
        self.assertEqual(res["recomputed_unit_counts"], {"dev": 1160, "formal": 4160, "total": 5320})
        self.assertEqual(res["selected_family"], "hybrid_bessel_t_tango_e3")
        self.assertEqual(res["companion_family"], "hybrid_pct_tango_e3")
        self.assertEqual(res["demoted_slots"], ["E3_H3"])

    def test_02_tango_7_sample_sizes_and_parse_v2(self):
        tango_meta = json.loads((EXP3_ROOT / "manifests" / "exact-tango-tables-e3-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(tango_meta["supported_ns"], [8, 12, 16, 20, 64, 79, 80])
        self.assertEqual(tango_meta["npz_file_sha256"], verify_prereg_e3.EXPECTED_TANGO_NPZ_SHA256)
        self.assertEqual(tango_meta["npz_payload_sha256"], verify_prereg_e3.EXPECTED_TANGO_PAYLOAD_SHA256)
        self.assertEqual(len(tango_meta["certified_left_cuts"]), 21)
        for n_key, inv in tango_meta["invariants"].items():
            self.assertEqual(inv["p_monotonicity_violations"], 0, n_key)

        self.assertFalse(exp3_parse.parse_direct("Probability: 50%\nProbability: invalid")["ok"])
        r_ok = exp3_parse.parse_direct("Analysis.\nProbability: 72.5%")
        self.assertTrue(r_ok["ok"])
        self.assertEqual(r_ok["value"], 72.5)

    def test_03_frozen_tokens_and_s4_step3_calibration_lock(self):
        frozen_tokens = json.loads((EXP3_ROOT / "label_tokens_qwen3-8b.json").read_text(encoding="utf-8"))
        assets = json.loads((EXP3_ROOT / "config_assets_macmini-m6.json").read_text(encoding="utf-8"))["models"]["qwen3-8b"]
        self.assertTrue(check_tokens.validate_frozen_structure(frozen_tokens, "qwen3-8b", assets))

        freeze_dir = EXP3_ROOT / "freeze" / "qwen3-8b@macmini-m6" / "cbd3b5af"
        cal_meta = json.loads((freeze_dir / "calibration-e3.json").read_text(encoding="utf-8"))
        self.assertEqual(cal_meta["schema_version"], "e3_calibration_v1")
        self.assertTrue(cal_meta["production_eligible"])
        self.assertEqual(cal_meta["status"], "pass")
        self.assertEqual(cal_meta["selected_step"], 3)
        self.assertEqual(cal_meta["selected_family"], "hybrid_bessel_t_tango_e3")
        self.assertEqual(cal_meta["companion_family"], "hybrid_pct_tango_e3")
        self.assertEqual(cal_meta["demoted_slots"], ["E3_H3"])
        self.assertEqual(len(cal_meta["step3_demoted_cells"]), 20)
        for cell in cal_meta["step3_demoted_cells"]:
            self.assertTrue(cell["cell_passed"])
            self.assertTrue(cell["fwer_passed"])
            self.assertTrue(cell["simultaneous_coverage_9875_passed"])
            self.assertTrue(cell["individual_coverage_9875_passed"])
            self.assertTrue(cell["screen05_passed"])

    def test_04_subclasses_and_split_manifests_reconstruct_cleanly(self):
        subclasses_built = materials_e3.build_subclasses_manifest()
        subclasses_disk = json.loads((EXP3_ROOT / "subclasses_e3.json").read_text(encoding="utf-8"))
        self.assertEqual(subclasses_built, subclasses_disk)
        split_built = materials_e3.build_split_manifest(subclasses_built)
        split_disk = json.loads((EXP3_ROOT / "split.json").read_text(encoding="utf-8"))
        self.assertEqual(split_built, split_disk)


if __name__ == "__main__":
    unittest.main()
