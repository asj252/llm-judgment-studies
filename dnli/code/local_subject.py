"""复制自 ../suppression/local_subject.py（2026-10-12，c 第三至第五轮审过的版本）。除本段说明外逐字未改。
本实验不用答案偏好（AP）：yes_no、score_strings、ap_bounds 保留但不被 run.py 调用。日志目录随文件位置变为 dnli/raw/llama_server。
"""
"""本地受测者（PLAN v0.5 第 3、4、7 节；任务书第 8 步）：llama.cpp（llama-server）+ GGUF Q8_0。

- 权重：由已下载、已核哈希的 safetensors（固定 commit）在本机用 convert_hf_to_gguf.py 转成 Q8_0（convert_gguf.py）；
  GGUF 的 SHA-256 进实验指纹。
- 服务：每个模型起一个 llama-server（127.0.0.1，单槽 --parallel 1，全部层放 GPU），关闭提示缓存（cache_prompt=false），
  逐请求设种子。服务参数、llama.cpp 版本进配置表。
- 提示：用 HF tokenizer 自带的聊天模板渲染（单条 user 消息、无系统提示；Qwen3 用 enable_thinking 硬开关），再用 HF
  tokenizer 编成 token id，以 id 数组送给 /completion——服务端不再套模板、不再分词。GGUF 的词表与 HF 一致由
  verify_vocab() 核对（/detokenize 与 /tokenize 对照）。
- 采样：temperature 0.6、top_k 20、top_p 0.95、min_p 0（Qwen3 官方 thinking 推荐值；三种配置相同）；采样器顺序设为
  temperature → top_k → top_p → min_p（与 transformers 的处理顺序相同）；其余采样器（重复惩罚、DRY、XTC、typical、
  top-n-sigma）显式关闭。
- 截断判定（写死）：服务端报告 stop_type 不是 "eos"（即在 n_predict 内没有产生结束 token）→ truncated；thinking 模式下
  返回的 token 里没有 </think> → thinking_unterminated（也算截断）。
- 答案偏好（yes_no）：在最终答案的第一个位置（关：模板之后；开：先生成，取到 </think> 为止，再接 "<LOCAL_PATH>" 的 token）
  请求 n_predict=1、n_probs=AP_TOPN，读未经采样器处理的概率（post_sampling_probs=false，verify_probs() 核对它与温度无关）。
  Yes、No 的完整串概率 = 首 token 概率 × 串后「边界」概率；边界概率由第二次请求（前缀 + 该 token）的 top-N 里
  边界 token（结束 token，或解码后首字符不是字母数字）的概率和给出，只能覆盖 top-N，覆盖率另记。
"""
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("HF_HOME", r"<LOCAL_PATH>")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

LLAMA_DIR = Path(r"<LOCAL_PATH>")
CUDART_DIR = Path(r"<LOCAL_PATH>")
GGUF_DIR = Path(r"<LOCAL_PATH>")
MODELS = {
    "qwen3-8b": {"repo": "Qwen/Qwen3-8B", "commit": "b968826d9c46dd6066d109eabc6255188de91218", "thinking_switch": True,
                 "gguf": "Qwen3-8B-b968826d-Q8_0.gguf", "ctx": 16384, "max_new_rule": "fixed"},
    "olmo2-7b": {"repo": "allenai/OLMo-2-1124-7B-Instruct", "commit": "470b1fba1ae01581f270116362ee4aa1b97f4c84",
                 "thinking_switch": False, "gguf": "OLMo-2-1124-7B-Instruct-470b1fba-Q8_0.gguf",
                 "ctx": 4096, "max_new_rule": "ctx_minus_prompt"},
}
CONFIGS = {"qwen3-off": ("qwen3-8b", False), "qwen3-on": ("qwen3-8b", True), "olmo2": ("olmo2-7b", None)}
SAMPLING = {"temperature": 0.6, "top_k": 20, "top_p": 0.95, "min_p": 0.0,
            "samplers": ["temperature", "top_k", "top_p", "min_p"],
            "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0, "dry_multiplier": 0.0,
            "xtc_probability": 0.0, "typical_p": 1.0, "top_n_sigma": -1.0}
