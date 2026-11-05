# 实验 3（英文活动边界修饰语对照版）：`ImperfectiveNLI` 非终结活动簇之「最低动作发生 `h_occ`」与「完结/全程持续 `h_plan`」单槽位修饰语正交拆解（计划草案 v0.3）

- 实例：`#imperfective`；计划树节点：`P16.6`；日期：2026-11-04；起草：a。
- 状态：**草案 v0.3（已回应 `c` 第 1–2 轮审查 `review-plan-e3-codex.md` 与 `review-plan-e3-r2-codex.md`，统一全字节级非 `data/` 零豁免扫描契约并通过 15/15 项负向突变自检，修正稀有尾部反例边界表述，送 `c` 第 3 轮终审）**。
- 上游依据：总计划 `../PLAN.md` 第 5、7、10 节（保持只读，不改动其 SHA-256）；实验 1 冻结规范 `../s5-mac-handoff-20261101/PLAN-E1.md` 与正式集报告 `../s5-mac-handoff-20261101/results/report-s7-formal.md`；实验 2 冻结规范 `../exp2-zh/PLAN-E2.md` 与正式集报告 `../exp2-zh/report-s6-s7-formal-e2.md`。
- 实验隔离与版权铁律：本实验全部代码、配置、账本、认证 Tango 查表清单与冻结记录均 100% 独立存放并构建于 `connecting-dots/imperfective/exp3-en/`，运行 ID 前缀为 `E3-`，不读取也不修改 `exp1-en/`、`exp2-zh/` 或任何其他子目录的文件。上游 `ImperfectiveNLI`（`imperfectiveNLI.json`，CC BY-NC 4.0）原题、派生题面及后续 S3/S4/S6 原始推理输出与服务日志均严格存放于 git 排除目录 `exp3-en/data/`（含 `data/raw/`、`data/server_logs/`）；`exp3-en/` 下除 `data/` 以外的**全部文件（无任何其他子目录或扩展名豁免）**严禁出现任何上游原句全文，并由 `validate_materials_e3.py:check_no_upstream_leakage_outside_data()` 按 UTF-8 字节序列机械扫描强制把关。

---

## 1. 研究动机、测量边界与与实验 1/2 的关系

在实验 1（英文 `ImperfectiveNLI`，`Qwen3-8B` 正式集 `4,160` 单元，公开预注册 `a6c90b5`）与实验 2（中文 `100` 簇四槽正交设计，`Qwen3-8B` 正式集 `4,160` 单元，公开预注册 `a42fbbe`）中，我们确立了以下实证事实：

1. **实验 1 中英文非终结活动簇（`B`/`D`）在 `CoT` 下的反常表现（`SA4` 与 `SA3`）**：
   - 在离散三分类逻辑任务 `L` 上，无转折进行体前提 `D` 组（形如 `<Subject> was/were <VP_ing>.` $\to$ 光杆一般过去时假设 `<Subject> <VP_ed>.`）的 `True` 判定率从零样本 `L/Z` 的 **`100.0%`** 暴跌至 `L/CoT` 的 **`8.75%`**（`73/80` 题转为 `Unknown`，`SA4 = -0.9125`，`p_Holm = 1.818e-21`）；而带 `but/so ...` 转折分句的 `B` 组在 `L/CoT` 下却有 **`50.00%`** 判 `True`（`38/80` 判 `Unknown`，`2/80` 判 `False`），出现反直觉的 `D < B` 倒挂。
   - 在常识多估计机率任务 `M_U` 上，`M_U/CoT` 将 `B` 组（`95.01% -> 72.20%`）与 `D` 组（`88.04% -> 65.37%`）平行拉低约 22 个百分点，导致 `D - B = -6.83`pp 未见正分离（`SA3` 未拒绝原假设）。
2. **开发集推理轨迹揭示的英文光杆一般过去时读法张力**：
   - 核查实验 1 开发集 20 个 `B`/`D` 簇在 `L/CoT` 下的逐题推理链可见：当 `CoT` 提示要求模型分析事件是否具有明确终点及是否已完成时，模型在 `19/20` 个 `D_k` 开发簇上将英文光杆一般过去时假设 $H_{\text{orig}}$（`<Subject> <VP_ed>.`）解读为要求**动作/过程已完结或已达到某种终点**而输出 `Unknown`。
   - 同时，上游 `ImperfectiveNLI` 标为 `"Activity"` 的 100 个 `B`/`D` 簇在词汇—体貌类型上并非同质：既包含常与日常任务/训练/作业/行程关联的施事活动（如簇 `007, 015, 017, 085, 095`）和渐进程度变化谓语（如簇 `077, 078, 079, 081`），也包含无预设任务终点的休闲/社交/感官活动、连续物理过程与身心/气象状态（如簇 `011, 036, 064, 073, 089`）。此外，上游 `B_k` 的 `but/so ...` 分句在语义上涵盖从「直接打断动作」到「外部伴随事件或目标受阻（如簇 `094, 095`）」的异质转折语境，并非全部断言动作本身物理终止。
3. **实验 3 的精确定位与语义解释边界（回应 `c` 第 1 轮阻断 1 与建议 2、3）**：
   - **保留实验 1 全部上游前提与实验协议**：完全保留实验 1 的 100 个英文 `B`/`D` 簇原前提（`D_k` 与 `B_k`）、实验 1 的精确开发/正式集切分（20 开发簇 / 80 正式簇）、实验 1 的逐字英文提示模板、解析器（`PARSE_VERSION = 2`）、首字母 token 计分器与受测模型（`Qwen3-8B`）。
   - **单槽位体貌修饰语最小对与语用补全边界**：由于上游 `D_k` / `B_k` 原前提并未显式给定待完成的具体任务配额、精确程度阈值或固定观察期起止时间戳，在光杆一般过去时词干后附加体貌修饰语（`h_occ` vs `h_plan`）在严格形式语义上**不能脱离语境补全而声称消除了全部真值条件歧义**。因此，本实验将 `(h_occ, h_plan)` 严格界定为**「受控单槽位体貌修饰语及其诱发的语用完结/时段补全（pragmatic completion/period accommodation）对比」**：
     - `h_occ`（`for at least a short time` / `at least partially`）显式锚定「最低时间发生或最低程度实现」；
     - `h_plan`（`all the way to completion` / `completely` / `throughout the entire period`）显式锚定「语境默认任务完结、程度完全达成或在整个相关参照时段内持续未断」。
   - **确认性结论与跨实验比较的边界**：本实验的 4 个主确认假设（`E3_H1`–`E3_H4`）严格用于**确认实验 3 内部由上述单槽位体貌修饰语及 `D_k`/`B_k` 前提对比所引起的模型读数差异**；其与实验 1 原题（光杆 $H_{\text{orig}}$，`SA3`/`SA4`）及实验 2（中文 `V了` vs `V完/好/够了`）的联系，在报告中作为**跨实验对照与机制解释证据**呈现（并在第 3 层分析中提供与实验 1 同簇原题的逐簇配对差分布），而不单凭实验 3 内部四项槽位差直接声称无条件证明了实验 1 原题的内部因果机制。

