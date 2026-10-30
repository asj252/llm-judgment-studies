# psych3 preregistration

This is the public preregistration package for five experiments comparing a single estimate with five weighted estimates. The frozen preregistration files are unchanged. Machine-readable Tables G2 and G3 from the first report are available in [supplement-v1/](supplement-v1/); other formal-run result and analysis artifacts are not included here. `PLAN.md` is in Chinese; sections 1–8 contain the main design and freeze rules, and section 7.2 specifies the final confirmatory lists.

- Original freeze record: PLAN v0.7, dated 2026-10-22; frozen state committed at `2026-10-22T10:19:46+08:00` in internal research-repository commit `f0e52d1`. This is the commit time; the exact freeze execution time is not established by this record.
- First public preregistration commit: after pushing this package to <https://github.com/asj252/llm-judgment-studies>, a will record that first public commit's hash and timestamp in a subsequent explanatory commit, before any formal run. The explanatory commit will identify the earlier publication commit, avoiding a self-reference.
- PLAN SHA-256: `67e50d8dc319ad89b557d79f6acb6f37c565f99ab2f10a8d9b9413f7faa2271c`.

The first public commit is the public registration record; the internal freeze commit records the original frozen state. This package alone does not establish that a public push has occurred.

## Experiments and configurations

- A (anchoring) compares responses to identical numbers framed as random anchors or estimates from a reliable source.
- B (hindsight) compares reconstructed prior estimates after outcome disclosure with prospective estimates and an outcome-confirmation control.
- C (base rates) measures responsiveness to base rates and error relative to Bayesian answers.
- D (conjunction) measures signed conjunction excess under separate and joint presentation.
- E (status quo and defaults) measures the pull of a randomly assigned current option or preselected option, with an informed recommendation as a positive control.

The six configurations are local Qwen3-8B with thinking off (Q8_0), codex gpt-6.1-sol (medium), and four agy configurations: gpt-oss-120b-medium, claude-sonnet-5-5-medium, gemini-3.8-flash-low, and gemini-3.8-flash-high. CLI pins, sampling parameters and execution metadata are recorded verbatim in the freeze and runner dependencies. OLMo-2 was removed after failing development acceptance.

## Frozen confirmatory lists (PLAN 7.2)

Each configuration and experiment forms its own Holm family. Unlisted hypotheses are descriptive; no family is reselected after shrinking it.

| Configuration | A | B | C | D | E | Total |
|---|---|---|---|---|---|---|
| Qwen3-8B, thinking off | — | — | — | — | — | 0 |
| codex gpt-6.1-sol | — | B1 B3 B4 | — | D1–D4 | E1–E4 | 11 |
| gpt-oss-120b-medium | A1 | B4 | — | — | E2 | 3 |
| claude-sonnet-5-5-medium | A1 A3 | B1–B4 | — | D1–D4 | E2 E4 | 12 |
| gemini-3.8-flash-low | — | B1 B3 B4 | — | D1–D4 | E1 E2 | 9 |
| gemini-3.8-flash-high | — | B1–B3 | — | D1–D4 | E1 E2 E4 | 10 |

All configurations triggered the C ceiling rule. Codex and both Gemini configurations triggered A's known-truth rule. Power-based demotions and the decision to retain 32 formal E items are documented in PLAN 7.2. Qwen3 remains a descriptive comparison. Formal schedules remain 3,218 main units plus 484 repeat units per configuration.

## Placement

Place these four sibling directories at the public repository root, preserving the paths in this release:

- `psych3/`: the preregistration package.
- `dnli/`: put the five dependencies `parse.py`, `prompts.py`, `run.py`, `local_subject.py` and `codex_subject.py` directly in this directory, keeping the existing `dnli/code/` directory.
- `dnli-agy/`: put its eight dependency files here, including `agent/dnli-subject.md`; keep the existing `dnli/agy-extension/` directory.
- `vs-pilot/`: put `subject.py` here as `vs-pilot/subject.py`; keep the existing `dnli/vs-pilot/subject.py`.

Do not move these dependencies into `dnli/code/` or substitute the previously published redacted copies. Among the 14 corresponding dependency copies, 12 have identical bytes; `dnli/local_subject.py` and `vs-pilot/subject.py` differ from the existing published copies. The latter difference is only comment redaction, but still changes its hash. The copies under `dnli/code/` and the other existing publication directories serve the earlier release; this package preserves the original dependency bytes and relative paths bound by the psych3 freeze. Run `verify_prereg.py` again in the public checkout after placement.

## Files

