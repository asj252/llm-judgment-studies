<!-- source: results-zh.md v0.2 -->

## 4 Results

### 4.1 Sample and completeness

All planned units of the three configurations were fully reconciled (every planned unit accounted for) (Table 1). qwen3-off and codex had no missing units; olmo2 was missing 3 units (0.12%), all under multi-estimate elicitation, and following the pre-specified rule we computed an additional conservative interval with worst-case imputation of missing units. No attempt was truncated. The formal run of codex was rerun under a new experiment fingerprint (a hash binding the plan, sampling, prompts, parser, runner and materials) after Addendum A1 (calls that fail to connect to the server do not invalidate the session); the earlier results do not enter the analysis.

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

### 4.6 Summary

1. All three configurations move in the annotated direction in response to a single-sentence update, with a directional movement of about 19 to 25 points; counted by update condition, 16%–29% of update sentences left the reported probability of the local models unchanged.
2. When the update is recast as an anonymous report, movement becomes smaller and more items move in the reverse direction; the direction is consistent across the three configurations, and only for codex does the point estimate reach 5 points.
3. Multi-estimate elicitation substantially reduces endpoint values; in the local models, the mean directional movement also decreases by about 43% and 68%, zero movement decreases and reverse movement increases; for codex the directional movement decreases by about 2.5 points, with the point estimate below the SESOI. In the exploratory analysis, the top-weighted candidate of olmo2 also moves only about 5.5 points, and that of qwen3-off about 14 points; the sources of these differences cannot at present be distinguished.
