# English paper appendices A-H

Original preregistration materials and Addendum 1 are public in the study repository. The v2 CSVs and analysis products are local package deliverables, without a claim that they are publicly uploaded. Original third-party SynAnchors and COPA/ProbCOPA texts are not reproduced.

## Appendix A. Materials, scale, and seeds

**A: anchoring.** SynAnchors 0.1 semantic subset, Hugging Face `TimTargaryen/SynAnchors` revision `e6df428`, whose data card specifies Apache-2.0. We use questions and truths, not its anchors or prompts. Eligibility was frozen before development: the question must stand alone; truth must be positive and finite, with clear units and reference time (time-invariant quantities need no year); anchors must be expressible at the item's precision. Of 60 items, 36 were eligible and 24 excluded: 19 lacked factual truth (subjective preferences, bargaining, compensation, etc.), 3 had ambiguous units or quantities, and 2 had clearly questionable truths. With fewer than 40 eligible items, we followed the plan and wrote 24 additional items with verifiable sources and review. Development has 10 items (6 SynAnchors, 4 new); formal testing has 50 (30, 20). Analyses also describe source strata. Anchors were rounded to customary item-specific precision and frozen individually, requiring 0 < low anchor < high anchor.

**B: hindsight.** ProbCOPA, GitHub `McGill-NLP/probabilistic-reasoning` revision `b983b12`. Its repository LICENSE is MIT, with no separate data-license clarification in README/LICENSE. There are 105 COPA effect items, each with two outcomes rated from 0–100 for likelihood by 25–30 native speakers. All 105 were matched using source IDs and premise text. Synthetic canary entries inserted by the authors were removed by deleting rows with `type == canary` and retaining the bytes of all other rows. Each source file was reduced from 5,908 to 5,858 rows; downloaded cleaning code was not executed. Human ratings are descriptive only: mean ratings (`mean_response`) are primary and medians secondary. Spearman correlations with F aggregate by UID and use average ranks for ties. Acquisition, reconstruction, and file SHA-256 values appear in `third-party-data.md`.

**C: base rates.** There are 24 newly written scenarios, without classic item wording. Bayesian answers are 8.33, 50.00, and 79.41% for accuracy set A (90%/10%), and 13.91, 64.00, and 87.27% for set B (80%/5%). Prompts define the event meant by “positive” and state that the person is randomly selected from positive cases, without other information.

**D: conjunction.** Item bank v0.2. Authors stored complete conjunction and disjunction sentences for person items. Components must be single, independently truth-evaluable facts, without protected attributes as the basis for A or B. Person items use “now” as a shared assessment time, and event pairs are restricted to “the same day.” Development includes P 4 and W 3 (1 per dependence stratum); formal testing includes P 20 and W 15 (5 per stratum).

**E: status quo and defaults.** The 40 items span 19 domains, including 4 each on software settings, insurance add-ons, and subscriptions. Scenarios establish registration, activation, or initial setup; cost-related items specify that the choice precedes payment. T is P in 20 items and Q in 20, with P listed first; the formal split is 17/15. Stratification by whether T is first or second is therefore a cross-item description, without identifying a position effect.

**Scale** (per configuration; `manifest_ids.json`)

| Experiment | Clusters (development/formal) | Units per item | Development | Formal | Repeat subset |
| --- | --- | --- | --- | --- | --- |
| A | 10/50 items | 10 | 100 | 500 | 80 (8 items) |
| B | 15/90 items | 16 | 240 | 1,440 | 192 (12 items) |
| C | 4/20 scenarios (8/40 items) | 12 | 96 | 480 | 96 (4 scenarios) |
| D | 7/35 items (P 4/20, W 3/15) | 10 | 70 | 350 | 60 (P 4, W 2) |
| E | 8/32 items | 14 | 112 | 448 | 56 (4 items) |
| Total |  |  | 618 | 3,218 | 484 |

**Seeds**

| Purpose | Seed | Source |
| --- | --- | --- |
| A split/repeats (SynAnchors) | 20261440/20261441 | `gen_a.py` |
| A split/repeats (new items) | 20261442/20261443 | `gen_a.py` |
| B split/repeats | 20261450/20261451 | `gen_b.py` |
| C split/repeats | 20261410/20261412 | `gen_c.py`, `manifest.py` |
| D joint order/split/repeats | 20261430/20261431/20261432 | `gen_d.py` |
| E split/repeats | 20261460/20261461 | `manifest.py` |
| Execution/call base seeds (development/formal) | 20261080/20261081 (same as δ-NLI) | `run_psych3.py` |
| Analysis/power bootstrap | 2026101903 | `analysis_psych3.py` |

Execution order initializes from “base seed × 10 + configuration offset,” shuffling clusters and then units within clusters. Configuration offsets follow δ-NLI (qwen3-off 0, codex 3); agy uses the first 8 hexadecimal digits of the configuration-name string's SHA-256 (e.g., of the string `agy:claude-sonnet-5-5-medium`). A call seed is the first 8 SHA-256 digits of “set|configuration|unit ID|a<attempt number>|base seed,” affecting Qwen3 only.

**Table A1. Admitted units and historical exclusions**

Excluded formal lines are reported once per configuration (on its r0 row), not allocated to a round. F0/F1 rows partition Flash high; they are not additional configurations.

| Configuration | Stage / round | Admitted | OK | Missing | Excluded lines |
| --- | --- | --- | --- | --- | --- |
| codex | dev r0 | 618 | 618 | 0 | 6 |
| codex | formal r0 | 3218 | 3215 | 3 | 22 |
| codex | formal r1 | 484 | 484 | 0 | see r0 |
| Sonnet 5.5 | dev r0 | 618 | 618 | 0 | 3 |
| Sonnet 5.5 | formal r0 | 3218 | 3218 | 0 | 9 |
| Sonnet 5.5 | formal r1 | 484 | 484 | 0 | see r0 |
| Qwen3 | dev r0 | 618 | 617 | 1 | 0 |
| Qwen3 | formal r0 | 3218 | 3211 | 7 | 1 |
| Qwen3 | formal r1 | 484 | 483 | 1 | see r0 |
| gpt-oss-120b | dev r0 | 618 | 618 | 0 | 4 |
| gpt-oss-120b | formal r0 | 3218 | 3210 | 8 | 24 |
| gpt-oss-120b | formal r1 | 484 | 484 | 0 | see r0 |
| Flash low | dev r0 | 618 | 618 | 0 | 1 |
| Flash low | formal r0 | 3218 | 3217 | 1 | 10 |
| Flash low | formal r1 | 484 | 484 | 0 | see r0 |
| Flash high | dev r0 | 618 | 618 | 0 | 1 |
| Flash high | formal r0 | 3218 | 3217 | 1 | 16 |
| Flash high | formal r1 | 484 | 484 | 0 | see r0 |
| Flash high F0 | r0 | 2687 | 2686 | 1 | 13 |
| Flash high F0 | r1 | 362 | 362 | 0 | see r0 |
| Flash high F1 | r0 | 531 | 531 | 0 | 3 |
| Flash high F1 | r1 | 122 | 122 | 0 | see r0 |

**Table A2. Formal missingness retained under Addendum 2 and the frozen rules**

Missing records remain missing; historical excluded lines are a different category. No missing result is silently treated as an observed number.

| Configuration | Experiment | Round | Missing | Batch |
| --- | --- | --- | --- | --- |
| codex | A | r0 | 3 | original batch |
| Qwen3 | E | r0 | 6 | original batch |
| Qwen3 | C | r0 | 1 | original batch |
| Qwen3 | E | r1 | 1 | original batch |
| gpt-oss-120b | B | r0 | 6 | original batch |
| gpt-oss-120b | A | r0 | 2 | original batch |
| Flash low | B | r0 | 1 | original batch |
| Flash high | B | r0 | 1 | F0 |

## Appendix B. Subject settings, parsing, and retries

**Qwen3.** Qwen3-8B, HF commit b968826, converted to GGUF Q8_0 using llama.cpp build b11560. Parameters are temperature 0.6, top-k 20, top-p 0.95, min-p 0, with other samplers disabled; context 16,384 and generation limit 8,192 tokens. The HF tokenizer's chat template is used with `enable_thinking=False`, one user message, and no system prompt. Exhausting the length limit before an end token counts as truncation.

**codex.** codex CLI 0.163.0-alpha.10.2, separately installed under Addendum 1, with executable SHA-256 in the fingerprint; gpt-6.1-sol, reasoning effort medium, ChatGPT login. Isolation options, the global `AGENTS.md` hash, event-stream checks, and internal-log checks follow δ-NLI. Tool contamination invalidates an attempt and permits one retry separate from parsing retries; persistent contamination is `tool_contaminated`. Disconnections invalidate attempts and permit retries, stopping only after three consecutive instances for the same unit. Calling errors or quota indications stop continuation; the unit is redone later. Changes to global instructions or log-integrity failures invalidate the entire session. psych3 executes codex sequentially in one worker.

**agy.** agy CLI 1.4.0 with automatic updates disabled. Each call starts outside a git repository in a fresh temporary directory containing only a custom agent definition: `tools: []`, default components excluded, and body “Answer the user's question directly.” Execution uses `--sandbox`, without conversation continuation, and a 600-second call timeout. Any event-stream step other than user input and final answer—including tool events, rejected actions, or unknown step types—counts as contamination and triggers a retry. Timeout, disconnection, and truncation invalidate attempts and permit retries; three consecutive instances of the same class for one unit stop execution for review. Rate limits trigger exponential backoff from 5 to 60 minutes; after 6 continuous hours, execution sleeps until the next day; 3 cumulative days for the same unit stop execution. Completed units remain valid. Before and after each unit, environment snapshots compare agy version, permission-setting hash, setting-key names, agent-file hash, and server-reported model name; any change stops execution before the next unit. Finalization is per unit: persist raw attempt → append result → read back and verify → atomically update registration.

**Parsing.** Probability cells use δ-NLI parser v2. Direct responses use the final answer field; an invalid number on that line fails without fallback. Multi-estimate responses use the last group beginning with a line resembling “Estimate 1.” Exactly 5 lines numbered 1–5 are required, with values from 0–100 carrying percent signs and weights in [0, 1]; a positive weight sum is normalized. A accepts finite positive quantities, including decimals and scientific notation such as `1.2e6`, but not commas or ranges; item-consistent unit suffixes may be ignored. Nonpositive or nonfinite values, an empty final field, an incomplete final multi-estimate group, or total weight ≤ 0 all fail. Joint D reads the final four lines for direct responses, or the final group of 5 lines each containing four percentages and a weight. Any missing number fails the entire cell; partial use is prohibited. Before parsing agy answers, Unicode space-separator characters (Zs) are replaced with ordinary spaces. For A's comparison answer, the first whole-word occurrence of higher/lower/equal in the full response is used, case-insensitively.

**Strict reader.** Analysis reads only records from normally finalized, noninvalidated sessions with matching fingerprints (registered units for agy), and matching result/raw-file hashes (`analyse_psych3.load_valid(..., strict=True)`). Residual records from unfinalized sessions and superseded retries are excluded.

## Appendix C. Missing-value substitutions and preregistered descriptive measures

**General missingness-protection rule** (PLAN §§1, 5b.3, 7.1 rules 3–4). Observed values remain unchanged; only missing cells are replaced. Linear statistics have lower- and upper-bound versions. The lower version assigns 0 to missing cells with positive coefficients and 100 to those with negative coefficients; the upper version reverses this. The positive-direction tail probability uses the lower version (proportion of resampled statistics ≤ 0); the negative direction uses the upper version (≥ 0). Conservative two-sided p is twice the smaller tail proportion, capped at 1. Protection uses the full formal item set for that hypothesis, equal item weights, and whole-cluster resampling; complete-item and protected analyses report separate denominators. Clipping bounds C's item-level slopes at approximately ±3.01, which supplies finite worst-case values. When a hypothesis requires both accuracy sets to be complete within a scenario, a scenario with one complete set is excluded from the complete-item analysis but filled by substitution in the protected analysis. A has no upper bound and no protection (Section 3.4).

