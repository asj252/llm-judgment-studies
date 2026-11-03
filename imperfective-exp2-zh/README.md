# Imperfective Paradox in LLMs — Experiment 2 (Chinese) Preregistration

This is the public preregistration package for **Experiment 2** of the LLM imperfective-paradox study (Mandarin Chinese minimal-pair aspectual markers, resultative/completive/satiation complements vs. bare perfective `-le` `V了`, single configuration `qwen3-8b@macmini-m6`, runner fingerprint `f81940ea79504f533d62d796a10812b2dd8e170f9b95a9d6e813d0d4e736b74b`). **No formal-run (`formal`) results are included, and zero formal units had been executed when this package was published.**

- **Relationship to Experiment 1**: Experiment 1 (English `ImperfectiveNLI`) was preregistered at commit [`a6c90b51c3bf2e3c21c34f017bd5549126322762`](https://github.com/asj252/llm-judgment-studies/commit/a6c90b51c3bf2e3c21c34f017bd5549126322762) under [`../imperfective/`](../imperfective/). Per the commitment in `imperfective/PREREGISTRATION_RECORD.md`, Experiment 2 is published in this separate directory (`imperfective-exp2-zh/`) without modifying any of the 65 preregistered Experiment 1 files.
- **Stage S5 freeze record**: `exp2-zh/freeze/qwen3-8b@macmini-m6/f81940ea/freeze.json` (`SHA-256: ffa29ab0d5c6455fe878c34c49a3df7044054793ddb1e7538818abc74a3a41ae`), binding frozen specification `PLAN-E2.frozen.md` (`SHA-256: 81fd2fe12540cc665fa650ffde3224ac95e9d08902af501b6cd2400212bac2c9`), S4 16-cell production calibration `calibration-e2.json` (`SHA-256: 4ad1af9ccfe15bdc89a3e51b861f9503e1ed77b0e686d72f1954b748aca11d32`), and independent critic review `c-review.md` (`SHA-256: 5cdaf9f192789302f175811f1cbbd1bb3d5524bb7bf63b021c10a9be3455f7b0`).

## Design overview (Experiment 2, Mandarin Chinese)

English Simple Past (`V-ed`, e.g. *ran on the track*, *pushed the broken car*, *built the gazebo*) conflates *minimal occurrence/actualization* and *telic culmination / bounded task completion*. Mandarin Chinese grammatically separates these two readings via strict single-insertion minimal pairs within each event cluster:

1. **Bare verbal `-le` (`V了`, `h_bare`)**: bare verb root plus post-verbal perfective `-le` without a resultative/completive/satiation complement (e.g., `盖了那座木亭`, `在体育场跑道上跑了步`, `在湖边步道上散了步`).
2. **Complement + `-le` (`V + comp_marker + 了`, `h_comp`)**: identical sentence with a single complement inserted immediately between `verb_root` and `了` (`h_comp.replace(f"{verb_root}{comp_marker}了", f"{verb_root}了", 1) == h_bare` holds across all 100 clusters):
   - **Telic clusters (`T`, 60 clusters: 12 `dev`, 48 `formal`)**: resultative/completive complements (`好` 31, `完` 16, `干净` 4, `干` 2, `断` 2, `光` 2, `熟` 1, `平整` 1, `锋利` 1) across 4 subclasses (`Creation` 26, `Change of State` 18, `Consumption` 10, `Motion to Goal` 6).
   - **Atelic clusters (`A`, 40 clusters: 8 `dev`, 32 `formal`)**:
     - `Goal-Prone / Planned Activity` (`A_plan`, 20 clusters: 4 `dev`, 16 `formal`): completive `完` (`20/20`, e.g., `跑完了步`, `推完了那辆抛锚的轿车`).
     - `Pure Unbounded Activity` (`A_pure`, 20 clusters: 4 `dev`, 16 `formal`): subjective satiation complement `够`/`足` (`够` 18, `足` 2, e.g., `散够了步`, `晒足了太阳`).

All **100 authored Chinese event clusters** (`400` main items across the $2 \times 2$ premise–hypothesis slots `NI_COMP`, `NI_BARE`, `INT_COMP`, `INT_BARE` + `200` deterministic diagnostic context items `DIAG_POS_COMP`, `DIAG_NEG_COMP` = `600` items total) are redistributed directly in `exp2-zh/data/clusters_100_curated.json` (`SHA-256: 963636a2a74a38f8b8fe6363a079be38f5f2f1b35ef37f1cf3fc89dd7fd6c437`). In `exp2-zh/split.json` (`SHA-256: 6382d84a293107215ab034d565415adc8f0a438d90152f4c2b2e9a8d868c3973`, stratified seed `2026110202`):

- `dev` holds 20 clusters (`12 T + 4 A_plan + 4 A_pure` = `80` main items × 13 conditions + `40` diagnostic items × 3 conditions = `1,160` units), completed with `1,157/1,160` `status == "ok"` (`0.2586%` missing, `100.0` vs. `0.0` diagnostic `P/Z` separation, and `20/20` raw-token determinism match).
- `formal` holds the disjoint 80 clusters (`48 T + 16 A_plan + 16 A_pure` = `320` main items × 13 conditions = `4,160` units), untouched prior to this preregistration.

## Primary confirmatory family (`m = 4`, Scheme E2) and S4/S5 calibration lock

Primary confirmatory inference on `formal` tests an `m = 4` one-sided paired-cluster contrast family ($H_0: \theta_j \le 0$ vs. $H_1: \theta_j > 0$) at family-wise Holm $\alpha_{\text{fam}} = 0.05$ (`B = 5000` cluster bootstrap draws, pre-registered seed `FORMAL_ANALYSIS_SEED_E2 = 2026110301`, simultaneous two-sided `98.75%` intervals):

| Slot | Target contrast | Cluster stratum |
|---|---|---|
| `E2_H1` | $\mu_T(\text{NI\_BARE}; P/\text{Z}) - \mu_T(\text{NI\_COMP}; P/\text{Z})$ (telic non-interrupted bare `-le` vs. resultative/completive complement under `P/Z`) | `T` ($n_T = 48$ telic clusters) |
| `E2_H2` | $\mu_T(\text{NI\_COMP}; P/\text{Z}) - \mu_T(\text{NI\_COMP}; M_U/\text{Z})$ (telic resultative/completive single-estimate vs. multi-estimate mean under `Z`) | `T` ($n_T = 48$ telic clusters) |
| `E2_H3` | $\mu_A(\text{INT\_BARE}; P/\text{Z}) - \mu_A(\text{INT\_COMP}; P/\text{Z})$ (atelic early-interrupted bare `-le` occurrence vs. bounded complement under `P/Z`) | `A` ($n_A = 32$ atelic clusters; co-reported by `A_plan` $n=16$ and `A_pure` $n=16$) |
| `E2_H4` | $\Pr_A(\text{True on NI\_BARE}; L/\text{CoT}) - \Pr_A(\text{True on NI\_COMP}; L/\text{CoT})$ (atelic non-interrupted `True` classification rate on bare `-le` vs. bounded complement under `L/CoT`) | `A` ($n_A = 32$ atelic clusters; certified exact Tango score-test inversion) |

**Locked S4 16-cell calibration (`exp2-zh/freeze/qwen3-8b@macmini-m6/f81940ea/calibration-e2.json`)**: Under the pre-specified 16-cell Monte Carlo calibration (`4 DGPs × 4 null/alternative/shared-missingness configs`, `R = 2000`, `B = 5000`, `seed = 2026110311`), Candidate 2 (**`hybrid_bessel_t_tango_e2`**, with finite-sample Bessel-$t$ expansion factors $c_{48} = 1.0509502165481253$ and $c_{32} = 1.0787284625848519$ on continuous slots `E2_H1..E2_H3` and certified exact Tango inversion on `E2_H4`) passed **all 16/16 cells across all four hard gates** (`max FWER = 0.0450 <= 0.059747`, `min simultaneous 98.75% coverage = 0.9455 >= 0.940253`, `min individual 98.75% coverage = 0.9805 >= 0.9750`, `max screen05 = 0.0630 <= 0.0750`). Accordingly, `freeze.json` locks **`selected_family = "hybrid_bessel_t_tango_e2"`** (`selected_step = 2`, **`demoted_slots = []`**), with **`companion_family = "hybrid_pct_tango_e2"`** co-reported on the identical bootstrap stream (`2026110301`).

## Offline verification

From `imperfective-exp2-zh/`, run:

```sh
python -X utf8 -B verify_prereg_e2.py
```

`verify_prereg_e2.py` uses only the Python standard library and verifies all 45 public files in `release-check.json`, all frozen code/material/table/calibration/freeze SHA-256 bindings, 100-cluster linguistic/mechanical invariants (`validate_materials.py`), and full in-memory recomputation of all `5,320` (`1,160 dev + 4,160 formal`) rendered unit message digests and the Experiment 2 runner fingerprint (`f81940ea79504f533d62d796a10812b2dd8e170f9b95a9d6e813d0d4e736b74b`).

To run the offline unit test suite, run from `imperfective-exp2-zh/`:

```sh
python -X utf8 -B -m unittest test_prereg_e2_offline.py -v
```
