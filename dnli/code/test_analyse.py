"""analyse.py（唯一分析入口）的测试，含 run.py → analyse.py 的替身端到端。用法：python -I -X utf8 -B test_analyse.py

覆盖：会话与冻结指纹筛选（复制自 ../suppression/test_analyse.py 并改 unit 形状）、替身端到端（run.execute 写记录与会话 →
freeze → analyse；dev 与正式；三个配置；家族成员与水平；重复轮）、材料绑定（清单、题面、模板、记录的 update_id、重复轮、
跨配置共同材料）、预算报告。
"""
import json
import random
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyse as AN  # noqa: E402
import analysis as A  # noqa: E402
import prompts  # noqa: E402
import run  # noqa: E402

VALUES = {("prior", "-"): 50, ("stated", "S"): 70, ("stated", "W"): 30, ("reported", "S"): 60, ("reported", "W"): 40}


def multi_text(center):
    ps = [center - 10, center - 5, center, center + 5, center + 10]
    return "\n".join("Estimate %d: %.1f%% | Weight: 0.2" % (i + 1, p) for i, p in enumerate(ps))


class ValueStub:
    """按 unit 给值：直接问法 VALUES ＋ 题内噪声；多估计问法的聚合值向 50 收缩一半（H4b 预期为负）。"""

    def __init__(self, cfg, seed=0):
        self.cfg, self.rng = cfg, random.Random(seed)

    def attempt(self, ask, prompt, tag, seed):
        uid = tag.split("__")[0]
        for (pres, ut), v in VALUES.items():
            if "_%s_%s_%s_" % (pres, ut, ask) in uid + "_":
                break
        else:
            raise AssertionError(uid)
        v = v + self.rng.uniform(-2, 2)
        if ask == "multi":
            return {"text": multi_text(50 + (v - 50) / 2), "truncated": False, "final": {"state": "ok"},
                    "meta": {"n_prompt_tokens": 200, "n_predict": 8192}}
        return {"text": "Probability: %.1f%%" % v, "truncated": False, "final": {"state": "ok"},
                "meta": {"n_prompt_tokens": 150, "n_predict": 8192}}


