<!-- source: methods-zh.md v0.2 -->

## 3 Methods

### 3.1 Materials

**Source.** Items were taken from the SNLI [Bowman et al. 2015] subset of δ-NLI (δ-SNLI; Rudinger et al., 2020; github.com/rudinger/defeasible-nli, commit c675ffc), merging dev and test, for a total of 3,860 rows. The data inherit SNLI's CC BY-SA 4.0 license. Each row consists of a premise P (an image caption), a hypothesis H, and a human-written update U, labelled as a strengthener (S) or a weakener (W). We do not use δ-ATOMIC (whose hypotheses are mostly template fragments) or δ-SOCIAL (which has no premise sentence).

**Item selection.** We first excluded the 238 rows marked as "impossible to write an update", leaving 3,622 rows. Aggregating by premise–hypothesis pair, we kept only pairs that have both an S and a W update: 194 pairs in dev and 202 in test. We further excluded pairs that share images with the two human-check materials (32 pairs), yielding a candidate pool of 364 pairs from 357 images. We shuffled the pool with seed 20261070 and took pairs in order, taking each image only once; for each pair, the same random number generator was then used to select one S and one W update (for replacement pairs and for the sentence selection in Block B, an independent generator seeded with the pair's ID was used instead, so that other pairs are not disturbed). The repeat subset was drawn from Block A with seed 20261071. In total we took 270 pairs: 30 for the development set and 240 for the formal set, the two being disjoint by image. The formal set is divided into two blocks of 120 pairs each; Block A is the originally planned formal set, and Block B was drawn further down the same shuffled sequence when the sample was expanded in v0.7 according to power scenarios.

**Exclusion of items involving protected attributes.** If the hypothesis H or a selected update S or W asserted or asked about a person's race, ethnicity, nationality, or religion, the whole pair was excluded and replaced by the next eligible pair in the original sampling sequence; pairs not excluded, and their selected sentences, were left unchanged (the premise P was not within the scope of this check). Candidates were first screened with a frozen keyword list; each flagged pair was then judged individually, with the reason recorded, by the language-model agent responsible for material checks in the research workflow, and the final list was re-checked with a broader word list. This was a material check performed by a model, not human screening. In total, 8 pairs were excluded. Rationale: in the development-set smoke test, codex refused to answer all such items; moreover, asking a model to infer race from appearance is itself ethically problematic.

**Clusters.** We use SNLI images as clusters: different captions of the same image are treated as the same cluster. The 240 pairs of the formal set come from 240 distinct images.

**Direction spot check.** We additionally drew 20 premise–hypothesis–update items (10 strengtheners and 10 weakeners, included in neither the development set nor the formal set), presented only in the stated version. The author, as the sole human rater and without seeing the labels, judged whether each update was a strengthener, a weakener, had no effect, was incomprehensible, or was ungrammatical: 17 items agreed with the label, 2 were judged "no effect", and 1 was in the opposite direction. This serves only as a check on the materials and is not used as human agreement-rate data (the original δ-NLI paper reports a human accuracy of 83.6% on the SNLI subset).

### 3.2 Item format and elicitation

All prompts are in English and consist of a single user message with no system prompt. The item format is:

> Here is a situation: P
> [Here is something else you learned: U]　　(stated)
> [Someone said that u]　　　　　　　　　　　 (reported)
>
> Using common sense, how likely is it that the following statement is true?
> Statement: H
>
> (elicitation-specific ending)
>
> Do not use any tools; answer directly.

Prior items omit the second line. In the reported version, u is U with its first letter lowercased according to a frozen rule: the first letter is left unchanged if the sentence begins with a non-letter, is already lowercase, begins with "I" or "I'", begins with an abbreviation containing capital letters, or begins with a word in a fixed proper-noun list (Batman, Christmas, Sally, Gone, Mom; determined from the sentence-initial words of all 3,622 updates, independently of which items were sampled); no general named-entity recognition is performed. If P, H, or U lacks sentence-final punctuation, a period is added; all other text (including spelling errors) is left unchanged. "Do not use any tools" is required for codex isolation; all three configurations use the same prompt.

The endings for the two elicitations:

- **Direct elicitation**: "What is the probability that the statement is true?", with the final line required to be written as `Probability: NN%` (0–100, decimals allowed).
- **Multi-estimate elicitation** (inspired by Verbalized Sampling; Zhang et al., 2025): "Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.", with the answer required to end with 5 lines of the form `Estimate k: NN% | Weight: W`. The aggregated value is the weighted mean.

Each pair has 10 conditions under each configuration: prior × 2 elicitations, plus posterior × 2 update types × 2 presentations × 2 elicitations. Within the same elicitation, the stated and reported versions share the same prior. A further 20 pairs were drawn as the repeat subset, for which every condition was asked once more independently, in order to estimate between-call variability.

### 3.3 Models tested

| Configuration | Model | How run | Key settings |
|---|---|---|---|
| Qwen3 (thinking off) | Qwen3-8B (HF commit b968826) | Local llama.cpp b11560, GGUF Q8_0 | Chat template `enable_thinking=False`; context 16,384, at most 8,192 generated tokens |
| OLMo-2 | OLMo-2-1124-7B-Instruct (HF commit 470b1fb) | Same as above | Context 4,096; generation up to the end of the context |
| codex | gpt-6.1-sol, reasoning effort medium | codex CLI, ChatGPT subscription quota | Invoked through the codex CLI harness; isolation and inclusion rules below |

The two local configurations use the same sampling parameters: temperature 0.6, top-k 20, top-p 0.95, min-p 0, with all other samplers disabled; prompts are rendered with the chat template bundled with the HF tokenizer, as a single user message. Every call uses an independent context. The call seed is the first 8 hexadecimal digits of the SHA-256 hash of the string "{set}|{configuration}|{unit id}|a{attempt}|{base seed}" (base seed: 20261080 for the development set, 20261081 for the formal set); the run order is shuffled with "base seed × 10 + configuration offset (qwen3-off 0, olmo2 2, codex 3)". A generation that used up the length limit before the end-of-sequence token was classified as truncated (this did not occur in the formal run).

codex is a commercial model invoked through an agent harness (codex CLI 0.162.0-alpha.17.2; in the formal run it was executed with 3 parallel worker processes, with the same attempt and resampling rules for each unit as in sequential execution). We cannot control its system prompt, and we did not set its sampling parameters or seed (the call seed described above has no effect for codex); our conclusions apply only to "the model inside the harness". Each call was made in an isolated temporary directory, and the event stream and internal logs were checked and handled according to the following rules:

- **Tool contamination**: if the logs or event stream contain a record of tool use (confirmed), or show multiple samples, multiple answers, or input tokens exceeding 1.5 times the baseline (7,300 plus one third of the prompt length in characters) (suspected), the attempt is voided and the same condition is resampled once; if it is still contaminated after resampling, it is recorded as `tool_contaminated` (missing).
- **Disconnection**: when the only integrity problem is that the message counts in the logs and in the events disagree, and the difference can be explained by the number of disconnection retries in the logs, only that attempt is voided and resampled, without counting against the resampling allowance above; the run stops only after three consecutive disconnections on the same unit.
- **Call errors** (non-zero exit, timeout, unknown event, no final answer, etc.) and **quota-exhaustion signals**: the run stops; the session is not voided, and the work is redone when the launcher script resumes the run. Addendum A1 (after the formal run had started) also placed in this category calls that "could not connect to the server and left no sampling record or output".
- **Session invalidation**: a change in the global instruction file or any other log-integrity error voids the entire session; voided sessions and sessions that did not terminate normally are not included in the analysis.

Addendum A1 changed codex's experiment fingerprint (a hash binding the plan, sampling, prompts, parser, runner and materials), so both the development set and the formal set for codex were rerun under the new fingerprint, and the earlier results do not enter the analysis. The isolation parameters and the frozen harness settings are recorded in the run metadata.

### 3.4 Parsing and missing data

Following the prompt's instructions, parsing reads the "last" answer (parsing rule v2). For direct elicitation, the last `Probability:` field is taken; if that field has no valid number on the same line, parsing fails, without falling back to earlier fields. For multi-estimate elicitation, the final group is taken starting from the last line that looks like "Estimate 1" (lenient match), but all estimate lines within the group must still strictly qualify: exactly 5 lines, numbered 1–5, each value in 0–100 with a percent sign, and weights in [0, 1]. As long as the weights sum to a positive number, they are normalized by that sum (the weighted mean is invariant to overall scaling); whether the sum falls within [0.95, 1.05] is reported only descriptively.

Parsing rule v2 was revised after inspecting the types of format failure in the development-set smoke test (for example, an extra `Probability:` field written in a heading, estimates listed once in the body and again at the end, or weights not summing to 1). No probability values were looked at during the revision. The Results section also reports the parse rate under the earlier parsing rule v1.

When parsing fails or the output is truncated, the same prompt is resampled once (this allowance is counted separately from the resampling allowance for tool contamination); if it still fails, the unit is recorded as missing. For each unit, the first qualifying attempt is used. Each comparison uses only the items for which all conditions involved in the comparison are valid (the common complete set). We also compute a missing-data bound: the contributions of missing units are replaced by the value least favourable to the conclusion (0 or 100 for linear quantities, 0 or 1 for endpoint indicators), and the bootstrap is rerun; only if this conservative interval still supports the conclusion do we use the verdict "the adjusted bound exceeds the SESOI (worst-case imputation of missing units)".

### 3.5 Measures and analysis

- **Directional movement**: Δ = p₁ − p₀ (posterior minus prior), and the directional movement *s* = Δ × direction (+1 for S, −1 for W), averaged over the S and W updates of each pair; s > 0 indicates movement in the annotated direction. The prior cancels out in s, so s depends only on the two posteriors. We also report Δ separately for strengtheners and weakeners, the difference between the two posteriors D = p_S − p_W, the agreement rate, the reversal rate, and the zero-movement rate.
- **Endpoint rate**: the proportion of reported values ≤ 5% or ≥ 95%; for H4a it is weighted 1/2 for the prior, 1/4 for the stated strengthener, and 1/4 for the stated weakener.
- **Confirmatory hypotheses** (Table 5): H1, directional sensitivity; H2, reported wording; H4a, endpoint rate under multi-estimate elicitation; H4b, directional sensitivity under multi-estimate elicitation.

**Table 5. Confirmatory hypotheses**

| Hypothesis | Statistic | Sidedness | Smallest effect size of interest (SESOI) |
|---|---|---|---|
| H1 | Mean s, stated, direct elicitation | One-sided, > 0 | 5 points |
| H2 | Mean s, stated minus reported (direct elicitation) | One-sided, > 0 | 5 points |
| H4a | Weighted endpoint rate, direct minus multi-estimate | One-sided, > 0 | 10 percentage points |
| H4b | Mean s, multi-estimate minus direct (stated) | Two-sided | 5 points |

- **Statistics**: items are weighted equally. We use a cluster bootstrap (each replicate resamples clusters, carrying along all conditions of each cluster), with B = 5,000, seed 20261090, and non-interpolated quantiles; we report two-sided 95% intervals. Bootstrap p-values: the one-sided p-value is the proportion of resampled statistics falling on the side opposite to the predicted direction (including zero); the two-sided p-value is twice the smaller of the two one-sided proportions (capped at 1). For each configuration, {H1, H2, H4a, H4b} form one Holm family: hypotheses are ordered by p-value and compared step by step against α/(4−k), stopping at the first non-rejection; the adjusted bounds are per-hypothesis adjusted intervals, not a joint confidence region. Each configuration is tested on its own planned sample (240 pairs for the local configurations, 120 pairs for codex); cross-configuration comparisons are descriptive only, and we additionally report the results of the local configurations on the same 120 pairs used for codex.
- **Verdict wording** (frozen in advance): "the adjusted bound exceeds the SESOI" = the Holm-adjusted bound nearer to zero strictly exceeds the SESOI; "the point estimate reaches the SESOI, but the adjusted bound does not" = the point estimate is ≥ the SESOI, but that bound does not exceed it; "direction confirmed; point estimate below the SESOI" = the direction is confirmed (that bound lies beyond zero), but the point estimate is smaller than the SESOI. For H1, H2, and H4a we use the adjusted one-sided bound; for H4b we use the end of the adjusted two-sided interval nearer to zero. H2 has one additional pre-specified interpretation rule: if the reversal rate under reported presentation is higher than under stated presentation, the conclusion is worded as "reporting shifts the direction of movement".
- **Pre-specified sensitivity analysis**: excluding pairs whose update is quoted speech (an update that reports the content of someone's utterance, so that its reported version becomes a quoted-speech update, i.e., speech nested within a report), we recompute H1, H2, and H4b, keep H4a on the original sample, and still use the four-hypothesis Holm family. The frozen list of quoted-speech updates has 11 IDs, of which 10 sentences are in the final materials (3 in the development set, 7 in the formal set), involving 7 pairs in the formal set.
- **Pre-specified descriptive analyses**: the prior distribution, endpoint rates for each condition, agreement and reversal rates, between-call variability, and stratification by the original δ-SNLI split (dev/test).

### 3.6 Pre-specification, freezing, and deviations

The analysis plan (hypotheses, sidedness, SESOIs, missing-data rules, B, Holm families) was written before the formal set was run, revised over several rounds of independent review (conducted by another model), and then frozen. The plan was thus pre-specified, frozen and hashed before the formal run; it was not deposited in a public registry. The experiment fingerprint binds the plan file, the sampling, the prompts, the parsing, the run program, and a digest of the materials; any change alters the fingerprint and requires the development set to be rerun. The analysis freeze additionally binds the analysis program and B, and the formal analysis was executed only after the reconciliation (every planned unit accounted for) was complete.

All revisions made before the formal run are recorded in the plan's change log, in three rounds:

- **v0.6 (after the first development-set smoke test)**: parsing rule v2; exclusion of protected-attribute items; the criterion for codex disconnections (disconnections in the middle of sampling); and removal of the originally planned Qwen3 thinking-on configuration and its hypothesis H3 (we decided not to run it). These revisions were based on diagnostics such as format-failure types and refusals; no probability values or direction results were looked at during the revision.
- **v0.7 (after the acceptance check of the development set under the new fingerprint)**: the formal set was expanded to 240 pairs for the local configurations and 120 pairs for codex. This step **drew on exploratory diagnostics and power scenarios from the development set** (development-set movements and differences), but no formal-set results were looked at.
- **v0.7.1**: codex was switched to parallel execution; the rules were unchanged, but the fingerprint changed, and the development set was rerun.

The only deviation after the formal run began is Addendum A1 (see 3.3): it handles calls that "could not connect to the server", which is a different situation from the mid-sampling disconnections addressed in v0.6; it changes only the inclusion rules for codex and does not change any hypothesis or analysis.

Every analysis devised only after the formal results had been seen (for example, the candidate-level readings in the Results section) is labelled as exploratory.