**Statistic-specific substitutions in D** (any missing number in a joint-response cell makes all four missing)

| Statistic | Supported direction | Worst-case substitution |
| --- | --- | --- |
| D1: Δ_S | Positive | Missing P_S(A and B) = 0; P_S(B) = 100 |
| D2: Δ_S − Δ_J | Positive | Minimize Δ_S as above; if joint values are missing, P_J(A and B) = 100 and P_J(B) = 0 (whole-cell missingness gives Δ_J = +100) |
| D3: Δ_S,multi − Δ_S,direct | Two-sided | Obtain feasible lower and upper difference bounds; use the lower for the positive direction and upper for the negative direction; crossing zero does not confirm direction |
| D4: Δ_J,multi − Δ_J,direct | Two-sided | As D3, using joint elicitation |

**E.** Item-level E1/E2, y(direct,T) − y(direct,O), ranges over [−100, 100]. E3/E4, y(multi,T) − y(multi,O) − y(direct,T) + y(direct,O), ranges over [−200, 200]. Both use the general rule. The advice control uses the same cell-level substitutions and descriptive intervals, outside Holm.

**Combined reporting.** Complete-item and protected results are combined into one report only when no cells required by the entire confirmatory family are missing. Because a test without missing cells can still change Holm position through other members' conservative p-values, the two versions are otherwise reported separately.

**Preregistered descriptive measures** (outside Holm; no significance conclusions)

- A: log errors relative to truth in each condition, including unanchored; weighted proportions of multi-estimate candidates beyond the anchor (above high anchors, below low anchors); agreement between comparison answers and final estimates; strata by item source.
- B: b stratified by whether the disclosed outcome is higher/lower in F; weighted proportions of multi-estimate HI candidates below the same-format F aggregate; Spearman correlations between F and human ratings; input-condition difference c = ½ Σₖ [PO(O_k) − F(O_k)].
- C: three-point scatterplots per item and nonmonotonicity rates; clipping-bound proportions and sensitivity to [0.1%, 99.9%] clipping; proportions within 1 percentage point of Bayesian answers; weight assigned to the multi-estimate candidate nearest the Bayesian answer; joint descriptions of |slope − 1|, intercept, and Bayesian error.
- D: violation rates for P and W separately by presentation and response format; means and SDs of Δ, Δ_min, and additive-identity deviation X for W by dependence stratum; disjunction excess; weighted candidate-level violation proportions under joint multi-estimate elicitation; whether P(B) < P(A) in person items; repeat-subset distributions of differences between two reports for the same unit.
- E: “label assigned to T − neutral” and “neutral − label assigned to the other option”; neutral-response distributions; E_advice, S_E = E_advice − E_status_quo (also relative to defaults), and their format changes; E_status_quo − E_default; weighted candidate proportions on either side of 50; strata with T first/second.
- Cross-experiment (PLAN §10): within each configuration, paired differences and 95% intervals on original scales for A's AI_irrelevant, AI_informative, and S; B's b and e_PO; C's slope and Bayesian error; D's Δ under separate and joint elicitation; and E's E_status_quo, E_default, and E_advice, showing values and differences across formats. δ-NLI s is a comparison only; no ratios are used.


## Appendix D. Development diagnostics and power

**Power simulations** (PLAN §§7, 7.1; `power_dev_summary.md`). Development clusters are resampled while retaining condition correlations within items. At the hypothesis-statistic level, mean contributions are shifted to the specified effect (AI scale in A), and planned numbers of clusters are resampled. Hypotheses in one family are resampled together; with fewer than 4 development clusters, they are instead resampled separately and this is noted. Missingness is generated from development cell-failure rates with a minimum of 2%; D joint elicitation fails as a whole cell. Scenarios are zero effect, the SESOI, and twice the SESOI (plus a ceiling scenario in C), under 1, 1.5, and 2 times the development SD. Each scenario has 1,000 simulations, each running the complete family Holm procedure and decisions with inner bootstrap B = 499. Power targets use complete-item-subset decisions. Protected-version attainment rates are reported alongside them but do not determine screening. For example, Sonnet B1's direction-confirmation rate at the SESOI is 1.000 for complete items and 0.003 with protection; the frozen rule retains it.


Table H1 gives the unchanged lists and all six development acceptance sets. Exact downgrade reasons remain in the audited supplementary JSON, separate from formal recommendation-control interpretation caveats. The E no-expansion exception preserves development fingerprints. Qwen3 is retained by decision as the descriptive benchmark.

## Appendix E. Execution details, addenda, and accounting

**Fingerprints.** The execution fingerprint binds the plan, material files and item manifest (`manifest_ids.json`), prompt and parsing code, runner code (including δ-NLI `run.py` and `parse.py`), subject-wrapper code, subject settings (version, model, reasoning effort, isolation options, instruction-source hashes, etc.), and retry rules. For the original agy F0 batches it also binds night-scheduler code and settings: 4 workers, Asia/Shanghai, new units 00:00–07:45, hard cutoff 08:00, and automatic-release limit 8. The analysis freeze separately binds analysis-code hashes, B, seed, α, hypothesis specifications, configuration lists, and development acceptance. Startup recomputes the execution fingerprint and rejects mismatches against the freeze.

**Time windows (original batches).** Night schedules for codex and Qwen3 start new attempts, including retries, only between 00:00 and 07:45. Calls in progress are not forcibly stopped at 08:00; units blocked by the window after 07:45 are redone the next night. Since Addendum 1, codex also permits daytime batches bounded by end time or unit count; no new units start after the boundary. Historical periods for the initial three configurations were codex 10-25 00:01 to 10-27 20:53; Sonnet 10-23 00:01 to 10-28 01:00; and Qwen3 10-23 00:01 to 10-24 06:00.

The original agy F0 batches used four workers, the 00:00-07:45 admission window and an 08:00 hard cutoff. F1 is the approved protocol exception for agy:gemini-3.8-flash-high: one worker, continuous admission from the approved start until formal coverage completed, and no 08:00 hard cutoff, with completion and safety stopping. The subject configuration, materials, prompts, parsing and ten-hypothesis list remain unchanged; the distinct F1 batch fingerprint is preserved.

**Addendum 1 (2026-10-24, commit `940aee5`).**

- At formal startup on 10-23 00:00, the desktop-installed codex CLI had automatically updated. Version checks refused startup, and no formal codex units ran. The same version, 0.163.0-alpha.10.2, was separately installed through npm that day in a location not updated by the desktop app. The new entry point verifies executable SHA-256 on startup, retaining per-call version checks. Model, reasoning effort, login, isolation options, global `AGENTS.md`, prompts, parsing, inclusion, and retry rules are unchanged. Only version-string equality is claimed, not byte identity with the original executable.
- The preregistered codex fingerprint included the model entry's SHA-256 from `codex debug models`. Snapshots on 10-24 showed the same model entry alternating between two versions within minutes, neither matching the preregistered hash. There were six differences: two plugin/application sections in base instructions; browser/computer confirmation policy; one default-collaboration-mode sentence; context window (500,000 versus 272,000 tokens); and `available_access_programs`. Most concern features disabled through isolation and unused by the task, but the context window differs as well. We did not test effects on answers. The fingerprint was changed to bind executable SHA-256. The complete entry and hash are saved at session start, which identifies only the version observed then, not which version served an individual call. Additional snapshots were scheduled every two hours for 14 days from 10-24.
- Development was fully rerun under the new fingerprint (10-24 14:35–17:14, seven sessions) and accepted using original criteria: 618/618 included, 618 first-attempt parses, 0 missing. The preregistered development set and an interrupted partial rerun remain archived unchanged. Only codex's entry in the analysis freeze changed (executable path/hash, removal of directory-entry hash, fingerprint ID); the other five configurations were unchanged.
- Execution changes without fingerprint effects: sessions stopped solely by inability to connect to OpenAI automatically restart after waits of 5, 10, and 20 minutes, with at most 8 restarts per runner launch and failed units redone. Night jobs no longer open a console window; closing a terminal had interrupted the first formal night on 10-23 at 00:14.

**Addendum 2 (2026-10-29; public commit to be added after release), §4 rules and decisions.** These do not change prompts, parsing, fingerprints, or scoring of completed answers. agy rules run in a separate script before the frozen night queue; fingerprint-bound files are unchanged and every action has an audit record.

1. Another recognized connection-failure message was added to codex automatic continuation (10-25); failed units remain subject to rerun.
2. Initial gpt-oss B710 disposition (decided 10-25, executed 10-26): a unit rejected by provider content-safety filtering three times on each of two nights was administratively marked missing (`manual_disposition`), referencing all six actual attempts without further calls. The same transaction registered two earlier interrupted-session residues as excluded; neither had been included.
3. General content-safety rule (10-26): an agy formal unit stopped after three attempts strictly matching provider content-safety criteria is retried the next night. A second such stop on another night leads to an administrative missing record.
4. gpt-oss B710-specific rule (10-27): all six units disclosing the second outcome were blocked, whereas the other ten were not. Only for this item and configuration, one strictly verified filtering stop suffices for an administrative missing record. On 10-28, a B710 unit with one capacity error (HTTP 503) and two content-safety refusals across three attempts was also assigned missing under this rule, with per-attempt reasons recorded. Units completed before filtering remain included.
5. Setting conflicts (night of 10-25 to 26): agy settings were restored to preregistered baseline before each night, but another project repeatedly added permission rules during execution. Environment checks stopped agy configurations; manual release followed the next day and affected units were redone. Other projects subsequently avoided agy during the night window.
6. Insufficient capacity (from 10-29): stops with three attempts strictly matching HTTP 503, at least 30 minutes since the last attempt, can be automatically released and rerun, at most 2 times per unit and 6 per model per night; beyond these limits, review is required. Stopped sessions remain invalidated.
7. Manual review: other stops (response-check failures, disconnections, environment checks, refused startup) were reviewed and released on 10-23, 24, 25, 26, and 29. Units were redone under unchanged rules, with an audit file for each review.


The completed-cohort dispositions and stage/round counts appear in Tables A1-A2. Missing values remain missing and enter the original complete-subset and worst-case procedures. The post-hoc closure of 359 codex units retains its disclosed inclusion status; it is not reclassified as a preregistered closure.

## Appendix F. Execution-window amendment and full endpoint inventory

The Flash-high identities are retained verbatim:

F0: `a532f2d198d661032c96b98e9eb0c88e15f391400c4e789dc0c8e9f652fe0a11`

F1: `8c35dff8fab0d60b39ee4fba09786f0ddca63c43df1c51a515be07438e434885`

F1 binds a new start boundary, remaining order, inherited development baseline and independent commit receipts. The original agy F0 batches used four workers, the 00:00-07:45 admission window and an 08:00 hard cutoff. F1 is the approved protocol exception for agy:gemini-3.8-flash-high: one worker, continuous admission from the approved start until formal coverage completed, and no 08:00 hard cutoff, with completion and safety stopping. The subject configuration, materials, prompts, parsing and ten-hypothesis list remain unchanged; the distinct F1 batch fingerprint is preserved. Cluster D / w01 spans F0 (7 r0 calls) and F1 (3 r0 calls) across both response formats. There are zero cross-batch r0/r1 repeat pairs: every repeated unit has its r0 and r1 calls in the same batch. Its union with F0 uses the original ten-hypothesis list; no development set or response prompt is changed. The host analysis passed v1 byte reproduction and seven-batch strict admission; this builder does not claim to rerun protected raw admission in the sandbox.

