"""受测者（codex exec）的调用、事件与日志检查、环境冻结（PLAN v0.8 第 5、8、8.1 节；isolation.md 第 9、10 节）。

run.py 与 probe.py 共用。只用标准库。用 python -I 运行时，调用方须自己把本目录放进 sys.path。
"""
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

EXPECTED_VERSION = "codex-cli 0.162.0-alpha.17.2"
MODEL = "gpt-6.1-sol"
EFFORT = "medium"
AGENTS_MD = Path.home() / ".codex" / "AGENTS.md"

# 隔离组（isolation.md 第 3、7、9 节；推理强度按 PLAN v0.4 起为 medium）
ISOLATION_ARGS = [
    "exec", "--ignore-user-config", "--ignore-rules",  # --ignore-rules：不读 ~/.codex/rules（探针 4 验证：读到 0 个规则文件）
    "-m", MODEL, "-c", 'model_reasoning_effort="%s"' % EFFORT,
    "-s", "read-only", "--ephemeral", "--skip-git-repo-check", "--json",
    "-c", 'web_search="disabled"',
    "-c", "agents.enabled=false",
    "-c", "skills.include_instructions=false",
    "-c", "include_permissions_instructions=false",
    "-c", "include_environment_context=false",
    "-c", "include_apps_instructions=false",
    "-c", "include_collaboration_mode_instructions=false",
    "-c", "project_doc_max_bytes=0",
    "--disable", "multi_agent", "--disable", "apps", "--disable", "plugins",
    "--disable", "memories", "--disable", "skill_search", "--disable", "tool_suggest",
    "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "image_generation",
    "--disable", "browser_use", "--disable", "computer_use", "--disable", "goals",
    "--disable", "sleep_tool", "--disable", "hooks",
    # 第二轮（a 2026-10-11 准）：codex features list 里其余与工具有关、默认开着的开关
    "--disable", "code_mode_host", "--disable", "view_image",
    "--disable", "browser_annotation_api", "--disable", "browser_use_external",
    "--disable", "browser_use_full_cdp_access", "--disable", "in_app_browser",
    "--disable", "in_app_local_automation", "--disable", "remote_plugin", "--disable", "plugin_sharing",
    "--disable", "shell_snapshot", "--disable", "unified_exec_tty", "--disable", "write_stdin_approval",
    "--disable", "skill_mcp_dependency_install", "--disable", "tool_call_mcp_elicitation",
    "--disable", "workspace_dependencies", "--disable", "realtime_conversation",
]

# 调试日志：每次调用只对本进程设 RUST_LOG；codex exec 把日志写到 stderr，call() 把 stderr 存到 raw/ 下被排除的目录
RUST_LOG = "codex_core=trace,codex_exec=debug"

# 事件白名单：只允许这些顶层事件与这些 item 类型；其余一律当作工具事件或异常
OK_EVENT_TYPES = {"thread.started", "turn.started", "turn.completed", "item.started", "item.updated", "item.completed"}
OK_ITEM_TYPES = {"agent_message", "reasoning"}
WARN_ITEM_TYPES = {"error"}  # codex 的配置警告等，以 item 形式出现；不算工具事件
# 允许的固定警告（a 2026-10-11 决定）：gpt-6.1-sol 是 code_mode_only，关掉 code_mode_host 后执行端 fail closed。每次至多 1 条。
ALLOWED_WARNINGS = (re.compile(r"^Code Mode is unavailable because code-mode host is disabled\. Code mode will fail closed"),)
MAX_ALLOWED_WARNINGS = 1
FAIL_EVENT_TYPES = {"turn.failed", "error"}

