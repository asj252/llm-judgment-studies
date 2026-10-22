"""δ-NLI 实验 跑题脚本（PLAN v0.2 第 3、4、6 节；任务书第 5 步）。阶段 A 只用替身测通（test_run.py），不跑受测调用。

来源：复制自 ../suppression/run.py（v0.7，经 c 第三至第五轮审过）。沿用：调度（按题交错、固定种子）、续跑、会话登记、
实验指纹、未收尾会话作废、codex 唯一最终纳入（codex_subject.final_inclusion：额度停、检查失效停并作废会话、
污染作废重采一次）、指令来源（AGENTS.md／CODEX_HOME）冻结、正式入口准入。改动：
- 调用单位 unit ＝ (题号, 呈现, 更新类型, 问法, 轮次)：呈现 prior／stated／reported；更新类型 S／W（先验为 '-'）；
  问法 direct／multi；轮次 r0（主）／r1（重复子集再问一轮，只在正式集）。每对每配置 10 个 unit：先验 2 ＋ 后验 2×2×2。
- 删去 E2、AP、t→t、词汇对照、次要样本、smoke 入口与 lexical 审核检查。
- 解析按问法：direct → parse.parse_direct；multi → parse.parse_multi。
- 题目清单 split.json、题面 raw/items_text.json；实验指纹加入「共同材料」：题面文件、清单（含选句 ID）、prompts.py、
  parse.py、模板文字（prompts.templates()）、全部 unit 的渲染提示摘要（materials_digest：dev＋正式＋重复的每个 unit 的
  提示哈希，与配置无关），以及 parse 的规则常量。
- 每条记录带 update_id（所用更新句的 split:line），分析入口逐条核对它与清单一致。

用法（阶段 B，从 PowerShell 调；包装脚本在 ../suppression/llm_python.cmd）：
    ..\\suppression\\llm_python.cmd -I -X utf8 -B run.py <dev|formal> <qwen3-off|olmo2|codex>
    --workers N 默认 1；只有 codex 可大于 1。dispatch_seq 为会话内从 1 开始的发出序号。
重试（PLAN 第 4 节）：解析失败或截断 → 同一提示重新采样一次（新种子）；仍失败记 missing。codex 每次尝试先过
  final_inclusion：污染（确证／疑似）→ 作废重采一次，仍作废记 tool_contaminated；额度 → 停（会话不失效）；
  检查失效 → 停（会话失效）；调用异常 → 停（会话不失效）。解析重试也再走 final_inclusion。两种重试各自最多一次。
  全部尝试保存，不按数值挑选：最终值＝第一个合格尝试的值。
  v0.6：断线重采不占用解析／污染重试次数；同一 unit 连续 3 次断线才停，会话不作废。
续跑：结果文件逐条追加；同一实验指纹、收尾核对通过且未失效的会话里已完成的 unit 跳过。指纹不同 → 在任何调用前拒绝。
  仍为 running 的旧会话一律判作废，其 unit 重排。分析只经 analyse.py（同一套筛选）。
正式入口准入：同一指纹下有已收尾（closed_ok）的 dev 会话，且 dev 全部 unit 已完成。
"""
import argparse
import hashlib
import json
import random
import sys
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from threading import Event, Lock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import parse  # noqa: E402
import prompts  # noqa: E402

CONFIGS = ("qwen3-off", "olmo2", "codex")
LOCAL = {"qwen3-off": ("qwen3-8b", False), "olmo2": ("olmo2-7b", None)}
ASKS = ("direct", "multi")
PRES_POST = ("stated", "reported")
TYPES = ("S", "W")
ROUNDS = ("r0", "r1")
BASE_SEED = {"dev": 20261080, "formal": 20261081}
CONFIG_OFFSET = {"qwen3-off": 0, "olmo2": 2, "codex": 3}
SPLIT_FILE = "split.json"
ITEMS_TEXT = "raw/items_text.json"
CODE_FILES = ("PLAN.md", SPLIT_FILE, "prompts.py", "parse.py", "run.py")
LOCAL_CODE = ("local_subject.py",)
CODEX_CODE = ("codex_subject.py", "../vs-pilot/subject.py")
PARSE_RULES = {"version": parse.PARSE_VERSION, "wsum": [parse.WSUM_LO, parse.WSUM_HI], "n_estimates": parse.N_ESTIMATES,
               "endpoint": [parse.ENDPOINT_LO, parse.ENDPOINT_HI]}


