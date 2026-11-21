# dnli/v3-release/dnli-api

Public D-NLI API runners, frozen configurations, run metadata, and sealed summaries.

Shared analysis code and split definitions: [../../code/](../../code/).
Public item text: [../../data/items_text.json](../../data/items_text.json).
Run the offline tests from this directory:

```sh
python3 -X utf8 -B -m unittest test_api.py
```

Raw response streams are archived separately and are not included in this release.
Optional local credential configuration uses DNLI_KEYS_ENV_FILE.

