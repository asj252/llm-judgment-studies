# 实验 3（英文活动边界消歧版）S1 提示模板与修饰语模具预览（无上游原题文本版）

- 依据：`PLAN.md` 第 5、10 节（CC BY-NC 4.0 原题不进 git）与 `exp3-en/PLAN-E3.md` 第 2、3 节。
- 含开发集 20 簇完整句面的本地预览文件路径：`exp3-en/data/s1_preview_e3.md`（SHA-256：`72d071989b2faa2441dacee1ffd659a50984d5d9c89e76b2277cade1702c130e`）。

## 1. 三类闭集修饰语最小对模具（`SUBCLASS_MODIFIERS`）

- `A_plan_task`（20 簇：开发集 5 簇、正式集 15 簇）：
  - `h_occ = f"{h_base} for at least a short time."`
  - `h_plan = f"{h_base} all the way to completion."`
- `A_plan_deg`（4 簇：开发集 3 簇、正式集 1 簇）：
  - `h_occ = f"{h_base} at least partially."`
  - `h_plan = f"{h_base} completely."`
- `A_pure`（76 簇：开发集 12 簇、正式集 64 簇）：
  - `h_occ = f"{h_base} for at least a short time."`
  - `h_plan = f"{h_base} throughout the entire period."`

## 2. 13 个（任务 × 提示）组合逐字模板（占位符 `<PREMISE>` / `<HYPOTHESIS>`）

### `L/Z`
**Role: `system`**
```text
System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.
If the Hypothesis MUST be true based only on the Premise, output "True".
If the Hypothesis is contradicted by the Premise, output "False".
If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".
Do not use common sense assumptions. Only use the text provided.
```
**Role: `user`**
```text
User Input: Premise: <PREMISE> Hypothesis: <HYPOTHESIS>
Please respond with ONLY one of the following options: "True", "False", or "Unknown".
```

### `L/DAP`
**Role: `system`**
```text
System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.
If the Hypothesis MUST be true based only on the Premise, output "True".
If the Hypothesis is contradicted by the Premise, output "False".
If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".

Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.
- For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.
- For activities (e.g., "was running", "was singing"), the process implies the action occurred.
Do not use common sense assumptions. Only use the text provided.
```
**Role: `user`**
```text
User Input: Premise: <PREMISE> Hypothesis: <HYPOTHESIS>
Please respond with ONLY one of the following options: "True", "False", or "Unknown".
```

### `L/CoT`
**Role: `system`**
```text
System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.
If the Hypothesis MUST be true based only on the Premise, output "True".
If the Hypothesis is contradicted by the Premise, output "False".
If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".
Do not use common sense assumptions. Only use the text provided.
```
**Role: `user`**
```text
Premise: <PREMISE>
Hypothesis: <HYPOTHESIS>

Instruction: First, analyze the temporal status of the event in the premise. Does the action have a defined endpoint? Was it completed? Then, provide your final label (True, False, or Unknown).

Output Requirement: You must output your response in strict JSON format containing exactly two keys:
1. "reasoning": A string explaining your step-by-step logic.
2. "label": The final judgment ("True", "False", or "Unknown").

Do not include markdown formatting (like ```json). Return ONLY the JSON object.
Example Format:
{
  "reasoning": "The premise describes a process...",
  "label": "True" / "False" / "Unknown"
}
```

### `L/CF`
**Role: `system`**
```text
System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.
If the Hypothesis MUST be true based only on the Premise, output "True".
If the Hypothesis is contradicted by the Premise, output "False".
If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".
Do not use common sense assumptions. Only use the text provided.
```
**Role: `user`**
```text
Premise: <PREMISE>
Hypothesis: <HYPOTHESIS>

Instruction: 
1. First, list 3 possible real-world scenarios where the action in the premise occurs but the result in the hypothesis is NOT achieved (e.g., interruptions, failures).
2. Based on these possibilities, determine if the hypothesis is necessarily true.

Output Requirement: You must output your response in strict JSON format containing exactly two keys:
1. "possible_interruptions": a list of three strings for 3 possible real-world scenarios.
2. "label": The final judgment ("True", "False", or "Unknown").

Do not include markdown formatting (like ```json). Return ONLY the JSON object.
Example Format:
{
  "possible_interruptions": ["..."],
  "label": "True" / "False" / "Unknown"
}
```

### `Ps/Z`
**Role: `system`**
```text
System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.
If the Hypothesis MUST be true based only on the Premise, output "True".
If the Hypothesis is contradicted by the Premise, output "False".
If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".
Do not use common sense assumptions. Only use the text provided.
```
**Role: `user`**
```text
User Input: Premise: <PREMISE> Hypothesis: <HYPOTHESIS>
What is the probability that the Hypothesis is necessarily true given only the Premise?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
```

### `P/Z`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
```

### `P/DAP`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.
- For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.
- For activities (e.g., "was running", "was singing"), the process implies the action occurred.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
```

### `P/CoT`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

First, analyze the temporal status of the event in the situation. Does the action have a defined endpoint? Was it completed? Then give your answer.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
```

### `P/CF`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

First, list 3 possible real-world scenarios where the action in the situation occurs but the result in the statement is NOT achieved (e.g., interruptions, failures). Then give your answer.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
```

### `M/Z`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.
```

### `M/DAP`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.
- For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.
- For activities (e.g., "was running", "was singing"), the process implies the action occurred.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.
```

### `M/CoT`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

First, analyze the temporal status of the event in the situation. Does the action have a defined endpoint? Was it completed? Then give your answer.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.
```

### `M/CF`
**Role: `user`**
```text
Here is a situation: <PREMISE>.

Using common sense, how likely is it that the following statement is true?
Statement: <HYPOTHESIS>.

First, list 3 possible real-world scenarios where the action in the situation occurs but the result in the statement is NOT achieved (e.g., interruptions, failures). Then give your answer.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.
```

