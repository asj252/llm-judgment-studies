"""Provider requests and JSON-aware answer normalization. No calls at import."""
import json
import math
import os
from pathlib import Path
import re
import urllib.request
from configs_p167 import TEMPERATURE, TOP_P

KEYS_FILE = Path(os.environ.get("P167_KEYS_ENV_FILE", ""))
KEY_NAMES = {
    "nvidia": ["NVIDIA_API_KEY", "NVDIA_API_KEY"] + [f"NVIDIA_API_KEY_{i}" for i in range(2, 11)],
    "aistudio": ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 11)] + ["GOOGLE_API_KEY"],
    "groq": ["GROQ_API_KEY"] + [f"GROQ_API_KEY_{i}" for i in range(2, 11)],
    "modelscope": ["MODELSCOPE_API_KEY", "MODELSCOPE_SDK_TOKEN"] + [f"MODELSCOPE_API_KEY_{i}" for i in range(2, 11)],
    "cloudflare": ["CF_API_TOKEN", "CLOUDFLARE_API_TOKEN"],
}


def load_keys_env():
    env = {}
    if os.environ.get("P167_KEYS_ENV_FILE") and KEYS_FILE.is_file():
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    env.update(os.environ)
    return env


def build_request_payload(cfg, messages):
    provider = cfg["provider_type"]
    if provider == "aistudio":
        payload = dict(contents=[{"role": "model" if m["role"] == "assistant" else "user",
                                  "parts": [{"text": m["content"]}]}
                                 for m in messages if m["role"] != "system"],
                       generationConfig=dict(temperature=TEMPERATURE, topP=TOP_P,
                                             maxOutputTokens=cfg["max_tokens"],
                                             thinkingConfig={"thinkingLevel": "MINIMAL"}))
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        return payload
    payload = dict(messages=messages, temperature=TEMPERATURE, top_p=TOP_P, max_tokens=cfg["max_tokens"])
    if provider != "cloudflare":
        payload["model"] = cfg["model_id"]
    if provider == "nvidia":
        payload.update(logprobs=True, top_logprobs=10, chat_template_kwargs={"enable_thinking": False})
    elif provider == "groq":
        payload["reasoning_effort"] = cfg["reasoning_effort"]
    elif provider == "modelscope":
        payload["enable_thinking"] = False
    elif provider == "cloudflare":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    else:
        raise ValueError(provider)
    return payload


def _is_valid_json_or_fenced_object(s):
    body = s.strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\s*```", body, re.DOTALL)
    if fence:
        body = fence[1].strip()
    if not (body.startswith("{") and body.endswith("}")):
        return False
    try:
        return isinstance(json.loads(body), dict)
    except (ValueError, TypeError):
        return False


def normalize_answer_text(raw_text):
    if raw_text is None:
        return None, "no_text"
    if _is_valid_json_or_fenced_object(raw_text):
        return raw_text.strip(), None
    for m in re.finditer("</think>", raw_text):
        cand = raw_text[m.end():]
        if _is_valid_json_or_fenced_object(cand):
            return cand.strip(), None
    if "</think>" in raw_text:
        post = raw_text.rsplit("</think>", 1)[1]
        return (None, "thinking_unterminated") if "<think>" in post else (post, None)
    if "<think>" in raw_text:
        return None, "thinking_unterminated"
    return raw_text, None


def parse_api_response(provider, data):
    if provider == "aistudio":
        cand = (data.get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts", [])
        return dict(text="".join(p.get("text", "") for p in parts if not p.get("thought")),
                    truncated=cand.get("finishReason") in ("MAX_TOKENS", "LENGTH"), logprobs=None)
    if provider == "cloudflare":
        if data.get("success") is False:
            raise ValueError("Cloudflare response unsuccessful")
        data = data.get("result", {})
        if "response" in data and not data.get("choices"):
            return dict(text=data["response"], truncated=False, logprobs=None)
    choice = data["choices"][0]
    content = choice.get("message", {}).get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if p.get("type") not in ("thinking", "reasoning"))
    return dict(text=content, truncated=choice.get("finish_reason") in ("length", "max_tokens"),
                logprobs=choice.get("logprobs"))


def extract_logprob_metrics(logprobs, raw_text, clean_text, parsed):
    """Bound True mass at the actual label token, leaving uncaptured mass unknown."""
    content = (logprobs or {}).get("content") or []
    if not content or not clean_text or parsed.get("char_start") is None:
        return None
    start = raw_text.find(clean_text)
    if start < 0:
        return None
    target = start + parsed["char_start"]
    offset = 0
    for token in content:
        end = offset + len(token.get("token", ""))
        if offset <= target < end:
            masses = {"True": 0.0, "False": 0.0, "Unknown": 0.0}
            for alt in token.get("top_logprobs") or []:
                label = alt.get("token", "").strip().strip('"')
                lp = alt.get("logprob")
                if label in masses and isinstance(lp, (int, float)) and math.isfinite(lp):
                    masses[label] += math.exp(lp)
            captured = min(1.0, sum(masses.values()))
            if captured == 0:
                return None
            lower = min(1.0, masses["True"])
            return dict(q_true_lower=lower, q_true_upper=min(1.0, lower + 1.0 - captured),
                        label_mass_captured=captured)
        offset = end
    return None


class APIAdapter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.env = load_keys_env()
        self.keys = list(dict.fromkeys(self.env[n] for n in KEY_NAMES[cfg["provider_type"]] if self.env.get(n)))
        if not self.keys:
            raise ValueError("No provider credentials configured")
        self.cursor = 0

    def generate(self, messages):
        cfg = self.cfg
        provider = cfg["provider_type"]
        key = self.keys[self.cursor % len(self.keys)]
        self.cursor += 1
        headers = {"Content-Type": "application/json"}
        if provider == "aistudio":
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{cfg["model_id"]}:generateContent'
            headers["x-goog-api-key"] = key
        else:
            headers["Authorization"] = "Bearer " + key
            endpoints = {"nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
                         "groq": "https://api.groq.com/openai/v1/chat/completions",
                         "modelscope": "https://api-inference.modelscope.cn/v1/chat/completions"}
            if provider == "cloudflare":
                account = self.env.get("CF_ACCOUNT_ID") or self.env.get("CLOUDFLARE_ACCOUNT_ID")
                if not account:
                    raise ValueError("Missing Cloudflare account ID")
                url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{cfg["model_id"]}'
            else:
                url = endpoints[provider]
        payload = json.dumps(build_request_payload(cfg, messages), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        generated = parse_api_response(provider, data)
        generated["response"] = data
        return generated