**Table F1. Flash-high primary-call assignment by material condition**

F0 and F1 are non-randomized execution windows confounded with item schedule order and collection time. Differences are exploratory and do not identify a causal execution-window or model effect.

| Batch | Experiment | Condition (frozen cell key) | Units |
| --- | --- | --- | --- |
| F0 | A | ('informative', 'high') | 86 |
| F0 | A | ('informative', 'low') | 86 |
| F0 | A | ('irrelevant', 'high') | 86 |
| F0 | A | ('irrelevant', 'low') | 86 |
| F0 | A | ('none', 'none') | 86 |
| F0 | B | ('F', 1) | 152 |
| F0 | B | ('F', 2) | 152 |
| F0 | B | ('HI', 1) | 152 |
| F0 | B | ('HI', 2) | 152 |
| F0 | B | ('HP', 1) | 152 |
| F0 | B | ('HP', 2) | 152 |
| F0 | B | ('PO', 1) | 152 |
| F0 | B | ('PO', 2) | 152 |
| F0 | C | ('frequency', 1) | 68 |
| F0 | C | ('frequency', 10) | 68 |
| F0 | C | ('frequency', 30) | 68 |
| F0 | C | ('probability', 1) | 68 |
| F0 | C | ('probability', 10) | 68 |
| F0 | C | ('probability', 30) | 68 |
| F0 | D | ('J', 'a') | 59 |
| F0 | D | ('S', 'a') | 60 |
| F0 | D | ('S', 'b') | 59 |
| F0 | D | ('S', 'conj') | 60 |
| F0 | D | ('S', 'disj') | 59 |
| F0 | E | ('default_O',) | 48 |
| F0 | E | ('default_T',) | 48 |
| F0 | E | ('neutral',) | 48 |
| F0 | E | ('recommend_O',) | 48 |
| F0 | E | ('recommend_T',) | 48 |
| F0 | E | ('status_O',) | 48 |
| F0 | E | ('status_T',) | 48 |
| F1 | A | ('informative', 'high') | 14 |
| F1 | A | ('informative', 'low') | 14 |
| F1 | A | ('irrelevant', 'high') | 14 |
| F1 | A | ('irrelevant', 'low') | 14 |
| F1 | A | ('none', 'none') | 14 |
| F1 | B | ('F', 1) | 28 |
| F1 | B | ('F', 2) | 28 |
| F1 | B | ('HI', 1) | 28 |
| F1 | B | ('HI', 2) | 28 |
| F1 | B | ('HP', 1) | 28 |
| F1 | B | ('HP', 2) | 28 |
| F1 | B | ('PO', 1) | 28 |
| F1 | B | ('PO', 2) | 28 |
| F1 | C | ('frequency', 1) | 12 |
| F1 | C | ('frequency', 10) | 12 |
| F1 | C | ('frequency', 30) | 12 |
| F1 | C | ('probability', 1) | 12 |
| F1 | C | ('probability', 10) | 12 |
| F1 | C | ('probability', 30) | 12 |
| F1 | D | ('J', 'a') | 11 |
| F1 | D | ('S', 'a') | 10 |
| F1 | D | ('S', 'b') | 11 |
| F1 | D | ('S', 'conj') | 10 |
| F1 | D | ('S', 'disj') | 11 |
| F1 | E | ('default_O',) | 16 |
| F1 | E | ('default_T',) | 16 |
| F1 | E | ('neutral',) | 16 |
| F1 | E | ('recommend_O',) | 16 |
| F1 | E | ('recommend_T',) | 16 |
| F1 | E | ('status_O',) | 16 |
| F1 | E | ('status_T',) | 16 |

**Table F2. All 120 planned endpoints and development eligibility**

Each endpoint is reported once per configuration. Confirmatory decisions are in H2 only. Development eligibility is separate from formal recommendation-control interpretation caveats. Full exact eligibility reasons and feasible missingness bounds are retained in the audited supplementary JSON.

| Configuration | H | Complete / planned clusters | Estimate [unadjusted 95% CI] | Missing cells | Eligibility |
| --- | --- | --- | --- | --- | --- |
| codex | A1 | 50/50 | -0.030 [-0.156, 0.087] | 0 | dev_diagnostic |
| codex | A2 | 50/50 | 0.459 [0.285, 0.657] | 0 | dev_diagnostic |
| codex | A3 | 49/50 | 0.005 [-0.151, 0.158] | 2 | dev_diagnostic |
| codex | A4 | 49/50 | 0.051 [-0.108, 0.206] | 2 | dev_diagnostic |
| codex | B1 | 90/90 | -2.289 [-3.589, -1.033] | 0 | frozen_confirmatory |
| codex | B2 | 90/90 | 48.256 [44.144, 52.028] | 0 | dev_power |
| codex | B3 | 90/90 | -0.363 [-1.570, 0.797] | 0 | frozen_confirmatory |
| codex | B4 | 90/90 | 0.905 [0.337, 2.013] | 0 | frozen_confirmatory |
| codex | C1 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| codex | C2 | 20/20 | 0.000 [0.000, 0.000] | 0 | dev_diagnostic |
| codex | C3 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| codex | C4 | 20/20 | -0.002 [-0.002, -0.001] | 0 | dev_diagnostic |
| codex | D1 | 20/20 | -1.425 [-3.850, 0.375] | 0 | frozen_confirmatory |
| codex | D2 | 20/20 | 2.458 [1.175, 3.875] | 0 | frozen_confirmatory |
| codex | D3 | 20/20 | -0.741 [-1.708, 0.231] | 0 | frozen_confirmatory |
| codex | D4 | 20/20 | 0.143 [-0.134, 0.446] | 0 | frozen_confirmatory |
| codex | E1 | 32/32 | -0.312 [-0.938, 0.000] | 0 | frozen_confirmatory |
| codex | E2 | 32/32 | 0.000 [0.000, 0.000] | 0 | frozen_confirmatory |
| codex | E3 | 32/32 | -0.383 [-2.086, 1.234] | 0 | frozen_confirmatory |
| codex | E4 | 32/32 | -0.023 [-1.555, 1.523] | 0 | frozen_confirmatory |
| Qwen3 | A1 | 50/50 | 0.946 [-0.231, 2.231] | 0 | descriptive_only |
| Qwen3 | A2 | 50/50 | -1.316 [-2.827, 0.060] | 0 | descriptive_only |
| Qwen3 | A3 | 50/50 | -0.608 [-1.955, 0.723] | 0 | descriptive_only |
| Qwen3 | A4 | 50/50 | 1.576 [-0.114, 3.309] | 0 | descriptive_only |
| Qwen3 | B1 | 90/90 | -7.751 [-12.228, -3.201] | 0 | descriptive_only |
| Qwen3 | B2 | 90/90 | 54.128 [49.861, 58.583] | 0 | descriptive_only |
| Qwen3 | B3 | 90/90 | 5.721 [0.677, 10.757] | 0 | descriptive_only |
| Qwen3 | B4 | 90/90 | 19.053 [15.600, 22.624] | 0 | descriptive_only |
| Qwen3 | C1 | 20/20 | -0.002 [-0.003, -0.000] | 0 | descriptive_only |
| Qwen3 | C2 | 19/20 | -0.001 [-0.003, -0.000] | 1 | descriptive_only |
| Qwen3 | C3 | 20/20 | -0.012 [-0.017, -0.008] | 0 | descriptive_only |
| Qwen3 | C4 | 20/20 | 0.647 [0.537, 0.761] | 0 | descriptive_only |
| Qwen3 | D1 | 20/20 | 13.025 [8.000, 19.075] | 0 | descriptive_only |
| Qwen3 | D2 | 20/20 | 15.775 [9.400, 22.900] | 0 | descriptive_only |
| Qwen3 | D3 | 20/20 | -4.613 [-12.936, 3.610] | 0 | descriptive_only |
| Qwen3 | D4 | 20/20 | -2.583 [-5.984, 0.726] | 0 | descriptive_only |
| Qwen3 | E1 | 32/32 | -1.648 [-9.719, 6.562] | 0 | descriptive_only |
| Qwen3 | E2 | 32/32 | -0.532 [-8.913, 6.589] | 0 | descriptive_only |
| Qwen3 | E3 | 31/32 | 4.042 [-5.568, 14.325] | 2 | descriptive_only |
| Qwen3 | E4 | 29/32 | 5.659 [-4.104, 15.685] | 3 | descriptive_only |
| Sonnet 5.5 | A1 | 50/50 | 0.019 [-0.069, 0.098] | 0 | frozen_confirmatory |
| Sonnet 5.5 | A2 | 50/50 | 0.471 [0.340, 0.606] | 0 | dev_power |
| Sonnet 5.5 | A3 | 50/50 | -0.057 [-0.187, 0.049] | 0 | frozen_confirmatory |
| Sonnet 5.5 | A4 | 50/50 | 0.131 [-0.044, 0.365] | 0 | dev_power |
| Sonnet 5.5 | B1 | 90/90 | -3.169 [-4.772, -1.633] | 0 | frozen_confirmatory |
| Sonnet 5.5 | B2 | 90/90 | 3.931 [1.678, 6.344] | 0 | frozen_confirmatory |
| Sonnet 5.5 | B3 | 90/90 | 1.750 [0.613, 2.836] | 0 | frozen_confirmatory |
| Sonnet 5.5 | B4 | 90/90 | -4.193 [-6.646, -1.792] | 0 | frozen_confirmatory |
| Sonnet 5.5 | C1 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| Sonnet 5.5 | C2 | 20/20 | 0.000 [0.000, 0.000] | 0 | dev_diagnostic |
| Sonnet 5.5 | C3 | 20/20 | -0.061 [-0.069, -0.053] | 0 | dev_diagnostic |
| Sonnet 5.5 | C4 | 20/20 | 1.006 [0.888, 1.121] | 0 | dev_diagnostic |
| Sonnet 5.5 | D1 | 20/20 | -1.480 [-3.730, 0.080] | 0 | frozen_confirmatory |
| Sonnet 5.5 | D2 | 20/20 | 2.300 [1.305, 3.490] | 0 | frozen_confirmatory |
| Sonnet 5.5 | D3 | 20/20 | -0.417 [-1.560, 0.508] | 0 | frozen_confirmatory |
| Sonnet 5.5 | D4 | 20/20 | -0.095 [-0.439, 0.211] | 0 | frozen_confirmatory |
| Sonnet 5.5 | E1 | 32/32 | 0.344 [-1.250, 1.844] | 0 | dev_power |
| Sonnet 5.5 | E2 | 32/32 | -1.406 [-3.125, 0.219] | 0 | frozen_confirmatory |
| Sonnet 5.5 | E3 | 32/32 | -0.298 [-3.066, 2.423] | 0 | dev_power |
| Sonnet 5.5 | E4 | 32/32 | 0.389 [-2.530, 3.095] | 0 | frozen_confirmatory |
| gpt-oss-120b | A1 | 50/50 | 0.039 [-0.944, 0.978] | 0 | frozen_confirmatory |
| gpt-oss-120b | A2 | 50/50 | -0.040 [-1.288, 1.099] | 0 | dev_power |
| gpt-oss-120b | A3 | 50/50 | 0.158 [-0.777, 1.133] | 0 | dev_power |
| gpt-oss-120b | A4 | 49/50 | 0.147 [-1.068, 1.473] | 1 | dev_power |
| gpt-oss-120b | B1 | 89/90 | 0.028 [-2.764, 2.837] | 1 | dev_power |
| gpt-oss-120b | B2 | 89/90 | 49.612 [46.197, 52.988] | 2 | dev_power |
| gpt-oss-120b | B3 | 89/90 | 6.143 [3.198, 9.236] | 2 | dev_power |
| gpt-oss-120b | B4 | 89/90 | 10.679 [7.607, 13.805] | 2 | frozen_confirmatory |
| gpt-oss-120b | C1 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| gpt-oss-120b | C2 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| gpt-oss-120b | C3 | 20/20 | -0.003 [-0.005, -0.000] | 0 | dev_diagnostic |
| gpt-oss-120b | C4 | 20/20 | 0.191 [0.155, 0.231] | 0 | dev_diagnostic |
| gpt-oss-120b | D1 | 20/20 | 9.600 [3.200, 17.100] | 0 | dev_power |
| gpt-oss-120b | D2 | 20/20 | 17.350 [9.750, 25.550] | 0 | dev_power |
| gpt-oss-120b | D3 | 20/20 | -2.695 [-10.673, 4.297] | 0 | dev_power |
| gpt-oss-120b | D4 | 20/20 | -1.963 [-4.289, 0.402] | 0 | dev_power |
| gpt-oss-120b | E1 | 32/32 | -1.133 [-7.561, 5.484] | 0 | dev_power |
| gpt-oss-120b | E2 | 32/32 | 1.478 [-3.219, 6.572] | 0 | frozen_confirmatory |
| gpt-oss-120b | E3 | 32/32 | 5.121 [-2.083, 12.396] | 0 | dev_power |
| gpt-oss-120b | E4 | 32/32 | 3.144 [-2.042, 8.020] | 0 | dev_power |
| Flash low | A1 | 50/50 | 0.042 [-0.047, 0.183] | 0 | dev_diagnostic |
| Flash low | A2 | 50/50 | 0.179 [0.042, 0.310] | 0 | dev_diagnostic |
| Flash low | A3 | 50/50 | 0.038 [-0.036, 0.145] | 0 | dev_diagnostic |
| Flash low | A4 | 50/50 | -0.018 [-0.208, 0.178] | 0 | dev_diagnostic |
| Flash low | B1 | 90/90 | -1.939 [-3.973, 0.022] | 0 | frozen_confirmatory |
| Flash low | B2 | 90/90 | 10.967 [7.222, 14.844] | 0 | dev_power |
| Flash low | B3 | 89/90 | 1.643 [0.410, 2.943] | 1 | frozen_confirmatory |
| Flash low | B4 | 90/90 | 2.520 [-0.513, 5.570] | 0 | frozen_confirmatory |
| Flash low | C1 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| Flash low | C2 | 20/20 | 0.000 [0.000, 0.000] | 0 | dev_diagnostic |
| Flash low | C3 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| Flash low | C4 | 20/20 | 0.005 [0.003, 0.007] | 0 | dev_diagnostic |
| Flash low | D1 | 20/20 | 0.085 [-1.015, 1.495] | 0 | frozen_confirmatory |
| Flash low | D2 | 20/20 | 3.373 [1.137, 6.130] | 0 | frozen_confirmatory |
| Flash low | D3 | 20/20 | 0.487 [-1.654, 2.775] | 0 | frozen_confirmatory |
| Flash low | D4 | 20/20 | -0.167 [-0.772, 0.355] | 0 | frozen_confirmatory |
| Flash low | E1 | 32/32 | -0.531 [-1.625, 0.188] | 0 | frozen_confirmatory |
| Flash low | E2 | 32/32 | 0.000 [0.000, 0.000] | 0 | frozen_confirmatory |
| Flash low | E3 | 32/32 | -0.731 [-2.833, 1.519] | 0 | dev_power |
| Flash low | E4 | 32/32 | 1.645 [-0.183, 3.558] | 0 | fingerprint_preservation_exception |
| Flash high | A1 | 50/50 | 0.034 [0.006, 0.072] | 0 | dev_diagnostic |
| Flash high | A2 | 50/50 | -0.026 [-0.241, 0.123] | 0 | dev_diagnostic |
| Flash high | A3 | 50/50 | -0.048 [-0.103, -0.003] | 0 | dev_diagnostic |
| Flash high | A4 | 50/50 | 0.197 [0.034, 0.458] | 0 | dev_diagnostic |
| Flash high | B1 | 90/90 | -3.972 [-5.983, -2.122] | 0 | frozen_confirmatory |
| Flash high | B2 | 90/90 | 0.850 [0.044, 1.761] | 0 | frozen_confirmatory |
| Flash high | B3 | 89/90 | 4.526 [3.036, 6.125] | 1 | frozen_confirmatory |
| Flash high | B4 | 90/90 | 1.403 [-1.909, 4.820] | 0 | dev_power |
| Flash high | C1 | 20/20 | -0.000 [-0.000, -0.000] | 0 | dev_diagnostic |
| Flash high | C2 | 20/20 | 0.000 [0.000, 0.000] | 0 | dev_diagnostic |
| Flash high | C3 | 20/20 | 0.000 [-0.000, 0.000] | 0 | dev_diagnostic |
| Flash high | C4 | 20/20 | 0.005 [0.003, 0.010] | 0 | dev_diagnostic |
| Flash high | D1 | 20/20 | -1.115 [-2.115, -0.215] | 0 | frozen_confirmatory |
| Flash high | D2 | 20/20 | 3.335 [1.245, 5.865] | 0 | frozen_confirmatory |
| Flash high | D3 | 20/20 | 0.979 [-0.727, 2.689] | 0 | frozen_confirmatory |
| Flash high | D4 | 20/20 | 0.758 [-0.169, 2.001] | 0 | frozen_confirmatory |
| Flash high | E1 | 32/32 | 0.625 [0.000, 1.875] | 0 | frozen_confirmatory |
| Flash high | E2 | 32/32 | 0.000 [0.000, 0.000] | 0 | frozen_confirmatory |
| Flash high | E3 | 32/32 | -2.188 [-4.438, 0.075] | 0 | fingerprint_preservation_exception |
| Flash high | E4 | 32/32 | 0.142 [-1.577, 1.897] | 0 | frozen_confirmatory |

