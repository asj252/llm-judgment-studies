"""smoke_report.py 的测试（PLAN v0.5 第 1、4 节；c 第二轮 S1；c 第三轮 N-S2、Q1）。用法：python -I -X utf8 -B test_smoke_report.py"""
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402
import smoke_report as SR  # noqa: E402

PLANNED = [run.unit_id(u) for i in range(30) for u in run.base_units("k%02d" % i)]     # 300 个计划 unit


def rec(unit, first=True, final="ok", err="n_estimates_4", truncated=False, state="ok"):
    k, pres, ut, ask, rnd = unit.split("|")
    a0 = {"state": state, "truncated": truncated, "parsed": first and not truncated and state == "ok",
          "parse": {"error": None if first else err}}
    a1 = {"state": "ok", "truncated": False, "parsed": final == "ok", "parse": {"error": None if final == "ok" else err}}
    return {"unit": unit, "key": k, "pres": pres, "utype": ut, "ask": ask, "round": rnd, "status": final,
            "attempts": [a0] if first else [a0, a1]}


def good_all():
    return {cfg: [rec(u) for u in PLANNED] for cfg in run.CONFIGS}


class Summary(unittest.TestCase):
    def test_parse_rates_and_weight_compliance_are_separate(self):
        units = ["k|prior|-|multi|r0", "k|stated|S|multi|r0", "k|stated|W|multi|r0"]
        rows = [rec(u) for u in units]
        for r, compliant in zip(rows, (True, False, True)):
            r["attempts"][0]["parse"].update(weight_sum_in_tolerance=compliant)
            r["attempts"][0]["parse_v1"] = {"ok": compliant}
        rows[2] = rec(units[2], first=False)
        rows[2]["attempts"][0]["parse_v1"] = {"ok": False}
        rows[2]["attempts"][1].update(parse_v1={"ok": True}, parse={"weight_sum_in_tolerance": True})
        s, _ = SR.smoke_summary({"olmo2": rows}, units)
        cells = s["configs"]["olmo2"]["cells"]
        c = cells["multi|stated|S"]["parsing_first"]
        self.assertEqual((c["v2_parseable_rate"], c["v1_parseable_rate"], c["weight_sum_compliance_rate"]), (1, 0, 0))
        w = cells["multi|stated|W"]
        self.assertEqual(w["parsing_first"]["v2_parseable_rate"], 0)
        self.assertEqual(w["parsing_after_retry"]["v2_parseable_rate"], 1)
        self.assertEqual(w["parsing_after_retry"]["v1_parseable_rate"], 1)
        self.assertIn("multi|prior|-", cells)

    def test_v1_reparses_same_raw_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for cfg in ("olmo2", "codex"):
                r = rec("k|prior|-|direct|r0")
                raw = base / "raw" / ("run_dev_" + cfg)
                raw.mkdir(parents=True)
                tag = run._safe(r["unit"]) + "__" + cfg + "__a0"
                text = "### Probability:\nProbability: 20%"
                suffix = ".last.txt" if cfg == "codex" else ".json"
                (raw / (tag + suffix)).write_text(text if cfg == "codex" else json.dumps({"text": text}), encoding="utf-8")
                result = SR.add_v1_comparison([r], cfg, base)[0]
                self.assertEqual(result["attempts"][0]["parse_v1"]["error"], "multiple_fields")
                self.assertNotIn("parse_v1", r["attempts"][0])
            missing = SR._stats({r["unit"]}, [r])["parsing_first"]
            self.assertIsNone(missing["v1_parseable_rate"])

    def test_all_good_passes(self):
        s, status = SR.smoke_summary(good_all(), PLANNED)
        self.assertEqual(status, SR.STATUS_PASS)
        o = s["configs"]["olmo2"]["overall"]
        self.assertEqual((o["first_success_rate_attempted"], o["first_success_coverage_planned"],
                          o["missing_rate_planned"]), (1.0, 1.0, 0.0))
        self.assertEqual(len(s["configs"]["olmo2"]["cells"]), 10)

    def test_c_round3_partial_counterexample(self):
        """c 第三轮 N-S2 反例：只有 10 个首次成功记录、计划 300 个 → 不得判通过；两种首次成功率分开报。"""
        s, status = SR.smoke_summary({"olmo2": [rec(u) for u in PLANNED[:10]]}, PLANNED)
        self.assertEqual(status, SR.STATUS_INCOMPLETE)
        o = s["configs"]["olmo2"]["overall"]
        self.assertEqual((o["first_success_rate_attempted"], o["n_not_attempted"]), (1.0, 290))
        self.assertAlmostEqual(o["first_success_coverage_planned"], 10 / 300)
        self.assertTrue(any("qwen3-off 未跑" in x for x in s["incomplete_reasons"]))
        self.assertTrue(any("olmo2 未尝试 290/300" in x for x in s["incomplete_reasons"]))

    def test_missing_config_not_pass(self):
        recs = good_all()
        del recs["codex"]
        self.assertEqual(SR.smoke_summary(recs, PLANNED)[1], SR.STATUS_INCOMPLETE)

    def test_two_percent_rule(self):
        """PLAN v0.5：每个配置分别算，分母＝该配置全部计划 unit（300），分子＝重试后仍缺的 unit；> 2% 停，并列条件格。"""
        recs = good_all()
        multi = [u for u in PLANNED if "|multi|" in u]
        bad = set(multi[:7])
        recs["olmo2"] = [rec(u, first=False, final="missing", err="missing_weight") if u in bad
                         else rec(u) for u in PLANNED]                   # 7/300 = 2.33%
        s, status = SR.smoke_summary(recs, PLANNED)
        self.assertEqual(status, SR.STATUS_STOP)
        reason = [x for x in s["stop_reasons"] if x.startswith("olmo2")]
        self.assertEqual(len(reason), 1)
        self.assertIn("7/300", reason[0])
        self.assertIn("> 2%", reason[0])
        self.assertIn("multi|", reason[0])                                # 列出条件格
        c = s["configs"]["olmo2"]["cells"]
        self.assertEqual(sum(x["n_missing_after_retry"] for x in c.values()), 7)
        self.assertAlmostEqual(s["configs"]["olmo2"]["overall"]["first_success_rate_attempted"], 293 / 300)
        recs["olmo2"] = [rec(u, first=False, final="missing") if u in set(multi[:6]) else rec(u) for u in PLANNED]
        self.assertEqual(SR.smoke_summary(recs, PLANNED)[1], SR.STATUS_PASS)   # 6/300 = 2.0%：不超过

    def test_retry_success_does_not_count_as_missing(self):
        recs = good_all()
        recs["codex"] = [rec(u, first=False, final="ok") if i < 20 else rec(u) for i, u in enumerate(PLANNED)]
        s, status = SR.smoke_summary(recs, PLANNED)
        o = s["configs"]["codex"]["overall"]
        self.assertEqual((o["n_missing_after_retry"], o["retry_success_rate"]), (0, 1.0))
        self.assertEqual(status, SR.STATUS_PASS)                          # 280/300 = 93% ≥ 90%

    def test_ninety_percent_rule(self):
        recs = good_all()
        recs["qwen3-off"] = [rec(u, first=False, final="ok", truncated=True) if i < 31 else rec(u)
                            for i, u in enumerate(PLANNED)]               # 269/300 < 90%
        s, status = SR.smoke_summary(recs, PLANNED)
        self.assertEqual(status, SR.STATUS_STOP)
        self.assertTrue(any(x.startswith("qwen3-off：已尝试 unit 的首次成功率") for x in s["stop_reasons"]))
        self.assertEqual(s["configs"]["qwen3-off"]["overall"]["errors"], {"truncated": 31})
        recs["qwen3-off"] = [rec(u, first=False, final="ok") if i < 30 else rec(u) for i, u in enumerate(PLANNED)]
        self.assertEqual(SR.smoke_summary(recs, PLANNED)[1], SR.STATUS_PASS)   # 恰 90%：不停

    def test_extra_units_ignored(self):
        recs = good_all()
        recs["olmo2"].append(rec("zz|prior|-|direct|r0", first=False, final="missing"))
        s, status = SR.smoke_summary(recs, PLANNED)
        self.assertEqual((status, s["configs"]["olmo2"]["n_extra_units_ignored"]), (SR.STATUS_PASS, 1))

    def test_codex_void_counts_as_first_failure(self):
        r = rec(PLANNED[0], first=False, state="contaminated_suspected")
        self.assertFalse(SR.first_ok(r))
        self.assertEqual(SR.error_type(r["attempts"][0]), "state:contaminated_suspected")


if __name__ == "__main__":
    unittest.main()