def write_base(base, n_dev=6, n_formal=10, n_rep=3):
    base.mkdir(parents=True, exist_ok=True)
    (base / "raw").mkdir(exist_ok=True)
    items, text = [], {}
    for j in range(n_dev + n_formal):
        key = "img%02d.jpg#0r1n" % j
        use = "dev" if j < n_dev else "formal"
        items.append({"key": key, "cluster": "img%02d.jpg" % (j // 2 if use == "formal" else j), "use": use,
                      "formal_block": 'A' if use == 'formal' else None,
                      "source_split": "dev" if j % 2 == 0 else "test",
                      "S": {"id": "dev:%d" % (2 * j)}, "W": {"id": "dev:%d" % (2 * j + 1)}})
        text[key] = {"P": "Situation %d" % j, "H": "A statement %d" % j, "U_S": "The strengthener %d" % j,
                     "U_W": "The weakener %d" % j, "S_id": "dev:%d" % (2 * j), "W_id": "dev:%d" % (2 * j + 1)}
    split = {"items": items, "repeat_subset": [it["key"] for it in items if it["use"] == "formal"][:n_rep]}
    run.save_json(base / run.SPLIT_FILE, split)
    run.save_json(base / run.ITEMS_TEXT, text)
    for f in ("PLAN.md", "prompts.py", "parse.py", "run.py", "local_subject.py", "codex_subject.py"):
        (base / f).write_text("# stand-in " + f, encoding="utf-8")
    (base.parent / "vs-pilot").mkdir(exist_ok=True)
    (base.parent / "vs-pilot" / "subject.py").write_text("# stand-in", encoding="utf-8")


def run_config(base, which, cfg, subj=None, log=None):
    items, split, all_items = run.load_items(which, base)
    fp, fid = run.fingerprint(base, cfg, {"cfg": cfg}, all_items, split)
    dev_units = set()
    if which == "formal":
        dev_items, _, _ = run.load_items("dev", base)
        dev_units = {run.unit_id(u) for u in run.make_schedule(dev_items, "dev", cfg, split)}
    return run.execute(which, cfg, items, split, subj or ValueStub(cfg), fp, fid,
                       base / ("results_%s_%s.jsonl" % (which, cfg)), base / ("run_meta_%s_%s.json" % (which, cfg)),
                       None, log=(log or (lambda *_: None)), dev_meta_path=base / ("run_meta_dev_%s.json" % cfg),
                       dev_results_path=base / ("results_dev_%s.jsonl" % cfg), dev_expected_units=dev_units)


class EndToEnd(unittest.TestCase):
    """替身测通：run.execute 写出的记录与会话，经 freeze 与 analyse 走完全部路径（任务书第 5、6 步）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name) / "dnli"
        write_base(cls.base)
        cls.fz = cls.base / "fz.json"
        for which in ("dev", "formal"):
            for cfg in run.CONFIGS:
                code, sess = run_config(cls.base, which, cfg)
                assert code == 0, sess
                AN.freeze(which, cfg, base=cls.base, freeze_path=cls.fz, B=300)    # 测试用较小的冻结 B
        cls.dev = AN.analyse("dev", base=cls.base, freeze_path=cls.fz)
        cls.formal = AN.analyse("formal", base=cls.base, freeze_path=cls.fz)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self, out, fam):
        return {r["test"]: r for r in out["families"][fam]["rows"]}

    def test_counts(self):
        self.assertEqual(self.dev["filter"]["olmo2"]["kept"], 6 * 10)
        self.assertEqual(self.formal["filter"]["olmo2"]["kept"], 10 * 10 + 3 * 10)
        self.assertEqual(self.formal["n_repeat"], 3)
        self.assertEqual(self.formal["binding"]["records_checked"], 3 * 130)

    def test_families_and_levels(self):
        fams = self.dev["families"]
        self.assertEqual(sorted(fams), ["config:codex", "config:olmo2", "config:qwen3-off"])
        for cfg in run.CONFIGS:
            rows = fams["config:" + cfg]["rows"]
            self.assertEqual([r["test"] for r in rows], ["H1", "H2", "H4a", "H4b"])
            self.assertEqual(sorted(round(r["alpha_adj"], 6) for r in rows),
                             sorted(round(0.05 / k, 6) for k in (4, 3, 2, 1)))

    def test_point_estimates(self):
        r = self.rows(self.formal, "config:olmo2")
        self.assertAlmostEqual(r["H1"]["point"], 20, delta=2)          # (70 − 30)/2
        self.assertAlmostEqual(r["H2"]["point"], 10, delta=2)          # 20 − (60 − 40)/2
        self.assertAlmostEqual(r["H4b"]["point"], -10, delta=2)        # 多估计收缩一半
        self.assertEqual(r["H4a"]["point"], 0.0)                       # 没有端点
        self.assertEqual(r["H1"]["n_clusters"], 5)                     # 正式集两题一簇
        self.assertIn("预测方向", r["H1"]["verdict"])
        self.assertTrue(r["H4b"]["verdict"].startswith("多估计 < 直接"))

    def test_descriptives(self):
        d = self.formal["descriptives"]["olmo2"]
        self.assertAlmostEqual(d["conditions_all_available"]["stated|direct|S"]["mean_delta"], 20, delta=2)
        self.assertEqual(d["conditions_all_available"]["stated|direct|pooled"]["reverse_rate"], 0.0)
        self.assertEqual(d["h2_reading"]["reading"], "转述下方向化移动与绝对移动都较小")
        self.assertEqual(d["endpoints_all_available"]["direct"]["prior"]["rate"], 0.0)
        h4a = self.rows(self.formal, "config:olmo2")["H4a"]["companion"]
        self.assertEqual((h4a["n_common"], h4a["e_direct_minus_e_multi"]), (10, 0.0))
        self.assertAlmostEqual(d["candidates_multi"]["stated"]["mean_endpoint_mass"], 0.0)
        self.assertEqual(d["repeat_noise"]["stated|S|direct"]["n"], 3)
        self.assertIsNone(d["power_scenarios"])
        self.assertIn("H1", self.dev["descriptives"]["olmo2"]["power_scenarios"])
        self.assertIsNone(self.dev["descriptives"]["olmo2"]["repeat_noise"])
        self.assertEqual(d["candidates_multi"]["stated"]["weight_sum_in_tolerance_rate"],1.0)
        self.assertEqual(set(self.formal["speech_sensitivity"]["comparison"]["config:olmo2"]),{"H1","H2","H4b"})
        self.assertIn("speech_updates.json",self.formal["analysis_code"])

    def test_budget_and_missing(self):
        b = self.formal["budget"]["olmo2|stated|S|direct|r0"]
        self.assertEqual((b["n"], b["prompt_tokens"], b["final_missing_rate"]), (10, 150.0, 0.0))
        self.assertEqual(self.formal["missing"]["codex|prior|-|multi|r1"]["n"], 3)

    def test_cross_config_summary(self):
        s = self.formal["cross_config_summary"]
        self.assertEqual(set(s["H1"]), set(run.CONFIGS))
        self.assertNotIn("H3", s)
        self.assertIn("opposite_direction", s["H1"]["olmo2"])

    def test_accounting_complete_and_strata(self):
        """c 第二轮 Q2：三个配置、全部计划 unit 都在 → 完整核账；S4：按 source_split 分层。"""
        for out, n in ((self.dev, 60), (self.formal, 130)):
            self.assertEqual(out["status"], "完整核账")
            self.assertEqual(out["accounting"]["n_planned_units_per_config"], n)
            self.assertEqual(out["accounting"]["configs"]["codex"]["completion_rate"], 1.0)
        st = self.formal["source_split_strata"]
        self.assertEqual(sorted(st), ["dev", "test"])
        self.assertEqual(st["dev"]["n_planned"] + st["test"]["n_planned"], 10)
        self.assertAlmostEqual(st["dev"]["olmo2|H1"]["point"], 20, delta=2)
        self.assertNotIn("H3", st["test"])
        fin = AN.analyse("formal", base=self.base, freeze_path=self.fz, final=True)
        self.assertEqual((fin["status"], fin["mode"]["mode"], fin["mode"]["B"]), ("完整核账", "正式", 300))
        self.assertEqual(self.formal["mode"]["mode"], "诊断")                   # final=False 一律标诊断

    def test_final_rejects_other_B(self):
        """c 第三轮 N-B1：冻结 B 后，正式分析传入其他 B 必须拒绝；诊断分析可以改 B，但标出与冻结值不同。"""
        with self.assertRaises(AN.MaterialMismatch) as cm:
            AN.analyse("formal", base=self.base, freeze_path=self.fz, B=5000, final=True)
        self.assertIn("frozen B=300", str(cm.exception))
        d = AN.analyse("formal", base=self.base, freeze_path=self.fz, B=50)
        self.assertEqual((d["mode"]["mode"], d["mode"]["B"], d["mode"]["B_frozen"]), ("诊断", 50, 300))
        self.assertTrue(d["mode"]["notes"])


class Bindings(unittest.TestCase):
    """材料绑定（c 第二轮 B4）：清单、题面、当前代码、模板、选句 ID、提示哈希、配置归属、unit 字段、重复轮、跨配置共同材料、分析代码，任一不符都拒绝；部分结果的核账（Q2）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "dnli"
        write_base(self.base, n_dev=4, n_formal=4, n_rep=1)
        self.fz = self.base / "fz.json"
        for cfg in ("olmo2", "codex"):
            run_config(self.base, "dev", cfg)
            AN.freeze("dev", cfg, base=self.base, freeze_path=self.fz)

    def tearDown(self):
        self.tmp.cleanup()

    def test_speech_list_changes_reject_frozen_analysis(self):
        trial = self.base / "speech_updates.json"
        trial.write_text('{"update_ids":[]}',encoding="utf-8")
        with patch.dict(AN.CODE_PATHS,{"speech_updates.json":trial}):
            with self.assertRaises(AN.MaterialMismatch):
                AN.analyse("dev",base=self.base,freeze_path=self.fz,B=50)

    def analyse(self):
        return AN.analyse("dev", base=self.base, freeze_path=self.fz, B=50)

    def edit_json(self, rel, fn):
        p = self.base / rel
        obj = json.loads(p.read_text(encoding="utf-8"))
        fn(obj)
        run.save_json(p, obj)

    def test_baseline(self):
        out = self.analyse()
        self.assertEqual(out["binding"]["records_checked"], 2 * 40)

    def test_split_cluster_changed(self):
        self.edit_json(run.SPLIT_FILE, lambda s: s["items"][0].update(cluster="other.jpg"))
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn(run.SPLIT_FILE, str(cm.exception))

    def test_items_text_changed(self):
        k = "img00.jpg#0r1n"
        self.edit_json(run.ITEMS_TEXT, lambda t: t[k].update(U_S="A different strengthener"))
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("materials_digest", str(cm.exception))
        self.assertIn(run.ITEMS_TEXT, str(cm.exception))

    def test_template_changed(self):
        old = prompts.FRAME_REPORTED
        try:
            prompts.FRAME_REPORTED = "I heard someone say that {u}"
            with self.assertRaises(AN.MaterialMismatch) as cm:
                self.analyse()
        finally:
            prompts.FRAME_REPORTED = old
        self.assertIn("templates", str(cm.exception))

    def rewrite_records(self, cfg, fn):
        p = self.base / ("results_dev_%s.jsonl" % cfg)
        recs = run.load_records(p)
        fn(recs)
        p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")

    def test_record_update_id_mismatch(self):
        def f(recs):
            r = next(r for r in recs if r["pres"] == "stated" and r["utype"] == "S")
            r["update_id"] = "dev:999"
        self.rewrite_records("olmo2", f)
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("update_id", str(cm.exception))

    def test_repeat_round_outside_subset(self):
        def f(recs):
            r = dict(recs[0])
            r["round"] = "r1"
            r["unit"] = r["unit"][:-2] + "r1"
            recs.append(r)
        self.rewrite_records("codex", f)
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("repeat round", str(cm.exception))

    def test_current_code_changed(self):
        """c 第二轮 B4 负例 1：当前 prompts.py／parse.py 与冻结会话不同 → 拒绝（即使两个配置彼此相同）。"""
        for f in ("prompts.py", "parse.py"):
            orig = (self.base / f).read_text(encoding="utf-8")
            (self.base / f).write_text(orig + " # edited", encoding="utf-8")
            with self.assertRaises(AN.MaterialMismatch) as cm:
                self.analyse()
            self.assertIn(f, str(cm.exception))
            (self.base / f).write_text(orig, encoding="utf-8")
        self.analyse()

    def test_record_prompt_hash_changed(self):
        """B4 负例 2：记录的 prompt_sha256 与当前代码重新渲染的提示不符 → 拒绝。"""
        self.rewrite_records("olmo2", lambda recs: recs[3].update(prompt_sha256="WRONG"))
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("prompt_sha256", str(cm.exception))

    def test_record_config_attribution(self):
        """B4 负例 3：olmo2 结果文件里的记录写着 codex → 拒绝。"""
        self.rewrite_records("olmo2", lambda recs: recs[0].update(config="codex"))
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("comes from the olmo2 results", str(cm.exception))

    def test_unit_fields_mismatch(self):
        """B4 负例 4：unit 与字段不一致（字段改成另一种呈现）→ 拒绝。"""
        def f(recs):
            r = next(r for r in recs if r["pres"] == "stated")
            r["pres"] = "reported"
        self.rewrite_records("codex", f)
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("unit does not match its fields", str(cm.exception))

    def test_analysis_code_bound(self):
        """分析代码与设置绑定到冻结：冻结文件里的哈希与当前不同 → 拒绝；freeze 也拒绝覆盖。"""
        fz = json.loads(self.fz.read_text(encoding="utf-8"))
        fz["dev"][AN.CODE_KEY]["analysis.py"] = "0" * 64
        self.fz.write_text(json.dumps(fz), encoding="utf-8")
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("analysis.py", str(cm.exception))
        with self.assertRaises(SystemExit):
            AN.freeze("dev", "olmo2", base=self.base, freeze_path=self.fz)

    def test_frozen_5000_final_other_B_rejected(self):
        """c 第三轮 N-B1 负例：默认冻结 B=5000；正式分析传入 50 必须拒绝（在核账之前）。"""
        fz = json.loads(self.fz.read_text(encoding="utf-8"))
        self.assertEqual(fz["dev"][AN.CODE_KEY]["B"], 5000)
        with self.assertRaises(AN.MaterialMismatch) as cm:
            AN.analyse("dev", base=self.base, freeze_path=self.fz, B=50, final=True)
        self.assertIn("frozen B=5000", str(cm.exception))
        with self.assertRaises(SystemExit):                       # 也不能用另一个 B 重新冻结
            AN.freeze("dev", "olmo2", base=self.base, freeze_path=self.fz, B=50)

    def test_run_py_current_file_bound(self):
        """c 第三轮 N-B2 负例（一）：当前目录的 run.py 与冻结会话不同（只改非渲染部分，提示不变）→ 拒绝。"""
        (self.base / "run.py").write_text("# stand-in run.py  # changed load_records only", encoding="utf-8")
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("run.py differs from the frozen session", str(cm.exception))
        self.assertNotIn("prompt_sha256", str(cm.exception))

    def test_run_py_analysis_dependency_bound(self):
        """c 第三轮 N-B2 负例（二）：分析实际依赖的 run.py（记录筛选等）换成只改了非渲染函数的副本，渲染完全相同
        （逐条提示哈希照样通过）→ 因分析冻结里的 run.py 哈希不符而拒绝。"""
        real = AN.CODE_PATHS["run.py"]
        src = real.read_text(encoding="utf-8")
        old = "def valid_records(records, sessions, fp_id):"
        self.assertIn(old, src)
        copy = Path(self.tmp.name) / "run_modified.py"
        copy.write_text(src.replace(old, old + "\n    # changed: non-rendering analysis dependency"),
                        encoding="utf-8")
        AN.CODE_PATHS["run.py"] = copy
        try:
            with self.assertRaises(AN.MaterialMismatch) as cm:
                self.analyse()
        finally:
            AN.CODE_PATHS["run.py"] = real
        self.assertIn("run.py", str(cm.exception))
        self.assertIn(AN.CODE_KEY, str(cm.exception))
        self.analyse()                                            # 换回后通过

    def test_extra_unit_rejected_in_final(self):
        """c 第三轮 N-S3：记录里有计划外 unit → 部分分析、不计入 ok、不进分析；正式分析拒绝。"""
        real = AN.planned_units

        def fewer(base, which):
            pu = real(base, which)
            for units in pu.values():
                units.discard(sorted(units)[0])
            return pu
        AN.planned_units = fewer
        try:
            out = self.analyse()
            acct = out["accounting"]["configs"]["olmo2"]
            self.assertEqual((acct["extra_units"], acct["ok"], acct["ok_rate_of_planned"]), (1, 39, 1.0))
            self.assertTrue(out["status"].startswith("部分分析"))
            with self.assertRaises(AN.Incomplete):
                AN.analyse("dev", base=self.base, freeze_path=self.fz, final=True)
        finally:
            AN.planned_units = real

    def test_partial_analysis(self):
        """c 第二轮 Q2：缺两个配置、某配置缺 unit → 「部分分析」，以计划 unit 为分母报完成率；final=True 拒绝。"""
        self.rewrite_records("codex", lambda recs: recs.__delitem__(slice(0, 5)))
        out = self.analyse()
        self.assertTrue(out["status"].startswith("部分分析"))
        acct = out["accounting"]
        self.assertEqual(acct["missing_configs"], ["qwen3-off"])
        self.assertEqual((acct["configs"]["codex"]["not_attempted"], acct["configs"]["codex"]["completion_rate"]),
                         (5, 35 / 40))
        self.assertEqual(acct["configs"]["olmo2"]["completion_rate"], 1.0)
        na = sum(v["status"].get("not_attempted", 0) for k, v in out["missing"].items() if k.startswith("codex|"))
        self.assertEqual(na, 5)
        with self.assertRaises(AN.Incomplete):
            AN.analyse("dev", base=self.base, freeze_path=self.fz, final=True)

    def test_cross_config_common_material(self):
        p = self.base / "run_meta_dev_codex.json"
        meta = run.load_json(p, {})
        for s in meta["sessions"]:
            s["fingerprint"]["parse.py"] = "0" * 64
        run.save_json(p, meta)
        with self.assertRaises(AN.MaterialMismatch) as cm:
            self.analyse()
        self.assertIn("parse.py", str(cm.exception))


def rec(unit, sid, fp, value, status="ok"):
    k, pres, ut, ask, rnd = unit.split("|")
    return {"unit": unit, "key": k, "pres": pres, "utype": ut, "ask": ask, "round": rnd, "use": "dev",
            "cluster": "c", "config": "codex", "status": status, "update_id": None,
            "result": {"value": value} if status == "ok" else None, "session_id": sid, "fingerprint_id": fp,
            "attempts": []}


def sess(sid, fp, closed_ok=True, invalid=False, status="finished"):
    return {"session_id": sid, "fingerprint_id": fp, "fingerprint": {}, "closed_ok": closed_ok, "invalid": invalid,
            "status": status}


class LoadValid(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.res, self.meta = d / "r.jsonl", d / "m.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, sessions, records):
        run.save_json(self.meta, {"sessions": sessions})
        self.res.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def test_filters(self):
        u = "k%d|prior|-|direct|r0"
        sessions = [sess("S1", "F"), sess("S2", "F", closed_ok=False, invalid=True, status="stopped"),
                    sess("S3", "F"), sess("S4", "G"), sess("S5", "F", closed_ok=False, status="running"),
                    sess("S6", "F")]
        records = [rec(u % 1, "S1", "F", 90), rec(u % 2, "S1", "F", 80),
                   rec(u % 3, "S2", "F", 99),          # 失效会话里的成功记录
                   rec(u % 3, "S3", "F", 50),          # 作废后重采
                   rec(u % 4, "S4", "G", 70),          # 旧指纹
                   rec(u % 5, "GHOST", "F", 60),       # 未知会话
                   rec(u % 6, "S5", "F", 40),          # 未收尾
                   rec(u % 1, "S6", "F", 91)]          # 同一 unit 的较新记录
        self.write(sessions, records)
        v, drop = AN.load_valid(self.res, self.meta, "F")
        self.assertEqual({r["unit"]: r["result"]["value"] for r in v}, {u % 1: 91, u % 2: 80, u % 3: 50})
        self.assertEqual(drop, {"invalid_session": 1, "other_fingerprint": 1, "unknown_session": 1,
                                "session_not_closed_ok": 1, "superseded_duplicate": 1})

    def test_record_fp_must_match_too(self):
        self.write([sess("S1", "F")], [rec("k|prior|-|direct|r0", "S1", "X", 10)])
        self.assertEqual(AN.load_valid(self.res, self.meta, "F"), ([], {"other_fingerprint": 1}))

    def test_freeze(self):
        base = Path(self.tmp.name)
        run.save_json(base / "run_meta_dev_olmo2.json", {"sessions": [sess("S1", "F"), sess("S2", "F")]})
        fz = base / "fz.json"
        self.assertEqual(AN.freeze("dev", "olmo2", base=base, freeze_path=fz), "F")
        self.assertEqual(AN.frozen_fp("olmo2", "dev", path=fz), "F")
        run.save_json(base / "run_meta_dev_olmo2.json", {"sessions": [sess("S1", "F"), sess("S2", "G")]})
        with self.assertRaises(SystemExit):
            AN.freeze("dev", "olmo2", base=base, freeze_path=fz)


class Accounting(unittest.TestCase):
    def test_c_round3_extra_unit_counterexample(self):
        """c 第三轮 N-S3 反例：计划 1 个 unit，给一个计划内记录与一个计划外成功记录 → 不得「完整核账」，ok 率不超过 1。"""
        recs = {cfg: [{"unit": "u1", "status": "ok"}, {"unit": "x9", "status": "ok"}] for cfg in AN.CONFIGS}
        a = AN.accounting({"u1"}, recs, set(AN.CONFIGS))
        self.assertTrue(a["status"].startswith("部分分析"))
        self.assertEqual((a["configs"]["olmo2"]["ok"], a["configs"]["olmo2"]["ok_rate_of_planned"],
                          a["configs"]["olmo2"]["extra_units"]), (1, 1.0, 1))


class Budget(unittest.TestCase):
    def test_budget(self):
        def r(n_prompt, n_pred, think, out, trunc2=False, status="ok"):
            atts = [{"truncated": trunc2, "meta": {"n_prompt_tokens": n_prompt, "n_predict": n_pred,
                                                  "n_thinking_tokens": think, "n_out_tokens": out}}]
            if trunc2:
                atts.append({"truncated": False, "meta": {"n_predict": n_pred}})
            return {"config": "qwen3-off", "pres": "reported", "utype": "W", "ask": "multi", "round": "r0",
                    "status": status, "attempts": atts, "n_attempts": len(atts)}
        out = AN.budget_report([r(100, 8192, 500, 700), r(120, 8192, 300, 360, trunc2=True),
                                r(130, 8192, 8192, 8192, trunc2=True, status="missing")])
        t = out["qwen3-off|reported|W|multi|r0"]
        self.assertEqual((t["n"], t["prompt_tokens"], t["thinking_tokens"]), (3, 116.7, 2997.3))
        self.assertAlmostEqual(t["attempt_truncation_rate"], 2 / 5, places=3)
        self.assertAlmostEqual(t["retry_rate"], 2 / 3, places=3)
        self.assertAlmostEqual(t["final_missing_rate"], 1 / 3, places=3)


if __name__ == "__main__":
    unittest.main()
