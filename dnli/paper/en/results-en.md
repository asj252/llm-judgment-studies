<!-- source: results-zh.md v0.2 -->

## 4 Results

Sections 4.1–4.5 report the three original configurations (Qwen3, OLMo-2, codex); Section 4.6 reports the four extension configurations run with the same protocol; Section 4.7 adds an exploratory analysis of candidate spread for all seven; Section 4.8 summarizes the confirmatory results.

### 4.1 Sample and completeness

All planned units of the three original configurations were fully reconciled (every planned unit accounted for) (Table 1). qwen3-off and codex had no missing units; olmo2 was missing 3 units (0.12%), all under multi-estimate elicitation, and following the pre-specified rule we computed an additional conservative interval with worst-case imputation of missing units. No attempt was truncated. The formal run of codex was rerun under a new experiment fingerprint (a hash binding the plan, sampling, prompts, parser, runner and materials) after Addendum A1 (calls that fail to connect to the server do not invalidate the session); the earlier results do not enter the analysis.

**Table 1. Sample and completeness**

| Configuration | Pairs | Planned units | Valid | Missing | First-attempt parse rate (v2, formal set r0) | Mean first-attempt time |
|---|---|---|---|---|---|---|
| Qwen3-8B (thinking off, local) | 240 | 2600 | 2600 | 0 | 100% | 4.8 s |
| OLMo-2-7B-Instruct (local) | 240 | 2600 | 2597 | 3 | 98.9% | 2.1 s |
| codex (gpt-6.1-sol, medium) | 120 | 1400 | 1400 | 0 | 100% | 13.4 s |

(Each pair has 10 conditions; in addition, the 20 pairs of the repeat subset were each asked once more. Parsing rule v2 was revised after the development-set smoke test according to the types of format failure, without looking at the probability values; under the old parsing rule v1, the first-attempt parse rates are 77%, 58% and 100%.)

### 4.2 Directional sensitivity (H1)

Under stated presentation and direct elicitation, all three configurations moved in the direction annotated for the update, and for all three the Holm-adjusted bound exceeds the smallest effect size of interest (SESOI) of 5 points (Table 2; Figure 1): the directional movement *s* is 18.6, 20.0 and 25.3 points. On average, strengtheners raised the probability by 15.9, 14.4 and 25.9 points, and weakeners lowered it by 21.3, 25.6 and 24.7 points; the difference D between the posteriors after strengtheners and after weakeners is 37.2, 40.1 and 50.6 points, respectively.

Item by item, the proportion of moves whose direction agrees with the annotation is 0.66, 0.55 and 0.83, and the proportion of reverse moves is 0.15, 0.16 and 0.09; the remainder report the same number before and after (qwen3-off: 23% for strengtheners, 16% for weakeners; olmo2: 29% for both; codex: 9% and 8%). That is, counted by update condition, 16%–29% of update sentences left the reported probability of the local models unchanged.

### 4.3 Reporting wording (H2)

When the same update was rephrased as "Someone said that …", the directional movement became smaller in all three configurations: stated minus reported is 2.0, 4.8 and 5.4 points (Table 2). All three pass the directional test under Holm correction. For codex the point estimate reaches the 5-point SESOI, but the Holm-adjusted bound (3.85) does not exceed it; for the two local configurations the point estimate is below the SESOI.

The **reversal rate** under reported presentation is higher than under stated presentation in all three configurations: qwen3-off 0.146 → 0.173, olmo2 0.163 → 0.221, codex 0.092 → 0.117. Following the pre-specified interpretation rule, we state the conclusion as **reporting shifts the direction of movement**: after the update is recast as a report, movement in the annotated direction is smaller, and at the same time more items move in the opposite direction. This is not the same as "discounting within the same direction."

Broken down by update type (descriptive; no per-type tests were run, and there is no evidence of equivalence), the three configurations show different patterns (Table 3): for olmo2 the difference lies almost entirely in strengtheners (stated +14.4, reported +4.7), while the means for weakeners are close (−25.6 vs. −25.7; equivalence not tested); for codex the difference lies mainly in weakeners (−24.7, −16.5); for qwen3-off both types decrease only slightly. This is a post hoc observation, offered only as exploratory description.

**Table 3. Mean probability change by update type (direct elicitation; points)**

| Configuration | Strengthener, stated | Strengthener, reported | Weakener, stated | Weakener, reported |
|---|---|---|---|---|
| Qwen3 (thinking off) | +15.9 | +15.0 | −21.3 | −18.3 |
| OLMo-2 | +14.4 | +4.7 | −25.6 | −25.7 |
| codex | +25.9 | +23.3 | −24.7 | −16.5 |

