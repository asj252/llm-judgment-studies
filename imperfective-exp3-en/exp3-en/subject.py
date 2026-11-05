"""Platform-independent adaptation of dnli/local_subject.py (2026-10-26) for Experiment 3.

Retains the HF template -> token IDs -> native /completion pipeline and HTTP
endpoints. Host controls process/asset operations; no platform paths or GPU code.
"""
import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from common import RAW_ROOT, digest
from score import validate_top

SAMPLING = {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0,
    "samplers": ["temperature", "top_k"], "repeat_penalty": 1.0,
    "presence_penalty": 0.0, "frequency_penalty": 0.0, "dry_multiplier": 0.0,
    "xtc_probability": 0.0, "typical_p": 1.0, "top_n_sigma": -1.0,
    "mirostat": 0, "dynatemp_range": 0.0}
SEED = 20261091
MAX_TOKENS = 1024
STOP_TOKENS = ("<|im_end|>", "<|endoftext|>")


def extract_top(response):
    """Preserve IDs and raw logprobs; never substitute sampled probabilities."""
    cp = response.get("completion_probabilities")
    if not isinstance(cp, list) or not cp or not isinstance(cp[0], dict):
        return []
    rows = cp[0].get("top_logprobs")
    if rows is None:
        rows = cp[0].get("top_probs", [])
    if not isinstance(rows, list):
        return []
    return [dict(row, rank=row.get("rank", i + 1)) if isinstance(row, dict) else {}
            for i, row in enumerate(rows)]


def stop_token_ids(tok):
    """{eos_token_id} plus those of STOP_TOKENS that this tokenizer really has (fix4)."""
    ids = {tok.eos_token_id} if type(tok.eos_token_id) is int else set()
    for text in STOP_TOKENS:
        tid = tok.convert_tokens_to_ids(text)
        if type(tid) is int and tid != getattr(tok, "unk_token_id", None) and tok.convert_ids_to_tokens(tid) == text:
            ids.add(tid)
    return ids


def _joined(tok, ids):
    return tok.decode(list(ids), skip_special_tokens=False, clean_up_tokenization_spaces=False)


def split_stop(ids, content, stop_type, tok):
    """(content_ids, stop_token_id): llama.cpp returns the final EOS id in tokens but not in content.

    Strip only when the stop was eos, the last id is a stop token, and dropping it makes the
    per-id decode equal content while keeping it does not; otherwise (ids, None).
    """
    ids = list(ids)
    if stop_type != "eos" or not ids or ids[-1] not in stop_token_ids(tok):
        return ids, None
    if _joined(tok, ids[:-1]) == content and _joined(tok, ids) != content:
        return ids[:-1], ids[-1]
    return ids, None


