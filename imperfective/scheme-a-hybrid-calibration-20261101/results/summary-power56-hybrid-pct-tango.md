# Scheme A Step 5b Simulation Executive Summary (`power_grid` / `hybrid_pct_tango`)

- **Bank / Seed**: `power_grid` (`2026110111`)
- **Method**: `hybrid_pct_tango`
- **Replicates per Cell**: 2000 (`B = 5000`)
- **Total Cells Evaluated**: 56
- **Cells Passing Main 98.75% Criteria**: 53 / 56
- **Cells Passing Historical 99.5% Criteria**: 41 / 56
- **Confirmation Bank Hard-Disabled**: `True`
- **Confirmation Status**: `not_applicable_power_grid`


## Power & Boundary Degeneracy Sequences

| Sequence | Slot | Smallest Tested Sufficient Effect | Largest Sufficient Effect | Monotone Tail? | High-Effect Collapse Cells |
|---|---|---|---|---|---|
| `SA1-baseline` | SA1 | `1/10` | `7/20` | `True` | None |
| `SA1-pinned` | SA1 | `1/8` | `7/20` | `True` | None |
| `SA2-continuous` | SA2 | `25` | `30` | `True` | None |
| `SA3-continuous` | SA3 | `-25` | `-30` | `True` | None |
| `SA4-baseline` | SA4 | `-1/4` | `-7/10` | `True` | None |
| `SA4-pinned` | SA4 | `-3/20` | `-19/20` | `True` | None |

## Failed Cells Under Main 98.75% Criteria

| Index | Cell Name | Failed Checks | Max Degen Rate | Simult Cov 98.75% |
|---|---|---|---|---|
| 25 | `power-SA3--8.5` | `screen0125` | 0.0000 | 0.9535 |
| 34 | `power-SA4-base--0.15` | `screen0125` | 0.0000 | 0.9570 |
| 35 | `power-SA4-base--0.20` | `screen0125` | 0.0000 | 0.9510 |

## Complete Cell Screening Table (All 56 Cells)

