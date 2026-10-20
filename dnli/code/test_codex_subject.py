"""复制自 ../suppression/test_codex_subject.py。除本段说明外逐字未改；在 dnli/ 下导入同目录的 codex_subject.py。
"""
"""codex_subject.final_inclusion 与指令来源冻结的测试（不调用 codex）。用法：python -I test_codex_subject.py

- 合成记录：沿用 ../vs-pilot/test_subject.py 的 build_raw（格式照真实探针日志构造）。
- 真实日志：../vs-pilot/raw/ 下 VS pilot 的探针、冒烟与正式运行的原始输出（本地有才跑）；核对状态与 VS pilot 的记录一致。
- 人工异常：删去 stderr（evaluate 仍给 ok=True）、合成工具调用（ok=True）、额度事件、指令来源变化、网络故障那次调用。
"""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VS = HERE.parent / "vs-pilot"
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(VS))
import codex_subject as C  # noqa: E402
import subject  # noqa: E402
from test_subject import build_raw  # noqa: E402

PROMPT = "x" * 1200
FP = "fp0"


def fin(out, err, o, rc=0, timed_out=False, fp_now=FP, prompt=PROMPT):
    r = subject.evaluate(out, err, o, rc, timed_out)
    return r, C.final_inclusion(r, prompt, fp_now, FP, err)