class Stop(Exception):
    def __init__(self, msg, invalidate=False):
        super().__init__(msg)
        self.invalidate = invalidate


def _sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------- 单位与调度 ----------------

def base_units(key, rnd="r0"):
    """一对题的 10 个 unit（先验 2 ＋ 后验 2 类型 × 2 呈现 × 2 问法）。"""
    out = [(key, "prior", "-", a, rnd) for a in ASKS]
    out += [(key, p, t, a, rnd) for p in PRES_POST for t in TYPES for a in ASKS]
    return out


def units_for(item, which, split):
    k = item["key"]
    out = base_units(k, "r0")
    if which == "formal" and k in split["repeat_subset"]:
        out += base_units(k, "r1")
    return out


def make_schedule(items, which, cfg, split):
    """按题交错：先打乱题，再在每题内打乱该题的全部 unit；种子按 (which, 配置) 固定。"""
    rng = random.Random(BASE_SEED[which] * 10 + CONFIG_OFFSET[cfg])
    keys = sorted(planned_items(items, which, cfg))
    rng.shuffle(keys)
    sched = []
    for k in keys:
        us = units_for(items[k], which, split)
        rng.shuffle(us)
        sched.extend(us)
    return sched


def planned_items(items, which, cfg):
    """各配置自己的事先指定集合；codex 正式集严格只含 block A。"""
    if cfg not in CONFIGS:
        raise ValueError(cfg)
    return {k: it for k, it in items.items() if it['use'] == which
            and (which != 'formal' or cfg != 'codex' or it.get('formal_block') == 'A')}


def unit_id(u):
    return "|".join(u)


def call_seed(cfg, u, attempt, which):
    s = "%s|%s|%s|a%d|%d" % (which, cfg, unit_id(u), attempt, BASE_SEED[which])
    return int(_sha(s.encode("utf-8"))[:8], 16)


def render_unit(item, u):
    _, pres, utype, ask, _ = u
    return prompts.render_item(item, pres, utype, ask)


def update_id(item, u):
    return None if u[1] == "prior" else item[u[2] + "_id"]


# ---------------- 实验指纹 ----------------

def materials_digest(all_items, split):
    """全部题（dev＋正式；正式含重复轮）每个 unit 的渲染提示哈希的摘要。与配置、与 which 无关（dev 与正式共用同一指纹）。"""
    rows = []
    for k in sorted(all_items):
        it = all_items[k]
        for u in units_for(it, it["use"], split):
            rows.append([unit_id(u), update_id(it, u), _sha(render_unit(it, u).encode("utf-8"))])
    return _sha(json.dumps(rows, ensure_ascii=False).encode("utf-8")), len(rows)


