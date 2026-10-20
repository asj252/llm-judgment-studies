"""Synthetic checkpoint filtering and exact upstream numerical equivalence."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import explore_spread_agy as agy


class SpreadAgyTests(unittest.TestCase):
    def setUp(self):
        # Avoid Windows tempfile's restrictive mode=0o700 under managed ACLs.
        self.base = agy.HERE / (".test_spread_" + uuid.uuid4().hex)
        self.base.mkdir()
        self.addCleanup(self.clean_fixture)
        self.config = agy.CONFIGS[0]
        self.suffix = agy.run.file_config(self.config)
        self.rows, self.sessions = [], []
        self.fp = "synthetic-frozen"
        for i in range(8):
            for j, (pres, ut) in enumerate(agy.spread.CELLS):
                result = dict(estimates=[10 + i, 20 + j, 30 + i + j, 60, 90],
                              weights=[0.1, 0.2, 0.3, 0.2, 0.2])
                if i == 0 and j == 0:
                    result["estimates"] = [0] * 5  # Valid SD, undefined relative spread.
                if i == 1 and j == 1:
                    result["weights"] = [0.3] * 5  # Sensitivity exclusion.
                if i == 2 and j == 2:
                    result["estimates"] = [101] * 5  # Invalid candidate data.
                result["weighted_sd"] = 999 if j == 3 else 0
                row = dict(key=f"pair{i}", pres=pres, utype=ut, ask="multi", round="r0",
                           status="ok", config=self.config, cluster=f"cluster{i // 2}", result=result)
                row["unit"] = "|".join((row["key"], pres, ut, "multi", "r0"))
                self.register(row)
        self.write()

    def clean_fixture(self):
        for path in self.base.iterdir():
            path.unlink()
        self.base.rmdir()

    def register(self, row, **session_overrides):
        row = copy.deepcopy(row)
        row.update(session_id=f"session{len(self.rows)}", fingerprint_id=self.fp)
        self.rows.append(row)
        self.sessions.append(dict(session_id=row["session_id"], unit=row["unit"],
                                  fingerprint_id=self.fp, closed_ok=True, invalid=False,
                                  record_sha256=agy.run.record_hash(row), **session_overrides))
        return row

    def write(self):
        (self.base / f"results_formal_{self.suffix}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in self.rows), encoding="utf-8")
        (self.base / f"run_meta_formal_{self.suffix}.json").write_text(
            json.dumps(dict(fingerprint_id=self.fp, sessions=self.sessions)), encoding="utf-8")
        (self.base / "analysis_freeze.json").write_text(
            json.dumps({"formal": {self.config: self.fp}}), encoding="utf-8")

    def test_registered_filter_last_unit_then_analysis_filter(self):
        replacement = copy.deepcopy(self.rows[0])
        replacement["result"]["estimates"] = [25] * 5
        self.register(replacement)
        for field, value in (("invalid", True), ("closed_ok", False), ("fingerprint_id", "old")):
            self.register(self.rows[1])
            self.sessions[-1][field] = value
        self.rows.append(dict(self.rows[0], session_id="unregistered"))
        self.register(dict(self.rows[2], round="r1", unit="repeat|stated|W|multi|r1"))
        self.register(dict(self.rows[3], ask="direct", unit="direct|reported|S|direct|r0"))
        self.register(dict(self.rows[4], status="missing"))  # Last unit must remove earlier ok.
        self.write()
        path = self.base / f"results_formal_{self.suffix}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write('{"incomplete":\n')
        records, audit, _ = agy.load_records(self.config, self.base)
        self.assertEqual(records[("pair0", "prior", "-")]["mean"], 25)
        self.assertNotIn(("pair0", "reported", "W"), records)
        expected = agy.run.valid_records(self.rows, self.sessions, self.fp)
        self.assertEqual(audit["registered_units"], len(expected))
        self.assertEqual(audit["excluded_records"], len(self.rows) - len(expected))
        self.assertEqual(audit["malformed_lines"], 1)
        self.assertEqual(audit["selected"], 39)

    def test_integrity_tampering_rejected(self):
        self.rows[0]["result"]["weights"][0] = 9
        self.write()
        with self.assertRaisesRegex(agy.run.Stop, "checkpoint integrity"):
            agy.load_records(self.config, self.base)

    def test_missing_registered_checkpoint_rejected(self):
        self.rows.pop()
        self.write()
        with self.assertRaisesRegex(agy.run.Stop, "registered checkpoint result missing"):
            agy.load_records(self.config, self.base)

    def test_frozen_fingerprint_mismatch_rejected(self):
        (self.base / "analysis_freeze.json").write_text(
            json.dumps({"formal": {self.config: "different"}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "frozen fingerprint"):
            agy.load_records(self.config, self.base)

    def test_entire_computation_matches_unmodified_upstream(self):
        spec = importlib.util.spec_from_file_location("_spread_test_reference", agy.spread.__file__)
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        reference.HERE = self.base
        reference.CONFIGS = (self.suffix,)
        expected = reference.compute()
        loader = agy.load_records
        with patch.object(agy.spread, "CONFIGS", (self.config,)), patch.object(
                agy.spread, "load_records", lambda config: loader(config, self.base)):
            actual = agy.compute()
        actual_data = actual["configs"][self.config]
        expected_data = expected["configs"][self.suffix]
        for field in ("parsed_records", "registered_units", "excluded_records", "malformed_lines"):
            actual_data["audit"].pop(field)
        self.assertEqual(actual_data, expected_data)
        self.assertEqual(actual["step2"]["configs"][self.config], expected["step2"]["configs"][self.suffix])
        for field in ("B", "seed", "stored_sd_absolute_tolerance"):
            self.assertEqual(actual[field], expected[field])

    def test_summary_percentages(self):
        def summary(x):
            return {"point": x}
        data = dict(cells={"prior:-": {"sd": summary(10)},
                           "stated:S": {"sd": summary(6)}, "stated:W": {"sd": summary(8)}},
                    contrasts={"change:stated:S": summary(-4), "change:stated:W": summary(-2),
                               "reported_minus_stated:pooled": summary(1.4), "spearman": summary(0.5)})
        row = agy.seven_config_rows({"configs": {"new": data}}, {"configs": {"old": data}})["new"]
        self.assertEqual(row["stated_change_pct"], -30)
        self.assertAlmostEqual(row["reported_minus_stated_pct"], 20)


if __name__ == "__main__":
    unittest.main()
