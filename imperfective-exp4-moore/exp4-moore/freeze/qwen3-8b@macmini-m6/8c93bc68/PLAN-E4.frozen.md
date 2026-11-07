# 实验 4（摩尔悖论与多维判准版）：言语行为信念冲突（Moore's Paradox）之单链 CoT 教科书反射坍缩 vs. Verbalized Sampling 多候选假说拆解（计划草案 v0.3）

- 实例：`#imperfective`；计划树节点：`P16.8`；日期：2026-11-06；起草：`a`；S0–S1 独立审查：`c`（`review-plan-e4-codex.md`，总体判定：**无阻断**）。
- 状态：**草案 v0.3（已完成 S0–S1 100 簇材料构造与 17/17 负向突变自检、独立认证 Tango 查表 `SUPPORTED_NS = (5, 20, 80)`、13 条件解析/协议自检与 `s1_preview_e4.md` 预览，`c` 首轮独立审查无阻断并已采纳全部非阻断润色建议，待用户确认 S1 预览）**。
- 上游依据：
  1. 总计划 `../PLAN.md`（保持只读，不改动其 SHA-256）；
  2. 实验 1 冻结规范 `../s5-mac-handoff-20261101/PLAN-E1.md` 与正式集报告 `../s5-mac-handoff-20261101/results/report-s7-formal.md`；
  3. 实验 2 冻结规范 `../exp2-zh/PLAN-E2.md` 与正式集报告 `../exp2-zh/report-s6-s7-formal-e2.md`；
  4. 实验 3 冻结规范 `../exp3-en/PLAN-E3.md` 与正式集报告 `../exp3-en/report-s6-s7-formal-e3.md`；
  5. 摩尔悖论目标基线论文：**Zheng et al. (2026)**, *"Assertion and Belief: Moore's Paradox in Language Models"*, `arXiv:2610.25586`（知识库证据卡 `../../../lit_kb/papers/zheng2026_moore.md`）；
  6. 跨篇 VS 格式与 Logprobs 消融实证报告：`../../dnli-api/REPORT_ABLATION_VS_FORMAT_LOGPROBS.md` 及格式防呆协议 `../PROTOCOL_NOTE_VS_FORMAT_FOR_E3_E4.md`。
- **实验隔离铁律**：本实验全部材料、代码、提示模板、解析器副本、精确 Tango 查表清单、账本与冻结记录均 100% 独立存放并构建于 `connecting-dots/imperfective/exp4-moore/`，运行 ID 前缀为 `E4-`，**绝不读取或修改 `exp1-en/`、`exp2-zh/`、`exp3-en/` 或 `PLAN.md` 的任何已冻结文件**。本实验 100 簇场景材料均为原创自编英文语料，无任何第三方版权受限文本。

---

## 1. 研究动机、理论同构性、测量边界与三大硬性格式准则

### 1.1 为什么在 `#imperfective` 论文中纳入摩尔悖论实验（Exp 4）？
在前三项预注册正式集实验（英文 Exp 1 `a6c90b5`、中文 Exp 2 `a42fbbe`、英文边界消歧 Exp 3 `d793eaa`，合计 **12,480 个正式推理单元**）中，我们揭示了一个贯穿语义—语用边界的核心规律：
- **现有文献的方法论盲区（Single-Chain CoT Collapse）**：无论是未完成体悖论领域的 **Ma & Miyao (2026)**、**Han & Sun (2026)**，还是言语行为与摩尔悖论领域的 **Zheng et al. (2026, `arXiv:2610.25586`)**，现有研究**全部依赖单一轨迹思维链（Single-Chain CoT）或单点输出**。
  - 在未完成体悖论中，单链 `L/CoT` 触发教条式规则反射（「进行体不能保证完成」），导致无界活动 `D` 组准确率从 `100.0%` 崩塌至 `8.75%`（Exp 1 `SA4`，`91.25%` 退向 `Unknown`），甚至在假说句已显式写明 `for at least a short time` 的最低发生读法下仍将 `97.50%`（`78/80`）的未受阻活动坍缩为 `Unknown`（Exp 3 `E3_H4`）。
  - 在摩尔悖论（形如 `"p, but I do not believe that p"`，如 Zheng et al. 2026 §2.1 的高空玻璃栈道案例 *"The skywalk is safe, but I do not believe it is"*）中，Zheng et al. (2026) 对 1,741 条 CoT 轨迹的标注揭露：单链 CoT 下高达 **`89%+`** 的模型轨迹实为**点名背诵 `"Moore's paradox"` 教科书标签的条件反射**，直接将句面锁死为「自相矛盾」；而在人类与模型认可摩尔句可理解的真实语境中，核心机制恰恰是**「双重判准重新诠释（Dual-Criteria Reinterpretation，占 34.0%）」**与**「词义/标准多义性拆解（Polysemy / Criteria Shift，占 11.1%）」**。
- **未完成体悖论与摩尔悖论的底层数学同构（Multi-Criteria & Alternative Hypotheses）**：
  - **未完成体悖论**：前半句进行体 $P$ 满足**局部动作发生判准（$H_{\text{occ}}$）**，但未满足或受阻于**全局目标完结判准（$H_{\text{plan}} / H_{\text{comp}}$）**；
  - **摩尔悖论（Dual-Criteria Moorean Statements）**：前半句断言 $p$ 满足**局部/客观技术指标判准（$p_{\text{local/obj}}$，如工程荷载达标、项目账面指标达成、体检化验单合格、程序合规签字）**，而后半句撤回信念 $\neg B(p)$ 针对的是**全局/主观零危机稳态判准（$p_{\text{global/subj}}$，如悬崖锚栓开裂、系统深层崩溃隐患、潜在复发危机、实质合规失效）**。
  - 单一轨迹 `CoT` 只能沿着一条主导解释路径（表面句法规则反射）坍缩；而我方提出的 **Verbalized Sampling (`VS / Task M`)** 在单次贪婪解码（`temperature = 0`）中通过**序列内自我条件化（In-Context Sequential Conditioning）**同时展开 5 个竞争诠释假说与口述机率分布，在抑制纯单维矛盾幻觉的同时保留双重判准的语用融贯空间。
- **确认性结论与机制解释边界（对齐 Exp 2 / Exp 3 严谨措辞原则）**：
  - 本实验的 4 个主确认假设（`E4_H1`–`E4_H4`）严格用于**确认实验 4 内部由受控语境槽位（`PURE_MOORE / DUAL_MOORE / DUAL_EXPLICIT / PURE_READ`）与提问接口（`M_U / P / L` 及 `Z / CoT / CF`）所引起的模型读数差异**（不单凭槽位读数差越界宣称向任意未抽样自然语言话语总体外推，亦不在主确认结论中脱离第 3 层文本轨迹分类而单独声称内部心理因果机制）。
  - 由于正式集 80 簇按 4 个语义领域子类（`D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`，正式集各 $n = 20$）分层构成，**主报告在给出全部 80 个正式簇汇总确认检验（`E4_H1`–`E4_H4`）的同时，必须在正文中紧跟并列报告 4 个领域子类（各 $n = 20$）的分层点估计与置信区间**。

### 1.2 跨篇消融实证锁定的三大硬性设计准则（源自 `REPORT_ABLATION_VS_FORMAT_LOGPROBS.md`）
基于 `#connecting-dots/dnli-api` 完成的 1,500 单元 OpenAI `1+4` 格式与 Token Logprobs 消融实验（`../../dnli-api/REPORT_ABLATION_VS_FORMAT_LOGPROBS.md`）及 `../PROTOCOL_NOTE_VS_FORMAT_FOR_E3_E4.md`，本实验严格执行以下 3 条铁律：
1. **铁律 1（严禁在数值机率任务中使用纯 JSON 输出格式 `V3`，沿用 5 行管线格式与 `PARSE_VERSION = 2`）**：
   - 消融实证证明：强制模型直接输出纯 JSON（`V3`）会因剥夺自然语言缓冲而将细粒度语义辨识度 $H_1$ 腰斩 **49%**（从 5 行管线格式 `V0` 的 `+26.49` 跌至 `+13.40`）。
   - 因此，`exp4-moore` 的所有数值机率任务（`Ps / P / M`）**严禁挂载任何要求输出 JSON 的系统提示**，`Task M` 一律继续沿用 `exp1`–`exp3` 的 5 行管线格式 `Estimate k: NN% | Weight: W` 与 `parse.py`（`PARSE_VERSION = 2`：自动提取最后一个 `Estimate 1..5` 区块 `starts[-1]` 并对正权重和 $\sum W_k > 0$ 自动归一化）。
