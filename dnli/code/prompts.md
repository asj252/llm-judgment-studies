# 提示模板与渲染样例（δ-NLI 实验；PLAN v0.2 第 3 节；任务书第 3 步）

- 实现：`prompts.py`（纯函数；模板文字由 `prompts.templates()` 汇总，进实验指纹的 `templates` 项）。全英文；冻结前送 c。
- 来源：改写自 `../suppression/prompts.py`。沿用 `Probability: NN%` 的格式说明与末行 `Do not use any tools; answer directly.`（codex 隔离要求，四个配置同一提示）。去掉演绎／日常指示与前提列表。
- 不出现的内容（c 第一轮阻断 4、建议 12）：「前提绝对为真」；「但我不确定是不是真的」之类的明说不确定；加强／削弱标签；不要求五个估计彼此不同（阻断 1）。
- 三种呈现 × 两种问法 = 6 种提示；后验另分 S／W（只换更新句）。每对每配置 10 次调用：先验 2 ＋ 后验 2 类型 × 2 呈现 × 2 问法；陈述与转述共用同一问法下的先验。

## 1 模板

各段以空行相连：`情境块`、`问题块`、`问法尾段`、`末行`。情境块的行之间只有换行。

| 片段 | 文字 |
|---|---|
| 情境（三种呈现都有） | `Here is a situation: {P}` |
| 陈述后验的第二行 | `Here is something else you learned: {U}` |
| 转述后验的第二行 | `Someone said that {u}` |
| 问题块（两行） | `Using common sense, how likely is it that the following statement is true?⏎Statement: {H}` |
| 末行 | `Do not use any tools; answer directly.` |

- `{P}`、`{U}`、`{H}` 都先过句末标点规则 `terminate()`；`{u}` 是 `lower_initial(U)` 再过 `terminate()`。先验没有第二行。

### 1.1 直接问法尾段

```text
What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
```

### 1.2 多估计问法尾段（VS 启发；PLAN 第 3 节原句＋格式说明）

```text
Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.
```

- 第一句照 PLAN 第 3 节原文；之后的格式说明是 e 加的（解析需要）：每行 `Estimate k: NN% | Weight: W`。解析规则见 `parse.py` 文件头。

## 2 机械规则（写死；见 `prompts.py` 文件头）

- **句末标点** `terminate()`：去首尾空白；以 `.` `!` `?` 结尾（其后可再跟右引号或右括号）就不动，否则补 `.`。P、H、U 同一规则；句中文字（拼写错误、双空格、弯引号、句首小写）一律不改。
- **首字母小写化** `lower_initial()`（只用于转述）：按第一个词判断——1 不以字母开头 → 不改；2 已小写 → 不改；3 代词 I／I'… → 不改；4 词内还有大写（缩写、McX）→ 不改；5 在专有名词表 `PROPER_INITIAL` → 不改；6 其余 → 首字符小写。
- `PROPER_INITIAL = ['Batman', 'Christmas', 'Sally', 'Gone', 'Mom']`：检查 δ-SNLI dev＋test 全部 3,622 句有效更新句（129 个不同的句首词）定出，与抽到哪些题无关。全集上的命中：规则 6 小写化 3,526 句、规则 2 已小写 89 句、规则 5 专有名词 6 句（dev:659 Batman、dev:848 与 test:625 Christmas、test:27 Sally、test:327 Gone、test:1915 Mom）、规则 1 引号开头 1 句（dev:375）。
- **所选 150 对、300 句更新句**：规则 6 小写化 294 句、规则 2 已小写 6 句；规则 1、3、4、5 都没有命中（所以没有受专有名词例外影响的题）；补句点 39 句。由 `render_check.py` 计算，明细见 `raw/render_check.md`。

## 3 一题渲染样例（开发集 `2817132182.jpg#2r1n`；S＝dev:1639，W＝dev:1642）

数据来自 δ-SNLI（SNLI 的 CC BY-SA 4.0）。下面 6 个提示逐字是送给受测者的 user 消息正文（本地模型另由聊天模板包装，codex 经 stdin 送入）（W 的两种后验只把更新句换成削弱句，见 `raw/render_check.md`）。

### 先验 × 直接

```text
Here is a situation: A woman is sitting outside while holding two cats.

Using common sense, how likely is it that the following statement is true?
Statement: This person likes cats.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.

Do not use any tools; answer directly.
```

### 先验 × 多估计

```text
Here is a situation: A woman is sitting outside while holding two cats.

Using common sense, how likely is it that the following statement is true?
Statement: This person likes cats.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.

Do not use any tools; answer directly.
```

### 陈述后验 S × 直接

```text
Here is a situation: A woman is sitting outside while holding two cats.
Here is something else you learned: The woman was petting both cats.

Using common sense, how likely is it that the following statement is true?
Statement: This person likes cats.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.

Do not use any tools; answer directly.
```

### 陈述后验 S × 多估计

```text
Here is a situation: A woman is sitting outside while holding two cats.
Here is something else you learned: The woman was petting both cats.

Using common sense, how likely is it that the following statement is true?
Statement: This person likes cats.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.

Do not use any tools; answer directly.
```

### 转述后验 S × 直接

```text
Here is a situation: A woman is sitting outside while holding two cats.
Someone said that the woman was petting both cats.

Using common sense, how likely is it that the following statement is true?
Statement: This person likes cats.

What is the probability that the statement is true?

On the last line of your answer, give the answer strictly in the following format:
Probability: NN%
where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.

Do not use any tools; answer directly.
```

### 转述后验 S × 多估计

```text
Here is a situation: A woman is sitting outside while holding two cats.
Someone said that the woman was petting both cats.

Using common sense, how likely is it that the following statement is true?
Statement: This person likes cats.

Give 5 probability estimates that the statement is true, each with a weight for how likely you think that estimate is; the weights sum to 1.

At the end of your answer, give the 5 estimates strictly in the following format, one per line:
Estimate 1: NN% | Weight: W
Estimate 2: NN% | Weight: W
Estimate 3: NN% | Weight: W
Estimate 4: NN% | Weight: W
Estimate 5: NN% | Weight: W
where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.

Do not use any tools; answer directly.
```
