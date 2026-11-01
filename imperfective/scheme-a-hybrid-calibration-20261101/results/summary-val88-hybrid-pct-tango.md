# Scheme A Step 5b Simulation Executive Summary (`validation` / `hybrid_pct_tango`)

- **Bank / Seed**: `validation` (`2026110101`)
- **Method**: `hybrid_pct_tango`
- **Replicates per Cell**: 2000 (`B = 5000`)
- **Total Cells Evaluated**: 88
- **Cells Passing Main 98.75% Criteria**: 82 / 88
- **Cells Passing Historical 99.5% Criteria**: 73 / 88
- **Confirmation Bank Hard-Disabled**: `True`
- **Confirmation Status**: `confirmation_not_run`

## 1. Historical Block 3 8-Cell Reference Evaluation

| Index | Cell Name | Slot | Effect | In Step 5b P_j? | Power | 95% MCSE Interval | Status |
|---|---|---|---|---|---|---|---|
| 35 | `block3-SA1-0.15` | SA1 | +0.15 | YES | 0.9885 | [0.9837, 0.9933] | **sufficient** |
| 36 | `block3-SA1-0.20` | SA1 | +0.20 | YES | 1.0000 | [1.0000, 1.0000] | **sufficient** |
| 40 | `block3-SA2-12.5` | SA2 | +12.5 | NO (descriptive) | 0.3410 | [0.3198, 0.3622] | **insufficient** |
| 41 | `block3-SA2-18.0` | SA2 | +18.0 | NO (descriptive) | 0.5980 | [0.5761, 0.6199] | **insufficient** |
| 45 | `block3-SA3--8.5` | SA3 | -8.5 | NO (descriptive) | 0.0925 | [0.0795, 0.1055] | **insufficient** |
| 44 | `block3-SA3--12.5` | SA3 | -12.5 | NO (descriptive) | 0.2380 | [0.2190, 0.2570] | **insufficient** |
| 49 | `block3-SA4--0.30` | SA4 | -0.30 | YES | 0.9720 | [0.9646, 0.9794] | **sufficient** |
| 48 | `block3-SA4--0.45` | SA4 | -0.45 | YES | 1.0000 | [1.0000, 1.0000] | **sufficient** |

## 2. Pinned Boundary Degeneracy Gate D_j Monitoring (Threshold: 0.20)

| Gate ID | Index | Cell Name | Max Degeneracy Rate | SA1 | SA2 | SA3 | SA4 | Passed? |
|---|---|---|---|---|---|---|---|---|
| `D01` | 65 | `pinned-SA1-devlike` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `D02` | 66 | `pinned-SA1-shrunken` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `D03` | 67 | `pinned-SA4-devlike` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `D04` | 68 | `pinned-SA4-moderate-ceiling` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `D05` | 83 | `empirical-observed` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |

## Failed Cells Under Main 98.75% Criteria

| Index | Cell Name | Failed Checks | Max Degen Rate | Simult Cov 98.75% |
|---|---|---|---|---|
| 0 | `regular-null` | `screen0125` | 0.0000 | 0.9525 |
| 4 | `regular-partial-null-bd` | `screen0125` | 0.0000 | 0.9440 |
| 48 | `block3-SA4--0.45` | `screen0125` | 0.0000 | 0.9465 |
| 64 | `ties-SA4--0.30` | `screen0125` | 0.0000 | 0.9545 |
| 67 | `pinned-SA4-devlike` | `screen0125` | 0.0000 | 0.9590 |
| 68 | `pinned-SA4-moderate-ceiling` | `screen0125` | 0.0000 | 0.9545 |

## Complete Cell Screening Table (All 88 Cells)

