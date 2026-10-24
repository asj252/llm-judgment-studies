# Addendum 1: Codex executable and fingerprint

This addendum changes how the Codex configuration is bound to the preregistration published at commit `802d760` (22 October 2026). It was written and published before any Codex formal unit was run. Nothing else in the preregistration changes: `PLAN.md`, the materials, the analysis code, the other five configurations and the Codex confirmatory list (Section 7.2 of the plan: B1, B3, B4, D1–D4, E1–E4) are as preregistered.

## 1. What happened

The frozen Codex entry bound `codex-cli 0.163.0-alpha.10.2` at the path where the Codex desktop application installs its command-line tool. When the Codex formal run started at 00:00 on 23 October, the installed tool reported `0.163.0-alpha.11.1`, and the version check refused to start; no Codex formal unit was run. When we checked later on 23 October, the installed tool was `0.163.0-alpha.11.2` (its executable file is dated 03:56 that morning) and the directory of the pinned version no longer existed.

## 2. Same version, separate installation

On 23 October the same version, `0.163.0-alpha.10.2`, was installed from the npm registry into a separate directory that the desktop application does not update:

| | Preregistered | From this addendum |
|---|---|---|
| CLI version | `codex-cli 0.163.0-alpha.10.2` | unchanged |
| Executable | `C:\Users\asj\AppData\Local\OpenAI\Codex\bin\896a0166b774037a\codex.exe` | `E:\Claude\tools\codex-0.163.0-alpha.10.2\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe` |
| Executable SHA-256 | not recorded | `76b4bfc83785f31c59ec384760003109410132bab602a2115d83e88e04a6dc47` |

A new entry point (`run_codex_psych3_pinned.py`) uses this executable, checks its SHA-256 at start-up and keeps the original version check before every call. The model (`gpt-6.1-sol`), reasoning effort (`medium`), ChatGPT login, isolation arguments, global `AGENTS.md`, prompts, parsing, inclusion and retry rules are unchanged. We do not claim that the npm binary is byte-identical to the one the desktop application had installed; only the version string is the same.

## 3. The model catalogue entry is no longer part of the fingerprint

The preregistered Codex fingerprint included the SHA-256 of the model's entry in `codex debug models` (`model_entry_sha256`). This entry is supplied by OpenAI's servers. Snapshots taken on 24 October showed two versions of the entry for the same model alternating within minutes, and the preregistered hash matched neither:

| | SHA-256 |
|---|---|
| preregistered | `bfb13398db3e0039f4f5290fb17a51e9b776a9c977a9ac24a3f464f85f814a56` |
| version A | `addc8ea3e7ce90428a89b2d82a5d57235ee07ae30d20f0391546fa4c8930dbb5` |
| version B | `2723b11fc3c0791615cb5a14f6c1abade723228bd7b3d269f5eebeb7264d2cb6` |

Versions A and B differ in six places: the section on plugins and apps in Codex's base instructions; the same section in `model_messages.instructions_template`; the browser-use and computer-use confirmation policies; one sentence of the default collaboration-mode text; the context window (500,000 vs 272,000 tokens); and `available_access_programs`. Most of these concern tools, plugins, apps and collaboration modes, which the isolation arguments disable and the task does not use; the context window does not. We have not tested whether any of these differences affects the answers. The catalogue entry mixes instruction text with metadata, and we cannot see exactly what Codex sends to the model; the plan already states that Codex's system prompt is outside our control (Sections 1 and 11).

Because the entry can change between sessions, keeping its hash in the fingerprint would stop Codex whenever a new session starts. From this addendum on, the Codex fingerprint binds the executable's SHA-256 instead of the catalogue entry. At the start of every Codex session the runner saves the full entry and its hash, indexed by session. This records the version observed when the session started; each call starts its own CLI process, so it does not establish which version served a given call. In addition, five snapshots were taken between 13:44 and 14:04 on 24 October, and from 14:04 that day the entry is snapshotted every two hours for 14 days.

## 4. Re-running the development set and replacing the freeze entry

Since the fingerprint changed, the formal gate requires a complete development set under the new fingerprint. The preregistered Codex development set (618 units, run on 19 October) was archived unchanged to `raw/archive_dev_codex_pre_repin_20261023/`. A partial rerun on 23 October under an intermediate fingerprint that still bound the catalogue entry (109 completed units, plus two stopped units, one of them at the end of a time-bounded batch) was archived to `raw/archive_dev_codex_pre_repin_20261024_v2/`. Both archives keep a per-file SHA-256 manifest. The full development set was then run again under the new fingerprint and checked against the preregistered acceptance criteria (complete set, at least 90% parsed at the first attempt, at most 2% missing). The rerun serves only as acceptance evidence; the power analysis, the diagnostics and the confirmatory list were not revisited.

