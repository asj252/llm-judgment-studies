"""Native HTTP shapes and lifecycle via loopback fake service / fake processes."""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import ROOT, scratch
from dry_stub import FakeTokenizer, fake_top
from host import FakeHost, FakeProcess
import parse
import score
from subject import MAX_TOKENS, LlamaServerSubject, split_stop, stop_token_ids

CANDIDATES = {"True": [1], "False": [2], "Unknown": [3]}


class HTTPClient(unittest.TestCase):
    def setUp(self):
        self.mode, self.requests = "normal", []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.reply(None)
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.reply(body)
            def reply(self, body):
                owner.requests.append((self.path, body))
                if owner.mode == "timeout":
                    time.sleep(0.12)
                if self.path == "/health":
                    data = {"status": "ok"}
                elif self.path == "/props":
                    data = owner.host.identity["service"]
                elif self.path == "/tokenize":
                    data = {"tokens": owner.tok.encode(body["content"])}
                elif self.path == "/detokenize":
                    data = {"content": owner.tok.decode(body["tokens"])}
                else:
                    data = {"content": "True", "tokens": [1], "stop_type": "eos",
                            "completion_probabilities": [{"top_logprobs": fake_top()}]}
                    if owner.mode == "missing":
                        del data["completion_probabilities"]
                    elif owner.mode == "short":
                        data["completion_probabilities"][0]["top_logprobs"].pop()
                    elif owner.mode == "nonfinite":
                        data["completion_probabilities"][0]["top_logprobs"][0]["logprob"] = float("nan")
                    elif owner.mode == "changed_probs" and body["temperature"] == 1:
                        data["completion_probabilities"][0]["top_logprobs"][0]["logprob"] -= 0.01
                    elif owner.mode == "changed_vocab" and self.path == "/completion":
                        data["tokens"] = [2]
                    elif owner.mode in ("eos", "eos2"):
                        data["tokens"] = [1, 151645 if owner.mode == "eos" else 151643]
                    elif owner.mode == "empty":
                        data.update(content="", tokens=[151645],
                                    completion_probabilities=[{"top_logprobs": fake_top(first=151645)}])
                raw = json.dumps(data).encode("utf-8")
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
        self.host, self.tok = FakeHost(), FakeTokenizer()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.proc = FakeProcess()
        self.scratch = scratch(ROOT / "raw" / "dry" / "http-tests")
        folder = self.scratch.__enter__()
        self.client = LlamaServerSubject({}, self.host, self.tok, self.server.server_port,
            process_factory=lambda *a, **kw: self.proc, logdir=folder)

    def tearDown(self):
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        self.scratch.__exit__(None, None, None)

    def test_endpoints_greedy_payload_and_verifiers(self):
        self.client.start(self.host.identity, self.host.identity["service"])
        messages = [{"role": "system", "content": "logic"}, {"role": "user", "content": "test"}]
        output = self.client.generate(messages)
        self.assertEqual(MAX_TOKENS, 1024)
        self.assertEqual(self.requests[-1][1]["n_predict"], MAX_TOKENS)
        self.assertEqual((output["text"], output["generated_ids"]), ("True", [1]))
        self.assertEqual(len(output["first_topN"]), 100)
        prefix = [8, 9, 10]
        self.client.top_at(prefix)
        path, body = self.requests[-1]
        self.assertEqual((path, body["prompt"], body["n_predict"]), ("/completion", prefix, 1))
        for key, value in (("temperature", 0), ("top_k", 1), ("n_probs", 100), ("post_sampling_probs", False), ("cache_prompt", False)):
            self.assertEqual(body[key], value)
        self.assertEqual(self.client.verify_vocab(["True", "a\n"])["status"], "pass")
        self.assertEqual(self.client.verify_probs(messages)["status"], "pass")
        self.assertEqual(self.client.verify_greedy(messages)["status"], "pass")
        self.mode = "changed_probs"
        self.assertEqual(self.client.verify_probs(messages)["status"], "fail")
        self.mode = "changed_vocab"
        self.assertEqual(self.client.verify_greedy(messages)["status"], "fail")
        self.assertEqual(self.client.config_table()["max_new_tokens"], MAX_TOKENS)

    def test_trailing_stop_token_split_and_located(self):
        messages = [{"role": "user", "content": "x"}]
        for mode, stop in (("eos", 151645), ("eos2", 151643)):
            with self.subTest(mode=mode):
                self.mode = mode
                out = self.client.generate(messages)
                self.assertEqual((out["text"], out["generated_ids"], out["generated_ids_raw"], out["stop_token_id"]),
                                 ("True", [1], [1, stop], stop))
                self.assertEqual(out["n_out_tokens"], 2)
                q = score.locate(out["text"], parse.parse_label_plain(out["text"]), out["prompt_ids"],
                                 out["generated_ids"], self.tok, CANDIDATES, "Z")
                self.assertEqual((q["q_status"], q["j"]), ("ready", 0))
                self.assertEqual(score.locate(out["text"], parse.parse_label_plain(out["text"]), out["prompt_ids"],
                                 out["generated_ids_raw"], self.tok, CANDIDATES, "Z")["q_status"], "missing:decode_mismatch")

    def test_empty_content_stop_only_and_greedy_uses_raw(self):
        self.mode = "empty"
        messages = [{"role": "user", "content": "x"}]
        out = self.client.generate(messages)
        self.assertEqual((out["generated_ids"], out["generated_ids_raw"], out["stop_token_id"]), ([], [151645], 151645))
        result = self.client.verify_greedy(messages)
        self.assertEqual(result["status"], "pass")
        self.mode = "eos"
        self.assertEqual(self.client.verify_greedy(messages)["status"], "pass")

    def test_bad_topN_is_not_silently_zeroed(self):
        from score import score_top
        c = {"True": [1], "False": [2], "Unknown": [3]}
        for mode in ("missing", "short", "nonfinite"):
            self.mode = mode
            result = self.client.generate([{"role": "user", "content": "x"}])
            self.assertEqual(score_top(result["first_topN"], c)["q_status"], "missing:bad_topN")

    def test_timeouts_refused_connection_and_midrun_exit(self):
        self.mode = "timeout"
        with self.assertRaises(OSError):
            self.client._request("/health", timeout=0.01)
        self.mode = "normal"
        self.client.start(self.host.identity, self.host.identity["service"])
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(OSError):
            self.client._request("/health", timeout=0.05)
        self.proc.returncode = 3
        with self.assertRaises(OSError):
            self.client.generate([{"role": "user", "content": "x"}])

    def test_initialization_failure_cleanup_and_idempotence(self):
        for path, fail in (("/health", TimeoutError("not ready")), ("/props", ValueError("bad props"))):
            proc = FakeProcess()
            self.client.process_factory = lambda *a, **kw: proc
            original = self.client._request
            self.client._request = lambda p, *a, **kw: (_ for _ in ()).throw(fail) if p == path else original(p, *a, **kw)
            with self.assertRaises((ValueError, TimeoutError)):
                self.client.start(self.host.identity, self.host.identity["service"], ready_timeout=0)
            self.assertIsNotNone(proc.returncode)
            self.client.close()
            self.assertEqual(proc.terminations, 1)
            self.client._request = original
        proc = FakeProcess()
        self.client.process_factory = lambda *a, **kw: proc
        with self.assertRaises(ValueError):
            self.client.start(self.host.identity, {"build_info": "wrong"})
        self.assertEqual(proc.terminations, 1)
        wrong = {**self.host.identity, "server_sha256": "wrong"}
        with self.assertRaises(ValueError):
            self.client.start(wrong, self.host.identity["service"])
        proc = FakeProcess()
        self.client.process_factory = lambda *a, **kw: proc
        from unittest.mock import patch
        with patch.object(self.host, "asset_identity", side_effect=[self.host.identity, wrong]):
            with self.assertRaises(ValueError):
                self.client.start(self.host.identity, self.host.identity["service"])
        self.assertEqual(proc.terminations, 1)