- `PLAN.md`, `analysis_freeze_psych3.json`, `manifest_ids.json`, `codex_pin.json`: design, per-configuration analysis/execution bindings, prompt IDs/hashes and the psych3 CLI pin.
- `a_*.json`, `b_pairing.json`, `b_canary_log.json`: reviewed IDs, numeric anchors, eligibility decisions, split assignments and cleaning metadata, with no third-party question text. The A eligibility reasons are researcher-authored annotations.
- `items_a_selfwritten.json`, `baserate_stories.json`, `conjunction_items.json`, `items_c.json`, `items_d.json`, `items_e*.json` and previews: researcher-authored materials and generated prompts.
- `prompts_*`, `parse_*`, `gen_*`, `manifest.py`, runners and adapters: original stimulus generation, parsing and execution code. `agy_night.*` and `settings_restore.py` implement scheduling and restoration.
- `analysis_psych3.py`, `analyse_psych3.py`, `bounds_d.py`, power and diagnostic programs: frozen analysis and supporting development calculations.
- `power_dev_summary.md`, `dev_diagnostics_psych3.md`: aggregate evidence used to choose the frozen lists; power recommendations alone are not the final lists.
- `test_*.py`, `stub_subject.py`: offline tests using authored materials or synthetic inputs. Tests requiring third-party inputs are omitted.
- `release-check.json`: logical source, byte size, SHA-256, binding status and per-occurrence scan review. It does not hash itself.

## Offline verification

From `psych3/`, run:

```sh
python -X utf8 -B verify_prereg.py
```

The verifier uses only the standard library and does not call models or access the network. It checks every listed public file, all public material/code/execution file bindings, nested scheduler and agent hashes, the manifest-ID file, and the six fingerprint IDs. `excluded_artifacts` reports all five excluded artifacts: missing files have status `self_acquisition_required` and appear in the list of that name; present files whose hashes match every binding have status `verified` and are removed from that list; present mismatches have status `failed` and make `ok` false.

`ok: true` means that the listed public file hashes, available frozen file bindings and six fingerprint IDs passed these checks. It permits missing excluded artifacts, which are reported separately. It does not establish third-party source authenticity, environment reproducibility or the historical freeze execution time. **This verifier does not recompute `parse_context`, even when `raw_manifest.json` is present.** See the independent calculation below. Environment, model and CLI hashes remain external attestations; unlisted files are not checked. Authenticate the freeze and inventory against the first public preregistration commit; an inventory is not a signature.

For the offline tests, install `requirements.txt` (NumPy is needed for power tests), then run from `psych3/`:

```sh
python -X utf8 -B -m unittest discover -p 'test_*.py'
```

Release preparation ran 170 tests from the release package: 169 passed; the native Windows `ReplaceFileW` test failed with WinError 5 (access denied) in the restricted sandbox. Its original test and assertion are retained. Sandboxed tempfile creation also required a test-process-only compatibility mapping of directory mode 0700 to 0777; no existing ACLs or product defaults were changed. Recheck the native replacement test in a Windows environment with the required file permissions.

## Acquisition, reconstruction and exclusions

See [third-party-data.md](third-party-data.md) for recorded source versions, download URLs, complete file hashes, placement and reconstruction commands. No third-party data is downloaded by verification. Perform reconstruction in a separate local working copy: the original generators write products in place. Compare reconstructed hashes with the freeze before using them.

SynAnchors source questions and ProbCOPA/COPA premises, alternatives and human ratings are not redistributed. Raw/generated A and B inputs, the full raw manifest, and `b_manifest.json` are excluded conservatively; their original hash bindings remain in the unchanged freeze. Development responses and run metadata are excluded because model text may repeat source materials. Raw archives, logs, locks, settings baselines, task/review/report documents and reading packets are excluded. Raw-dependent tests (`test_prompts_b.py`, `test_manifest.py`, `test_run_psych3.py`, `test_agy_night.py`) are not included. The two aggregate development summaries contain no source question text or local paths and are included.

`psych3/analysis_freeze_psych3.json` and `dnli/local_subject.py` contain local machine paths (six in total). By the author's decision, both files are published unchanged so that their byte-for-byte hashes and the frozen fingerprints remain verifiable; they contain no credentials. Changing these paths would invalidate frozen bindings. Scan findings are review evidence, not a guarantee of absence of other sensitive information.

## Appendix: independently recompute parse_context

In a separate local copy, acquire and hash-check the third-party files following [third-party-data.md](third-party-data.md), then run `gen_a.py`, `gen_b.py` and `manifest.py` there to rebuild the full manifest. Run the verifier to check the reconstructed file hashes first. From that copy's `psych3/`, save and run the following as a local Python script with `python -X utf8 -B`. It reproduces the parser-context projection and JSON serialization in `run_psych3.fingerprint`, without importing a runner or invoking a model:

```python
import hashlib
import json
from pathlib import Path

rows = json.loads(Path('raw_manifest.json').read_text(encoding='utf-8'))
context = [{k: row[k] for k in ('unit_id', 'quantity_unit', 'order') if k in row}
           for row in rows]
digest = hashlib.sha256(
    json.dumps(context, ensure_ascii=False, sort_keys=True).encode('utf-8')
).hexdigest()
freeze = json.loads(Path('analysis_freeze_psych3.json').read_text(encoding='utf-8'))
for config, entry in freeze['formal'].items():
    expected = entry['fingerprint']['parse_context']
    if digest != expected:
        raise SystemExit(config + ': parse_context mismatch')
    print(config + ': parse_context verified')
```

Keep the manifest row order unchanged and use the default JSON separators as shown. This independent calculation is separate from the verifier's `ok` result.