def fingerprint(base, cfg, subject_meta, all_items, split, items_file=ITEMS_TEXT):
    """subject_meta：本地为 config_table + 库版本；codex 为冻结结果（指令来源指纹、模型条目、版本、隔离参数）。
    共同材料（跨配置必须相同）：items_file、SPLIT_FILE、prompts.py、parse.py、templates、parse_rules、materials_digest。"""
    base = Path(base)
    fp = {}
    files = list(CODE_FILES) + [items_file] + list(LOCAL_CODE if cfg in LOCAL else CODEX_CODE)
    for rel in files:
        fp[rel] = _sha((base / rel).read_bytes())
    fp["templates"] = _sha(json.dumps(prompts.templates(), sort_keys=True, ensure_ascii=False).encode("utf-8"))
    fp["parse_rules"] = _sha(json.dumps(PARSE_RULES, sort_keys=True).encode("utf-8"))
    fp["materials_digest"], fp["n_units_all"] = materials_digest(all_items, split)
    fp["subject_meta"] = _sha(json.dumps(subject_meta, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    fp["config"] = cfg
    return fp, _sha(json.dumps(fp, sort_keys=True).encode("utf-8"))


# ---------------- 单次 unit ----------------

def judge_text(ask, text):
    r = parse.PARSERS[ask](text)
    out = {k: r.get(k) for k in ("value", "error", "forms")}
    if ask == "multi":
        out.update({k: r.get(k) for k in ("estimates", "weights", "weight_sum", "weight_sum_in_tolerance", "endpoint_mass", "weighted_sd")})
    return r["ok"], out


def run_unit(cfg, which, item, u, subj, rawdir):
    """返回结构化记录（不含原文）。subj.attempt(ask, prompt, tag, seed) 返回统一 dict：
    text、truncated、final（codex 的 final_inclusion 结果或本地的 {'state':'ok'}）、meta。"""
    prompt = render_unit(item, u)
    ask = u[3]
    attempts, void_left, retry_left = [], 1, 1
    status, result = None, None
    disconnects = 0
    while True:
        k = len(attempts)
        seed = call_seed(cfg, u, k, which)
        tag = "%s__%s__a%d" % (_safe(unit_id(u)), cfg, k)
        r = subj.attempt(ask, prompt, tag, seed)
        fin = r["final"]
        att = {"attempt": k, "seed": seed, "state": fin["state"], "reasons": fin.get("reasons", []),
               "truncated": r.get("truncated"), "parsed": None, "meta": r.get("meta", {})}
        attempts.append(att)
        if fin["state"] == "disconnect":
            disconnects += 1
            if disconnects >= 3:
                raise Stop("%s: disconnect 3 consecutive attempts" % unit_id(u), False)
            continue
        disconnects = 0
        if fin.get("stop"):
            raise Stop("%s: %s %s" % (unit_id(u), fin["state"], fin.get("reasons")), fin.get("invalidate_session", False))
        if fin.get("resample"):
            if void_left:
                void_left -= 1
                continue
            status = "tool_contaminated"
            break
        if r.get("truncated"):
            ok, pr = False, {"error": "truncated"}
        else:
            ok, pr = judge_text(ask, r["text"])
        att["parsed"] = ok
        att["parse"] = pr
        if ok:
            result = pr
            status = "ok"
            break
        if retry_left:
            retry_left -= 1
            continue
        status = "missing"
        break
    return {"unit": unit_id(u), "key": u[0], "pres": u[1], "utype": u[2], "ask": ask, "round": u[4],
            "update_id": update_id(item, u), "cluster": item["cluster"], "use": item["use"], "config": cfg,
            "status": status, "result": result, "n_attempts": len(attempts), "attempts": attempts,
            "prompt_sha256": _sha(prompt.encode("utf-8"))}


def _safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)[:120]


# ---------------- 会话 ----------------

def load_json(p, default):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save_json(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def load_records(p):
    p = Path(p)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def valid_records(records, sessions, fp_id):
    ok = {s["session_id"] for s in sessions
          if s.get("closed_ok") and not s.get("invalid") and s["fingerprint_id"] == fp_id}
    keep = {}
    for r in records:
        if r.get("session_id") in ok and r.get("fingerprint_id") == fp_id:
            keep[r["unit"]] = r
    return keep


def execute(which, cfg, items, split, subj, fp, fp_id, results_path, meta_path, rawdir, log=print,
            dev_meta_path=None, dev_results_path=None, dev_expected_units=None, extra_meta=None, workers=1):
    validate_workers(cfg, workers)
    sessions = load_json(meta_path, {"sessions": []})["sessions"]
    for s in sessions:
        if s.get("status") == "running":   # 未收尾的旧会话一律作废（分析只认收尾核对通过的会话）
            s.update({"status": "abandoned", "invalid": True, "invalid_reason": "未收尾的旧会话", "closed_ok": False})
    for s in sessions:
        if not s.get("invalid") and s["fingerprint_id"] != fp_id:
            raise Stop("实验指纹与旧会话 %s 不符：%s" % (
                s["session_id"], ", ".join(sorted(k for k in set(fp) | set(s["fingerprint"])
                                                  if fp.get(k) != s["fingerprint"].get(k)))))
    records = load_records(results_path)
    known = {s["session_id"] for s in sessions}
    if any(r.get("session_id") not in known for r in records):
        raise Stop("结果文件里有记录不属于任何已登记会话")
    if which == "formal":
        dsess = load_json(dev_meta_path, {"sessions": []})["sessions"]
        if not any(s.get("closed_ok") and not s.get("invalid") and s["fingerprint_id"] == fp_id for s in dsess):
            raise Stop("没有同一指纹下已收尾的开发集会话")
        dv = valid_records(load_records(dev_results_path), dsess, fp_id)
        if set(dv) != set(dev_expected_units or ()):
            raise Stop("开发集未跑完：缺 %d 个 unit" % len(set(dev_expected_units or ()) - set(dv)))
    done = valid_records(records, sessions, fp_id)
    sched = make_schedule(items, which, cfg, split)
    sess = {"session_id": uuid.uuid4().hex, "which": which, "config": cfg, "fingerprint": fp,
            "fingerprint_id": fp_id, "seed": BASE_SEED[which] * 10 + CONFIG_OFFSET[cfg],
            "schedule_sha256": _sha(json.dumps(sched).encode("utf-8")), "n_schedule": len(sched),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": "running", "invalid": False,
            "closed_ok": False, "stats": {}}
    sess.update(extra_meta or {})
    sess['workers'] = workers
    sessions.append(sess)
    save_json(meta_path, {"sessions": sessions})
    code = 0
    stats = sess["stats"]
    # Workers only evaluate units. Admission and stop notification share a lock;
    # after any Stop is observed by a worker no further unit can be submitted.
    stopped, admission = Event(), Lock()
    pending_units = iter(u for u in sched if unit_id(u) not in done)
    started = time.monotonic()
    n, completed, dispatch_seq = len(done), 0, 0

    def evaluate(u, seq):
        t0 = time.monotonic()
        try:
            rec = run_unit(cfg, which, items[u[0]], u, subj, rawdir)
        except Stop as e:
            with admission:
                stopped.set()
            return e
        rec.update({'wall_seconds': round(time.monotonic() - t0, 2),
                    'dispatch_seq': seq, 'session_id': sess['session_id'], 'fingerprint_id': fp_id})
        return rec

    sess['status'] = 'finished'
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        while True:
            with admission:
                while not stopped.is_set() and len(active) < workers:
                    u = next(pending_units, None)
                    if u is None:
                        break
                    dispatch_seq += 1
                    active[pool.submit(evaluate, u, dispatch_seq)] = dispatch_seq
            if not active:
                break
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            # Process the entire completed batch before considering replenishment.
            for future in sorted(ready, key=active.get):
                active.pop(future)
                rec = future.result()
                if isinstance(rec, Stop):
                    sess['status'] = 'stopped'
                    sess.setdefault('stopped', str(rec))
                    if rec.invalidate:
                        sess['invalid'] = True
                        sess['invalid_reason'] = str(rec)
                    code = 3
                    log('STOP: %s' % rec)
                    continue
                # This code runs only on the calling (main) thread.
                with open(results_path, 'a', encoding='utf-8', newline='\n') as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                n += 1
                completed += 1
                stats[rec['status']] = stats.get(rec['status'], 0) + 1
                log('[%d/%d] %s -> %s (%.1fs)' %
                    (n, len(sched), rec['unit'], rec['status'], rec['wall_seconds']))
                if completed % 50 == 0:
                    elapsed = time.monotonic() - started
                    log('TIMING: %d units completed, elapsed %.1fs, average %.2fs/unit' %
                        (completed, elapsed, elapsed / completed))
    sess["closed_ok"] = not sess["invalid"]
    sess["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save_json(meta_path, {"sessions": sessions})
    return code, sess


# ---------------- 受测者适配 ----------------

def validate_workers(cfg, workers):
    if workers < 1:
        raise Stop('--workers 必须 >= 1')
    if cfg != 'codex' and workers > 1:
        raise Stop('只有 codex 配置允许 --workers > 1（本地只有一张显卡）')

class LocalAdapter:
    def __init__(self, cfg, rawdir, max_new_tokens=None):
        import local_subject as LS
        model_key, self.thinking = LS.CONFIGS[cfg]
        kw = {"max_new_tokens": max_new_tokens} if max_new_tokens else {}
        self.s = LS.LocalSubject(model_key, **kw)
        self.rawdir = Path(rawdir)
        self.rawdir.mkdir(parents=True, exist_ok=True)

    def meta(self):
        """配置表（含 GGUF 的 SHA-256、llama.cpp 构建号、服务参数）与分词所用库的版本。"""
        import transformers
        import tokenizers
        ct = self.s.config_table()
        h = hashlib.sha256()
        with open(self.s.gguf, "rb") as f:
            for b in iter(lambda: f.read(1 << 24), b""):
                h.update(b)
        ct["gguf_sha256"] = h.hexdigest()
        return {"config_table": ct, "thinking": self.thinking,
                "versions": {"transformers": transformers.__version__, "tokenizers": tokenizers.__version__}}

    def attempt(self, ask, prompt, tag, seed):
        r = self.s.generate(prompt, self.thinking, seed)
        (self.rawdir / (tag + ".json")).write_text(json.dumps({"prompt": prompt, **r}, ensure_ascii=False),
                                                   encoding="utf-8")
        meta = {k: r.get(k) for k in ("seconds", "n_out_tokens", "n_thinking_tokens", "n_prompt_tokens",
                                      "n_predict", "stop_type", "gpu_proc_peak_mib", "template_sha256")}
        return {"text": r["text"], "truncated": r["truncated"], "final": {"state": "ok"}, "meta": meta}


class CodexAdapter:
    def __init__(self, rawdir, workroot):
        import codex_subject as CS
        self.CS = CS
        self.s = CS.CodexSubject(rawdir, workroot)

    def meta(self):
        f = dict(self.s.frozen)
        f.pop("model_entry", None)
        return f

    def attempt(self, ask, prompt, tag, seed):
        r = self.s.call(prompt, tag)
        return {"text": r["text"], "truncated": False, "final": r["final"],
                "meta": {"seconds": r["seconds"], "usage": r["check"]["usage"],
                         "sampling_requests": r["check"]["sampling_requests"]}}


def load_all_items(base=HERE):
    """清单里全部题（dev＋正式）及其题面；题面缺题或多题就拒绝。"""
    split = json.loads((Path(base) / SPLIT_FILE).read_text(encoding="utf-8"))
    text = json.loads((Path(base) / ITEMS_TEXT).read_text(encoding="utf-8"))
    keys = {it["key"] for it in split["items"]}
    if set(text) != keys:
        raise Stop("题面与清单的题不一致：%d 对 %d" % (len(text), len(keys)))
    items = {}
    for it in split["items"]:
        t = text[it["key"]]
        if t["S_id"] != it["S"]["id"] or t["W_id"] != it["W"]["id"]:
            raise Stop("题面的选句 ID 与清单不符：%s" % it["key"])
        items[it["key"]] = dict(t, key=it["key"], use=it["use"], cluster=it["cluster"],
                                formal_block=it.get('formal_block') if it['use'] == 'formal' else None)
    return items, split


def load_items(which, base=HERE):
    all_items, split = load_all_items(base)
    return {k: v for k, v in all_items.items() if v["use"] == which}, split, all_items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["dev", "formal"])
    ap.add_argument("config", choices=CONFIGS)
    ap.add_argument('--workers', type=int, default=1)
    a = ap.parse_args()
    subj = None
    try:
        validate_workers(a.config, a.workers)
        items, split, all_items = load_items(a.which)
        rawdir = HERE / "raw" / ("run_%s_%s" % (a.which, a.config))
        if a.config == "codex":
            import os
            subj = CodexAdapter(rawdir, Path(os.environ.get("TEMP") or os.environ["TMP"]) / "dnli-work"
                                / time.strftime("%Y%m%d-%H%M%S"))
        else:
            subj = LocalAdapter(a.config, rawdir)
        meta = subj.meta()
        fp, fp_id = fingerprint(HERE, a.config, meta, all_items, split)
        dev_units = set()
        if a.which == "formal":
            dev_items, _, _ = load_items("dev")
            dev_units = {unit_id(u) for u in make_schedule(dev_items, "dev", a.config, split)}
        code, _ = execute(a.which, a.config, items, split, subj, fp, fp_id,
                          HERE / ("results_%s_%s.jsonl" % (a.which, a.config)),
                          HERE / ("run_meta_%s_%s.json" % (a.which, a.config)), rawdir,
                          dev_meta_path=HERE / ("run_meta_dev_%s.json" % a.config),
                          dev_results_path=HERE / ("results_dev_%s.jsonl" % a.config),
                          dev_expected_units=dev_units, extra_meta={"subject_meta": meta}, workers=a.workers)
    except Stop as e:
        print("REFUSED:", e)
        code = 2
    finally:
        if subj is not None and hasattr(subj, "s") and hasattr(subj.s, "close"):
            subj.s.close()          # 关掉 llama-server 子进程
    sys.exit(code)


if __name__ == "__main__":
    main()
