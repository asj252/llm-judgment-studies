"""基于 ../suppression/codex_subject.py（2026-10-12，c 第二至第五轮审过的版本）；v0.6 增加断线重采。
../vs-pilot/subject.py 的路径（HERE.parent / "vs-pilot"）在 dnli/ 下同样成立；其 SHA-256 进实验指纹（run.CODEX_CODE）。
"""
"""codex 受测者（PLAN v0.4 第 4、7 节；任务书第 8 步）。

- 调用、事件与日志检查沿用 `../vs-pilot/subject.py`（直接导入，不复制；其 SHA-256 进实验指纹）。
- **唯一的最终纳入函数** `final_inclusion()`：每次调用只经由它判定状态与处理；`subject.evaluate` 的 `ok` 只作为
  「调用异常」判定的一部分输入，从不作为纳入依据。状态与处理（照 `../vs-pilot/run.py` 的 check_call 与 contamination）：
    检查顺序：额度 → 指令文件指纹 → 计算调用健康 → 完整性／受限断线判定 → 工具污染。
    QUOTA_STOP        额度／付费／限流迹象：停；会话不失效（已写入的记录各自通过了检查）。
    DISCONNECT        唯一完整性问题为可由日志断线重试次数解释的消息数差：本次作废重采，不作废会话。
    CHECK_FAILED      全局指令文件指纹变化、日志完整性错误：停；会话失效。
    CALL_ERROR        非 0 退出、超时、失败事件、非允许警告、未知事件、坏行、没有最终回答：停；会话不失效。
    CONFIRMED         日志或 --json 里有工具 item（确证污染）：作废，同题同条件重采一次；仍作废记 tool_contaminated。
    SUSPECTED         只有多次采样、多条 agent_message 或输入 token 超基线 1.5 倍（疑似污染）：同上。
    OK                普通成功：才进入解析；解析失败的重试也再走一遍本函数。
- 冻结（freeze_codex）：在 vs-pilot 的 freeze 之上，记录实际 CODEX_HOME（环境变量或默认 ~/.codex）与其下
  AGENTS.override.md、AGENTS.md 的存在与 SHA-256；CODEX_HOME 被设成非默认、或存在 AGENTS.override.md → 拒绝（停）；
  model_entry_json() 与隔离参数并入同一指纹。不读 auth.json、logs_2.sqlite，不改 ~/.codex。
"""
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
VS = HERE.parent / "vs-pilot"
sys.path.insert(0, str(VS))
import subject  # noqa: E402  ../vs-pilot/subject.py

OK, CONFIRMED, SUSPECTED, CHECK_FAILED, QUOTA_STOP, CALL_ERROR = (
    "ok", "contaminated_confirmed", "contaminated_suspected", "check_failed", "quota_stop", "call_error")
STOP_STATES = {CHECK_FAILED: True, QUOTA_STOP: False, CALL_ERROR: False}   # 值 = 是否作废会话
VOID_STATES = {CONFIRMED, SUSPECTED}
DISCONNECT = "disconnect"
TOKEN_OVERHEAD = 7300
CHARS_PER_TOKEN_LOW = 3.0
BASELINE_FACTOR = 1.5
DEFAULT_CODEX_HOME = Path.home() / ".codex"


class FreezeError(Exception):
    pass


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def instruction_sources(env=None, default_home=None):
    """实际生效的全局指令来源。只看文件是否存在与哈希，不读其他文件。"""
    env = os.environ if env is None else env
    default_home = Path(default_home) if default_home else DEFAULT_CODEX_HOME
    raw = env.get("CODEX_HOME")
    home = Path(raw) if raw else default_home
    out = {"codex_home_env": raw, "codex_home": str(home),
           "codex_home_is_default": (not raw) or Path(raw).resolve() == default_home.resolve()}
    for name in ("AGENTS.override.md", "AGENTS.md"):
        p = home / name
        out[name] = {"exists": p.is_file(), "sha256": _sha(p.read_bytes()) if p.is_file() else None}
    return out


def check_instruction_sources(src):
    """有 override 或 CODEX_HOME 非默认 → FreezeError（停下回报）。"""
    if not src["codex_home_is_default"]:
        raise FreezeError("CODEX_HOME is not the default: %r" % src["codex_home_env"])
    if src["AGENTS.override.md"]["exists"]:
        raise FreezeError("AGENTS.override.md exists under CODEX_HOME")
    if not src["AGENTS.md"]["exists"]:
        raise FreezeError("AGENTS.md missing under CODEX_HOME (fixed condition changed)")
    return src