MAX_NEW_TOKENS = 8192
# 上下文长度与最大输出长度按模型定（a 2026-10-12）：
# - Qwen3-8B：-c 16384，最大输出 8192（固定）。
# - OLMo-2：-c 4096（训练长度；-c 16384 时 KV 缓存约 8 GiB，整卡峰值超过 15 GB，见 config.md 第 4 节），
#   最大输出 = 4096 − 提示 token 数（写死）。性能测量中 OLMo-2 最长输出 317 token。
SERVER_ARGS = ["-ngl", "999", "--parallel", "1", "--host", "127.0.0.1", "--no-webui", "--seed", "0"]


def server_args_for(model_key):
    return ["-c", str(MODELS[model_key]["ctx"])] + SERVER_ARGS


AP_MAX_WIDTH = 0.2


def ap_bounds(cands, cover_first):
    """答案偏好分数的上下界（c 第三轮建议 5）。cands[s] 含 p_first（首位 top-N 里该 token 的概率；不在 top-N 为 None）、
    p_boundary_after_topN（串后 top-N 里边界 token 的概率和）、topN_coverage_after（串后 top-N 的总概率）。
    完整串概率 ∈ [p_first × 边界下界, p_first × (边界下界 + 串后未覆盖质量)]；归一化分数 Yes/(Yes+No) 的界取两端组合。
    候选不在首位 top-N、或界限宽于 AP_MAX_WIDTH → 无效。返回 dict(score_yes_lo, score_yes_hi, valid, invalid_reason)。"""
    if any(cands[s]["p_first"] is None for s in ("Yes", "No")):
        return {"score_yes_lo": None, "score_yes_hi": None, "valid": False, "invalid_reason": "candidate_not_in_topN"}
    lo_, hi_ = {}, {}
    for s in ("Yes", "No"):
        c = cands[s]
        b_lo = c["p_boundary_after_topN"]
        b_hi = min(1.0, b_lo + max(0.0, 1.0 - c["topN_coverage_after"]))
        lo_[s], hi_[s] = c["p_first"] * b_lo, c["p_first"] * b_hi
    if lo_["Yes"] + hi_["No"] <= 0 or hi_["Yes"] + lo_["No"] <= 0:
        return {"score_yes_lo": None, "score_yes_hi": None, "valid": False, "invalid_reason": "zero_mass"}
    lo = lo_["Yes"] / (lo_["Yes"] + hi_["No"])
    hi = hi_["Yes"] / (hi_["Yes"] + lo_["No"])
    ok = (hi - lo) <= AP_MAX_WIDTH
    return {"score_yes_lo": lo, "score_yes_hi": hi, "valid": ok, "invalid_reason": None if ok else "interval_too_wide",
            "first_token_uncovered": max(0.0, 1.0 - cover_first)}


def max_new_for(model_key, n_prompt, fixed=MAX_NEW_TOKENS):
    """写死的最大输出长度：Qwen3 固定 8192；OLMo-2 为 4096 − 提示 token 数。"""
    if MODELS[model_key]["max_new_rule"] == "ctx_minus_prompt":
        return MODELS[model_key]["ctx"] - n_prompt
    return fixed
PRECISION = "GGUF Q8_0 (llama.cpp convert_hf_to_gguf.py --outtype q8_0 from the pinned safetensors)"
AP_TOPN = 100
AP_CANDIDATES = ("Yes", "No")


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def snapshot_path(model_key):
    from huggingface_hub import snapshot_download
    m = MODELS[model_key]
    return snapshot_download(repo_id=m["repo"], revision=m["commit"], local_files_only=True)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class GpuPeak:
    """后台线程每 0.25 秒读一次 nvidia-smi：该进程的显存与整卡占用，取峰值（MiB）。"""

    def __init__(self, pid):
        self.pid, self.proc_peak, self.total_peak = pid, 0, 0
        self._stop = threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        while not self._stop.is_set():
            # 两项分开读：Windows（WDDM）下逐进程显存是 [N/A]，不能让它连累整卡占用的读取
            try:
                out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True,
                                     timeout=10).stdout
                for line in out.strip().splitlines():
                    pid, mem = [x.strip() for x in line.split(",")]
                    if pid.isdigit() and mem.isdigit() and int(pid) == self.pid:
                        self.proc_peak = max(self.proc_peak, int(mem))
            except Exception:  # noqa: BLE001
                pass
            try:
                tot = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=10).stdout.strip()
                self.total_peak = max(self.total_peak, int(tot.splitlines()[0]))
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(0.25)

    def reset(self):
        self.proc_peak, self.total_peak = 0, 0

    def stop(self):
        self._stop.set()