class Synthetic(unittest.TestCase):
    def test_disconnect_message_count_retry(self):
        out, err, o = build_raw(preamble=True)
        events = [json.loads(line) for line in out.splitlines()]
        out = "\n".join(json.dumps(e) for e in events if not (e.get("item", {}).get("id") == "item_m0"))
        warn = '2026-10-11T10:17:25.000000Z WARN codex_core::client: retrying sampling request sampling_error=stream disconnected before response completed\n'
        r, f = fin(out, err + warn, o)
        self.assertTrue(any("message_count_log=2_events=1" in x for x in r["integrity_errors"]))
        self.assertEqual(f["state"], C.DISCONNECT)
        self.assertTrue(f["resample"])
        self.assertFalse(f["include"] or f["stop"] or f["invalidate_session"])
        self.assertEqual(fin(out, err, o)[1]["state"], C.CHECK_FAILED)
        tool = {"type":"item.completed","item":{"id":"tool","type":"command_execution"}}
        self.assertEqual(fin(out + "\n" + json.dumps(tool), err + warn, o)[1]["state"], C.CHECK_FAILED)
        self.assertEqual(fin(out, err + warn, o, fp_now="changed")[1]["state"], C.CHECK_FAILED)
        self.assertEqual(fin(out,err+warn,"different output")[1]["state"], C.CHECK_FAILED)

    def test_reconnecting_event_and_quota_priority(self):
        out, err, o = build_raw(other_warning="Reconnecting... 1/5")
        self.assertEqual(fin(out,err,o)[1]["state"], C.CALL_ERROR)
        out,err,o = build_raw(other_warning="Reconnecting... quota exceeded")
        self.assertEqual(fin(out,err,o)[1]["state"], C.QUOTA_STOP)

    def test_disconnect_does_not_hide_token_or_sampling_anomalies(self):
        warn = '2026-10-11T10:17:25.000000Z WARN codex_core::client: retrying sampling request sampling_error=stream disconnected before response completed\n'
        for tokens in (1000, 20000):
            out, err, o = build_raw(preamble=True, tokens=tokens)
            events = [json.loads(line) for line in out.splitlines()]
            out = '\n'.join(json.dumps(e) for e in events if e.get('item', {}).get('id') != 'item_m0')
            r = subject.evaluate(out, err + warn, o, 0, False)
            self.assertEqual(r["integrity_errors"], ["message_count_log=2_events=1"])
            self.assertEqual(len(PROMPT), 1200)
            self.assertEqual(C.BASELINE_FACTOR * C.token_baseline(PROMPT), 11550)
            r["log"]["sampling_requests"] = 2
            f = C.final_inclusion(r, PROMPT, FP, FP, err + warn)
            if tokens == 20000:
                self.assertEqual(f["state"], C.SUSPECTED)
                self.assertEqual(f["reasons"], ["input_tokens=20000>11550"])
                self.assertTrue(f["resample"])
                self.assertFalse(f["stop"] or f["invalidate_session"] or f["include"])
                self.assertEqual(fin(*build_raw(tokens=tokens))[1]["state"], f["state"])
            else:
                self.assertEqual(f["state"], C.DISCONNECT)
            r["log"]["sampling_requests"] = 20
            f = C.final_inclusion(r, PROMPT, FP, FP, err + warn)
            self.assertEqual(f["state"], C.CHECK_FAILED)
            self.assertTrue(f["stop"] and f["invalidate_session"])

    def test_round5_combined_anomalies_are_check_failed(self):
        out, err, o = build_raw(preamble=True, other_warning="Reconnecting... 1/5")
        # 两条回答仍在事件流；另加日志消息使计数不一致。
        r = subject.evaluate(out + '\n{"type":"unknown.synthetic"}\nnot-json', err, o, 0, False)
        r["integrity_errors"].append("message_count_log=3_events=2")
        f = C.final_inclusion(r, PROMPT, FP, FP, err)
        self.assertEqual(f["state"], C.CHECK_FAILED)
        self.assertTrue(f["stop"] and f["invalidate_session"])

    def test_disconnect_gap_and_health_constraints(self):
        out, err, o = build_raw(preamble=True, other_warning="Reconnecting... 1/5")
        events = [json.loads(line) for line in out.splitlines()]
        out = '\n'.join(json.dumps(e) for e in events if e.get('item', {}).get('id') != 'item_m0')
        warn = '2026-10-11T10:17:25.000000Z WARN codex_core::client: retrying sampling request sampling_error=stream disconnected before response completed\n'
        r, f = fin(out, err + warn, o)
        self.assertEqual(f["state"], C.DISCONNECT)
        r["integrity_errors"] = ["message_count_log=3_events=1"]
        self.assertEqual(C.final_inclusion(r, PROMPT, FP, FP, err + warn)["state"], C.CHECK_FAILED)
        self.assertEqual(C.final_inclusion(r, PROMPT, FP, FP, err + warn * 2)["state"], C.DISCONNECT)
        for kwargs in ({"rc": 1}, {"timed_out": True}):
            self.assertEqual(fin(out, err + warn, o, **kwargs)[1]["state"], C.CHECK_FAILED)
        for extra in ('\n{"type":"unknown.synthetic"}', '\nnot-json'):
            self.assertEqual(fin(out + extra, err + warn, o)[1]["state"], C.CHECK_FAILED)

    def test_disconnect_words_in_prompt_not_evidence(self):
        raw = build_raw(prompt_extra=" retrying sampling request sampling_error=stream disconnected")
        self.assertEqual(fin(*raw)[1]["state"], C.OK)
    def test_clean_is_ok(self):
        r, f = fin(*build_raw())
        self.assertTrue(r["ok"])
        self.assertEqual(f["state"], C.OK)
        self.assertTrue(f["include"])

    def test_missing_log_is_check_failed_although_ok_true(self):
        out, _, o = build_raw()
        r, f = fin(out, "", o)
        self.assertTrue(r["ok"])                       # evaluate 的 ok 不管完整性
        self.assertEqual(f["state"], C.CHECK_FAILED)
        self.assertFalse(f["include"])
        self.assertTrue(f["stop"] and f["invalidate_session"])

    def test_each_missing_log_element(self):
        for d in ("sampling", "items", "completion", "loop_exit"):
            r, f = fin(*build_raw(drop=(d,)))
            self.assertEqual(f["state"], C.CHECK_FAILED, d)

    def test_tool_call_confirmed_although_ok_true(self):
        r, f = fin(*build_raw(tool=True))
        self.assertTrue(r["ok"])
        self.assertEqual(r["integrity_errors"], [])
        self.assertEqual(f["state"], C.CONFIRMED)
        self.assertFalse(f["include"])
        self.assertTrue(f["resample"])
        self.assertFalse(f["stop"])

    def test_preamble_message_suspected(self):
        r, f = fin(*build_raw(preamble=True))
        self.assertEqual(f["state"], C.SUSPECTED)
        self.assertTrue(f["resample"])

    def test_token_baseline_suspected(self):
        r, f = fin(*build_raw(tokens=20000))
        self.assertEqual(f["state"], C.SUSPECTED)

    def test_quota_first(self):
        r, f = fin(*build_raw(quota_event="You've hit your usage limit."))
        self.assertEqual(f["state"], C.QUOTA_STOP)
        self.assertTrue(f["stop"])
        self.assertFalse(f["invalidate_session"])

    def test_quota_beats_integrity(self):
        out, _, o = build_raw(quota_event="rate limit reached")
        r, f = fin(out, "", o)
        self.assertEqual(f["state"], C.QUOTA_STOP)

    def test_instruction_change_is_check_failed(self):
        r, f = fin(*build_raw(), fp_now="other")
        self.assertEqual(f["state"], C.CHECK_FAILED)
        self.assertEqual(f["reasons"], ["instruction_sources_changed"])

    def test_call_error_states(self):
        out, err, o = build_raw()
        _, f = fin(out, err, o, rc=1)
        self.assertEqual(f["state"], C.CALL_ERROR)
        _, f = fin(out, err, o, timed_out=True)
        self.assertEqual(f["state"], C.CALL_ERROR)
        _, f = fin(*build_raw(other_warning="Falling back from WebSockets to HTTPS transport."))
        self.assertEqual(f["state"], C.CALL_ERROR)
        _, f = fin(*build_raw(allowed=2))
        self.assertEqual(f["state"], C.CALL_ERROR)

    def test_integrity_beats_call_error(self):
        out, _, o = build_raw()
        _, f = fin(out, "", o, rc=1)
        self.assertEqual(f["state"], C.CHECK_FAILED)

    def test_only_ok_is_included(self):
        cases = [build_raw(), build_raw(tool=True), build_raw(preamble=True), build_raw(tokens=20000),
                 build_raw(quota_event="quota exceeded"), build_raw(drop=("items",)), build_raw(allowed=2)]
        for c in cases:
            _, f = fin(*c)
            self.assertEqual(f["include"], f["state"] == C.OK)