## Appendix G. Exploratory candidate-spread analyses

**Table G1. Exploratory weighted candidate-spread distributions**

A spread is measured on the log scale; B-E in probability points. D joint spread averages conjunction and B component spreads, not all four statements. D valid counts refer to calls. Full distributions by condition: supplement-v2/g2-spread-by-condition.csv (198 rows). Item pairing counts: supplement-v2/g3-paired-cell-counts.csv (1,482 rows). These v2 CSVs are delivered locally, not claimed to be live on GitHub.

| Configuration | Exp | Planned multi calls | Valid | Skipped | Unpaired | Q1 | Median | Q3 | Zero fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codex | A | 250 | 247 | 3 | 0 | 0.0096 | 0.0522 | 0.1455 | 0.000 |
| codex | B | 720 | 720 | 0 | 0 | 0.9581 | 6.9417 | 10.9545 | 0.075 |
| codex | C | 240 | 240 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | 1.000 |
| codex | D | 175 | 175 | 0 | 0 | 1.5945 | 6.0696 | 10.9545 | 0.000 |
| codex | E | 224 | 224 | 0 | 0 | 10.9545 | 11.1523 | 15.0831 | 0.000 |
| Sonnet 5.5 | A | 250 | 250 | 0 | 0 | 0.0503 | 0.1418 | 0.2400 | 0.000 |
| Sonnet 5.5 | B | 720 | 720 | 0 | 0 | 3.5163 | 6.2639 | 10.0369 | 0.000 |
| Sonnet 5.5 | C | 240 | 240 | 0 | 0 | 1.6325 | 6.5819 | 11.2777 | 0.000 |
| Sonnet 5.5 | D | 175 | 175 | 0 | 0 | 1.3434 | 3.4825 | 7.4795 | 0.000 |
| Sonnet 5.5 | E | 224 | 224 | 0 | 0 | 8.5398 | 9.7559 | 11.5814 | 0.000 |
| Qwen3 | A | 250 | 250 | 0 | 0 | 0.0429 | 0.0922 | 0.2110 | 0.000 |
| Qwen3 | B | 720 | 720 | 0 | 0 | 6.6144 | 11.2823 | 20.5183 | 0.074 |
| Qwen3 | C | 240 | 240 | 0 | 1 | 1.6926 | 2.7436 | 4.4615 | 0.004 |
| Qwen3 | D | 175 | 175 | 0 | 0 | 4.9686 | 7.2647 | 12.7720 | 0.000 |
| Qwen3 | E | 224 | 218 | 6 | 0 | 11.5293 | 13.9272 | 17.6014 | 0.000 |
| gpt-oss-120b | A | 250 | 248 | 2 | 0 | 0.0213 | 0.0680 | 0.1551 | 0.000 |
| gpt-oss-120b | B | 720 | 717 | 3 | 0 | 6.5990 | 11.9478 | 20.2037 | 0.006 |
| gpt-oss-120b | C | 240 | 240 | 0 | 0 | 0.8700 | 1.8166 | 2.4150 | 0.000 |
| gpt-oss-120b | D | 175 | 175 | 0 | 0 | 5.2180 | 8.7006 | 13.7148 | 0.000 |
| gpt-oss-120b | E | 224 | 224 | 0 | 0 | 12.8774 | 16.8300 | 19.3200 | 0.000 |
| Flash low | A | 250 | 250 | 0 | 0 | 0.0067 | 0.0465 | 0.1140 | 0.000 |
| Flash low | B | 720 | 719 | 1 | 0 | 2.7383 | 6.4177 | 10.6946 | 0.000 |
| Flash low | C | 240 | 240 | 0 | 0 | 0.0616 | 0.1101 | 0.1581 | 0.000 |
| Flash low | D | 175 | 175 | 0 | 0 | 1.8731 | 4.0924 | 8.5474 | 0.000 |
| Flash low | E | 224 | 224 | 0 | 0 | 8.0612 | 10.2956 | 11.6619 | 0.000 |
| Flash high | A | 250 | 250 | 0 | 0 | 0.0061 | 0.0367 | 0.1173 | 0.000 |
| Flash high | B | 720 | 719 | 1 | 0 | 4.6503 | 7.2902 | 11.3908 | 0.000 |
| Flash high | C | 240 | 240 | 0 | 0 | 0.0454 | 0.1096 | 0.1615 | 0.000 |
| Flash high | D | 175 | 175 | 0 | 0 | 1.8654 | 4.4272 | 8.6493 | 0.000 |
| Flash high | E | 224 | 224 | 0 | 0 | 9.1864 | 11.1692 | 13.0118 | 0.000 |


## Appendix H. Complete six-configuration overview tables

**Table H1. Development acceptance and frozen configuration-specific gates**

All six configurations triggered the C ceiling (48/48 development direct cells within one point). A known truth uses 20 unanchored estimates. No D floor gate triggered. Low E4 (39 required items) and high E3 (36) were downgraded rather than expanding 32 formal E items and invalidating development fingerprints. Qwen3 was retained as a descriptive benchmark by decision, with no confirmatory tests.

| Configuration | First parses / 618 | Missing | A known truth | Forwarded | Hypotheses | Downgrade categories |
| --- | --- | --- | --- | --- | --- | --- |
| codex | 618 | 0 | 80% | 11 | B1 B3 B4 D1 D2 D3 D4 E1 E2 E3 E4 | dev_diagnostic: 8; dev_power: 1 |
| Sonnet 5.5 | 617 | 0 | 70% | 12 | A1 A3 B1 B2 B3 B4 D1 D2 D3 D4 E2 E4 | dev_power: 4; dev_diagnostic: 4 |
| Qwen3 | 610 | 1 | 15% | 0 | descriptive only | descriptive_only: 20 |
| gpt-oss-120b | 612 | 0 | 40% | 3 | A1 B4 E2 | dev_power: 13; dev_diagnostic: 4 |
| Flash low | 617 | 0 | 85% | 9 | B1 B3 B4 D1 D2 D3 D4 E1 E2 | dev_diagnostic: 8; dev_power: 2; fingerprint_preservation_exception: 1 |
| Flash high | 616 | 0 | 80% | 10 | B1 B2 B3 D1 D2 D3 D4 E1 E2 E4 | dev_diagnostic: 8; dev_power: 1; fingerprint_preservation_exception: 1 |