---

## 2. 材料构造、三子类闭集修饰语模具与五项硬性护栏

### 2.1 上游数据绑定与 100 簇两层词汇体貌分类（`subclasses_e3.json`）
- **上游数据绑定**：读取本地 `exp3-en/data/imperfectiveNLI.json`（SHA-256 强制校验为 `ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a`，与实验 1 逐字节相同）中的全部 100 个非终结簇（`D_001..D_100` 作为无转折进行体前提 `p_no_int`，`B_001..B_100` 作为上游转折进行体前提 `p_int`，原假设记为 `h_orig`）。
- **无原题文本的受控分类清单 `exp3-en/subclasses_e3.json`**（SHA-256 `ff3be2370261c499397fbfba9921086cb69467775d196e53bf6d83912c01721d`，纳入 git 追踪，不含任何 `ImperfectiveNLI` 原句文本）：
  - **关于 `B_k` 独立性的准确界定（回应 `c` 第 1 轮疑问 2）**：由于 `ImperfectiveNLI` 为工作区既有公开数据集，本计划不声称人类研究者在阅读公开数据集前处于双盲状态；本计划所称并由代码强制执行的「独立于 `B_k` 的受控闭集映射」是指：（a）`materials_e3.py:build_subclasses_manifest()` 的分类规则仅以 `D_k`/`H_k` 核心谓语的词汇—体貌类别为依据，分类与修饰语派生的代码输入完全不读取 `B_k`；（b）全部 100 个簇的 `(occ_mod, plan_mod)` 100% 从下述 3 组固定闭集常数中按 `template_subclass` 机械映射，不对任何单题的 `B_k` 分句做词汇定制。
  - **两大语义子类（`macro_subclass`）与三类闭集修饰语模具（`template_subclass`）**：
    1. **带语境任务/计划或程度上限的有界化倾向子类（`macro_subclass = "A_plan"`，全集共 24 簇：开发集 8 簇、正式集 16 簇）**：
       - **`A_plan_task`（常伴随语境任务/训练/作业/行程边界的施事活动，全集 20 簇：开发集 5 簇［`017, 046, 084, 085, 099`］、正式集 15 簇［`001, 004, 007, 013, 015, 016, 021, 041, 042, 043, 045, 058, 061, 062, 095`］）**：
         - 最低发生修饰语 `occ_mod`：**`"for at least a short time"`**
         - 完结修饰语 `plan_mod`：**`"all the way to completion"`**（诱发模型对当前活动所关联的常规任务/日程完结的语用补全）。
       - **`A_plan_deg`（渐进程度变化谓语 Degree Achievements，全集 4 簇：开发集 3 簇［`077, 078, 081`］、正式集 1 簇［`079`］）**：
         - 最低实现修饰语 `occ_mod`：**`"at least partially"`**
         - 完全达成修饰语 `plan_mod`：**`"completely"`**（对应程度量表上的部分实现 vs 最高程度达成对比）。
    2. **纯无界持续活动、物理过程与身心/气象状态子类（`macro_subclass = "A_pure"` / `template_subclass = "A_pure"`，全集共 76 簇：开发集 12 簇、正式集 64 簇）**：
       - 涵盖无预设任务终点的日常活动以及非施事连续物理过程、身心状态与气象过程：
       - 最低发生修饰语 `occ_mod`：**`"for at least a short time"`**
       - 全程持续修饰语 `plan_mod`：**`"throughout the entire period"`**（对应「至少短暂发生过」vs「在语境相关参照时段内全程持续未断」的时量修饰对比）。
- **解释边界与分层报告铁律（对齐实验 2 `PLAN-E2.md` §1 与 §2.1）**：
  鉴于 `A_plan`（任务/程度完结 `all the way to completion` / `completely`，正式集 $n = 16$）与 `A_pure`（全程持续 `throughout the entire period`，正式集 $n = 64$）的 `h_plan` 修饰语对应不同的有界化机制与语用补全方式，**主报告在给出全部 80 个正式簇汇总确认检验（`E3_H1`–`E3_H4`）的同时，必须在正文中紧跟并列报告 `A_plan`（$n = 16$，并附 `A_plan_task` $n=15$ 与 `A_plan_deg` $n=1$ 明细）与 `A_pure`（$n = 64$）两个子类的分层点估计与置信区间**。

### 2.2 派生公式、单处词干归一化（`095`）与五项机械硬性护栏（`validate_materials_e3.py`）
由 `exp3-en/materials_e3.py` 从上游 `imperfectiveNLI.json` 与 `subclasses_e3.json` 确定性生成 `exp3-en/data/clusters_100_e3.json`（SHA-256 `7f10a952c8ec32a4c978b69a0f755085fd76490d72d3706db8773b93d17da8aa`），并由 `validate_materials_e3.py` 强制核验以下护栏（100/100 簇零错误、全部非 `data/` 文件零上游原句泄漏，且 **15/15 项负向突变自检全部拦截**）：
1. **上游记录逐项全等绑定与 100 簇完整分区锁定（回应 `c` 第 1 轮阻断 3）**：
   - `imperfectiveNLI.json` SHA-256 必须等于 `ddd01d06...`；
   - `subclasses_e3.json` 必须与 `build_subclasses_manifest()` 内存重建结果逐字段全等；`split.json` 必须与 `build_split_manifest()` 内存重建结果（含全部展开单元 ID 列表 `smoke/dev/formal` 及子类簇列表）逐字段全等；
   - 每簇 `c["p_no_int"]`、`c["p_int"]`、`c["h_orig"]`、`c["upstream_d_id"]`、`c["upstream_b_id"]` 必须与 `imperfectiveNLI.json` 中对应 `D_<cid>`、`B_<cid>` 记录逐字全等；每簇 `template_subclass`、`macro_subclass`、`occ_mod`、`plan_mod` 必须与 `subclasses_e3.json["clusters"][cid]` 逐字全等；
   - `A_plan` 固定 24 簇（`A_plan_task` 20 + `A_plan_deg` 4），`A_pure` 固定 76 簇。
2. **进行体前提格式与转折前缀全等核验**：每簇 `p_no_int`（`D_k`）严格匹配 `^(.+?)\s+(was|were)\s+(.+)\.$`；`p_int`（`B_k`）严格以 `p_no_int[:-1] + ","` 为前缀且以 `"."` 结尾；前提中严禁泄漏 `ALL_MODIFIERS` 中的任何修饰语字符串。
3. **一般过去时词干锁定与单槽位后缀替换最小对铁律**：
   - 对 `cid != "095"` 的全部 99 个簇，词干 `h_base = h_orig[:-1]` 与上游原假设去句号形式逐字全等；
   - 对唯一的 `cid == "095"`（全集唯一在 `H_k` 句尾自带全天时量短语 `" all day."` 的题目），词干执行唯一一处确定性去尾归一化 `h_base = h_orig[:-1].removesuffix(" all day")`（正文中第 3 层分析额外固定报告剔除 `095` 后的 79 簇精确 Tango 与 Bootstrap 敏感度复核）；
   - 配对假设严格定义为：
     $$h_{\text{occ}} = \text{``\{h\_base\} \{occ\_mod\}.''}, \qquad h_{\text{plan}} = \text{``\{h\_base\} \{plan\_mod\}.''}$$
   - `validate_materials_e3.py` 逐簇强制核验单槽位替换恒等式 `h_plan[:-len(f" {plan_mod}.")] + f" {occ_mod}." == h_occ`。
