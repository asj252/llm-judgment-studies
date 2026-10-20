# Reader's guide to the frozen plan (`PLAN.md`)

`PLAN.md` is the study plan as it was frozen before the formal runs (version 0.7.1, dated 2026-10-12 to 2026-10-13). It is kept in its original language (Chinese) and is not edited after the formal runs began: its SHA-256 hash is part of every experiment fingerprint, so any change would invalidate the recorded sessions. Changes made after the formal runs started are recorded separately in `PLAN-addendum.md`.

The plan was pre-specified but **not publicly registered**. Read it as a time-stamped record of what was decided before the data came in, not as a polished document.

## What the study asks

When a language model is given a new piece of everyday information, how does its stated probability for a hypothesis change, and does that change depend on (a) whether the information is presented as a known fact or as an anonymous report ("someone says…"), and (b) whether the model gives a single number or a weighted set of five estimates?

## Section map

| Section | Title (translated) | Content |
|---|---|---|
| header | — | Version history, origin of the study, scope, and the novelty claim (a specific combination of design features, not a new phenomenon). |
| 1 | Question, measures and hypotheses | Prior p₀ (context only) and posterior p₁ (context + update sentence); directional movement s = (p₁ − p₀) × sign of the update; the hypothesis table below; rules for wording conclusions and for missing data. |
| 2 | Materials | Item source (δ-SNLI strengthener/weakener sentences), sampling, and exclusion rules (e.g. items asserting a person's ethnicity were excluded; see `sensitive_decisions.json`). |
| 3 | Design | Cells per item: prior, stated update, reported update; strengthener and weakener; direct and multi-estimate asks; a repeat subset. |
| 4 | Parsing and missing data | How answers are read, one resample on failure, and the worst-case imputation used for missing-protected intervals. |
| 5 | Analysis | Item-weighted means, whole-cluster bootstrap (B = 5,000), Holm correction within each configuration, and the three-level wording of conclusions. |
| 6 | Execution | Configurations, seeds, isolation and inclusion rules, session handling. |
| 7 | Known limitations | — |
| 8 | Contribution table | Comparison with the closest prior work. |
| 9–10 | Change logs v0.6, v0.7 | Decisions after the development-set smoke test (parser v2, exclusion of protected-attribute items, dropping the reasoning-on configuration and H3, sensitivity analysis for quoted-speech updates). |

## Hypotheses (Section 1)

| Hypothesis | Statistic | Side | Smallest effect of interest |
|---|---|---|---|
| H1 basic check | mean s, direct ask, stated update | one-sided > 0 | 5 points |
| H2 report wording | mean s (stated) − mean s (reported), direct ask | one-sided > 0 | 5 points |
| H3 reasoning switch | removed in v0.6 (the reasoning-on configuration was not run) | — | — |
| H4a endpoint rate | endpoint rate (direct) − endpoint rate (multi-estimate); endpoint = ≤ 5% or ≥ 95% | one-sided > 0 | 10 percentage points |
| H4b direction sensitivity | mean s (multi-estimate) − mean s (direct), stated update | two-sided | 5 points |

Conclusions distinguish "point estimate reaches the threshold" (≥) from "interval lower bound exceeds the threshold" (strictly >).

## Internal labels you will see

The study was planned and run by the author working with AI assistants in fixed roles. The plan refers to them by letter:

- **a** — planning and writing assistant (drafted the plan and the manuscript);
- **c** — independent reviewer of the plan and code (review rounds are cited as "c 第 N 轮", "c round N");
- **d** — data and literature checker;
- **e** — engineer (implementation and tests);
- **用户** ("the user") — the author, who made all design decisions marked as such.

Other internal references: `#connecting-dots` is the project workspace name; "计划树 P7" (plan tree P7) is the internal index of this plan; `../suppression/`, `report5-…`, `report6-…`, `dev-smoke2-results.md` and `human20-check.md` are working files that are not part of this release. The plan's origin note mentions an earlier pilot whose construct was rejected after human checking; that pilot is not reported here.

## Where the plan and the paper meet

- The four hypotheses and thresholds in the paper are exactly those in Section 1 (H3 removed before the formal runs).
- The analysis code (`analysis.py`, `analyse.py`) and the frozen settings (`analysis_freeze.json`) implement Sections 4–5; `reproduce.py` re-runs them.
- The spread (dispersion) analysis reported in the paper is exploratory and was not part of the frozen plan.