**Table H2. All 45 frozen confirmatory tests and missingness protection**

One-sided unbounded endpoints are printed as unbounded. These are per-family Holm-step intervals, not fixed 95% simultaneous intervals. Worst-case rows are shown whenever a family required protection. Complete-case rejected flags are preserved separately from the final directional decision. A uses AI units (SESOI 0.10), others 5 pp.

| Configuration | H | Analysis | Estimate [adjusted bound / CI] | Clusters | p / Holm alpha | Rejected | Final status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| codex | B1 | complete | -2.289 [-3.389, unbounded] | 90 | 0.9998 / 0.0500 | False | not retained |
| codex | B3 | complete | -0.363 [-1.749, 0.931] | 90 | 0.5512 / 0.0250 | False | not retained |
| codex | B4 | complete | 0.905 [0.328, 2.538] | 90 | <.001 / 0.0167 | True | retained directional |
| codex | D1 | complete | -1.425 [-3.400, unbounded] | 20 | 0.9248 / 0.0500 | False | not retained |
| codex | D2 | complete | 2.458 [1.015, unbounded] | 20 | <.001 / 0.0125 | True | retained directional |
| codex | D3 | complete | -0.741 [-1.894, 0.457] | 20 | 0.1344 / 0.0167 | False | not retained |
| codex | D4 | complete | 0.143 [-0.172, 0.497] | 20 | 0.3352 / 0.0250 | False | not retained |
| codex | E1 | complete | -0.312 [-1.250, 0.000] | 32 | 0.7008 / 0.0167 | False | not retained |
| codex | E2 | complete | 0.000 [0.000, 0.000] | 32 | 1.0000 / 0.0500 | False | not retained |
| codex | E3 | complete | -0.383 [-2.578, 1.617] | 32 | 0.6748 / 0.0125 | False | not retained |
| codex | E4 | complete | -0.023 [-1.758, 1.773] | 32 | 0.9564 / 0.0250 | False | not retained |
| Sonnet 5.5 | A1 | complete | 0.019 [-0.069, unbounded] | 50 | 0.3192 / 0.0250 | False | not retained |
| Sonnet 5.5 | A3 | complete | -0.057 [-0.187, 0.049] | 50 | 0.3260 / 0.0500 | False | not retained |
| Sonnet 5.5 | B1 | complete | -3.169 [-4.497, unbounded] | 90 | 1.0000 / 0.0500 | False | not retained |
| Sonnet 5.5 | B2 | complete | 3.931 [1.497, unbounded] | 90 | <.001 / 0.0167 | True | retained directional |
| Sonnet 5.5 | B3 | complete | 1.750 [0.479, 2.996] | 90 | <.001 / 0.0250 | True | retained directional |
| Sonnet 5.5 | B4 | complete | -4.193 [-7.350, -1.081] | 90 | <.001 / 0.0125 | True | retained directional |
| Sonnet 5.5 | D1 | complete | -1.480 [-3.365, unbounded] | 20 | 0.9628 / 0.0500 | False | not retained |
| Sonnet 5.5 | D2 | complete | 2.300 [1.235, unbounded] | 20 | <.001 / 0.0125 | True | retained directional |
| Sonnet 5.5 | D3 | complete | -0.417 [-1.810, 0.660] | 20 | 0.4768 / 0.0167 | False | not retained |
| Sonnet 5.5 | D4 | complete | -0.095 [-0.500, 0.242] | 20 | 0.5724 / 0.0250 | False | not retained |
| Sonnet 5.5 | E2 | complete | -1.406 [-3.375, 0.469] | 32 | 0.0988 / 0.0250 | False | not retained |
| Sonnet 5.5 | E4 | complete | 0.389 [-2.530, 3.095] | 32 | 0.7768 / 0.0500 | False | not retained |
| gpt-oss-120b | A1 | complete | 0.039 [-0.704, unbounded] | 50 | 0.4374 / 0.0500 | False | not retained |
| gpt-oss-120b | B4 | complete | 10.679 [7.607, 13.805] | 89 | <.001 / 0.0500 | True | bound exceeds SESOI |
| gpt-oss-120b | B4 | worst-case | 10.035 [6.785, 14.320] | 90 | <.001 / 0.0500 | True | protected=True |
| gpt-oss-120b | E2 | complete | 1.478 [-3.219, 6.572] | 32 | 0.5748 / 0.0500 | False | not retained |
| Flash low | B1 | complete | -1.939 [-3.668, unbounded] | 90 | 0.9738 / 0.0500 | False | not retained |
| Flash low | B1 | worst-case | -1.939 [-3.668, unbounded] | 90 | 0.9738 / 0.0500 | False | protected=False |
| Flash low | B3 | complete | 1.643 [0.094, 3.243] | 89 | 0.0108 / 0.0167 | True | not retained |
| Flash low | B3 | worst-case | 1.141 [-0.792, 3.182] | 90 | 0.1724 / 0.0250 | False | protected=False |
| Flash low | B4 | complete | 2.520 [-0.810, 6.058] | 90 | 0.0996 / 0.0250 | False | not retained |
| Flash low | B4 | worst-case | 2.520 [-1.080, 6.341] | 90 | 0.0996 / 0.0167 | False | protected=False |
| Flash low | D1 | complete | 0.085 [-1.100, unbounded] | 20 | 0.4782 / 0.0167 | False | not retained |
| Flash low | D2 | complete | 3.373 [0.847, unbounded] | 20 | <.001 / 0.0125 | True | retained directional |
| Flash low | D3 | complete | 0.487 [-1.654, 2.775] | 20 | 0.6724 / 0.0500 | False | not retained |
| Flash low | D4 | complete | -0.167 [-0.868, 0.420] | 20 | 0.5892 / 0.0250 | False | not retained |
| Flash low | E1 | complete | -0.531 [-1.875, 0.188] | 32 | 0.3132 / 0.0250 | False | not retained |
| Flash low | E2 | complete | 0.000 [0.000, 0.000] | 32 | 1.0000 / 0.0500 | False | not retained |
| Flash high | B1 | complete | -3.972 [-5.639, unbounded] | 90 | 1.0000 / 0.0500 | False | not retained |
| Flash high | B1 | worst-case | -3.972 [-5.639, unbounded] | 90 | 1.0000 / 0.0500 | False | protected=False |
| Flash high | B2 | complete | 0.850 [0.044, unbounded] | 90 | 0.0196 / 0.0250 | True | retained directional |
| Flash high | B2 | worst-case | 0.850 [0.044, unbounded] | 90 | 0.0196 / 0.0250 | True | protected=True |
| Flash high | B3 | complete | 4.526 [2.762, 6.453] | 89 | <.001 / 0.0167 | True | retained directional |
| Flash high | B3 | worst-case | 4.114 [1.982, 6.584] | 90 | <.001 / 0.0167 | True | protected=True |
| Flash high | D1 | complete | -1.115 [-1.950, unbounded] | 20 | 0.9942 / 0.0500 | False | not retained |
| Flash high | D2 | complete | 3.335 [1.075, unbounded] | 20 | <.001 / 0.0125 | True | retained directional |
| Flash high | D3 | complete | 0.979 [-0.996, 2.891] | 20 | 0.2628 / 0.0250 | False | not retained |
| Flash high | D4 | complete | 0.758 [-0.294, 2.302] | 20 | 0.1544 / 0.0167 | False | not retained |
| Flash high | E1 | complete | 0.625 [0.000, 2.500] | 32 | 0.7184 / 0.0167 | False | not retained |
| Flash high | E2 | complete | 0.000 [0.000, 0.000] | 32 | 1.0000 / 0.0500 | False | not retained |
| Flash high | E4 | complete | 0.142 [-1.844, 2.092] | 32 | 0.8348 / 0.0250 | False | not retained |

**Table H3. A, B, C descriptive summaries across six configurations**

Unadjusted descriptive cluster-bootstrap intervals; complete paired subsets can differ from single-format endpoint denominators. Supplemental B2 is HP minus HI; C1 is 1 minus direct probability slope; C2 is direct frequency minus probability slope; neither is itself a direct probability slope. Supplemental endpoints remain descriptive when outside the frozen list.

