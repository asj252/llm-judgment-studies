"""REST API subject adapter for un-harnessed δ-NLI runs (pure Python stdlib).

Supports:
- Google AI Studio (`aistudio`): `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- OpenRouter (`openrouter`): `https://openrouter.ai/api/v1/chat/completions`
- Cloudflare Workers AI (`cloudflare`): `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}`
- Colab / Local OpenAI-compatible (`openai_compat`): `{API_BASE_URL}/chat/completions`
"""
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from configs import CONFIGS, SAMPLING, file_config

GEMINI_SAFETY_OFF = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_logprob_metrics(logprobs_obj: dict | None) -> dict | None:
    """Compute sequence NLL and top-K Shannon entropy (in bits) across all tokens and digit tokens."""
    if not isinstance(logprobs_obj, dict):
        return None
    content = logprobs_obj.get("content")
    if not isinstance(content, list) or not content:
        return None

    ln2 = math.log(2.0)
    all_nll: list[float] = []
    all_ent: list[float] = []
    digit_nll: list[float] = []
    digit_ent: list[float] = []

    for tok_info in content:
        if not isinstance(tok_info, dict):
            continue
        lp = tok_info.get("logprob")
        tok_str = str(tok_info.get("token", ""))
        has_digit = any(ch.isdigit() for ch in tok_str)
        if isinstance(lp, (int, float)):
            nll_bits = -float(lp) / ln2
            all_nll.append(nll_bits)
            if has_digit:
                digit_nll.append(nll_bits)

        top_list = tok_info.get("top_logprobs")
        if isinstance(top_list, list) and top_list:
            probs = [
                math.exp(float(item["logprob"]))
                for item in top_list
                if isinstance(item, dict) and isinstance(item.get("logprob"), (int, float))
            ]
            total_p = sum(probs)
            if total_p > 0:
                ent_bits = -sum((p / total_p) * (math.log(p / total_p) / ln2) for p in probs if p > 0)
                all_ent.append(ent_bits)
                if has_digit:
                    digit_ent.append(ent_bits)

    if not all_nll and not all_ent:
        return None

    return {
        "n_tokens": len(all_nll),
        "token_nll_mean_bits": round(sum(all_nll) / len(all_nll), 4) if all_nll else None,
        "token_entropy_mean_bits": round(sum(all_ent) / len(all_ent), 4) if all_ent else None,
        "n_digit_tokens": len(digit_nll),
        "digit_token_nll_mean_bits": round(sum(digit_nll) / len(digit_nll), 4) if digit_nll else None,
        "digit_token_entropy_mean_bits": round(sum(digit_ent) / len(digit_ent), 4) if digit_ent else None,
    }


