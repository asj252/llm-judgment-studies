"""split.py 与 split.json 的核对（PLAN v0.2 第 2 节；c 第一轮阻断 7、建议 10）。用法：python -I -X utf8 -B test_split.py
需要本地 data/defeasible-snli/（被 git 排除）；没有就跳过。
"""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import copy
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import split as SP  # noqa: E402

HAVE = (HERE / "data" / "defeasible-snli" / "dev.jsonl").is_file()


@unittest.skipUnless(HAVE, "data/defeasible-snli not present")
class SplitFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
        cls.text = json.loads((HERE / "raw" / "items_text.json").read_text(encoding="utf-8"))
        cls.rows = {}
        for sp in SP.SPLITS:
            for r in SP.load(HERE / "data" / "defeasible-snli" / ("%s.jsonl" % sp), sp):
                cls.rows["%s:%d" % (sp, r["_line"])] = r

    def test_reproducible_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            split, text, _ = SP.build(HERE)
            SP.dump(Path(d) / "s.json", split)
            SP.dump(Path(d) / "t.json", text)
            self.assertEqual((Path(d) / "s.json").read_bytes(), (HERE / "split.json").read_bytes())
            self.assertEqual((Path(d) / "t.json").read_bytes(), (HERE / "raw" / "items_text.json").read_bytes())

    def test_sizes_and_distinct_images(self):
        items = self.split["items"]
        uses = Counter(it["use"] for it in items)
        self.assertEqual(uses, {"dev": 30, "formal": 240})
        self.assertEqual(len({it["cluster"] for it in items}), 270)          # 各对来自不同图片
        dev = {it["cluster"] for it in items if it["use"] == "dev"}
        formal = {it["cluster"] for it in items if it["use"] == "formal"}
        self.assertFalse(dev & formal)                                        # 开发与正式按图片互斥
        self.assertEqual(len({it["key"] for it in items}), 270)

    def test_exclusions(self):
        read20 = json.loads((HERE / "read20_ids.json").read_text(encoding="utf-8"))
        r_imgs = {SP.image(it["pair_id"]) for it in read20["items"] if it["subset"] == "snli"}
        h_imgs = set(json.loads((HERE / "human20_images.json").read_text(encoding="utf-8"))["images"])
        self.assertEqual((len(r_imgs), len(h_imgs)), (10, 20))
        imgs = {it["cluster"] for it in self.split["items"]}
        self.assertFalse(imgs & r_imgs)
        self.assertFalse(imgs & h_imgs)
        # 同一图片的其他 P–H 对也不在任何一边（簇＝图片，不只是同一 SNLIPairId）
        all_pid_imgs = {SP.image(r["SNLIPairId"]) for r in self.rows.values()}
        self.assertTrue(r_imgs <= all_pid_imgs and h_imgs <= all_pid_imgs)

    def test_selected_rows(self):
        """所选 S／W 行：类型正确、非 impossible、属于该 P–H 对；AssignmentIdAnon 与原行一致；题面原文与原行一致。"""
        for it in self.split["items"]:
            t = self.text[it["key"]]
            for typ in ("S", "W"):
                r = self.rows[it[typ]["id"]]
                self.assertEqual(r["UpdateType"], SP.TYPE[typ])
                self.assertIsNot(r["UpdateTypeImpossible"], True)
                self.assertEqual((r["Premise"], r["Hypothesis"], r["SNLIPairId"]), (t["P"], t["H"], it["key"]))
                self.assertEqual(r["AssignmentIdAnon"], it[typ]["AssignmentIdAnon"])
                self.assertEqual(r["Update"], t["U_" + typ])
                self.assertEqual(t[typ + "_id"], it[typ]["id"])
                self.assertEqual(SP.image(r["SNLIPairId"]), it["cluster"])
            n = Counter(r["UpdateType"] for r in self.rows.values()
                        if r["SNLIPairId"] == it["key"] and r["UpdateTypeImpossible"] is not True)
            self.assertEqual((n["strengthener"], n["weakener"]), (it["n_S_cand"], it["n_W_cand"]))

    def test_repeat_subset(self):
        rep = self.split["repeat_subset"]
        formal = {it["key"] for it in self.split["items"] if it["use"] == "formal"}
        self.assertEqual(len(rep), 20)
        self.assertEqual(len(set(rep)), 20)
        self.assertTrue(set(rep) <= formal)

    def test_attrition_consistent(self):
        a = self.split["attrition"]
        self.assertEqual(a["n_ph_pairs_S_and_W"], 396)
        self.assertEqual(a["n_ph_pairs_S_and_W_by_split"], {"dev": 194, "test": 202})   # PLAN 第 2 节的数字
        self.assertEqual(a["n_pool_pairs"], a["n_ph_pairs_S_and_W"] - a["n_pairs_dropped_read20_image"]
                         - a["n_pairs_dropped_human20_image"])
        self.assertEqual(a["n_rows_possible"], sum(a["n_lines"].values()) - sum(a["n_rows_impossible_dropped"].values()))
        self.assertEqual(self.split["data_sha256"], {
            "data/defeasible-snli/dev.jsonl": "34a0be2e4ea4b7533c8e32984c9ead0dcf05962620fceb7b543cfcaa9aee084e",
            "data/defeasible-snli/test.jsonl": "081d0b7a7a563b15a590fffdc4c0741c956e93c93def0cc77def326603f6904a"})

    def test_no_text_in_split_json(self):
        s = (HERE / "split.json").read_text(encoding="utf-8")
        for t in list(self.text.values())[:20]:
            self.assertNotIn(t["U_S"], s)
            self.assertNotIn(t["H"], s)

    def test_retained_items_and_selected_sentences_unchanged(self):
        old = json.loads((HERE / "split_v1.json").read_text(encoding="utf-8"))
        rebuilt, old_text, _ = SP.build_v1(HERE)
        self.assertEqual(json.loads(json.dumps(rebuilt)), old)
        by_old = {it["key"]:it for it in old["items"]}
        new = {it["key"]:it for it in self.split["items"]}
        shared = set(new) & set(by_old)
        self.assertEqual(len(shared),146)
        for key in shared:
            self.assertEqual({k:v for k,v in new[key].items() if k != 'formal_block'}, by_old[key])
            self.assertEqual(self.text[key], old_text[key])
        self.assertEqual(self.split["repeat_subset"],old["repeat_subset"])

    def test_replacement_keys_and_reproducibility(self):
        expected = ["3726215814.jpg#0r1n", "2942311160.jpg#3r1n", "200797624.jpg#4r1n", "2726222057.jpg#3r1n"]
        self.assertEqual([r["replacement"] for r in self.split["attrition"]["protected_attribute_replacements"]],expected)
        self.assertEqual(SP.build(HERE),SP.build(HERE))
        for key in expected:
            self.assertFalse(SP.sensitive_hits(self.text[key]))

    def test_replacement_inherits_repeat_position(self):
        original = SP.build_v1(HERE)
        old = copy.deepcopy(original)
        formal_removed = "3512747808.jpg#2r1n"
        old[0]["repeat_subset"][7] = formal_removed
        with patch.object(SP,"build_v1",return_value=old):
            new,_,_ = SP.build(HERE)
        self.assertEqual(new["repeat_subset"][7],"2726222057.jpg#3r1n")
        self.assertEqual(len(new["repeat_subset"]),20)
        self.assertTrue(new["attrition"]["protected_attribute_replacements"][-1]["inherits_repeat"])

    def test_unknown_sensitive_replacement_stops(self):
        original = SP.sensitive_hits
        def screen(item):
            return {"H":["synthetic hit"]} if item["H"] == "It is noon." else original(item)
        with patch.object(SP,"sensitive_hits",side_effect=screen):
            with self.assertRaises(SP.SensitiveReviewRequired) as cm:
                SP.build(HERE)
        self.assertIn("3726215814.jpg#0r1n",cm.exception.pending)


class KeywordScreen(unittest.TestCase):
    def test_person_predicate_and_clothing(self):
        for h in ("The boy is Hispanic.","An African boy is playing.","They are Japanese.","A Jewish woman walks."):
            self.assertTrue(SP.sensitive_hits({"H":h,"U_S":"A ball.","U_W":"A road."}))
        for h in ("A white jersey.","The jersey is white.","A black and red bottle.","A bike race."):
            hit = SP.sensitive_hits({"H":h,"U_S":"A ball.","U_W":"A road."})
            if "race" not in h:
                self.assertFalse(hit)
        self.assertTrue(SP.sensitive_hits({"H":"A person walks.","U_S":"They are Japanese.","U_W":"A road."}))


if __name__ == "__main__":
    unittest.main()