2. **铁律 2（假说文字诠释置前、结尾固定纯数值 5 行，杜绝行内文字污染 Parser）**：
   - `parse.py` 的 `parse_multi` 对每一行 `Estimate k: NN% | Weight: W` 执行严格数值扫描：在 `Estimate k:` 与 `%` 之间仅允许出现单一数字 `NN`；同时 `protocol.py` 要求回答最后 5 个非空行严格匹配 `Estimate k: NN% | Weight: W`。若将竞争假说的文字说明写进 `Estimate k:` 行内，一旦文字偶发包含数字（如 `2 criteria`）或 `%`，将直接触发 `estimate_range_or_extra_number` 解析报错。
   - 因此，在需要模型显式写出 5 个竞争假说文字诠释的机率条件（`P/CF` 与 `M/CF`）中，提示词强制要求模型**先在前面独立段落写出 5 条编号为 `Interpretation 1:` 至 `Interpretation 5:` 的简短诠释说明（提示不在该段落使用词 `"Estimate"`、`"Probability:"` 或 `"%"` 符号），随后空一行，在回答最末尾仅输出纯数值答案行（`Probability: NN%` 或 5 行 `Estimate k: NN% | Weight: W`）**。
3. **铁律 3（论文方法论与 Token Logprobs 背书引用）**：
   - 在本实验报告与论文方法论章节中，直接引用 `../../dnli-api/REPORT_ABLATION_VS_FORMAT_LOGPROBS.md` 作为选用 5 行管线格式 `V0`、等权/加权聚合（`M_U` / `M_W`）以及「单点 `D0` 首数值 Token 熵显著低于多候选 `V0`（`0.765` vs `1.261` bits）」的跨篇实证背书。

---

## 2. 实验材料设计：100 组场景簇 × 4 槽位正交最小对（`data/clusters_100_e4.json`）

为与实验 1、2、3 保持完全一致的统计检验力、样本量结构与查表基础设施，本实验由 `exp4-moore/curate_100_clusters_e4.py`（SHA-256 `07bf41530b2a96fbb53e16391e70b1347f963d3472477260d3541fcfc873123e`）确定性构建 **100 个原创英文摩尔悖论场景簇（Cluster `001`..`100`）**：
- 数据文件：`exp4-moore/data/clusters_100_e4.json`（SHA-256 `f0a2de8192a1c7321e8903818920036b8dcce1b607644f4c3381a5d41768b3f3`）；
- 子类清单：`exp4-moore/subclasses_e4.json`（SHA-256 `77b1874bba695c33197c8898afa23285186525ed20593f9e9407446fce754bc4`）；
- 切分清单：`exp4-moore/split.json`（SHA-256 `1552968c6b597b37b18eb349ba81f0c08e0faa037d66bfcf468bb2a5d8055731`，种子 `2026110601`）。

### 2.1 四大语义领域子类（`domain_subclass`，全集 100 簇，每领域 25 簇：开发集 5 簇 / 正式集 20 簇）
1. **`D1_safety`（工程技术指标达标 vs. 切身运行/环境危机，对接 Zheng et al. 2026 `Skywalk` 原型，簇 `001`..`025`，共 25 簇）**：
   - 例：高空玻璃栈道通过静态荷载测试但悬崖主锚栓被落石砸出严重裂纹（`001`）；暴雪山地接驳车在测试道障碍识别完美但下坡路段覆盖隐形黑冰（`002`）等。
2. **`D2_project`（局部账面/阶段指标成功 vs. 全局系统架构危机，对接核心洞见「局部成功 vs. 危机四伏」，簇 `026`..`050`，共 25 簇）**：
   - 例：新版软件按期上线且首日吞吐量达标但底层未修补内存泄漏正逼近全网崩溃（`026`）；移动应用注册安装数达标但超九成新用户几分钟内卸载（`029`）等。
3. **`D3_medical`（单项化验/筛查指标正常 vs. 临床深层病变/复发危机，簇 `051`..`075`，共 25 簇）**：
   - 例：白血病术后常规外周血白细胞计数回到正常区间但骨髓穿刺检出恶性原始细胞急剧增殖（`051`）；静息心电图显示窦性心律但动态监测记录到劳力性多形性室速（`052`）等。
4. **`D4_institutional`（程序/字面合规核查通过 vs. 实质治理失效/系统性风险，簇 `076`..`100`，共 25 簇）**：
   - 例：商业信贷风控模型通过年度历史回测核查表但宏观利率冲击已引发模型假设视为不可能的大面积企业违约（`082`）；商业银行账面一级资本充足率达标但存款挤兑已耗尽流动性且未对冲长债亏损超过全部股东权益（`100`）等。

### 2.2 簇内确定性生成公式与 4 主槽 + 2 诊断槽定义
每个簇 $k \in \{001, \dots, 100\}$ 在 `RAW_CLUSTER_SPECS` 中具有唯一议题 `topic_label`、唯一说话者 `speaker`、单维原子事实命题 `p_atomic_cap`（首字母小写形式 `p_atomic_low = "t" + p_atomic_cap[1:]`）、可双判准评估的核心命题 `p_core_cap`（首字母小写形式 `p_core_low = "t" + p_core_cap[1:]`）、单维语境 `pure_context`、双重判准张力语境 `dual_context`、朗读测试语境 `reading_context`、正向全达标语境 `all_clear_context` 以及局部标准修饰语 `local_mod` 与全局标准修饰语 `global_mod`。

令：
- `moore_atomic_quote = f"{p_atomic_cap}, but I do not believe that {p_atomic_low}."`
- `moore_core_quote = f"{p_core_cap}, but I do not believe that {p_core_low}."`
- `explicit_core_quote = f"{p_core_cap} {local_mod}, but I do not believe that {p_core_low} {global_mod}."`