### 4.4 Multi-estimate elicitation (H4a, H4b)

**Endpoints (H4a).** Under direct elicitation, a large share of responses fall at ≤5% or ≥95% (Figure 2 shows the unweighted rate in each condition): the endpoint rate, computed with the pre-specified weights (prior 1/2, stated strengthener 1/4, stated weakener 1/4), is 29.6%, 42.0% and 25.2%. With multi-estimate elicitation (listing 5 estimates, each with a weight, and taking the weighted mean), it drops to 4.3%, 4.9% and 14.4%. The differences 0.25, 0.37 and 0.11 all pass Holm correction; for the two local configurations the adjusted bound exceeds the SESOI of 10 percentage points, while for codex the point estimate reaches the SESOI but the adjusted bound does not (Table 2).

**Directional sensitivity (H4b).** Multi-estimate elicitation reduces the directional movement: multi-estimate minus direct is −7.9, −13.7 and −2.5 points. For the two local configurations the adjusted bound lies beyond −5 points (the whole interval falls below −5 points); for codex the direction is confirmed and the point estimate is below the SESOI (Table 2).

Taken together, multi-estimate elicitation reduced endpoint values in all three configurations; in the two local models it also reduced the mean directional movement, by about 43% (qwen3-off 18.6 → 10.7) and 68% (olmo2 20.0 → 6.3, 238 pairs), respectively; for codex the directional movement decreased by about 2.5 points (25.3 → 22.8), with the direction confirmed and the point estimate below the 5-point SESOI.

Viewed by update condition, the change in the local models is not merely a smaller magnitude: under multi-estimate elicitation, **the proportion of zero movement falls and the proportion of reverse movement rises**. Zero movement: qwen3-off strengtheners 22.9% → 4.6%, weakeners 16.3% → 5.8%; olmo2 29.2% → 0.4%, 29.2% → 1.3%. Reverse movement: qwen3-off 0.14 → 0.34, 0.15 → 0.24; olmo2 0.17 → 0.41, 0.16 → 0.40. The pooled agreement rate, however, did not fall (qwen3-off 0.658 → 0.658, olmo2 0.546 → 0.586): update sentences that originally produced no movement moved, under multi-estimate elicitation, some in the annotated direction and some in the opposite direction. For codex the reversal rate is similar to that under direct elicitation (0.067 → 0.067, 0.117 → 0.125), and the pooled agreement rate goes from 0.825 to 0.871.

**Candidate level (descriptive).** Under the stated condition, the weighted standard deviation of the 5 estimates is 16.1 points for qwen3-off, 18.3 points for olmo2 and 7.6 points for codex. The proportion of responses whose weights sum to a value in [0.95, 1.05] is 93–94% for qwen3-off, 22–29% for olmo2 and 100% for codex (non-conforming weights are normalized by their sum; the weighted mean is invariant to overall scaling).

**Readings within the candidates (exploratory, not pre-specified).** To distinguish "the weighted mean pulls dispersed candidates toward the middle" from "the candidates themselves move little", we recomputed the directional movement post hoc with two other readings: the top-weighted candidate and the weighted median (Table 4). For qwen3-off, switching to the top-weighted candidate shrinks the difference from direct elicitation from −7.9 to −4.6 points (a reduction of about 42%), and the directional movement of the top-weighted candidate remains about 14.0 points; for olmo2 the top-weighted-candidate difference is −14.5 points, larger than that of the weighted mean, and its directional movement is only about 5.5 points; for codex all three readings are around −2 points. This describes only the size of the differences under different readings and does not support attributing a mechanism: model capability, vendor, training method and CLI harness are confounded with one another, and the present data also cannot separate the two explanations "candidates interfere with one another" and "format burden". These analyses were conceived only after we had seen the formal results and are offered only as exploration.

**Table 4. Directional movement under the three multi-estimate readings minus direct elicitation (stated; points; brackets give 95% cluster bootstrap (resampling images) intervals, 2000 resamples, seed 20261490, from the same computation as Figure 3)**

| Configuration | Candidate weighted SD (stated) | Weighted mean | Top-weighted candidate | Weighted median |
|---|---|---|---|---|
| Qwen3 (thinking off) | 16.1 | −7.9 [−9.7, −6.2] | −4.6 [−6.4, −2.7] | −6.7 [−8.5, −4.9] |
| OLMo-2 | 18.3 | −13.7 [−16.1, −11.3] | −14.5 [−17.0, −11.9] | −12.8 [−15.3, −10.2] |
| codex | 7.6 | −2.5 [−3.2, −1.8] | −2.1 [−2.8, −1.4] | −2.3 [−3.0, −1.7] |