| Configuration | Quantity | Direct / endpoint [95% CI] | Multi-estimate [95% CI] | Multi minus direct [95% CI] | Paired clusters |
| --- | --- | --- | --- | --- | --- |
| codex | A AI_irrelevant | -0.0302 [-0.1487, 0.0887] | -0.0252 [-0.1100, 0.0511] | 0.0051 [-0.1535, 0.1553] | 49 |
| codex | A AI_informative | 0.4291 [0.3012, 0.5552] | 0.4845 [0.3591, 0.6066] | 0.0554 [0.0173, 0.1016] | 50 |
| codex | A S | 0.4680 [0.2886, 0.6508] | 0.5193 [0.3683, 0.6758] | 0.0512 [-0.1034, 0.2102] | 49 |
| codex | B b | -2.2889 [-3.5889, -1.0333] | -2.6514 [-3.9655, -1.4595] | -0.3626 [-1.5705, 0.7967] | 90 |
| codex | B e_PO | 0.0000 [0.0000, 0.0000] | 0.9054 [0.3369, 2.0125] | 0.9054 [0.3369, 2.0125] | 90 |
| codex | C probability | 1.0000 [1.0000, 1.0001] | 1.0000 [1.0000, 1.0000] | -0.0001 [-0.0001, -0.0000] | 20 |
| codex | C frequency | 1.0001 [1.0001, 1.0001] | 1.0000 [1.0000, 1.0000] | -0.0001 [-0.0001, -0.0001] | 20 |
| codex | C error | 0.0017 [0.0016, 0.0018] | 0.0002 [0.0001, 0.0003] | -0.0016 [-0.0017, -0.0014] | 20 |
| codex | B2 supplemental endpoint | 48.2556 [44.1444, 52.0278] | not a format mean | see endpoint definition | 90 |
| codex | C1 supplemental endpoint | -0.0000 [-0.0001, -0.0000] | not a format mean | see endpoint definition | 20 |
| codex | C2 supplemental endpoint | 0.0000 [0.0000, 0.0000] | not a format mean | see endpoint definition | 20 |
| Sonnet 5.5 | A AI_irrelevant | 0.0185 [-0.0663, 0.0970] | -0.0383 [-0.1460, 0.0464] | -0.0568 [-0.1857, 0.0501] | 50 |
| Sonnet 5.5 | A AI_informative | 0.4899 [0.3788, 0.6015] | 0.5641 [0.3982, 0.8048] | 0.0742 [-0.0716, 0.3065] | 50 |
| Sonnet 5.5 | A S | 0.4714 [0.3408, 0.6094] | 0.6024 [0.4069, 0.8564] | 0.1309 [-0.0491, 0.3761] | 50 |
| Sonnet 5.5 | B b | -3.1694 [-4.7722, -1.6333] | -1.4199 [-2.7041, -0.2263] | 1.7496 [0.6135, 2.8356] | 90 |
| Sonnet 5.5 | B e_PO | 24.9333 [20.8667, 29.1889] | 20.7408 [17.1964, 24.5289] | -4.1926 [-6.6464, -1.7923] | 90 |
| Sonnet 5.5 | C probability | 1.0001 [1.0000, 1.0001] | 0.9392 [0.9309, 0.9473] | -0.0609 [-0.0691, -0.0527] | 20 |
| Sonnet 5.5 | C frequency | 1.0001 [1.0001, 1.0001] | 0.9434 [0.9367, 0.9511] | -0.0567 [-0.0634, -0.0490] | 20 |
| Sonnet 5.5 | C error | 0.0024 [0.0021, 0.0027] | 1.0082 [0.8906, 1.1242] | 1.0058 [0.8882, 1.1214] | 20 |
| Sonnet 5.5 | B2 supplemental endpoint | 3.9306 [1.6778, 6.3444] | not a format mean | see endpoint definition | 90 |
| Sonnet 5.5 | C1 supplemental endpoint | -0.0001 [-0.0001, -0.0000] | not a format mean | see endpoint definition | 20 |
| Sonnet 5.5 | C2 supplemental endpoint | 0.0000 [0.0000, 0.0001] | not a format mean | see endpoint definition | 20 |
| Qwen3 | A AI_irrelevant | 0.9456 [-0.1951, 2.2417] | 0.3377 [-0.1843, 1.0605] | -0.6079 [-1.9899, 0.7651] | 50 |
| Qwen3 | A AI_informative | -0.3706 [-1.4018, 0.4421] | 0.5976 [0.3781, 0.8066] | 0.9682 [0.1846, 1.9290] | 50 |
| Qwen3 | A S | -1.3162 [-2.8477, 0.0430] | 0.2599 [-0.5114, 0.8378] | 1.5761 [-0.1316, 3.3604] | 50 |
| Qwen3 | B b | -7.7506 [-12.2283, -3.2011] | -2.0294 [-5.3361, 1.2062] | 5.7212 [0.6766, 10.7569] | 90 |
| Qwen3 | B e_PO | 6.0389 [3.7056, 8.8111] | 25.0916 [21.8431, 28.4780] | 19.0527 [15.6001, 22.6239] | 90 |
| Qwen3 | C probability | 1.0017 [1.0005, 1.0030] | 0.9894 [0.9847, 0.9939] | -0.0123 [-0.0171, -0.0076] | 20 |
| Qwen3 | C frequency | 1.0004 [0.9993, 1.0017] | 0.9883 [0.9853, 0.9911] | -0.0121 [-0.0152, -0.0092] | 19 |
| Qwen3 | C error | 0.0220 [0.0110, 0.0337] | 0.6693 [0.5572, 0.7843] | 0.6473 [0.5373, 0.7611] | 20 |
| Qwen3 | B2 supplemental endpoint | 54.1278 [49.8611, 58.5833] | not a format mean | see endpoint definition | 90 |
| Qwen3 | C1 supplemental endpoint | -0.0017 [-0.0030, -0.0005] | not a format mean | see endpoint definition | 20 |
| Qwen3 | C2 supplemental endpoint | -0.0013 [-0.0027, -0.0000] | not a format mean | see endpoint definition | 19 |
| gpt-oss-120b | A AI_irrelevant | 0.0392 [-0.9207, 0.9738] | 0.1968 [0.0334, 0.4177] | 0.1576 [-0.7893, 1.0983] | 50 |
| gpt-oss-120b | A AI_informative | -0.0168 [-0.8497, 0.4916] | 0.2807 [0.1285, 0.4300] | 0.2975 [-0.2785, 1.1478] | 49 |
| gpt-oss-120b | A S | -0.0539 [-1.2572, 1.1360] | 0.0927 [-0.2274, 0.3226] | 0.1466 [-1.1240, 1.4502] | 49 |
| gpt-oss-120b | B b | 0.0281 [-2.7640, 2.8371] | 6.1715 [3.5615, 8.7524] | 6.1434 [3.1982, 9.2360] | 89 |
| gpt-oss-120b | B e_PO | 7.2433 [4.5579, 10.3933] | 17.9221 [15.2253, 20.6850] | 10.6788 [7.6066, 13.8052] | 89 |
| gpt-oss-120b | C probability | 1.0001 [1.0001, 1.0002] | 0.9976 [0.9952, 0.9997] | -0.0026 [-0.0049, -0.0005] | 20 |
| gpt-oss-120b | C frequency | 1.0001 [1.0001, 1.0001] | 0.9985 [0.9956, 1.0009] | -0.0016 [-0.0044, 0.0008] | 20 |
| gpt-oss-120b | C error | 0.0030 [0.0026, 0.0033] | 0.1936 [0.1584, 0.2346] | 0.1906 [0.1554, 0.2315] | 20 |
| gpt-oss-120b | B2 supplemental endpoint | 49.6118 [46.1966, 52.9882] | not a format mean | see endpoint definition | 89 |
| gpt-oss-120b | C1 supplemental endpoint | -0.0001 [-0.0002, -0.0001] | not a format mean | see endpoint definition | 20 |
| gpt-oss-120b | C2 supplemental endpoint | -0.0001 [-0.0001, -0.0000] | not a format mean | see endpoint definition | 20 |
| Flash low | A AI_irrelevant | 0.0416 [-0.0479, 0.1867] | 0.0796 [-0.0384, 0.2330] | 0.0380 [-0.0359, 0.1452] | 50 |
| Flash low | A AI_informative | 0.2208 [0.1281, 0.3230] | 0.2411 [0.1047, 0.4118] | 0.0203 [-0.1265, 0.1891] | 50 |
| Flash low | A S | 0.1792 [0.0385, 0.3094] | 0.1614 [-0.0215, 0.3537] | -0.0177 [-0.2067, 0.1799] | 50 |
| Flash low | B b | -1.9612 [-4.0393, -0.0393] | -0.3180 [-2.2554, 1.5576] | 1.6432 [0.4099, 2.9430] | 89 |
| Flash low | B e_PO | 6.1944 [3.1389, 9.6389] | 8.7143 [5.5196, 12.1089] | 2.5199 [-0.5135, 5.5701] | 90 |
| Flash low | C probability | 1.0001 [1.0001, 1.0001] | 0.9999 [0.9998, 1.0000] | -0.0001 [-0.0003, -0.0001] | 20 |
| Flash low | C frequency | 1.0001 [1.0001, 1.0001] | 1.0001 [1.0000, 1.0001] | 0.0000 [-0.0000, 0.0001] | 20 |
| Flash low | C error | 0.0018 [0.0018, 0.0018] | 0.0064 [0.0047, 0.0087] | 0.0046 [0.0029, 0.0069] | 20 |
| Flash low | B2 supplemental endpoint | 10.9667 [7.2222, 14.8444] | not a format mean | see endpoint definition | 90 |
| Flash low | C1 supplemental endpoint | -0.0001 [-0.0001, -0.0001] | not a format mean | see endpoint definition | 20 |
| Flash low | C2 supplemental endpoint | 0.0000 [0.0000, 0.0000] | not a format mean | see endpoint definition | 20 |
| Flash high | A AI_irrelevant | 0.0344 [0.0058, 0.0724] | -0.0131 [-0.0545, 0.0247] | -0.0475 [-0.1066, -0.0024] | 50 |
| Flash high | A AI_informative | 0.0085 [-0.2115, 0.1641] | 0.1579 [0.0751, 0.2505] | 0.1494 [0.0082, 0.3948] | 50 |
| Flash high | A S | -0.0259 [-0.2456, 0.1243] | 0.1710 [0.0743, 0.2822] | 0.1969 [0.0305, 0.4770] | 50 |
| Flash high | B b | -3.9888 [-5.9719, -2.1573] | 0.5376 [-0.9949, 2.0855] | 4.5263 [3.0365, 6.1252] | 89 |
| Flash high | B e_PO | 24.3056 [19.3889, 29.2222] | 25.7084 [21.8358, 29.5567] | 1.4029 [-1.9089, 4.8196] | 90 |
| Flash high | C probability | 1.0001 [1.0001, 1.0001] | 1.0001 [1.0000, 1.0002] | 0.0001 [-0.0000, 0.0002] | 20 |
| Flash high | C frequency | 1.0001 [1.0001, 1.0001] | 1.0001 [1.0000, 1.0002] | 0.0000 [-0.0001, 0.0001] | 20 |
| Flash high | C error | 0.0018 [0.0018, 0.0018] | 0.0072 [0.0046, 0.0114] | 0.0054 [0.0028, 0.0096] | 20 |
| Flash high | B2 supplemental endpoint | 0.8500 [0.0444, 1.7611] | not a format mean | see endpoint definition | 90 |
| Flash high | C1 supplemental endpoint | -0.0001 [-0.0001, -0.0001] | not a format mean | see endpoint definition | 20 |
| Flash high | C2 supplemental endpoint | 0.0000 [0.0000, 0.0000] | not a format mean | see endpoint definition | 20 |

**Table H4. D, E descriptive summaries across six configurations**

Unadjusted descriptive cluster-bootstrap intervals; complete paired subsets can differ from single-format endpoint denominators. Supplemental B2 is HP minus HI; C1 is 1 minus direct probability slope; C2 is direct frequency minus probability slope; neither is itself a direct probability slope. Supplemental endpoints remain descriptive when outside the frozen list.

