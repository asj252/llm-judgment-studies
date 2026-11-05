# Imperfective Paradox in LLMs — Experiment 3 (English Activity Boundary Modifier Contrast) Preregistration

This is the public preregistration package for **Experiment 3** of the LLM imperfective-paradox study (English atelic activity `B/D` controlled single-slot aspectual boundary modifiers contrasting minimal occurrence vs. bounded plan/task/period completion, single configuration `qwen3-8b@macmini-m6`, runner fingerprint `cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3`). **No formal-run (`formal`) results are included, and zero formal units had been executed when this package was published.**

- **Relationship to Experiments 1 and 2**:
  - Experiment 1 (English `ImperfectiveNLI` bare progressive baseline) was preregistered at commit [`a6c90b51c3bf2e3c21c34f017bd5549126322762`](https://github.com/asj252/llm-judgment-studies/commit/a6c90b51c3bf2e3c21c34f017bd5549126322762) under [`../imperfective/`](../imperfective/).
  - Experiment 2 (Mandarin Chinese minimal-pair aspectual markers) was preregistered at commit [`a42fbbea113a6d0eaab423f440a4b64b7a6d3215`](https://github.com/asj252/llm-judgment-studies/commit/a42fbbea113a6d0eaab423f440a4b64b7a6d3215) under [`../imperfective-exp2-zh/`](../imperfective-exp2-zh/).
  - Experiment 3 is published in this separate directory (`imperfective-exp3-en/`) without modifying any preregistered files from Experiment 1 or Experiment 2.
- **Frozen Stage S5 artifacts (`exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/`)**:
  - `PLAN-E3.frozen.md` (`SHA-256: ec4137b4a280b34977a26d755bd414b81392ec3419f6b9a84e4e6de941f3082b`)
  - `calibration-e3.json` (`SHA-256: 0719bb94336a2b18e1795aae7767714169ddf94c60502aa542b14454a0a44806`)
  - `c-review.md` (`SHA-256: 70acde0775c2fd7d1e3806264519665ff45f2cfa19d26a430bda0014a932f87f`)

## Design overview (Experiment 3, English Activity Boundary Modifier Contrast)

In Experiment 1 (`qwen3-8b@macmini-m6`), English bare Simple Past hypotheses (`H_orig`) on the 100 atelic activity clusters (`D_001..D_100` non-interrupted, `B_001..B_100` interrupted) received near-ceiling zero-shot probability ratings (`D: 98.78`, `B: 99.64` under `P/Z`) but collapsed under `M_U/CoT` (`D: 65.37`, `B: [72.20, 73.45]`) and `L/CoT` (`73/80` `D` items labeled `Unknown`). Experiment 3 tests whether this divergence reflects pragmatic competition between an **unbounded minimal-occurrence reading** and a **bounded plan/task/period-completion reading** by introducing controlled single-slot aspectual modifiers (`h_occ` vs. `h_plan`) on the exact same 100 `D_k`/`B_k` cluster pairs (`exp3-en/subclasses_e3.json`, `SHA-256: ff3be2370261c499397fbfba9921086cb69467775d196e53bf6d83912c01721d`):

1. **Goal-Prone / Planned Activity (`A_plan`, 24 clusters: 8 `dev`, 16 `formal`)**:
   - `A_plan_task` (20 clusters: 7 `dev`, 13 `formal`): `h_occ = H_base + " for a bit."` vs. `h_plan = H_base + " all the way to completion."`
   - `A_plan_deg` (4 clusters: 1 `dev`, 3 `formal`): `h_occ = H_base + " for a bit."` vs. `h_plan = H_base + " completely."`
2. **Pure Unbounded Activity (`A_pure`, 76 clusters: 12 `dev`, 64 `formal`)**:
   - `h_occ = H_base + " for a bit."` vs. `h_plan = H_base + " throughout the entire period."`

In `exp3-en/split.json` (`SHA-256: cd0e099a38481b23c071d3950aac4527daf29aea12076f34ea9eadc4a90d7ea4`, inheriting the exact `20 dev` / `80 formal` atelic cluster partition from Experiment 1):
- `dev` holds 20 clusters (`8 A_plan + 12 A_pure` = `80` main items × 13 conditions + `40` diagnostic items × 3 conditions = `1,160` units), completed with `1,040/1,040` (`100.0%`) main units `status == "ok"` (`1,159/1,160` overall), `100.0` vs. `0.0` diagnostic `P/Z` separation across all 3 template subclasses, and `20/20` raw-token determinism match.
- `formal` holds the disjoint 80 clusters (`16 A_plan + 64 A_pure` = `320` main items × 13 conditions = `4,160` units), untouched prior to this preregistration.

## Primary confirmatory family (`m = 4`, Scheme E3) and S4/S5 calibration lock

Primary confirmatory inference on `formal` tests an `m = 4` one-sided paired-cluster contrast family ($H_0: \theta_j \le 0$ vs. $H_1: \theta_j > 0$) across all $n = 80$ formal clusters at family-wise Holm $\alpha_{\text{fam}} = 0.05$ (`B = 5000` cluster bootstrap draws, pre-registered seed `FORMAL_ANALYSIS_SEED_E3 = 2026110401`, simultaneous two-sided `98.75%` intervals):

| Slot | Target contrast ($n = 80$ formal clusters) | Status under locked S4 calibration |
|---|---|---|
| `E3_H1` | $\mu(\text{NI\_OCC}; P/\text{Z}) - \mu(\text{NI\_PLAN}; P/\text{Z})$ (non-interrupted minimal-occurrence vs. bounded-completion modifier under `P/Z`) | **Active Layer 1 confirmatory** (`hybrid_bessel_t_tango_e3`, $c_{80} = 1.0298680169611695$) |
| `E3_H2` | $\mu(\text{INT\_OCC}; P/\text{Z}) - \mu(\text{INT\_PLAN}; P/\text{Z})$ (early-interrupted minimal-occurrence vs. bounded-completion modifier under `P/Z`) | **Active Layer 1 confirmatory** (`hybrid_bessel_t_tango_e3`, $c_{80} = 1.0298680169611695$) |
| `E3_H3` | $\mu(\text{NI\_PLAN}; M_U/\text{CoT}) - \mu(\text{INT\_PLAN}; M_U/\text{CoT})$ (non-interrupted vs. interrupted bounded-completion modifier under `M_U/CoT`) | **Demoted per Step 3 (`demoted_slots = ["E3_H3"]`) to Layer 3 exploratory** (Layer 1 retains $m = 4$ and Holm denominators `4, 3, 2, 1` with `E3_H3` fixed to $p = 1.0, \text{CI}_{98.75\%} = [-100, 100]$) |
| `E3_H4` | $\Pr(\text{True on NI\_OCC}; L/\text{CoT}) - \Pr(\text{True on NI\_PLAN}; L/\text{CoT})$ (non-interrupted `True` classification rate on `NI_OCC` vs. `NI_PLAN` under `L/CoT`) | **Active Layer 1 confirmatory** (certified exact Tango score-test inversion at $n = 80$) |

**Locked S4 20-cell calibration (`exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/calibration-e3.json`)**: Under the pre-specified 20-cell Monte Carlo calibration (`5 DGPs × 4 null/alternative/missingness configs`, `R = 2000`, `B = 5000`, `seed = 2026110411`, `dev_joint_mode = "joint_123"`), `E3_H3` exhibited near-degenerate ceiling concentration on `dev` (17/20 clusters equal to `0.0` alongside a `+30.0` outlier on cluster `085`), causing Candidate 1 (`15/20` passed) and Candidate 2 (`17/20` passed) to fall slightly short on `DGP1_emp` individual coverage for `E3_H3` (`0.9610..0.9705 < 0.975`) while `E3_H1`, `E3_H2`, and `E3_H4` passed all 20 cells. Per `PLAN-E3.md` §4.2(5) Step 3, `calibrate_e3.py` deterministically demoted `E3_H3` (`selected_step = 3`, `selected_family = "hybrid_bessel_t_tango_e3"`, `companion_family = "hybrid_pct_tango_e3"`, `demoted_slots = ["E3_H3"]`), achieving **20/20 cells passed across all four hard gates** (`FWER = 0.0095..0.0400 <= 0.059747`, `simultaneous 98.75% coverage = 0.9605..0.9925 >= 0.940253`, `individual 98.75% coverage = 0.9815..0.9990 >= 0.9750`, `max screen05 = 0.0285..0.0645 <= 0.0750`).

## Offline verification

From `imperfective-exp3-en/`, run:

```sh
python -X utf8 -B verify_prereg_e3.py
python -X utf8 -B -m unittest test_prereg_e3_offline.py -v
```

See [`third-party-data.md`](third-party-data.md) for local acquisition of the two upstream files (`imperfectiveNLI.json` and `run_inference.py.txt`) to enable full in-memory recomputation of all `5,320` rendered unit digests and `fingerprint_id = cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3`.