同一簇内全部 6 个单元（4 主槽 + 2 诊断槽）共享**逐字全等的统一目标假设 `hypothesis`（记为 $H_{\text{coh}}$）**：
$$\text{hypothesis} = \text{``\{speaker\}'s utterance in this context is coherent and does not commit \{speaker\} to a self-contradiction.''}$$
> **统一假设句的语义—语用严密性**：使用 `"is coherent and does not commit {speaker} to a self-contradiction"` 直接锁定说话者在当前语境中的**言语行为承诺（pragmatic commitment）**——在 `PURE_READ`（照剧本朗读台词测试麦克风而不表达个人信念）中，尽管被朗读的台词字面含摩尔句式，但说话者的朗读行为并未使其背负自相矛盾的信念承诺，故在 `PURE_READ` 与 `DUAL_EXPLICIT` 下均为融贯无矛盾，而在 `PURE_MOORE` 下则使说话者背负直接自相矛盾。

四个正交主实验槽位（共 $100 \times 4 = 400$ 条主实验题）与两个诊断槽位（共 $100 \times 2 = 200$ 条诊断题）由以下确定性公式生成：

| 槽位名称 | 单元 ID 格式 | 确定性前提生成公式（`premise`） | 理论预期与测量定位 |
| :--- | :--- | :--- | :--- |
| **`PURE_MOORE`**<br>（单维原子事实 + 裸摩尔断言） | `PURE_MOORE_<cid>` | `f'{pure_context} Looking directly at that single unambiguous indicator, {speaker} sincerely asserts: "{moore_atomic_quote}"'` | **单维矛盾下界锚点（Floor Anchor）**：针对单一无歧义指标作第一人称摩尔断言，构成真正的单判准信念冲突。 |
| **`DUAL_MOORE`**<br>（双重判准危机语境 + 裸摩尔断言） | `DUAL_MOORE_<cid>` | `f'{dual_context} Speaking about the situation as a whole, {speaker} sincerely says: "{moore_core_quote}"'` | **核心攻防测试槽（Target Paradox Slot）**：语境同时交代局部技术达标与全局严重危机，说话者说出表面未加修饰的裸摩尔句；单链 `CoT` 易触发教科书标签反射而压低读数，多候选 `VS (M_U/CF, M_U/Z)` 可拆解双重判准而恢复融贯度读数。 |
| **`DUAL_EXPLICIT`**<br>（双重判准危机语境 + 显式双标准消歧句） | `DUAL_EXPLICIT_<cid>` | `f'{dual_context} Speaking about the situation as a whole, {speaker} sincerely says: "{explicit_core_quote}"'` | **显式双判准上界锚点（Explicit Dual-Criteria Upper Anchor）**：与 `DUAL_MOORE` 共享 100% 逐字全等的语境前缀，仅在引语内显式插入 `local_mod` 与 `global_mod`（严格双槽位修饰语最小对）。 |
| **`PURE_READ`**<br>（取消断言承诺控制槽：照剧本朗读测试麦克风） | `PURE_READ_<cid>` | `f'{reading_context} While reading a printed drama script line aloud to test the microphone (without stating any personal beliefs), {speaker} reads the line: "{moore_atomic_quote}"'` | **取消断言控制槽（Cancelled-Assertion Control，对接 Zheng et al. 2026 `Reading Aloud`）**：引号内台词与 `PURE_MOORE` 100% 逐字全等，但明确取消个人信念断言承诺。 |
| **`DIAG_POS`**<br>（正向极性诊断槽） | `DIAG_POS_<cid>` | `f'{all_clear_context} Speaking about the situation as a whole, {speaker} sincerely says: "{p_core_cap}, and I fully believe that {p_core_low}."'` | **管道与正向极性健全性检查**（仅在 S3/S4 跑 `L/Z, P/Z, M/Z`）：局部与全局均达标且真诚肯定相信；S4 要求 `P/Z` 均值 $\ge 80.0$。 |
| **`DIAG_NEG`**<br>（负向极性诊断槽） | `DIAG_NEG_<cid>` | `f'{pure_context} Looking directly at that single unambiguous indicator, {speaker} sincerely asserts: "{p_atomic_cap}, and at the exact same time and in the exact same sense it is false that {p_atomic_low}."'` | **管道与负向极性健全性检查**（仅在 S3/S4 跑 `L/Z, P/Z, M/Z`）：单一指标下显式同义同时逻辑矛盾；S4 要求 `P/Z` 均值 $\le 20.0$。 |

> **诊断语境的解释边界（对齐 Exp 3 `PLAN-E3.md` §2.2(5)）**：`DIAG_POS` 与 `DIAG_NEG` 仅作为提示渲染管道、数值解析与极性方向的健全性检查（pipeline & polarity sanity check），不作为主实验双重判准语用消歧独立成立的证据。在 S4 开发集报告中，除检验 20 簇总体均值门槛（`P/Z` 下 `mean(Pos) >= 80.0` 且 `mean(Neg) <= 20.0`）外，还必须按 4 个 `domain_subclass`（各 $n=5$）分别报告均值与逐簇明细。

### 2.3 五项机械硬性护栏与 17 项负向突变自检（`validate_materials_e4.py`）
由 `exp4-moore/validate_materials_e4.py`（SHA-256 `eef0f594d2c4574f13430d8ab735aa6f775d50206b0a2f4d49e037aa6d0cb135`）在内存中强制执行全量核验（实测 **100/100 簇 0 错误，17/17 项负向突变自检全部拦截**，其中结构突变 `M1`–`M15` 在开启与关闭 `check_raw_spec_binding` 两种模式下均被独立拦截）：
1. **原始规范与三大清单逐项全等绑定**：
   - `clusters_100_e4.json`、`subclasses_e4.json`、`split.json` 必须分别与 `build_clusters_obj()`、`build_subclasses_manifest()`、`build_split_manifest()` 的确定性重建结果逐字段全等；
   - 每簇 12 个原始字段必须与 `RAW_CLUSTER_SPECS[idx]` 逐字全等，且 `domain_subclass, topic_label, speaker, local_mod, global_mod` 必须与 `subclasses_e4.json["clusters"][cid]` 逐字全等；
   - 全集 100 簇的 `cluster_id`（`001`..`100`）、`topic_label`、`speaker`、`p_core_cap`、`p_atomic_cap`、`pure_context`、`reading_context`、`dual_context`、`all_clear_context`、`local_mod`、`global_mod` 均 **100/100 互异（零重复）**。
2. **唯一说话者锁定与 `DUAL_EXPLICIT` / `DUAL_MOORE` 严格最小对恒等式**：
   - 每簇 6 个前提与 `hypothesis` 均包含该簇唯一 `speaker`；
   - `p_dual_moore` 与 `p_dual_explicit` 严格共享相同前缀 `f'{dual_context} Speaking about the situation as a whole, {speaker} sincerely says: "'`；
   - 从 `p_dual_explicit` 依次删去一次 `f" {local_mod}"` 与一次 `f" {global_mod}"` 后，必须与 `p_dual_moore` **逐字符完全相等**，且 `p_dual_moore` 中严禁泄漏 `local_mod` 或 `global_mod`。
3. **`PURE_MOORE` 与 `PURE_READ` 句内摩尔引语逐字全等及统一假设句锁定**：
   - `p_pure_moore` 与 `p_pure_read` 必须以逐字相同的双引号摩尔句 `f'"{p_atomic_cap}, but I do not believe that {p_atomic_low}."'` 结尾；
   - 每簇 `hypothesis` 必须严格等于 `f"{speaker}'s utterance in this context is coherent and does not commit {speaker} to a self-contradiction."`。
4. **前提禁漏元语言标签词、禁含数字/`%` 与禁连续重复词护栏**：
   - 全部 6 个前提（`p_pure_moore, p_dual_moore, p_dual_explicit, p_pure_read, p_diag_pos, p_diag_neg`）及全部原始组件字段中，严禁出现以下 17 个元语言或剧透词项（大小写不敏感）：`"moore"`, `"moorean"`, `"paradox"`, `"paradoxical"`, `"contradict"`, `"contradiction"`, `"contradictory"`, `"coherent"`, `"incoherent"`, `"coherence"`, `"pragmatic"`, `"pragmatically"`, `"dual criteria"`, `"polysemy"`, `"polysemous"`, `"entail"`, `"entailment"`；
   - 全部 6 个前提与 `hypothesis` 中严禁出现任何阿拉伯数字 `[0-9]`、百分号 `%` 或连续重复英文单词（正则 `\b([A-Za-z]+)\s+\1\b`）。
5. **诊断模板绑定与分层切分锁定（`split.json`，种子 `2026110601`）**：
   - 使用 `random.Random(2026110601)` 按 `("D1_safety", "D2_project", "D3_medical", "D4_institutional")` 顺序从每个领域的 25 个簇中无放回抽取 5 个开发簇，合成 **开发集 20 簇**（`["002", "003", "012", "016", "020", "029", "038", "039", "046", "049", "051", "058", "059", "068", "071", "082", "087", "090", "092", "100"]`，每领域精确 5 簇，展开为 80 条主实验题 + 40 条诊断题）与 **正式集 80 簇**（其余 80 簇，每领域精确 20 簇，展开为 320 条主实验题）；
   - **S3 冒烟集（`smoke`）**固定取开发集升序前 3 簇 `["002", "003", "012"]`（3 簇 = 12 条主实验题 + 6 条诊断题 = **174 单元**，与实验 2、3 冒烟规模完全一致）。
   - 17 项负向突变自检（`M1`–`M17`）覆盖上述全部护栏及 `subclasses_e4.json` 单独篡改（`M16`）、整簇协调替换（`M17`），实测 `17/17` 全部拦截。

---

## 3. 任务、英文提示模板与输出解析协议（`prompts_e4.py`）

### 3.1 13 个 `(task, prompt)` 条件与单元规模（与实验 1、2、3 完全同构）
- **13 个条件**：`L/Z, L/DAP, L/CoT, L/CF, Ps/Z, P/Z, P/DAP, P/CoT, P/CF, M/Z, M/DAP, M/CoT, M/CF`。
- **单元规模**：
  - **S3 冒烟（`smoke`）**：`3 簇 × 4 主槽 × 13 条件 = 156 主单元` + `3 簇 × 2 诊断槽 × 3 零样本条件（L/Z, P/Z, M/Z）= 18 诊断单元` = **`174 单元`**。
  - **S4 开发集（`dev`）**：`80 题 × 13 条件 = 1,040 主单元` + `40 诊断题 × 3 零样本条件 = 120 诊断单元` = **`1,160 单元`**。
  - **S6 正式集（`formal`）**：`320 题 × 13 条件 = 4,160 单元`。

### 3.2 逐字英文提示模板与解析器/协议全兼容核验（`prompts_e4.py`）
本实验提示词渲染器为 `exp4-moore/prompts_e4.py`（SHA-256 `63442bf71ec72a9b1e77a21f8abe4c62d3508cc5d46507ecf351799368971a90`），直接复用与 `exp1-en`、`exp3-en` **逐字节完全相同**的四个基础模块：
- `exp4-moore/parse.py`（SHA-256 `b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342`，`PARSE_VERSION = 2`）；
- `exp4-moore/prompt_parts.py`（SHA-256 `027a6329088a71bb18fe2d4ac8d4999bec00f34af707092c659d54d5f69b8e41`）；
- `exp4-moore/score.py`（SHA-256 `ce5a5ea26be775f6aa206c57ba0253cf57b9219730a0bd830187b021370e3f3a`，`VERSION = 1`）；
- `exp4-moore/protocol.py`（SHA-256 `8b427b57400016e50bdab458c4402efcfb80718541b78b9eb7ebc7baa55e6904`，`VERSION = 1`）。

各组件逐字文本如下：
1. **语用原则定义段 `DAP_RULE_E4`（用于 `L/DAP`, `P/DAP`, `M/DAP`，不剧透具体槽位名称）**：
   ```text
   Important Linguistic & Pragmatic Principle: Note the distinction between a single-standard assertion conflict and a multi-criteria or non-assertive utterance.
   - When a speaker sincerely asserts a single unambiguous atomic fact while simultaneously denying belief in that exact same fact under the same standard, the utterance commits the speaker to a self-contradiction.
   - When an utterance evaluates a situation across two distinct standards (such as local technical compliance versus broader systemic risk), or when a speaker merely reads a line aloud without asserting personal belief, the utterance can be coherent and does not commit the speaker to a self-contradiction.
   ```
2. **严格逻辑任务 `Task L`（`L/Z, L/DAP, L/CoT, L/CF`）与 `Ps/Z`**：
   - `L/Z`, `L/CoT`, `L/CF`, `Ps/Z` 的系统提示与 `exp1-en`/`exp3-en` 逐字相同（`L/DAP` 在系统提示中插入 `DAP_RULE_E4`）；
   - `L/CoT` 用户提示要求先在单链推理中分析说话者话语是否构成逻辑或语用矛盾，并输出仅含 `"reasoning"` 与 `"label"`（末键）的 JSON 对象；
   - `L/CF` 用户提示要求先列出 3 个影响说话者话语是否构成自相矛盾的竞争语境诠释或因素，并输出含 `"possible_interruptions"`（长度为 3 的字符串数组，100% 兼容 `parse.py:parse_label_json` 与 `protocol.py` 的 `n_interruptions == 3` 校验）与 `"label"`（末键）的 JSON 对象；
   - `Ps/Z` 用户提示与 `exp1-en`/`exp3-en` 的 `PS` 模板逐字相同（不含任何 JSON 指令，末尾输出 `Probability: NN%`）。
3. **常识单点机率 `Task P` 与多候选分布 `Task M`（仅单条 `user` 消息，零 JSON 指令，段间以 `\n\n` 连接）**：
   - 情境与陈述段：`"Here is a situation: " + terminate(premise)`、（仅 `DAP`）`DAP_RULE_E4`、`"Using common sense, how likely is it that the following statement is true?\nStatement: " + terminate(hypothesis)`；
   - `CoT` 推理指令 `INSTRUCTIONS_E4["CoT"]`：
     ```text
     First, analyze step by step in a single reasoning chain whether the speaker's utterance commits a logical or pragmatic contradiction (such as asserting a proposition while denying belief in it). Do not use the word "Estimate", the word "Probability:", or the "%" sign in your analysis paragraph. Then leave a blank line and give your final numerical answer.
     ```
   - `CF` 竞争假说展开指令 `INSTRUCTIONS_E4["CF"]`（严格落实铁律 2 段落分离，并显式规定多候选输出时 `Estimate 1..5` 为各 `Interpretation k` 下 Statement 为真的条件机率而 `Weight` 为该诠释的合理权重，回应 S1 审查疑问与 S3 冒烟格式对齐）：
     ```text
     Before giving your final answer, write 5 short lines in a separate paragraph listing 5 distinct candidate perspectives on whether the speaker's utterance is coherent in this situation (such as evaluating the utterance across two distinct standards—local technical compliance versus broader systemic risk—versus treating it as a single-standard conflict, pragmatic hedging, or non-assertive reading), labeled "Interpretation 1:" through "Interpretation 5:" (do not use the word "Estimate" or the "%" sign in those 5 lines). Then leave a blank line and give your final answer at the very end strictly in the format requested below (when giving 5 estimates, each Estimate k: NN% is the conditional probability from 0% to 100% that the Statement is true under Interpretation k—so the five NN% values do NOT sum to 100%—and Weight: W is how plausible Interpretation k is in this situation, with the five weights summing to 1).
     ```
   - 结尾格式指令（逐字节引自 `prompt_parts.py`）：
     - `Task P` 使用 `ASK_DIRECT`：
       ```text
       What is the probability that the statement is true?

       On the last line of your answer, give the answer strictly in the following format:
       Probability: NN%
       where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
       ```
     - `Task M` 使用 `ASK_MULTI`：
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
4. **S1 预览产物与解析兼容验证**：
   - `prompts_e4.py:verify_parser_compatibility()` 已验证全部 13 个条件在 `parse.py`（`PARSE_VERSION = 2`）与 `protocol.py`（`protocol_ok == True`）下 13/13 通过，并包含针对行内夹带含数字文字触发 `estimate_range_or_extra_number` 的负向回归测试；
   - 开发集 20 簇完整 6 槽题面与首个冒烟簇 `002` 之 `DUAL_MOORE_002` 全 13 条件逐字渲染预览已生成于 `exp4-moore/s1_preview_e4.md`（SHA-256 `29e6378c6beb1095add94a3b08a661a98f51895dc9d6296f5d9b5af31376932e`）。

---

## 4. 主确认检验家族（方案 E4，`m = 4`，$\alpha_{\text{fam}} = 0.05$）与封闭统计规范

### 4.1 四个主确认假设（`m = 4`，全部定义于正式集 $n = 80$ 簇，且底层 8 个实验单元两两完全不相交）

Holm 逐步检验固定破平顺序为 `E4_H1, E4_H2, E4_H3, E4_H4`：

| 编号 | 检验对象与簇集 | 统计量定义 $\theta_j$ | 零假设与备择方向 | 确认性结论用语（拒绝 $H_0$ 时，正文必须紧跟并列报告 `D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`［各 $n=20$］四领域分解效应） |
| :--- | :--- | :--- | :--- | :--- |
| **`E4_H1`**<br>双重判准摩尔句（`DUAL_MOORE`）之「VS 多候选假说展开 `M_U/CF` vs. 单链 `P/CoT`」机率读数差 | 正式集全部簇<br>（$n = 80$ 簇）<br>槽位：`DUAL_MOORE` | $\mu(\text{DUAL\_MOORE}; M_U/\text{CF}) - \mu(\text{DUAL\_MOORE}; P/\text{CoT})$<br>*(第 3 层并列报告 $M_U/\text{Z} - P/\text{CoT}$ 与 $M_W/\text{CF} - P/\text{CoT}$)* | $H_0: \theta_1 \le 0$<br>$H_1: \theta_1 > 0$<br>（单侧，整簇 bootstrap） | **方向确认**：「在双重判准危机语境的裸摩尔句槽位（`DUAL_MOORE`）上，多候选竞争假说分布 `M_U/CF` 的融贯度机率读数显著高于单链思维链单点估计 `P/CoT`」。 |
| **`E4_H2`**<br>零样本 VS 多候选 `M_U/Z` 下「双重判准摩尔句 `DUAL_MOORE` vs. 单维原子矛盾摩尔句 `PURE_MOORE`」机率读数差 | 正式集全部簇<br>（$n = 80$ 簇）<br>条件：`M_U/Z` | $\mu(\text{DUAL\_MOORE}; M_U/\text{Z}) - \mu(\text{PURE\_MOORE}; M_U/\text{Z})$<br>*(第 3 层并列报告 `M_U/CF` 与 `P/Z`)* | $H_0: \theta_2 \le 0$<br>$H_1: \theta_2 > 0$<br>（单侧，整簇 bootstrap） | **方向确认**：「在零样本多候选分布 `M_U/Z` 下，双重判准危机语境摩尔句（`DUAL_MOORE`）的融贯度机率读数显著高于单维原子事实摩尔句（`PURE_MOORE`）」。 |
| **`E4_H3`**<br>双重判准语境下「显式双标准消歧 `DUAL_EXPLICIT` vs. 隐式裸摩尔句 `DUAL_MOORE`」在 `P/Z` 上的单点机率差 | 正式集全部簇<br>（$n = 80$ 簇）<br>条件：`P/Z` | $\mu(\text{DUAL\_EXPLICIT}; P/\text{Z}) - \mu(\text{DUAL\_MOORE}; P/\text{Z})$ | $H_0: \theta_3 \le 0$<br>$H_1: \theta_3 > 0$<br>（单侧，整簇 bootstrap） | **方向确认**：「在双重判准危机语境的零样本单点估计 `P/Z` 下，显式标出局部与全局双标准的消歧句（`DUAL_EXPLICIT`）的融贯度机率读数显著高于未显式标出的裸摩尔句（`DUAL_MOORE`）」。 |
| **`E4_H4`**<br>单链 `L/CoT` 下「显式双标准消歧 `DUAL_EXPLICIT` vs. 隐式裸摩尔句 `DUAL_MOORE`」的 `True` 判定率差 | 正式集全部簇<br>（$n = 80$ 簇）<br>条件：`L/CoT` | $\Pr(\text{True on DUAL\_EXPLICIT}; L/\text{CoT}) - \Pr(\text{True on DUAL\_MOORE}; L/\text{CoT})$<br>*(第 3 层并列报告 `PURE_READ - DUAL_MOORE` 及 `L/CF` vs `L/CoT`)* | $H_0: \theta_4 \le 0$<br>$H_1: \theta_4 > 0$<br>（单侧，认证精确 Tango） | **方向确认**：「在离散三分类逻辑任务 `L/CoT` 下，显式双标准消歧句（`DUAL_EXPLICIT`）的 `True` 判定率显著高于隐式裸摩尔句（`DUAL_MOORE`）」（正文中并列报告完整 `{True, False, Unknown}` 三标签分布）。 |

> **底层实验单元两两不相交性核验与因子归因边界**：
> - `E4_H1` 使用 `(DUAL_MOORE, M_U/CF)` 与 `(DUAL_MOORE, P/CoT)`；
> - `E4_H2` 使用 `(DUAL_MOORE, M_U/Z)` 与 `(PURE_MOORE, M_U/Z)`；
> - `E4_H3` 使用 `(DUAL_EXPLICIT, P/Z)` 与 `(DUAL_MOORE, P/Z)`；
> - `E4_H4` 使用 `(DUAL_EXPLICIT, L/CoT)` 与 `(DUAL_MOORE, L/CoT)`。
> **以上 4 个主确认假设所依赖的 8 个 `(slot, task, prompt)` 底层实验条件两两 100% 不相交（零跨假设共享单元）**。
> - **因子归因口径约束**：`E4_H1` 检验的是同槽位（`DUAL_MOORE`）下「多候选假说展开接口 `M_U/CF` vs. 单链思维链单点接口 `P/CoT`」的联合方法对比，主确认结论仅陈述该联合对比方向，单因子拆解（`M_U/Z - P/CoT`、`M_U/CoT - P/CoT`、`P/CF - P/CoT`）固定在第 3 层并列报告；`E4_H2` 检验的是同条件（`M_U/Z`）下「双重判准危机语境摩尔槽 `DUAL_MOORE` vs. 单维原子事实摩尔槽 `PURE_MOORE`」的复合槽位对比（两者同时包含语境结构与核心/原子命题差异），而严格保持 `dual_context` 与 `p_core` 逐字不变的纯修饰语最小对效应则由 `E4_H3` 与 `E4_H4`（`DUAL_EXPLICIT` vs. `DUAL_MOORE`）专门承担。

### 4.2 封闭统计推断规范与 20 格校准矩阵（完全独立实现于 `exp4-moore/`）

1. **推断目标、整簇等权多项式重抽与统计声称边界**：
   - **推断目标**：本实验主确认分析的推断目标定义为当前 4 领域等配额设计下正式集 $n = 80$ 簇（每领域 20 簇）的簇平均效应（开发集为 $n_{\text{dev}} = 20$ 簇，每领域 5 簇）。
   - **共享整簇重抽流**：固定重抽次数 **`B = 5000`**；正式集分析种子 **`FORMAL_ANALYSIS_SEED_E4 = 2026110601`**，开发集分析种子 **`DEV_ANALYSIS_SEED_E4 = 2026110602`**。使用单一共享随机流 `rng = np.random.Generator(np.random.PCG64(seed))`，对按 `cluster_id` 升序排列的 $n$ 个簇（正式集 $n = 80$，开发集 $n = 20$）抽取单一共享权重矩阵 `w = rng.multinomial(n, np.full(n, 1.0 / n), size=B) / float(n)`（形状 `(B, n)`），同时用于连续三槽 `E4_H1, E4_H2, E4_H3`。第 3 层领域分解中针对 `D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`（正式集各 $n = 20$，开发集各 $n = 5$）的重抽，在同一 `rng` 之后严格按 `DOMAIN_SUBCLASSES = ("D1_safety", "D2_project", "D3_medical", "D4_institutional")` 顺序依次对各领域按 `cluster_id` 升序排列的子集调用 `rng.multinomial(n_sub, np.full(n_sub, 1.0 / n_sub), size=B) / float(n_sub)`。
   - **关于合并重抽与固定领域配额的统计声称边界及极端稀有尾部不覆盖声明（对齐 `PLAN-E2.md` §4.2(1) 与 `PLAN-E3.md` §4.2(1)）**：
     - 鉴于普通等权多项式 bootstrap 的条件方差本身不能直接推出分位数区间覆盖率或离散检验拒绝域在固定配额异质子类下的解析保序关系，本计划**不宣称全集合并重抽或汇总 Tango 查表对固定领域配额具有解析上的自动向上保守包络保证**。
     - `hybrid_pct_tango_e4` 与 `hybrid_bessel_t_tango_e4` 均严格定位为**待校准的有限样本近似推断程序**，其第一类错误率与覆盖率保护声明严格限定于下述第 5 条预注册的 **5 类 DGP $\times$ 4 类配置 = 20 格校准矩阵**（含 4 领域固定配额强异质情景 `DGP4_het` 与 70% 极端端点堆积 `DGP5_endpt`）实测验证通过的范围。
     - **极端稀有尾部反例风险与不覆盖范围声明**：本计划的候选推断程序**不声称**对任意有界分布均具有无条件有限样本保护，尤其明确不覆盖「总体零均值由极低概率（如 $p = 0.01$）极端反方向点质量与高概率（如 $1 - p = 0.99$）窄支撑正向质量相抵而成」的对抗性稀有尾部偏斜混合分布（例如以 $0.01$ 概率取 $-35.0$、以 $0.99$ 概率取均值 $+35/99$ 且半宽 $0.01$ 的均匀分布，在 $n = 80$ 下有 $0.99^{80} \approx 44.7523\%$ 的样本完全漏抽负尾点；在该类已验证的漏尾反例样本上，两套候选程序均不会触发退化规则且会给出全正置信区间与小 p 值而发生误拒）。因此，本计划明确将该类未观测稀有尾部极端混合分布排除在方法统计保证范围之外。

2. **连续配对差（`E4_H1`、`E4_H2`、`E4_H3`）的两套候选方法与退化规则**：
   - 对第 $i$ 个簇，设被比较两单元的上下界为 $[X_{i,\text{lower}}, X_{i,\text{upper}}]$ 与 $[Y_{i,\text{lower}}, Y_{i,\text{upper}}]$，定义簇内配对差下界 $d^L_i = X_{i,\text{lower}} - Y_{i,\text{upper}} \in [-100, 100]$ 与上界 $d^U_i = X_{i,\text{upper}} - Y_{i,\text{lower}} \in [-100, 100]$。观测均值上下界为 $\hat{\theta}^L_j = \frac{1}{n}\sum_{i=1}^n d^L_i$，$\hat{\theta}^U_j = \frac{1}{n}\sum_{i=1}^n d^U_i$；重抽均值序列为 $\theta^{*,L}_{j,b} = \sum_{i=1}^n w_{b,i} d^L_i$ 与 $\theta^{*,U}_{j,b} = \sum_{i=1}^n w_{b,i} d^U_i$（$b = 0, \dots, B-1$，$B = 5000$）。
   - **候选方法 1（默认主方法 `hybrid_pct_tango_e4`：未插值次序统计量 Percentile Bootstrap）**：
     - 对升序排序后的 $B = 5000$ 个下界重抽均值 $s_{\text{low},(0)} \le \dots \le s_{\text{low},(4999)}$ 与上界重抽均值 $s_{\text{high},(0)} \le \dots \le s_{\text{high},(4999)}$：
       - **双侧 98.75% Bonferroni 同时置信区间**（单项 $\alpha_{\text{ind}} = 0.0125$）：取 0-based 下标 **`idx_lo = 31`** 与 **`idx_hi = 4968`**，即 $[s_{\text{low},(31)}, s_{\text{high},(4968)}]$；
       - **双侧 95% 伴随置信区间**：取 0-based 下标 **`idx_lo_95 = 124`** 与 **`idx_hi_95 = 4875`**；
     - **单侧 p 值**：若观测点估计下界 $\hat{\theta}^L_j \le 0$，设 $p_j = 1.0$；若 $\hat{\theta}^L_j > 0$，则 $p_j = \frac{1 + \#\{b : \theta^{*,L}_{j,b} \le 0.0\}}{B + 1}$。
   - **候选方法 2 / 伴随敏感度方法（`hybrid_bessel_t_tango_e4`：保序 Bessel-$t$ 中心外扩 Bootstrap）**：
     - 对同一组重抽均值围绕观测点估计按 70 位 `Decimal` 高精度求根锁定的有限样本扩展因子 $c_n = \sqrt{\frac{n}{n-1}} \cdot \frac{t_{n-1,\, 0.99375}}{z_{0.99375}}$ 向外保序扩展（完整覆盖本实验全部 3 种预设样本量 $n \in \{5, 20, 80\}$）：
       - $c_{80} = 1.0298684039340296$（$\text{df} = 79$，正式集全集 $n=80$）
       - $c_{20} = 1.1331397732007173$（$\text{df} = 19$，开发集全集 $n=20$ 及正式集单领域子集 $n=20$）
       - $c_{5} = 1.9313454535930072$（$\text{df} = 4$，开发集单领域子集 $n=5$，80 位有效数字高精度算术向最近偶数 binary64 舍入）
     - 保序外扩公式 $\tilde{\theta}^{*,L}_{j,b} = \min(\theta^{*,L}_{j,b}, \hat{\theta}^L_j + c_n(\theta^{*,L}_{j,b} - \hat{\theta}^L_j))$、$\tilde{\theta}^{*,U}_{j,b} = \max(\theta^{*,U}_{j,b}, \hat{\theta}^U_j + c_n(\theta^{*,U}_{j,b} - \hat{\theta}^U_j))$、贪心锚点互异值计数（`_greedy_distinct_1d_sorted`，`TOL_DUST = 1e-12`）与裁剪前四项退化判据（`u_low < 20 or u_high < 20`、单流跨度 $\le 10^{-12}$、非有限或反序、外扩原始区间与 `[-100, 100]` 交集为空；触发任一条则 `degenerate = True, p = 1.0, ci = [-100.0, 100.0]`）与 `PLAN-E2.md` §4.2(2) 及 `PLAN-E3.md` §4.2(2) 完全一致。

3. **离散配对比例差（`E4_H4`）的认证精确无条件 Tango (1998) 规范**：
   - 定义簇内三值差 $d_i = \mathbb{I}(\text{label}_{i,\text{DUAL\_EXPLICIT}} = \text{True}) - \mathbb{I}(\text{label}_{i,\text{DUAL\_MOORE}} = \text{True}) \in \{-1, 0, +1\}$。
   - 由 `exp4-moore/exact_tango_e4.py`（SHA-256 `df21fd7a74d4fa1ee96b4b06f7b0d2fc4820f750aa9565a435024b183c85a4c6`）在本实验目录内 **100% 独立从头构建（零跨目录读取）** 并经精确 `Fraction` 算术认证生成：
     - `exp4-moore/manifests/exact-tango-tables-e4.npz`（`file_sha256 = e6378b3a1c85bf851ff623e906d50edb0572f2b282a3c66297483ef1a43ea3ff`，`payload_sha256 = b22aafc7e21787ead903540ac8312a48a1444f7c2627c8ce3813703556a04ddf`）；
     - `exp4-moore/manifests/exact-tango-tables-e4-meta.json`（SHA-256 `2ecabd0e9158dcc51b03dc1f46da6558602f364ce6fbd9744f2cb44fa83dd9e1`）；
     - 完整覆盖 **`SUPPORTED_NS = (5, 20, 80)`** 三种样本量（9/9 项左截断有理数证书通过，0 单调性违例）。
   - 单侧 p 值、双侧 98.75% Bonferroni 精确置信区间、缺失回退以及独立同分布三项模型假设与 4 领域固定配额异质性校准（`DGP4_het`）边界，与 `PLAN-E2.md` §4.2(3) 完全一致。

4. **`L` 首字母标签分数 `q`、单元四终结状态 `status`、最不利缺失界限传播与 Holm 流程**：
   - 与 `PLAN-E1.md` §3.2、§4.2(4) 及 `PLAN-E2.md` §4.2(4)-(5) 逐字一致：主确认分析严格仅在 `status == "ok"` 时代入观测点值，凡 `status != "ok"`（`missing_transport`、`missing_format`［含截断］、`missing_score`）一律代入最不利极值界（连续机率 `[0.0, 100.0]`，离散指示变量 `[0, 1]`）；对 `E4_H4` 固定并列输出 `label_available`（`status in ("ok", "missing_score")`）伴随诊断行；Holm 逐步检验（$m = 4, \alpha_{\text{fam}} = 0.05$）按固定编号顺序 `E4_H1, E4_H2, E4_H3, E4_H4` 破平。

5. **S4 统计校准核验的 20 格矩阵（5 DGP × 4 Cfg）、`DGP1_emp` 缺失处理与退出条件（`calibrate_e4.py`）**：
   - **模拟参数**：在 S4 开发集完成后、S5 冻结前，运行 `exp4-moore/calibrate_e4.py`，使用固定模拟种子 **`CALIB_SEED_E4 = 2026110611`**，针对正式集精确簇数 $n = 80$（4 个领域子类各 $20$ 簇）及 4 项家族（`E4_H1..E4_H4`），在 **5 类 DGP $\times$ 4 类真值/缺失配置 = 20 个校准格**上每格运行 **`R = 2000`** 次模拟，每次模拟内部调用 **`B = 5000`** 与 0-based 下标 **`idx_lo = 31, idx_hi = 4968`**（$\text{SE}_{\text{sim}} = \sqrt{0.05 \times 0.95 / 2000} \approx 0.0048734$）。
   - **8 个两两不相交底层实验条件与对称中心化配对读数生成机制**：
     - `E4_H1`（`DUAL_MOORE(M_U/CF)` vs `DUAL_MOORE(P/CoT)`）、`E4_H2`（`DUAL_MOORE(M_U/Z)` vs `PURE_MOORE(M_U/Z)`）、`E4_H3`（`DUAL_EXPLICIT(P/Z)` vs `DUAL_MOORE(P/Z)`）与 `E4_H4`（`DUAL_EXPLICIT(L/CoT)` vs `DUAL_MOORE(L/CoT)`）所使用的 **8 个底层 `(slot, task, prompt)` 实验条件两两完全不相交**。
     - 对每个模拟簇 $i \in \{1, \dots, 80\}$ 及连续槽 $j \in \{1, 2, 3\}$，给定目标真值 $\theta_j \in \{0.0, 20.0, 25.0, 15.0\}$ 与有界扰动 $\varepsilon_{j,i} \in [-35.0, +35.0]$，生成该槽两个不同条件下的**对称中心化配对底层条件读数**（满足 $X_{j,i} + Y_{j,i} = 100.0$）：
       $$X_{j,i} = 50.0 + \frac{\theta_j + \varepsilon_{j,i}}{2} \in [20.0, 80.0] \subset [0, 100], \qquad Y_{j,i} = 50.0 - \frac{\theta_j + \varepsilon_{j,i}}{2} \in [20.0, 80.0] \subset [0, 100]$$
       其簇内差恒为 $d_{j,i} = X_{j,i} - Y_{j,i} = \theta_j + \varepsilon_{j,i} \in [-35.0, +60.0] \subset [-100, 100]$。
     - 对离散槽 `E4_H4`（目标真值 $\theta_4 \in \{0.0, 0.35\}$），按合法单纯形参数化 $\tau(\theta_4) = \max(\tau_0, |\theta_4| + 0.10) \in [0.15, 0.80]$，$\pi_+ = (\tau + \theta_4)/2, \pi_- = (\tau - \theta_4)/2, \pi_0 = 1 - \tau$ 生成配对指示变量 $(I_{i,\text{EXP}}, I_{i,\text{MOORE}}) \in \{(1,0), (0,1), (0,0)\}$。
   - **5 类数据生成分布家族（DGP 1–5）**：
     1. `DGP1_emp`（开发集中心化有界经验残差与缺失处理规则）：
        - 对开发集 20 簇，令 $K_{\text{ok}, j} \subseteq \{1, \dots, 20\}$ 为第 $j \in \{1, 2, 3, 4\}$ 个槽位配对双方底层单元均满足 `status == "ok"` 的完整开发簇下标集。**硬性前置闸门**：要求所有 $j \in \{1, 2, 3, 4\}$ 均满足 $|K_{\text{ok}, j}| \ge 15$；若任一槽位完整开发簇数 $< 15$，直接触发停止规则 `insufficient_complete_dev_clusters_stop_s5`，严禁进入校准或 S5。
        - 设三项连续槽共同完整开发簇集为 $K_{\text{ok, joint}} = K_{\text{ok}, 1} \cap K_{\text{ok}, 2} \cap K_{\text{ok}, 3}$。若 $|K_{\text{ok, joint}}| \ge 15$，则在 $K_{\text{ok, joint}}$ 上按等权均值中心化 $r_{j, k} = d_{j, k} - \frac{1}{|K_{\text{ok, joint}}|} \sum_{m \in K_{\text{ok, joint}}} d_{j, m}$，令缩放因子 $\kappa_j = \min(1.0, 35.0 / \max(10^{-12}, \max_{m \in K_{\text{ok, joint}}} |r_{j, m}|))$，每个模拟簇 $i \in \{1, \dots, 80\}$ 从 $K_{\text{ok, joint}}$ 中等概（$1 / |K_{\text{ok, joint}}|$）抽取同一个开发簇下标 $k$，成组取出 $(\kappa_1 r_{1, k}, \kappa_2 r_{2, k}, \kappa_3 r_{3, k}) \in [-35.0, +35.0]^3$；若 $|K_{\text{ok, joint}}| < 15$（但各 $|K_{\text{ok}, j}| \ge 15$），则各连续槽 $j$ 分别在其自身 $K_{\text{ok}, j}$ 上中心化、缩放并等概抽取。
        - 对 `E4_H4`，在 $K_{\text{ok}, 4}$ 上计算经验不一致率 $\hat{\tau}_{\text{dev}} = \frac{1}{|K_{\text{ok}, 4}|} \sum_{k \in K_{\text{ok}, 4}} \mathbb{I}(d_{4, k} \ne 0)$，取 $\tau_0 = \text{clip}(\hat{\tau}_{\text{dev}}, 0.15, 0.80)$。
     2. `DGP2_skew`（有界强偏斜且簇内相关分布）：在每个簇 $i$ 上由三元标准正态 $(Z_1, Z_2, Z_3)$（两两相关系数 $\rho = 0.5$）经正态 CDF 与 $\text{Beta}(2, 8)$ 逆 CDF 变换得边际严格服从 $\text{Beta}(2, 8)$（精确均值 $0.2$）的 $(U_1, U_2, U_3)$，令 $\varepsilon_{j,i} = 40.0 \times (U_{j,i} - 0.2) \in [-8.0, +32.0]$（每簇精确均值 $0$）；`E4_H4` 取 $\tau_0 = 0.50$。
     3. `DGP3_ties`（高并列离散三点分布与低不一致率）：$\varepsilon_{j,i} \in \{-30.0, 0.0, +30.0\}$ 按概率 $(0.30, 0.40, 0.30)$ 独立抽取（每簇精确均值 $0$）；`E4_H4` 取 $\tau_0 = 0.15$。
     4. `DGP4_het`（4 个领域子类 `D1_safety`, `D2_project`, `D3_medical`, `D4_institutional` 各 $20$ 簇固定配额强异质性分布，领域内期望为 $\delta_h$、全集 80 簇配额加权平均期望精确为 $0$）：
        - 连续三槽（$j \in \{1, 2, 3\}$）：令 4 个领域子类（各 $20$ 簇，权重各 $20/80 = 0.25$）偏移分别为 $\delta_{D1} = +12.0, \delta_{D2} = +4.0, \delta_{D3} = -4.0, \delta_{D4} = -12.0$——全集加权平均期望恒为 $\frac{20(+12.0) + 20(+4.0) + 20(-4.0) + 20(-12.0)}{80} = 0.0$；每簇 $\varepsilon_{j,i} = \delta_{h(i)} + \eta_{j,i} \in [-32.0, +32.0] \subset [-35.0, +35.0]$，其中 $\eta_{j,i} \sim \text{Uniform}(-20.0, +20.0)$。
        - 离散槽（`E4_H4`，$80 = 20_{D1} + 20_{D2} + 20_{D3} + 20_{D4}$）：固定 $\tau_{\text{sub}} = 0.70$，令 4 个领域的三项均值差参数分别为 $\theta_{4,D1} = \bar{\theta}_4 + 0.15, \theta_{4,D2} = \bar{\theta}_4 + 0.05, \theta_{4,D3} = \bar{\theta}_4 - 0.05, \theta_{4,D4} = \bar{\theta}_4 - 0.15$（对 $\bar{\theta}_4 \in \{0.0, 0.35\}$ 均有 $|\theta_{4,Dh}| \le 0.50 < \tau_{\text{sub}} = 0.70$，保证所有 $\pi_+, \pi_-, \pi_0 \ge 0.10 > 0$，且 4 领域等权平均恒等于 $\bar{\theta}_4$）。
     5. `DGP5_endpt`（70% 极端边界端点堆积与高方差双峰分布）：
        - 连续三槽（$j \in \{1, 2, 3\}$）：$\varepsilon_{j,i} \in \{-35.0, 0.0, +35.0\}$ 按概率 $(0.35, 0.30, 0.35)$ 独立抽取（每簇精确均值 $0.0$，方差 $857.5$）；`E4_H4` 取边界低不一致率 $\tau_0 = 0.15$。
   - **4 类真值/缺失配置（Cfg A–D）**：
     1. `CfgA_all_null_comp`：$\boldsymbol{\theta} = (0.0, 0.0, 0.0, 0.0)$（$I_0 = \{1,2,3,4\}$），0% 缺失；
     2. `CfgB_half_null_comp`：$\boldsymbol{\theta} = (20.0, 0.0, 15.0, 0.0)$（$I_0 = \{2, 4\}$），0% 缺失；
     3. `CfgC_alt_null_comp`：$\boldsymbol{\theta} = (0.0, 25.0, 0.0, 0.35)$（$I_0 = \{1, 3\}$），0% 缺失；
     4. `CfgD_all_null_miss2`：$\boldsymbol{\theta} = (0.0, 0.0, 0.0, 0.0)$（$I_0 = \{1,2,3,4\}$），在每簇 8 个不相交底层条件读数上各自独立以 $0.01$ 概率注入缺失（连续缺失代入 `[0.0, 100.0]`，离散缺失代入 `[0, 1]`，使每槽约 $1 - 0.99^2 = 1.99\%$ 的簇承受最不利界限拓宽）。
   - **四项准入硬闸门与候选选择/降级/停止规则**：与 `PLAN-E2.md` §4.2(6) 及 `PLAN-E3.md` §4.2(5) 完全一致（`fwer <= 0.059747`、`simultaneous_coverage_9875 >= 0.940253`、`individual_coverage_9875 >= 0.975`、`screen05 <= 0.075` 必须在全部 **20 格**同时通过；依次评估 `Candidate 1 = hybrid_pct_tango_e4` $\to$ `Candidate 2 = hybrid_bessel_t_tango_e4` $\to$ 最多一次 1–2 个连续槽降级重验［维持 $m=4$ 分母］ $\to$ 否则触发 `calibration_failed_stop_s5` 严禁进入 S5）。

### 4.3 第三层描述性与机制拆解分析（预先锁定，不占确认性 $\alpha$）
1. **推理轨迹与竞争假说文本分类（对接 Zheng et al. 2026 Table 4 & Table 5 的 89% vs. 34% 基准）**：
   - 自动扫描 `L/CoT`、`P/CoT`、`M/CoT`、`L/CF`、`P/CF` 与 `M/CF` 的输出文本，统计：
     - **教科书标签/规则反射率（Textbook / Single-Standard Reflex Rate）**：显式点名 `"Moore's paradox"` / `"Moorean"` 或直接套用「断言 $p$ 同时不信 $p$ 即自相矛盾」单一标准规则的比例；
     - **双重判准 / 多义性拆解检出率（Dual-Criteria / Polysemy Rate）**：显式区分「局部/技术/账面/程序标准」与「全局/系统性风险/实质危机标准」的比例。
2. **取消断言控制槽 `PURE_READ` 的专项配对分析**：在全部 13 个 `(task, prompt)` 条件下对比 `PURE_READ` 与 `PURE_MOORE`、`DUAL_MOORE`，检验单链 `CoT` 是否因表面字符串匹配而对非断言朗读产生误判。
3. **`M_U`（等权）vs. `M_W`（自报权重加权）、候选中位数 `Median`、最高权重 `Top-1` 与调用内标准差（Within-Call SD）分析**。
4. **四大领域子类（`D1_safety`, `D2_project`, `D3_medical`, `D4_institutional`，正式集各 $n = 20$，开发集各 $n = 5$）分层点估计与 98.75% / 95% 置信区间**。

---

## 5. 阶段、闸门与停止规则（S0–S7）

| 阶段 | 内容 | 闸门与停止规则 |
| :--- | :--- | :--- |
| **S0** | 编写 `curate_100_clusters_e4.py` 生成 100 簇摩尔悖论材料 `data/clusters_100_e4.json`、`subclasses_e4.json`、`split.json` 与独立认证 Tango 表 `manifests/exact-tango-tables-e4.npz` | `validate_materials_e4.py` 100/100 簇零错误、假设句簇内逐字全等、前提禁漏元语言标签词及数字/`%` 且 17/17 负向突变自检全拦截；Tango 表覆盖 `SUPPORTED_NS = (5, 20, 80)` 且 9/9 有理数证书 100% 通过、0 单调性违例 |
| **S1** | 生成开发集 20 簇与 13 条件预览 `s1_preview_e4.md`，送 `c` 审查 `PLAN-E4.md` 与 S0–S1 产物 | `prompts_e4.py` 通过 `PARSE_VERSION = 2` 及 `protocol.py` 全 13 格兼容自检（含 `M/CF` 段落分离正向与负向回归验证）；`c` 审查无阻断；用户确认 S1 预览 |
| **S2** | 实现 `exp4-moore/` 独立运行器、计分器、统计核心 `core_e4.py`、`calibrate_e4.py` 与单元测试套件 | 单元测试全过；首 token 互斥核验通过；`c` 审查 S2 代码无阻断 |
| **S3** | Mac mini（`qwen3-8b@macmini-m6`）真实冒烟（开发集前 3 簇 `002, 003, 012`，共 174 单元） | 任一单元不可用则停下诊断；诊断语境 `P/Z` 下 `mean(Pos) > mean(Neg)` |
| **S4** | Mac mini 开发集完整运行（1,160 单元）+ 20 单元确定性重跑 + `calibrate_e4.py`（20 格，`R=2000, B=5000`）统计校准 | 任一格首次可用率 $< 90\%$、截断率 $> 5\%$ 或整体缺失率 $> 2\%$ 则停下；诊断语境 `P/Z` 全集 `mean(Pos) >= 80.0, mean(Neg) <= 20.0` 并按 4 领域子类报告；四槽完整开发簇数均 $\ge 15$；20 格统计校准 `status = pass` |
| **S5** | 冻结 `exp4-moore/PLAN-E4.md`（生成 `freeze.json`），构建并推送公开预注册包（`imperfective-exp4-moore/`）至 `asj252/llm-judgment-studies` | `c` 预冻结审查无阻断 + 用户确认冻结与推送；公开预注册提交时间严格早于 S6 首条正式 unit |
| **S6** | Mac mini 正式集 80 簇（4,160 单元）执行 | `statistics.json` 闸门 `pass` |
| **S7** | 正式集统计分析、推理轨迹文本分类（教科书反射 vs. 双重判准拆解）、知识库沉淀与报告生成 | 双端独立复现逐位一致 |

---

## 6. `c` 首轮 S0–S1 独立审查（`review-plan-e4-codex.md`）意见与逐条回应

- **审查报告**：`exp4-moore/review-plan-e4-codex.md`（命令行 Codex `read-only` 独立审查，总体判定：**无阻断 / Zero Blockers**）。
- **逐条回应表**：

| 条目 | `c` 审查意见摘要 | 处理决定与落地位置 |
| :--- | :--- | :--- |
| **建议 1** | `PLAN-E4.md` §4.2(2) 中 $c_5$（$\text{df}=4$）在 80 位有效数字高精度下向最近偶数 binary64 舍入值为 `1.9313454535930072`（原 `1.931345453593007` 相差 1 ULP）。 | **采纳**。已在 §4.2(2) 更新为 `c_5 = 1.9313454535930072`，并在 S2 `core_e4.py` 实现时锁定该精确常数。 |
| **建议 2** | 保持 `E4_H1`（同时改变 `task` 与 `prompt`）与 `E4_H2`（`DUAL_MOORE` vs. `PURE_MOORE` 同时改变语境与核心/原子命题）的确认结论口径严格受控，不作越界单因子归因。 | **采纳**。已在 §4.1 增补「因子归因口径约束」专段，明确 `E4_H1` 为联合接口对比（单因子拆解由第 3 层并列报告）、`E4_H2` 为复合槽位对比，纯修饰语最小对归因由 `E4_H3`/`E4_H4` 承担。 |
| **建议 3** | 清理 `validate_materials_e4.py` 头部注释中的旧数字 `15`（应为 `17`）与 `exact_tango_e4.py` 头部注释中的 `6 (n, alpha)`（应为 `9 (n, alpha)`），并支持在负向突变自检中独立验证结构护栏（不被 `RAW_CLUSTER_SPECS` 绑定短路掩盖）。 | **采纳**。已更新两文件头部文档字符串，并在 `validate_materials_e4.py` 中增加 `check_raw_spec_binding: bool = True` 参数，使 `_killed_both_modes` 同时验证 `M1`–`M15` 在 `check_raw_spec_binding=False` 与 `True` 下均被独立拦截（实测 `17/17` 全拦截）。 |
| **问题 1** | `M/CF` 中是否需要显式提示 `Estimate 1..5` 与 `Interpretation 1..5` 按序对应？ | **采纳**。已在 `prompts_e4.py` 的 `INSTRUCTIONS_E4["CF"]` 中加入显式绑定（并在 S3 冒烟诊断后进一步明确 `Estimate k: NN%` 为在 `Interpretation k` 下 Statement 为真的条件机率 `0%–100%`、各 `NN%` 不相加为 `100%`，而 `Weight: W` 为该诠释的合理度权重且五项权重和为 `1`），重新生成 `s1_preview_e4.md` 且通过全 13 条件 `parse.py` / `protocol.py` 自检。 |
| **问题 2** | S2 实现 `core_e4.py` 与 `calibrate_e4.py` 时，建议将引用 `PLAN-E1/E2/E3` 的统计与退化细则自包含写入代码与单元测试。 | **采纳**。已在 S2 编写 `core_e4.py`、`calibrate_e4.py` 与 `test_e4.py`（18 项单元测试全部通过）时 100% 自包含实现，并通过 `c` 独立审查（`review-s2-e4-codex.md`：**无阻断**）。 |

---

## 7. S2 实现审查、S3 冒烟与 S4 开发集校准锁定的预冻结记录

1. **S2 代码实现与独立审查（已完成）**：
   - 运行器与统计实现文件哈希锁定：`core_e4.py`（`7c766006ce544402a4655bd52c9f8577c948f7e405e774748eb05691e387940e`）、`calibrate_e4.py`（`a4c928e0e86a42eee89aaf603fa310bdc7e50f849c0ec365fd5cf6709b400279`）、`run.py`（`a598d2570e74a95517c1dfcc2d98d9c37edef3995391975ac371a18e59cbc69b`）、`test_e4.py`（`149ada8e3065341c615b3340053c369793d74c8d9fdf1ff27570cea63a11539a`）。
   - `c` 独立审查报告：`exp4-moore/review-s2-e4-codex.md`（SHA-256 `064b5c91b228f1701979f8d2c32419eac7308d970492fcfd7aef67c90d27bb75`，总体判定：**无阻断**）。
2. **S3 冒烟（`smoke` 174 单元）与探针核验（`verify`）（已完成）**：
   - 诊断性早停与 `INSTRUCTIONS_E4["CF"]` 微调说明：首轮冒烟（命名空间 `ea110416`）在完成前 151 个单元后于第 152 单元 `PURE_READ_012/P/CF` 触发 `smoke unit unavailable in P/CF` 停机，诊断发现原 `INSTRUCTIONS_E4["CF"]` 禁止出现 `"Probability:"` 的表述导致模型在 `P/CF` 末行漏写 `"Probability: "` 前缀，且在 `M/CF` 中将 `Estimate k: NN%` 误等同于 `100% * Weight_k`。据此修订 `prompts_e4.py`（SHA-256 `63442bf71ec72a9b1e77a21f8abe4c62d3508cc5d46507ecf351799368971a90`）与 `s1_preview_e4.md`（SHA-256 `29e6378c6beb1095add94a3b08a661a98f51895dc9d6296f5d9b5af31376932e`），生成锁定运行指纹 `fingerprint_id = 8c93bc6870a1a00500c3e91c7fd842a100e7d573c33c965963c6ccddec8dce2d`（目录 `8c93bc68`）。
   - 锁定指纹 `8c93bc68` 下的正式 S3 冒烟（`run_id = E4-718d3f6c500d4c1097be2fc4eadf1a78`，`session_id = e31a5b86ea9241cb80eb798069b5b6a3`）：`174/174` 单元全部首轮一次通过（`missing = 0, first_attempt_missing = 0, truncated = 0`），诊断语境 `P/Z` 极性门 `pos_mean_pz = 100.0%, neg_mean_pz = 0.0%`（`gate.json` `status = "pass"`，SHA-256 `5ac6f473374ed726c6831df9b106a220766ccbd6e64088129c45fc2d610d0ed1`）。
   - S3 `verify`：`verify_vocab.json`、`verify_probs.json`、`verify_greedy.json` 三项全部 `status = "pass"`。
3. **S4 开发集运行（`dev` 1,160 单元）、确定性重跑（`determinism` 20 单元）与统计校准锁定（已完成）**：
   - S4 `dev`（`run_id = E4-a8ee5534b8de48d58bf78be85f42e9df`，`session_id = 049a17f849074bedaa3793e1875092c1`）：执行 `1,160/1,160` 单元，有效可用 `1,157/1,160`（总缺失率 `0.2586% <= 2.0%`，截断率 `0.0% <= 5.0%`；仅 `M/Z` 有 3 个单元 `PURE_MOORE_016/M/Z`、`DUAL_MOORE_082/M/Z`、`PURE_MOORE_071/M/Z` 因末尾附加额外列表触发 `missing_format`，该格可用率 `77/80 = 96.25% >= 90.0%`，其余 12 个主条件与 3 个诊断条件可用率均为 `100.0%`）。诊断语境 `P/Z` 全集 `pos_mean_pz = 99.62% >= 80.0%, neg_mean_pz = 0.0% <= 20.0%`（四领域 `D1_safety = 99.9%/0.0%`、`D2_project = 99.8%/0.0%`、`D3_medical = 99.78%/0.0%`、`D4_institutional = 99.0%/0.0%`），`gate.json` `status = "pass"`（SHA-256 `1e7b401e26b91a06c4d5adaed0428257a73d4606c905e091182dcc7ba2b2cdb8`）。
   - S4 `determinism`（`run_id = E4-5e68f5c729b64906adf3b01356c0f656`，抽样种子 `DETERMINISM_SEED_E4 = 2026110692`）：20 个抽样单元重跑生成的原始 token ID 序列 `20/20` 与首跑 100% 逐元素一致（`determinism.json` `status = "pass"`，SHA-256 `4a1223600167a701dabd9b36614691c48c31b659bc02b848ade04e793e958a5d`）。
   - S4 20 格蒙特卡洛统计校准（`calibrate_e4.py`，种子 `CALIB_SEED_E4 = 2026110611`，$R = 2000, B = 5000$，基于真实开发集账本 `dev_ledger_sha256 = 4b19a82ff1d756bada03d04f34fff708549b1c7372d0e42d46bca35987eafa50`，完整开发簇数 `{"E4_H1": 20, "E4_H2": 17, "E4_H3": 20, "E4_H4": 20}`，联合完整簇数 `17 >= 15`，`joint_123` 模式）：
     - **Step 1（`hybrid_pct_tango_e4`）**：通过 `19/20` 格，仅在第 0 格（`DGP1_emp / CfgA_all_null_comp`）因联合 98.75% 覆盖率 `0.9395 < 0.940253` 未过（差 1/2000 次模拟）。
     - **Step 2（`hybrid_bessel_t_tango_e4`）**：**`20/20` 格全部通过**（`fwer` 范围 `0.0075–0.0505 <= 0.059747`，联合 98.75% 覆盖率范围 `0.9500–0.9895 >= 0.940253`，单项 98.75% 覆盖率最小值 `0.9820 >= 0.975`，`max_screen05` 范围 `0.0205–0.0595 <= 0.075`）。
     - **正式集 S6/S7 锁定统计推断家族**：按 §4.2(5) 确定性选择规则，锁定 **`selected_step = 2`、`selected_family = "hybrid_bessel_t_tango_e4"`、`selected_continuous_method = "bessel_t"`、`companion_family = "hybrid_pct_tango_e4"`、`demoted_slots = []`**（无槽位降级，全部 4 个主确认假设 `E4_H1, E4_H2, E4_H3, E4_H4` 均保留在 $m = 4$ 确认性 Holm 家族内）。校准产物已固化于 `exp4-moore/calibration-e4.json` 与 `data/raw/calibration_e4.json`（SHA-256 `4de801144abc35dd75b67a768d279a8b5582d8b6d6536e669dbdf26237b604df`，`production_eligible = true`）。
   - S3–S4 详细数据与诊断已汇总于阶段报告 `exp4-moore/report-s3-s4-autonomous-e4.md`。


