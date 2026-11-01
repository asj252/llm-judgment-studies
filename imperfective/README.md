# Imperfective Paradox in LLMs — Experiment 1 Preregistration

This is the public preregistration package for **Experiment 1** of the LLM imperfective-paradox study (English probability and label-protocol comparison on `ImperfectiveNLI`, single configuration `qwen3-8b@macmini-m6`, runner fingerprint `895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2`). **No formal-run (`formal`) results are included, and zero formal units had been executed when this package was published.**

- **Internal freeze preparation record**: committed in the internal research repository at commit `79a19522` (`2026-11-01T19:23:42+08:00`), binding frozen Experiment 1 specification `s5-mac-handoff-20261101/PLAN-E1.md` (`SHA-256: 59aa81d09c30ecc04c5bdb5d5cf26c052a51a2d719f9767b9a8fa256a13fecd6`) and execution manifest `s5-mac-handoff-20261101/s6-s7-execution-manifest.json` (`SHA-256: ca5c5bd1b5159652772aee77f08ea2601cccc6327d76f04fcbfd8ee4f45d8f22`).
- **First public preregistration commit**: after pushing this package to <https://github.com/asj252/llm-judgment-studies>, a subsequent explanatory commit adds `imperfective/PREREGISTRATION_RECORD.md` naming that first public commit's hash and timestamp before any formal unit is executed, without modifying any preregistered file.
- **Language note**: `PLAN.md` (overall two-experiment plan v0.5) and `s5-mac-handoff-20261101/PLAN-E1.md` (Experiment 1 frozen confirmatory and Option-III preregistration specification) are in Chinese. Sections 1–7 of `PLAN-E1.md` specify the complete experimental design, prompt templates, parsing/scoring rules, primary confirmatory family, pre-freeze simulation calibration disclosure, and three-tier interpretive claim boundaries. Experiment 2 (Chinese authored materials) is planned separately and is not yet frozen here.

## Design overview (Experiment 1)

`ImperfectiveNLI` comprises 400 English premise–hypothesis items across 100 telic (`A`/`C`) and 100 atelic (`B`/`D`) verb clusters (`A`: telic interrupted, gold `False`; `C`: telic open progressive, gold `Unknown`; `B`: atelic interrupted, gold `True`; `D`: atelic open progressive, gold `True`). In `exp1-en/split.json` (`SHA-256: 6821a3b3ad2378d51c683b8abc8a5b45d402b9997e3c8957bcda95cd0ef289b7`):

- `dev` holds 40 clusters (`20 AC + 20 BD` = 80 items × 13 conditions = `1,040` units; `smoke` is a 4-item / 52-unit subset of `dev`), already completed with `0` missing units and `20/20` raw-token determinism verification.
- `formal` holds the disjoint 160 clusters (`80 AC + 80 BD` = 320 items × 13 conditions = `4,160` units), untouched prior to this preregistration.

Each item is evaluated across **13 conditions** under deterministic greedy decoding (`temperature = 0.0`, `top_k = 1`, `MAX_TOKENS = 1024`, Qwen3-8B `Q8_0` via `llama-server` build `b11560-b13a93a3d` on Apple Silicon Metal):

- **Task `L`** (`Z`, `DAP`, `CoT`, `CF`): discrete three-way NLI classification (`True` / `False` / `Unknown`) using the upstream literal prompt templates, plus bounded first-letter label-token probability score `q`.
- **Task `Ps`** (`Z`): probability protocol control pairing the upstream premise/hypothesis wording (`necessarily true given only the Premise`) with a direct `0–100%` probability output format.
- **Task `P`** (`Z`, `DAP`, `CoT`, `CF`): single direct common-sense probability estimate (`Probability: NN%`).
- **Task `M`** (`Z`, `DAP`, `CoT`, `CF`): five weighted probability estimates (`Estimate 1..5: NN% | Weight: W`, normalized mean $M_U$).

## Primary confirmatory family (`m = 4`, Scheme A) and Option-III calibration disclosure

Primary confirmatory inference on `formal` tests an `m = 4` paired-cluster contrast family at family-wise Holm $\alpha = 0.05$ (`B = 5000` cluster bootstrap draws, pre-registered seed `FORMAL_ANALYSIS_SEED = 2026110201`, simultaneous nominal `98.75%` two-sided intervals):

