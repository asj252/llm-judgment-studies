# agy extension (v2)

This extension runs four agy configurations on the original delta-NLI block-A
materials. It retains the hypotheses, framing, elicitation questions and parsing
rules, with Unicode whitespace normalization added to parsing. It extends the
original study; it does not replace its three configurations.

The directory contains execution adapters and scheduling code, offline tests,
the frozen agent and task specification, original-source hash inventory,
development/formal result JSONL and session metadata, frozen analysis settings,
archived confirmatory and exploratory analyses, and probe incident notes.
`source_hashes.json` describes the private original source snapshot; it is not
a manifest of this sanitized release. Use the top-level `release-check.json`
for release file hashes and path-redaction counts.

The explicitly allowlisted results_*_agy_*.jsonl, run_meta_*_agy_*.json and
brief-e-agy.md are included byte-for-byte, retaining the original execution's
raw-file paths so record hashes and experiment fingerprints can be verified.
The raw files themselves are not included. release-check.json records each
exception's original-byte status, source SHA-256 and path-prefix counts.
All other text files retain path redaction; sensitive-content scanning also
applies to these exceptions.

Raw streams, stderr, environment snapshot files, review backups and settings
copies are excluded. Tests requiring those original execution archives are
excluded: test_agent.py, test_probe_agy.py, test_probe_fixtures.py and
test_r4_fixes.py. Tests create synthetic inputs and use stub_agy.py; they do
not need a model service. Full material-dependent tests need the layout below.

## Re-run analysis without calling a model

From the release root, using Python 3.10 or later and reconstructed/included
`data/items_text.json`, choose a new output filename:

```sh
python -X utf8 -B agy-extension/reproduce_public.py --out reproduced-agy.json
```

This public entry creates a temporary legacy layout and runs all frozen
calculations with B=5000. Its only validation change replaces the check that
raw attempt files exist and match their hashes with a check that raw SHA-256
hashes are registered in each attempt record. Session registration,
record_sha256, fingerprints, material/prompt bindings, planned units and
frozen analysis code hashes remain checked. It compares every value in the
complete decoded output with analysis_formal.json, including all confirmatory
results, and prints OK only on exact equality.

The public entry cannot verify the raw files themselves. Their SHA-256 hashes
are registered in the records. The authors retain the original streams and
stderr and can provide them for verification on request. They are excluded
because they contain local user paths and conversation IDs.

For strict original verification with access to those archives, copy code/ to
dnli/, agy-extension/ to dnli-agy/, and data/items_text.json to
dnli/raw/items_text.json under a new temporary parent. Preserve file bytes.
From dnli-agy/ run:

```sh
python -X utf8 -B analyse.py run formal reproduced-agy.json --final
```

This frozen entry still requires the raw files at their recorded paths.
Original fingerprint IDs and registered hashes have not been recomputed.