def instruction_fingerprint(src):
    return _sha(json.dumps(src, sort_keys=True).encode("utf-8"))


def freeze_codex(exe):
    """运行前冻结。返回 dict；不符即抛异常。"""
    src = check_instruction_sources(instruction_sources())
    fz = subject.freeze(exe)          # 版本、登录（ChatGPT）不符即抛
    entry = subject.model_entry_json(exe)
    return {"exe": fz["exe"], "version": fz["version"], "login": fz["login"], "model": fz["model"],
            "effort": fz["effort"], "isolation_args": list(subject.ISOLATION_ARGS), "rust_log": subject.RUST_LOG,
            "instruction_sources": src, "instruction_fingerprint": instruction_fingerprint(src),
            "model_entry_sha256": _sha(entry.encode("utf-8")), "model_entry": json.loads(entry),
            "subject_py_sha256": _sha((VS / "subject.py").read_bytes())}


def token_baseline(prompt):
    return TOKEN_OVERHEAD + len(prompt) / CHARS_PER_TOKEN_LOW


def final_inclusion(r, prompt, instr_fp_now, instr_fp_frozen, stderr=""):
    """唯一的最终纳入函数。r 是 subject.evaluate（或 subject.call）的返回。
    返回 dict(state, reasons, include, stop, invalidate_session, resample)。"""
    ev, log = r["events"], r["log"]
    if r["quota_hit"]:
        return _st(QUOTA_STOP, ["quota:" + ",".join(r.get("quota_hits", []))])
    if instr_fp_now != instr_fp_frozen:
        return _st(CHECK_FAILED, ["instruction_sources_changed"])
    health = []
    if r["timed_out"]:
        health.append("timed_out")
    if r["returncode"] != 0:
        health.append("returncode=%s" % r["returncode"])
    if ev["failures"]:
        health.append("failure_events=%d" % len(ev["failures"]))
    warnings = [w for w in ev["warnings"] if not _DISCONNECTED.search(w)]
    if warnings:
        health.append("warnings=%s" % warnings)
    if ev["unknown"]:
        health.append("unknown_events=%s" % ev["unknown"])
    if ev["bad_lines"]:
        health.append("bad_lines=%d" % ev["bad_lines"])
    if ev["final_text"] is None:
        health.append("no_final_text")
    confirmed, suspected = [], []
    if log["tool_items"]:
        confirmed.append("log_tool_items=" + ",".join(log["tool_items"]))
    if ev["tool_events"]:
        confirmed.append("json_tool_items=%d" % len(ev["tool_events"]))
    if log["sampling_requests"] > 1:
        suspected.append("sampling_requests=%d" % log["sampling_requests"])
    if len(ev["agent_message_ids"]) > 1:
        suspected.append("agent_messages=%d" % len(ev["agent_message_ids"]))
    inp = (ev.get("usage") or {}).get("input_tokens")
    if inp is not None and inp > BASELINE_FACTOR * token_baseline(prompt):
        suspected.append("input_tokens=%d>%.0f" % (inp, BASELINE_FACTOR * token_baseline(prompt)))
    # a 2026-10-13（正式运行中发现）：连不上服务端、什么都没产生的调用（no_contact）是调用失败，不是完整性异常；
    # 判 call_error（停下、会话不作废、续跑时重做），不再判 check_failed 作废整个会话。
    if is_no_contact(r):
        return _st(CALL_ERROR, ["no_contact"] + health)
    # 完成全部检查后，只豁免可由断线重试解释的计数差与额外采样。
    disconnect = not health and is_disconnect(r, stderr)
    if r["integrity_errors"] and not disconnect:
        return _st(CHECK_FAILED, list(r["integrity_errors"]) + health)
    if health:
        return _st(CALL_ERROR, health)
    if ev["warnings"] and not disconnect:
        return _st(CALL_ERROR, ["warnings=%s" % ev["warnings"]])
    if disconnect:
        suspected = [reason for reason in suspected if not reason.startswith("sampling_requests=")]
    if confirmed:
        return _st(CONFIRMED, confirmed + suspected)
    if suspected:
        return _st(SUSPECTED, suspected)
    if disconnect:
        return _st(DISCONNECT, ["sampling_stream_disconnected"])
    return _st(OK, [])


def _st(state, reasons):
    return {"state": state, "reasons": reasons, "include": state == OK, "stop": state in STOP_STATES,
            "invalidate_session": STOP_STATES.get(state, False), "resample": state in VOID_STATES or state == DISCONNECT}


