"""run.py 的替身测试（不调用任何模型）。用法：python -I -X utf8 -B test_run.py

来源：改写自 ../suppression/test_run.py。覆盖：unit 组成（每对 10 个；正式集重复子集再加 10 个）、调度（交错、固定种子、
可复现）、题面渲染接线、重试（解析失败、截断、多估计解析失败）、codex 污染作废重采、停止（额度不作废会话、检查失效作废会话）、
续跑（跳过已完成、指纹不符拒绝、未收尾会话作废）、正式入口准入、实验指纹（共同材料各项都会改变指纹）、真实清单与题面的接线。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prompts  # noqa: E402
import run  # noqa: E402

SPLIT = {"repeat_subset": ["img1.jpg#0r1e"]}
MULTI_OK = "\n".join("Estimate %d: %d%% | Weight: 0.2" % (k, 10 * k) for k in range(1, 6))


def make_items(use="formal"):
    base = {"P": "A man rides a bike", "H": "A man is outdoors.", "U_S": "The road is wet from rain.",
            "U_W": "He is on a stationary bike in a gym", "S_id": "dev:1", "W_id": "test:2", "use": use,
            "formal_block": 'A' if use == 'formal' else None}
    return {"img1.jpg#0r1e": dict(base, key="img1.jpg#0r1e", cluster="img1.jpg"),
            "img2.jpg#3r1n": dict(base, key="img2.jpg#3r1n", cluster="img2.jpg"),
            "img3.jpg#1r1c": dict(base, key="img3.jpg#1r1c", cluster="img3.jpg")}


class Stub:
    """script：{(unit 片段, 尝试序号): 响应}；默认合格回答（direct 50%，multi 聚合 30%）。"""

    def __init__(self, script=None, default_value=50):
        self.script = script or {}
        self.calls = []
        self.default_value = default_value

    def attempt(self, ask, prompt, tag, seed):
        self.calls.append((ask, tag, seed, prompt))
        for (frag, k), resp in self.script.items():
            if frag in tag and tag.endswith("__a%d" % k):
                return resp(ask) if callable(resp) else resp
        if ask == "multi":
            return {"text": MULTI_OK, "truncated": False, "final": {"state": "ok"}}
        return {"text": "Probability: %d%%" % self.default_value, "truncated": False, "final": {"state": "ok"}}


def resp(text=None, truncated=False, state="ok", stop=False, invalidate=False, resample=False):
    return {"text": text, "truncated": truncated,
            "final": {"state": state, "stop": stop, "invalidate_session": invalidate, "resample": resample}}


class Units(unittest.TestCase):
    def test_ten_units_per_pair(self):
        """PLAN 第 3 节：每对每配置 先验 2 ＋ 后验 2 类型 × 2 呈现 × 2 问法 ＝ 10。"""
        us = run.units_for(make_items("dev")["img2.jpg#3r1n"], "dev", SPLIT)
        self.assertEqual(len(us), 10)
        self.assertEqual(len(set(us)), 10)
        self.assertEqual(sum(u[1] == "prior" for u in us), 2)
        self.assertEqual({(u[1], u[2]) for u in us if u[1] != "prior"},
                         {(p, t) for p in ("stated", "reported") for t in ("S", "W")})
        self.assertEqual({u[4] for u in us}, {"r0"})

    def test_repeat_subset_only_formal(self):
        us = run.units_for(make_items()["img1.jpg#0r1e"], "formal", SPLIT)
        self.assertEqual(len(us), 20)
        self.assertEqual(sum(u[4] == "r1" for u in us), 10)
        self.assertEqual(len(run.units_for(make_items("dev")["img1.jpg#0r1e"], "dev", SPLIT)), 10)
        self.assertEqual(len(run.units_for(make_items()["img2.jpg#3r1n"], "formal", SPLIT)), 10)

    def test_interleaved_and_deterministic(self):
        items = make_items()
        a = run.make_schedule(items, "formal", "qwen3-off", SPLIT)
        self.assertEqual(a, run.make_schedule(items, "formal", "qwen3-off", SPLIT))
        keys = [u[0] for u in a]
        blocks = [k for i, k in enumerate(keys) if i == 0 or keys[i - 1] != k]
        self.assertEqual(len(blocks), 3)
        self.assertNotEqual(a, run.make_schedule(items, "formal", "olmo2", SPLIT))
        self.assertEqual(len(a), 40)

    def test_call_seed(self):
        u = ("k", "stated", "S", "direct", "r0")
        self.assertNotEqual(run.call_seed("olmo2", u, 0, "dev"), run.call_seed("olmo2", u, 1, "dev"))
        self.assertNotEqual(run.call_seed("olmo2", u, 0, "dev"), run.call_seed("olmo2", u[:4] + ("r1",), 0, "dev"))
        self.assertEqual(run.call_seed("olmo2", u, 0, "dev"), run.call_seed("olmo2", u, 0, "dev"))

    def test_render_wiring(self):
        it = make_items()["img1.jpg#0r1e"]
        p0 = run.render_unit(it, ("k", "prior", "-", "direct", "r0"))
        ps = run.render_unit(it, ("k", "stated", "S", "direct", "r0"))
        pr = run.render_unit(it, ("k", "reported", "W", "multi", "r0"))
        rep = run.render_unit(it, ("k", "stated", "S", "direct", "r1"))
        self.assertEqual(ps, rep)                                      # 重复轮同一提示
        self.assertNotIn("learned", p0)
        self.assertNotIn("Someone said", p0)
        self.assertIn("Here is something else you learned: The road is wet from rain.", ps)
        self.assertIn("Someone said that he is on a stationary bike in a gym.", pr)
        self.assertIn("Estimate 5: NN% | Weight: W", pr)
        self.assertIn("Probability: NN%", ps)
        self.assertEqual(run.update_id(it, ("k", "reported", "W", "multi", "r0")), "test:2")
        self.assertIsNone(run.update_id(it, ("k", "prior", "-", "direct", "r0")))


class Retry(unittest.TestCase):
    def setUp(self):
        self.it = make_items()["img1.jpg#0r1e"]
        self.u = ("img1.jpg#0r1e", "stated", "S", "direct", "r0")

    def rec(self, script, u=None):
        return run.run_unit("qwen3-off", "formal", self.it, u or self.u, Stub(script), None)

    def test_ok_first(self):
        r = self.rec({})
        self.assertEqual((r["status"], r["result"]["value"], r["n_attempts"]), ("ok", 50.0, 1))
        self.assertEqual((r["pres"], r["utype"], r["ask"], r["round"], r["update_id"]),
                         ("stated", "S", "direct", "r0", "dev:1"))

    def test_parse_fail_then_ok(self):
        r = self.rec({("stated_S_direct", 0): resp("Probability: 0.7")})
        self.assertEqual((r["status"], r["n_attempts"]), ("ok", 2))
        self.assertEqual(r["attempts"][0]["parse"]["error"], "no_percent")

    def test_parse_fail_twice_missing(self):
        r = self.rec({("stated_S_direct", 0): resp("nothing"), ("stated_S_direct", 1): resp("Probability: 101%")})
        self.assertEqual((r["status"], r["result"], r["n_attempts"]), ("missing", None, 2))

    def test_truncated_then_ok(self):
        r = self.rec({("stated_S_direct", 0): resp("Probability: 80%", truncated=True)})
        self.assertEqual((r["status"], r["n_attempts"]), ("ok", 2))
        self.assertEqual(r["attempts"][0]["parse"]["error"], "truncated")

    def test_multi_ok_and_fail(self):
        u = ("img1.jpg#0r1e", "reported", "W", "multi", "r0")
        r = self.rec({}, u)
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["result"]["value"], 30.0)
        self.assertEqual(r["result"]["estimates"], [10.0, 20.0, 30.0, 40.0, 50.0])
        bad = MULTI_OK.replace("Weight: 0.2\nEstimate 5", "Weight: absent\nEstimate 5")
        r = self.rec({("reported_W_multi", 0): resp(bad), ("reported_W_multi", 1): resp(MULTI_OK, truncated=True)}, u)
        self.assertEqual((r["status"], r["n_attempts"]), ("missing", 2))
        self.assertEqual(r["attempts"][0]["parse"]["error"], "weight_no_number")

    def test_disconnect_retry_limit_and_reset(self):
        d = resp("Probability: 99%", state="disconnect", resample=True)
        r = self.rec({("stated_S_direct",0):d, ("stated_S_direct",1):d})
        self.assertEqual((r["n_attempts"],r["result"]["value"]), (3,50))
        self.assertTrue(all(a["parsed"] is None for a in r["attempts"][:2]))
        with self.assertRaises(run.Stop) as cm:
            self.rec({("stated_S_direct",i):d for i in range(3)})
        self.assertFalse(cm.exception.invalidate)
        self.assertIn("3 consecutive",str(cm.exception))
        r = self.rec({("stated_S_direct",0):d, ("stated_S_direct",1):resp("no field"),
                      ("stated_S_direct",2):d, ("stated_S_direct",3):d})
        self.assertEqual((r["status"],r["n_attempts"]), ("ok",5))

    def test_parser_version_in_fingerprint_rules(self):
        self.assertEqual(run.PARSE_RULES["version"],2)
        self.assertEqual(run.CONFIGS,("qwen3-off","olmo2","codex"))

    def test_attempt_seeds_recorded(self):
        r = self.rec({("stated_S_direct", 0): resp("x")})
        self.assertNotEqual(r["attempts"][0]["seed"], r["attempts"][1]["seed"])

    def test_codex_void_then_ok(self):
        r = self.rec({("stated_S_direct", 0): resp("Probability: 10%", state="contaminated_confirmed", resample=True)})
        self.assertEqual((r["status"], r["result"]["value"], r["n_attempts"]), ("ok", 50.0, 2))

    def test_codex_void_twice(self):
        v = resp("Probability: 10%", state="contaminated_suspected", resample=True)
        r = self.rec({("stated_S_direct", 0): v, ("stated_S_direct", 1): v})
        self.assertEqual((r["status"], r["result"]), ("tool_contaminated", None))

    def test_void_and_parse_retries_independent(self):
        r = self.rec({("stated_S_direct", 0): resp("x", state="contaminated_confirmed", resample=True),
                      ("stated_S_direct", 1): resp("no field")})
        self.assertEqual((r["status"], r["n_attempts"]), ("ok", 3))

    def test_parse_retry_goes_through_inclusion_again(self):
        with self.assertRaises(run.Stop):
            self.rec({("stated_S_direct", 0): resp("no field"),
                      ("stated_S_direct", 1): resp("x", state="quota_stop", stop=True)})


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.res, self.meta = d / "res.jsonl", d / "meta.json"
        self.dres, self.dmeta = d / "dres.jsonl", d / "dmeta.json"
        self.items = make_items()
        self.fp, self.fid = {"a": "1"}, "FID"

    def tearDown(self):
        self.tmp.cleanup()

    def ex(self, subj, cfg="qwen3-off", which="formal", fid=None, fp=None, dev_units=()):
        logs = []
        return run.execute(which, cfg, self.items, SPLIT, subj, fp or self.fp, fid or self.fid, self.res,
                           self.meta, None, log=logs.append, dev_meta_path=self.dmeta,
                           dev_results_path=self.dres, dev_expected_units=dev_units)

    def dev_ok(self):
        run.save_json(self.dmeta, {"sessions": [{"session_id": "d", "fingerprint_id": self.fid, "fingerprint": self.fp,
                                                 "closed_ok": True, "invalid": False, "status": "finished"}]})
        self.dres.write_text(json.dumps({"unit": "u1", "session_id": "d", "fingerprint_id": self.fid}) + "\n",
                             encoding="utf-8")

    def test_formal_refused_without_dev(self):
        with self.assertRaises(run.Stop):
            self.ex(Stub(), dev_units={"u1"})

    def test_formal_refused_with_incomplete_dev(self):
        self.dev_ok()
        with self.assertRaises(run.Stop):
            self.ex(Stub(), dev_units={"u1", "u2"})

    def test_full_run_and_resume_skips(self):
        self.dev_ok()
        code, sess = self.ex(Stub(), dev_units={"u1"})
        self.assertEqual(code, 0)
        recs = run.load_records(self.res)
        self.assertEqual(len(recs), 40)
        self.assertEqual({r["status"] for r in recs}, {"ok"})
        s2 = Stub()
        code, _ = self.ex(s2, dev_units={"u1"})
        self.assertEqual((code, len(s2.calls)), (0, 0))

    def test_fingerprint_mismatch_refused_before_calls(self):
        self.dev_ok()
        self.ex(Stub(), dev_units={"u1"})
        s = Stub()
        with self.assertRaises(run.Stop):
            self.ex(s, fid="OTHER", fp={"a": "2"}, dev_units={"u1"})
        self.assertEqual(s.calls, [])

    def test_quota_stop_keeps_session_and_resumes(self):
        self.dev_ok()
        sched = run.make_schedule(self.items, "formal", "codex", SPLIT)
        third = run._safe(run.unit_id(sched[2]))
        code, sess = self.ex(Stub({(third, 0): resp("x", state="quota_stop", stop=True)}), cfg="codex",
                             dev_units={"u1"})
        self.assertEqual(code, 3)
        self.assertFalse(sess["invalid"])
        self.assertEqual(len(run.load_records(self.res)), 2)
        s2 = Stub()
        code, _ = self.ex(s2, cfg="codex", dev_units={"u1"})
        self.assertEqual(code, 0)
        self.assertEqual(len(s2.calls), len(sched) - 2)

    def test_check_failed_invalidates_and_requeues(self):
        self.dev_ok()
        sched = run.make_schedule(self.items, "formal", "codex", SPLIT)
        third = run._safe(run.unit_id(sched[2]))
        code, sess = self.ex(Stub({(third, 0): resp("x", state="check_failed", stop=True, invalidate=True)}),
                             cfg="codex", dev_units={"u1"})
        self.assertTrue(sess["invalid"])
        s2 = Stub()
        self.ex(s2, cfg="codex", dev_units={"u1"})
        self.assertEqual(len(s2.calls), len(sched))

    def test_three_disconnects_keep_session_and_completed_units(self):
        self.dev_ok()
        sched = run.make_schedule(self.items,"formal","codex",SPLIT)
        third = run._safe(run.unit_id(sched[2]))
        d = resp("Probability: 99%",state="disconnect",resample=True)
        code,sess = self.ex(Stub({(third,i):d for i in range(3)}),cfg="codex",dev_units={"u1"})
        self.assertEqual(code,3)
        self.assertFalse(sess["invalid"])
        self.assertTrue(sess["closed_ok"])
        self.assertEqual(len(run.load_records(self.res)),2)
        s = Stub()
        self.assertEqual(self.ex(s,cfg="codex",dev_units={"u1"})[0],0)
        self.assertEqual(len(s.calls),len(sched)-2)

    def test_unfinished_session_invalid(self):
        self.dev_ok()
        for cfg in ("codex", "olmo2"):
            run.save_json(self.meta, {"sessions": [{"session_id": "old", "fingerprint_id": self.fid,
                                                    "fingerprint": self.fp, "status": "running", "invalid": False}]})
            first = run.unit_id(run.make_schedule(self.items, "formal", cfg, SPLIT)[0])
            self.res.write_text(json.dumps({"unit": first, "session_id": "old", "fingerprint_id": self.fid}) + "\n",
                                encoding="utf-8")
            s = Stub()
            self.ex(s, cfg=cfg, dev_units={"u1"})
            self.assertTrue(run.load_json(self.meta, {})["sessions"][0]["invalid"], cfg)
            self.assertEqual(len(s.calls), len(run.make_schedule(self.items, "formal", cfg, SPLIT)), cfg)
            self.res.unlink()

    def test_stray_records_refused(self):
        self.dev_ok()
        self.res.write_text(json.dumps({"unit": "x", "session_id": "ghost", "fingerprint_id": self.fid}) + "\n",
                            encoding="utf-8")
        with self.assertRaises(run.Stop):
            self.ex(Stub(), dev_units={"u1"})


class Fingerprint(unittest.TestCase):
    """PLAN 第 6 节；c 第一轮建议 17：共同材料指纹含题面、选句 ID、转述模板、问法与解析。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "dnli"        # ../vs-pilot 落在临时目录内
        (self.d / "raw").mkdir(parents=True)
        for rel in list(run.CODE_FILES) + [run.ITEMS_TEXT, "local_subject.py"]:
            (self.d / rel).write_text(rel, encoding="utf-8")
        self.items = make_items()

    def tearDown(self):
        self.tmp.cleanup()

    def fp(self, items=None, meta=None, cfg="olmo2"):
        return run.fingerprint(self.d, cfg, meta or {"commit": "c1"}, items or self.items, SPLIT)

    def test_fields_and_sensitivity(self):
        fp, fid = self.fp()
        for k in ("templates", "parse_rules", "materials_digest", run.ITEMS_TEXT, run.SPLIT_FILE, "prompts.py",
                  "parse.py", "local_subject.py"):
            self.assertIn(k, fp)
        self.assertEqual(fp["n_units_all"], 3 * 10 + 10)          # 三对 × 10 ＋ 重复子集 1 对 × 10
        self.assertNotEqual(fid, self.fp(meta={"commit": "c2"})[1])
        changed = {k: dict(v) for k, v in self.items.items()}
        changed["img2.jpg#3r1n"]["U_S"] = "The road is dry."      # 改一句更新句
        self.assertNotEqual(fp["materials_digest"], self.fp(changed)[0]["materials_digest"])
        changed = {k: dict(v) for k, v in self.items.items()}
        changed["img2.jpg#3r1n"]["S_id"] = "dev:99"               # 只改选句 ID
        self.assertNotEqual(fp["materials_digest"], self.fp(changed)[0]["materials_digest"])

    def test_template_change_changes_fingerprint(self):
        fp, fid = self.fp()
        old = prompts.FRAME_REPORTED
        try:
            prompts.FRAME_REPORTED = "I heard someone say that {u}"
            fp2, fid2 = self.fp()
        finally:
            prompts.FRAME_REPORTED = old
        self.assertNotEqual(fp["templates"], fp2["templates"])
        self.assertNotEqual(fp["materials_digest"], fp2["materials_digest"])
        self.assertNotEqual(fid, fid2)

    def test_digest_independent_of_config(self):
        a, _ = self.fp(cfg="olmo2")
        (self.d / "codex_subject.py").write_text("x", encoding="utf-8")
        (self.d.parent / "vs-pilot").mkdir()
        (self.d.parent / "vs-pilot" / "subject.py").write_text("y", encoding="utf-8")
        b, _ = self.fp(cfg="codex")
        for k in ("templates", "parse_rules", "materials_digest", run.ITEMS_TEXT, run.SPLIT_FILE):
            self.assertEqual(a[k], b[k])