| Slot | Target contrast | Cluster stratum ($n = 80$) |
|---|---|---|
| `SA1` | $\text{TBR}_C(L/\text{CoT}) - \text{TBR}_C(L/\text{Z})$ (telic progressive `True`-bias reduction under `CoT`) | `AC` (`80` telic clusters) |
| `SA2` | $[(C - A)_{P/\text{CoT}} - (C - A)_{M_U/\text{Z}}]$ (paired interruption sensitivity: single-estimate `CoT` vs. multi-estimate zero-shot) | `AC` (`80` telic clusters) |
| `SA3` | $[(D - B)_{M_U/\text{CoT}} - (D - B)_{P/\text{CoT}}]$ (atelic over-transfer penalty when stacking `M` onto `CoT`) | `BD` (`80` atelic clusters) |
| `SA4` | $\text{TBR}_C(L/\text{Z}) - \mathbb{E}[P_C(P/\text{Z})]/100$ (discrete binary/ternary forced-choice distortion vs. direct probability under zero-shot) | `AC` (`80` telic clusters) |

**Pre-freeze calibration disclosure (Option III, `PLAN-E1.md` §1.2 & §5.1)**: In the sealed Step 5b simulation calibration (`R = 2000`, `B = 5000`, 88 null/boundary cells + 56 power cells; `scheme-a-hybrid-calibration-20261101/report-final.md`), replacing percentile intervals on discrete binary slot `SA1` with exact score-test inversion (`Tango` 1998) resolved discrete boundary under-coverage, raising 88-cell joint pass counts from pure percentile `72/88` to **`82/88`** for both `hybrid_pct_tango` and `hybrid_bessel_t_tango` (`D_j = 5/5` degeneracy checks, `P_j = 17/17` power checks; empirical `dev`-anchored `all4` power `0.9945` and `0.9925`). The remaining 6 flagged cells (all continuous-slot high-skew / small-cluster stresses) exceeded the fixed unbuffered `screen0125 <= 0.01875` threshold slightly (maximum `0.0215` for `hybrid_pct_tango`, `0.0225` for `hybrid_bessel_t_tango`), triggering `branch_id = 4` (`descriptive_downgrade_or_stop`). By explicit author decision prior to any `formal` run (Option III, without touching the hard-disabled `confirmation` seed bank `2026110102`):

1. **`hybrid_pct_tango`** is locked as the primary confirmatory procedure, and **`hybrid_bessel_t_tango`** ($c_{80} = \sqrt{80/79} \approx 1.0298684039$) is co-reported on the identical bootstrap stream (`2026110201`) as a pre-registered sensitivity companion.
2. **Three-tier claim boundary**:
   - *Tier 1 (robust directional confirmation)* requires simultaneous Holm rejection ($\alpha = 0.05$) with concordant sign under **both** `hybrid_pct_tango` and `hybrid_bessel_t_tango`, always accompanied by the empirical calibration disclosure (`C_j = 82/88`, max unbuffered `screen0125 = 0.0215`).
   - *Tier 2 (method-sensitive boundary signal)* applies if only one of the two procedures rejects; claims are restricted to boundary-sensitive evidence.
   - *Tier 3 (descriptive / diagnostic)* covers all secondary metrics (`H1–H6` 10-contrast legacy family, bounded `q`, `Ps/Z`, `DAP`, `CF`, candidate spread, and format/cost profiles).

## Files