class InstructionSources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "default_codex"
        self.home.mkdir()
        (self.home / "AGENTS.md").write_text("rules", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_ok(self):
        src = C.check_instruction_sources(C.instruction_sources(env={}, default_home=self.home))
        self.assertTrue(src["AGENTS.md"]["exists"])
        self.assertFalse(src["AGENTS.override.md"]["exists"])

    def test_override_stops(self):
        (self.home / "AGENTS.override.md").write_text("x", encoding="utf-8")
        with self.assertRaises(C.FreezeError):
            C.check_instruction_sources(C.instruction_sources(env={}, default_home=self.home))

    def test_non_default_codex_home_stops(self):
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        (other / "AGENTS.md").write_text("rules", encoding="utf-8")
        with self.assertRaises(C.FreezeError):
            C.check_instruction_sources(C.instruction_sources(env={"CODEX_HOME": str(other)}, default_home=self.home))

    def test_codex_home_set_to_default_ok(self):
        C.check_instruction_sources(C.instruction_sources(env={"CODEX_HOME": str(self.home)}, default_home=self.home))

    def test_fingerprint_changes_with_content(self):
        a = C.instruction_fingerprint(C.instruction_sources(env={}, default_home=self.home))
        (self.home / "AGENTS.md").write_text("rules2", encoding="utf-8")
        b = C.instruction_fingerprint(C.instruction_sources(env={}, default_home=self.home))
        self.assertNotEqual(a, b)


def _triplets(d):
    out = {}
    for p in sorted(Path(d).glob("*.events.jsonl")):
        tag = p.name[:-len(".events.jsonl")]
        out[tag] = (p, Path(d) / (tag + ".stderr.txt"), Path(d) / (tag + ".last.txt"))
    return out


def _read(p):
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


@unittest.skipUnless((VS / "raw" / "run_formal").is_dir(), "VS pilot raw logs not present")
class RealLogs(unittest.TestCase):
    """VS pilot 的真实原始输出。正式与冒烟：除网络故障那一次外都应为 OK（VS pilot 的记录：0 污染、0 额度、全部完整）。"""
    NET_FAIL = "20261011-191932_belief_r_ponens_373-weak__R__a0"

    def states(self, d):
        res = {}
        for tag, (e, s, l) in _triplets(d).items():
            r = subject.evaluate(_read(e), _read(s) or "", _read(l), 0, False)
            res[tag] = (r, C.final_inclusion(r, PROMPT, FP, FP))
        return res

    def test_formal_and_smoke(self):
        n = 0
        for sub in ("run_formal", "run_smoke"):
            for tag, (r, f) in self.states(VS / "raw" / sub).items():
                n += 1
                if tag == self.NET_FAIL:
                    self.assertEqual(f["state"], C.CALL_ERROR, f)
                    self.assertTrue(r["ok"] is False)
                    self.assertEqual(r["integrity_errors"], [])
                    self.assertFalse(r["quota_hit"])
                else:
                    self.assertEqual(f["state"], C.OK, (tag, f))
        self.assertGreater(n, 290)

    def test_probes(self):
        st = {t: f["state"] for t, (r, f) in self.states(VS / "raw" / "probes").items()}
        self.assertEqual(st["p1_tools_1791712922"], C.CHECK_FAILED)   # 没开 RUST_LOG
        self.assertEqual(st["p2_shell_1791712991"], C.CHECK_FAILED)
        self.assertEqual(st["p2_shell_1791713834"], C.CONFIRMED)      # custom_tool_call
        self.assertEqual(st["p3_web_1791713866"], C.CONFIRMED)
        self.assertEqual(st["p1_tools_1791713455"], C.OK)
        self.assertEqual(st["p4_instructions_1791713917"], C.OK)

    def test_real_log_with_stderr_removed(self):
        tag, (e, s, l) = next(iter(_triplets(VS / "raw" / "run_smoke").items()))
        r = subject.evaluate(_read(e), "", _read(l), 0, False)
        self.assertTrue(r["ok"])
        self.assertEqual(C.final_inclusion(r, PROMPT, FP, FP)["state"], C.CHECK_FAILED)

    def test_real_log_with_injected_tool_item(self):
        tag, (e, s, l) = next(iter(_triplets(VS / "raw" / "run_smoke").items()))
        err = _read(s)
        line = next(x for x in err.splitlines() if 'Output item item_type="message"' in x)
        fake = re.sub(r'item_type="message" item_id="[^"]+"', 'item_type="custom_tool_call" item_id="ctc_fake"', line)
        err2 = err.replace(line, fake + "\n" + line, 1)
        r = subject.evaluate(_read(e), err2, _read(l), 0, False)
        self.assertTrue(r["ok"])
        f = C.final_inclusion(r, PROMPT, FP, FP)
        self.assertEqual(f["state"], C.CONFIRMED)
        self.assertFalse(f["include"])


NOCONTACT_DIR = HERE / "raw" / "codex_v071" / "run_formal_codex"


@unittest.skipUnless(any(NOCONTACT_DIR.glob("397451339_jpg_4r1n_reported_S_multi_r0__codex__a0__*.events.jsonl")),
                     "formal no-contact raw logs not present")
class NoContact(unittest.TestCase):
    """a 2026-10-13：正式运行中连不上服务端（workspace routing discovery failed）的真实输出，应判 call_error，不作废会话。"""

    def raw(self):
        e = sorted(NOCONTACT_DIR.glob("397451339_jpg_4r1n_reported_S_multi_r0__codex__a0__*.events.jsonl"))[0]
        s = Path(str(e)[:-len(".events.jsonl")] + ".stderr.txt")
        return e.read_text(encoding="utf-8"), s.read_text(encoding="utf-8", errors="replace")

    def test_real_no_contact_is_call_error(self):
        out, err = self.raw()
        r, f = fin(out, err, None, rc=1)
        self.assertEqual(r["log"]["sampling_requests"], 0)
        self.assertEqual(f["state"], C.CALL_ERROR, f)
        self.assertIn("no_contact", f["reasons"])
        self.assertTrue(f["stop"])
        self.assertFalse(f["include"] or f["invalidate_session"] or f["resample"])

    def test_any_output_or_tool_is_not_no_contact(self):
        out, err = self.raw()
        msg = {"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "Probability: 50%"}}
        tool = {"type": "item.completed", "item": {"id": "t", "type": "command_execution"}}
        for extra in (msg, tool):
            r, f = fin(out + "\n" + json.dumps(extra), err, None, rc=1)
            self.assertFalse(C.is_no_contact(r))
            self.assertNotIn("no_contact", f["reasons"])
        reasoning = {"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "thinking"}}
        r, f = fin(out + "\n" + json.dumps(reasoning), err, None, rc=1)
        self.assertFalse(C.is_no_contact(r))
        self.assertNotIn("no_contact", f["reasons"])
        r, f = fin(out, err, "partial output", rc=1)
        self.assertFalse(C.is_no_contact(r))
        self.assertNotIn("no_contact", f["reasons"])
        r, f = fin(out, err, None, rc=0)
        self.assertFalse(C.is_no_contact(r))
        self.assertEqual(f["state"], C.CHECK_FAILED)
        r, f = fin(out, err, None, rc=1, fp_now="changed")
        self.assertEqual(f["state"], C.CHECK_FAILED)


if __name__ == "__main__":
    unittest.main()
