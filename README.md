# LLM Judgment Studies

An-Sheng Jhang, Dongguan University of Technology · ansheng.jhang@gmail.com

One repository for a series of studies on how large language models report probabilities and quantities, and how the way a question is asked changes those reports. Each study lives in its own folder with its own README, license files, frozen plan, code, results and paper sources.

| Folder | Study | Status |
|---|---|---|
| [`dnli/`](dnli/) | *Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates* (δ-NLI); [paper: arXiv:2610.27745](https://arxiv.org/abs/2610.27745); [public dataset (Hugging Face)](https://huggingface.co/datasets/anshengjhang/dnli-hearsay-or-fact) | Formal v3 release, manuscript and sealed aggregate bundle: [v3-release](dnli/v3-release/). |
| [`psych3/`](psych3/) | *Multi-Estimate Elicitation Does Not Uniformly Debias Language Model Judgments*: anchoring, hindsight, base-rate, conjunction and status-quo/default paradigms | [v4 paper](psych3/paper-v4/), [P1](psych3/p1-factorial/), [P2](psych3/p2-supplemental/) and [Stage 2 summaries](psych3/stage2-summaries/). |
| [`imperfective/`](imperfective/) | Imperfective paradox, discrete-label vs. probability elicitation, and multi-estimate stacking on English `ImperfectiveNLI` (Experiment 1) | [Formal results](imperfective/formal-results/), [P16.7](imperfective/p167-api/) and [paper arXiv:2611.22188v1](imperfective/paper/). |
| [`imperfective-exp2-zh/`](imperfective-exp2-zh/) | Imperfective paradox in Mandarin Chinese: bare perfective `-le` (`V了`) vs. resultative/completive/satiation complements across telic and atelic event clusters (Experiment 2) | Frozen preregistration preserved; [formal results](imperfective-exp2-zh/formal-results/). |
| [`imperfective-exp3-en/`](imperfective-exp3-en/) | Imperfective paradox in English atelic activities (`B/D`): controlled single-slot aspectual boundary modifiers contrasting minimal occurrence vs. bounded plan/task/period completion (Experiment 3) | Frozen preregistration preserved; [formal results](imperfective-exp3-en/formal-results/). |
| [`imperfective-exp4-moore/`](imperfective-exp4-moore/) | Moorean belief-assertion paradox vs. multi-criteria Verbalized Sampling across 4 professional domains in English (Experiment 4) | Frozen preregistration preserved; [formal results](imperfective-exp4-moore/formal-results/). |
| Stereotype Readouts | Surface ties and stereotype updating | [code](stereotype-readouts/) | [paper: SSRN 7736298](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7736298) | [public dataset (Hugging Face)](https://huggingface.co/datasets/anshengjhang/stereotype-readouts-formal) (pending sign-off and upload) |

`dnli-agy/` and `vs-pilot/` at the top level hold unmodified copies of shared code that the psych3 freeze binds by hash; `dnli/code/` keeps the path-redacted copies used by the δ-NLI release.

Raw execution logs, model weights and credentials are not part of this repository. See each study's README for what is included and how to reproduce its analysis.

Root `mcv_standard.py` is the unchanged shared frozen multi-candidate verbalization module.