| Configuration | Quantity | Direct / endpoint [95% CI] | Multi-estimate [95% CI] | Multi minus direct [95% CI] | Paired clusters |
| --- | --- | --- | --- | --- | --- |
| codex | D delta_S | -1.4250 [-3.8500, 0.3750] | -2.1658 [-4.3306, -0.3609] | -0.7409 [-1.7079, 0.2306] | 20 |
| codex | D delta_J | -3.8825 [-6.3075, -2.0325] | -3.7396 [-5.9672, -1.9636] | 0.1429 [-0.1341, 0.4459] | 20 |
| codex | E E_status | -0.3125 [-0.9375, 0.0000] | -0.6953 [-2.3984, 0.8906] | -0.3828 [-2.0859, 1.2344] | 32 |
| codex | E E_default | 0.0000 [0.0000, 0.0000] | -0.0234 [-1.5547, 1.5234] | -0.0234 [-1.5547, 1.5234] | 32 |
| codex | E E_recommend | 49.8438 [48.2812, 51.5625] | 50.8125 [48.5234, 53.0859] | 0.9688 [-1.0000, 2.9453] | 32 |
| codex | E neutral direct | 50.625 | n=32 | descriptive | 32 |
| codex | E advice control direct | 49.844 [48.281, 51.562] | missing bounds [49.844, 49.844] | downgrade=False | 32 |
| codex | E neutral multi | 49.922 | n=32 | descriptive | 32 |
| codex | E advice control multi | 50.812 [48.523, 53.086] | missing bounds [50.812, 50.812] | downgrade=False | 32 |
| codex | D2 supplemental S minus J | 2.458 [1.175, 3.875] | direct comparison | not a format contrast | 20 |
| Sonnet 5.5 | D delta_S | -1.4800 [-3.7300, 0.0800] | -1.8965 [-4.5800, -0.0055] | -0.4165 [-1.5597, 0.5083] | 20 |
| Sonnet 5.5 | D delta_J | -3.7800 [-6.4300, -1.8550] | -3.8750 [-6.7585, -1.8514] | -0.0950 [-0.4385, 0.2107] | 20 |
| Sonnet 5.5 | E E_status | 0.3438 [-1.2500, 1.8438] | 0.0453 [-1.8969, 1.9297] | -0.2984 [-3.0656, 2.4234] | 32 |
| Sonnet 5.5 | E E_default | -1.4062 [-3.1250, 0.2188] | -1.0175 [-3.4947, 1.1403] | 0.3888 [-2.5297, 3.0953] | 32 |
| Sonnet 5.5 | E E_recommend | 52.9688 [50.0312, 55.8750] | 49.0409 [47.0156, 51.0678] | -3.9278 [-5.7788, -2.0466] | 32 |
| Sonnet 5.5 | E neutral direct | 43.656 | n=32 | descriptive | 32 |
| Sonnet 5.5 | E advice control direct | 52.969 [50.031, 55.875] | missing bounds [52.969, 52.969] | downgrade=False | 32 |
| Sonnet 5.5 | E neutral multi | 43.660 | n=32 | descriptive | 32 |
| Sonnet 5.5 | E advice control multi | 49.041 [47.016, 51.068] | missing bounds [49.041, 49.041] | downgrade=False | 32 |
| Sonnet 5.5 | D2 supplemental S minus J | 2.300 [1.305, 3.490] | direct comparison | not a format contrast | 20 |
| Qwen3 | D delta_S | 13.0250 [8.0000, 19.0750] | 8.4120 [1.9751, 15.1723] | -4.6130 [-12.9365, 3.6095] | 20 |
| Qwen3 | D delta_J | -2.7500 [-7.5000, 1.4000] | -5.3333 [-9.3099, -1.7365] | -2.5833 [-5.9837, 0.7263] | 20 |
| Qwen3 | E E_status | -3.3142 [-11.3265, 4.3013] | 0.7275 [-3.6466, 4.8992] | 4.0417 [-5.5677, 14.3247] | 31 |
| Qwen3 | E E_default | 0.1021 [-9.1462, 7.8159] | 5.7613 [-0.5824, 11.8820] | 5.6592 [-4.1036, 15.6847] | 29 |
| Qwen3 | E E_recommend | 63.9616 [50.3052, 77.0968] | 36.0131 [31.0953, 40.4462] | -27.9485 [-39.7935, -15.7437] | 31 |
| Qwen3 | E neutral direct | 53.359 | n=32 | descriptive | 32 |
| Qwen3 | E advice control direct | 64.932 [51.046, 77.323] | missing bounds [64.932, 64.932] | downgrade=False | 32 |
| Qwen3 | E neutral multi | 45.695 | n=32 | descriptive | 32 |
| Qwen3 | E advice control multi | 36.013 [31.095, 40.446] | missing bounds [33.544, 36.669] | downgrade=False | 31 |
| Qwen3 | D2 supplemental S minus J | 15.775 [9.400, 22.900] | direct comparison | not a format contrast | 20 |
| gpt-oss-120b | D delta_S | 9.6000 [3.2000, 17.1000] | 6.9050 [3.9825, 10.3775] | -2.6950 [-10.6725, 4.2975] | 20 |
| gpt-oss-120b | D delta_J | -7.7500 [-12.4500, -4.1000] | -9.7134 [-12.9747, -7.1175] | -1.9634 [-4.2893, 0.4016] | 20 |
| gpt-oss-120b | E E_status | -1.1334 [-7.5606, 5.4844] | 3.9875 [0.9813, 7.0375] | 5.1209 [-2.0831, 12.3959] | 32 |
| gpt-oss-120b | E E_default | 1.4781 [-3.2188, 6.5719] | 4.6219 [0.3625, 8.7203] | 3.1438 [-2.0422, 8.0203] | 32 |
| gpt-oss-120b | E E_recommend | 50.3438 [42.1250, 57.3750] | 27.1091 [22.1556, 31.8578] | -23.2347 [-31.3428, -14.1425] | 32 |
| gpt-oss-120b | E neutral direct | 42.672 | n=32 | descriptive | 32 |
| gpt-oss-120b | E advice control direct | 50.344 [42.125, 57.375] | missing bounds [50.344, 50.344] | downgrade=False | 32 |
| gpt-oss-120b | E neutral multi | 49.591 | n=32 | descriptive | 32 |
| gpt-oss-120b | E advice control multi | 27.109 [22.156, 31.858] | missing bounds [27.109, 27.109] | downgrade=False | 32 |
| gpt-oss-120b | D2 supplemental S minus J | 17.350 [9.750, 25.550] | direct comparison | not a format contrast | 20 |
| Flash low | D delta_S | 0.0850 [-1.0150, 1.4950] | 0.5722 [-1.6420, 2.9412] | 0.4872 [-1.6540, 2.7748] | 20 |
| Flash low | D delta_J | -3.2875 [-5.5700, -1.5275] | -3.4545 [-6.2085, -1.5231] | -0.1670 [-0.7720, 0.3549] | 20 |
| Flash low | E E_status | -0.5312 [-1.6250, 0.1875] | -1.2622 [-3.1075, 0.6453] | -0.7309 [-2.8325, 1.5188] | 32 |
| Flash low | E E_default | 0.0000 [0.0000, 0.0000] | 1.6453 [-0.1828, 3.5578] | 1.6453 [-0.1828, 3.5578] | 32 |
| Flash low | E E_recommend | 65.6875 [59.6875, 71.0938] | 59.2622 [56.6569, 61.8575] | -6.4253 [-11.4000, -0.2187] | 32 |
| Flash low | E neutral direct | 46.875 | n=32 | descriptive | 32 |
| Flash low | E advice control direct | 65.688 [59.688, 71.094] | missing bounds [65.688, 65.688] | downgrade=False | 32 |
| Flash low | E neutral multi | 53.308 | n=32 | descriptive | 32 |
| Flash low | E advice control multi | 59.262 [56.657, 61.858] | missing bounds [59.262, 59.262] | downgrade=False | 32 |
| Flash low | D2 supplemental S minus J | 3.373 [1.137, 6.130] | direct comparison | not a format contrast | 20 |
| Flash high | D delta_S | -1.1150 [-2.1150, -0.2150] | -0.1357 [-1.9650, 1.4325] | 0.9793 [-0.7268, 2.6888] | 20 |
| Flash high | D delta_J | -4.4500 [-7.3250, -2.3000] | -3.6920 [-6.6698, -1.6965] | 0.7580 [-0.1690, 2.0015] | 20 |
| Flash high | E E_status | 0.6250 [0.0000, 1.8750] | -1.5625 [-3.5766, 0.4328] | -2.1875 [-4.4375, 0.0750] | 32 |
| Flash high | E E_default | 0.0000 [0.0000, 0.0000] | 0.1419 [-1.5772, 1.8969] | 0.1419 [-1.5772, 1.8969] | 32 |
| Flash high | E E_recommend | 71.8750 [62.8125, 80.1562] | 58.4344 [56.1047, 60.6156] | -13.4406 [-21.4906, -4.4484] | 32 |
| Flash high | E neutral direct | 36.875 | n=32 | descriptive | 32 |
| Flash high | E advice control direct | 71.875 [62.812, 80.156] | missing bounds [71.875, 71.875] | downgrade=False | 32 |
| Flash high | E neutral multi | 53.511 | n=32 | descriptive | 32 |
| Flash high | E advice control multi | 58.434 [56.105, 60.616] | missing bounds [58.434, 58.434] | downgrade=False | 32 |
| Flash high | D2 supplemental S minus J | 3.335 [1.245, 5.865] | direct comparison | not a format contrast | 20 |

**Table H5. Repeat consistency: 484 calls and 520 planned numeric pairs per configuration**

D joint calls each supply four dependent numeric statement pairs; they are not four independent calls. A SDs are on raw quantity scales, incomparable across items. Qwen3 loses one E multi repeat pair because its r1 unit is missing; a missing primary C cell can also remove a C pair.

| Configuration | Exp | Format | Planned calls | Planned pairs | Available pairs | Zero differences | Median cell call SD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| codex | A | direct | 40 | 40 | 40 | 37 | 0.000 |
| codex | A | multi | 40 | 40 | 40 | 11 | 4687.502 |
| codex | B | direct | 96 | 96 | 96 | 70 | 3.125 |
| codex | B | multi | 96 | 96 | 96 | 32 | 1.994 |
| codex | C | direct | 48 | 48 | 48 | 46 | 0.000 |
| codex | C | multi | 48 | 48 | 48 | 36 | 0.000 |
| codex | D | direct | 30 | 48 | 48 | 26 | 2.189 |
| codex | D | multi | 30 | 48 | 48 | 7 | 2.303 |
| codex | E | direct | 28 | 28 | 28 | 24 | 0.000 |
| codex | E | multi | 28 | 28 | 28 | 13 | 2.129 |
| Sonnet 5.5 | A | direct | 40 | 40 | 40 | 24 | 12.787 |
| Sonnet 5.5 | A | multi | 40 | 40 | 40 | 1 | 11222500.000 |
| Sonnet 5.5 | B | direct | 96 | 96 | 96 | 45 | 3.206 |
| Sonnet 5.5 | B | multi | 96 | 96 | 96 | 6 | 3.889 |
| Sonnet 5.5 | C | direct | 48 | 48 | 48 | 41 | 0.002 |
| Sonnet 5.5 | C | multi | 48 | 48 | 48 | 4 | 0.715 |
| Sonnet 5.5 | D | direct | 30 | 48 | 48 | 17 | 1.800 |
| Sonnet 5.5 | D | multi | 30 | 48 | 48 | 0 | 1.367 |
| Sonnet 5.5 | E | direct | 28 | 28 | 28 | 9 | 2.761 |
| Sonnet 5.5 | E | multi | 28 | 28 | 28 | 1 | 1.823 |
| Qwen3 | A | direct | 40 | 40 | 40 | 23 | 1305041.211 |
| Qwen3 | A | multi | 40 | 40 | 40 | 3 | 55001.998 |
| Qwen3 | B | direct | 96 | 96 | 96 | 56 | 3.506 |
| Qwen3 | B | multi | 96 | 96 | 96 | 9 | 13.987 |
| Qwen3 | C | direct | 48 | 48 | 48 | 44 | 0.041 |
| Qwen3 | C | multi | 48 | 48 | 48 | 0 | 0.517 |
| Qwen3 | D | direct | 30 | 48 | 48 | 22 | 6.887 |
| Qwen3 | D | multi | 30 | 48 | 48 | 8 | 6.219 |
| Qwen3 | E | direct | 28 | 28 | 28 | 10 | 22.638 |
| Qwen3 | E | multi | 28 | 28 | 27 | 2 | 6.051 |
| gpt-oss-120b | A | direct | 40 | 40 | 40 | 14 | 1711905.080 |
| gpt-oss-120b | A | multi | 40 | 40 | 40 | 0 | 50000.020 |
| gpt-oss-120b | B | direct | 96 | 96 | 96 | 36 | 8.536 |
| gpt-oss-120b | B | multi | 96 | 96 | 96 | 1 | 9.240 |
| gpt-oss-120b | C | direct | 48 | 48 | 48 | 45 | 0.000 |
| gpt-oss-120b | C | multi | 48 | 48 | 48 | 6 | 0.211 |
| gpt-oss-120b | D | direct | 30 | 48 | 48 | 11 | 5.017 |
| gpt-oss-120b | D | multi | 30 | 48 | 48 | 0 | 6.247 |
| gpt-oss-120b | E | direct | 28 | 28 | 28 | 12 | 10.452 |
| gpt-oss-120b | E | multi | 28 | 28 | 28 | 1 | 6.424 |
| Flash low | A | direct | 40 | 40 | 40 | 28 | 10.335 |
| Flash low | A | multi | 40 | 40 | 40 | 5 | 22500.002 |
| Flash low | B | direct | 96 | 96 | 96 | 62 | 4.812 |
| Flash low | B | multi | 96 | 96 | 96 | 13 | 3.803 |
| Flash low | C | direct | 48 | 48 | 48 | 48 | 0.000 |
| Flash low | C | multi | 48 | 48 | 48 | 16 | 0.005 |
| Flash low | D | direct | 30 | 48 | 48 | 17 | 2.889 |
| Flash low | D | multi | 30 | 48 | 48 | 0 | 1.694 |
| Flash low | E | direct | 28 | 28 | 28 | 26 | 0.000 |
| Flash low | E | multi | 28 | 28 | 28 | 1 | 4.058 |
| Flash high | A | direct | 40 | 40 | 40 | 32 | 10.078 |
| Flash high | A | multi | 40 | 40 | 40 | 2 | 12500.010 |
| Flash high | B | direct | 96 | 96 | 96 | 60 | 3.858 |
| Flash high | B | multi | 96 | 96 | 96 | 2 | 2.928 |
| Flash high | C | direct | 48 | 48 | 48 | 48 | 0.000 |
| Flash high | C | multi | 48 | 48 | 48 | 17 | 0.011 |
| Flash high | D | direct | 30 | 48 | 48 | 21 | 2.196 |
| Flash high | D | multi | 30 | 48 | 48 | 1 | 1.998 |
| Flash high | E | direct | 28 | 28 | 28 | 25 | 0.000 |
| Flash high | E | multi | 28 | 28 | 28 | 1 | 2.808 |

