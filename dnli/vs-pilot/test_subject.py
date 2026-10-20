"""subject.py 判定函数的测试（不调用 codex）：日志完整性四要素、-o 一致性、固定警告数量、message 去重、额度扫描。
日志与事件的格式照阶段 A 探针的真实输出（raw/probes/）构造。用法：python -I test_subject.py
另有一组测试（本地有 raw/probes/ 才跑）把真实探针输出送进 evaluate，核对结论与 isolation.md 第 8 节一致。"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import subject  # noqa: E402

TS = "2026-10-11T10:17:24.%06dZ"
WARN_FIXED = ("Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; "
              "enable `features.code_mode_host` and install `codex-code-mode-host`.")


def build_raw(text="Final Answer [c].", *, tool=False, preamble=False, allowed=1, other_warning=None,
              tokens=8000, drop=(), o_text=None, msg_lifecycle=False, quota_event=None, quota_log=None,
              api_key_in_trace=True, log_thread="t", quota_level="WARN", log_msg_ids=("msg_1", "msg_2"),
              prompt_continuation=False, sse_continuation=False, diag_continuation=None, prompt_extra=""):
    """返回 (stdout, stderr, o_text)。drop 可含 'sampling'、'items'、'completion'、'loop_exit'、'turn_completed'。
    tool=True：模型先发 custom_tool_call（被拒），第二次采样后回答；preamble=True：第一条 message 是开场白。"""
    ev, log = [], []
    ev.append({"type": "thread.started", "thread_id": "t"})
    for k in range(allowed):
        ev.append({"type": "item.completed", "item": {"id": "item_w%d" % k, "type": "error", "message": WARN_FIXED}})
    if other_warning:
        ev.append({"type": "item.completed", "item": {"id": "item_x", "type": "error", "message": other_warning}})
    ev.append({"type": "turn.started"})
    n = [0]

    def L(level, msg):
        n[0] += 1
        log.append((TS % n[0]) + " %s session_loop{thread_id=%s}: %s" % (level, log_thread, msg))

    if api_key_in_trace:  # trace 级配置转储里本来就有 api_key 字样，不能误报
        L("TRACE", "codex_core::session::session: Configuring session: enable_codex_api_key_env: true")
    L("DEBUG", 'codex_core::session::handlers: Submission sub=Submission { op: TurnInput { input: UserInput { '
               'content: [Text { text: "Mention quota and billing and rate limit in the prompt%s" }] } } }' % prompt_extra)
    if prompt_continuation:  # 假如提示以多行续行的形式出现在日志里（真实日志没有，见 RealProbeOutputs）
        log.append("The detective noted the unpaid billing and the quota of payments.")
        log.append("  You've hit your usage limit, said the clerk.")
    m1, m2 = log_msg_ids
    msgs = []
    if tool or preamble:
        msgs.append(("msg_1", "I'll try."))
        if "items" not in drop:
            L("TRACE", 'codex_core::stream_events_utils: Output item item_type="message" item_id="%s"' % m1)
            L("TRACE", 'codex_core::stream_events_utils: Output item item_type="message" item_id="%s"' % m1)
        if tool and "items" not in drop:
            L("TRACE", 'codex_core::stream_events_utils: Output item item_type="custom_tool_call" item_id="ctc_1"')
            L("DEBUG", "codex_core::stream_events_utils: ToolCall: exec thread_id=%s" % log_thread)
            L("ERROR", "codex_core::tools::router: error=code-mode host is disabled")
        if "sampling" not in drop:
            L("DEBUG", "codex_core::session::turn: post sampling token usage turn_id=u total_usage_tokens=7350 "
                       "model_needs_follow_up=true has_pending_input=false")
    if "items" not in drop:
        L("TRACE", 'codex_core::stream_events_utils: Output item item_type="reasoning" item_id="rs_2"')
        L("TRACE", 'codex_core::stream_events_utils: Output item item_type="message" item_id="%s"' % m2)
        L("TRACE", 'codex_core::stream_events_utils: Output item item_type="message" item_id="%s"' % m2)
    if sse_continuation:  # 假如将来开了 codex_api trace，模型输出以多行记录出现
        L("TRACE", "codex_api::sse::responses: SSE event: {\"type\":\"response.output_text.delta\",")
        log.append("  \"delta\": \"Final Answer [c]. The billing quota was exceeded in the story.\"}")
    msgs.append(("msg_2", text))
    if "sampling" not in drop:
        L("DEBUG", "codex_core::session::turn: post sampling token usage turn_id=u total_usage_tokens=7358 model_needs_follow_up=%s "
                   "has_pending_input=false" % ("true" if "completion" in drop else "false"))
    if quota_log:
        L(quota_level, quota_log)
    if diag_continuation:  # 客户端诊断带续行：续行属于这条记录，要扫
        L("DEBUG", "codex_core::client: request failed, response body follows")
        log.append(diag_continuation)
    if "loop_exit" not in drop:
        L("DEBUG", "codex_core::session::handlers: Agent loop exited")
    for k, (mid, t) in enumerate(msgs):
        iid = "item_m%d" % k
        if msg_lifecycle:
            ev.append({"type": "item.started", "item": {"id": iid, "type": "agent_message", "text": ""}})
            ev.append({"type": "item.updated", "item": {"id": iid, "type": "agent_message", "text": t[:3]}})
        ev.append({"type": "item.completed", "item": {"id": iid, "type": "agent_message", "text": t}})
    if quota_event:
        ev.append({"type": "item.completed", "item": {"id": "item_q", "type": "error", "message": quota_event}})
    if "turn_completed" not in drop:
        ev.append({"type": "turn.completed", "usage": {"input_tokens": tokens, "cached_input_tokens": 0,
                                                       "output_tokens": 50}})
    out = "\n".join(json.dumps(e) for e in ev) + "\n"
    return out, "\n".join(log) + "\n", (text if o_text is None else o_text)


def ev_of(**kw):
    out, err, o = build_raw(**kw)
    return subject.evaluate(out, err, o, 0, False)


class Integrity(unittest.TestCase):
    def test_complete_clean(self):
        r = ev_of()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["integrity_errors"], [])
        self.assertEqual(r["log"]["sampling_requests"], 1)
        self.assertEqual(r["log"]["tool_items"], [])
        self.assertFalse(r["quota_hit"], r["quota_hits"])

    def test_tool_call_detected_and_still_integral(self):
        r = ev_of(tool=True)
        self.assertEqual(r["integrity_errors"], [])
        self.assertEqual(r["log"]["tool_items"], ["custom_tool_call"])
        self.assertEqual(r["log"]["sampling_requests"], 2)
        self.assertEqual(len(r["events"]["agent_message_ids"]), 2)

    def test_only_sampling_line_is_not_enough(self):
        # c 复现：只有一条 post sampling token usage 时旧版判 log_present=True
        err = (TS % 1) + " DEBUG x: codex_core::session::turn: post sampling token usage turn_id=u model_needs_follow_up=false\n"
        out, _, o = build_raw()
        r = subject.evaluate(out, err, o, 0, False)
        self.assertIn("log_no_output_item_record", r["integrity_errors"])
        self.assertIn("log_no_turn_completion", r["integrity_errors"])  # 没有 Agent loop exited

    def test_missing_output_items(self):
        self.assertIn("log_no_output_item_record", ev_of(drop=("items",))["integrity_errors"])

    def test_missing_sampling(self):
        errs = ev_of(drop=("sampling",))["integrity_errors"]
        self.assertIn("log_no_sampling_record", errs)
        self.assertIn("log_no_turn_completion", errs)

    def test_missing_turn_completion(self):
        self.assertIn("log_no_turn_completion", ev_of(drop=("completion",))["integrity_errors"])
        self.assertIn("log_no_turn_completion", ev_of(drop=("loop_exit",))["integrity_errors"])
        self.assertIn("event_turn.completed_count=0", ev_of(drop=("turn_completed",))["integrity_errors"])

    def test_o_file_mismatch_and_missing(self):
        out, err, _ = build_raw()
        self.assertIn("o_file_text_mismatch", subject.evaluate(out, err, "Final Answer [a].", 0, False)["integrity_errors"])
        self.assertIn("o_file_missing", subject.evaluate(out, err, None, 0, False)["integrity_errors"])
        self.assertEqual(subject.evaluate(out, err, "Final Answer [c].\n", 0, False)["integrity_errors"], [])

    def test_message_count_log_vs_events(self):
        out, err, o = build_raw(preamble=True)
        err = "\n".join(l for l in err.splitlines() if 'item_id="msg_1"' not in l)  # 日志少了开场白那条 message
        self.assertTrue(any(e.startswith("message_count_log=1_events=2")
                            for e in subject.evaluate(out, err, o, 0, False)["integrity_errors"]))


class HeaderParse(unittest.TestCase):
    """记录头解析（格式照真实探针日志）。"""

    def test_span_chain_with_quoted_fields(self):
        h = subject.parse_header(
            '2026-10-11T10:17:24.670916Z ERROR session_loop{thread_id=abc}:submission_dispatch{otel.name="op: x {y}" '
            'submission.id="s" codex.op="turn_input"}:codex.turn_input{conversation.id=abc}: '
            'codex_core::tools::router: error=code-mode host is disabled')
        self.assertEqual(h["target"], "codex_core::tools::router")
        self.assertEqual([n for n, _ in h["spans"]], ["session_loop", "submission_dispatch", "codex.turn_input"])
        self.assertEqual(h["message"], "error=code-mode host is disabled")

    def test_bare_span_names(self):
        h = subject.parse_header('2026-10-11T10:17:17.376359Z DEBUG thread_spawn{otel.name="thread_spawn"}:session_init: '
                                 'codex_core::session::session: Configuring session: model=m')
        self.assertEqual(h["target"], "codex_core::session::session")
        self.assertTrue(h["message"].startswith("Configuring session"))

    def test_no_spans(self):
        h = subject.parse_header("2026-10-11T10:17:14.619533Z DEBUG codex_core::exec_policy: loaded rules from 0 files")
        self.assertEqual((h["target"], h["spans"]), ("codex_core::exec_policy", []))
        h = subject.parse_header("2026-10-11T10:17:14.619533Z  INFO codex_exec: Codex initialized with event: x")
        self.assertEqual(h["target"], "codex_exec")

    def test_quoted_thread_id_in_span(self):
        h = subject.parse_header('2026-10-11T10:17:17.432089Z  INFO codex.exec{otel.kind="internal" thread.id="abc-1"}: '
                                 'codex_exec: Sent prompt with event ID: x')
        self.assertEqual(subject._SPAN_THREAD.findall(h["spans"][0][1]), ["abc-1"])

    def test_unparseable_is_none(self):
        self.assertIsNone(subject.parse_header("not a log line"))
        self.assertIsNone(subject.parse_header("2026-10-11T10:17:14.6Z DEBUG no colon space here"))


class CrossSourceLink(unittest.TestCase):
    """第三轮阻断 2：日志与事件流必须能关联。"""

    def test_thread_id_mismatch_rejected(self):
        # 等数量的 message，但日志来自另一个线程
        r = ev_of(log_thread="other-thread")
        self.assertTrue(any(e.startswith("thread_id_mismatch") for e in r["integrity_errors"]), r["integrity_errors"])

    def test_mixed_threads_in_log_rejected(self):
        out, err, o = build_raw()
        err += (TS % 99) + " DEBUG session_loop{thread_id=another}: codex_core::session::handlers: Agent loop exited\n"
        r = subject.evaluate(out, err, o, 0, False)
        self.assertTrue(any(e.startswith("thread_id_mismatch") for e in r["integrity_errors"]))

    def test_missing_thread_started_rejected(self):
        out, err, o = build_raw()
        out = "\n".join(l for l in out.splitlines() if "thread.started" not in l) + "\n"
        errs = subject.evaluate(out, err, o, 0, False)["integrity_errors"]
        self.assertIn("events_no_thread_id", errs)

    def test_final_message_correspondence(self):
        r = ev_of(preamble=True)
        self.assertEqual(r["integrity_errors"], [])
        self.assertEqual(subject.message_mapping(r["events"], r["log"]), [("item_m0", "msg_1"), ("item_m1", "msg_2")])

    # 第四轮阻断 1：thread_id 只认记录头 span 里的结构性元数据
    def test_thread_id_in_prompt_body_ignored(self):
        # c 的复现 1：提示正文含 thread_id=other，同一线程的正常调用不能被误判为混入线程
        r = ev_of(prompt_extra=" thread_id=other and thread.id=\\\"other2\\\"")
        self.assertEqual(r["log"]["thread_ids"], ["t"])
        self.assertEqual(r["integrity_errors"], [])

    def test_only_body_thread_id_without_structural_rejected(self):
        # c 的复现 2：删掉全部结构性 session_loop{thread_id=t}:，只在提示正文留 thread_id=t → 必须拒绝
        out, err, o = build_raw(prompt_extra=" thread_id=t")
        err = err.replace("session_loop{thread_id=t}: ", "")
        r = subject.evaluate(out, err, o, 0, False)
        self.assertEqual(r["log"]["thread_ids"], [])
        self.assertTrue(any(e.startswith("thread_id_mismatch") for e in r["integrity_errors"]), r["integrity_errors"])

    def test_tool_call_message_thread_id_not_structural(self):
        # ToolCall 记录的正文也写着 thread_id=…；只认 span 里的
        out, err, o = build_raw(tool=True)
        err = err.replace("session_loop{thread_id=t}: ", "")
        self.assertEqual(subject.evaluate(out, err, o, 0, False)["log"]["thread_ids"], [])

    def test_structural_markers_in_body_are_not_evidence(self):
        # 同一原则用于其他证据：提示正文里写着 post sampling token usage／Output item／Agent loop exited 都不算
        fake = (" codex_core::session::turn: post sampling token usage turn_id=u model_needs_follow_up=false"
                " codex_core::stream_events_utils: Output item item_type=\\\"message\\\" item_id=\\\"msg_2\\\""
                " codex_core::session::handlers: Agent loop exited")
        r = ev_of(drop=("sampling", "items", "loop_exit"), prompt_extra=fake)
        for e in ("log_no_sampling_record", "log_no_output_item_record", "log_no_turn_completion"):
            self.assertIn(e, r["integrity_errors"])

    def test_known_limit_message_ids_are_different_namespaces(self):
        # 已知边界（如实记录，不是通过条件）：日志的 message ID 是响应 ID（msg_…），事件流的是 exec 自编的 item_N，
        # 两者没有对照表，所以换掉日志里的 message ID 本身无法被识别；跨来源关联靠 thread_id（上面三个测试）。
        r = ev_of(log_msg_ids=("other_1", "other_2"))
        self.assertEqual(r["integrity_errors"], [])


class Warnings(unittest.TestCase):
    def test_one_fixed_warning_allowed(self):
        r = ev_of(allowed=1)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["events"]["allowed_warnings"]), 1)

    def test_no_fixed_warning_is_fine(self):
        self.assertTrue(ev_of(allowed=0)["ok"])

    def test_two_fixed_warnings_rejected(self):
        r = ev_of(allowed=2)
        self.assertFalse(r["ok"])
        self.assertIn("allowed_warning_repeated:2", r["events"]["warnings"])

    def test_other_warning_rejected(self):
        r = ev_of(other_warning="Codex is ignoring 1 unrecognized configuration setting.")
        self.assertFalse(r["ok"])


class Dedup(unittest.TestCase):
    def test_message_lifecycle_counts_once(self):
        r = ev_of(msg_lifecycle=True)
        self.assertEqual(len(r["events"]["agent_message_ids"]), 1)  # started／updated／completed 同一 ID
        self.assertEqual(r["events"]["item_types"]["agent_message"], 1)
        self.assertEqual(r["text"], "Final Answer [c].")
        self.assertEqual(r["integrity_errors"], [])


class Quota(unittest.TestCase):
    def test_quota_in_event_with_exit_zero(self):
        r = ev_of(quota_event="You've hit your usage limit. Try again later.")
        self.assertTrue(r["quota_hit"])
        self.assertEqual(r["returncode"], 0)

    def test_quota_in_warn_log_with_exit_zero(self):
        r = ev_of(quota_log="codex_core::client: 429 Too Many Requests (rate limit)")
        self.assertTrue(r["quota_hit"])

    def test_prompt_and_answer_words_do_not_trigger(self):
        r = ev_of(text="Final Answer [c]. (Nothing about billing, quota, credits or an API key here.)")
        self.assertFalse(r["quota_hit"], r["quota_hits"])  # 回答与提示（Submission 行）里的词不扫

    def test_trace_config_dump_api_key_does_not_trigger(self):
        self.assertFalse(ev_of(api_key_in_trace=True)["quota_hit"])

    # 第三轮阻断 5：客户端诊断不论级别都扫
    def test_quota_diagnostic_at_info_and_debug_and_trace(self):
        for level in ("INFO", "DEBUG", "TRACE", "ERROR"):
            r = ev_of(quota_log="codex_core::client: 429 Too Many Requests", quota_level=level)
            self.assertTrue(r["quota_hit"], level)

    # 第三轮建议 2：续行按完整日志记录处理
    def test_prompt_continuation_lines_do_not_trigger(self):
        r = ev_of(prompt_continuation=True)
        self.assertFalse(r["quota_hit"], r["quota_hits"])

    def test_model_output_record_continuation_does_not_trigger(self):
        r = ev_of(sse_continuation=True)
        self.assertFalse(r["quota_hit"], r["quota_hits"])

    def test_diagnostic_continuation_line_is_scanned(self):
        r = ev_of(diag_continuation="{\"error\": {\"code\": \"insufficient_quota\"}}")
        self.assertTrue(r["quota_hit"])

    # 第四轮阻断 2：内容排除只按记录头的 target 判定
    def add_line(self, line):
        out, err, o = build_raw()
        return subject.evaluate(out, err + (TS % 98) + " " + line + "\n", o, 0, False)

    def test_client_429_mentioning_userinput_is_scanned(self):
        # c 的复现 1
        r = self.add_line("ERROR codex_core::client: 429 Too Many Requests; rejected UserInput { content: [] }")
        self.assertTrue(r["quota_hit"], r["quota_hits"])

    def test_client_429_mentioning_sse_target_is_scanned(self):
        # c 的复现 2
        r = self.add_line("INFO codex_core::client: 429 Too Many Requests; context codex_api::sse")
        self.assertTrue(r["quota_hit"], r["quota_hits"])

    def test_client_diagnostic_mentioning_content_target_names_is_scanned(self):
        r = self.add_line("WARN codex_core::client: usage limit reached (seen near codex_core::exec_policy: and "
                          "codex_core::session::handlers: Submission sub=)")
        self.assertTrue(r["quota_hit"])

    def test_content_targets_still_excluded(self):
        for line in ('DEBUG session_loop{thread_id=t}: codex_core::session::handlers: Submission sub=Submission { '
                     'op: UserInput { text: "the quota and billing" } }',
                     'TRACE thread_spawn{otel.name="thread_spawn"}:session_init: codex_core::session::session: '
                     'Configuring session: enable_codex_api_key_env: true',
                     'DEBUG codex_core::exec_policy: loaded rules=Policy { "payment" }',
                     'TRACE codex_api::sse::responses: SSE event: {"delta": "rate limit"}'):
            r = self.add_line(line)
            self.assertFalse(r["quota_hit"], (line, r["quota_hits"]))

    def test_untimestamped_lines_before_any_record_are_scanned(self):
        out, err, o = build_raw()
        r = subject.evaluate(out, "Error: You've hit your usage limit.\n" + err, o, 0, False)
        self.assertTrue(r["quota_hit"])


@unittest.skipUnless((HERE / "raw" / "probes" / "p2_shell_1791713834.stderr.txt").exists(), "raw probes not present")
class RealProbeOutputs(unittest.TestCase):
    """isolation.md 第 8 节的结论应能由 evaluate 重现。"""

    def ev(self, tag):
        d = HERE / "raw" / "probes"
        out = (d / (tag + ".events.jsonl")).read_text(encoding="utf-8")
        err = (d / (tag + ".stderr.txt")).read_text(encoding="utf-8")
        o = (d / (tag + ".last.txt")).read_text(encoding="utf-8")
        return subject.evaluate(out, err, o, 0, False)

    def test_probe_4_shell_tool_call_caught(self):
        r = self.ev("p2_shell_1791713834")
        self.assertEqual(r["integrity_errors"], [])
        self.assertEqual(r["log"]["tool_items"], ["custom_tool_call"])
        self.assertEqual(r["log"]["sampling_requests"], 2)
        self.assertFalse(r["quota_hit"])

    def test_probe_6_clean(self):
        r = self.ev("p4_instructions_1791713917")
        self.assertTrue(r["ok"])
        self.assertEqual(r["integrity_errors"], [])
        self.assertEqual(r["log"]["tool_items"], [])

    def test_real_logs_have_no_continuation_lines(self):
        # 建议 2 的格式核对：真实日志每条记录都是单行（提示正文以 Rust Debug 格式转义成 \n），没有续行
        d = HERE / "raw" / "probes"
        for tag in ("p1_tools_1791713455", "p2_shell_1791713834", "p3_web_1791713866", "p4_instructions_1791713917"):
            err = (d / (tag + ".stderr.txt")).read_text(encoding="utf-8")
            self.assertEqual(len(subject.log_records(err)), len(err.splitlines()), tag)
            self.assertFalse(subject.evaluate((d / (tag + ".events.jsonl")).read_text(encoding="utf-8"), err,
                                              (d / (tag + ".last.txt")).read_text(encoding="utf-8"), 0, False)["quota_hit"])

    def test_real_logs_fully_parsed(self):
        # 第四轮：4 份真实日志的每条记录都能解析出 target；内容型记录只落在预期的 target 上
        d = HERE / "raw" / "probes"
        allowed = {"codex_core::exec_policy", "codex_core::session::session", "codex_exec", "codex_core::session::handlers"}
        for tag in ("p1_tools_1791713455", "p2_shell_1791713834", "p3_web_1791713866", "p4_instructions_1791713917"):
            recs = subject.records_parsed((d / (tag + ".stderr.txt")).read_text(encoding="utf-8"))
            self.assertTrue(recs)
            self.assertEqual([r[:80] for r, h in recs if h is None], [], tag)
            content = {h["target"] for r, h in recs if subject.is_content_record(r, h)}
            self.assertTrue(content <= allowed, content)

    def test_real_logs_thread_linked(self):
        r = self.ev("p2_shell_1791713834")
        self.assertEqual(r["log"]["thread_ids"], [r["events"]["thread_id"]])

    def test_probe_without_rust_log_fails_integrity(self):
        r = self.ev("p2_shell_1791712991")  # 第 2 次探针没开 RUST_LOG
        self.assertIn("log_no_sampling_record", r["integrity_errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