4. **闭集修饰语防词汇泄漏护栏**：`occ_mod` 与 `plan_mod` 必须 100% 取自 `SUBCLASS_MODIFIERS[template_subclass]` 的三组闭集常数，严禁出现 `"interruption"`, `"interrupted"`, `"but"`, `"stopped"`, `"halted"` 等任何与转折分句词汇重叠的词项。
5. **诊断语境（`p_diag_pos` / `p_diag_neg`）确定性派生、指代绑定与验证边界（回应 `c` 第 1 轮建议 1）**：
   - 设 `h_plan_clause` 为 `h_plan` 首字母小写形式（若以第一人称 `"I "` 或专有名词 `"Grandpa "` 开头则保留首字母大写）：
   - 正向诊断前提：`p_diag_pos = f"{p_no_int[:-1]}, and {h_plan_clause}"`；
   - 负向诊断前提（统一使用指示代词 `that` 回指 `p_no_int` 所述进行中事件）：对 `A_plan_deg` 为 `f"{p_no_int[:-1]}, but that ended early and did not happen {plan_mod}."`；对 `A_plan_task` 与 `A_pure` 为 `f"{p_no_int[:-1]}, but that ended early and did not continue {plan_mod}."`；
   - **诊断语境的解释边界**：由于 `p_diag_pos` 与 `p_diag_neg` 在前提中显式包含了 `plan_mod` 的肯定或否定陈述，它们在 S3/S4 中**仅作为提示管道、输出解析与极性方向的健全性检查（pipeline & polarity sanity check）**，不作为修饰语自然度或隐含终点独立成立的证据。在 S4 开发集报告中，除检验 20 簇总体均值门槛（`P/Z` 下 `mean(Pos) >= 80` 且 `mean(Neg) <= 20`）外，还必须按三个 `template_subclass`（`A_plan_task`、`A_plan_deg`、`A_pure`）分别报告均值与逐簇明细。
6. **全部非 `data/` 文件零豁免字节级泄漏扫描（`check_no_upstream_leakage_outside_data`，回应 `c` 第 2 轮 B2）**：自动遍历 `exp3-en/` 下除 `data/` 以外的**全部文件（不豁免 `raw/`、`server_logs/` 或任何文件扩展名）**，按 UTF-8 字节序列核验 `imperfectiveNLI.json` 全部 400 条记录的 600 条去重 `premise`/`hypothesis` 原句出现次数为 `0`，并通过 `M12_leak_in_markdown`、`M13_leak_in_raw_dir`、`M14_leak_in_server_logs_dir`、`M15_leak_in_binary_ext` 四项负向探针验证拦截能力。

### 2.3 簇内 4 个主实验条件格（2 前提 × 2 假设）及其测量定位
每个簇 $k \in \{001, \dots, 100\}$ 展开为 4 条主实验题 `(slot_name, premise_key, hyp_key)`：
1. **`NI_OCC`（`p_no_int` + `h_occ`，单元 ID `NI_OCC_<cid>`）**：无转折进行体（`D_k`）下询问最低发生/部分实现假设 `h_occ`。
2. **`NI_PLAN`（`p_no_int` + `h_plan`，单元 ID `NI_PLAN_<cid>`）**：无转折进行体（`D_k`）下询问完结/全程持续假设 `h_plan`（因 `p_no_int` 仅陈述动作/过程正在进行而未保证完结或持续到底，预期在 `L/CoT` 下主要判 `Unknown`，且在 `P/Z` 下读数显著低于 `NI_OCC`）。
3. **`INT_OCC`（`p_int` + `h_occ`，单元 ID `INT_OCC_<cid>`）**：上游转折进行体（`B_k`）下询问最低发生/部分实现假设 `h_occ`（动作在转折事件前已处于进行中，预期保持高机率读数与高 `True` 率）。
4. **`INT_PLAN`（`p_int` + `h_plan`，单元 ID `INT_PLAN_<cid>`）**：上游转折进行体（`B_k`）下询问完结/全程持续假设 `h_plan`：
   - **不预设全集单一黄金离散标签（对齐实验 2 `PLAN-E2.md` §2.3 与 `c` 建议 2）**：由于上游 `B_k` 原句的 `but/so ...` 分句在打断强度上存在客观异质性（部分直接终止动作，部分仅陈述伴随困难或外部事件），本计划不对 `INT_PLAN` 预设单一 `False` 黄金标签，而在第 3 层分析中完整报告 `{True, False, Unknown}` 三标签分布，并在主确认检验中以连续配对机率差 `INT_OCC - INT_PLAN`（`E3_H2`）与 `NI_PLAN - INT_PLAN`（`E3_H3`）度量读数分离。

### 2.4 开发集与正式集切分锁定（`split.json`，完全沿用实验 1 `seed = 20261090`）
- 分割清单：`exp3-en/split.json`（SHA-256 `cd0e099a38481b23c071d3950aac4527daf29aea12076f34ea9eadc4a90d7ea4`）。
- **零跨实验泄漏保证**：100% 沿用实验 1（`exp1-en/split.json`，种子 `20261090`）对 `atelic_clusters` 的简单随机切分：
  - **开发集（`dev`，20 簇 = 80 条主实验题 + 40 条诊断语境题）**：`["011", "017", "025", "036", "037", "039", "046", "047", "048", "056", "064", "065", "073", "077", "078", "081", "082", "084", "085", "099"]`（含 `A_plan` 8 簇［`A_plan_task` 5、`A_plan_deg` 3］，`A_pure` 12 簇）。
  - **正式集（`formal`，80 簇 = 320 条主实验题）**：其余 80 簇（含 `A_plan` 16 簇［`A_plan_task` 15、`A_plan_deg` 1］，`A_pure` 64 簇）。正式集 80 簇在 S5 冻结前 100% 不参与任何受测模型冒烟（S3）或开发集运行（S4）。
  - **S3 冒烟子集（`smoke`，3 簇 = 12 条主实验题 + 6 条诊断题）**：取三个模具子类在开发集中的最小簇编号 `["011", "017", "077"]`。

---

## 3. 任务、英文提示模板与输出协议

### 3.1 任务与提示组合（每条主实验题 13 个单元，与实验 1、2 完全同构）
- **13 个 `(task, prompt)` 条件**：`L/Z, L/DAP, L/CoT, L/CF, Ps/Z, P/Z, P/DAP, P/CoT, P/CF, M/Z, M/DAP, M/CoT, M/CF`。
- **单元规模**：
  - S3 冒烟：`3 簇 × 4 主槽 × 13 条件 = 156 主单元` + `3 簇 × 2 诊断槽 × 3 零样本任务（L/Z, P/Z, M/Z）= 18 诊断单元`，共 **`174 单元`**。
  - S4 开发集：`80 题 × 13 条件 = 1,040 主单元` + `40 诊断题 × 3 零样本任务 = 120 诊断单元`，共 **`1,160 单元`**（与实验 2 开发集规模完全一致）。
  - S6 正式集：`320 题 × 13 条件 = 4,160 单元`（与实验 1、实验 2 正式集规模完全一致）。

