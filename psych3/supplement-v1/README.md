# Machine-readable Tables G2 and G3

This supplement provides the machine-readable versions of Tables G2 and G3 for One Shot or Five Weights? Probing Judgment Biases in Language Models via Multi-Estimate Elicitation.

These are exports of the reviewed English manuscript Appendix G, covering formal round r0 in three completed configurations (codex, Sonnet, and Qwen3). The analyses are nonpreregistered descriptive analyses. No statistics were recomputed.

- `g2-spread-by-condition.csv`: 99 data rows, 9 columns. Existing condition-level descriptive distributions, including Q1, Median, Q3 and zero-spread fraction. Displayed decimal strings are preserved.
- `g3-paired-cell-counts.csv`: 741 data rows, 5 columns. Configuration, experiment, item ID, cluster ID and available paired-cell count only; no question text.

## G2 fields and condition labels

Condition labels follow analysis outputs. In A, informative/irrelevant/none mean informative anchors, irrelevant anchors, and no anchor; high/low identify anchor levels. For B, F denotes prospective estimates; HI denotes outcome disclosure followed by an instruction to set the disclosed outcome aside and reconstruct a prediction from the situation alone; HP omits that instruction; PO asks the same prospective question after outcome disclosure. Numbers identify the queried outcome. In C, frequency/probability identify natural-frequency/probability presentation, and numbers identify base rates. In D, J/S mean joint/separate elicitation, and a, b, conj, disj identify two components, conjunction, and disjunction. In E, T/O identify assignment of the manipulation to the target/other option, recommend denotes advice, and neutral identifies the neutral condition.

Configuration/Experiment identify the configuration and experiment; Condition preserves the existing JSON-array-like label. Measure preserves spread/conj/b. Valid cells is the existing available-cell count; Q1/Median/Q3 are the existing descriptive quartiles; Zero-spread fraction is the existing zero fraction. A uses natural-log units, while B-E retain percentage-point units.

## G3 fields and interpretation

The table lists only item IDs, cluster IDs, and available paired-cell counts from existing item summaries. Candidates and cells are not independent repetitions. Usually there are 5 cells per item in A, 8 in B, 6 in C, 5 in D, and 7 in E. C's two items within one scenario share a cluster. One codex A item has only 2 cells; one Qwen3 C item has 5; Qwen3 E items affected by missingness average available cells. A's error grouping is separately reported in Table 9, using 1 unanchored or up to 4 anchored cells, rather than this table's all-condition denominators.

## Provenance and scope

The CSVs preserve each displayed field in the approved tables; only Markdown delimiters and CSV quoting differ. `manifest.json` records the source appendix hash, row/column counts and CSV hashes. These two files do not release complete experimental results, Addendum 2, raw responses, or third-party item texts.