class Adapters(unittest.TestCase):
    """适配器接线（不载入模型、不调用 codex）：用替身模块顶替 local_subject 与 codex_subject。"""

    def test_local_adapter(self):
        import types
        calls = []

        class FakeLS:
            def __init__(self, model_key, **kw):
                self.model_key = model_key

            def generate(self, prompt, thinking, seed):
                calls.append((self.model_key, thinking, seed))
                return {"text": "Probability: 42%", "truncated": False, "seconds": 1.0, "n_out_tokens": 9,
                        "n_thinking_tokens": 0, "n_prompt_tokens": 120, "n_predict": 8192, "stop_type": "eos"}
        fake = types.ModuleType("local_subject")
        fake.CONFIGS = {"qwen3-off": ("qwen3-8b", False)}
        fake.LocalSubject = FakeLS
        old = sys.modules.get("local_subject")
        sys.modules["local_subject"] = fake
        try:
            with tempfile.TemporaryDirectory() as d:
                ad = run.LocalAdapter("qwen3-off", d)
                it = make_items()["img1.jpg#0r1e"]
                r = run.run_unit("qwen3-off", "dev", it, ("img1.jpg#0r1e", "reported", "S", "direct", "r0"), ad, d)
                self.assertEqual(len(list(Path(d).glob("*.json"))), 1)       # 原文写进 rawdir
        finally:
            if old is None:
                sys.modules.pop("local_subject", None)
            else:
                sys.modules["local_subject"] = old
        self.assertEqual((r["status"], r["result"]["value"]), ("ok", 42.0))
        self.assertEqual(calls[0][:2], ("qwen3-8b", False))
        self.assertEqual(r["attempts"][0]["meta"]["n_predict"], 8192)

    def test_codex_adapter(self):
        import types

        class FakeCS:
            def __init__(self, rawdir, workroot):
                self.frozen = {"instruction_fingerprint": "f", "model_entry": {"x": 1}}

            def call(self, prompt, tag):
                return {"text": "\n".join("Estimate %d: 50%% | Weight: 0.2" % k for k in range(1, 6)),
                        "final": {"state": "ok", "stop": False, "resample": False}, "seconds": 3.0,
                        "check": {"usage": {"input_tokens": 9000}, "sampling_requests": 1}}
        fake = types.ModuleType("codex_subject")
        fake.CodexSubject = FakeCS
        old = sys.modules.get("codex_subject")
        sys.modules["codex_subject"] = fake
        try:
            ad = run.CodexAdapter("raw", "work")
            self.assertNotIn("model_entry", ad.meta())
            r = run.run_unit("codex", "dev", make_items()["img1.jpg#0r1e"],
                             ("img1.jpg#0r1e", "prior", "-", "multi", "r0"), ad, None)
        finally:
            if old is None:
                sys.modules.pop("codex_subject", None)
            else:
                sys.modules["codex_subject"] = old
        self.assertEqual((r["status"], r["result"]["value"]), ("ok", 50.0))
        self.assertEqual(r["attempts"][0]["meta"]["usage"], {"input_tokens": 9000})