### 3.2 逐字英文提示模板与 `PARSE_VERSION = 2` 兼容核验（`prompts_e3.py`）
- 本实验英文提示由 `exp3-en/prompts_e3.py` 渲染，**逐字沿用实验 1（`exp1-en/prompts.py` + `exp1-en/prompt_parts.py` + `data/run_inference.py.txt` SHA-256 `5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880`）的全部英文提示文本**，零改动。
- 解析器 `exp3-en/parse.py`（SHA-256 `b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342`，`PARSE_VERSION = 2`）与实验 1、2 逐字节一致；`prompts_e3.py:verify_parser_compatibility()` 已通过全部 13 个条件的合成输出回归校验。
- S1 预览产物：
  - 含开发集 20 簇完整句面的本地预览：`exp3-en/data/s1_preview_e3.md`（SHA-256 `72d071989b2faa2441dacee1ffd659a50984d5d9c89e76b2277cade1702c130e`，因含 CC BY-NC 4.0 原题前提置于 git 排除目录 `data/`）；
  - 无原题文本的脱敏模板预览：`exp3-en/s1_preview_templates_e3.md`（SHA-256 `cec9aa31daa0b2f8740512de1fe99146c9e06b0be2a01741c59819dbbb2f6c1c`，纳入 git 追踪）。

---

## 4. 主确认检验家族（方案 E3，`m = 4`，$\alpha_{\text{fam}} = 0.05$）与封闭统计规范

### 4.1 四个主确认假设（`m = 4`，全部定义于正式集 $n = 80$ 簇，且底层 8 个实验单元两两完全不相交）

| 编号 | 检验对象与簇集 | 统计量定义 $\theta_j$ | 零假设与备择方向 | 确认性结论用语（拒绝 $H_0$ 时，正文必须紧跟并列报告 `A_plan`［$n=16$］与 `A_pure`［$n=64$］分解效应） |
| :--- | :--- | :--- | :--- | :--- |
| **`E3_H1`**<br>原 `D_k` 前提下「最低发生修饰 `h_occ` vs 完结/全程修饰 `h_plan`」单点机率差 | 正式集全部簇<br>（$n = 80$ 簇）<br>前提：`p_no_int`（`D_k`） | $\mu(\text{NI\_OCC}; P/\text{Z}) - \mu(\text{NI\_PLAN}; P/\text{Z})$ | $H_0: \theta_1 \le 0$<br>$H_1: \theta_1 > 0$（单侧，整簇 bootstrap） | **方向确认**：「在英文无转折进行体前提（`D_k`）下，附加最低发生/部分实现修饰语的假设 `h_occ`（`NI_OCC`）在 `P/Z` 上的机率读数显著高于附加完结/全程持续修饰语的假设 `h_plan`（`NI_PLAN`）」。 |
| **`E3_H2`**<br>原 `B_k` 前提下「最低发生修饰 `h_occ` vs 完结/全程修饰 `h_plan`」单点机率差 | 正式集全部簇<br>（$n = 80$ 簇）<br>前提：`p_int`（`B_k`） | $\mu(\text{INT\_OCC}; P/\text{Z}) - \mu(\text{INT\_PLAN}; P/\text{Z})$ | $H_0: \theta_2 \le 0$<br>$H_1: \theta_2 > 0$（单侧，整簇 bootstrap） | **方向确认**：「在英文上游转折进行体前提（`B_k`）下，附加最低发生/部分实现修饰语的假设 `h_occ`（`INT_OCC`）在 `P/Z` 上的机率读数显著高于附加完结/全程持续修饰语的假设 `h_plan`（`INT_PLAN`）」。 |
| **`E3_H3`**<br>`M_U/CoT` 下完结/全程修饰 `h_plan` 之「原 `D_k` 前提 vs 原 `B_k` 前提」读数差（对照实验 1 `SA3`） | 正式集全部簇<br>（$n = 80$ 簇）<br>假设：`h_plan` | $\mu(\text{NI\_PLAN}; M_U/\text{CoT}) - \mu(\text{INT\_PLAN}; M_U/\text{CoT})$ | $H_0: \theta_3 \le 0$<br>$H_1: \theta_3 > 0$（单侧，整簇 bootstrap） | **方向确认**：「在显式附加完结/全程持续修饰语 `h_plan` 后，多估计 `M_U/CoT` 在原 `D_k` 无转折前提（`NI_PLAN`）上的机率读数显著高于原 `B_k` 转折前提（`INT_PLAN`）」（第 3 层并列报告 `NI_OCC - INT_OCC`、双差交互项及与实验 1 同簇 `D_k - B_k` 的对比）。 |
| **`E3_H4`**<br>`L/CoT` 下原 `D_k` 前提「最低发生修饰 `h_occ` vs 完结/全程修饰 `h_plan`」`True` 判定率差（对照实验 1 `SA4`） | 正式集全部簇<br>（$n = 80$ 簇）<br>前提：`p_no_int`（`D_k`） | $\Pr(\text{True on NI\_OCC}; L/\text{CoT}) - \Pr(\text{True on NI\_PLAN}; L/\text{CoT})$ | $H_0: \theta_4 \le 0$<br>$H_1: \theta_4 > 0$（单侧，认证精确 Tango） | **方向确认**：「在英文无转折进行体前提（`D_k`）的 `L/CoT` 任务下，附加最低发生/部分实现修饰语的假设（`NI_OCC`）的 `True` 判定率显著高于附加完结/全程持续修饰语的假设（`NI_PLAN`）」（第 3 层并列报告 `L/Z` 与 `L/CoT` 完整三标签分布及与实验 1 同簇 `D_k` 原题的配对对比）。 |

### 4.2 封闭统计推断规范（继承并对齐实验 1 `PLAN-E1.md` 与实验 2 `PLAN-E2.md` v0.6）