| Index | Cell Name | FWER | Fam Dir Err | Simult Cov 98.75% | Max Degen | 98.75% Passed? |
|---|---|---|---|---|---|---|
| 0 | `regular-null` | 0.0560 | 0.0560 | 0.9525 | 0.0000 | **FAIL** |
| 1 | `regular-composite-interior-1` | 0.0365 | 0.0365 | 0.9585 | 0.0000 | **PASS** |
| 2 | `regular-composite-interior-2` | 0.0410 | 0.0410 | 0.9545 | 0.0000 | **PASS** |
| 3 | `regular-partial-null-ac` | 0.0375 | 0.0375 | 0.9585 | 0.0000 | **PASS** |
| 4 | `regular-partial-null-bd` | 0.0360 | 0.0370 | 0.9440 | 0.0000 | **FAIL** |
| 5 | `pilot-sd-SA1-m0.5` | 0.0370 | 0.0370 | 0.9585 | 0.0000 | **PASS** |
| 6 | `pilot-sd-SA1-p0.5` | 0.0385 | 0.0385 | 0.9580 | 0.0000 | **PASS** |
| 7 | `pilot-sd-SA1-p1.0` | 0.0365 | 0.0365 | 0.9670 | 0.0000 | **PASS** |
| 8 | `pilot-sd-SA1-p2.0` | 0.0500 | 0.0500 | 0.9570 | 0.0000 | **PASS** |
| 9 | `pilot-sd-SA2-m2.0` | 0.0405 | 0.0405 | 0.9535 | 0.0000 | **PASS** |
| 10 | `pilot-sd-SA2-m1.0` | 0.0350 | 0.0355 | 0.9560 | 0.0000 | **PASS** |
| 11 | `pilot-sd-SA2-m0.5` | 0.0360 | 0.0365 | 0.9600 | 0.0000 | **PASS** |
| 12 | `pilot-sd-SA2-p0.5` | 0.0385 | 0.0390 | 0.9570 | 0.0000 | **PASS** |
| 13 | `pilot-sd-SA2-p1.0` | 0.0370 | 0.0370 | 0.9525 | 0.0000 | **PASS** |
| 14 | `pilot-sd-SA2-p2.0` | 0.0300 | 0.0300 | 0.9575 | 0.0000 | **PASS** |
| 15 | `pilot-sd-SA3-m2.0` | 0.0370 | 0.0370 | 0.9590 | 0.0000 | **PASS** |
| 16 | `pilot-sd-SA3-m1.0` | 0.0325 | 0.0330 | 0.9610 | 0.0000 | **PASS** |
| 17 | `pilot-sd-SA3-m0.5` | 0.0335 | 0.0380 | 0.9520 | 0.0000 | **PASS** |
| 18 | `pilot-sd-SA3-p0.5` | 0.0320 | 0.0335 | 0.9510 | 0.0000 | **PASS** |
| 19 | `pilot-sd-SA3-p1.0` | 0.0285 | 0.0285 | 0.9670 | 0.0000 | **PASS** |
| 20 | `pilot-sd-SA3-p2.0` | 0.0355 | 0.0355 | 0.9605 | 0.0000 | **PASS** |
| 21 | `pilot-sd-SA4-m2.0` | 0.0430 | 0.0430 | 0.9585 | 0.0000 | **PASS** |
| 22 | `pilot-sd-SA4-m1.0` | 0.0465 | 0.0470 | 0.9520 | 0.0000 | **PASS** |
| 23 | `pilot-sd-SA4-m0.5` | 0.0375 | 0.0375 | 0.9645 | 0.0000 | **PASS** |
| 24 | `pilot-sd-SA4-p0.5` | 0.0370 | 0.0390 | 0.9580 | 0.0000 | **PASS** |
| 25 | `pilot-sd-SA4-p1.0` | 0.0405 | 0.0405 | 0.9520 | 0.0000 | **PASS** |
| 26 | `pilot-sd-SA4-p2.0` | 0.0435 | 0.0435 | 0.9575 | 0.0000 | **PASS** |
| 27 | `multi-scale-1_4` | 0.0000 | 0.0080 | 0.9590 | 0.0000 | **PASS** |
| 28 | `multi-scale-1_2` | 0.0000 | 0.0010 | 0.9625 | 0.0000 | **PASS** |
| 29 | `multi-scale-3_4` | 0.0000 | 0.0005 | 0.9630 | 0.0000 | **PASS** |
| 30 | `multi-scale-1` | 0.0000 | 0.0010 | 0.9525 | 0.0000 | **PASS** |
| 31 | `multi-sign-cross-1` | 0.0000 | 0.0000 | 0.9640 | 0.0000 | **PASS** |
| 32 | `multi-sign-cross-2` | 0.0000 | 0.0000 | 0.9610 | 0.0000 | **PASS** |
| 33 | `block3-SA1-0.08` | 0.0500 | 0.0500 | 0.9550 | 0.0000 | **PASS** |
| 34 | `block3-SA1-0.12` | 0.0485 | 0.0485 | 0.9580 | 0.0000 | **PASS** |
| 35 | `block3-SA1-0.15` | 0.0420 | 0.0420 | 0.9675 | 0.0000 | **PASS** |
| 36 | `block3-SA1-0.20` | 0.0570 | 0.0570 | 0.9530 | 0.0000 | **PASS** |
| 37 | `block3-SA1-0.25` | 0.0495 | 0.0495 | 0.9580 | 0.0000 | **PASS** |
| 38 | `block3-SA2--15.0` | 0.0410 | 0.0410 | 0.9605 | 0.0000 | **PASS** |
| 39 | `block3-SA2-8.0` | 0.0315 | 0.0315 | 0.9570 | 0.0000 | **PASS** |
| 40 | `block3-SA2-12.5` | 0.0385 | 0.0385 | 0.9500 | 0.0000 | **PASS** |
| 41 | `block3-SA2-18.0` | 0.0300 | 0.0300 | 0.9580 | 0.0000 | **PASS** |
| 42 | `block3-SA2-25.0` | 0.0475 | 0.0475 | 0.9465 | 0.0000 | **PASS** |
| 43 | `block3-SA3--20.0` | 0.0385 | 0.0385 | 0.9585 | 0.0000 | **PASS** |
| 44 | `block3-SA3--12.5` | 0.0350 | 0.0350 | 0.9590 | 0.0000 | **PASS** |
| 45 | `block3-SA3--8.5` | 0.0320 | 0.0320 | 0.9530 | 0.0000 | **PASS** |
| 46 | `block3-SA3--5.0` | 0.0345 | 0.0355 | 0.9590 | 0.0000 | **PASS** |
| 47 | `block3-SA3-10.0` | 0.0395 | 0.0395 | 0.9495 | 0.0000 | **PASS** |
| 48 | `block3-SA4--0.45` | 0.0540 | 0.0540 | 0.9465 | 0.0000 | **FAIL** |
| 49 | `block3-SA4--0.30` | 0.0505 | 0.0505 | 0.9620 | 0.0000 | **PASS** |
| 50 | `block3-SA4--0.20` | 0.0400 | 0.0400 | 0.9605 | 0.0000 | **PASS** |
| 51 | `block3-SA4--0.12` | 0.0360 | 0.0360 | 0.9625 | 0.0000 | **PASS** |
| 52 | `block3-SA4-0.20` | 0.0440 | 0.0440 | 0.9645 | 0.0000 | **PASS** |
| 53 | `skew-null` | 0.0435 | 0.0435 | 0.9600 | 0.0000 | **PASS** |
| 54 | `rare-null` | 0.0025 | 0.0025 | 0.9975 | 1.0000 | **PASS** |
| 55 | `ties-null` | 0.0420 | 0.0420 | 0.9665 | 0.0000 | **PASS** |
| 56 | `sparse-endpoint-null` | 0.0410 | 0.0410 | 0.9635 | 0.0045 | **PASS** |
| 57 | `bimodal-polarized-null` | 0.0395 | 0.0395 | 0.9660 | 0.0000 | **PASS** |
| 58 | `skew-SA1-0.15` | 0.0365 | 0.0365 | 0.9690 | 0.0000 | **PASS** |
| 59 | `skew-SA2-12.5` | 0.0330 | 0.0330 | 0.9595 | 0.0000 | **PASS** |
| 60 | `skew-SA3--8.5` | 0.0305 | 0.0305 | 0.9635 | 0.0000 | **PASS** |
| 61 | `rare-SA2-12.5` | 0.0000 | 0.0000 | 0.9965 | 1.0000 | **PASS** |
| 62 | `rare-SA3--8.5` | 0.0005 | 0.0005 | 0.9995 | 1.0000 | **PASS** |
| 63 | `ties-SA1-0.20` | 0.0390 | 0.0390 | 0.9695 | 0.0000 | **PASS** |
| 64 | `ties-SA4--0.30` | 0.0515 | 0.0515 | 0.9545 | 0.0000 | **FAIL** |
| 65 | `pinned-SA1-devlike` | 0.0500 | 0.0500 | 0.9540 | 0.0000 | **PASS** |
| 66 | `pinned-SA1-shrunken` | 0.0470 | 0.0470 | 0.9570 | 0.0000 | **PASS** |
| 67 | `pinned-SA4-devlike` | 0.0495 | 0.0495 | 0.9590 | 0.0000 | **FAIL** |
| 68 | `pinned-SA4-moderate-ceiling` | 0.0505 | 0.0505 | 0.9545 | 0.0000 | **FAIL** |
| 69 | `mcar-2pct-null` | 0.0115 | 0.0115 | 0.9895 | 0.0000 | **PASS** |
| 70 | `adverse-2pct-null` | 0.0070 | 0.0070 | 0.9935 | 0.0000 | **PASS** |
| 71 | `mcar-2pct-composite-interior` | 0.0055 | 0.0055 | 0.9920 | 0.0000 | **PASS** |
| 72 | `adverse-2pct-composite-interior` | 0.0085 | 0.0085 | 0.9880 | 0.0000 | **PASS** |
| 73 | `mcar-2pct-SA1-0.20` | 0.0085 | 0.0085 | 0.9915 | 0.0000 | **PASS** |
| 74 | `adverse-2pct-SA1-0.20` | 0.0065 | 0.0065 | 0.9935 | 0.0000 | **PASS** |
| 75 | `mcar-2pct-SA2-12.5` | 0.0095 | 0.0095 | 0.9915 | 0.0000 | **PASS** |
| 76 | `adverse-2pct-SA2-12.5` | 0.0075 | 0.0075 | 0.9905 | 0.0000 | **PASS** |
| 77 | `mcar-2pct-SA3--8.5` | 0.0055 | 0.0055 | 0.9920 | 0.0000 | **PASS** |
| 78 | `adverse-2pct-SA3--8.5` | 0.0065 | 0.0065 | 0.9895 | 0.0000 | **PASS** |
| 79 | `mcar-2pct-SA4--0.35` | 0.0075 | 0.0075 | 0.9920 | 0.0000 | **PASS** |
| 80 | `adverse-2pct-SA4--0.35` | 0.0120 | 0.0120 | 0.9880 | 0.0000 | **PASS** |
| 81 | `mcar-4pct-null` | 0.0020 | 0.0020 | 0.9985 | 0.0000 | **PASS** |
| 82 | `adverse-4pct-null` | 0.0025 | 0.0025 | 0.9980 | 0.0000 | **PASS** |
| 83 | `empirical-observed` | 0.0000 | 0.0000 | 0.9555 | 0.0000 | **PASS** |
| 84 | `empirical-calibrated-null` | 0.0525 | 0.0525 | 0.9485 | 0.0000 | **PASS** |
| 85 | `empirical-attenuated-75pct` | 0.0000 | 0.0000 | 0.9490 | 0.0000 | **PASS** |
| 86 | `empirical-attenuated-50pct` | 0.0000 | 0.0000 | 0.9585 | 0.0000 | **PASS** |
| 87 | `empirical-calibrated-null-mcar-2pct` | 0.0080 | 0.0080 | 0.9925 | 0.0000 | **PASS** |
