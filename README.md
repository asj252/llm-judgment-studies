# LLM Judgment Studies

An-Sheng Jhang, Dongguan University of Technology · ansheng.jhang@gmail.com

One repository for a series of studies on how large language models report probabilities and quantities, and how the way a question is asked changes those reports. Each study lives in its own folder with its own README, license files, frozen plan, code, results and paper sources.

| Folder | Study | Status |
|---|---|---|
| [`dnli/`](dnli/) | *Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates* (δ-NLI); [arXiv:2610.27745](https://arxiv.org/abs/2610.27745) | Frozen experiment, the extension with four further configurations (`dnli/agy-extension/`), and the English manuscript v2 (seven configurations). |
| [`psych3/`](psych3/) | Elicitation format in anchoring, hindsight, base-rate, conjunction and status-quo/default paradigms | Preregistration: frozen plan, analysis freeze, materials and code, published before the formal runs ([record](psych3/PREREGISTRATION_RECORD.md)). No results yet. |

`dnli-agy/` and `vs-pilot/` at the top level hold unmodified copies of shared code that the psych3 freeze binds by hash; `dnli/code/` keeps the path-redacted copies used by the δ-NLI release.

Raw execution logs, model weights and credentials are not part of this repository. See each study's README for what is included and how to reproduce its analysis.