1. **推断目标、整簇等权多项式重抽与统计声称边界**：
   - **推断目标**：由于实验 3 的开发集（$n_{\text{dev}} = 20$）与正式集（$n = 80$）直接沿用实验 1 `exp1-en/split.json`（种子 `20261090`）对 `ImperfectiveNLI` 100 个非终结簇的简单随机切分，主确认分析的推断目标为正式集 $n = 80$ 簇所代表的簇平均效应。
   - **共享整簇重抽流**：固定重抽次数 **`B = 5000`**；正式集分析种子 **`FORMAL_ANALYSIS_SEED_E3 = 2026110401`**，开发集分析种子 **`DEV_ANALYSIS_SEED_E3 = 2026110402`**，第 3 层剔除 `095` 簇（$n = 79$）敏感度分析专用种子 **`SENS79_ANALYSIS_SEED_E3 = 2026110403`**。使用单一共享随机流 `rng = np.random.Generator(np.random.PCG64(seed))`，对按 `cluster_id` 升序排列的 $n$ 个簇（正式集 $n = 80$，开发集 $n = 20$，79 簇敏感度子集 $n = 79$）抽取单一共享权重矩阵 `w = rng.multinomial(n, np.full(n, 1.0 / n), size=B) / float(n)`（形状 `(B, n)`），同时用于连续三槽 `E3_H1, E3_H2, E3_H3`。第 3 层子类分解中针对 `A_plan`（正式集 $n=16$，开发集 $n=8$）与 `A_pure`（正式集 $n=64$，开发集 $n=12$）的重抽，在同一 `rng` 之后依次按 `cluster_id` 升序抽取各自子集的等权多项式权重矩阵。
   - **统计保证措辞与极端稀有尾部反例风险边界（回应 `c` 第 1–2 轮阻断 4）**：
     - 有限样本下的 `hybrid_pct_tango_e3` 与 `hybrid_bessel_t_tango_e3` 均严格定位为**待校准的有限样本近似推断程序**，其第一类错误率与覆盖率保护声明严格限定于下述第 5 条预注册的 **5 类 DGP $\times$ 4 类配置 = 20 格校准矩阵**（涵盖经验残差 `DGP1_emp`、强偏斜 `DGP2_skew`、高并列离散 `DGP3_ties`、16:64 子类强异质性 `DGP4_het` 与 70% 极端端点堆积 `DGP5_endpt`）实测验证通过的水平。
     - **候选程序在极端稀有尾部反例上的误拒风险与不覆盖范围声明**：本计划的候选推断程序**不声称**对任意有界分布均具有无条件有限样本保护，尤其明确不覆盖「总体零均值由极低概率（如 $p = 0.01$）极端反方向点质量与高概率（如 $1 - p = 0.99$）窄支撑正向质量相抵而成」的对抗性稀有尾部偏斜混合分布。如 `c` 第 1 轮审查核实的反例所示：若扰动以 $0.01$ 概率取 $-35.0$、以 $0.99$ 概率取均值 $+35/99 \approx +0.3535$ 且半宽 $0.01$ 的均匀分布（总体均值严格为 $0$），在 $n = 80$ 簇下有 $0.99^{80} \approx 44.7523\%$ 的样本完全未抽中负尾点；在此类漏掉负尾的样本上，`hybrid_pct_tango_e3` 与 `hybrid_bessel_t_tango_e3` 均具有 5,000 个互异重抽值、不会触发退化规则，且会给出全正置信区间与小 p 值（发生误拒）。因此，本计划明确将该类未观测稀有尾部极端混合分布排除在方法统计保证范围之外。