class LlamaServerSubject:
    def __init__(self, model_cfg, host, tokenizer, port, *, process_factory=subprocess.Popen,
                 timeout=lambda: 600.0, logdir=None, evidence=None):
        self.cfg, self.host, self.tok, self.port = model_cfg, host, tokenizer, port
        self.process_factory, self.timeout, self.evidence = process_factory, timeout, evidence
        self.logdir = Path(logdir or RAW_ROOT / "llama_server")
        if not self.logdir.resolve().is_relative_to(RAW_ROOT.resolve()):
            raise ValueError(f"LlamaServerSubject logdir must reside inside {RAW_ROOT}: got {self.logdir}")
        self.proc, self.logfile, self.props = None, None, None
        self.deadline = None
        self._close_lock = threading.Lock()

    def _request(self, path, body=None, timeout=None):
        seconds = self.timeout() if timeout is None else timeout
        if seconds <= 0:
            raise TimeoutError("deadline")
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=seconds) as result:
            raw = result.read()
        if self.evidence:
            self.evidence(path, body, raw)
        return json.loads(raw.decode("utf-8"))

    def start(self, expected_assets, expected_service, ready_timeout=600):
        try:
            if self.host.asset_identity(self.cfg) != expected_assets:
                raise ValueError("asset identity mismatch")
            self.logdir.mkdir(parents=True, exist_ok=True)
            self.logfile = (self.logdir / (str(time.time_ns()) + ".log")).open("wb")
            command, env = self.host.server_command(self.cfg), self.host.server_env()
            self.timeout()
            if self.deadline:
                self.deadline.check()
            self.proc = self.process_factory(command, stdin=subprocess.DEVNULL,
                stdout=self.logfile, stderr=subprocess.STDOUT, env=env)
            if self.deadline:
                self.deadline.attach(self)
                self.deadline.check()
            started = time.monotonic()
            while True:
                if self.proc.poll() is not None:
                    raise ConnectionError("server exited during initialization")
                try:
                    if self._request("/health").get("status") == "ok":
                        break
                except (OSError, ValueError):
                    if time.monotonic() - started >= ready_timeout:
                        raise TimeoutError("server readiness timeout")
                    self.timeout()
                    time.sleep(min(0.05, max(0, ready_timeout - (time.monotonic() - started))))
            self.props = self._request("/props")
            actual = {k: self.props.get(k) for k in expected_service}
            if actual != expected_service:
                raise ValueError("service identity mismatch")
            if self.host.asset_identity(self.cfg) != expected_assets:
                raise ValueError("asset identity changed during initialization")
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        with self._close_lock:
            if self.proc is not None:
                self.host.terminate(self.proc)
            if self.logfile is not None and not self.logfile.closed:
                self.logfile.close()

    def render(self, messages):
        return self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)

    def config_table(self):
        return {"model": self.cfg, "sampling": SAMPLING, "seed": SEED, "max_new_tokens": MAX_TOKENS,
                "cache_prompt": False, "n_probs": 100, "post_sampling_probs": False,
                "enable_thinking": False, "return_tokens": True,
                "truncation_rule": "stop_type != eos"}

    def _complete(self, ids, n_predict, temperature=None):
        body = {"prompt": list(ids), "n_predict": n_predict, "n_probs": 100, "post_sampling_probs": False,
                "return_tokens": True, "cache_prompt": False, "stream": False, "seed": SEED, **SAMPLING}
        if temperature is not None:
            body["temperature"] = temperature
        return self._request("/completion", body)

    def generate(self, messages, **kwargs):
        text = self.render(messages)
        prompt_ids = self.tok.encode(text, add_special_tokens=False)
        started = time.monotonic()
        result = self._complete(prompt_ids, MAX_TOKENS)
        raw = result.get("tokens")
        if not isinstance(raw, list) or not all(type(t) is int for t in raw) or not isinstance(result.get("content"), str):
            raise ValueError("generation response missing content or raw token IDs")
        ids, stop = split_stop(raw, result["content"], result.get("stop_type"), self.tok)
        return {"prompt_ids": prompt_ids, "generated_ids": ids, "generated_ids_raw": raw, "stop_token_id": stop,
                "text": result["content"],
                "first_topN": extract_top(result), "truncated": result.get("stop_type") != "eos",
                "stop_type": result.get("stop_type"), "n_out_tokens": len(raw),
                "seconds": time.monotonic() - started, "raw_response": result, "rendered_sha256": digest(text)}

    def top_at(self, prefix_ids):
        return extract_top(self._complete(prefix_ids, 1))

    def verify_vocab(self, texts):
        rows = []
        for text in texts:
            ids = self.tok.encode(text, add_special_tokens=False)
            decoded = self._request("/detokenize", {"tokens": ids})["content"]
            server = self._request("/tokenize", {"content": text, "add_special": False, "parse_special": True})["tokens"]
            server = [t if isinstance(t, int) else t["id"] for t in server]
            rows.append({"ids_equal": server == ids, "detok_equal": decoded == self.tok.decode(ids)})
        return {"status": "pass" if rows and all(all(r.values()) for r in rows) else "fail", "checks": rows}

    def verify_probs(self, messages):
        ids = self.tok.encode(self.render(messages), add_special_tokens=False)
        tops = [extract_top(self._complete(ids, 1, temperature=t)) for t in (0.0, 1.0)]
        valid = all(validate_top(t) for t in tops)
        a, b = ({r["id"]: r["logprob"] for r in top} for top in tops) if valid else ({}, {})
        delta = max((abs(a[k] - b[k]) for k in a), default=0) if a.keys() == b.keys() else None
        ok = valid and delta is not None and delta <= 1e-4
        return {"status": "pass" if ok else "fail", "max_difference": delta, "topN": tops}

    def verify_greedy(self, messages):
        a, b = self.generate(messages), self.generate(messages)
        ok = (a["generated_ids_raw"] == b["generated_ids_raw"] and bool(a["generated_ids_raw"]) and
              validate_top(a["first_topN"]) and a["generated_ids_raw"][0] == a["first_topN"][0]["id"])
        return {"status": "pass" if ok else "fail", "generations": [a, b]}
