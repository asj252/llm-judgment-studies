"""Comprehensive S2 unit test suite for Experiment 4 (English Moorean Paradox) (`exp4-moore/`).

Covers:
1. S0–S1 materials, 17 negative validator mutations, split preservation across 4 domains (`seed = 2026110601`),
   and English prompt/parser v2 compatibility;
2. Offline tokenizer candidate disjointness (`label_tokens_qwen3-8b.json` & Qwen3-8B tokenizer on 480 dev L contexts);
3. Fixed-array unit tests for `_greedy_distinct_1d_sorted`, all 3 Bessel-t factors (`5, 20, 80`),
   all 4 degeneracy branches in `core_e4.py`, certified exact Tango (`E4_H4`), worst-case missingness bounds,
   Holm step-down (`m = 4`), parallel 4-domain breakdown (`D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`),
   and reasoning mechanism text classification;
4. 8-disjoint-condition generator (`X + Y = 100`), `DGP1_emp` complete-cluster filtering & `>= 15` stop-S5 gate,
   all 5 DGPs (`DGP1_emp..DGP5_endpt`) x 4 Cfg = 20 cells, 4-domain fixed quota in `DGP4_het`,
   and deterministic candidate selection/demotion/stop-S5 steps in `calibrate_e4.py`;
5. Full dry-run runner (`smoke` 174 units, `dev` 1,160 units, `determinism` 20 units, `freeze`, `formal` 2-unit `run_stage` + 4,160-unit seeded formal ledger analysis),
   diagnostic `P/Z` gates with 4-domain and per-cluster reporting, fault injection scenarios, ledger recovery,
   and deadline watchdog.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import admission
import calibrate_e4
import check_tokens
import common
from common import RAW_ROOT, ROOT, atomic_json, canonical, digest, read_json, scratch, sha256
import core_e4
from dry_stub import DrySubject, fake_top
import exact_tango_e4
import gates
from ledger import Ledger
import parse
from prompts_e4 import COMBINATIONS, SLOTS, render_unit, verify_parser_compatibility
import protocol
from provenance import load_clusters, load_items, verify_sources
import run
import score
import subject
from validate_materials_e4 import (
    run_negative_mutations,
    validate_materials,
)


@contextmanager
def test_scratch(name: str):
    """Use `RAW_ROOT / 'dry' / name` when writable, or a `/tmp` fallback in read-only sandboxes."""
    probe_dir = RAW_ROOT / "dry"
    can_write_raw = False
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        can_write_raw = os.access(probe_dir, os.W_OK)
    except OSError:
        can_write_raw = False
    if can_write_raw:
        with scratch(probe_dir / name) as base:
            yield base
    else:
        tmp_parent = "/tmp" if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK) else None
        try:
            td_cm = tempfile.TemporaryDirectory(dir=tmp_parent)
        except OSError as exc:
            raise unittest.SkipTest(f"No writable directory available in read-only seatbelt sandbox: {exc}") from exc
        with td_cm as td:
            fake_raw = Path(td) / "raw"
            (fake_raw / "dry").mkdir(parents=True, exist_ok=True)
            with (
                patch.object(common, "RAW_ROOT", fake_raw),
                patch.object(run, "RAW_ROOT", fake_raw),
                patch.object(calibrate_e4, "RAW_ROOT", fake_raw),
                patch.object(subject, "RAW_ROOT", fake_raw),
            ):
                with scratch(fake_raw / "dry" / name) as base:
                    yield base


def make_dry_context(base: Path, cfg: str = "qwen3-8b@dry", host: Any = None) -> run.Context:
    c = run.Context(cfg, dry=True, base=base, host=host)
    run.prepare_dry(c)
    return c


def build_synthetic_stage_rows_e4(
    plan_units: list[dict[str, Any]],
    stage: str,
    *,
    cfg: str = "qwen3-8b@dry",
    fp: str = "0123456789abcdef",
    sid: str = "synth-session",
    run_id: str = "E4-DRY-synth",
    raw: tuple[int, ...] = (1,),
    written_at: str | None = None,
) -> list[dict[str, Any]]:
    rows = []
    ts_val = written_at if written_at is not None else run.timestamp()
    for n, u in enumerate(plan_units, 1):
        slot = u.get("slot", "DUAL_MOORE")
        val = (
            95.0 if slot == "DIAG_POS"
            else 5.0 if slot == "DIAG_NEG"
            else 80.0 if slot in ("DUAL_EXPLICIT", "PURE_READ")
            else 65.0 if slot == "DUAL_MOORE"
            else 15.0  # PURE_MOORE
        )
        lbl = (
            "False" if slot in ("DIAG_NEG", "PURE_MOORE")
            else "True"
        )
        reasoning_text = (
            "The speaker evaluates the canyon glass skywalk across two distinct standards."
            if slot in ("DUAL_MOORE", "DUAL_EXPLICIT")
            else "The speaker states that the load needle points to green."
        )
        rows.append({
            **{k: v for k, v in u.items() if k not in ("premise", "hypothesis")},
            "stage": stage,
            "config": cfg,
            "fingerprint_id": fp,
            "session_id": sid,
            "run_id": run_id,
            "commit_seq": n,
            "written_at": ts_val,
            "first_attempt_ok": True,
            "errors": [],
            "status": "ok",
            "truncated": False,
            "label": lbl if u["task"] == "L" else None,
            "value": None if u["task"] == "L" else val,
            "parsed": (
                {"form": "exact", "label": lbl, "reasoning": reasoning_text}
                if u["task"] == "L"
                else {"ok": True, "value": val, "estimates": [val] * 5, "reasoning": reasoning_text}
            ),
            "protocol": {"protocol_ok": True, "reasons": []},
            "q": {"q_status": "full", "q_L": 0.9, "q_U": 0.9} if u["task"] == "L" else None,
            "generated_ids": [1],
            "generated_ids_raw": list(raw),
            "text": reasoning_text + f" Label: {lbl}",
            "messages": [],
        })
    return rows


def seed_stage_e4(c: run.Context, stage: str, raw: tuple[int, ...] = (1,), written_at: str | None = None) -> tuple[list[dict[str, Any]], Ledger]:
    ledger = Ledger(c.namespace(stage))
    sid = ledger.begin(c.run_id)
    rows = build_synthetic_stage_rows_e4(
        c.plan(stage),
        stage,
        cfg=c.cfg,
        fp=c.fp,
        sid=sid,
        run_id=c.run_id,
        raw=raw,
        written_at=written_at,
    )
    ledger.results.write_bytes(("".join(canonical(r) + "\n" for r in rows)).encode("utf-8"))
    ledger.finish(sid, "complete")
    atomic_json(c.namespace(stage) / "gate.json", c.gate(stage))
    return rows, ledger


class TestMaterialsSplitAndPromptsE4(unittest.TestCase):
    def test_s0_sources_clusters_and_17_mutations(self):
        hashes = verify_sources()
        self.assertIn("clusters_100_e4.json", hashes)
        self.assertIn("exact-tango-tables-e4.npz", hashes)
        clusters_obj = read_json(ROOT / "data" / "clusters_100_e4.json")
        sub_m = read_json(ROOT / "subclasses_e4.json")
        split_m = read_json(ROOT / "split.json")
        self.assertEqual(validate_materials(clusters_obj, sub_m, split_m), [])
        killed = run_negative_mutations(clusters_obj, sub_m, split_m)
        self.assertEqual(killed, 17)

        items = load_items()
        self.assertEqual(len(items), 600)
        self.assertEqual(sum(not i["is_diagnostic"] for i in items), 400)
        self.assertEqual(sum(i["is_diagnostic"] for i in items), 200)

    def test_split_reproducible_and_previews(self):
        split_m = read_json(ROOT / "split.json")
        self.assertEqual(len(split_m["dev"]["cluster_ids"]), 20)
        self.assertEqual(len(split_m["formal"]["cluster_ids"]), 80)
        self.assertTrue(set(split_m["dev"]["cluster_ids"]).isdisjoint(set(split_m["formal"]["cluster_ids"])))
        for dom, cnt in split_m["domain_subclass_counts"]["dev"].items():
            self.assertEqual(cnt, 5)
        for dom, cnt in split_m["domain_subclass_counts"]["formal"].items():
            self.assertEqual(cnt, 20)

        preview_text = (ROOT / "s1_preview_e4.md").read_text(encoding="utf-8")
        self.assertIn("### 簇 `002`", preview_text)
        self.assertIn("### 簇 `003`", preview_text)

    def test_prompts_and_parser_v2_compatibility(self):
        verify_parser_compatibility()
        for task, prompt in COMBINATIONS:
            msgs = render_unit(
                "The canyon glass skywalk is safe.",
                "The canyon glass skywalk is safe under the current cliffside anchor conditions.",
                task,
                prompt,
            )
            expected_roles = ["system", "user"] if task in ("L", "Ps") else ["user"]
            self.assertEqual([m["role"] for m in msgs], expected_roles)
        with self.assertRaises(ValueError):
            render_unit("Premise.", "Hypothesis.", "Ps", "CoT")


class TestTokensParseProtocolAndScoreE4(unittest.TestCase):
    def test_frozen_token_sets_disjoint_and_real_tokenizer_if_cached(self):
        frozen = read_json(ROOT / "label_tokens_qwen3-8b.json")
        assets = read_json(ROOT / "config_assets_macmini-m6.json")["models"]["qwen3-8b"]
        self.assertTrue(check_tokens.validate_frozen_structure(frozen, "qwen3-8b", assets))
        hf_candidates = [
            os.environ.get("HF_HOME"),
            "/Volumes/2026General_Space/imperfective/hf",
        ]
        hf_path = next(
            (
                Path(p)
                for p in hf_candidates
                if p
                and (
                    Path(p)
                    / "hub"
                    / "models--Qwen--Qwen3-8B"
                    / "snapshots"
                    / "b968826d9c46dd6066d109eabc6255188de91218"
                    / "tokenizer.json"
                ).is_file()
            ),
            None,
        )
        if hf_path is None:
            self.skipTest("Qwen3-8B tokenizer cache not found in HF_HOME or /Volumes/2026General_Space/imperfective/hf")
        env_patch = {
            "HF_HOME": str(hf_path),
            "HF_HUB_CACHE": str(hf_path / "hub"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK):
            env_patch["TMPDIR"] = "/tmp"
            tempfile.tempdir = "/tmp"
        with patch.dict(os.environ, env_patch):
            tok, hashes = check_tokens.load_tokenizer()
            check_tokens.validate_frozen(tok, hashes, frozen, "qwen3-8b", assets)
            report = check_tokens.check_all(tok, hashes)
            self.assertEqual((report["status"], report["context_count"], report["not_applicable"]), ("pass", 480, 0))
            self.assertEqual(report["sets"], frozen["sets"])

            utf8_text = '{"reasoning":"The speaker evaluates the canyon glass skywalk across two distinct standards. 🌉","label":"True"}'
            parsed_u = parse.parse_label_json(utf8_text)
            self.assertTrue(protocol.check(utf8_text, "L", "CoT", parsed_u)["protocol_ok"])
            gen_ids = tok.encode(utf8_text, add_special_tokens=False)
            loc_u = score.locate(utf8_text, parsed_u, [10, 20], gen_ids, tok, frozen["sets"], "CoT")
            self.assertEqual(loc_u["q_status"], "ready")
            self.assertIn(gen_ids[loc_u["j"]], frozen["sets"]["True"])
            eos_id = tok.eos_token_id
            stripped_ids, stop_id = subject.split_stop(gen_ids + [eos_id], utf8_text, "eos", tok)
            self.assertEqual((stripped_ids, stop_id), (gen_ids, eos_id))

            # Also explicitly verify _ReadOnlyFastTokenizer fallback (including convert_tokens_to_ids / convert_ids_to_tokens / split_stop)
            snap_dir = hf_path / "hub" / "models--Qwen--Qwen3-8B" / "snapshots" / "b968826d9c46dd6066d109eabc6255188de91218"
            ro_tok = check_tokens._ReadOnlyFastTokenizer(snap_dir)
            check_tokens.validate_frozen(ro_tok, hashes, frozen, "qwen3-8b", assets)
            ro_stripped, ro_stop = subject.split_stop(gen_ids + [ro_tok.eos_token_id], utf8_text, "eos", ro_tok)
            self.assertEqual((ro_stripped, ro_stop), (gen_ids, ro_tok.eos_token_id))

    def test_score_top_bounds(self):
        c = {"True": [1, 4], "False": [2], "Unknown": [3]}
        top_full = fake_top("full", first=1)
        res_bounded = score.score_top(top_full, c)
        self.assertEqual(res_bounded["q_status"], "bounded")
        self.assertLess(res_bounded["q_L"], res_bounded["q_U"])
        c_exact = {"True": [1], "False": [2], "Unknown": [3]}
        res_full = score.score_top(top_full, c_exact)
        self.assertEqual(res_full["q_status"], "full")
        self.assertAlmostEqual(res_full["q_L"], res_full["q_U"], places=12)
        self.assertEqual(score.score_top(fake_top("none"), c_exact)["q_status"], "missing:none_in_topN")
        self.assertEqual(score.score_top(fake_top("bad"), c_exact)["q_status"], "missing:bad_topN")


class TestCoreE4AndDegeneracyRules(unittest.TestCase):
    def test_bessel_t_constants_and_order_stat_indices(self):
        self.assertEqual(set(core_e4.EXPECTED_BESSEL_T_FACTORS.keys()), {5, 20, 80})
        for n, expected in core_e4.EXPECTED_BESSEL_T_FACTORS.items():
            self.assertAlmostEqual(core_e4.BESSEL_T_FACTORS_BY_N[n], expected, places=15)
        self.assertEqual(core_e4._order_stat_indices(5000, 0.0125), (31, 4968))
        self.assertEqual(core_e4._order_stat_indices(5000, 0.05), (124, 4875))

    def test_greedy_distinct_and_all_four_degeneracy_rules(self):
        self.assertEqual(core_e4._greedy_distinct_1d_sorted(np.array([], dtype=np.float64)), 0)
        self.assertEqual(core_e4._greedy_distinct_1d_sorted(np.array([1.0, np.nan], dtype=np.float64)), 0)
        self.assertEqual(core_e4._greedy_distinct_1d_sorted(np.zeros(80, dtype=np.float64)), 1)
        arr_chain = np.array([0.0, 0.6e-12, 1.2e-12], dtype=np.float64)
        self.assertEqual(core_e4._greedy_distinct_1d_sorted(arr_chain), 2)

        w_80 = core_e4.draw_cluster_bootstrap_weights_e4(80, b=5000, seed=core_e4.FORMAL_ANALYSIS_SEED_E4)

        # Rule 1: Constant array -> u_low = u_high = 1 < 20
        d_const = np.full(80, 20.0, dtype=np.float64)
        res_r1 = core_e4.infer_continuous_slot_e4(d_const, d_const, w_80, method="pct")
        self.assertTrue(res_r1["degenerate"])
        self.assertIn("insufficient_distinct_draws", res_r1["degeneracy_reasons"])
        self.assertEqual((res_r1["p"], res_r1["ci_9875"]), (1.0, [-100.0, 100.0]))

        # Rule 2: Zero quantile span while u_low >= 20
        w_span = np.zeros((5000, 80), dtype=np.float64)
        for b_idx in range(31):
            frac = float(b_idx + 1) / 32.0
            w_span[b_idx, 0] = frac
            w_span[b_idx, 1] = 1.0 - frac
        w_span[31:4969, 40] = 1.0
        for idx_tail, b_idx in enumerate(range(4969, 5000), start=1):
            frac = float(idx_tail) / 32.0
            w_span[b_idx, 78] = frac
            w_span[b_idx, 79] = 1.0 - frac
        d_inc = np.linspace(-40.0, 60.0, 80, dtype=np.float64)
        d_inc[40] = 10.0
        res_r2 = core_e4.infer_continuous_slot_e4(d_inc, d_inc, w_span, method="pct")
        self.assertTrue(res_r2["degenerate"])
        self.assertIn("zero_quantile_span", res_r2["degeneracy_reasons"])
        self.assertEqual((res_r2["p"], res_r2["ci_9875"]), (1.0, [-100.0, 100.0]))

        # Rule 3: Inverted CI
        d_lo_inv = np.linspace(20.0, 60.0, 80, dtype=np.float64)
        d_hi_inv = np.linspace(-60.0, -20.0, 80, dtype=np.float64)
        res_r3 = core_e4.infer_continuous_slot_e4(d_lo_inv, d_hi_inv, w_80, method="pct")
        self.assertTrue(res_r3["degenerate"])
        self.assertEqual(res_r3["degeneracy_reasons"], ["invalid_or_inverted_ci"])

        # Rule 4: Bessel-t unclipped raw CI completely outside [-100, 100]
        d_out = np.linspace(102.0, 110.0, 80, dtype=np.float64)
        res_r4 = core_e4.infer_continuous_slot_e4(d_out, d_out, w_80, method="bessel_t")
        self.assertTrue(res_r4["degenerate"])
        self.assertIn("out_of_domain_unclipped_ci", res_r4["degeneracy_reasons"])

    def test_exact_tango_all_3_ns_and_holm_step_down(self):
        for n in exact_tango_e4.SUPPORTED_NS:
            d4 = np.array([1] * n, dtype=np.int64)
            res = core_e4.infer_discrete_slot_e4(d4, d4, one_sided=True)
            self.assertEqual(res["n"], n)
            self.assertLess(res["p"], 0.05)

        holm = core_e4.holm_step_down_e4({"E4_H1": 0.010, "E4_H2": 0.010, "E4_H3": 0.020, "E4_H4": 0.001})
        self.assertEqual(holm["E4_H4"]["step"], 1)
        self.assertEqual(holm["E4_H1"]["step"], 2)
        self.assertEqual(holm["E4_H2"]["step"], 3)
        self.assertEqual(holm["E4_H3"]["step"], 4)
        self.assertTrue(all(holm[k]["rejected"] for k in core_e4.E4_SLOT_ORDER))

    def test_reasoning_mechanism_classifier(self):
        # 1. Affirmative textbook Moorean / single-standard reflex
        t1 = "This statement is a classic Moore's paradox: one cannot assert p and believe not p."
        c1 = core_e4.classify_reasoning_text_e4(t1)
        self.assertTrue(c1["textbook_single_standard_reflex"])
        self.assertFalse(c1["dual_criteria_or_polysemy_detected"])

        # 2. Affirmative dual criteria / polysemy decomposition
        t2 = "The speaker distinguishes between two distinct standards: local technical compliance vs global substantive risk."
        c2 = core_e4.classify_reasoning_text_e4(t2)
        self.assertFalse(c2["textbook_single_standard_reflex"])
        self.assertTrue(c2["dual_criteria_or_polysemy_detected"])

        # 3. Concessive refutation of paradox followed by dual criteria -> textbook=False, dual_criteria=True
        t3 = "Although it resembles a paradox, there are two distinct perspectives: procedural checklist versus actual environmental hazard."
        c3 = core_e4.classify_reasoning_text_e4(t3)
        self.assertFalse(c3["textbook_single_standard_reflex"])
        self.assertTrue(c3["dual_criteria_or_polysemy_detected"])

        # 4. Negated contradiction -> textbook=False, dual_criteria=False
        t_neg = "There is no self-contradiction."
        c_neg = core_e4.classify_reasoning_text_e4(t_neg)
        self.assertFalse(c_neg["textbook_single_standard_reflex"])
        self.assertFalse(c_neg["dual_criteria_or_polysemy_detected"])

        # 5. Speech-act cancellation ("reading a script") -> must NOT trigger dual_criteria_or_polysemy_detected
        t_read = "The speaker is merely reading a script."
        c_read = core_e4.classify_reasoning_text_e4(t_read)
        self.assertFalse(c_read["textbook_single_standard_reflex"])
        self.assertFalse(c_read["dual_criteria_or_polysemy_detected"])

        # 6. Both affirmative textbook reflex and dual criteria in separate clauses
        t_both = (
            "First, under a single standard this is Moore's paradox because one cannot assert p and disbelieve p; "
            "second, another interpretation separates local checklist compliance from global environmental safety."
        )
        c_both = core_e4.classify_reasoning_text_e4(t_both)
        self.assertTrue(c_both["textbook_single_standard_reflex"])
        self.assertTrue(c_both["dual_criteria_or_polysemy_detected"])

        # 7. Irrelevant text
        t4 = "The sky is blue."
        c4 = core_e4.classify_reasoning_text_e4(t4)
        self.assertFalse(c4["textbook_single_standard_reflex"])
        self.assertFalse(c4["dual_criteria_or_polysemy_detected"])

        # 8. Critic c Round 2 Blocker 1 edge cases:
        # 8a. Negated bare polysemy ("There is no polysemy.") -> both False
        c_no_poly = core_e4.classify_reasoning_text_e4("There is no polysemy.")
        self.assertEqual(
            c_no_poly,
            {"textbook_single_standard_reflex": False, "dual_criteria_or_polysemy_detected": False},
        )
        # 8b. Negated local-vs-global pair + single standard -> both False
        c_no_lvg = core_e4.classify_reasoning_text_e4(
            "The speaker is not using local technical and global substantive standards; there is only one standard."
        )
        self.assertEqual(
            c_no_lvg,
            {"textbook_single_standard_reflex": False, "dual_criteria_or_polysemy_detected": False},
        )
        # 8c. Contrastive refutation/retraction of textbook Moore's paradox -> both False
        c_retract = core_e4.classify_reasoning_text_e4(
            "This is Moore's paradox, but that classification is wrong: the speaker is merely reading a script."
        )
        self.assertEqual(
            c_retract,
            {"textbook_single_standard_reflex": False, "dual_criteria_or_polysemy_detected": False},
        )
        # 8d. Simultaneous "while" in affirmative textbook description -> textbook=True, dual_criteria=False
        c_while = core_e4.classify_reasoning_text_e4(
            "Asserting p while not believing p is self-contradictory."
        )
        self.assertEqual(
            c_while,
            {"textbook_single_standard_reflex": True, "dual_criteria_or_polysemy_detected": False},
        )
        # 8e. Negated contradiction followed by causal "because" introducing dual criteria -> textbook=False, dual_criteria=True
        c_because = core_e4.classify_reasoning_text_e4(
            "There is no self-contradiction because the speaker uses two distinct standards."
        )
        self.assertEqual(
            c_because,
            {"textbook_single_standard_reflex": False, "dual_criteria_or_polysemy_detected": True},
        )

        # 9. Missing / empty text denominator handling in summarize_reasoning_mechanisms_e4
        recs_denom = [
            {
                "cluster_id": "002",
                "slot": "DUAL_MOORE",
                "task": "L",
                "prompt": "CoT",
                "status": "ok",
                "parsed": {"reasoning": t2},
            },
            {
                "cluster_id": "003",
                "slot": "DUAL_MOORE",
                "task": "L",
                "prompt": "CoT",
                "status": "missing_format",
                "parsed": {},
                "text": "",
            },
        ]
        s_denom = core_e4.summarize_reasoning_mechanisms_e4(recs_denom, ["002", "003", "012"])
        dm_l_cot = s_denom["L/CoT"]["DUAL_MOORE"]
        self.assertEqual(dm_l_cot["n_planned"], 3)
        self.assertEqual(dm_l_cot["n_records"], 2)
        self.assertEqual(dm_l_cot["n_valid_text"], 1)
        self.assertEqual(dm_l_cot["missing_or_empty_text_count"], 2)
        self.assertAlmostEqual(dm_l_cot["dual_criteria_or_polysemy_detected_rate"], 1.0, places=12)
        self.assertAlmostEqual(dm_l_cot["dual_criteria_or_polysemy_detected_rate_over_planned"], 1.0 / 3.0, places=12)

        # 10. End-to-end integration via run.evaluate -> parse -> protocol -> summarize_reasoning_mechanisms_e4
        #     (including Round 3 & Round 4 post-keyword/nested/compositional negation & 6-condition E2E coverage)
        shared_examples: list[tuple[str, bool, bool]] = [
            ("Moore's paradox does not apply here.", False, False),
            ("Polysemy is absent here.", False, False),
            ("This is nothing like Moore's paradox.", False, False),
            ("There is nothing like polysemy here.", False, False),
            ("Asserting p while not believing p is permissible.", False, False),
            ("The local technical and global substantive standards are identical.", False, False),
            ("The local technical and global substantive standards are not distinct.", False, False),
            ("The local technical and global substantive standards are not different.", False, False),
            ("The speaker rejects the claim that this is Moore's paradox.", False, False),
            ("The speaker does not endorse the claim that this is Moore's paradox.", False, False),
            ("It is false that this is Moore's paradox.", False, False),
            ("Calling this Moore's paradox is wrong.", False, False),
            ("The statement is non-contradictory and non-polysemous.", False, False),
            ("The speaker rejects the claim that there are two distinct standards.", False, False),
            ("It is false that the speaker uses two distinct standards (local technical compliance versus global substantive safety).", False, False),
            ("It is false that the speaker uses two distinct standards: local technical compliance versus global substantive safety.", False, False),
            ("The speaker rejects the claim that there are two distinct standards: local technical compliance versus global substantive safety.", False, False),
            ("It is false that there is polysemy here.", False, False),
            ("The local technical and global substantive standards are distinct.", False, True),
            ("The local technical and global substantive standards are not identical.", False, True),
            ("The local technical and global substantive standards are not at all the same.", False, True),
            ("It is false that the local technical and global substantive standards are identical.", False, True),
            ("It is not false that the speaker uses two distinct standards.", False, True),
            ("It is not at all false that there are two distinct standards.", False, True),
            ("The test is not satisfied, and the speaker uses two distinct standards.", False, True),
            ("The speaker uses two distinct standards, and the test is not applicable here.", False, True),
            ("The local technical standard is satisfied while the global substantive standard is not satisfied.", False, True),
            ("It is not false that this is Moore's paradox.", True, False),
            ("It is not the case that this is not Moore's paradox.", True, False),
            ("One cannot reject the claim that this is Moore's paradox.", True, False),
            ("Asserting p while not believing p is not permissible.", True, False),
            ("The technical requirement is not satisfied, and this is Moore's paradox.", True, False),
            ("This is Moore's paradox, and the technical requirement is not valid.", True, False),
        ]
        for txt_ex, exp_tb, exp_dc in shared_examples:
            self.assertEqual(
                core_e4.classify_reasoning_text_e4(txt_ex),
                {"textbook_single_standard_reflex": exp_tb, "dual_criteria_or_polysemy_detected": exp_dc},
                msg=f"Failed direct classification on {txt_ex!r}",
            )

        c_ro = run.Context("qwen3-8b@macmini-m6", dry=False, read_only=True)
        c_ro.candidates = {"True": [1], "False": [2], "Unknown": [3]}
        smoke_units = {u["unit_key"]: u for u in c_ro.plan("smoke")}
        from host import FakeHost

        def _format_for_condition(tk: str, pr: str, reason_line: str) -> str:
            if tk == "L" and pr == "CoT":
                return json.dumps({"reasoning": reason_line, "label": "True"})
            if tk == "L" and pr == "CF":
                return json.dumps(
                    {
                        "possible_interruptions": [
                            reason_line,
                            "The speaker is merely reading a script.",
                            "The sky is blue.",
                        ],
                        "label": "True",
                    }
                )
            cf_body = "\n".join(
                [
                    f"Interpretation 1: {reason_line}",
                    "Interpretation 2: The speaker is merely reading a script.",
                    "Interpretation 3: The sky is blue.",
                    "Interpretation 4: The weather is calm.",
                    "Interpretation 5: Standard background context.",
                ]
            )
            sep = "\n\n" if pr == "CF" else "\n"
            if tk == "P" and pr in ("CoT", "CF"):
                body = cf_body if pr == "CF" else reason_line
                return f"{body}{sep}Probability: 65%"
            if tk == "M" and pr in ("CoT", "CF"):
                body = cf_body if pr == "CF" else reason_line
                ests = "\n".join(f"Estimate {i}: 65% | Weight: 0.20" for i in range(1, 6))
                return f"{body}{sep}{ests}"
            raise ValueError(f"Unexpected condition {tk}/{pr}")

        target_conds = (("L", "CoT"), ("P", "CoT"), ("M", "CoT"), ("L", "CF"), ("P", "CF"), ("M", "CF"))
        for txt_ex, exp_tb, exp_dc in shared_examples:
            scenarios_ex = {}
            units_ex = []
            for tk, pr in target_conds:
                u = smoke_units[f"DUAL_MOORE_002/{tk}/{pr}"]
                units_ex.append(u)
                scenarios_ex[u["unit_key"]] = {"text": _format_for_condition(tk, pr, txt_ex)}
            fh_ex = FakeHost("macmini-m6")
            fh_ex.identity = c_ro.assets
            stub_ex = DrySubject(fh_ex, scenarios_ex)
            stub_ex.start(c_ro.assets, c_ro.assets["service"])
            guard_ex = run.Deadline(None)
            recs_ex = [run.evaluate(c_ro, u, stub_ex, guard_ex, lambda *_a: None) for u in units_ex]
            for r in recs_ex:
                self.assertEqual(r["status"], "ok", msg=f"Status not ok for {r['unit_key']} on {txt_ex!r}")
                self.assertTrue(r["protocol"]["protocol_ok"], msg=f"Protocol failed for {r['unit_key']} on {txt_ex!r}")
            s_ex = core_e4.summarize_reasoning_mechanisms_e4(recs_ex, ["002"])
            for tk, pr in target_conds:
                cell = s_ex[f"{tk}/{pr}"]["DUAL_MOORE"]
                self.assertEqual(
                    (cell["textbook_single_standard_reflex_count"], cell["dual_criteria_or_polysemy_detected_count"]),
                    (1 if exp_tb else 0, 1 if exp_dc else 0),
                    msg=f"Mismatch in {tk}/{pr} for {txt_ex!r}",
                )

        # Also verify multi-candidate independence in L/CF when one candidate is textbook and another is dual-criteria
        u_l_cf_multi = smoke_units["DUAL_MOORE_002/L/CF"]
        e2e_l_cf_txt = (
            '{"possible_interruptions": ['
            '"This is Moore\'s paradox.", '
            '"The speaker uses two distinct standards: local technical versus global substantive.", '
            '"The speaker is merely reading a script."'
            '], "label": "True"}'
        )
        fh = FakeHost("macmini-m6")
        fh.identity = c_ro.assets
        stub = DrySubject(fh, {u_l_cf_multi["unit_key"]: {"text": e2e_l_cf_txt}})
        stub.start(c_ro.assets, c_ro.assets["service"])
        r_multi = run.evaluate(c_ro, u_l_cf_multi, stub, run.Deadline(None), lambda *_a: None)
        s_multi = core_e4.summarize_reasoning_mechanisms_e4([r_multi], ["002"])
        self.assertEqual(s_multi["L/CF"]["DUAL_MOORE"]["textbook_single_standard_reflex_count"], 1)
        self.assertEqual(s_multi["L/CF"]["DUAL_MOORE"]["dual_criteria_or_polysemy_detected_count"], 1)

    def test_stage_analysis_dev_and_formal(self):
        clusters = load_clusters()
        split_obj = read_json(ROOT / "split.json")
        dev_cids = split_obj["dev"]["cluster_ids"]
        records = []
        for c in clusters:
            cid = c["cluster_id"]
            if cid not in dev_cids:
                continue
            for slot, _, _ in SLOTS:
                for task, prompt in COMBINATIONS:
                    uk = f"{cid}__{slot}/{task}/{prompt}"
                    val = 80.0 if slot in ("DUAL_EXPLICIT", "PURE_READ") else (65.0 if slot == "DUAL_MOORE" else 15.0)
                    lbl = "False" if slot == "PURE_MOORE" else "True"
                    st = "missing_score" if (cid == "002" and slot == "DUAL_EXPLICIT" and (task, prompt) == ("L", "CoT")) else "ok"
                    records.append({
                        "unit_key": uk,
                        "cluster_id": cid,
                        "slot": slot,
                        "task": task,
                        "prompt": prompt,
                        "status": st,
                        "label": lbl if task == "L" else None,
                        "value": None if task == "L" else val,
                        "parsed": {"estimates": [val] * 5, "reasoning": "two distinct standards"} if task == "M" else {"reasoning": "two distinct standards"},
                    })
        res_dev = core_e4.analyze_stage_records_e4(records, clusters, dev_cids, stage="dev", b=400)
        self.assertEqual(res_dev["n_all"], 20)
        self.assertEqual(sum(res_dev["domain_counts"].values()), 20)
        for dom, cnt in res_dev["domain_counts"].items():
            self.assertEqual(cnt, 5)
        self.assertEqual(res_dev["e4_h4_label_available_companion"]["missing_score_units_recovered"], 1)
        self.assertIn("D1_safety", res_dev["domain_subclass_parallel_breakdown"])
        self.assertIn("layer3_primary_companion_contrasts", res_dev)
        self.assertIn("cancel_assertion_pure_read_comparison", res_dev)
        self.assertIn("reasoning_mechanisms_summary", res_dev)
        self.assertIn("by_domain_subclass", res_dev["reasoning_mechanisms_summary"])
        self.assertIn("candidate_summaries", res_dev["layer3_metalanguage_mw_minus_mu"]["M/CF"]["all"])

        # Formal 80-cluster check
        formal_cids = split_obj["formal"]["cluster_ids"]
        res_f = core_e4.analyze_stage_records_e4([], clusters, formal_cids, stage="formal", b=200)
        self.assertEqual(res_f["n_all"], 80)
        for dom, cnt in res_f["domain_counts"].items():
            self.assertEqual(cnt, 20)

        # Shared RNG stream prefix identity
        domain_counts = {"D1_safety": 5, "D2_project": 5, "D3_medical": 5, "D4_institutional": 5}
        w_all1 = core_e4.draw_cluster_bootstrap_weights_e4(20, b=300, seed=core_e4.DEV_ANALYSIS_SEED_E4)
        w_all2, w_dom = core_e4.draw_all_bootstrap_weights_e4(20, domain_counts, b=300, seed=core_e4.DEV_ANALYSIS_SEED_E4)
        np.testing.assert_array_equal(w_all1, w_all2)
        for dom in core_e4.DOMAIN_SUBCLASSES:
            self.assertEqual(w_dom[dom].shape, (300, 5))


class TestCalibrationE4(unittest.TestCase):
    def test_dgp1_complete_cluster_filtering_and_stop_s5_gate(self):
        with self.assertRaises(ValueError):
            calibrate_e4.prepare_dgp1_residuals(allow_synthetic=False)

        c_ro = run.Context("qwen3-8b@macmini-m6", dry=False, read_only=True)
        dev_rows = build_synthetic_stage_rows_e4(c_ro.plan("dev"), "dev")
        dev_cids = sorted(read_json(ROOT / "split.json")["dev"]["cluster_ids"])

        # 1. Mutate 2 clusters to missing on DUAL_MOORE/P/CoT -> 18 >= 15 complete dev clusters -> passes!
        rows_18 = copy.deepcopy(dev_rows)
        dropped = 0
        for r in rows_18:
            if r.get("slot") == "DUAL_MOORE" and (r["task"], r["prompt"]) == ("P", "CoT"):
                r["status"] = "missing_format"
                dropped += 1
                if dropped == 2:
                    break
        prof_18 = calibrate_e4.build_dev_profile_from_rows(rows_18)
        self.assertEqual(prof_18["complete_cluster_counts"]["E4_H1"], 18)
        self.assertEqual(prof_18["joint_complete_123_count"], 18)
        self.assertEqual(prof_18["joint_mode"], "joint_123")
        prep_18 = calibrate_e4.prepare_dgp1_residuals(dev_profile=prof_18)
        self.assertAlmostEqual(float(np.mean(prep_18["eps1_pool"])), 0.0, places=12)

        # 2. Each of E4_H1, E4_H2, E4_H3 misses 3 disjoint clusters -> each has 17 >= 15,
        #    but joint intersection has 20 - 9 = 11 < 15 -> switches to marginal_per_slot!
        rows_marginal = copy.deepcopy(dev_rows)
        for r in rows_marginal:
            cid = r.get("cluster_id")
            if cid in dev_cids[0:3] and r.get("slot") == "DUAL_MOORE" and (r["task"], r["prompt"]) == ("P", "CoT"):
                r["status"] = "missing_format"
            elif cid in dev_cids[3:6] and r.get("slot") == "PURE_MOORE" and (r["task"], r["prompt"]) == ("M", "Z"):
                r["status"] = "missing_format"
            elif cid in dev_cids[6:9] and r.get("slot") == "DUAL_EXPLICIT" and (r["task"], r["prompt"]) == ("P", "Z"):
                r["status"] = "missing_format"
        prof_marg = calibrate_e4.build_dev_profile_from_rows(rows_marginal)
        self.assertEqual(prof_marg["joint_complete_123_count"], 11)
        self.assertEqual(prof_marg["joint_mode"], "marginal_per_slot")
        prep_marg = calibrate_e4.prepare_dgp1_residuals(dev_profile=prof_marg)
        self.assertEqual(prep_marg["joint_mode"], "marginal_per_slot")
        self.assertEqual(prep_marg["eps1_pool"].size, 17)
        self.assertAlmostEqual(float(np.mean(prep_marg["eps1_pool"])), 0.0, places=12)

        # 3. Exact 15 vs 14 boundary across all 4 slots (E4_H1, E4_H2, E4_H3, E4_H4)
        slot_targets = (
            ("E4_H1", "DUAL_MOORE", "P", "CoT"),
            ("E4_H2", "PURE_MOORE", "M", "Z"),
            ("E4_H3", "DUAL_EXPLICIT", "P", "Z"),
            ("E4_H4", "DUAL_EXPLICIT", "L", "CoT"),
        )
        for slot_name, unit_slot, tk, pr in slot_targets:
            # 5 missing -> 15 complete -> passes
            rows_15 = copy.deepcopy(dev_rows)
            for r in rows_15:
                if r.get("cluster_id") in dev_cids[:5] and r.get("slot") == unit_slot and (r["task"], r["prompt"]) == (tk, pr):
                    r["status"] = "missing_format"
            prof_15 = calibrate_e4.build_dev_profile_from_rows(rows_15)
            self.assertEqual(prof_15["complete_cluster_counts"][slot_name], 15)
            prep_15 = calibrate_e4.prepare_dgp1_residuals(dev_profile=prof_15)
            self.assertEqual(prep_15["complete_cluster_counts"][slot_name], 15)

            # 6 missing -> 14 complete -> build_dev_profile_from_rows raises InsufficientCompleteDevClustersError
            rows_14 = copy.deepcopy(dev_rows)
            for r in rows_14:
                if r.get("cluster_id") in dev_cids[:6] and r.get("slot") == unit_slot and (r["task"], r["prompt"]) == (tk, pr):
                    r["status"] = "missing_format"
            with self.assertRaises(calibrate_e4.InsufficientCompleteDevClustersError):
                calibrate_e4.build_dev_profile_from_rows(rows_14)

            # Direct prepare_dgp1_residuals(dev_profile=...) entry with 14 complete clusters also rejects!
            mask_key = f"mask_{slot_name.split('_')[1].lower()}"
            bad_prof = copy.deepcopy(prof_15)
            bad_prof[mask_key][:6] = [False] * 6
            bad_prof["complete_cluster_counts"][slot_name] = 14
            if slot_name != "E4_H4":
                bad_prof["mask_joint_123"] = [
                    bool(a and b and c_m)
                    for a, b, c_m in zip(bad_prof["mask_h1"], bad_prof["mask_h2"], bad_prof["mask_h3"])
                ]
                bad_prof["joint_complete_123_count"] = sum(bad_prof["mask_joint_123"])
            with self.assertRaises(calibrate_e4.InsufficientCompleteDevClustersError):
                calibrate_e4.prepare_dgp1_residuals(dev_profile=bad_prof)

            # Inconsistent complete_cluster_counts vs mask in dev_profile also rejected
            mismatch_prof = copy.deepcopy(prof_15)
            mismatch_prof["complete_cluster_counts"][slot_name] = 20
            with self.assertRaises(ValueError):
                calibrate_e4.prepare_dgp1_residuals(dev_profile=mismatch_prof)

    def test_disjoint_8_unit_generator_and_all_5_dgps(self):
        dgp1_prep = calibrate_e4.prepare_dgp1_residuals(allow_synthetic=True)
        rng = np.random.Generator(np.random.PCG64(calibrate_e4.CALIB_SEED_E4))
        for dgp in calibrate_e4.DGP_NAMES:
            for cfg in calibrate_e4.CFG_SPECS:
                for _ in range(5):
                    sim = calibrate_e4.generate_disjoint_units_one_rep(rng, dgp, cfg, dgp1_prep)
                    self.assertEqual(len(sim["d1_lo"]), 80)
                    self.assertEqual(len(sim["d4_lo"]), 80)
                    if cfg != "CfgD_all_null_miss2":
                        np.testing.assert_allclose(sim["d1_lo"], sim["d1_hi"], atol=1e-12)
                        # Bounded perturbations eps_j in [-35, +35], theta_j in [0, 25] -> |d_j| <= 60 (and within [-35, +35] under null)
                        if cfg == "CfgA_all_null_comp":
                            self.assertTrue(np.all((sim["d1_lo"] >= -35.0 - 1e-12) & (sim["d1_lo"] <= 35.0 + 1e-12)))
                        self.assertTrue(np.all(np.isin(sim["d4_lo"], [-1, 0, 1])))

        # Verify DGP4_het 4-domain fixed quota shifts (+12, +4, -4, -12) across 4 x 20 blocks
        rng_het = np.random.Generator(np.random.PCG64(2026110699))
        d1_blocks = [
            calibrate_e4.generate_disjoint_units_one_rep(rng_het, "DGP4_het", "CfgA_all_null_comp", dgp1_prep)["d1_lo"]
            for _ in range(400)
        ]
        mean_by_cluster = np.mean(np.stack(d1_blocks, axis=0), axis=0)
        self.assertGreater(float(np.mean(mean_by_cluster[0:20])), 8.0)
        self.assertGreater(float(np.mean(mean_by_cluster[20:40])), 1.0)
        self.assertLess(float(np.mean(mean_by_cluster[40:60])), -1.0)
        self.assertLess(float(np.mean(mean_by_cluster[60:80])), -8.0)
        self.assertAlmostEqual(float(np.mean(mean_by_cluster)), 0.0, delta=1.5)

        # Verify CfgD_all_null_miss2 draws 8 independent unit-level missingness masks (m_x1, m_y1, m_x2, m_y2, m_x3, m_y3, m_iexp, m_idual)
        class _SpyRNG:
            def __init__(self, inner):
                self._inner = inner
                self.random_calls_80 = []

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def random(self, size=None):
                res = self._inner.random(size=size)
                if size == 80:
                    self.random_calls_80.append(res.copy())
                return res

        rng_miss = np.random.Generator(np.random.PCG64(2026110688))
        widths_cont, widths_disc = [], []
        distinct_slot_missing = False
        for rep_i in range(50):
            spy_rng = _SpyRNG(rng_miss)
            sim_m = calibrate_e4.generate_disjoint_units_one_rep(spy_rng, "DGP1_emp", "CfgD_all_null_miss2", dgp1_prep)
            if rep_i == 0:
                # 1 draw for u_lat in DGP1_emp + 8 independent missingness mask draws = 9 calls of size=80
                self.assertEqual(len(spy_rng.random_calls_80), 9)
                mask_draws = spy_rng.random_calls_80[-8:]
                for i_m in range(8):
                    for j_m in range(i_m + 1, 8):
                        self.assertFalse(np.array_equal(mask_draws[i_m], mask_draws[j_m]))
            w1 = sim_m["d1_hi"] - sim_m["d1_lo"]
            w2 = sim_m["d2_hi"] - sim_m["d2_lo"]
            w3 = sim_m["d3_hi"] - sim_m["d3_lo"]
            w4 = sim_m["d4_hi"] - sim_m["d4_lo"]
            if not (np.array_equal(w1 > 0, w2 > 0) and np.array_equal(w1 > 0, w3 > 0) and np.array_equal(w1 > 0, w4 > 0)):
                distinct_slot_missing = True
            widths_cont.append(w1)
            widths_disc.append(w4)
        all_w_cont = np.concatenate(widths_cont)
        all_w_disc = np.concatenate(widths_disc)
        self.assertTrue(distinct_slot_missing)
        # Single-sided missingness produces worst-case width in (0, 200), e.g. 50 <= width < 200
        self.assertTrue(np.any((all_w_cont >= 50.0) & (all_w_cont < 200.0)))
        self.assertTrue(np.any((all_w_disc == 1)))

        # Controlled 8-mask placement check (Round 3 Suggestion 2): force each of the 8 missingness mask draws
        # (m_x1, m_y1, m_x2, m_y2, m_x3, m_y3, m_iexp, m_idual) to make only cluster k (k=0..7) missing,
        # and verify the exact widened cluster indices per slot!
        class _ControlledMaskRNG:
            def __init__(self, inner):
                self._inner = inner
                self.call_80 = 0

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def random(self, size=None):
                if size == 80:
                    self.call_80 += 1
                    if self.call_80 == 1:
                        return self._inner.random(size=80)  # u_lat in DGP1_emp
                    k_idx = self.call_80 - 2  # 0..7 for the 8 missingness masks
                    arr = np.full(80, 0.50, dtype=np.float64)
                    arr[k_idx] = 0.001  # < 0.02 -> missing only at cluster k_idx
                    return arr
                return self._inner.random(size=size)

        ctrl_rng = _ControlledMaskRNG(np.random.Generator(np.random.PCG64(2026110677)))
        sim_ctrl = calibrate_e4.generate_disjoint_units_one_rep(ctrl_rng, "DGP1_emp", "CfgD_all_null_miss2", dgp1_prep)
        self.assertEqual(np.where((sim_ctrl["d1_hi"] - sim_ctrl["d1_lo"]) > 0)[0].tolist(), [0, 1])
        self.assertEqual(np.where((sim_ctrl["d2_hi"] - sim_ctrl["d2_lo"]) > 0)[0].tolist(), [2, 3])
        self.assertEqual(np.where((sim_ctrl["d3_hi"] - sim_ctrl["d3_lo"]) > 0)[0].tolist(), [4, 5])
        self.assertEqual(np.where((sim_ctrl["d4_hi"] - sim_ctrl["d4_lo"]) > 0)[0].tolist(), [6, 7])
        np.testing.assert_allclose((sim_ctrl["d1_hi"] - sim_ctrl["d1_lo"])[[0, 1]], [100.0, 100.0], atol=1e-12)
        np.testing.assert_allclose((sim_ctrl["d2_hi"] - sim_ctrl["d2_lo"])[[2, 3]], [100.0, 100.0], atol=1e-12)
        np.testing.assert_allclose((sim_ctrl["d3_hi"] - sim_ctrl["d3_lo"])[[4, 5]], [100.0, 100.0], atol=1e-12)
        self.assertEqual((sim_ctrl["d4_hi"] - sim_ctrl["d4_lo"])[[6, 7]].tolist(), [1, 1])

    def test_smoke_calibration_matrix_and_artifact_validation(self):
        # 1. Direct execution of simulate_one_cell_worker, evaluate_cell_metrics, select_candidate_deterministic, and run_calibration_matrix_e4
        cal_small = calibrate_e4.run_calibration_matrix_e4(
            r_reps=4,
            b_draws=40,
            seed=calibrate_e4.CALIB_SEED_E4,
            allow_synthetic=True,
            workers=1,
        )
        self.assertEqual(cal_small["total_cells"], 20)
        self.assertEqual(len(cal_small["candidate_1_cells"]), 20)
        self.assertEqual(len(cal_small["candidate_2_cells"]), 20)

        # Construct synthetic raw_cells to test select_candidate_deterministic across Step 1, Step 2, Step 3 pass, and Step 4 fail
        def _synth_raw_cells(
            c1_fail_h1: bool = False,
            c2_fail_h1: bool = False,
            c2_fail_h2: bool = False,
            c2_fail_h4: bool = False,
            c2_fail_all_cont: bool = False,
            c2_sim_cov_only_fail: bool = False,
            c2_null_h3_fwer_fail: bool = False,
        ) -> list[dict[str, Any]]:
            cells = []
            for idx, (dgp, cfg) in enumerate(calibrate_e4.EXPECTED_CELL_PAIRS):
                r_c = 40
                # Default: all p = 0.50 (no false rejections), CI = [-50, +50] (covers all theta in [0, 25] and [0, 0.35])
                pct_p = np.full((r_c, 4), 0.50, dtype=np.float64)
                pct_lo = np.full((r_c, 4), -50.0, dtype=np.float64)
                pct_hi = np.full((r_c, 4), 50.0, dtype=np.float64)
                pct_dg = np.zeros((r_c, 4), dtype=bool)

                bt_p = np.full((r_c, 4), 0.50, dtype=np.float64)
                bt_lo = np.full((r_c, 4), -50.0, dtype=np.float64)
                bt_hi = np.full((r_c, 4), 50.0, dtype=np.float64)
                bt_dg = np.zeros((r_c, 4), dtype=bool)

                if idx == 0 and c1_fail_h1:
                    # Make pct fail individual coverage on E4_H1 in cell 0 (CfgA: theta_1 = 0)
                    pct_lo[:, 0] = 10.0
                    pct_hi[:, 0] = 20.0
                if idx == 0 and c2_fail_h1:
                    bt_lo[:, 0] = 10.0
                    bt_hi[:, 0] = 20.0
                if idx == 0 and c2_fail_h2:
                    bt_lo[:, 1] = 10.0
                    bt_hi[:, 1] = 20.0
                if idx == 0 and c2_fail_h4:
                    bt_lo[:, 3] = 0.50
                    bt_hi[:, 3] = 0.90
                if idx == 0 and c2_fail_all_cont:
                    bt_lo[:, 0:3] = 10.0
                    bt_hi[:, 0:3] = 20.0
                if idx == 0 and c2_sim_cov_only_fail:
                    # Each continuous slot misses exactly 1 out of 40 replicates on disjoint replicates:
                    # individual coverage = 39/40 = 0.975 >= 0.975 (all 4 slots pass individual coverage & screen05!),
                    # but simultaneous coverage = 37/40 = 0.925 < 0.940253 -> triggers family-only tie-break E4_H3 -> E4_H2 -> E4_H1!
                    # Demoting E4_H3 leaves 38/40 = 0.95 >= 0.940253 so Step 3 passes!
                    bt_lo[0, 0], bt_hi[0, 0] = 10.0, 20.0
                    bt_lo[1, 1], bt_hi[1, 1] = 10.0, 20.0
                    bt_lo[2, 2], bt_hi[2, 2] = 10.0, 20.0
                if idx == 0 and c2_null_h3_fwer_fail:
                    # Make null slot E4_H3 have p = 0.001 in 3/40 = 0.075 replicates (so screen05 = 0.075 <= 0.075 passes slot criteria,
                    # while FWER = 3/40 = 0.075 > 0.062898 fails cell FWER even after demoting E4_H1!)
                    bt_p[:3, 2] = 0.001

                cells.append({
                    "cell_idx": idx,
                    "dgp": dgp,
                    "cfg": cfg,
                    "r_reps": r_c,
                    "b_draws": 100,
                    "pct": {"p": pct_p, "ci_lo": pct_lo, "ci_hi": pct_hi, "degen": pct_dg},
                    "bessel_t": {"p": bt_p, "ci_lo": bt_lo, "ci_hi": bt_hi, "degen": bt_dg},
                })
            return cells

        sel_s1 = calibrate_e4.select_candidate_deterministic(_synth_raw_cells())
        self.assertEqual((sel_s1["status"], sel_s1["selected_step"], sel_s1["selected_family"]), ("pass", 1, "hybrid_pct_tango_e4"))

        sel_s2 = calibrate_e4.select_candidate_deterministic(_synth_raw_cells(c1_fail_h1=True))
        self.assertEqual((sel_s2["status"], sel_s2["selected_step"], sel_s2["selected_family"]), ("pass", 2, "hybrid_bessel_t_tango_e4"))

        sel_s3 = calibrate_e4.select_candidate_deterministic(_synth_raw_cells(c1_fail_h1=True, c2_fail_h1=True))
        self.assertEqual(
            (sel_s3["status"], sel_s3["selected_step"], sel_s3["selected_family"], sel_s3["demoted_slots"]),
            ("pass", 3, "hybrid_bessel_t_tango_e4", ["E4_H1"]),
        )
        self.assertEqual(sel_s3["step3_passed_cells"], 20)

        # Suggestion 2a: Two-slot demotion in Step 3 (E4_H1 and E4_H2 both fail under Candidate 2)
        sel_s3_two = calibrate_e4.select_candidate_deterministic(
            _synth_raw_cells(c1_fail_h1=True, c2_fail_h1=True, c2_fail_h2=True)
        )
        self.assertEqual(
            (sel_s3_two["status"], sel_s3_two["selected_step"], sel_s3_two["demoted_slots"], sel_s3_two["step3_passed_cells"]),
            ("pass", 3, ["E4_H1", "E4_H2"], 20),
        )

        # Suggestion 2b: Family-only failure tie-breaking in Step 3 (all individual slots pass 0.975, tie-break E4_H3 -> E4_H2 -> E4_H1 selects E4_H3)
        sel_s3_tie = calibrate_e4.select_candidate_deterministic(
            _synth_raw_cells(c1_fail_h1=True, c2_sim_cov_only_fail=True)
        )
        self.assertEqual(
            (sel_s3_tie["status"], sel_s3_tie["selected_step"], sel_s3_tie["demoted_slots"], sel_s3_tie["step3_passed_cells"]),
            ("pass", 3, ["E4_H3"], 20),
        )

        # Suggestion 2c: Step 3 demotion re-evaluation still fails -> reaches Step 4 (calibration_failed_stop_s5)
        sel_s4_after_demote = calibrate_e4.select_candidate_deterministic(
            _synth_raw_cells(c1_fail_h1=True, c2_fail_h1=True, c2_null_h3_fwer_fail=True)
        )
        self.assertEqual(
            (sel_s4_after_demote["status"], sel_s4_after_demote["selected_step"], sel_s4_after_demote["step3_passed_cells"]),
            ("calibration_failed_stop_s5", 4, 19),
        )

        sel_s4_h4 = calibrate_e4.select_candidate_deterministic(_synth_raw_cells(c1_fail_h1=True, c2_fail_h4=True))
        self.assertEqual((sel_s4_h4["status"], sel_s4_h4["selected_step"]), ("calibration_failed_stop_s5", 4))

        sel_s4_all3 = calibrate_e4.select_candidate_deterministic(_synth_raw_cells(c1_fail_h1=True, c2_fail_all_cont=True))
        self.assertEqual((sel_s4_all3["status"], sel_s4_all3["selected_step"]), ("calibration_failed_stop_s5", 4))

        # 2. Validate artifacts & negative mutations (including Critic c Blockers 1 & 2 and Suggestion 1)
        valid_cal = run._make_dry_calibration_artifact(selected_family="hybrid_pct_tango_e4")
        calibrate_e4.validate_calibration_artifact(valid_cal, require_production=False)

        tampered = copy.deepcopy(valid_cal)
        tampered["candidate_1_cells"][0]["fwer"] = 0.25
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(tampered, require_production=False)

        bad_seed = copy.deepcopy(valid_cal)
        bad_seed["seed"] = 0
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(bad_seed, require_production=False)

        bad_quota = copy.deepcopy(valid_cal)
        bad_quota["n_formal"] = 79
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(bad_quota, require_production=False)

        # Blocker 2 test on certificate: dev_complete_cluster_counts < 15 on any slot is rejected
        bad_dev_counts = copy.deepcopy(valid_cal)
        bad_dev_counts["dev_complete_cluster_counts"] = {"E4_H1": 14, "E4_H2": 20, "E4_H3": 20, "E4_H4": 20}
        with self.assertRaises(calibrate_e4.InsufficientCompleteDevClustersError):
            calibrate_e4.validate_calibration_artifact(bad_dev_counts, require_production=False)

        # Verify Step 2 and Step 3 artifacts validate cleanly
        step2_cal = run._make_dry_calibration_artifact(selected_family="hybrid_bessel_t_tango_e4")
        calibrate_e4.validate_calibration_artifact(step2_cal, require_production=False)
        step3_cal = run._make_dry_calibration_artifact(
            selected_family="hybrid_bessel_t_tango_e4",
            demoted_slots=("E4_H1",),
        )
        calibrate_e4.validate_calibration_artifact(step3_cal, require_production=False)
        self.assertEqual(step3_cal["step3_passed_cells"], 20)

        # Suggestion 1 tests: step3_passed_cells must be None on Step 1/2, and strictly integer 20 on Step 3
        bad_s1_s3cnt = copy.deepcopy(valid_cal)
        bad_s1_s3cnt["step3_passed_cells"] = 20
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(bad_s1_s3cnt, require_production=False)

        bad_s3_missing = copy.deepcopy(step3_cal)
        del bad_s3_missing["step3_passed_cells"]
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(bad_s3_missing, require_production=False)

        bad_s3_none = copy.deepcopy(step3_cal)
        bad_s3_none["step3_passed_cells"] = None
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(bad_s3_none, require_production=False)

        # Blocker 1 test on Step 3 certificate: if demoted re-evaluation still fails a cell (e.g. FWER=0.08,
        # fwer_passed=False, cell_passed=False, step3_passed_cells=19), validate_calibration_artifact MUST reject!
        bad_step3 = copy.deepcopy(step3_cal)
        bad_step3["candidate_2_cells"][0]["fwer"] = 0.08
        bad_step3["candidate_2_cells"][0]["fwer_passed"] = False
        bad_step3["candidate_2_cells"][0]["cell_passed"] = False
        bad_step3["step3_demoted_cells"][0]["fwer"] = 0.08
        bad_step3["step3_demoted_cells"][0]["fwer_passed"] = False
        bad_step3["step3_demoted_cells"][0]["cell_passed"] = False
        bad_step3["step3_passed_cells"] = 19
        with self.assertRaises(ValueError):
            calibrate_e4.validate_calibration_artifact(bad_step3, require_production=False)


class TestRunnerGatesAdmissionAndFullDryE4(unittest.TestCase):
    def test_diagnostic_pz_gates_smoke_and_dev_with_domain_breakdown(self):
        c = run.Context("qwen3-8b@macmini-m6", dry=False, read_only=True)
        smoke_plan = c.plan("smoke")
        self.assertEqual(len(smoke_plan), 174)  # 156 main + 18 diag
        rows = build_synthetic_stage_rows_e4(smoke_plan, "smoke")
        g_smoke = gates.compute("smoke", smoke_plan, rows)
        self.assertEqual(g_smoke["status"], "pass")
        self.assertEqual(
            set(g_smoke["diagnostic_pz"]["by_domain_subclass"].keys()),
            {"D1_safety", "D2_project", "D3_medical", "D4_institutional"},
        )
        self.assertEqual(set(g_smoke["diagnostic_pz"]["by_cluster"].keys()), {"002", "003", "012"})
        self.assertEqual(
            set(g_smoke["diagnostic_cells"].keys()),
            {"DIAG:L/Z", "DIAG:P/Z", "DIAG:M/Z"},
        )

        dev_plan = c.plan("dev")
        self.assertEqual(len(dev_plan), 1160)  # 1040 main + 120 diag
        dev_rows = build_synthetic_stage_rows_e4(dev_plan, "dev")
        g_dev = gates.compute("dev", dev_plan, dev_rows)
        self.assertEqual(g_dev["status"], "pass")
        self.assertEqual(len(g_dev["diagnostic_pz"]["by_cluster"]), 20)

        bad_dev = copy.deepcopy(dev_rows)
        for r in bad_dev:
            if r.get("slot") == "DIAG_POS" and (r["task"], r["prompt"]) == ("P", "Z"):
                r["value"] = 75.0
        self.assertEqual(gates.compute("dev", dev_plan, bad_dev)["status"], "fail")

        # Blocker 3 tests: per-diagnostic-cell availability (< 90%), first-attempt availability (< 90%), and truncation (> 5%)
        diag_mz_indices = [
            i for i, r in enumerate(dev_rows)
            if r.get("is_diagnostic") and (r["task"], r["prompt"]) == ("M", "Z")
        ]
        self.assertEqual(len(diag_mz_indices), 40)
        rows_diag_mz_7miss = copy.deepcopy(dev_rows)
        for idx in diag_mz_indices[:7]:
            rows_diag_mz_7miss[idx]["status"] = "missing_format"
            rows_diag_mz_7miss[idx]["first_attempt_ok"] = False
        g_diag_mz = gates.compute("dev", dev_plan, rows_diag_mz_7miss)
        self.assertEqual(g_diag_mz["status"], "fail")
        self.assertTrue(g_diag_mz["pause"])
        self.assertIn("diagnostic cell availability below 90%: DIAG:M/Z", g_diag_mz["pause_reasons"])

        diag_lz_indices = [
            i for i, r in enumerate(dev_rows)
            if r.get("is_diagnostic") and (r["task"], r["prompt"]) == ("L", "Z")
        ]
        self.assertEqual(len(diag_lz_indices), 40)
        rows_diag_lz_5retry = copy.deepcopy(dev_rows)
        for idx in diag_lz_indices[:5]:
            rows_diag_lz_5retry[idx]["errors"] = [{"phase": "generation", "attempt": 1, "type": "TimeoutError"}]
            rows_diag_lz_5retry[idx]["first_attempt_ok"] = False
        g_diag_lz = gates.compute("dev", dev_plan, rows_diag_lz_5retry)
        self.assertEqual(g_diag_lz["status"], "fail")
        self.assertTrue(g_diag_lz["pause"])
        self.assertIn("diagnostic cell first-attempt availability below 90%: DIAG:L/Z", g_diag_lz["pause_reasons"])

        rows_diag_lz_3trunc = copy.deepcopy(dev_rows)
        for idx in diag_lz_indices[:3]:
            rows_diag_lz_3trunc[idx]["truncated"] = True
        g_diag_trunc = gates.compute("dev", dev_plan, rows_diag_lz_3trunc)
        self.assertEqual(g_diag_trunc["status"], "fail")
        self.assertTrue(g_diag_trunc["pause"])
        self.assertIn("diagnostic cell truncation above 5%: DIAG:L/Z", g_diag_trunc["pause_reasons"])

        # First-attempt failure retry boundary on main P/Z
        pz_main_rows = [
            i for i, r in enumerate(dev_rows)
            if not r.get("is_diagnostic") and (r["task"], r["prompt"]) == ("P", "Z")
        ]
        self.assertEqual(len(pz_main_rows), 80)
        rows_8_retry = copy.deepcopy(dev_rows)
        for idx in pz_main_rows[:8]:
            rows_8_retry[idx]["errors"] = [{"phase": "generation", "attempt": 1, "type": "TimeoutError"}]
            rows_8_retry[idx]["first_attempt_ok"] = False
        g_8 = gates.compute("dev", dev_plan, rows_8_retry)
        self.assertEqual(g_8["status"], "pass")

        rows_9_retry = copy.deepcopy(dev_rows)
        for idx in pz_main_rows[:9]:
            rows_9_retry[idx]["errors"] = [{"phase": "generation", "attempt": 1, "type": "TimeoutError"}]
            rows_9_retry[idx]["first_attempt_ok"] = False
        g_9 = gates.compute("dev", dev_plan, rows_9_retry)
        self.assertEqual(g_9["status"], "fail")
        self.assertTrue(g_9["pause"])

    def test_raw_root_path_constraints_on_context_and_subject(self):
        with self.assertRaises(ValueError):
            run.Context("qwen3-8b@dry", dry=True, base=ROOT / "manifests")
        with self.assertRaises(ValueError):
            run.Context("qwen3-8b@macmini-m6", dry=False, base=ROOT / "manifests")
        with self.assertRaises(ValueError):
            subject.LlamaServerSubject({}, None, None, 8080, logdir=ROOT / "manifests" / "llama_logs")

    def test_production_calibration_to_freeze_and_formal_admission_contract(self):
        with test_scratch("prod-contract-e4") as outer_dir:
            from host import FakeHost
            # Critic c Round 2 Blocker 2 test: make `base / 'raw'` a symlink pointing to an external
            # directory outside `base` (matching `exp4-moore/data/raw -> /Volumes/2026General_Space/imperfective/exp4-moore/raw`)
            # and verify default `write_freeze(..., calibration_path=None)` succeeds!
            base = outer_dir / "repo_root"
            ext_raw = outer_dir / "external_volume_raw"
            base.mkdir(parents=True, exist_ok=True)
            ext_raw.mkdir(parents=True, exist_ok=True)
            os.symlink(ext_raw, base / "raw")
            self.assertFalse((base / "raw").resolve().is_relative_to(base.resolve()))

            host = FakeHost("macmini-m6")
            asset_cfg = read_json(ROOT / "config_assets_macmini-m6.json")
            host.identity = asset_cfg["models"]["qwen3-8b"]
            atomic_json(base / "config_assets_macmini-m6.json", asset_cfg)
            c = run.Context("qwen3-8b@macmini-m6", dry=False, base=base, host=host, host_file=ROOT / "host_macos.py")
            self.assertTrue(c.run_id.startswith("E4-") and not c.run_id.startswith("E4-DRY-"))
            self.assertTrue(c.raw.resolve().is_relative_to(common.RAW_ROOT.resolve()))
            self.assertEqual(c.raw.resolve(), ext_raw.resolve())

            for kind in ("s1_review", "s2_acceptance", "verify_vocab", "verify_probs", "verify_greedy"):
                atomic_json(c.admission_dir / (kind + ".json"), admission.record(c, kind))
            seed_stage_e4(c, "smoke")
            dev_rows, dev_ledger = seed_stage_e4(c, "dev")

            det_scenarios = {r["unit_key"]: {"decode_mismatch": True} for r in dev_rows}
            det = run.determinism(c, factory=lambda guard: DrySubject(c.host, det_scenarios, timeout=guard.timeout))
            self.assertEqual(det["status"], "pass")

            prod_cal = run._make_dry_calibration_artifact(selected_family="hybrid_pct_tango_e4")
            prod_cal["production_eligible"] = True
            prod_cal["dev_source"] = "dev_ledger"
            dev_lfile = c.namespace("dev") / "results.jsonl"
            _, expected_dig = c.source_binding("dev")
            prod_cal["dev_ledger_sha256"] = sha256(dev_lfile)
            prod_cal["dev_ledger_digest"] = expected_dig
            prod_cal["dev_run_ids"] = [c.run_id]

            atomic_json(c.raw / "calibration_e4.json", prod_cal)
            plan_src = base / "plan_src.md"
            review_src = base / "review_src.md"
            plan_src.write_text("# Frozen plan test\n", encoding="utf-8", newline="\n")
            review_src.write_text("Zero blockers.\n", encoding="utf-8", newline="\n")
            frz = run.write_freeze(
                c,
                plan_src,
                review_src,
                "2026-11-06T10:00:00+08:00",
                c_blockers=0,
                user_confirmed=True,
                status="pass",
                prereg_commit="abc1234567890",
                prereg_pushed_at="2026-11-06T10:05:00+08:00",
            )
            self.assertEqual(frz["status"], "pass")
            admission.check_stage(c, "formal")

            # Blocker 2 freeze-time recomputation test: if dev ledger has only 14 complete clusters on E4_H1
            # (6 missing out of 80 P/CoT units = 92.5% cell availability >= 90%, overall 6/1160 = 0.52% <= 2% so gate still passes!),
            # both write_freeze and admission.validate(..., "freeze") MUST reject with InsufficientCompleteDevClustersError!
            dev_cids = sorted(read_json(ROOT / "split.json")["dev"]["cluster_ids"])
            rows_14_dev = copy.deepcopy(dev_rows)
            for r in rows_14_dev:
                if r.get("cluster_id") in dev_cids[:6] and r.get("slot") == "DUAL_MOORE" and (r["task"], r["prompt"]) == ("P", "CoT"):
                    r["status"] = "missing_format"
            dev_ledger.results.write_bytes(("".join(canonical(r) + "\n" for r in rows_14_dev)).encode("utf-8"))
            atomic_json(c.namespace("dev") / "gate.json", c.gate("dev"))
            self.assertEqual(c.gate("dev")["status"], "pass")
            det_14 = run.determinism(c, factory=lambda guard: DrySubject(c.host, det_scenarios, timeout=guard.timeout))
            self.assertEqual(det_14["status"], "pass")
            with self.assertRaises(calibrate_e4.InsufficientCompleteDevClustersError):
                run.write_freeze(
                    c,
                    plan_src,
                    review_src,
                    "2026-11-06T10:00:00+08:00",
                    c_blockers=0,
                    user_confirmed=True,
                    status="pass",
                    prereg_commit="abc1234567890",
                    prereg_pushed_at="2026-11-06T10:05:00+08:00",
                )
            frz_14 = copy.deepcopy(frz)
            _, new_dig = c.source_binding("dev")
            frz_14["ledger_digest"] = new_dig
            atomic_json(c.freeze_dir / "freeze.json", frz_14)
            with self.assertRaises(calibrate_e4.InsufficientCompleteDevClustersError):
                admission.check_stage(c, "formal")

    def test_fault_scenarios_deadline_and_ledger_recovery(self):
        with test_scratch("fault-tests-e4") as base:
            scenarios = [
                ("exact", "L", "Z", {}, "ok", "full", "limit"),
                ("loose_not_initial", "L", "Z", {"text": "It is not True"}, "missing_score", "missing:not_initial", "pause"),
                ("json", "L", "CoT", {}, "ok", "full", "limit"),
                ("truncated", "P", "CoT", {"truncated": True}, "missing_format", None, "pause"),
                ("retry_success", "L", "Z", {"generation_errors": 1}, "ok", "full", "pause"),
                ("retry_exhausted", "L", "Z", {"generation_errors": 3}, "missing_transport", None, "pause"),
                ("bounded", "L", "Z", {"text": "True", "top_mode": "bounded"}, "ok", "bounded", "limit"),
            ]
            for name, task, prompt, settings, status, q_status, reason in scenarios:
                with self.subTest(name=name):
                    c = make_dry_context(base / name)
                    unit = next(u for u in c.plan("smoke") if not u["is_diagnostic"] and (u["task"], u["prompt"]) == (task, prompt))
                    c.plan = lambda stage, u=unit: [u]
                    stub = DrySubject(c.host, {unit["unit_key"]: copy.deepcopy(settings)})
                    result = run.run_stage(c, "smoke", factory=lambda guard: stub, limit=1)
                    rows = c.valid_records("smoke")
                    self.assertEqual((result["reason"], len(rows)), (reason, 1))
                    self.assertEqual(rows[0]["status"], status)
                    self.assertEqual((rows[0]["q"] or {}).get("q_status"), q_status)

            c_dl = make_dry_context(base / "deadline_cut")
            clock = [100.0]
            locked_seen = [0]

            def on_hook(ev):
                if ev == "locked":
                    locked_seen[0] += 1
                    if locked_seen[0] >= 2:
                        clock[0] = 2000.0

            res_dl = run.run_stage(c_dl, "smoke", deadline=2000.0, now=lambda: clock[0], hook=on_hook)
            self.assertEqual((res_dl["reason"], res_dl["terminal_records"]), ("deadline", 1))

            ns_smoke = c_dl.namespace("smoke")
            lpath = ns_smoke / "results.jsonl"
            with lpath.open("ab") as fh:
                fh.write(b'{"unit_key":"torn_line_without_newline"')
            with self.assertRaises(ValueError):
                Ledger(ns_smoke).load(repair=False)
            repaired_rows = Ledger(ns_smoke).load(repair=True)
            self.assertEqual(len(repaired_rows), 1)
            self.assertTrue((ns_smoke / "repair_log.json").is_file())

    def test_full_dry_smoke_verify_dev_determinism_freeze_formal(self):
        with test_scratch("full-e4") as base:
            c = make_dry_context(base)
            self.assertTrue(c.run_id.startswith("E4-DRY-"))
            self.assertEqual(run.run_stage(c, "smoke")["terminal_records"], 174)
            self.assertEqual(c.gate("smoke")["status"], "pass")
            run.verify(c)
            self.assertEqual(run.run_stage(c, "dev")["terminal_records"], 1160)
            self.assertEqual(c.gate("dev")["status"], "pass")
            dev_analysis = run.analyze_stage(c, "dev")
            self.assertEqual(dev_analysis["n_all"], 20)
            det = run.determinism(c)
            self.assertEqual((det["status"], len(det["checks"])), ("pass", 20))
            with self.assertRaises(ValueError):
                admission.check_stage(c, "formal")

            bad_cal = run._make_dry_calibration_artifact(status="calibration_failed_stop_s5")
            with self.assertRaises(ValueError):
                run.prepare_dry(c, freeze=True, calibration=bad_cal)

            custom_cal = run._make_dry_calibration_artifact(
                selected_family="hybrid_pct_tango_e4",
                status="pass",
            )
            run.prepare_dry(c, freeze=True, calibration=custom_cal)
            self.assertTrue((c.freeze_dir / "PLAN-E4.frozen.md").is_file())
            self.assertTrue((c.freeze_dir / "calibration-e4.json").is_file())
            admission.check_stage(c, "formal")
            self.assertEqual(len(c.plan("formal")), 4160)
            self.assertEqual(run.run_stage(c, "formal", limit=2)["terminal_records"], 2)
            with self.assertRaises(ValueError):
                run.analyze_stage(c, "formal")
            partial_analysis = run.analyze_stage(c, "formal", allow_partial=True)
            self.assertEqual(partial_analysis["analysis_mode"], "partial_diagnostic")

            c_session2 = run.Context("qwen3-8b@dry", dry=True, base=base)
            seed_stage_e4(c_session2, "formal")
            formal_analysis = run.analyze_stage(c_session2, "formal")
            self.assertEqual(formal_analysis["analysis_mode"], "s7_formal_complete")
            self.assertEqual(formal_analysis["records_analyzed"], 4160)
            self.assertEqual(formal_analysis["primary_method"], "pct")


if __name__ == "__main__":
    unittest.main(verbosity=2)
