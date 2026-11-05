# Six-configuration machine-readable Tables G2 and G3

This supplement accompanies *Multi-Estimate Elicitation Does Not Uniformly Debias Language Model Judgments* (English v2), by An-Sheng Jhang, Dongguan University of Technology. It covers six completed configurations: codex, Sonnet 5.5, Qwen3, gpt-oss-120b, Flash low and Flash high. The formal-r0 candidate-spread analyses are nonpreregistered and exploratory.

- `g2-spread-by-condition.csv`: 198 data rows, 9 columns; 33 condition summaries per configuration. Fields: Configuration, Experiment, Condition, Measure, Valid cells, Q1, Median, Q3 and Zero-spread fraction.
- `g3-paired-cell-counts.csv`: 1,482 data rows, 5 columns; 247 item summaries per configuration. Fields: Configuration, Experiment, Item ID, Cluster ID and Available paired cells.

Both CSVs are exact byte copies from the reviewed English v2 package. No statistics, rows or displayed values were changed for release. `manifest.json` records their SHA-256 values, dimensions and the source Appendix G hash.

## Conditions and interpretation

A: informative/irrelevant/none denote anchor framing; high/low denote levels. B: F is prospective; HI is outcome disclosure followed by an instruction to set the disclosed outcome aside and reconstruct a prediction from the situation alone; HP retains retrospective reconstruction of the pre-outcome prediction while omitting only the explicit ignore-outcome instruction; PO asks the prospective question after outcome disclosure. Numbers denote queried outcomes. C: frequency/probability denote presentation, with numeric base-rate labels. D: J/S denote joint/separate elicitation; a, b, conj and disj denote components, conjunction and disjunction. E: T/O denote assignment to target/other; recommend is informed advice and neutral is the neutral condition. A spread uses natural-log units; B-E use percentage points. Candidates and cells are not independent repetitions.

## Available paired-cell counts

No item has 0 paired cells. Items affected by missing cells have reduced paired-cell counts rather than 0. The table below counts items at each available-cell count directly from the byte-preserved CSV. Each configuration has 247 items.

| Configuration | 2 cells | 4 cells | 5 cells | 6 cells | 7 cells | 8 cells | Total items |
|---|---:|---:|---:|---:|---:|---:|---:|
| codex | 1 | 0 | 84 | 40 | 32 | 90 | 247 |
| Sonnet 5.5 | 0 | 0 | 85 | 40 | 32 | 90 | 247 |
| Qwen3 | 0 | 0 | 88 | 41 | 28 | 90 | 247 |
| gpt-oss-120b | 0 | 2 | 84 | 40 | 32 | 89 | 247 |
| Flash low | 0 | 0 | 85 | 40 | 33 | 89 | 247 |
| Flash high | 0 | 0 | 85 | 40 | 33 | 89 | 247 |

Usual complete counts are A: 5, B: 8, C: 6, D: 5 and E: 7 cells per item. The following 11 item summaries have fewer cells than their experiment-specific complete count:

| Configuration | Experiment | Item ID | Available paired cells | Complete count |
|---|---|---|---:|---:|
| codex | A | S06 | 2 | 5 |
| Qwen3 | C | s04_A | 5 | 6 |
| Qwen3 | E | E04 | 6 | 7 |
| Qwen3 | E | E09 | 5 | 7 |
| Qwen3 | E | E21 | 5 | 7 |
| Qwen3 | E | E25 | 6 | 7 |
| gpt-oss-120b | A | A13 | 4 | 5 |
| gpt-oss-120b | A | S15 | 4 | 5 |
| gpt-oss-120b | B | 710 | 5 | 8 |
| Flash low | B | 710 | 7 | 8 |
| Flash high | B | 710 | 7 | 8 |

## Scope

No question text, full model responses or raw execution records are included. The reviewed manuscript and aggregate summaries are available alongside this supplement in [paper-v2/](../paper-v2/). Local preparation does not establish a remote GitHub publication.