class SplitStop(unittest.TestCase):
    tok = FakeTokenizer()

    def test_stop_set(self):
        self.assertEqual(stop_token_ids(self.tok), {151645, 151643})
        class Partial(FakeTokenizer):
            def convert_ids_to_tokens(self, tid):
                return "other" if tid == 151643 else super().convert_ids_to_tokens(tid)
        self.assertEqual(stop_token_ids(Partial()), {151645})

    def test_json_prompts_locate_with_raw_prefix(self):
        texts = {"CoT": '{"reasoning": "x", "label": "True"}',
                 "CF": '{"possible_interruptions": ["x", "y", "z"], "label": "True"}'}
        for prompt, text in texts.items():
            with self.subTest(prompt=prompt):
                raw = self.tok.encode(text) + [151645]
                ids, stop = split_stop(raw, text, "eos", self.tok)
                self.assertEqual((ids, stop), (raw[:-1], 151645))
                q = score.locate(text, parse.parse_label_json(text, prompt), [7, 8], ids, self.tok, CANDIDATES, prompt)
                self.assertEqual(q["q_status"], "ready")
                self.assertGreater(q["j"], 0)
                self.assertEqual(q["prefix_ids"], [7, 8] + raw[:q["j"]])

    def test_not_stripped(self):
        cases = {"content_ends_with_stop_text": ([1, 151645], "True<|im_end|>", "eos"),
                 "truncated": ([1, 151645], "True", "limit"),
                 "not_a_stop_token": ([1, 1007], "True", "eos"),
                 "empty": ([], "", "eos")}
        for label, (raw, content, stop_type) in cases.items():
            with self.subTest(label):
                self.assertEqual(split_stop(raw, content, stop_type, self.tok), (raw, None))
        ids, _ = split_stop([1, 1007], "True", "eos", self.tok)
        q = score.locate("True", parse.parse_label_plain("True"), [], ids, self.tok, CANDIDATES, "Z")
        self.assertEqual(q["q_status"], "missing:decode_mismatch")