class LocalSubject:
    """一个模型的 llama-server；同一模型的 thinking 开与关共用同一个服务。"""

    def __init__(self, model_key, max_new_tokens=MAX_NEW_TOKENS, logdir=None, gguf_dir=GGUF_DIR,
                 llama_dir=LLAMA_DIR):
        from transformers import AutoTokenizer
        self.model_key = model_key
        self.max_new_tokens = max_new_tokens
        self.path = snapshot_path(model_key)
        self.tok = AutoTokenizer.from_pretrained(self.path)
        self.gguf = Path(gguf_dir) / MODELS[model_key]["gguf"]
        self.exe = Path(llama_dir) / "llama-server.exe"
        self.port = _free_port()
        self.server_args = [str(self.exe), "-m", str(self.gguf), "--port", str(self.port)] + server_args_for(model_key)
        logdir = Path(logdir) if logdir else Path(__file__).resolve().parent / "raw" / "llama_server"
        logdir.mkdir(parents=True, exist_ok=True)
        self.logfile = open(logdir / ("%s_%d.log" % (model_key, int(time.time()))), "wb")
        t0 = time.monotonic()
        env = dict(os.environ)
        env["PATH"] = str(CUDART_DIR) + os.pathsep + env.get("PATH", "")   # cudart64_13 等只对这个子进程
        self.proc = subprocess.Popen(self.server_args, stdin=subprocess.DEVNULL, stdout=self.logfile,
                                     stderr=subprocess.STDOUT, env=env)
        self._wait_ready(600)
        self.load_seconds = round(time.monotonic() - t0, 1)
        self.gpu = GpuPeak(self.proc.pid)
        self.props = self._get("/props")
        self.think_close = self.tok.convert_tokens_to_ids("</think>") if MODELS[model_key]["thinking_switch"] else None
        self.eos_text = None
        self._boundary_cache = {}

    # ---------- HTTP ----------
    def _url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def _get(self, path):
        with urllib.request.urlopen(self._url(path), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path, body, timeout=7200):
        req = urllib.request.Request(self._url(path), data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _wait_ready(self, timeout):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server exited with %s" % self.proc.returncode)
            try:
                if self._get("/health").get("status") == "ok":
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        raise RuntimeError("llama-server not ready")

    def close(self):
        try:
            self.gpu.stop()
        except AttributeError:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.logfile.close()

    # ---------- 模板与核对 ----------
    def render(self, prompt, thinking):
        kw = {}
        if MODELS[self.model_key]["thinking_switch"]:
            kw["enable_thinking"] = bool(thinking)
        elif thinking is not None:
            raise ValueError("this model has no thinking switch")
        return self.tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False,
                                            add_generation_prompt=True, **kw)

    def encode(self, text):
        return self.tok(text, add_special_tokens=False).input_ids

    def verify_vocab(self, texts):
        """对每段文字：HF 的 id 经 /detokenize 还原的文字与 HF decode 相同；服务端 /tokenize（解析特殊 token）的 id 与 HF 相同。"""
        res = []
        for t in texts:
            ids = self.encode(t)
            det = self._post("/detokenize", {"tokens": ids})["content"]
            srv = self._post("/tokenize", {"content": t, "add_special": False, "parse_special": True})["tokens"]
            srv = [x if isinstance(x, int) else x["id"] for x in srv]
            res.append({"n": len(ids), "ids_equal": srv == ids, "detok_equal": det == self.tok.decode(ids)})
        return res

    def config_table(self):
        return {"model_key": self.model_key, "repo": MODELS[self.model_key]["repo"],
                "commit": MODELS[self.model_key]["commit"], "precision": PRECISION, "gguf": self.gguf.name,
                "gguf_sha256": None, "sampling": SAMPLING, "max_new_tokens": self.max_new_tokens,
                "ctx": MODELS[self.model_key]["ctx"], "max_new_rule": MODELS[self.model_key]["max_new_rule"],
                "server_args": server_args_for(self.model_key), "llama_build": self.props.get("build_info"),
                "chat_template_sha256": sha256_text(self.tok.chat_template or ""), "system_prompt": None,
                "think_close_id": self.think_close,
                "truncation_rule": "stop_type != 'eos' -> truncated; thinking mode without </think> token -> "
                                   "thinking_unterminated (counts as truncated)"}

    # ---------- 生成 ----------
    def _complete(self, ids, seed, n_predict, n_probs=0):
        body = {"prompt": ids, "n_predict": n_predict, "seed": seed, "cache_prompt": False, "return_tokens": True,
                "n_probs": n_probs, "post_sampling_probs": False, "stream": False}
        body.update(SAMPLING)
        return self._post("/completion", body)

    def prepare(self, prompt, thinking):
        """渲染、分词、算输出预算（与 bf16_ref.BF16Subject.prepare 同一规则：max_new_for）。"""
        text = self.render(prompt, thinking)
        ids = self.encode(text)
        return text, ids, max_new_for(self.model_key, len(ids), self.max_new_tokens)

    def generate(self, prompt, thinking, seed):
        text, ids, n_predict = self.prepare(prompt, thinking)
        if n_predict <= 0:   # 拒绝非正预算（c 第三轮建议 4）：不调用，记截断
            return {"text": "", "thinking": None, "n_prompt_tokens": len(ids), "n_predict": n_predict,
                    "n_out_tokens": 0, "n_thinking_tokens": 0, "finished_eos": False,
                    "stop_type": "budget_nonpositive", "thinking_closed": None, "truncated": True, "seconds": 0.0,
                    "seed": seed, "template_sha256": sha256_text(text)}
        self.gpu.reset()
        t0 = time.monotonic()
        r = self._complete(ids, seed, n_predict)
        secs = time.monotonic() - t0
        toks = r.get("tokens") or []
        finished = r.get("stop_type") == "eos"
        thinking_text, final_ids, think_ok, n_think = None, toks, True, 0
        if thinking:
            if self.think_close in toks:
                k = toks.index(self.think_close)
                thinking_text = self.tok.decode(toks[:k], skip_special_tokens=False)
                final_ids, n_think = toks[k + 1:], k + 1
            else:
                think_ok, thinking_text, final_ids, n_think = False, self.tok.decode(toks), [], len(toks)
        final = self.tok.decode(final_ids, skip_special_tokens=True)
        return {"text": final, "thinking": thinking_text, "n_prompt_tokens": len(ids), "n_predict": n_predict,
                "n_prompt_evaluated": r.get("tokens_evaluated"), "n_out_tokens": len(toks),
                "n_thinking_tokens": n_think, "finished_eos": finished, "stop_type": r.get("stop_type"),
                "thinking_closed": think_ok if thinking else None, "truncated": (not finished) or (not think_ok),
                "seconds": round(secs, 2), "seed": seed, "template_sha256": sha256_text(text),
                "timings": r.get("timings"), "gpu_proc_peak_mib": self.gpu.proc_peak,
                "gpu_total_peak_mib": self.gpu.total_peak}

    # ---------- 答案偏好 ----------
    def _is_boundary(self, tid, piece):
        if tid in set(self.tok.all_special_ids):
            return True
        return piece == "" or not piece[0].isalnum()

    def _top(self, ids, seed):
        r = self._complete(ids, seed, 1, n_probs=AP_TOPN)
        cp = r["completion_probabilities"][0]
        tops = cp.get("top_logprobs") or cp.get("top_probs") or []
        out = {}
        import math
        for t in tops:
            p = math.exp(t["logprob"]) if "logprob" in t else t["prob"]
            out[int(t["id"])] = p
        return out

    def score_strings(self, prefix, seed):
        top0 = self._top(prefix, seed)
        res, tokenization = {}, {}
        for s in AP_CANDIDATES:
            toks = self.encode(s)
            tokenization[s] = toks
            if len(toks) != 1:
                raise RuntimeError("AP candidate %r is not a single token: %s" % (s, toks))
            p_first = top0.get(toks[0])
            after = self._top(prefix + toks, seed)
            bmass = sum(p for tid, p in after.items() if self._is_boundary(tid, self.tok.decode([tid])))
            res[s] = {"p_first": p_first, "p_boundary_after_topN": bmass, "topN_coverage_after": sum(after.values()),
                      "p_full": (p_first * bmass) if p_first is not None else None}
        py, pn = res["Yes"]["p_full"], res["No"]["p_full"]
        known = [x for x in (res["Yes"]["p_first"], res["No"]["p_first"]) if x is not None]
        top5 = sorted(top0.items(), key=lambda kv: -kv[1])[:5]
        out = {"candidates": res, "tokenization": tokenization,
                "other_mass_first_token": 1.0 - sum(known) if len(known) == 2 else None,
                "topN_coverage_first": sum(top0.values()),
                "score_yes": (py / (py + pn)) if (py is not None and pn is not None and py + pn > 0) else None,
                "top5": [(self.tok.decode([t]), p) for t, p in top5]}
        out.update(ap_bounds(res, out["topN_coverage_first"]))
        return out

    def yes_no(self, prompt, thinking, seed):
        text = self.render(prompt, thinking)
        prefix = self.encode(text)
        self.gpu.reset()
        t0 = time.monotonic()
        n_predict = max_new_for(self.model_key, len(prefix), self.max_new_tokens)
        rec = {"seed": seed, "template_sha256": sha256_text(text), "n_prompt_tokens": len(prefix),
               "n_predict": n_predict if thinking else 1, "n_thinking_tokens": 0, "thinking": None, "truncated": False}
        if n_predict <= 0:
            rec.update({"truncated": True, "stop_type": "budget_nonpositive"})
        elif thinking:
            r = self._complete(prefix, seed, n_predict)
            toks = r.get("tokens") or []
            if self.think_close in toks:
                k = toks.index(self.think_close)
                rec["thinking"] = self.tok.decode(toks[:k], skip_special_tokens=False)
                rec["n_thinking_tokens"] = k + 1
                prefix = prefix + toks[:k + 1] + self.encode("\n\n")
            else:
                rec.update({"thinking": self.tok.decode(toks), "n_thinking_tokens": len(toks), "truncated": True})
        if not rec["truncated"]:
            rec.update(self.score_strings(prefix, seed))
        rec["seconds"] = round(time.monotonic() - t0, 2)
        rec["gpu_proc_peak_mib"] = self.gpu.proc_peak
        rec["gpu_total_peak_mib"] = self.gpu.total_peak
        return rec

    def verify_probs(self, prompt, thinking=None):
        """核对 n_probs 给的是未经采样器处理的分布：温度 0.6 与 1.0 下首 token 的 top 概率应相同。"""
        ids = self.encode(self.render(prompt, thinking))
        outs = []
        for temp in (0.6, 1.0):
            body = {"prompt": ids, "n_predict": 1, "seed": 1, "cache_prompt": False, "n_probs": 10,
                    "post_sampling_probs": False, "stream": False}
            body.update(SAMPLING)
            body["temperature"] = temp
            cp = self._post("/completion", body)["completion_probabilities"][0]
            outs.append({int(t["id"]): t["logprob"] for t in cp["top_logprobs"]})
        common = set(outs[0]) & set(outs[1])
        return {"n_common": len(common), "max_abs_logprob_diff": max(abs(outs[0][i] - outs[1][i]) for i in common)}
