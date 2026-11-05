# Third-party data: acquire locally without redistribution (Experiment 3)

This preregistration package does **not** redistribute `ImperfectiveNLI` item text (`premise` or `hypothesis`), derived Experiment 3 item text (`clusters_100_e3.json`), upstream inference code, or development-set model free-text responses. Validate every acquired or locally derived file against the complete SHA-256 hashes below before use.

## Upstream source and license note

- **Upstream repository**: GitHub `boleima/ImperfectiveParadox`, fixed commit `938ef893c3368f3a597e6add2cfebdad02fddebf`
- **Associated paper**: arXiv:2601.09373v3 (*Artifact Usage* section, verified 2026-10-26), releasing the `ImperfectiveNLI` dataset under Creative Commons Attribution-NonCommercial 4.0 International (`CC BY-NC 4.0`) for research purposes.

Obtain the two pinned files from commit `938ef893c3368f3a597e6add2cfebdad02fddebf` and place them in `imperfective-exp3-en/exp3-en/data/` using the exact filenames below:

- `imperfectiveNLI.json`: download [`imperfectiveNLI.json`](https://raw.githubusercontent.com/boleima/ImperfectiveParadox/938ef893c3368f3a597e6add2cfebdad02fddebf/imperfectiveNLI.json) and save to `imperfective-exp3-en/exp3-en/data/imperfectiveNLI.json`
- `run_inference.py.txt`: download [`run_inference.py`](https://raw.githubusercontent.com/boleima/ImperfectiveParadox/938ef893c3368f3a597e6add2cfebdad02fddebf/run_inference.py) and save to `imperfective-exp3-en/exp3-en/data/run_inference.py.txt`

Do **not** execute the downloaded `run_inference.py.txt`: `exp3-en/prompt_parts.py` parses only the `PROMPT_TEMPLATES` dictionary literal via `ast.parse` / `ast.literal_eval`.

##Deterministic local derivation of `clusters_100_e3.json`

Once `imperfectiveNLI.json` and `run_inference.py.txt` are placed in `imperfective-exp3-en/exp3-en/data/`, run from `imperfective-exp3-en/exp3-en/`:

```sh
python -X utf8 -B materials_e3.py
python -X utf8 -B validate_materials_e3.py
```

`materials_e3.py` deterministically derives `exp3-en/data/clusters_100_e3.json` (`400` main items + `200` diagnostic items across the 100 atelic activity clusters `D_001..D_100` / `B_001..B_100`) and verifies all SHA-256 digests.

## SHA-256 of acquired and derived bytes

| File (relative to `imperfective-exp3-en/exp3-en/data/`) | Role | SHA-256 |
|---|---|---|
| `imperfectiveNLI.json` | Upstream dataset (acquired) | `ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a` |
| `run_inference.py.txt` | Upstream prompt template source (acquired) | `5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880` |
| `clusters_100_e3.json` | Deterministically derived E3 clusters (`materials_e3.py`) | `7f10a952c8ec32a4c978b69a0f755085fd76490d72d3706db8773b93d17da8aa` |

## Local verification after acquisition

From `imperfective-exp3-en/`, run:

```sh
python -X utf8 -B verify_prereg_e3.py
```

When the two upstream files are absent, `verify_prereg_e3.py` verifies all public file hashes, cryptographic bindings, and S4/S5 calibration locks and reports both files under `self_acquisition_required` (`ok: true`, `runner_fingerprint_recomputed: "requires_third_party_data"`). Once `imperfectiveNLI.json` and `run_inference.py.txt` are placed in `imperfective-exp3-en/exp3-en/data/`, `verify_prereg_e3.py` deterministically derives and validates the 100 clusters in memory (`validate_materials_e3.py`) and recomputes all `5,320` (`1,160 dev + 4,160 formal`) rendered unit message digests to verify the full Experiment 3 runner fingerprint ID:

```text
cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3
```

Do not add `exp3-en/data/` to a public repository checkout.