2. **连续配对差（`E3_H1`、`E3_H2`、`E3_H3`）的两套候选方法与退化规则**：
   - **候选方法 1（`hybrid_pct_tango_e3`：未插值次序统计量 Percentile Bootstrap）**：
     - 对升序排序后的 $B = 5000$ 个下界重抽均值 $s_{\text{low},(0)} \le \dots \le s_{\text{low},(4999)}$ 与上界重抽均值 $s_{\text{high},(0)} \le \dots \le s_{\text{high},(4999)}$：
       - **双侧 98.75% Bonferroni 同时置信区间**（单项 $\alpha_{\text{ind}} = 0.0125$）：取 0-based 下标 **`idx_lo = 31`** 与 **`idx_hi = 4968`**，即 $[s_{\text{low},(31)}, s_{\text{high},(4968)}]$；
       - **双侧 95% 伴随置信区间**：取 0-based 下标 **`idx_lo_95 = 124`** 与 **`idx_hi_95 = 4875`**；
     - **单侧 p 值**：若观测点估计下界 $\hat{\theta}^L_j \le 0$，设 $p_j = 1.0$；若 $\hat{\theta}^L_j > 0$，则 $p_j = \frac{1 + \#\{b : \theta^{*,L}_{j,b} \le 0.0\}}{B + 1}$。
   - **候选方法 2 / 伴随敏感度方法（`hybrid_bessel_t_tango_e3`：保序 Bessel-$t$ 中心外扩 Bootstrap）**：
     - 对同一组重抽均值围绕观测点估计按 70 位 `Decimal` 高精度求根锁定的有限样本扩展因子 $c_n = \sqrt{\frac{n}{n-1}} \cdot \frac{t_{n-1,\, 0.99375}}{z_{0.99375}}$ 向外保序扩展（覆盖全部 7 种预设样本量，含 79 簇敏感度复核，回应 `c` 阻断 5）：
       - $c_{80} = 1.0298684039340296$（$\text{df} = 79$，正式集全集 $n=80$）
       - $c_{79} = 1.0302596947224958$（$\text{df} = 78$，正式集剔除 `095` 敏感度子集 $n=79$）
       - $c_{64} = 1.037660015052903$（$\text{df} = 63$，正式集 `A_pure` 子集 $n=64$）
       - $c_{20} = 1.1331397732007173$（$\text{df} = 19$，开发集全集 $n=20$）
       - $c_{16} = 1.1729390393815105$（$\text{df} = 15$，正式集 `A_plan` 子集 $n=16$）
       - $c_{12} = 1.2465119462060201$（$\text{df} = 11$，开发集 `A_pure` 子集 $n=12$）
       - $c_{8} = 1.4275423213691008$（$\text{df} = 7$，开发集 `A_plan` 子集 $n=8$）
     - 扩展公式、贪心锚点互异值计数（`_greedy_distinct_1d_sorted`，`TOL_DUST = 1e-12`）与裁剪前四项退化判据（`u_low < 20 or u_high < 20`、单流跨度 $\le 10^{-12}$、非有限或反序、外扩原始区间与 `[-100, 100]` 交集为空）与 `PLAN-E2.md` §4.2 第 2 条及 `core_e2.py` 逐行全等。

3. **离散配对比例差（`E3_H4`）的认证精确无条件 Tango (1998) 规范（回应 `c` 阻断 5 与阻断 6）**：
   - 定义簇内三值差 $d_i = \mathbb{I}(\text{label}_{i,\text{NI\_OCC}} = \text{True}) - \mathbb{I}(\text{label}_{i,\text{NI\_PLAN}} = \text{True}) \in \{-1, 0, +1\}$。
   - 由 `exp3-en/exact_tango_e3.py` 在本实验目录内 **100% 独立从头构建（已彻底移除跨目录读取逻辑 `_try_load_existing_res_for_n`）** 并经精确 `Fraction` 算术认证 `exp3-en/manifests/exact-tango-tables-e3.npz`（`file_sha256 = 59845e08a34c997c66b8d3c86244a87a7c5d8e6d018743c467bf37be4300828f`，`payload_sha256 = 0140b92cb110b6986af2d4ad0007d837cbac136e90ed7cce52135e0759df9439`）及 `exact-tango-tables-e3-meta.json`，完整覆盖 **`SUPPORTED_NS = (8, 12, 16, 20, 64, 79, 80)`** 七种样本量（21/21 项左截断有理数证书通过，0 单调性违例）。
   - 单侧 p 值、双侧 98.75% Bonferroni 精确置信区间、缺失回退以及独立同分布三项模型假设与异质性校准（`DGP4_het`）边界，与 `PLAN-E2.md` §4.2 第 3 条完全一致。

4. **`L` 首字母标签分数 `q`、单元四终结状态 `status`、最不利缺失界限传播与 Holm 流程**：
   - 与实验 1 `PLAN-E1.md` §3.2、§4.2(4) 及实验 2 `PLAN-E2.md` §4.2 第 4–5 条逐字一致：主确认分析严格仅在 `status == "ok"` 时代入观测点值，凡 `status != "ok"`（`missing_transport`、`missing_format`［含截断］、`missing_score`）一律代入最不利极值界（连续机率 `[0.0, 100.0]`，离散指示变量 `[0, 1]`）；对 `E3_H4` 固定并列输出 `label_available`（`status in ("ok", "missing_score")`）伴随诊断行；Holm 逐步检验（$m = 4, \alpha_{\text{fam}} = 0.05$）按固定编号顺序 `E3_H1, E3_H2, E3_H3, E3_H4` 破平。

5. **S4 统计校准核验的 20 格矩阵（5 DGP × 4 Cfg）、`DGP1_emp` 缺失处理与退出条件（`calibrate_e3.py`）**：
   - **模拟参数**：在 S4 开发集完成后、S5 冻结前，运行 `exp3-en/calibrate_e3.py`，使用固定模拟种子 **`CALIB_SEED_E3 = 2026110411`**，针对正式集精确簇数 $n = 80$（含 `A_plan` $16$ 簇、`A_pure` $64$ 簇）及 4 项家族（`E3_H1..E3_H4`），在 **5 类 DGP $\times$ 4 类真值/缺失配置 = 20 个校准格**上每格运行 **`R = 2000`** 次模拟，每次模拟内部调用 **`B = 5000`** 与 0-based 下标 **`idx_lo = 31, idx_hi = 4968`**（$\text{SE}_{\text{sim}} = \sqrt{0.05 \times 0.95 / 2000} \approx 0.0048734$）。
   - **8 个两两不相交底层实验条件与对称中心化配对读数生成机制（回应 `c` 建议 4）**：
     - `E3_H1`（`NI_OCC(P/Z)` vs `NI_PLAN(P/Z)`）、`E3_H2`（`INT_OCC(P/Z)` vs `INT_PLAN(P/Z)`）、`E3_H3`（`NI_PLAN(M_U/CoT)` vs `INT_PLAN(M_U/CoT)`）与 `E3_H4`（`NI_OCC(L/CoT)` vs `NI_PLAN(L/CoT)`）所使用的 **8 个底层 `(slot, task, prompt)` 实验条件两两完全不相交**（无任何跨假设共享单元）。
     - 对每个模拟簇 $i \in \{1, \dots, 80\}$ 及连续槽 $j \in \{1, 2, 3\}$，给定目标真值 $\theta_j \in \{0.0, 20.0, 25.0, 15.0\}$ 与有界扰动 $\varepsilon_{j,i} \in [-35.0, +35.0]$，生成该槽两个不同条件下的**对称中心化配对底层条件读数**（满足 $X_{j,i} + Y_{j,i} = 100.0$）：
       $$X_{j,i} = 50.0 + \frac{\theta_j + \varepsilon_{j,i}}{2} \in [20.0, 80.0] \subset [0, 100], \qquad Y_{j,i} = 50.0 - \frac{\theta_j + \varepsilon_{j,i}}{2} \in [20.0, 80.0] \subset [0, 100]$$
       其簇内差恒为 $d_{j,i} = X_{j,i} - Y_{j,i} = \theta_j + \varepsilon_{j,i} \in [-35.0, +60.0] \subset [-100, 100]$。
     - 对离散槽 `E3_H4`（目标真值 $\theta_4 \in \{0.0, 0.35\}$），按合法单纯形参数化 $\tau(\theta_4) = \max(\tau_0, |\theta_4| + 0.10) \in [0.15, 0.80]$，$\pi_+ = (\tau + \theta_4)/2, \pi_- = (\tau - \theta_4)/2, \pi_0 = 1 - \tau$ 生成配对指示变量 $(I_{i,\text{OCC}}, I_{i,\text{PLAN}}) \in \{(1,0), (0,1), (0,0)\}$。
   - **5 类数据生成分布家族（DGP 1–5，新增 `DGP5_endpt` 回应 `c` 阻断 4，明确 `DGP1_emp` 缺失处理回应 `c` 疑问 1）**：
     1. `DGP1_emp`（开发集中心化有界经验残差与缺失处理规则）：
        - 对开发集 20 簇，令 $K_{\text{ok}, j} \subseteq \{1, \dots, 20\}$ 为第 $j \in \{1, 2, 3, 4\}$ 个槽位配对双方底层单元均满足 `status == "ok"` 的完整开发簇下标集。**硬性前置闸门**：要求所有 $j \in \{1, 2, 3, 4\}$ 均满足 $|K_{\text{ok}, j}| \ge 15$；若任一槽位完整开发簇数 $< 15$，直接触发停止规则 `insufficient_complete_dev_clusters_stop_s5`，严禁进入校准或 S5。
        - 设三项连续槽共同完整开发簇集为 $K_{\text{ok, joint}} = K_{\text{ok}, 1} \cap K_{\text{ok}, 2} \cap K_{\text{ok}, 3}$。若 $|K_{\text{ok, joint}}| \ge 15$，则在 $K_{\text{ok, joint}}$ 上按等权均值中心化 $r_{j, k} = d_{j, k} - \frac{1}{|K_{\text{ok, joint}}|} \sum_{m \in K_{\text{ok, joint}}} d_{j, m}$，令缩放因子 $\kappa_j = \min(1.0, 35.0 / \max(10^{-12}, \max_{m \in K_{\text{ok, joint}}} |r_{j, m}|))$，每个模拟簇 $i \in \{1, \dots, 80\}$ 从 $K_{\text{ok, joint}}$ 中等概（$1 / |K_{\text{ok, joint}}|$）抽取同一个开发簇下标 $k$，成组取出 $(\kappa_1 r_{1, k}, \kappa_2 r_{2, k}, \kappa_3 r_{3, k}) \in [-35.0, +35.0]^3$（精确保证每槽 $\mathbb{E}[\varepsilon_{j, i}] = 0$ 并保留簇内跨槽相关性）；若 $|K_{\text{ok, joint}}| < 15$（但各 $|K_{\text{ok}, j}| \ge 15$），则各连续槽 $j$ 分别在其自身 $K_{\text{ok}, j}$ 上中心化、缩放并等概抽取（每槽 $\mathbb{E}[\varepsilon_{j, i}] = 0$）。
        - 对 `E3_H4`，在 $K_{\text{ok}, 4}$ 上计算经验不一致率 $\hat{\tau}_{\text{dev}} = \frac{1}{|K_{\text{ok}, 4}|} \sum_{k \in K_{\text{ok}, 4}} \mathbb{I}(d_{4, k} \ne 0)$，取 $\tau_0 = \text{clip}(\hat{\tau}_{\text{dev}}, 0.15, 0.80)$。
     2. `DGP2_skew`（有界强偏斜且簇内相关分布）：在每个簇 $i$ 上由三元标准正态 $(Z_1, Z_2, Z_3)$（两两相关系数 $\rho = 0.5$）经正态 CDF 与 $\text{Beta}(2, 8)$ 逆 CDF 变换得边际严格服从 $\text{Beta}(2, 8)$（精确均值 $0.2$）的 $(U_1, U_2, U_3)$，令 $\varepsilon_{j,i} = 40.0 \times (U_{j,i} - 0.2) \in [-8.0, +32.0]$（每簇精确均值 $0$）；`E3_H4` 取 $\tau_0 = 0.50$。
     3. `DGP3_ties`（高并列离散三点分布与低不一致率）：$\varepsilon_{j,i} \in \{-30.0, 0.0, +30.0\}$ 按概率 $(0.30, 0.40, 0.30)$ 独立抽取（每簇精确均值 $0$）；`E3_H4` 取 $\tau_0 = 0.15$。
     4. `DGP4_het`（`A_plan` $16$ 簇 vs `A_pure` $64$ 簇固定配额强异质性分布，子类内期望为 $\delta_h$、全集 80 簇配额加权平均期望精确为 $0$）：
        - 连续三槽（$j \in \{1, 2, 3\}$）：令 `A_plan`（$16$ 簇，权重 $16/80 = 0.20$）偏移 $\delta_{\text{plan}} = +12.0$，`A_pure`（$64$ 簇，权重 $64/80 = 0.80$）偏移 $\delta_{\text{pure}} = -3.0$——全集加权平均期望恒为 $\frac{16(+12.0) + 64(-3.0)}{80} = 0.0$；每簇 $\varepsilon_{j,i} = \delta_{h(i)} + \eta_{j,i} \in [-32.0, +32.0] \subset [-35.0, +35.0]$，其中 $\eta_{j,i} \sim \text{Uniform}(-20.0, +20.0)$。
        - 离散槽（`E3_H4`，$80 = 16_{\text{plan}} + 64_{\text{pure}}$）：固定 $\tau_{\text{sub}} = 0.70$，令 $\theta_{4,\text{plan}} = \bar{\theta}_4 + 0.20$，$\theta_{4,\text{pure}} = \bar{\theta}_4 - 0.05$（加权均值恒为 $\bar{\theta}_4$）。
     5. `DGP5_endpt`（70% 极端边界端点堆积与高方差双峰分布，回应 `c` 阻断 4）：
        - 连续三槽（$j \in \{1, 2, 3\}$）：$\varepsilon_{j,i} \in \{-35.0, 0.0, +35.0\}$ 按概率 $(0.35, 0.30, 0.35)$ 独立抽取，使高达 **70% 的概率质量直接堆积在有界扰动区间 $[-35.0, +35.0]$ 的两侧极限端点**（每簇精确均值 $\mathbb{E}[\varepsilon_{j,i}] = 0.0$，方差 $\text{Var}(\varepsilon_{j,i}) = 0.70 \times 35^2 = 857.5$）；`E3_H4` 取边界低不一致率 $\tau_0 = 0.15$。
   - **4 类真值/缺失配置（Cfg A–D）**：
     1. `CfgA_all_null_comp`：$\boldsymbol{\theta} = (0.0, 0.0, 0.0, 0.0)$（$I_0 = \{1,2,3,4\}$），0% 缺失；
     2. `CfgB_half_null_comp`：$\boldsymbol{\theta} = (20.0, 0.0, 15.0, 0.0)$（$I_0 = \{2, 4\}$），0% 缺失；
     3. `CfgC_alt_null_comp`：$\boldsymbol{\theta} = (0.0, 25.0, 0.0, 0.35)$（$I_0 = \{1, 3\}$），0% 缺失；
     4. `CfgD_all_null_miss2`：$\boldsymbol{\theta} = (0.0, 0.0, 0.0, 0.0)$（$I_0 = \{1,2,3,4\}$），在每簇 8 个不相交底层条件读数上各自独立以 $0.01$ 概率注入缺失（连续缺失代入 `[0.0, 100.0]`，离散缺失代入 `[0, 1]`，使每槽约 $1 - 0.99^2 = 1.99\%$ 的簇承受最不利界限拓宽）。
   - **四项准入硬闸门与候选选择/降级/停止规则**：与 `PLAN-E2.md` §4.2 第 6 条完全一致（`fwer <= 0.059747`、`simultaneous_coverage_9875 >= 0.940253`、`individual_coverage_9875 >= 0.975`、`screen05 <= 0.075` 必须在全部 **20 格**同时通过；依次评估 `Candidate 1 = hybrid_pct_tango_e3` $\to$ `Candidate 2 = hybrid_bessel_t_tango_e3` $\to$ 最多一次 1–2 个连续槽降级重验［维持 $m=4$ 分母］ $\to$ 否则触发 `calibration_failed_stop_s5` 严禁进入 S5）。

### 4.3 第三层描述性与探索性分析（预先锁定，不占确认性 $\alpha$）
1. **子类分解（`A_plan` 16 簇［含 `A_plan_task` 15 簇、`A_plan_deg` 1 簇］ vs `A_pure` 64 簇）**：在全部 13 个 `(task, prompt)` 条件下分别报告各子类的四槽轨迹、`E3_H1..E3_H4` 子类点估计与置信区间。
2. **与实验 1 同簇原题（`D_k` / `B_k` 光杆 $H_{\text{orig}}$）的簇内配对对照**：利用实验 3 与实验 1 共享完全相同的 80 个正式簇（及 20 个开发簇），在每个 `(task, prompt)` 下直接计算每簇 `NI_OCC - D_orig`、`NI_PLAN - D_orig`、`INT_OCC - B_orig`、`INT_PLAN - B_orig` 的描述性分布，作为解释实验 1 `SA3`/`SA4` 的跨实验对照证据。
3. **剔除 `095` 簇的 79 簇敏感度复核（回应 `c` 阻断 5）**：使用独立种子 `SENS79_ANALYSIS_SEED_E3 = 2026110403`（`B = 5000`）、扩展常数 $c_{79} = 1.0302596947224958$ 及 `exact-tango-tables-e3.npz` 中预计算的认证 `n = 79` 表，并列输出剔除唯一经过 `" all day"` 去尾归一化的 `095` 簇后的 79 簇 `E3_H1..E3_H4` 点估计与置信区间。
4. **13 条件全矩阵、多估计权重偏差 $\Delta = M_W - M_U$ 与三标签完整分布表**。

---

## 5. 阶段、闸门与停止规则（S0–S7）

| 阶段 | 内容 | 闸门与停止规则 |
| :--- | :--- | :--- |
| **S0** | 锁定 `subclasses_e3.json`、`split.json`、派生 `data/clusters_100_e3.json` 及认证 Tango 查表 `manifests/exact-tango-tables-e3.npz` 的 SHA-256 | `validate_materials_e3.py` 100/100 零错误、全部非 `data/` 文件零豁免字节扫描 0 原句泄漏且 15/15 负向自检通过；开发集 20 簇与正式集 80 簇与实验 1 `atelic_clusters` 完全一致；`exact-tango-tables-e3.npz` 独立构建覆盖 `n in (8, 12, 16, 20, 64, 79, 80)` 且 21/21 有理数证书通过、0 单调性违例 |
| **S1** | 生成开发集 20 簇预览 `data/s1_preview_e3.md` 与无原题模板预览 `s1_preview_templates_e3.md`，送 `c` 审查 `PLAN-E3.md` | `prompts_e3.py` 通过 `PARSE_VERSION = 2` 全 13 格兼容自检；`c` 审查无阻断；用户确认 S1 预览 |
| **S2** | 构建 `exp3-en/` 独立运行器、计分器、统计核心 `core_e3.py`、`calibrate_e3.py` 与单测套件 | 单元测试全过；首 token 互斥核验通过；`c` 审查 S2 代码无阻断 |
| **S3** | Mac mini 真实冒烟（开发集代表簇 `011, 017, 077`） | 任一单元不可用则停下诊断；诊断语境 `P/Z` 下 `Pos > Neg` 方向正确 |
| **S4** | 开发集完整运行（`1,040` 主单元 + `120` 诊断单元 = `1,160` 单元）+ 20 单元确定性重跑 + `calibrate_e3.py`（20 格，`R=2000, B=5000`）统计校准核验 | 任一格首次可用率 $< 90\%$ 或整体缺失率 $> 2\%$ 则停下修解析；诊断语境 `P/Z` 下全集与三模具子类均报告 `Pos`/`Neg` 均值且全集 `mean(Pos) >= 80, mean(Neg) <= 20`；四槽完整开发簇数均 $\ge 15$；`calibrate_e3.py` 通过全部 20 格四项硬闸门 |
| **S5** | 冻结 `exp3-en/PLAN-E3.md`（生成 `freeze.json`），构建并推送公开预注册包（`imperfective-exp3-en/`）至 `asj252/llm-judgment-studies` | `c` 预冻结审查无阻断 + 用户确认冻结与推送；公开预注册提交时间严格早于 S6 首条正式 unit |
| **S6** | Mac mini 正式集 80 簇（`320 题 × 13 = 4,160` 单元）执行 | `statistics.json` 闸门 `pass` |
| **S7** | 正式集统计分析、双端独立复现核账、知識庫沉淀与报告生成 | 双端逐位一致 |

---

## 6. 对 `c` 第 1 轮审查（`review-plan-e3-codex.md`）的逐项回应与修订记录

| 审查项 | `c` 第 1 轮问题摘要 | v0.2 处置与落位 |
| :--- | :--- | :--- |
| **阻断 1** | `all the way to completion`、`completely`、`throughout the entire period` 在原前提未给定任务/程度终点或观察期起止点时依赖语境补全，不能声称脱离语境的语义消歧 | 已在标题、§1 第 3 点、§2.1 与 §4.1 明确收窄定位：将 `(h_occ, h_plan)` 界定为「受控单槽位体貌修饰语及其诱发的语用完结/时段补全（pragmatic completion/period accommodation）对比」，不声称脱离语境的绝对真值消歧。 |
| **阻断 2** | `PLAN-E3.md` 第 15、18、54 行及 `validate_materials_e3.py` 第 156 行含上游原句全文；第 2 轮指出扫描器对 `raw/`、`server_logs/` 及扩展名存在豁免 | 已从 `PLAN-E3.md` 与 `validate_materials_e3.py` 彻底清除全部上游原句；在 v0.3 中取消除 `data/` 以外的一切子目录与扩展名豁免，按 UTF-8 字节序列扫描全部非 `data/` 文件，并新增 `M12`–`M15` 四项路径/扩展名泄漏探针（15/15 项负向突变全拦截）。 |
| **阻断 3** | `validate_materials_e3.py` 未逐簇核对 `imperfectiveNLI.json` 原句与 `subclasses_e3.json`、`split.json` 重建一致性 | 已在 `validate_materials_e3.py` 中加入对 `imperfectiveNLI.json`（`p_no_int, p_int, h_orig, upstream_d_id, upstream_b_id`）、`build_subclasses_manifest()` 与 `build_split_manifest()` 的逐项全等绑定，并新增 `M10_upstream_record_swap` 与 `M11_subclasses_manifest_tamper`。 |
| **阻断 4** | S4 校准矩阵缺少端点堆积情景；第 2 轮指出 v0.2 新增的最小点质量说明（`>=0.15`）及 Bahadur–Savage 普遍必然拒绝推导不准确 | 已在 §4.2(5) 新增第 5 类分布 `DGP5_endpt`（扩充为 **5 DGP × 4 Cfg = 20 格校准矩阵**）；在 v0.3 §4.2(1) 删除不准确的统一最小点质量数值与过强的普遍推导，准确限定为本计划两套候选程序在稀有负尾漏抽样本上的具体误拒风险与不覆盖分布范围声明。 |
| **阻断 5** | 79 簇敏感度复核缺少认证的 `n = 79` Tango 表与 $c_{79}$ 扩展常数 | 已在 `exact_tango_e3.py` 的 `SUPPORTED_NS` 中加入 `79`（`SUPPORTED_NS = (8, 12, 16, 20, 64, 79, 80)`，21/21 有理数左截断证书通过），并在 §4.2(1)-(2) 与 §4.3(3) 锁定 $c_{79} = 1.0302596947224958$ 与专用种子 `SENS79_ANALYSIS_SEED_E3 = 2026110403`。 |
| **阻断 6** | `exact_tango_e3.py` 存在跨目录读取 `exp2-zh/` 与旧校准目录的复用逻辑 | 已从 `exact_tango_e3.py` 彻底删除 `_try_load_existing_res_for_n` 跨目录复用函数，全部 7 个样本量均在 `exp3-en/` 内 100% 独立从头构建并认证。 |
| **建议 1–4** | 诊断语境解释边界与指代统一；`B_k` 表述为转折前提；收窄机制归因措辞；修正 $X+Y=100$ 表述 | 已统一 `p_diag_neg` 为 `but that ended early...` 并收窄诊断语境为管道/极性方向检查且按三模具子类分层报告（§2.2(5)）；将 `E3_H3` 表述为原 `D_k` vs `B_k` 前提对比（§4.1）；收窄 §1 与 §4.1 归因措辞；将 $(X_{j,i}, Y_{j,i})$ 修正为对称中心化配对底层条件读数（§4.2(5)）。 |
| **疑问 1–2** | `DGP1_emp` 开发集缺失筛选、中心化与停止规则；`B_k` 盲性表述边界 | 已在 §4.2(5) 明确 `DGP1_emp` 完整开发簇筛选、$|K_{\text{ok}, j}| \ge 15$ 硬闸门（否则 `insufficient_complete_dev_clusters_stop_s5`）与中心化规则；已在 §2.1 明确界定「代码与闭集映射不使用 `B_k`」而非人类阅读公开数据集前的双盲。 |