class RealMaterials(unittest.TestCase):
    """真实清单与题面（raw/items_text.json 本地有才跑）：接线、单位总数、调度覆盖。"""

    @unittest.skipUnless((HERE / run.ITEMS_TEXT).is_file(), "raw/items_text.json not present")
    def test_real_entry(self):
        dev, split, all_items = run.load_items("dev")
        formal, _, _ = run.load_items("formal")
        self.assertEqual((len(dev), len(formal), len(all_items)), (30, 240, 270))
        for which, items in (("dev", dev), ("formal", formal)):
            for cfg in run.CONFIGS:
                n = 300 if which == 'dev' else (1400 if cfg == 'codex' else 2600)
                sched = run.make_schedule(items, which, cfg, split)
                self.assertEqual(len(sched), n)
                self.assertEqual(len(set(sched)), n)
        _, n_all = run.materials_digest(all_items, split)
        self.assertEqual(n_all, 300 + 2600)
        for it in all_items.values():
            for u in run.units_for(it, it["use"], split):
                p = run.render_unit(it, u)
                self.assertTrue(p.startswith("Here is a situation: "))
                self.assertTrue(p.endswith(prompts.NO_TOOLS))
        # 真实文件上的实验指纹：本地与 codex 的共同材料相同，配置部分不同
        fl, idl = run.fingerprint(HERE, "olmo2", {"stand_in": True}, all_items, split)
        fc, idc = run.fingerprint(HERE, "codex", {"stand_in": True}, all_items, split)
        for k in ("templates", "parse_rules", "materials_digest", run.ITEMS_TEXT, run.SPLIT_FILE, "prompts.py",
                  "parse.py", "PLAN.md", "run.py"):
            self.assertEqual(fl[k], fc[k], k)
        self.assertIn("local_subject.py", fl)
        self.assertIn("../vs-pilot/subject.py", fc)
        self.assertNotEqual(idl, idc)


if __name__ == "__main__":
    unittest.main()
