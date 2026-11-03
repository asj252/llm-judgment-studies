"""Offline preregistration, material validation, prompt/parser, and S4/S5 lock tests for Experiment 2 (Chinese).

Runs entirely from the published imperfective-exp2-zh/ directory without raw
execution ledgers (exp2-zh/raw/), model weights, or network access.
"""
import json
import os
from pathlib import Path
import sys
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
EXP2_ROOT = HERE / "exp2-zh"

for _p in (str(HERE), str(EXP2_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_tokens  # noqa: E402
import parse as exp2_parse  # noqa: E402
import prompts_zh  # noqa: E402
import provenance  # noqa: E402
import validate_materials  # noqa: E402
import verify_prereg_e2  # noqa: E402


class TestPublicPreregE2Offline(unittest.TestCase):
    def test_01_verify_prereg_e2_passes_offline(self):
        res = verify_prereg_e2.verify(HERE)
        self.assertTrue(res["ok"], f"verify_prereg_e2 failed: {res['errors']}")
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["runner_fingerprint_id"], verify_prereg_e2.EXPECTED_RUNNER_FP)
        self.assertEqual(res["runner_fingerprint_recomputed"], "verified")
        self.assertEqual(res["recomputed_unit_counts"], {"dev": 1160, "formal": 4160, "total": 5320})
        self.assertEqual(res["selected_family"], "hybrid_bessel_t_tango_e2")
        self.assertEqual(res["companion_family"], "hybrid_pct_tango_e2")
        self.assertEqual(res["demoted_slots"], [])

    def test_02_100_clusters_and_9_negative_mutations(self):
        hashes = provenance.verify_sources(data_dir=EXP2_ROOT / "data", root_dir=EXP2_ROOT)
        self.assertEqual(hashes["clusters_100_curated.json"], verify_prereg_e2.EXPECTED_CLUSTERS_100_SHA256)
        clusters = provenance.load_clusters(EXP2_ROOT / "data" / "clusters_100_curated.json")
        self.assertEqual(len(clusters), 100)
        self.assertEqual(validate_materials.validate_clusters(clusters), [])
        validate_materials.run_negative_self_tests(clusters[0])
        items = provenance.load_items(EXP2_ROOT / "data" / "clusters_100_curated.json")
        self.assertEqual(len(items), 600)

    def test_03_prompts_zh_and_parse_v2_compatibility(self):
        prompts_zh.verify_parser_compatibility()
        self.assertFalse(exp2_parse.parse_direct("Probability: 50%\nProbability: invalid")["ok"])
        r_ok = exp2_parse.parse_direct("分析略。\nProbability: 72.5%")
        self.assertTrue(r_ok["ok"])
        self.assertEqual(r_ok["value"], 72.5)

    def test_04_frozen_tokens_and_s5_freeze_bindings(self):
        frozen_tokens = json.loads((EXP2_ROOT / "label_tokens_qwen3-8b.json").read_text(encoding="utf-8"))
        assets = json.loads((EXP2_ROOT / "config_assets_macmini-m6.json").read_text(encoding="utf-8"))["models"]["qwen3-8b"]
        self.assertTrue(check_tokens.validate_frozen_structure(frozen_tokens, "qwen3-8b", assets))

        freeze_dir = EXP2_ROOT / "freeze" / "qwen3-8b@macmini-m6" / "f81940ea"
        freeze_meta = json.loads((freeze_dir / "freeze.json").read_text(encoding="utf-8"))
        cal_meta = json.loads((freeze_dir / "calibration-e2.json").read_text(encoding="utf-8"))
        self.assertEqual(freeze_meta["selected_family"], cal_meta["selected_family"])
        self.assertEqual(freeze_meta["selected_family"], "hybrid_bessel_t_tango_e2")
        self.assertTrue(cal_meta["candidate_2_passed_all_16"])
        for cell in cal_meta["candidate_2_cells"]:
            self.assertTrue(cell["cell_passed"])
            self.assertTrue(cell["fwer_passed"])
            self.assertTrue(cell["simultaneous_coverage_9875_passed"])
            self.assertTrue(cell["individual_coverage_9875_passed"])
            self.assertTrue(cell["screen05_passed"])


if __name__ == "__main__":
    unittest.main()