After acceptance, only the Codex entry of `analysis_freeze_psych3.json` was rebuilt, with the same function and arguments as before (`analyse_psych3.freeze('formal', 'codex', B=5000, names=<the eleven hypotheses>)`). The replacement tool refuses any change other than those described in Sections 2 and 3 (executable path changed, `model_entry_sha256` removed, `exe_sha256` added) and the resulting fingerprint ID and development-acceptance figures; it also checks that the entries for the other five configurations, the bound plan, materials and code are unchanged. The original Codex entry is kept in `raw/archive_freeze_codex_v1.json` and the field-by-field difference in `raw/codex_repin_freeze_diff.json`.

Evidence:

- Development rerun: 24 October 2026, 14:35–17:14 (Asia/Shanghai), in seven sessions that share one fingerprint. The results file holds 624 records: 618 admitted units and 6 units stopped by a failed call. All six stops were failures of the connection to OpenAI (repeated "Reconnecting…" errors); each session that stopped closed with `closed_ok=True`, so its completed units count, and each stopped unit was run again in a later session. Three stops were resumed by hand after review and three automatically (Section 5). Completed units per session: 5, 195, 204, 137, 6, 16 and 55. Acceptance: 618 of 618 admitted, 618 parsed at the first attempt of their admitted record, 0 missing. Six sessions started with catalogue version A and one with version B. `results_dev_codex.jsonl` SHA-256 `7ba0be2c7caccce6383f214d87a3f40f421781bd48b32fa3885d2440ff888626`; `run_meta_dev_codex.json` SHA-256 `eef39b81ed9165346234da514bc3742aa5b290c46953d2b03a6ace5401c6002e`.
- Fingerprint ID of the Codex entry: `0fe9f96afb8af3f2e8a994d4711144ff0aafbcc47e52c5ba51805ee3cd82c51b` → `02801ac0f09c816ea0ceadd1d59dd4041475cb4be6ade960cd4b1e59e957d8db`. The difference receipt lists exactly four changed fields: `subject_meta.exe`, `subject_meta.exe_sha256` (added), `subject_meta.model_entry_sha256` (removed) and `fingerprint_id`.
- Replacement freeze: research-repository commit `08591dd` (2026-10-24T17:14:42+08:00); `analysis_freeze_psych3.json` SHA-256 `00da3c3fec1cad6dec9b93bf0fd3e85ff3f12cf5d86ffa51515902df3985d5a1`. The entries for the other five configurations are identical to the preregistered ones.
- Codex formal results: none. `results_formal_codex.jsonl` and `run_meta_formal_codex.json` did not exist when checked at 2026-10-24T18:45:39+08:00, immediately before this addendum was published.

## 5. Operational changes that do not affect the fingerprint

These change only when the runs happen, not what is run or how responses are scored:

- Codex may also be run during the day, in batches bounded by an end time or a number of units, in addition to the nightly window (00:00–07:45 Asia/Shanghai). The Codex fingerprint never included a time window. A batch that reaches its bound stops before starting a new unit; completed units count, and the interrupted unit is run again later.
- When a Codex session stops only because the connection to OpenAI failed, the runner records the event and starts a new session after a wait (5, 10, then 20 minutes), at most eight times per runner invocation. "Only because the connection failed" means: the failed call's reasons are a count of failure events, optionally with a warning that the client fell back from WebSockets to HTTPS; every error event is a "Reconnecting…" message whose cause is a timed-out request, a failed or timed-out workspace routing discovery, or a stream that disconnected before completion; the only other permitted item is the fixed Code Mode notice that the isolation arguments always produce. Any other stop still waits for review. The inclusion rules are unchanged: the unit whose call failed is run again.
- The nightly tasks now start without a console window, after a closed terminal window interrupted the first formal night (23 October, 00:14). Records written before the interruption were kept under the existing session rules.

## 6. Files

The preregistered files in `psych3/` are left as published at `802d760`, so they still verify against that commit. The files of this addendum are in `psych3/addendum-1/`:

- `ADDENDUM-1.md`: this text;
- `analysis_freeze_psych3.json`: the freeze file in force from this addendum on (only the Codex entry differs from the preregistered one);
- `codex_repin_freeze_diff.json`: the field-by-field difference of the Codex entry;
- `codex_exe.json`: path and SHA-256 of the Codex executable;
- `run_codex_psych3_pinned.py`, `codex_repin.py`, `night_local_codex.py`, `sample_codex_model_entry.py`: the new Codex entry point, the archive-and-replace tool, the runner for night and daytime batches, and the catalogue sampler;
- `codex_model_entry_hashes.json`: time and SHA-256 of every saved catalogue entry (the entries contain OpenAI's instruction text and are not republished); derived from the runner's indexes;
- `SHA256SUMS`: SHA-256 of the files above.

The scripts are source snapshots from the research repository, where they sit in the `psych3/` folder next to the preregistered code. To run them, copy them, together with `codex_exe.json`, into a working copy of `psych3/` (with the top-level `dnli/`, `dnli-agy/` and `vs-pilot/` folders beside it, as in this repository) and replace `psych3/analysis_freeze_psych3.json` there with the version in this folder. Running them from `addendum-1/` itself fails, because they import the preregistered modules and read the materials and freeze file from their own folder.
