"""P16.7 model roster fixed by the reviewed task brief."""
TEMPERATURE = 0.0
TOP_P = 1.0
DEFAULT_MAX_TOKENS = 1024
PROVIDERS = {"nv": "nvidia", "aistudio": "aistudio", "groq": "groq",
             "ms": "modelscope", "cf": "cloudflare"}
CONFIGS = {}


def _add(key, model_id, scale, family, rpm, **extra):
    prefix = key.split(":")[0]
    CONFIGS[key] = dict(patrol_provider=prefix, provider_type=PROVIDERS[prefix],
                        model_id=model_id, scale_label=scale, family=family,
                        enable_thinking=False, supports_logprobs=prefix == "nv",
                        top_logprobs=10 if prefix == "nv" else 0,
                        max_tokens=1024, rpm=rpm, min_interval_sec=60.0 / rpm)
    CONFIGS[key].update(extra)


_add("nv:nemotron-3.5-bolt-e4b", "nvidia/nemotron-3.5-bolt-e4b", "4B", "NVIDIA Nemotron-3.5", 30)
_add("nv:nemotron-3.5-lightning-30b", "nvidia/nemotron-3.5-lightning-30b-a3b", "30B-A3B", "NVIDIA Nemotron-3.5", 30)
_add("nv:nemotron-3.5-super-vl-120b", "nvidia/nemotron-3.5-super-vl-120b-a12b", "120B-A12B", "NVIDIA Nemotron-3.5", 30)
_add("nv:nemotron-3-ultra-550b", "nvidia/nemotron-3-ultra-550b-a55b", "550B-A55B", "NVIDIA Nemotron-3", 25)
_add("aistudio:gemma-4-31b-it", "gemma-4-31b-it", "31B", "Google Gemma-4", 15, thinking_level="MINIMAL")
_add("groq:gpt-oss-120b", "openai/gpt-oss-120b", "120B", "OpenAI GPT-OSS", 20,
     enable_thinking=True, reasoning_effort="medium", max_tokens=2048)
PRIMARY_MODELS = tuple(CONFIGS)
_add("ms:deepseek-v4.1-flash", "deepseek-ai/DeepSeek-V4.1-Flash-1017", "Flash", "DeepSeek-V4.1", 20)
_add("cf:qwen3.8-27b", "@cf/qwen/qwen3.8-27b", "27B", "Alibaba Qwen3.8", 30)
ZH_SUPPLEMENT_MODELS = tuple(k for k in CONFIGS if k not in PRIMARY_MODELS)