_ABSENCE = re.compile(r"(log_no_sampling_record|log_no_output_item_record|log_no_turn_completion"
                      r"|event_turn\.completed_count=0|events_no_final_message|o_file_missing"
                      r"|log_last_item_not_message:None)")


def is_no_contact(r):
    """连不上服务端：非零退出、日志里没有任何采样、没有回答、没有工具、没有输出文件，完整性错误全是「缺了什么」。"""
    ev, log = r["events"], r["log"]
    errors = r["integrity_errors"]
    return (r["returncode"] != 0 and not r["quota_hit"] and log["sampling_requests"] == 0
            and not ev["agent_message_ids"] and not ev["tool_events"] and not log["tool_items"]
            and ev["final_text"] is None and not ev["unknown"] and not ev["bad_lines"]
            and bool(errors) and all(_ABSENCE.fullmatch(e) for e in errors)
            # c 第九轮：必须确实没有输出文件，且事件流里除 error 条目外没有任何 item（含 reasoning）。
            and "o_file_missing" in errors
            and set(ev.get("item_types", {})) <= {"error"})


_DISCONNECTED = re.compile(r"stream disconnected|websocket.*(?:disconnect|closed)|connection (?:closed|reset)|reconnecting", re.I)


def is_disconnect(r, stderr):
    """只认客户端诊断与 error 事件，正文中出现断线字样不作为证据。"""
    ev, log = r["events"], r["log"]
    if (r["quota_hit"] or ev["tool_events"] or log["tool_items"]
            or len(ev["agent_message_ids"]) != 1 or ev["unknown"] or ev["bad_lines"]
            or r["timed_out"] or r["returncode"] != 0 or ev["failures"]
            or ev["final_text"] is None):
        return False
    errors = r["integrity_errors"]
    if len(errors) != 1:
        return False
    mismatch = re.fullmatch(r"message_count_log=(\d+)_events=(\d+)", errors[0])
    if not mismatch:
        return False
    diagnostics = []
    for rec, header in subject.records_parsed(stderr):
        if header is None:
            continue
        target, message = header["target"], header["message"]
        if any(target == t and message.startswith(prefix) for t, prefix in subject.CONTENT_TARGETS):
            continue
        if any(target.startswith(t) for t in subject.CONTENT_TARGET_PREFIXES):
            continue
        diagnostics.append(rec)
    retries = sum("retrying sampling request" in d.lower() and bool(_DISCONNECTED.search(d))
                  for d in diagnostics)
    if any(not _DISCONNECTED.search(w) for w in ev["warnings"]):
        return False
    gap = abs(int(mismatch[1]) - int(mismatch[2]))
    return 0 < gap <= retries and log["sampling_requests"] - 1 <= retries


class CodexSubject:
    """跑题脚本用的包装：每次调用保存完整 stdin 提示与检查结果（raw/ 下）。"""

    def __init__(self, rawdir, workroot):
        self.exe = subject.find_codex()
        self.frozen = freeze_codex(self.exe)
        self.rawdir = Path(rawdir)
        self.workroot = Path(workroot)
        self.rawdir.mkdir(parents=True, exist_ok=True)

    def call(self, prompt, tag):
        # Unique even across resumed sessions or colliding sanitized unit names.
        tag = tag + '__' + uuid.uuid4().hex
        (self.rawdir / (tag + ".prompt.txt")).write_text(prompt, encoding="utf-8", newline="\n")
        r = subject.call(self.exe, prompt, self.workroot / tag, self.rawdir, tag)
        now = instruction_fingerprint(instruction_sources())
        stderr = Path(r["files"]["stderr"]).read_text(encoding="utf-8", errors="replace")
        fin = final_inclusion(r, prompt, now, self.frozen["instruction_fingerprint"], stderr)
        check = {"tag": tag, "prompt_sha256": _sha(prompt.encode("utf-8")), "final": fin,
                 "evaluate_ok_not_used": r["ok"], "integrity_errors": r["integrity_errors"],
                 "quota_hits": r["quota_hits"], "sampling_requests": r["log"]["sampling_requests"],
                 "tool_items_log": r["log"]["tool_items"], "tool_events_json": r["events"]["tool_events"],
                 "agent_messages": len(r["events"]["agent_message_ids"]), "usage": r["events"]["usage"],
                 "seconds": r["seconds"], "files": r["files"]}
        (self.rawdir / (tag + ".check.json")).write_text(json.dumps(check, ensure_ascii=False, indent=1),
                                                         encoding="utf-8", newline="\n")
        return {"text": r["text"], "final": fin, "seconds": r["seconds"], "check": check}