# 额度、付费、限流、API key 的迹象（出现即停，不改用 API）。不依赖退出码（PLAN v0.8 第 8 节）。
# 扫描范围按来源与内容类型划分，不按日志级别：stderr 先按时间戳切成完整日志记录（续行归入上一条记录），
# 排除内容型记录（提示正文、配置转储、规则转储、模型输出事件），其余记录不论级别都扫（客户端诊断都在其中）；
# 加上 --json 事件流中除 agent_message、reasoning 文字以外的全部内容。
QUOTA_RE = re.compile(
    r"usage limit|rate[ _-]?limit|quota|billing|insufficient[ _](?:quota|credits?|funds)|payment|"
    r"purchase (?:more )?credits|out of credits|api[ _-]?key|\b429\b|too many requests",
    re.IGNORECASE,
)
_TS_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T\S+\s+(TRACE|DEBUG|INFO|WARN|ERROR)\b")
# 日志记录头的结构（照阶段 A 探针的真实日志）：
#   <时间戳> <级别> [<span 链>: ]<target>: <消息>
#   span 链 = 段:段:…，每段是 名字 或 名字{字段}；名字用点不用 ::（如 session_loop、codex.exec、session_init）；
#   字段里可能有带引号的字符串（含空格、冒号、括号）。target 是模块路径（如 codex_core::tools::router、codex_exec）。
# 例：… ERROR session_loop{thread_id=…}:submission_dispatch{otel.name="…" …}:…: codex_core::tools::router: error=…
#     … TRACE thread_spawn{otel.name="thread_spawn"}:session_init: codex_core::session::session: Configuring session: …
#     … DEBUG codex_core::exec_policy: loaded 1 .rules files in …
# 解析：先找第一个不在括号、引号里的「: 」，前面一段记为 head。head 能完整解析成 span 链、且后面紧接「target: 」时，
# head 是 span 链；否则 head 就是 target（模块路径里的 :: 不会被当成 span 分隔符）。
_HDR = re.compile(r"^(\d{4}-\d{2}-\d{2}T\S+)\s+(TRACE|DEBUG|INFO|WARN|ERROR)\s+")
_SPAN_NAME = re.compile(r"[A-Za-z_][\w.]*")
_TARGET_RE = re.compile(r"[A-Za-z_]\w*(?:::\w+)*")
_SPAN_THREAD = re.compile(r'(?:^|[\s{])thread[._]id="?([0-9A-Za-z-]+)"?')


def _skip_braced(text, i):
    """text[i] == '{'。返回配平后 '}' 之后的位置；配不平返回 None。跳过引号内的内容。"""
    depth, inq = 0, False
    while i < len(text):
        ch = text[i]
        if inq:
            if ch == "\\":
                i += 1
            elif ch == '"':
                inq = False
        elif ch == '"':
            inq = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _split_top(text):
    """第一个不在括号、引号里的「: 」的位置；没有返回 -1。"""
    depth, inq, i = 0, False, 0
    while i < len(text) - 1:
        ch = text[i]
        if inq:
            if ch == "\\":
                i += 1
            elif ch == '"':
                inq = False
        elif ch == '"':
            inq = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ":" and depth == 0 and text[i + 1] == " ":
            return i
        i += 1
    return -1


def _parse_span_chain(head):
    """head 若是 span 链，返回 [(名字, 字段文本)]；否则 None。"""
    spans, i = [], 0
    while True:
        m = _SPAN_NAME.match(head, i)
        if not m:
            return None
        name, i = m.group(0), m.end()
        fields = ""
        if i < len(head) and head[i] == "{":
            j = _skip_braced(head, i)
            if j is None:
                return None
            fields, i = head[i + 1:j - 1], j
        spans.append((name, fields))
        if i == len(head):
            return spans
        if head[i] == ":" and not head.startswith("::", i):
            i += 1
            continue
        return None


def parse_header(line):
    """解析一条日志记录的首行。返回 dict(level, spans=[(名字, 字段文本)], target, message)；不合格式返回 None。"""
    m = _HDR.match(line)
    if not m:
        return None
    body = line[m.end():]
    k = _split_top(body)
    if k < 0:
        return None
    head, rest = body[:k], body[k + 2:]
    spans = _parse_span_chain(head)
    if spans is not None:
        k2 = _split_top(rest)
        if k2 > 0 and _TARGET_RE.fullmatch(rest[:k2]):
            return {"level": m.group(2), "spans": spans, "target": rest[:k2], "message": rest[k2 + 2:]}
    if _TARGET_RE.fullmatch(head):
        return {"level": m.group(2), "spans": [], "target": head, "message": rest}
    return None


