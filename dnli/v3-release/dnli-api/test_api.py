"""Unit tests for dnli-api (payload construction, response parsing, runner & analysis)."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import api_subject as S
from configs import CONFIGS
import run_api as R


class ApiSubjectTests(unittest.TestCase):
    def test_aistudio_request_and_response(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            url, headers, body = S.build_request("aistudio:gemma-4-31b-it", "Hello?", 42)
        self.assertIn("gemma-4-31b-it:generateContent?key=test-key", url)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["generationConfig"]["temperature"], 0.6)
        self.assertEqual(payload["generationConfig"]["seed"], 42)

        sample_resp = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Thinking...", "thought": True},
                                {"text": "Probability: 75%"},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "modelVersion": "gemma-4-31b-it",
            }
        ).encode("utf-8")
        parsed = S.parse_api_response("aistudio", sample_resp)
        self.assertEqual(parsed["state"], "ok")
        self.assertEqual(parsed["text"], "Probability: 75%")
        self.assertFalse(parsed["truncated"])

    def test_openrouter_and_cloudflare_parsing(self):
        or_resp = json.dumps(
            {
                "model": "qwen/qwen3.8-27b:free",
                "choices": [{"message": {"content": "Probability: 30%"}, "finish_reason": "stop"}],
            }
        ).encode("utf-8")
        parsed = S.parse_api_response("openrouter", or_resp)
        self.assertEqual(parsed["state"], "ok")
        self.assertEqual(parsed["text"], "Probability: 30%")

        cf_resp = json.dumps(
            {
                "success": True,
                "result": {"response": "Estimate 1: 20% | Weight: 0.2\n" * 5},
            }
        ).encode("utf-8")
        parsed_cf = S.parse_api_response("cloudflare", cf_resp)
        self.assertEqual(parsed_cf["state"], "ok")
        self.assertIn("Estimate 1: 20%", parsed_cf["text"])

    def test_judge_text_normalizes_unicode_spaces(self):
        raw_multi = "\n".join(
            f"Estimate\u00a0{i}: {i*10}% | Weight: 0.2" for i in range(1, 6)
        )
        judged = R.judge_text("multi", raw_multi)
        self.assertIsNone(judged["error"])
        self.assertAlmostEqual(judged["value"], 30.0)
        self.assertEqual(len(judged["estimates"]), 5)

    def test_openai_compat_logprob_metrics(self):
        import math
        ln_half = math.log(0.5)
        compat_resp = json.dumps(
            {
                "model": "qwen3-8b",
                "choices": [
                    {
                        "message": {"content": "Probability: 75%"},
                        "finish_reason": "stop",
                        "logprobs": {
                            "content": [
                                {
                                    "token": "Probability: ",
                                    "logprob": 0.0,
                                    "top_logprobs": [{"token": "Probability: ", "logprob": 0.0}],
                                },
                                {
                                    "token": "75",
                                    "logprob": ln_half,
                                    "top_logprobs": [
                                        {"token": "75", "logprob": ln_half},
                                        {"token": "80", "logprob": ln_half},
                                    ],
                                },
                            ]
                        },
                    }
                ],
            }
        ).encode("utf-8")
        parsed = S.parse_api_response("openai_compat", compat_resp)
        self.assertEqual(parsed["state"], "ok")
        lp = parsed["logprob_metrics"]
        self.assertIsNotNone(lp)
        self.assertEqual(lp["n_tokens"], 2)
        self.assertEqual(lp["n_digit_tokens"], 1)
        self.assertAlmostEqual(lp["digit_token_nll_mean_bits"], 1.0, places=4)
        self.assertAlmostEqual(lp["digit_token_entropy_mean_bits"], 1.0, places=4)


if __name__ == "__main__":
    unittest.main()