- `PLAN.md`, `s5-mac-handoff-20261101/PLAN-E1.md`, `s5-mac-handoff-20261101/s6-s7-execution-manifest.json`: overall study plan, frozen Experiment 1 specification, and acyclic SHA-256 execution bindings.
- `exp1-en/split.json`, `exp1-en/label_tokens_qwen3-8b.json`, `exp1-en/test_prompt_golden.json`: frozen cluster/item ID split (`smoke`/`dev`/`formal`, IDs only), frozen Qwen3-8B label-token candidate sets, and synthetic prompt-format golden strings.
- `exp1-en/*.py`, `exp1-en/config_*.json`, `exp1-en/host_paths_macmini-m6.json`: frozen Experiment 1 runner, prompt renderer, parsers, strict protocol checker, bounded `q` scorer, ledger, admission gates, and macOS `llama-server` host adapter (all 24 hash-locked files plus `gpu_s3_stage_macos.py`).
- `scheme-a-hybrid-calibration-20261101/code/*.py`, `scheme-a-hybrid-calibration-20261101/manifests/{exact-tango-tables.npz, exact-tango-tables-meta.json, sealed-run-identity.json}`: sealed Step 5b statistical engine (`code_sha256 = 4e7030de928ec5a7a9fe398c557795ccd4f34a1693c7cebda475a675386537b1`) and certified exact Tango lookup tables (`SHA-256 = 090bfbb5a859238ad05100443b4727c61644e030fd2d5e05359c5d575f4c46bf`).
- `s5-mac-handoff-20261101/{gpu_s6_formal_stage_macos.py, run_s7_formal_analysis.py}`, `exp1-en/stats_validation/{__init__.py, core.py, studentized.py}`: hash-bound S6 formal execution wrapper, S7 `<100 MiB` streaming formal statistical analysis script, and secondary descriptive `H1–H6` (`m = 10`) support modules.
- `scheme-a-hybrid-calibration-20261101/{report-final.md, manifests/manifest-88.json, manifests/manifest-power56.json, results/candidate-selection-summary.json, results/summary-*.md}`: aggregate pre-freeze simulation manifests and calibration summaries (zero item text).
- `exp1-en/test_*.py`, `test_prereg_offline.py`: offline unit tests runnable without third-party datasets or raw execution ledgers.
- `verify_prereg.py`, `release-check.json`, `third-party-data.md`, `requirements.txt`: stdlib-only offline byte/binding verifier, file inventory and scan audit, third-party dataset acquisition guide, and Python dependency list (`numpy>=1.26` for statistical tests).

## Offline verification

From `imperfective/`, run:

```sh
python -X utf8 -B verify_prereg.py
```

`verify_prereg.py` uses only the Python standard library and never invokes models, writes files, or accesses the network. It verifies:

1. Every listed public file against `release-check.json` (byte count and SHA-256);
2. All 24 frozen `exp1-en/` file hashes, `split.json`, `PLAN-E1.md` (`59aa81d0...`), `s6-s7-execution-manifest.json` (`B = 5000`, `seed = 2026110201`, `confirmatory_unit_index_input_allowed = false`), and the S6/S7 entrypoint SHA-256s embedded inside `PLAN-E1.md`;
3. All 8 sealed Step 5b statistical modules, their combined `code_sha256` (`4e7030de...`), `exact-tango-tables.npz` (`090bfbb5...`), and `sealed-run-identity.json`;
4. Canonical reconstruction of `prompt_templates_canonical_sha256` (`6573fa60...`) directly from the 5 verbatim Task `L` template blocks in `PLAN-E1.md`;
5. Both excluded third-party files (`exp1-en/data/imperfectiveNLI.json` and `exp1-en/data/run_inference.py.txt`): reported as `self_acquisition_required` when absent (`ok: true`), or verified against every binding plus full 5,200-unit `materials` and runner `fingerprint_id` (`895f4e6f51ca3044...`) recomputation when present (`status: "verified"`).

To run the offline unit tests (after installing `requirements.txt` for NumPy), run from `imperfective/`:

```sh
python -X utf8 -B -m unittest discover -s exp1-en -p "test_*.py"
python -X utf8 -B -m unittest test_prereg_offline.py -v
```

(`exp1-en/test_subject.py` uses gitignored local HTTP scratch directories under `exp1-en/raw/dry/http-tests/` during execution.)

## Exclusions and unchanged path bindings

See [third-party-data.md](third-party-data.md) for upstream acquisition URLs, commit hash, and SHA-256 verification of `imperfectiveNLI.json` and `run_inference.py.txt`. No `ImperfectiveNLI` item text, raw execution ledgers (`exp1-en/raw/`), development-set model text responses, simulation chunk archives, or internal task/review/handoff documents are redistributed.

Nine hash-bound files (`exp1-en/config_assets_macmini-m6.json`, `exp1-en/host_paths_macmini-m6.json`, `exp1-en/gpu_preflight_macos.py`, `exp1-en/gpu_s3_stage_macos.py`, `s5-mac-handoff-20261101/PLAN-E1.md`, `s5-mac-handoff-20261101/gpu_s6_formal_stage_macos.py`, and CLI default constants in `scheme-a-hybrid-calibration-20261101/code/{inputs.py, manifest_a.py, formal_engine.py}`) contain non-sensitive external volume and local workspace paths (19 occurrences total, zero usernames or credentials). By the author's decision, these files are published byte-for-byte unchanged so that every frozen SHA-256 and runner/engine fingerprint remains directly verifiable.