# 内容型日志记录：正文是提示、配置或模型输出，不是客户端诊断。只按记录头解析出的 target（及该 target 下消息的开头）判定，
# 整条记录（含续行）排除；不在正文里找来源名。依据：阶段 A 探针日志里，额度词只出现在 Configuring session 的配置转储
# （enable_codex_api_key_env）；提示正文在 Submission 记录里（Rust Debug 格式，换行转义成 \n，单行）。
CONTENT_TARGETS = (
    ("codex_core::session::handlers", "Submission sub="),        # 提示转储（UserInput）
    ("codex_core::session::session", "Configuring session"),     # 配置转储
    ("codex_exec", "Codex initialized with event"),              # 配置转储（SessionConfiguredEvent）
    ("codex_core::exec_policy", ""),                             # 命令规则转储（该 target 全部）
)
CONTENT_TARGET_PREFIXES = ("codex_api::sse",)                    # 模型输出的 SSE 事件（若将来提高日志级别）


def records_parsed(stderr_text):
    """[(记录全文, 头解析结果或 None)]。"""
    return [(r, parse_header(r.split("\n", 1)[0])) for r in log_records(stderr_text)]


def find_codex():
    """%LOCALAPPDATA%<LOCAL_PATH> 下同时含 codex.exe 与 codex-code-mode-host.exe 的最新目录。"""
    base = Path(os.environ["LOCALAPPDATA"]) / "OpenAI" / "Codex" / "bin"
    cands = [d for d in base.iterdir()
             if d.is_dir() and (d / "codex.exe").is_file() and (d / "codex-code-mode-host.exe").is_file()]
    if not cands:
        raise RuntimeError("no codex.exe with codex-code-mode-host.exe under " + str(base))
    return max(cands, key=lambda d: d.stat().st_mtime) / "codex.exe"


def default_work_root():
    """每次调用的空工作目录放在 %TEMP%\\vs-pilot-work 下（不在任何 git 仓库里）。"""
    return os.path.join(os.environ.get("TEMP") or os.environ["TMP"], "vs-pilot-work")


INSTRUCTION_FILES = ("AGENTS.md", "AGENTS.override.md", "CLAUDE.md")


def check_workdir_clean(path):
    """工作目录及其所有上层目录都不能有 .git 或指令文件（防止 codex 找到项目根和项目 AGENTS.md）。"""
    p = Path(path).resolve()
    for d in [p] + list(p.parents):
        if (d / ".git").exists():
            raise RuntimeError("work dir is inside a git repo: " + str(d))
        for name in INSTRUCTION_FILES:
            if (d / name).exists():
                raise RuntimeError("instruction file above work dir: " + str(d / name))


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def agents_md_hash():
    return sha256_file(AGENTS_MD)