### 4.5 Robustness and supplementary description

- **Quoted-speech updates** (updates whose reported version becomes quoted speech embedded in a report; pre-specified; of the 11 IDs on the frozen list, the formal set contains 7 sentences, involving 7 pairs): after excluding these 7 pairs and recomputing, the H1, H2 and H4b conclusions are unchanged in all three configurations (e.g., H2: 2.05, 4.92, 5.48 points; codex was run only on Block A, leaving 117 pairs after exclusion).
- **The common 120 pairs**: on the same 120 pairs used for codex, the two local configurations' point estimates for H1, H2, H4a and H4b have the same direction as on the 240 pairs, although the values differ (e.g., olmo2 H1 22.0 vs. 20.0, H2 6.2 vs. 4.8; for qwen3-off, H2 is 1.7 points, with interval [−0.6, 3.9] spanning 0). Cross-configuration comparisons are descriptive only.
- **Stratification by material source** (the dev and test splits of δ-SNLI, unrelated to this study's development set): the direction is consistent across the two strata; H2 is larger on items from dev in all three configurations.
- **Between-call variability** (repeat subset of 20 pairs): when the same prompt was asked a second time, the mean absolute difference between the two reported values was 9.6, 7.7 and 2.3 points under direct elicitation, and 7.7, 9.5 and 2.0 points under multi-estimate elicitation. Under stated presentation, the mean absolute difference in *s* is 5.7, 7.2 and 2.3 points, whereas the between-item standard deviation is 16.9, 23.7 and 15.3 points. Single reported values from the local models are very noisy; the conclusions rest on averages over 240 pairs and are not suited to interpreting individual items.
- **Comparison with the development set**: on the development set (30 pairs), H2 was 4.3, 4.6 and 5.7 points (7.0 for codex on the development set rerun after Addendum A1); on the formal set, qwen3-off is about half its development-set value, and the others are close. The H4b pattern of "large differences for the local models, a small difference for codex" recurs in the formal set.

**Table 2. Confirmatory tests (one Holm family {H1, H2, H4a, H4b} per configuration; intervals are two-sided 95% cluster bootstrap (resampling images) intervals on the common complete set; "Bound" is the Holm-adjusted bound nearer zero: the one-sided bound for H1, H2 and H4a, and the end of the two-sided interval nearer zero for H4b)**

| Configuration | Test | n | Point estimate | 95% interval | Holm α | Bound | Judgment |
|---|---|---|---|---|---|---|---|
| Qwen3 | H1 movement (points) | 240 | 18.6 | [16.5, 20.7] | 0.0125 | 16.1 | The adjusted bound exceeds the SESOI |
| | H2 stated − reported (points) | 240 | 2.0 | [0.4, 3.6] | 0.05 | 0.6 | Direction confirmed; point estimate below the SESOI |
| | H4a endpoint-rate difference (proportion) | 240 | 0.25 | [0.21, 0.29] | 0.0167 | 0.21 | The adjusted bound exceeds the SESOI |
| | H4b multi-estimate − direct (points) | 240 | −7.9 | [−9.7, −6.2] | 0.025 | −6.0 | The adjusted bound exceeds the SESOI |
| OLMo-2 | H1 | 240 | 20.0 | [17.4, 22.7] | 0.0125 | 17.1 | The adjusted bound exceeds the SESOI |
| | H2 | 240 | 4.8 | [2.4, 7.2] | 0.0167 | 2.3 | Direction confirmed; point estimate below the SESOI |
| | H4a | 237 | 0.37 | [0.33, 0.42] | 0.025 | 0.33 | The adjusted bound exceeds the SESOI (worst-case imputation of missing units) |
| | H4b | 238 | −13.7 | [−16.1, −11.2] | 0.05 | −11.0 | The adjusted bound exceeds the SESOI (worst-case imputation of missing units) |
| codex | H1 | 120 | 25.3 | [22.6, 27.8] | 0.0125 | 22.3 | The adjusted bound exceeds the SESOI |
| | H2 | 120 | 5.4 | [3.9, 7.0] | 0.0167 | 3.8 | The point estimate reaches the SESOI, but the adjusted bound does not |
| | H4a | 120 | 0.11 | [0.075, 0.14] | 0.025 | 0.075 | The point estimate reaches the SESOI, but the adjusted bound does not |
| | H4b | 120 | −2.5 | [−3.2, −1.8] | 0.05 | −1.8 | Direction confirmed; point estimate below the SESOI |

(SESOI: 5 points for H1, H2 and H4b; 10 percentage points for H4a. All 12 tests reject the null hypothesis under Holm correction, and there are no results in the opposite direction. H4b is signed as "multi-estimate < direct", and the bound is taken at the end nearer zero. For olmo2, the H4a and H4b judgments use the conservative bounds after worst-case imputation of missing units.)

### 4.6 Extension: four further configurations (v2)

The four extension configurations (Section 3.3) were run on the same 120 Block-A pairs and the same 20-pair repeat subset as codex, with the same prompts, parser (with one input normalization; Section 3.3), hypotheses, SESOIs and Holm families; each configuration forms its own family {H1, H2, H4a, H4b}. All planned units were reconciled and none were missing (Table 6). Retries were rare: in the final records, 5, 5, 8 and 5 earlier attempts were discarded, almost all because the event stream contained a step other than the answer (classified as possible tool use and resampled), and three because of a timeout; counted by the run's persistent retry counter, which also covers sessions that were later resumed, gemini-3.8-flash (low) had 10 retries and the others 5. According to the run log, six units of gemini-3.8-flash (low) were blocked at least once by the provider's content filter, which surfaced as such a step; one of them was blocked three times in a row and stopped the run. On review (recorded in the run's review log), the stop was cleared once so that the unit could be retried, because blocks appeared to be stochastic (other conditions of the same pair had passed on retry); we decided at the same time that units blocked persistently would be recorded as missing and reported in an addendum. The retried unit was answered on its next attempts, so this provision was never needed. All six units therefore have valid answers, and no unit is missing for this reason. Service errors that occurred before a conversation started also stopped the run and were cleared under a written rule before resuming (Section 3.6); such calls produced no answer and leave no attempt in the analysed record.

**Table 6. Sample and completeness (extension)**

| Configuration | Pairs | Planned units | Valid | Missing | First-attempt success (formal set r0) | Mean first-attempt time |
|---|---|---|---|---|---|---|
| gpt-oss-120b (medium) | 120 | 1400 | 1400 | 0 | 99.7% | 9.1 s |
| claude-sonnet-5.5 (medium) | 120 | 1400 | 1400 | 0 | 99.7% | 10.2 s |
| gemini-3.8-flash (low) | 120 | 1400 | 1400 | 0 | 99.4% | 9.6 s |
| gemini-3.8-flash (high) | 120 | 1400 | 1400 | 0 | 99.6% | 19.1 s |

**Table 7. Confirmatory tests (extension; same layout as Table 2; n = 120 for every test; "—" = not rejected under Holm, so no bound is reported)**

| Configuration | Test | Point estimate | 95% interval | Holm α | Bound | Judgment |
|---|---|---|---|---|---|---|
| gpt-oss-120b | H1 movement (points) | 17.6 | [15.0, 20.2] | 0.0125 | 14.5 | The adjusted bound exceeds the SESOI |
| | H2 stated − reported (points) | 0.9 | [−0.9, 2.7] | 0.05 | — | Not rejected; direction not established |
| | H4a endpoint-rate difference (proportion) | 0.10 | [0.067, 0.142] | 0.0167 | 0.065 | The point estimate reaches the SESOI, but the adjusted bound does not |
| | H4b multi-estimate − direct (points) | −2.3 | [−4.1, −0.6] | 0.025 | −0.3 | Direction confirmed; point estimate below the SESOI |
| claude-sonnet-5.5 | H1 | 22.0 | [19.4, 24.6] | 0.0125 | 19.0 | The adjusted bound exceeds the SESOI |
| | H2 | 3.1 | [1.8, 4.5] | 0.0167 | 1.7 | Direction confirmed; point estimate below the SESOI |
| | H4a | 0.065 | [0.038, 0.094] | 0.025 | 0.038 | Direction confirmed; point estimate below the SESOI |
| | H4b | +0.5 | [−0.3, 1.3] | 0.05 | — | Not rejected; direction not established |
| gemini-3.8-flash (low) | H1 | 26.6 | [23.6, 29.6] | 0.0125 | 23.2 | The adjusted bound exceeds the SESOI |
| | H2 | 4.1 | [2.4, 5.9] | 0.0167 | 2.2 | Direction confirmed; point estimate below the SESOI |
| | H4a | 0.16 | [0.123, 0.204] | 0.025 | 0.12 | The adjusted bound exceeds the SESOI |
| | H4b | −2.5 | [−3.7, −1.4] | 0.05 | −1.4 | Direction confirmed; point estimate below the SESOI |
| gemini-3.8-flash (high) | H1 | 28.3 | [25.6, 31.0] | 0.0125 | 25.1 | The adjusted bound exceeds the SESOI |
| | H2 | 4.1 | [2.7, 5.8] | 0.0167 | 2.5 | Direction confirmed; point estimate below the SESOI |
| | H4a | 0.090 | [0.056, 0.123] | 0.025 | 0.056 | Direction confirmed; point estimate below the SESOI |
| | H4b | −3.7 | [−5.1, −2.5] | 0.05 | −2.5 | Direction confirmed; point estimate below the SESOI |

(No unit was missing, so no worst-case imputation was needed. No result fell in the direction opposite to a one-sided prediction.)

**Directional sensitivity (H1).** All four configurations moved in the annotated direction, and for all four the adjusted bound exceeds the 5-point SESOI: *s* = 17.6, 22.0, 26.6 and 28.3 points. The difference between the posteriors after a strengthener and after a weakener, D, is 35.2, 44.0, 53.3 and 56.6 points. Zero movement under stated presentation was less common than in the local models (6.7%–15.0% of update conditions, against 16%–29%).

**Reporting wording (H2).** Recasting the update as a report reduced the directional movement in three configurations (3.1, 4.1 and 4.1 points; direction confirmed, point estimates below the SESOI); for gpt-oss-120b the difference was 0.9 points and the direction was not established. As in the original three configurations, the reversal rate was higher under reported than under stated presentation in all four (0.163 → 0.192, 0.079 → 0.125, 0.062 → 0.092 and 0.050 → 0.079), so under the pre-specified rule the conclusion is again worded as "reporting shifts the direction of movement". By update type (descriptive), the reduction lay mainly in weakeners for claude-sonnet-5.5 (−18.6 → −13.9) and gemini-3.8-flash (low) (−26.4 → −19.6), and was spread over both types for gemini-3.8-flash (high) (+27.9 → +24.9; −28.7 → −23.5).

**Multi-estimate elicitation (H4a, H4b).** The weighted endpoint rate under direct elicitation was 14.4%, 24.0%, 38.8% and 32.3%, and under multi-estimate elicitation 4.2%, 17.5%, 22.5% and 23.3%. The reduction passed Holm correction in all four configurations; only for gemini-3.8-flash (low) does the adjusted bound exceed the 10-point SESOI. The change in directional sensitivity was small: −2.3, +0.5, −2.5 and −3.7 points (direction confirmed in three configurations, point estimates below the SESOI; not established for claude-sonnet-5.5). The pattern seen in the local models recurs on a smaller scale: under multi-estimate elicitation, zero movement almost disappears (at most 3.3% of update conditions), the reversal rate rises (pooled: 0.163 → 0.212, 0.079 → 0.117, 0.062 → 0.133, 0.050 → 0.113), and the pooled agreement rate does not fall (0.746 → 0.783, 0.846 → 0.875, 0.804 → 0.846, 0.846 → 0.887). The weighted standard deviation of the five candidates under stated presentation was 14.0 points for gpt-oss-120b and 6.3–7.5 points for the other three; every multi-estimate response had weights summing to a value in [0.95, 1.05].

**Robustness (pre-specified).** Excluding the three Block-A pairs with quoted-speech updates (117 pairs remaining) leaves every conclusion unchanged (e.g., H2: 0.85, 3.07, 4.16 and 4.19 points). Stratified by material source, H2 was larger on δ-SNLI dev items for two configurations and on test items for the other two, unlike the original three configurations, where it was larger on dev items in all three. Between-call variability was small except for gpt-oss-120b: on the repeat subset, the mean absolute difference in *s* between two calls of the same prompt was 5.9, 1.4, 2.3 and 1.4 points, against between-item standard deviations of 17.5, 14.5, 15.5 and 14.7 points.

**Reasoning effort (descriptive only).** The two gemini-3.8-flash configurations differ only in reasoning effort. On the common 120 pairs, high minus low effort was +1.7 points for H1 (descriptive 95% interval [0.3, 3.2]), 0.0 for H2 ([−1.9, 2.0]), −0.073 for H4a ([−0.110, −0.037]) and −1.3 for H4b ([−2.7, 0.1]). These contrasts are not part of any Holm family.

### 4.7 Candidate spread (exploratory, not pre-specified)

Under multi-estimate elicitation each response gives five candidate probabilities with weights, so it also carries a spread: the weighted standard deviation of the candidates (weights normalized to sum to 1; SD = √Σ wᵢ(xᵢ − m)², where m is the weighted mean). We asked three questions after seeing the formal results: does the spread shrink after an update, is it larger after a report than after a stated update, and do items with a more dispersed prior move more? Intervals are cluster-bootstrap 95% intervals (B = 2,000, seed 20261500); none of these analyses enters a Holm family.

**Table 8. Candidate spread (stated and reported posteriors versus prior; points, with the change as a percentage of the reference spread)**

| Configuration | Prior spread | Stated posterior minus prior | Reported minus stated | Spearman ρ (prior spread, *s*) |
|---|---|---|---|---|
| Qwen3 (thinking off) | 15.8 | +0.3 (+2%) | −2.1 (−13%) [−2.8, −1.5] | 0.09 [−0.04, 0.21] |
| OLMo-2 | 17.5 | +0.8 (+4%) | 0.0 (0%) [−0.8, 0.9] | 0.10 [−0.03, 0.22] |
| codex | 9.2 | −1.6 (−18%) | +0.7 (+9%) [0.3, 1.0] | 0.15 [−0.05, 0.33] |
| gpt-oss-120b | 15.7 | −1.7 (−11%) | +0.9 (+7%) [0.1, 1.7] | 0.08 [−0.11, 0.25] |
| claude-sonnet-5.5 | 7.0 | −0.7 (−10%) | +0.6 (+9%) [0.3, 0.9] | 0.31 [0.13, 0.48] |
| gemini-3.8-flash (low) | 9.0 | −1.5 (−17%) | +0.4 (+6%) [−0.01, 0.86] | 0.24 [0.04, 0.42] |
| gemini-3.8-flash (high) | 8.8 | −1.3 (−15%) | +0.8 (+11%) [0.4, 1.3] | 0.26 [0.08, 0.43] |

("Stated posterior minus prior" averages the strengthener and weakener changes; its percentage is relative to the prior spread. "Reported minus stated" pools strengtheners and weakeners; its percentage is relative to the stated-posterior spread.)

The two local models show no consistent pattern: in Qwen3 a stated strengthener widened the spread (+2.6 points) and a weakener narrowed it (−2.1), so the average barely moves, and after a report the spread was smaller, not larger; in OLMo-2 the changes were near zero. The five configurations accessed through agent harnesses behave alike: after a stated update the spread narrowed by 10%–18% of the prior spread (mainly after weakeners in the four extension configurations), and after a report it was 6%–11% wider than after the same update stated (the interval excludes zero in four of the five). In claude-sonnet-5.5 and both gemini-3.8-flash configurations, items with a more dispersed prior also moved more (ρ = 0.24 to 0.31); in the other four configurations the correlation was weak (0.08 to 0.15) and its interval included zero. These are small absolute differences (under 2 points of spread) and were examined only post hoc. In the harnessed configurations the candidate spread thus shows the pattern one would expect of an expression of uncertainty (narrowing with information, staying wider for hearsay), whereas in the two small local models it does not show this pattern; there is no independent measure of uncertainty against which to check either, and the present data cannot say whether this reflects model scale, the harnesses, or training.

### 4.8 Summary

1. All seven configurations move in the annotated direction in response to a single-sentence update; the directional movement ranges from about 18 to 28 points, and for every configuration the adjusted bound exceeds the 5-point SESOI.
2. Recasting the update as an anonymous report reduces the movement in all seven point estimates (0.9 to 5.4 points) and raises the reversal rate in all seven. The direction is confirmed in six configurations (2.0 to 5.4 points); for gpt-oss-120b it is not established. The point estimate reaches 5 points only for codex, and no adjusted bound exceeds 5 points.
3. Multi-estimate elicitation reduces endpoint values in all seven configurations (the adjusted bound exceeds 10 percentage points in three). Its cost in directional sensitivity is large in the two local models (−7.9 and −13.7 points, adjusted bounds beyond −5); in the five configurations accessed through agent harnesses the point estimates lie between −3.7 and +0.5 points, the direction is confirmed in four, and no clear change is detected for claude-sonnet-5.5. Wherever zero movement was common under direct elicitation, multi-estimate elicitation replaced it with a mixture of agreeing and reversed movement.
