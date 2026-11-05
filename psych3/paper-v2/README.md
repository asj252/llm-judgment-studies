# Six-configuration English v2 manuscript release

**Multi-Estimate Elicitation Does Not Uniformly Debias Language Model Judgments**

An-Sheng Jhang, Dongguan University of Technology. This release tree contains the Round-6-reviewed six-configuration English v2 report.

- `manuscript.md`, `appendices.md`, `references.bib`, `title.txt`, `abstract.txt`: exact copies of the audited v2 text.
- `typeset/figures/`: the three figures in PNG/PDF form and `figure_data.json`. The original relative image paths are preserved so the manuscript image links resolve in this tree.
- `analysis-summary/`: seven aggregate JSONs covering the six-configuration summary, descriptive endpoints, admitted-unit accounting, flash-high two-batch provenance/diagnostics, v1 equivalence receipt and table audit. These are aggregate results, not a raw-response or strict-reanalysis bundle.
- `manifest.json`: all payload byte sizes, SHA-256 values and exact-copy provenance; its own hash is excluded.

The manuscript and appendices are preserved byte-for-byte from the audited build. The appendices were compiled before this public-repository release and do not claim that supplement-v2 had been publicly uploaded. The corresponding machine-readable Tables G2 and G3 are now available alongside this manuscript at [supplement-v2/](../supplement-v2/) in this release tree. No commit, push, arXiv upload or remote publication is performed by this preparation step.

## Provenance and disclosure

`analysis-summary/reproduce_v1_check.json` is an exact byte copy of the identically named receipt in the audited analysis bundle. It reports zero JSON-value and exact-byte differences for all three v1 configurations. No new result was computed for this release.

No third-party SynAnchors or ProbCOPA item texts, full model-response records, raw JSONL execution logs or local machine paths are included. Box 1 in the byte-preserved manuscript contains six reviewed numeric response-format lines: one direct probability line and five weighted-estimate lines for the researcher-authored p01 example. These approved numeric excerpts are retained. Verification checks their count explicitly and separately confirms zero raw JSONL execution logs and zero source-item-text matches.

The [supplement README](../supplement-v2/README.md) reports the exact paired-cell count distribution from the audited G3 CSV: no item has zero paired cells; missing cells reduce the available counts. Non-rejection is not evidence of equivalence. Flash-high retains two disjoint execution-window identities; its exploratory batch contrasts have the non-causal interpretation stated in the audited report.
