# Third-party data: acquire and reconstruct locally

This package does not redistribute SynAnchors questions or ProbCOPA/COPA premises, options or human ratings. The following versions and hashes were recorded on 2026-10-15 in the research download log and `raw_data/SHA256SUMS.txt`. No network lookup was performed when preparing this package. Revision IDs below are the abbreviated IDs recorded at acquisition; validate every download against the complete hashes.

## Sources and placement

SynAnchors 0.1, semantic subset: Hugging Face `TimTargaryen/SynAnchors`, revision `e6df428`, data card declaring Apache-2.0. Save [Qsemantic.json](https://huggingface.co/datasets/TimTargaryen/SynAnchors/resolve/e6df428/Qsemantic.json) to `psych3/raw_data/synanchors/Qsemantic.json`. The source [README](https://huggingface.co/datasets/TimTargaryen/SynAnchors/resolve/e6df428/README.md) is provenance only.

ProbCOPA: GitHub `McGill-NLP/probabilistic-reasoning`, revision `b983b12`. The repository LICENSE is MIT; its README/LICENSE did not separately specify a data license in the recorded review. Obtain these files and save them under `psych3/raw_data/probcopa/` using the final filename:

- [datasets/probcopa_items.jsonl](https://raw.githubusercontent.com/McGill-NLP/probabilistic-reasoning/b983b12/datasets/probcopa_items.jsonl)
- [datasets/probcopa_CANARY.jsonl](https://raw.githubusercontent.com/McGill-NLP/probabilistic-reasoning/b983b12/datasets/probcopa_CANARY.jsonl)
- [results/probcopa_human_results_annotated_CANARY.jsonl](https://raw.githubusercontent.com/McGill-NLP/probabilistic-reasoning/b983b12/results/probcopa_human_results_annotated_CANARY.jsonl)

The upstream [remove_canary_strings.py](https://raw.githubusercontent.com/McGill-NLP/probabilistic-reasoning/b983b12/scripts/remove_canary_strings.py), [LICENSE](https://raw.githubusercontent.com/McGill-NLP/probabilistic-reasoning/b983b12/LICENSE), and [README](https://raw.githubusercontent.com/McGill-NLP/probabilistic-reasoning/b983b12/README.md) are provenance references. Do not execute the downloaded cleaning script: `gen_b.py` implements the recorded rule locally (remove rows with `type == "canary"`, preserve retained line bytes).

## SHA-256 of acquired bytes

| File (relative to raw_data/) | SHA-256 |
|---|---|
| synanchors/Qsemantic.json | `356095ff77a6e32913d00dae758e0be3a170fdc921857ff142c70fa86ca48070` |
| synanchors/README.md | `78fd1cceeaff8958f3edb2b423c02c5643668b9b49ec01eed5ce7944a3f35a48` |
| probcopa/probcopa_items.jsonl | `604d75e51af67925e48ab032a7e2f4a82454225fddec328df2a4caa340e57b40` |
| probcopa/probcopa_CANARY.jsonl | `fadc90cbaf2a7b228e6830c19e7b9b1bf7e4d78df1e1b113fbcb215dab95be1d` |
| probcopa/probcopa_human_results_annotated_CANARY.jsonl | `882f156f2e9659ecc5def78311376dc79ae00d28cba2e08540b026702f34fb8a` |
| probcopa/remove_canary_strings.py | `e6e0dd1ea865b426623b98ceec5965c1158caddc1c399f93023aa5965a12f497` |
| probcopa/LICENSE | `3f83f463f68f583ce0b89d78148bad6f7b8d9e898b8512cc0890fef3ab2ed9ae` |
| probcopa/README.md | `12c70e1570d2f3d87002498a9977826b8160ce04cc4488430c3f5ce2d4471e1e` |

## Reconstruction

Use a separate local copy, preserving the sibling dependency directories. In its `psych3/` directory, after verifying the downloaded bytes:

```sh
python -X utf8 -B gen_a.py
python -X utf8 -B gen_b.py
python -X utf8 -B manifest.py
python -X utf8 -B verify_prereg.py
```

`gen_a.py` uses the published eligibility decisions, 24 authored items and fixed seeds to reconstruct A. `gen_b.py` cleans both CANARY sources, pairs alternative IDs, builds B, and computes local human summaries. `manifest.py` combines A–E into the full local manifest and ID manifest. Do not use `gen_a.py --preview-all`: that is a trial mode and does not reconstruct the frozen release. Original generators use text-mode JSON output; on platforms with different newline conventions, byte hashes may differ. The recorded run was on Windows; compare bytes rather than treating a semantic JSON match as hash verification.

The verifier lists the five excluded artifacts bound by the freeze, with their expected hashes: `raw_items_a.json`, `raw_items_b.json`, `b_manifest.json`, `raw_manifest.json`, and `raw_probcopa_human_clean.jsonl`. Other raw products and human summaries stay local. None should be added to a public preregistration upload.
