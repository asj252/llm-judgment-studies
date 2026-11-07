# Imperfective Paradox in LLMs — Experiment 4 (English Moorean Paradox vs. Multi-Criteria Verbalized Sampling) Preregistration

This is the public preregistration package for **Experiment 4** of the LLM imperfective-paradox & multi-estimate elicitation study (English Moorean belief-assertion conflicts vs. dual-criteria crisis/compliance utterances across four professional domains, single configuration `qwen3-8b@macmini-m6`, runner fingerprint `8c93bc6870a1a00500c3e91c7fd842a100e7d573c33c965963c6ccddec8dce2d`). **No formal-run (`formal`) results are included, and zero formal units had been executed when this package was published.**

- **Relationship to Experiments 1–3**:
  - Experiment 1 (English `ImperfectiveNLI` bare progressive baseline) was preregistered at commit [`a6c90b51c3bf2e3c21c34f017bd5549126322762`](https://github.com/asj252/llm-judgment-studies/commit/a6c90b51c3bf2e3c21c34f017bd5549126322762) under [`../imperfective/`](../imperfective/).
  - Experiment 2 (Mandarin Chinese minimal-pair aspectual markers) was preregistered at commit [`a42fbbea113a6d0eaab423f440a4b64b7a6d3215`](https://github.com/asj252/llm-judgment-studies/commit/a42fbbea113a6d0eaab423f440a4b64b7a6d3215) under [`../imperfective-exp2-zh/`](../imperfective-exp2-zh/).
  - Experiment 3 (English activity boundary modifiers) was preregistered at commit [`d793eaafdb42222cc0a993cddba3baf1f700bf23`](https://github.com/asj252/llm-judgment-studies/commit/d793eaafdb42222cc0a993cddba3baf1f700bf23) under [`../imperfective-exp3-en/`](../imperfective-exp3-en/).
  - Experiment 4 is published in this separate directory (`imperfective-exp4-moore/`) without modifying any preregistered files from Experiments 1–3.
- **Frozen Stage S5 artifacts (`exp4-moore/freeze/qwen3-8b@macmini-m6/8c93bc68/`)**:
  - `PLAN-E4.frozen.md` (`SHA-256: 750339807d4b97a96cf1702eafe73c062e783069851639d3084cbaee3775ad85`)
  - `calibration-e4.json` (`SHA-256: 4de801144abc35dd75b67a768d279a8b5582d8b6d6536e669dbdf26237b604df`)
  - `c-review.md` (`SHA-256: 3621d32131d8e75e9921254a71286471d77464d661e4d40da468cb6f5f169cdf`)

## Design overview (Experiment 4, English Moore's Paradox vs. Verbalized Sampling)

Across Experiments 1–3, switching from single-estimate probability elicitation (`P`) to 5-estimate Verbalized Sampling (`M` / VS) reduced zero-shot completion/occurrence ratings on underspecified aspectual sentences. Experiment 4 tests whether VS acts as an **indiscriminate downward compressor / variance hedge** or as a **context-sensitive multi-perspective decomposer** by contrasting:

1. **`PURE_MOORE` (Single-Standard Atomic Fact Moorean Contradiction — Floor Baseline)**:
   A speaker sincerely asserts an unambiguous atomic physical fact $p$ while simultaneously denying belief in $p$ (`"p, but I do not believe that p"`). Under a single unambiguous standard, this is a pragmatic self-contradiction (expected coherence near `0%`).
2. **`DUAL_MOORE` (Dual-Criteria Crisis Context Bare Moorean Utterance — Core Test Slot)**:
   In a situation where a local technical/procedural checklist criterion (`local_mod`) is satisfied while a broader systemic crisis/safety criterion (`global_mod`) fails, the speaker utters the bare Moorean sentence (`"p, but I do not believe that p"`). Under zero-shot single-estimate elicitation (`P/Z`), surface proximity to `"p, but I do not believe that p"` pulls coherence ratings toward the floor; under multi-perspective elicitation (`M_U/CF` or `M_W/CF`), decomposing candidate interpretations across local vs. global standards can recover latent pragmatic coherence.
3. **`DUAL_EXPLICIT` (Dual-Criteria Explicitly Disambiguated Utterance — Upper Anchor)**:
   In the same crisis context, the speaker explicitly disambiguates the two standards (`"p by the standard of {local_mod}, but I do not believe that p in terms of {global_mod}"`).
4. **`PURE_READ` (Non-Assertive Script/Line Reading Control — Speech-Act Control)**:
   The speaker reads the bare Moorean sentence aloud from a printed card during a rehearsal without asserting personal belief.

All **100 newly authored English event clusters** across 4 balanced professional domains (`D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`, 25 clusters each: `5 dev + 20 formal`)—comprising `400` main items (`PURE_MOORE`, `DUAL_MOORE`, `DUAL_EXPLICIT`, `PURE_READ`) plus `200` deterministic diagnostic items (`DIAG_POS`, `DIAG_NEG`) sharing the identical cluster hypothesis $H_{\text{coh}}$ (`"The speaker's utterance in this situation is coherent and does not commit the speaker to a self-contradiction."`)—are redistributed directly in `exp4-moore/data/clusters_100_e4.json` (`SHA-256: f0a2de8192a1c7321e8903818920036b8dcce1b607644f4c3381a5d41768b3f3`). In `exp4-moore/split.json` (`SHA-256: 1552968c6b597b37b18eb349ba81f0c08e0faa037d66bfcf468bb2a5d8055731`, stratified seed `2026110601`):

- `dev` holds 20 clusters (`5` per domain = `80` main items × 13 conditions + `40` diagnostic items × 3 conditions = `1,160` units), completed with `1,157/1,160` (`99.7414%`) `status == "ok"` (`0.2586%` missing, `99.62` vs. `0.00` diagnostic `P/Z` separation, and `20/20` raw-token determinism match under `DETERMINISM_SEED_E4 = 2026110692`).
- `formal` holds the disjoint 80 clusters (`20` per domain = `320` main items × 13 conditions = `4,160` units), untouched prior to this preregistration.

## Primary confirmatory family (`m = 4`, Scheme E4) and S4/S5 calibration lock

Primary confirmatory inference on `formal` tests an `m = 4` one-sided paired-cluster contrast family ($H_0: \theta_j \le 0$ vs. $H_1: \theta_j > 0$) across all $n = 80$ formal clusters at family-wise Holm $\alpha_{\text{fam}} = 0.05$ (`B = 5000` cluster bootstrap draws, pre-registered seed `FORMAL_ANALYSIS_SEED_E4 = 2026110602`, simultaneous two-sided `98.75%` intervals):

| Slot | Target contrast ($n = 80$ formal clusters) | Status under locked S4 calibration |
|---|---|---|
| `E4_H1` | $\mu(\text{DUAL\_EXPLICIT}; P/\text{Z}) - \mu(\text{DUAL\_MOORE}; P/\text{Z})$ (baseline Moorean penalty on un-disambiguated dual-criteria utterances under `P/Z`) | **Active Layer 1 confirmatory** (`hybrid_bessel_t_tango_e4`, $c_{80} = 1.0298680169611695$) |
| `E4_H2` | $\mu(\text{DUAL\_MOORE}; M_U/\text{CF}) - \mu(\text{DUAL\_MOORE}; P/\text{Z})$ (multi-perspective VS recovery over zero-shot single-estimate on `DUAL_MOORE`) | **Active Layer 1 confirmatory** (`hybrid_bessel_t_tango_e4`, $c_{80} = 1.0298680169611695$) |
| `E4_H3` | $[\mu(\text{DUAL\_MOORE}; M_U/\text{CF}) - \mu(\text{DUAL\_MOORE}; P/\text{Z})] - [\mu(\text{PURE\_MOORE}; M_U/\text{CF}) - \mu(\text{PURE\_MOORE}; P/\text{Z})]$ (selective VS recovery on `DUAL_MOORE` vs. `PURE_MOORE` floor control, paired difference-in-differences) | **Active Layer 1 confirmatory** (`hybrid_bessel_t_tango_e4`, $c_{80} = 1.0298680169611695$) |
| `E4_H4` | $\Pr(\text{True on DUAL\_EXPLICIT}; L/\text{CoT}) - \Pr(\text{True on DUAL\_MOORE}; L/\text{CoT})$ (discrete-label `True` classification gap under `L/CoT`) | **Active Layer 1 confirmatory** (certified exact Tango score-test inversion at $n = 80$) |

**Locked S4 20-cell calibration (`exp4-moore/freeze/qwen3-8b@macmini-m6/8c93bc68/calibration-e4.json`)**: Under the pre-specified 20-cell Monte Carlo calibration (`5 DGPs × 4 null/alternative/shared-missingness configs`, `R = 2000`, `B = 5000`, `seed = 2026110611`, `dev_joint_complete_123_count = 20`), Candidate 2 (**`hybrid_bessel_t_tango_e4`**, with finite-sample Bessel-$t$ expansion factor $c_{80} = 1.0298680169611695$ on continuous slots `E4_H1..E4_H3` and certified exact Tango inversion on `E4_H4`) passed **all 20/20 cells across all four hard gates** (`FWER = 0.0040..0.0365 <= 0.059747`, `simultaneous 98.75% coverage = 0.9410..0.9680 >= 0.940253`, `individual 98.75% coverage = 0.9755..0.9960 >= 0.9750`, `max screen05 = 0.0155..0.0505 <= 0.0750`), with **zero slot demotions (`demoted_slots = []`, `selected_step = 2`)** and **`companion_family = "hybrid_pct_tango_e4"`** (`19/20` cells passed) co-reported on the identical bootstrap stream (`2026110602`).

## Offline verification

From `imperfective-exp4-moore/`, run:

```sh
python -X utf8 -B verify_prereg_e4.py
python -X utf8 -B -m unittest test_prereg_e4_offline.py -v
```

`verify_prereg_e4.py` uses only the Python standard library and verifies all public files in `release-check.json`, all frozen code/material/table/calibration/freeze SHA-256 bindings, 100-cluster linguistic/mechanical invariants (`validate_materials_e4.py`), and full in-memory recomputation of all `5,320` (`1,160 dev + 4,160 formal`) rendered unit message digests and the Experiment 4 runner fingerprint (`8c93bc6870a1a00500c3e91c7fd842a100e7d573c33c965963c6ccddec8dce2d`).
