# Third-party data: acquire locally without redistribution

This preregistration package does **not** redistribute `ImperfectiveNLI` item text (`premise` or `hypothesis`), upstream inference code, or development-set model free-text responses. The source commit and SHA-256 digests below were recorded on 2026-10-26 during Stage S0 provenance verification (`exp1-en/provenance.py`). Validate every acquired file against the complete SHA-256 hashes before use.

## Upstream source and license note

- **Upstream repository**: GitHub `boleima/ImperfectiveParadox`, fixed commit `938ef893c3368f3a597e6add2cfebdad02fddebf`
- **Associated paper**: arXiv:2601.09373v3 (*Artifact Usage* section, verified 2026-10-26), declaring release of the `ImperfectiveNLI` dataset under Creative Commons Attribution-NonCommercial 4.0 International (`CC BY-NC 4.0`) for research purposes. The upstream GitHub repository did not carry a standalone `LICENSE` file at acquisition (`license: null`).

Obtain the two pinned files from commit `938ef893c3368f3a597e6add2cfebdad02fddebf` and place them in `imperfective/exp1-en/data/` using the exact filenames below:

- `imperfectiveNLI.json`: download [`imperfectiveNLI.json`](https://raw.githubusercontent.com/boleima/ImperfectiveParadox/938ef893c3368f3a597e6add2cfebdad02fddebf/imperfectiveNLI.json) and save to `imperfective/exp1-en/data/imperfectiveNLI.json`
- `run_inference.py.txt`: download [`run_inference.py`](https://raw.githubusercontent.com/boleima/ImperfectiveParadox/938ef893c3368f3a597e6add2cfebdad02fddebf/run_inference.py) and save to `imperfective/exp1-en/data/run_inference.py.txt`

Do **not** execute the downloaded `run_inference.py.txt`: `exp1-en/prompts.py` parses only the `PROMPT_TEMPLATES` dictionary literal via `ast.parse` / `ast.literal_eval`.

## SHA-256 of acquired bytes

| File (relative to `imperfective/exp1-en/data/`) | SHA-256 |
|---|---|
| `imperfectiveNLI.json` | `ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a` |
| `run_inference.py.txt` | `5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880` |

## Local verification after acquisition

Work in a separate local copy of the repository. After placing both files in `imperfective/exp1-en/data/`, run from `imperfective/`:

```sh
python -X utf8 -B verify_prereg.py
```

When the two files are absent, `verify_prereg.py` verifies all public file hashes and cryptographic bindings and reports both files under `self_acquisition_required` (`ok: true`, `runner_fingerprint_recomputed: "requires_third_party_data"`). Once both files are placed at `imperfective/exp1-en/data/` with matching SHA-256 digests, `verify_prereg.py` transitions both excluded artifacts to `verified` (`self_acquisition_required: []`) and also recomputes all 5,200 (`1,040 dev + 4,160 formal`) rendered unit message digests in memory to verify the full Experiment 1 runner fingerprint ID:

```text
895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2
```

Do not add `exp1-en/data/` or `exp1-en/raw/` to a public repository checkout.