def _run_small(exe, args, timeout=120):
    r = subprocess.run([str(exe)] + args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def model_entry_json(exe):
    """`codex debug models` 里受测模型的条目（不调用模型），按键排序后的 JSON 字符串；用于实验指纹。"""
    out, _ = _run_small(exe, ["debug", "models"])
    d = json.loads(out.lstrip("﻿"))
    models = d["models"] if isinstance(d, dict) else d
    ent = [m for m in models if isinstance(m, dict) and m.get("slug") == MODEL]
    if len(ent) != 1:
        raise RuntimeError("model entry for %s not found exactly once" % MODEL)
    return json.dumps(ent[0], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def freeze(exe):
    """运行前冻结：版本、登录方式、模型、推理强度、AGENTS.md 哈希。版本或登录不符抛异常。"""
    ver = "".join(_run_small(exe, ["--version"])).strip()
    login = "".join(_run_small(exe, ["login", "status"])).strip()
    if ver != EXPECTED_VERSION:
        raise RuntimeError("codex version changed: %r" % ver)
    if "Logged in using ChatGPT" not in login:
        raise RuntimeError("codex not logged in with ChatGPT: %r" % login)
    return {"exe": str(exe), "version": ver, "login": login, "model": MODEL, "effort": EFFORT,
            "args": ISOLATION_ARGS, "agents_md_sha256": agents_md_hash()}


# ---------------- --json 事件流 ----------------

def check_events(stdout_text):
    """解析 --json 事件流。item 一律按 item ID 去重（同一 message 的 started／updated／completed 只算一次）。
    返回 dict：tool_events、failures、unknown、warnings（不允许的，含固定警告超过 1 条）、allowed_warnings、
    agent_message_ids、item_types（按 ID 去重后的计数）、event_types、n_lines、bad_lines、usage、
    final_text（最后一条完成的 agent_message 文字）、lifecycle_errors、quota_scan_text。"""
    tool, fails, unknown, bad = [], [], [], 0
    warn_by_id, allowed_by_id = {}, {}
    item_type_by_id = {}
    msg_ids = []
    event_types = {}
    usage, final_text, final_id, thread_id = None, None, None, None
    scan_parts = []
    lines = [l for l in stdout_text.splitlines() if l.strip()]
    for n, l in enumerate(lines):
        try:
            e = json.loads(l)
        except ValueError:
            bad += 1
            scan_parts.append(l)
            continue
        t = e.get("type")
        event_types[t] = event_types.get(t, 0) + 1
        if t in FAIL_EVENT_TYPES:
            fails.append(e)
        elif t not in OK_EVENT_TYPES:
            unknown.append(t)
        item = e.get("item")
        if isinstance(item, dict):
            it = item.get("type") or item.get("item_type")
            iid = item.get("id") or ("_line%d" % n)
            item_type_by_id.setdefault(iid, it)
            if it in WARN_ITEM_TYPES:
                msg = item.get("message") or ""
                if any(a.search(msg) for a in ALLOWED_WARNINGS):
                    allowed_by_id[iid] = msg
                else:
                    warn_by_id[iid] = msg
            elif it == "agent_message":
                if iid not in msg_ids:
                    msg_ids.append(iid)
                if t == "item.completed":
                    final_text = item.get("text")
                    final_id = iid
            elif it not in OK_ITEM_TYPES:
                if not any(x["item_id"] == iid for x in tool):
                    tool.append({"event": t, "item_type": it, "item_id": iid})
            # 额度扫描：去掉 agent_message、reasoning 的文字
            if it in ("agent_message", "reasoning"):
                scan_parts.append(json.dumps({k: v for k, v in e.items() if k != "item"}, ensure_ascii=False))
            else:
                scan_parts.append(l)
        else:
            scan_parts.append(l)
        if t == "turn.completed":
            usage = e.get("usage")
        if t == "thread.started":
            thread_id = e.get("thread_id")
    warnings = list(warn_by_id.values())
    allowed = list(allowed_by_id.values())
    if len(allowed) > MAX_ALLOWED_WARNINGS:
        warnings.append("allowed_warning_repeated:%d" % len(allowed))
    lifecycle = []
    for et in ("thread.started", "turn.started", "turn.completed"):
        if event_types.get(et, 0) != 1:
            lifecycle.append("event_%s_count=%d" % (et, event_types.get(et, 0)))
    item_types = {}
    for it in item_type_by_id.values():
        item_types[it] = item_types.get(it, 0) + 1
    return {"tool_events": tool, "failures": fails, "unknown": unknown, "warnings": warnings,
            "allowed_warnings": allowed, "agent_message_ids": msg_ids, "item_types": item_types,
            "event_types": event_types, "n_lines": len(lines), "bad_lines": bad, "usage": usage,
            "final_text": final_text, "final_message_id": final_id, "thread_id": thread_id,
            "lifecycle_errors": lifecycle, "quota_scan_text": "\n".join(scan_parts)}


def final_message(stdout_text):
    """最后一条完成的 agent_message 的文字。"""
    return check_events(stdout_text)["final_text"]


# ---------------- RUST_LOG 日志（主检查） ----------------

_LOG_ITEM = re.compile(r'^Output item item_type="([^"]+)" item_id="([^"]+)"')
_LOG_SAMPLING = re.compile(r"^post sampling token usage .*?model_needs_follow_up=(true|false)")


def check_log(stderr_text):
    """从 RUST_LOG 日志（stderr）找直接证据，并检查日志完整性（PLAN v0.6 第 8.1 节）。
    - 采样请求：每次一行 post sampling token usage（带 model_needs_follow_up）。
    - 输出 item：每个 item 一行或两行 Output item item_type=... item_id=...，按 item_id 去重。
    - turn 完成：最后一次采样的 model_needs_follow_up=false，且有 Agent loop exited。
    reasoning、message 以外的 item 类型（如 custom_tool_call、function_call）都算工具调用（确证污染）。
    integrity_errors 非空即「检查失效」。"""
    items, follow, loop_exited, thread_set = {}, [], False, set()
    for rec, h in records_parsed(stderr_text):
        if h is None:
            continue
        # thread_id 只取 span 字段里的（结构性元数据），正文里的 thread_id= 不算（第四轮阻断 1）
        for _, fields in h["spans"]:
            thread_set.update(_SPAN_THREAD.findall(fields))
        t, msg = h["target"], h["message"]
        if t == "codex_core::stream_events_utils":
            m = _LOG_ITEM.match(msg)
            if m:
                items.setdefault(m.group(2), m.group(1))  # dict 保留首次出现的顺序
        elif t == "codex_core::session::turn":
            m = _LOG_SAMPLING.match(msg)
            if m:
                follow.append(m.group(1) == "true")
        elif t == "codex_core::session::handlers" and msg.startswith("Agent loop exited"):
            loop_exited = True
    types = {}
    for t in items.values():
        types[t] = types.get(t, 0) + 1
    tool_items = sorted(t for t in items.values() if t not in ("reasoning", "message"))
    message_ids = [i for i, t in items.items() if t == "message"]
    thread_ids = sorted(thread_set)
    last_item_type = list(items.values())[-1] if items else None
    errs = []
    if not follow:
        errs.append("log_no_sampling_record")
    if not items:
        errs.append("log_no_output_item_record")
    if not follow or follow[-1] or not loop_exited:
        errs.append("log_no_turn_completion")
    return {"sampling_requests": len(follow), "output_item_types": types, "tool_items": tool_items,
            "message_ids": message_ids, "last_item_type": last_item_type, "loop_exited": loop_exited,
            "log_present": bool(follow), "integrity_errors": errs, "thread_ids": thread_ids}


def log_records(stderr_text):
    """把 stderr 切成完整日志记录：带时间戳的行开始一条记录，之后不带时间戳的行是它的续行。
    第一条时间戳之前的行各自成为一条（客户端直接打印的诊断）。"""
    recs, cur = [], None
    for line in stderr_text.splitlines():
        if _TS_LINE.match(line):
            if cur is not None:
                recs.append(cur)
            cur = [line]
        elif cur is None:
            recs.append([line])
        else:
            cur.append(line)
    if cur is not None:
        recs.append(cur)
    return ["\n".join(r) for r in recs]


def is_content_record(rec, header=None):
    """只按记录头解析出的 target 判定（第四轮阻断 2）；头解析不了的记录不算内容型（照扫）。"""
    h = header if header is not None else parse_header(rec.split("\n", 1)[0])
    if h is None:
        return False
    t, msg = h["target"], h["message"]
    if any(t == ct and msg.startswith(mp) for ct, mp in CONTENT_TARGETS):
        return True
    return any(t == p or t.startswith(p + "::") for p in CONTENT_TARGET_PREFIXES)


def quota_scan(stderr_text, events):
    """额度迹象：stderr 中非内容型的完整日志记录（不论级别）加事件流中除回答文字外的内容。返回命中的片段列表。"""
    parts = [r for r, h in records_parsed(stderr_text) if not is_content_record(r, h)]
    parts.append(events["quota_scan_text"])
    return sorted({m.group(0).lower() for m in QUOTA_RE.finditer("\n".join(parts))})


def message_mapping(events, log):
    """日志与事件流的 message 对应。两边的 ID 不在同一命名空间（日志是响应 ID msg_…，事件流是 exec 自编的 item_N；
    6 次探针的日志与事件流里都没有两者的对照），所以只能按出现顺序一一对应。返回 [(事件 ID, 日志 ID)]，数目不同返回 None。"""
    ev_ids, log_ids = events["agent_message_ids"], log["message_ids"]
    if len(ev_ids) != len(log_ids):
        return None
    return list(zip(ev_ids, log_ids))


def integrity(events, log, o_text):
    """日志完整性四要素与文字一致性（PLAN v0.6 第 8.1 节）。返回错误列表；非空即「检查失效」。
    注：本版本的 RUST_LOG 日志不含 message 正文（6 次探针的日志都查过），所以「日志里最终 message 与 -o 文字一致」
    落实为：日志最后一个输出 item 是 message；日志与事件流的 message 数（按 ID 去重）相同；
    事件流最后一条 agent_message 的文字与 -o 文件文字相同。"""
    errs = list(log["integrity_errors"]) + list(events["lifecycle_errors"])
    if events["final_text"] is None:
        errs.append("events_no_final_message")
    if o_text is None:
        errs.append("o_file_missing")
    elif events["final_text"] is not None and o_text.strip() != events["final_text"].strip():
        errs.append("o_file_text_mismatch")
    if log["last_item_type"] != "message":
        errs.append("log_last_item_not_message:%s" % log["last_item_type"])
    mapping = message_mapping(events, log)
    if mapping is None:
        errs.append("message_count_log=%d_events=%d" % (len(log["message_ids"]), len(events["agent_message_ids"])))
    elif mapping and (mapping[-1][0] != events["final_message_id"] or mapping[-1][1] != log["message_ids"][-1]):
        errs.append("final_message_not_corresponding")
    # 跨来源关联：事件流 thread.started 的 thread_id 必须出现在日志里，且日志里只有这一个 thread_id
    tid = events["thread_id"]
    if not tid:
        errs.append("events_no_thread_id")
    elif log["thread_ids"] != [tid]:
        errs.append("thread_id_mismatch:events=%s_log=%s" % (tid, ",".join(log["thread_ids"]) or "none"))
    return errs


def evaluate(out_s, err_s, o_text, returncode, timed_out):
    """把一次调用的原始输出变成判定。call() 与测试共用。"""
    ev = check_events(out_s)
    log = check_log(err_s)
    integ = integrity(ev, log, o_text)
    quota_hits = quota_scan(err_s, ev)
    ok = (not timed_out and returncode == 0 and not ev["failures"] and not ev["unknown"] and not ev["warnings"]
          and ev["bad_lines"] == 0 and ev["final_text"] is not None)
    return {"ok": ok, "returncode": returncode, "timed_out": timed_out, "events": ev, "log": log,
            "integrity_errors": integ, "quota_hit": bool(quota_hits), "quota_hits": quota_hits,
            "text": ev["final_text"]}


def call(exe, prompt, workdir, outdir, tag, timeout=900):
    """一次独立调用。提示由 stdin 送，写完即关闭 stdin。原始输出存在 outdir（本地、被排除）。"""
    workdir, outdir = Path(workdir), Path(outdir)
    workdir.mkdir(parents=True, exist_ok=False)  # 每次新建的空目录
    check_workdir_clean(workdir)
    outdir.mkdir(parents=True, exist_ok=True)
    last = outdir / (tag + ".last.txt")
    args = [str(exe)] + ISOLATION_ARGS + ["-C", str(workdir), "-o", str(last), "-"]
    env = dict(os.environ)
    env["RUST_LOG"] = RUST_LOG  # 只对这个子进程生效
    t0 = time.monotonic()
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         cwd=str(workdir), env=env)
    try:
        out, err = p.communicate(input=prompt.encode("utf-8"), timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        timed_out = True
    secs = time.monotonic() - t0
    out_s, err_s = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    (outdir / (tag + ".events.jsonl")).write_text(out_s, encoding="utf-8")
    (outdir / (tag + ".stderr.txt")).write_text(err_s, encoding="utf-8")
    o_text = last.read_text(encoding="utf-8", errors="replace") if last.is_file() else None
    r = evaluate(out_s, err_s, o_text, p.returncode, timed_out)
    r["seconds"] = round(secs, 2)
    r["files"] = {"events": str(outdir / (tag + ".events.jsonl")), "stderr": str(outdir / (tag + ".stderr.txt")),
                  "last": str(last)}
    return r
