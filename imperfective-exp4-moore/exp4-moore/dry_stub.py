"""Platform-neutral fake subject for Experiment 4 (adapted from exp3-en/dry_stub.py).

Provides deterministic token/probability fixtures and injectable per-unit generation
and scoring failures. Never loads a model.
"""
import json
from host import FakeProcess
from subject import split_stop


class FakeTokenizer:
    chat_template = "DRY: roles followed by content; assistant generation prompt"
    pieces = {1: "True", 2: "False", 3: "Unknown", 4: '"True', 151645: "<|im_end|>", 151643: "<|endoftext|>"}
    eos_token_id, unk_token_id = 151645, None

    def convert_tokens_to_ids(self, token):
        return next((tid for tid, piece in self.pieces.items() if piece == token), None)

    def convert_ids_to_tokens(self, tid):
        return self.pieces.get(tid)

    def encode(self, text, **kwargs):
        ids, i = [], 0
        while i < len(text):
            for tid in (1, 2, 3):
                part = self.pieces[tid]
                if text.startswith(part, i):
                    ids.append(tid)
                    i += len(part)
                    break
            else:
                ids.append(1000 + ord(text[i]))
                i += 1
        return ids

    def decode(self, ids, **kwargs):
        return "".join(self.pieces.get(t, chr(t - 1000) if t >= 1000 else "?") for t in ids)

    def apply_chat_template(self, messages, **kwargs):
        return "\n".join(m["role"] + ": " + m["content"] for m in messages) + "\nassistant: "


def fake_top(mode="full", first=1):
    candidates = [first, 1, 2, 3] if mode == "full" else [first, 1, 2] if mode == "bounded" else []
    ids = list(dict.fromkeys(candidates))
    ids += list(range(90000, 90100 - len(ids)))
    rows = [{"id": tid, "logprob": -1.0 - k / 10, "rank": k + 1} for k, tid in enumerate(ids)]
    if mode == "bad":
        rows = rows[:99]
    return rows


class DrySubject:
    def __init__(self, host, scenarios=None, timeout=lambda: 600, **kwargs):
        self.host, self.scenarios, self.timeout = host, scenarios or {}, timeout
        self.tok, self.proc, self.props = FakeTokenizer(), None, host.identity["service"]
        self.calls, self.score_calls, self.current = [], [], {}

    def start(self, expected_assets, expected_service, **kwargs):
        self.timeout()
        self.proc = FakeProcess()
        if expected_assets != self.host.identity or expected_service != self.props:
            self.close()
            raise ValueError("dry identity mismatch")
        return self

    def close(self):
        if self.proc:
            self.host.terminate(self.proc)

    def generate(self, messages, unit=None):
        self.timeout()
        key = unit["unit_key"] if unit else ""
        scenario = self.scenarios.get(key, {})
        self.current = scenario
        self.calls.append(key)
        if scenario.get("generation_errors", 0) > 0:
            scenario["generation_errors"] -= 1
            raise ConnectionError("injected generation transport failure")
        slot = unit.get("slot", "DUAL_MOORE") if unit else "DUAL_MOORE"
        default_label = "False" if slot in ("DIAG_NEG", "PURE_MOORE") else "True"
        default_prob = "95" if slot == "DIAG_POS" else "5" if slot == "DIAG_NEG" else ("80" if slot in ("DUAL_EXPLICIT", "PURE_READ") else ("65" if slot == "DUAL_MOORE" else "15"))
        label = unit.get("gold_label", default_label) if unit else "True"
        task = unit["task"] if unit else "L"
        prompt = unit["prompt"] if unit else "Z"
        if task == "L":
            text = label if prompt in ("Z", "DAP") else json.dumps(
                {"reasoning": "x", "label": label} if prompt == "CoT" else
                {"possible_interruptions": ["x", "y", "z"], "label": label})
        elif task in ("P", "Ps"):
            text = f"Probability: {default_prob}%"
        else:
            text = "\n".join(f"Estimate {k}: {default_prob}% | Weight: .2" for k in range(1, 6))
        text = scenario.get("text", text)
        ids = self.tok.encode(text)
        if scenario.get("decode_mismatch"):
            ids = [1]
        if scenario.get("offset_token"):
            text, ids = '"True', [4]
        raw = ids + [scenario["stop_token"]] if scenario.get("stop_token") else ids
        truncated = scenario.get("truncated", False)
        ids, stop = split_stop(raw, text, "limit" if truncated else "eos", self.tok)
        return {"text": text, "prompt_ids": self.tok.encode(self.tok.apply_chat_template(messages)),
                "generated_ids": ids, "generated_ids_raw": raw, "stop_token_id": stop,
                "first_topN": fake_top(scenario.get("top_mode", "full"), raw[0] if raw else 1),
                "seconds": 0.001, "n_out_tokens": len(raw), "truncated": truncated}

    def top_at(self, prefix_ids):
        self.timeout()
        self.score_calls.append(list(prefix_ids))
        if self.current.get("score_errors", 0) > 0:
            self.current["score_errors"] -= 1
            raise TimeoutError("injected scoring transport failure")
        return fake_top(self.current.get("top_mode", "full"))

    def verify_vocab(self, texts):
        return {"status": "pass", "checks": [True for _ in texts]}

    def verify_probs(self, messages):
        return {"status": "pass", "max_difference": 0}

    def verify_greedy(self, messages):
        return {"status": "pass", "checks": [True]}