def _load_default_env() -> None:
    env_file = Path(os.environ.get("DNLI_KEYS_ENV_FILE", ""))
    if os.environ.get("DNLI_KEYS_ENV_FILE") and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def build_request(cfg_name: str, prompt: str, seed: int) -> tuple[str, dict[str, str], bytes]:
    _load_default_env()
    spec = CONFIGS[cfg_name]
    provider = spec["provider"]
    model = spec["model"]

    if provider == "aistudio":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY) in environment")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
        )
        gen_cfg = {
            "temperature": SAMPLING["temperature"],
            "topP": SAMPLING["top_p"],
            "topK": SAMPLING["top_k"],
            "maxOutputTokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if spec.get("thinking_level"):
            gen_cfg["thinkingConfig"] = {"thinkingLevel": spec["thinking_level"]}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
            "safetySettings": GEMINI_SAFETY_OFF,
        }
        headers = {"Content-Type": "application/json"}
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENROUTER_API_KEY in environment")
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "top_k": SAMPLING["top_k"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "cloudflare":
        api_token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_KEY")
        account_id = os.environ.get("CF_ACCOUNT_ID")
        if not api_token or not account_id:
            raise RuntimeError("Missing CF_API_TOKEN (or CLOUDFLARE_API_KEY) or CF_ACCOUNT_ID in environment")
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "top_k": SAMPLING["top_k"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if spec.get("enable_thinking") is False:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "siliconflow":
        sf_free_allowlist = {
            "Qwen/Qwen3-8B",
            "Qwen/Qwen3.5-4B",
            "Qwen/Qwen2.5-7B-Instruct",
            "THUDM/GLM-4-9B-0414",
            "THUDM/GLM-Z1-9B-0414",
            "XingChenAGI/Xing4.0-29B",
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        }
        if model not in sf_free_allowlist:
            raise RuntimeError(f"Paid model {model!r} is strictly forbidden on SiliconFlow free-only lane!")
        api_key = os.environ.get("SILICONFLOW_API_KEY")
        if not api_key:
            raise RuntimeError("Missing SILICONFLOW_API_KEY in environment")
        url = "https://api.siliconflow.cn/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "top_k": SAMPLING["top_k"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if spec.get("enable_thinking") is False:
            payload["enable_thinking"] = False
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "mistral":
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("Missing MISTRAL_API_KEY in environment")
        url = "https://api.mistral.ai/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "random_seed": int(seed) & 0x7FFFFFFF,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GROQ_API_KEY in environment")
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if spec.get("reasoning_effort"):
            payload["reasoning_effort"] = spec["reasoning_effort"]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "modelscope":
        api_key = os.environ.get("MODELSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing MODELSCOPE_API_KEY in environment")
        url = "https://api-inference.modelscope.cn/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if spec.get("enable_thinking") is False:
            payload["enable_thinking"] = False
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "nvidia":
        api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVDIA_API_KEY")
        if not api_key:
            raise RuntimeError("Missing NVIDIA_API_KEY in environment")
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "max_tokens": spec.get("max_output_tokens", SAMPLING["max_output_tokens"]),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if spec.get("enable_thinking") is False:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if spec.get("request_logprobs"):
            payload["logprobs"] = True
            payload["top_logprobs"] = int(spec.get("top_logprobs", 10))
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if provider == "openai_compat":
        base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        api_key = os.environ.get("OPENAI_API_KEY", "local")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SAMPLING["temperature"],
            "top_p": SAMPLING["top_p"],
            "max_tokens": SAMPLING["max_output_tokens"],
            "seed": int(seed) & 0x7FFFFFFF,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if os.environ.get("REQUEST_LOGPROBS", "1") != "0":
            payload["logprobs"] = True
            payload["top_logprobs"] = int(os.environ.get("TOP_LOGPROBS", "20"))
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        return url, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    raise ValueError(f"Unsupported provider: {provider}")


def parse_api_response(provider: str, raw_bytes: bytes) -> dict:
    data = json.loads(raw_bytes.decode("utf-8"))
    if provider == "aistudio":
        candidates = data.get("candidates") or []
        if not candidates:
            block_reason = (data.get("promptFeedback") or {}).get("blockReason")
            return {
                "text": "",
                "truncated": False,
                "reported_model": data.get("modelVersion"),
                "state": "content_blocked" if block_reason else "call_error",
                "reason": block_reason or "no_candidates",
            }
        cand = candidates[0]
        finish = cand.get("finishReason", "")
        parts = (cand.get("content") or {}).get("parts") or []
        # Skip thought parts if any model emits thought=True parts
        text_parts = [p.get("text", "") for p in parts if not p.get("thought")]
        text = "".join(text_parts)
        truncated = finish in ("MAX_TOKENS", "LENGTH")
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST") and not text.strip():
            return {
                "text": "",
                "truncated": False,
                "reported_model": data.get("modelVersion"),
                "state": "content_blocked",
                "reason": finish,
            }
        return {
            "text": text,
            "truncated": truncated,
            "reported_model": data.get("modelVersion"),
            "state": "ok",
            "reason": finish or "STOP",
        }

    if provider in ("openrouter", "openai_compat", "siliconflow", "mistral", "groq", "modelscope", "nvidia"):
        if "error" in data and not data.get("choices"):
            err = data["error"]
            code = err.get("code") if isinstance(err, dict) else None
            msg = str(err)
            is_rate = code in (429, "1300", "1305") or "rate" in msg.lower() or "quota" in msg.lower() or "访问量过大" in msg
            return {
                "text": "",
                "truncated": False,
                "reported_model": data.get("model"),
                "state": "rate_limited" if is_rate else "call_error",
                "reason": msg[:200],
            }
        choices = data.get("choices") or []
        if not choices:
            return {
                "text": "",
                "truncated": False,
                "reported_model": data.get("model"),
                "state": "call_error",
                "reason": "no_choices",
            }
        ch = choices[0]
        msg = ch.get("message") or {}
        raw_content = msg.get("content") or ""
        if isinstance(raw_content, list):
            parts = []
            for block in raw_content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") not in ("thinking", "reasoning"):
                    if isinstance(block.get("text"), str):
                        parts.append(block["text"])
                    elif isinstance(block.get("content"), str):
                        parts.append(block["content"])
            text = "".join(parts)
        else:
            text = str(raw_content)
        finish = ch.get("finish_reason") or ""
        truncated = finish in ("length", "max_tokens")
        lp_metrics = extract_logprob_metrics(ch.get("logprobs"))
        return {
            "text": text,
            "truncated": truncated,
            "reported_model": data.get("model"),
            "logprob_metrics": lp_metrics,
            "state": "ok",
            "reason": finish or "stop",
        }

    if provider == "cloudflare":
        if not data.get("success", True):
            errors = data.get("errors") or []
            msg = json.dumps(errors)
            is_rate = "rate" in msg.lower() or "quota" in msg.lower() or "limit" in msg.lower()
            return {
                "text": "",
                "truncated": False,
                "reported_model": None,
                "state": "rate_limited" if is_rate else "call_error",
                "reason": msg[:200],
            }
        res = data.get("result") or {}
        if isinstance(res, dict) and "choices" in res:
            ch = (res.get("choices") or [{}])[0]
            text = (ch.get("message") or {}).get("content") or ch.get("text") or ""
            finish = ch.get("finish_reason") or ""
        else:
            text = res.get("response") or "" if isinstance(res, dict) else ""
            finish = ""
        return {
            "text": text,
            "truncated": finish in ("length", "max_tokens"),
            "reported_model": None,
            "state": "ok",
            "reason": finish or "stop",
        }

    raise ValueError(f"Unsupported provider: {provider}")


class ApiSubject:
    """Rate-paced REST client that saves raw responses with SHA-256 digests."""

    def __init__(self, cfg_name: str, raw_dir: Path | None = None, sleep_fn=time.sleep, clock_fn=time.monotonic):
        if cfg_name not in CONFIGS:
            raise ValueError(f"Unknown config: {cfg_name}")
        self.cfg_name = cfg_name
        self.spec = CONFIGS[cfg_name]
        self.provider = self.spec["provider"]
        self.min_interval = 60.0 / max(1, self.spec["rpm"])
        self.sleep = sleep_fn
        self.clock = clock_fn
        self._last_call = None
        base_raw = Path(raw_dir) if raw_dir else Path(__file__).resolve().parent / "raw" / file_config(cfg_name)
        self.raw_dir = base_raw
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _pace(self):
        if self._last_call is not None:
            elapsed = self.clock() - self._last_call
            if elapsed < self.min_interval:
                self.sleep(self.min_interval - elapsed)
        self._last_call = self.clock()

    def attempt(self, which: str, unit_str: str, attempt_idx: int, prompt: str, seed: int, timeout: int = 120) -> dict:
        self._pace()
        safe_unit = unit_str.replace("|", "__")
        prefix = self.raw_dir / f"{which}__{safe_unit}__a{attempt_idx}"
        url, headers, body = build_request(self.cfg_name, prompt, seed)
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        t0 = self.clock()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
        except urllib.error.HTTPError as e:
            raw_bytes = e.read() if e.fp else str(e).encode("utf-8")
            status_code = e.code
            elapsed = round(self.clock() - t0, 3)
            resp_path = Path(str(prefix) + ".err.json")
            resp_path.write_bytes(raw_bytes)
            msg = raw_bytes.decode("utf-8", errors="replace")[:300]
            if status_code in (429, 503) or "rate" in msg.lower() or "quota" in msg.lower():
                state = "rate_limited"
            elif status_code in (500, 502, 504):
                state = "disconnect"
            else:
                state = "call_error"
            return {
                "text": "",
                "truncated": False,
                "meta": {
                    "elapsed_s": elapsed,
                    "http_status": status_code,
                    "seed": seed,
                    "raw_prefix": str(prefix),
                    "raw_sha256": {".err.json": _sha(raw_bytes)},
                },
                "final": {
                    "state": state,
                    "reason": f"HTTP {status_code}: {msg}",
                    "stop": state == "call_error",
                    "resample": state == "disconnect",
                },
            }
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            elapsed = round(self.clock() - t0, 3)
            return {
                "text": "",
                "truncated": False,
                "meta": {"elapsed_s": elapsed, "seed": seed},
                "final": {
                    "state": "disconnect",
                    "reason": str(e)[:200],
                    "stop": False,
                    "resample": True,
                },
            }

        elapsed = round(self.clock() - t0, 3)
        resp_path = Path(str(prefix) + ".resp.json")
        resp_path.write_bytes(raw_bytes)
        parsed = parse_api_response(self.provider, raw_bytes)
        state = parsed["state"]
        meta = {
            "elapsed_s": elapsed,
            "http_status": status_code,
            "seed": seed,
            "reported_model": parsed.get("reported_model"),
            "raw_prefix": str(prefix),
            "raw_sha256": {".resp.json": _sha(raw_bytes)},
        }
        if parsed.get("logprob_metrics") is not None:
            meta["logprob_metrics"] = parsed["logprob_metrics"]
        return {
            "text": parsed["text"],
            "truncated": parsed["truncated"],
            "meta": meta,
            "final": {
                "state": state,
                "reason": parsed.get("reason"),
                "stop": state == "call_error",
                "resample": state in ("disconnect", "content_blocked"),
            },
        }
