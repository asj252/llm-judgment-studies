# Preregistration record (Experiment 3, English Activity Boundary Modifiers)

| Item | Value |
|---|---|
| First public preregistration commit (Experiment 3) | [`d793eaafdb42222cc0a993cddba3baf1f700bf23`](https://github.com/asj252/llm-judgment-studies/commit/d793eaafdb42222cc0a993cddba3baf1f700bf23) |
| Commit time | 2026-11-05T11:00:55+08:00 (pushed 2026-11-05T11:00:59.307475+08:00) |
| Experiment 1 public preregistration commit (unchanged) | [`a6c90b51c3bf2e3c21c34f017bd5549126322762`](https://github.com/asj252/llm-judgment-studies/commit/a6c90b51c3bf2e3c21c34f017bd5549126322762) |
| Experiment 2 public preregistration commit (unchanged) | [`a42fbbea113a6d0eaab423f440a4b64b7a6d3215`](https://github.com/asj252/llm-judgment-studies/commit/a42fbbea113a6d0eaab423f440a4b64b7a6d3215) |
| `exp3-en/PLAN-E3.md` / `PLAN-E3.frozen.md` SHA-256 | `ec4137b4a280b34977a26d755bd414b81392ec3419f6b9a84e4e6de941f3082b` |
| `exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/freeze.json` SHA-256 | `94b74e82a600c084909a837b06dc65eb7846ff358359fc42992124e4ce81e47c` (`written_at = 2026-11-05T11:33:02.927635+08:00`) |
| `exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/calibration-e3.json` SHA-256 | `0719bb94336a2b18e1795aae7767714169ddf94c60502aa542b14454a0a44806` |
| `exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/c-review.md` SHA-256 | `70acde0775c2fd7d1e3806264519665ff45f2cfa19d26a430bda0014a932f87f` |
| `exp3-en/subclasses_e3.json` SHA-256 | `ff3be2370261c499397fbfba9921086cb69467775d196e53bf6d83912c01721d` |
| `exp3-en/split.json` (`20 dev` / `80 formal` clusters) SHA-256 | `cd0e099a38481b23c071d3950aac4527daf29aea12076f34ea9eadc4a90d7ea4` |
| `exp3-en/data/clusters_100_e3.json` (self-acquired via `materials_e3.py` from `imperfectiveNLI.json`) SHA-256 | `7f10a952c8ec32a4c978b69a0f755085fd76490d72d3706db8773b93d17da8aa` |
| Experiment 3 runner `fingerprint_id` (`qwen3-8b@macmini-m6`) | `cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3` |
| Locked primary confirmatory family (`selected_step = 3`) | `hybrid_bessel_t_tango_e3` (companion `hybrid_pct_tango_e3`, `demoted_slots = ["E3_H3"]`, `20/20` calibration cells passed) |
| Certified exact Tango lookup tables (`exact-tango-tables-e3.npz`) SHA-256 | `59845e08a34c997c66b8d3c86244a87a7c5d8e6d018743c467bf37be4300828f` |
| Experiment 1 reference summary (`exp1-bd-reference-summary.json`) SHA-256 | `739a91ede22b30d65a1dc41d38e681adc3a913ea01024bc4c53c0c89fa6dac5e` |
| Formal runs started | not yet (no Experiment 3 formal unit had been run when commit `d793eaa` was pushed or when `freeze.json` was written) |

The 44 files of commit `d793eaa` are the Experiment 3 (English activity boundary modifiers) preregistration. This record was added in a subsequent commit so that it can name commit `d793eaa` and the `freeze.json` receipt (`94b74e82a600c084909a837b06dc65eb7846ff358359fc42992124e4ce81e47c`) bound to `prereg_commit = d793eaafdb42222cc0a993cddba3baf1f700bf23`; it does not change any of the 44 preregistered Experiment 3 files, any of the 46 Experiment 2 files from commit `a42fbbe`, or any of the 65 Experiment 1 files from commit `a6c90b5`. `verify_prereg_e3.py` reported `ok: true` (`43/43` public files verified; with self-acquired `imperfectiveNLI.json` and `run_inference.py.txt`, all `5,320` rendered unit digests recompute to `cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3`).
