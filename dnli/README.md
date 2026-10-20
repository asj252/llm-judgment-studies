# Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates

An-Sheng Jhang, Dongguan University of Technology  
Contact: ansheng.jhang@gmail.com

This local release contains the frozen delta-NLI experiment and English
manuscript. It does not include raw execution logs, Chinese manuscript drafts,
review notes, model weights, or credentials.
The frozen PLAN and prompt documentation retain their original language.
An English reader's guide to the frozen plan is in `code/PLAN-guide-en.md`.

- `code/`: experiment/analysis code, portable unit tests, frozen rules, splits,
  development/formal result JSONL, session metadata, and archived analyses.
- `data/items_text.json`: optional selected source text (see reconstruction).
- `vs-pilot/`: shared Codex adapter dependency and its synthetic unit tests.
- `paper/en/`, `paper/references.bib`: English manuscript and bibliography.
- `paper/figures/`: frozen Chinese baseline figures and numerical regression data.
- `paper/figures/en/`: three English PDF/PNG figures and numerical figure data.
- `paper/typst/`: manuscript converter, Typst entry point, and integration tests.
- `paper/fixtures/` and `paper/references-map.md`: minimal numerical regression
  fixtures and citation aliases, replacing dependencies on Chinese draft notes.
- `release-check.json`: complete payload hashes, byte counts, path-redaction
  counts, path-only publication rewrites, and heuristic sensitive-term findings.
  The check file itself is excluded from its own hash inventory.

## Version 2

The v2 manuscript and figures add four agy configurations on the original
block-A materials. See [agy-extension](agy-extension/) for frozen code,
results, metadata and analysis instructions. Its explicitly allowlisted result
records, session metadata and frozen brief retain their original bytes and paths
for hash verification. Raw execution files are excluded; strict analysis needs
those files at their recorded paths. The public offline entry is:

```sh
python -X utf8 -B agy-extension/reproduce_public.py --out reproduced-agy.json
```

It checks registered raw SHA-256 hashes, retains all other frozen checks, and
requires exact equality of the full analysis JSON. It cannot verify raw files
themselves. The authors retain the originals and can provide them for
verification on request; see agy-extension/README.md for the boundary and
release-check.json for the byte-preserving exceptions.

## Reproduce the frozen analysis

Use Python 3.10 or later. Analysis needs only the standard library. From the
release root (choose a new output filename):

```sh
python -X utf8 -B reproduce.py --out analysis_reproduced.json
```

This creates a temporary legacy layout, restores `raw/items_text.json` from
`data/items_text.json`, and runs `analyse.py run formal --final` with the frozen
5,000 bootstrap replicates. It requires exact equality of the entire decoded
JSON with `code/analysis_formal.json`. No model calls are made. The legacy
code and material hashes are preserved, rather than weakening binding checks.
Original absolute runtime paths in metadata are replaced by `<LOCAL_PATH>`;
original fingerprint IDs remain historical identifiers, not hashes of redacted
metadata. Do not attempt to resume historical sessions in this portable copy.

If selected text was omitted, obtain only delta-SNLI dev/test from the URLs in
`code/download.json` and verify their recorded SHA-256 values. Put them in
`<scratch>/data/defeasible-snli/{dev,test}.jsonl`. Copy `code/*.json` to scratch
(including read20_ids.json, human20_images.json, sensitive_decisions.json,
speech_updates.json and download.json). Then run:

```sh
python -X utf8 -B code/split.py <scratch> --out <new-rebuilt-directory>
python -X utf8 -B reproduce.py --items-text <new-rebuilt-directory>/raw/items_text.json --out analysis_reproduced.json
```

`split.py` verifies upstream hashes and rebuilds the selection and text.
Check the rebuilt split against `code/split.json`; the analysis also verifies
all text/material hashes. Avoid overwriting the release's frozen split.

## Recreate the three English figures

Install `requirements.txt` (record the versions used in your environment).
The source project did not provide a dependency lockfile; these requirements
are an import inventory, not a claim of exact environment reproduction.
Choose a new figure output directory:

```sh
python -X utf8 -B paper/make_figures.py --lang en --output <new-figure-directory>
```

This recomputes all three descriptive figures from the released formal result
records; confirmatory analysis stays in `code/analysis_formal.json`.

## Tests and manuscript

```sh
cd code
python -X utf8 -B -m unittest discover -p "test_*.py"
cd ../vs-pilot
python -X utf8 -B -m unittest test_subject.py
cd ../paper
python -X utf8 -B -m unittest test_make_figures.py
cd typst
python -X utf8 -B -m unittest test_build.py
```

Raw-probe tests and upstream-data split integration tests skip when their
private/external fixtures are absent. For the original study, tests of old raw
archives and shell launchers are omitted; the release manifest explains why.
The agy extension includes its launcher and queue tests (see
`agy-extension/README.md`). No test calls models.
Typst integration requires `typst` (original build: 0.14.2) and Poppler
`pdftotext` on PATH; it regenerates abstract/body Typst, PDF and local logs.
To build without testing, run `python -X utf8 -B build.py` from paper/typst.
The release includes the v2 manuscript PDF (`paper/typst/dnli-arxiv.pdf`);
local build and test logs are not included.

## Model configuration and versions

- Qwen/Qwen3-8B, revision b968826d9c46dd6066d109eabc6255188de91218,
  Q8_0 GGUF, thinking off, context 16,384, maximum output 8,192.
- allenai/OLMo-2-1124-7B-Instruct, revision
  470b1fba1ae01581f270116362ee4aa1b97f4c84, Q8_0 GGUF, context 4,096;
  maximum output equals remaining context.
- Local backend: llama.cpp b11560; temperature 0.6, top-k 20, top-p 0.95,
  min-p 0. Other sampler settings are explicit in `code/local_subject.py`.
- Codex: gpt-6.1-sol, medium reasoning, codex-cli 0.162.0-alpha.17.2.
  Exact settings/session versions appear in `code/run_meta_*.json`.

Local machine paths in adapters are placeholders after redaction. Configure
model/cache/backend locations before conducting a *new* experiment, which
requires new fingerprints and must not overwrite the frozen evidence.

## Sources, licensing and citation

Selected text derives from SNLI through delta-SNLI in delta-NLI (Rudinger et
al., 2020), upstream revision c675ffc1b0eec5fa56287f08490da8ed43c1ecc5.
See `code/download.json` for retrieval URLs/hashes and `DATA_LICENSE.md` for
SNLI/delta-NLI attribution and CC BY-SA 4.0 terms for derived items and result
files containing text. Software is MIT, copyright An-Sheng Jhang 2026.
Responses were generated by the three original configurations identified
above and, in `agy-extension/`, by four further configurations (gpt-oss-120b,
claude-sonnet-5.5, and gemini-3.8-flash at two reasoning efforts) run through
the agy command-line harness.
See `CITATION.cff`; the manuscript arXiv identifier is **TBD**.

Sensitive scans are heuristic and flag many benign token/API documentation
mentions. Review the reported files and line numbers before publication;
this local preparation does not publish or push anything.
