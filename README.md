# LLM Judgment Studies

An-Sheng Jhang, Dongguan University of Technology · ansheng.jhang@gmail.com

One repository for a series of studies on how large language models report probabilities and quantities, and how the way a question is asked changes those reports. Each study lives in its own folder with its own README, license files, frozen plan, code, results and paper sources.

| Folder | Study | Status |
|---|---|---|
| [`dnli/`](dnli/) | *Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates* (δ-NLI); [paper: arXiv:2610.27745](https://arxiv.org/abs/2610.27745); [public dataset (Hugging Face)](https://huggingface.co/datasets/anshengjhang/dnli-hearsay-or-fact) | Frozen experiment, the extension with four further configurations (`dnli/agy-extension/`), and the English manuscript v2 (seven configurations). |
| [`psych3/`](psych3/) | Elicitation format in anchoring, hindsight, base-rate, conjunction and status-quo/default paradigms | Preregistration: frozen plan, analysis freeze, materials and code, published before the formal runs ([record](psych3/PREREGISTRATION_RECORD.md)). No results yet. |
| [`imperfective/`](imperfective/) | Imperfective paradox, discrete-label vs. probability elicitation, and multi-estimate stacking on English `ImperfectiveNLI` (Experiment 1) | Preregistration: frozen Experiment 1 specification (`PLAN-E1.md`), execution manifest, split/token materials, runner, and sealed Scheme A statistical engine, published before the formal runs ([record](imperfective/PREREGISTRATION_RECORD.md)). No results yet. |
| [`imperfective-exp2-zh/`](imperfective-exp2-zh/) | Imperfective paradox in Mandarin Chinese: bare perfective `-le` (`V了`) vs. resultative/completive/satiation complements across telic and atelic event clusters (Experiment 2) | Preregistration: frozen Experiment 2 specification (`PLAN-E2.frozen.md`), S5 `freeze.json`, S4 16-cell calibration (`hybrid_bessel_t_tango_e2`), all 100 authored Chinese clusters (`600` items), and runner (`f81940ea`), published before the formal runs ([record](imperfective-exp2-zh/PREREGISTRATION_RECORD.md)). No results yet. |

`dnli-agy/` and `vs-pilot/` at the top level hold unmodified copies of shared code that the psych3 freeze binds by hash; `dnli/code/` keeps the path-redacted copies used by the δ-NLI release.

Raw execution logs, model weights and credentials are not part of this repository. See each study's README for what is included and how to reproduce its analysis.