| Index | Cell Name | FWER | Fam Dir Err | Simult Cov 98.75% | Max Degen | 98.75% Passed? |
|---|---|---|---|---|---|---|
| 0 | `power-SA1-base-0.05` | 0.0375 | 0.0375 | 0.9600 | 0.0000 | **PASS** |
| 1 | `power-SA1-base-0.10` | 0.0500 | 0.0500 | 0.9605 | 0.0000 | **PASS** |
| 2 | `power-SA1-base-0.15` | 0.0445 | 0.0445 | 0.9640 | 0.0000 | **PASS** |
| 3 | `power-SA1-base-0.20` | 0.0455 | 0.0455 | 0.9635 | 0.0000 | **PASS** |
| 4 | `power-SA1-base-0.25` | 0.0465 | 0.0465 | 0.9590 | 0.0000 | **PASS** |
| 5 | `power-SA1-base-0.30` | 0.0445 | 0.0445 | 0.9615 | 0.0000 | **PASS** |
| 6 | `power-SA1-base-0.35` | 0.0450 | 0.0450 | 0.9545 | 0.0000 | **PASS** |
| 7 | `power-SA1-pinned-0.05` | 0.0295 | 0.0295 | 0.9745 | 0.0000 | **PASS** |
| 8 | `power-SA1-pinned-0.10` | 0.0520 | 0.0520 | 0.9585 | 0.0000 | **PASS** |
| 9 | `power-SA1-pinned-0.125` | 0.0450 | 0.0450 | 0.9605 | 0.0000 | **PASS** |
| 10 | `power-SA1-pinned-0.15` | 0.0430 | 0.0430 | 0.9685 | 0.0000 | **PASS** |
| 11 | `power-SA1-pinned-0.20` | 0.0500 | 0.0500 | 0.9600 | 0.0000 | **PASS** |
| 12 | `power-SA1-pinned-0.25` | 0.0500 | 0.0500 | 0.9570 | 0.0000 | **PASS** |
| 13 | `power-SA1-pinned-0.30` | 0.0480 | 0.0480 | 0.9615 | 0.0000 | **PASS** |
| 14 | `power-SA1-pinned-0.35` | 0.0475 | 0.0475 | 0.9555 | 0.0000 | **PASS** |
| 15 | `power-SA2-5.0` | 0.0350 | 0.0350 | 0.9535 | 0.0000 | **PASS** |
| 16 | `power-SA2-8.0` | 0.0295 | 0.0295 | 0.9625 | 0.0000 | **PASS** |
| 17 | `power-SA2-10.0` | 0.0385 | 0.0385 | 0.9590 | 0.0000 | **PASS** |
| 18 | `power-SA2-12.5` | 0.0285 | 0.0285 | 0.9530 | 0.0000 | **PASS** |
| 19 | `power-SA2-15.0` | 0.0405 | 0.0405 | 0.9590 | 0.0000 | **PASS** |
| 20 | `power-SA2-18.0` | 0.0375 | 0.0375 | 0.9515 | 0.0000 | **PASS** |
| 21 | `power-SA2-20.0` | 0.0335 | 0.0335 | 0.9640 | 0.0000 | **PASS** |
| 22 | `power-SA2-25.0` | 0.0295 | 0.0295 | 0.9635 | 0.0000 | **PASS** |
| 23 | `power-SA2-30.0` | 0.0445 | 0.0445 | 0.9575 | 0.0000 | **PASS** |
| 24 | `power-SA3--5.0` | 0.0350 | 0.0355 | 0.9565 | 0.0000 | **PASS** |
| 25 | `power-SA3--8.5` | 0.0410 | 0.0415 | 0.9535 | 0.0000 | **FAIL** |
| 26 | `power-SA3--10.0` | 0.0365 | 0.0365 | 0.9620 | 0.0000 | **PASS** |
| 27 | `power-SA3--12.5` | 0.0300 | 0.0300 | 0.9600 | 0.0000 | **PASS** |
| 28 | `power-SA3--15.0` | 0.0380 | 0.0380 | 0.9570 | 0.0000 | **PASS** |
| 29 | `power-SA3--18.0` | 0.0330 | 0.0330 | 0.9615 | 0.0000 | **PASS** |
| 30 | `power-SA3--20.0` | 0.0375 | 0.0375 | 0.9560 | 0.0000 | **PASS** |
| 31 | `power-SA3--25.0` | 0.0370 | 0.0370 | 0.9615 | 0.0000 | **PASS** |
| 32 | `power-SA3--30.0` | 0.0450 | 0.0450 | 0.9640 | 0.0000 | **PASS** |
| 33 | `power-SA4-base--0.10` | 0.0355 | 0.0355 | 0.9615 | 0.0000 | **PASS** |
| 34 | `power-SA4-base--0.15` | 0.0445 | 0.0445 | 0.9570 | 0.0000 | **FAIL** |
| 35 | `power-SA4-base--0.20` | 0.0535 | 0.0535 | 0.9510 | 0.0000 | **FAIL** |
| 36 | `power-SA4-base--0.25` | 0.0470 | 0.0470 | 0.9530 | 0.0000 | **PASS** |
| 37 | `power-SA4-base--0.30` | 0.0485 | 0.0485 | 0.9540 | 0.0000 | **PASS** |
| 38 | `power-SA4-base--0.40` | 0.0445 | 0.0445 | 0.9575 | 0.0000 | **PASS** |
| 39 | `power-SA4-base--0.50` | 0.0425 | 0.0425 | 0.9580 | 0.0000 | **PASS** |
| 40 | `power-SA4-base--0.60` | 0.0415 | 0.0415 | 0.9645 | 0.0000 | **PASS** |
| 41 | `power-SA4-base--0.70` | 0.0410 | 0.0410 | 0.9620 | 0.0000 | **PASS** |
| 42 | `power-SA4-pinned--0.15` | 0.0540 | 0.0540 | 0.9520 | 0.0000 | **PASS** |
| 43 | `power-SA4-pinned--0.25` | 0.0520 | 0.0520 | 0.9510 | 0.0000 | **PASS** |
| 44 | `power-SA4-pinned--0.35` | 0.0515 | 0.0515 | 0.9570 | 0.0000 | **PASS** |
| 45 | `power-SA4-pinned--0.50` | 0.0505 | 0.0505 | 0.9515 | 0.0000 | **PASS** |
| 46 | `power-SA4-pinned--0.65` | 0.0420 | 0.0420 | 0.9635 | 0.0000 | **PASS** |
| 47 | `power-SA4-pinned--0.75` | 0.0545 | 0.0545 | 0.9530 | 0.0000 | **PASS** |
| 48 | `power-SA4-pinned--0.80` | 0.0400 | 0.0400 | 0.9605 | 0.0000 | **PASS** |
| 49 | `power-SA4-pinned--0.85` | 0.0420 | 0.0420 | 0.9665 | 0.0000 | **PASS** |
| 50 | `power-SA4-pinned--0.90` | 0.0545 | 0.0545 | 0.9595 | 0.0000 | **PASS** |
| 51 | `power-SA4-pinned--0.95` | 0.0430 | 0.0430 | 0.9695 | 0.0000 | **PASS** |
| 52 | `power-empirical-convex-1_4` | 0.0000 | 0.0000 | 0.9550 | 0.0000 | **PASS** |
| 53 | `power-empirical-convex-1_2` | 0.0000 | 0.0000 | 0.9575 | 0.0000 | **PASS** |
| 54 | `power-empirical-convex-3_4` | 0.0000 | 0.0000 | 0.9545 | 0.0000 | **PASS** |
| 55 | `power-empirical-convex-1` | 0.0000 | 0.0000 | 0.9565 | 0.0000 | **PASS** |