**Table H6. External delta-NLI stated-presentation H4b comparison**

Cached results from a separate frozen study, not six new Psych3 confirmation tests. codex CLI versions differ between the experiments; cross-task comparisons are descriptive.

| Configuration | Paired items | Direct mean s | Multi mean s | Multi minus direct [raw 95% CI] |
| --- | --- | --- | --- | --- |
| codex | 120 | 25.283 | 22.801 | -2.482 [-3.181, -1.797] |
| Sonnet 5.5 | 120 | 22.008 | 22.479 | 0.471 [-0.342, 1.32] |
| Qwen3 | 240 | 18.594 | 10.655 | -7.939 [-9.716, -6.245] |
| gpt-oss-120b | 120 | 17.592 | 15.296 | -2.295 [-4.081, -0.561] |
| Flash low | 120 | 26.641 | 24.163 | -2.478 [-3.677, -1.358] |
| Flash high | 120 | 28.296 | 24.563 | -3.733 [-5.051, -2.52] |

**Table H7. Candidate spread versus absolute response-format difference**

Post-hoc, in-sample, whole-cluster bootstrap (5,000 draws; seed 20261029). Undefined correlations are left undefined; zero valid resamples are not failed experiments. No multiplicity-adjusted or held-out predictive conclusion is drawn.

| Configuration | Exp | Items | Clusters | Spearman rho [95% CI] | Valid resamples | Degenerate resamples |
| --- | --- | --- | --- | --- | --- | --- |
| codex | A | 50 | 50 | 0.728 [0.525, 0.869] | 5000 | 0 |
| codex | B | 90 | 90 | 0.379 [0.174, 0.557] | 5000 | 0 |
| codex | C | 40 | 20 | undefined | 0 | 0 |
| codex | D | 35 | 35 | 0.473 [0.170, 0.710] | 5000 | 0 |
| codex | E | 32 | 32 | -0.256 [-0.609, 0.155] | 5000 | 0 |
| Sonnet 5.5 | A | 50 | 50 | 0.877 [0.760, 0.934] | 5000 | 0 |
| Sonnet 5.5 | B | 90 | 90 | 0.504 [0.309, 0.670] | 5000 | 0 |
| Sonnet 5.5 | C | 40 | 20 | 0.627 [0.400, 0.786] | 5000 | 0 |
| Sonnet 5.5 | D | 35 | 35 | 0.506 [0.191, 0.745] | 5000 | 0 |
| Sonnet 5.5 | E | 32 | 32 | -0.162 [-0.485, 0.184] | 5000 | 0 |
| Qwen3 | A | 50 | 50 | 0.501 [0.250, 0.694] | 5000 | 0 |
| Qwen3 | B | 90 | 90 | 0.373 [0.174, 0.543] | 5000 | 0 |
| Qwen3 | C | 40 | 20 | 0.398 [0.162, 0.573] | 5000 | 0 |
| Qwen3 | D | 35 | 35 | 0.527 [0.220, 0.735] | 5000 | 0 |
| Qwen3 | E | 32 | 32 | -0.156 [-0.481, 0.222] | 5000 | 0 |
| gpt-oss-120b | A | 50 | 50 | 0.792 [0.620, 0.893] | 5000 | 0 |
| gpt-oss-120b | B | 90 | 90 | 0.543 [0.367, 0.683] | 5000 | 0 |
| gpt-oss-120b | C | 40 | 20 | 0.579 [0.342, 0.764] | 5000 | 0 |
| gpt-oss-120b | D | 35 | 35 | 0.608 [0.321, 0.789] | 5000 | 0 |
| gpt-oss-120b | E | 32 | 32 | 0.111 [-0.288, 0.504] | 5000 | 0 |
| Flash low | A | 50 | 50 | 0.941 [0.876, 0.968] | 5000 | 0 |
| Flash low | B | 90 | 90 | 0.571 [0.384, 0.722] | 5000 | 0 |
| Flash low | C | 40 | 20 | 0.134 [-0.204, 0.450] | 5000 | 0 |
| Flash low | D | 35 | 35 | 0.911 [0.823, 0.948] | 5000 | 0 |
| Flash low | E | 32 | 32 | 0.087 [-0.304, 0.469] | 5000 | 0 |
| Flash high | A | 50 | 50 | 0.955 [0.901, 0.975] | 5000 | 0 |
| Flash high | B | 90 | 90 | 0.642 [0.477, 0.767] | 5000 | 0 |
| Flash high | C | 40 | 20 | 0.433 [0.193, 0.644] | 5000 | 0 |
| Flash high | D | 35 | 35 | 0.669 [0.432, 0.822] | 5000 | 0 |
| Flash high | E | 32 | 32 | 0.049 [-0.337, 0.427] | 5000 | 0 |

**Table H8. Candidate spread versus absolute multi-estimate log error in A**

| Configuration | A framing | Items | Clusters | Spearman rho [95% CI] | Valid resamples |
| --- | --- | --- | --- | --- | --- |
| codex | none | 49 | 49 | 0.836 [0.697, 0.929] | 5000 |
| codex | anchored | 50 | 50 | 0.829 [0.683, 0.910] | 5000 |
| Sonnet 5.5 | none | 50 | 50 | 0.902 [0.810, 0.944] | 5000 |
| Sonnet 5.5 | anchored | 50 | 50 | 0.876 [0.768, 0.932] | 5000 |
| Qwen3 | none | 50 | 50 | 0.566 [0.308, 0.763] | 5000 |
| Qwen3 | anchored | 50 | 50 | 0.598 [0.378, 0.754] | 5000 |
| gpt-oss-120b | none | 49 | 49 | 0.692 [0.469, 0.840] | 5000 |
| gpt-oss-120b | anchored | 50 | 50 | 0.733 [0.528, 0.856] | 5000 |
| Flash low | none | 50 | 50 | 0.798 [0.647, 0.895] | 5000 |
| Flash low | anchored | 50 | 50 | 0.900 [0.806, 0.945] | 5000 |
| Flash high | none | 50 | 50 | 0.884 [0.756, 0.947] | 5000 |
| Flash high | anchored | 50 | 50 | 0.881 [0.753, 0.946] | 5000 |

**Table H9. Exploratory A error split at the within-sample median spread**

Lower group: spread at or below the median; upper: strictly above. Ties are not split. These are not validated deployment thresholds.

| Configuration | A framing | Median cutoff | Lower-group items | Lower mean abs log error | Upper-group items | Upper mean abs log error |
| --- | --- | --- | --- | --- | --- | --- |
| codex | none | 0.0390 | 25 | 0.0266 | 24 | 0.4022 |
| codex | anchored | 0.0579 | 25 | 0.0425 | 25 | 0.3594 |
| Sonnet 5.5 | none | 0.0985 | 25 | 0.0291 | 25 | 0.5500 |
| Sonnet 5.5 | anchored | 0.1448 | 25 | 0.0588 | 25 | 0.4559 |
| Qwen3 | none | 0.0929 | 25 | 0.7175 | 25 | 0.8857 |
| Qwen3 | anchored | 0.1107 | 25 | 0.4215 | 25 | 0.9914 |
| gpt-oss-120b | none | 0.0729 | 25 | 0.1360 | 24 | 1.4604 |
| gpt-oss-120b | anchored | 0.0781 | 25 | 0.1118 | 25 | 0.3939 |
| Flash low | none | 0.0415 | 25 | 0.0276 | 25 | 0.3532 |
| Flash low | anchored | 0.0521 | 25 | 0.0139 | 25 | 0.3996 |
| Flash high | none | 0.0559 | 25 | 0.0283 | 25 | 0.3859 |
| Flash high | anchored | 0.0446 | 25 | 0.0353 | 25 | 0.3314 |

**Table H10. D spread associations separated by person and event items**

P: 20 person items; W: 15 event pairs. Pooling these strata does not identify an association in each stratum.

| Configuration | Type | Items | Clusters | Spearman rho [95% CI] | Valid resamples |
| --- | --- | --- | --- | --- | --- |
| codex | P | 20 | 20 | 0.346 [-0.148, 0.734] | 5000 |
| codex | W | 15 | 15 | 0.796 [0.462, 0.944] | 5000 |
| Sonnet 5.5 | P | 20 | 20 | 0.296 [-0.116, 0.657] | 5000 |
| Sonnet 5.5 | W | 15 | 15 | 0.582 [0.011, 0.905] | 5000 |
| Qwen3 | P | 20 | 20 | 0.570 [0.160, 0.837] | 5000 |
| Qwen3 | W | 15 | 15 | 0.679 [0.176, 0.922] | 5000 |
| gpt-oss-120b | P | 20 | 20 | 0.611 [0.208, 0.840] | 5000 |
| gpt-oss-120b | W | 15 | 15 | 0.654 [0.154, 0.924] | 5000 |
| Flash low | P | 20 | 20 | 0.862 [0.647, 0.941] | 5000 |
| Flash low | W | 15 | 15 | 0.864 [0.609, 0.955] | 5000 |
| Flash high | P | 20 | 20 | 0.549 [0.153, 0.820] | 5000 |
| Flash high | W | 15 | 15 | 0.754 [0.370, 0.908] | 5000 |

**Table H11. Exploratory Flash-high execution-window partition**

F0 and F1 are non-randomized execution windows confounded with item schedule order and collection time. Differences are exploratory and do not identify a causal execution-window or model effect. Cluster D / w01 spans F0 (7 r0 calls) and F1 (3 r0 calls) across both response formats. There are zero cross-batch r0/r1 repeat pairs: every repeated unit has its r0 and r1 calls in the same batch. Full item/cluster partitions and the empty cross-batch repeat-pair list remain in high_batch_diagnostics_exploratory.json; assignments to the other batch are not missing outcomes.

| Batch | Round | Experiment | Assigned admitted units | True missing | Assigned to other batch |
| --- | --- | --- | --- | --- | --- |
| F0 | r0 | A | 430 | 0 | 653 |
| F0 | r0 | B | 1216 | 1 |  |
| F0 | r0 | C | 408 | 0 |  |
| F0 | r0 | D | 297 | 0 |  |
| F0 | r0 | E | 336 | 0 |  |
| F0 | r1 | A | 60 | 0 |  |
| F0 | r1 | B | 128 | 0 |  |
| F0 | r1 | C | 72 | 0 |  |
| F0 | r1 | D | 60 | 0 |  |
| F0 | r1 | E | 42 | 0 |  |
| F1 | r0 | A | 70 | 0 | 3049 |
| F1 | r0 | B | 224 | 0 |  |
| F1 | r0 | C | 72 | 0 |  |
| F1 | r0 | D | 53 | 0 |  |
| F1 | r0 | E | 112 | 0 |  |
| F1 | r1 | A | 20 | 0 |  |
| F1 | r1 | B | 64 | 0 |  |
| F1 | r1 | C | 24 | 0 |  |
| F1 | r1 | D | 0 | 0 |  |
| F1 | r1 | E | 14 | 0 |  |
