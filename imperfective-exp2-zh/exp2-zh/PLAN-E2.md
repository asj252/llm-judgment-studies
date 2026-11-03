# 实验 2（中文版）：体貌标记、结果补语与有界活动补语的机率读数（计划草案 v0.6）

- 实例：`#imperfective`；计划树节点：`P16.5`；日期：2026-11-02；起草：a。
- 状态：**草案 v0.6（已按 `c` 第一至四轮审查意见 `review-plan-e2-codex.md`、`review-plan-e2-r2-codex.md`、`review-plan-e2-r3-codex.md`、`review-plan-e2-r4-codex.md` 完成全部闭环修订，送 `c` 第五轮复核）**。
- 上游依据：总计划 `../PLAN.md` 第 6、7 节（保持只读，不改动其 SHA-256）；实验 1 冻结规范 `../s5-mac-handoff-20261101/PLAN-E1.md` 与正式集报告 `../s5-mac-handoff-20261101/results/report-s7-formal.md`。
- 实验隔离原则：本实验全部材料、代码、提示、解析器副本、精确 Tango 查表清单、账本与冻结记录均独立存放于 `connecting-dots/imperfective/exp2-zh/`，运行 ID 前缀为 `E2-`，不读取也不修改 `exp1-en/` 的任何生产文件。

---

## 1. 研究动机与核心问题

在实验 1（英文 `ImperfectiveNLI`，`Qwen3-8B` 正式集 `4,160` 单元）中，我们观察到：
1. **零样本多估计压低高端点堆积（`SA1`）**：在 `C` 组（无中断终结事件）上，`M_U/Z` 将 $\ge 95\%$ 高端点率从 `P/CoT` 的 `26.25%` 压低至 `1.25%`（`p_Holm = 1.312e-05`）。
2. **`CoT` 保持终结类中断敏感度（`SA2`）**：在终结簇 `AC` 上，`P/CoT` 的中断降幅 `C - A = 32.69` 高于 `M_U/Z` 的 `23.54`（`p_Holm = 0.003199`）。
3. **英文非终结活动在 `CoT` 下的标签坍缩与机率平行下移（`SA4` 与 `SA3`）**：
   - 在离散标签任务下，`L/CoT` 虽令 `C` 组 `True` 比例归零，却导致 `D` 组（无中断非终结活动，如 `was running on the track`）`True` 比例从 `100.0%` 暴跌至 `8.75%`（73/80 题转为 `Unknown`，`p_Holm = 1.818e-21`）。
   - 在多估计机率任务下，`M_U/CoT` 将 `B`（中断活动）与 `D`（无中断活动）同步拉低约 22 个百分点（`95.01% -> 72.20%`、`88.04% -> 65.37%`），导致 `SA3` 未见优势。

### 核心语言学对比：从英文形态混同到中文语法分离
英文一般过去时（Simple Past `V-ed`，如 `ran on the track`、`pushed the broken car`、`built the gazebo`）在表层形态上混同了两种事件读法：
- **读法一（动作发生 / 起始实现，Minimal Occurrence / Actualization）**：该动作在观察期内是否至少实际发生过片刻？
- **读法二（终点达成 / 有界量程或满足度达成，Culmination / Bounded Completion or Satiation）**：该动作是否达到了自然终点、预设任务终点或主观满足界限？

现代汉语在语法层面上可将这两类读法拆分为显式配对构式：
1. **光杆动词 + 词尾「了」（`V了`，记为 `h_bare`）**：仅带词尾完成体标记「了」而不带结果/完结/满足补语（如「盖了那座木亭」「写了那封辞职信」「在体育场跑道上跑了步」「在湖边步道上散了步」）。
2. **核心动词 + 单字/双字补语 + 「了」（`V + comp_marker + 了`，记为 `h_comp`）**：在 `h_bare` 的核心动词与「了」之间插入显式补语 `comp_marker`，其余词序、时间锚点、施事、处所与有定受事与 `h_bare` **逐字全等**：
   - **终结类（`T`，全集 60 簇：开发集 12 簇、正式集 48 簇）**：使用结果/完结补语（全集 60 簇精确频数为：`好` 31 簇、`完` 16 簇［其中开发集 4 簇、正式集 12 簇］、`干净` 4 簇、`干` 2 簇、`断` 2 簇、`光` 2 簇、`熟` 1 簇、`平整` 1 簇、`锋利` 1 簇；其中 `Motion to Goal` 6 簇 `T_10, T_66, T_67, T_68, T_70, T_71` 统一使用全程完结补语 `完`，如「爬完了那段登山石道」「登完了那段古塔石阶」，并在中断前提中明确将中断位置绑定在「那段石道的开头一小截」「那段石阶的头几级」等起点处，彻底消除「爬上了」的表面登临歧义与路径终点位置歧义）。
   - **非终结活动类之带常见计划/任务活动材料类（`A_plan`，全集 20 簇：开发集 4 簇、正式集 16 簇）**：统一使用任务完结补语 **`完`**（20/20 簇，如「跑完了步」「推完了那辆抛锚的轿车」「弹完了钢琴练习曲」「骑完了公路自行车」）。
   - **非终结活动类之纯无界休闲/感官活动材料类（`A_pure`，全集 20 簇：开发集 4 簇、正式集 16 簇）**：由于纯无界休闲/感官活动在自然汉语中不预设客观任务终点，统一使用主观满足度有界补语 **`够`/`足`**（`够` 18 簇、`足` 2 簇，如「散够了步」「吹够了晚风」「晒足了太阳」）。

> **相对总计划 `PLAN.md` 第 6 节的设计扩展记录（保持顶层 `PLAN.md` 只读）**：
> 总计划 `PLAN.md` 第 6 节最初仅要求非终结类测试 `V了`（`h_bare`），且跨大类只比较共有形式 `V了`。本实验 `PLAN-E2.md` 在完全保留非终结类 `h_bare` 及「跨大类只比较共有形式」规则的基础上，**为非终结类每簇新增了严格插入最小对 `h_comp`**（`A_plan` 插入任务完结补语 `完`，`A_pure` 插入满足度补语 `够`/`足`），使每个事件簇均构成完整的 $2 \times 2$ 簇内配对设计。鉴于 `A_pure`（满足度补语 `够/足`）与 `A_plan`（任务完结补语 `完`）的补语语义功能不同，凡涉及非终结类 `h_comp` 的分析（如 `E2_H3` 与 `E2_H4`），主报告除给出 32 簇非终结类汇总检验外，**必须并列报告 `A_plan`（16 簇，`V了` vs `V完了`）与 `A_pure`（16 簇，`V了` vs `V够/足了`）的分层估计与置信区间**；跨大类（`T` vs `A`）探索性对比仅在同为 `h_bare`（光杆 `V了`）或同为 `完` 补语（正式集 `T` 中 `完` 补语 12 簇子集 vs 正式集 `A_plan` 16 簇）下进行。

---

## 2. 材料构造、句法铁律与开发/正式集分割

### 2.1 100 组中文事件簇构成与事前分类判据（`data/clusters_100_curated.json`）
- 数据文件：`exp2-zh/data/clusters_100_curated.json`（SHA-256 `963636a2a74a38f8b8fe6363a079be38f5f2f1b35ef37f1cf3fc89dd7fd6c437`，纯 UTF-8 LF，由 `curate_100_clusters.py` 统一生成，经 `validate_materials.py` 机械与形态校验 `100/100` 零错误，且通过 9 项负向突变自检）。
- 抽样与重抽基本单位：**事件簇（Cluster）**，共 **100 簇**（每簇含 4 条主实验题 + 2 条诊断语境题 = 6 句，100 簇共 **400 条主实验题 + 200 条诊断语境题**）：
  1. **终结类（`macro_class = "telic"`，共 60 簇，240 条主实验题）**：
     - `Creation`（建造/创制）：26 簇
     - `Change of State`（状态改变/修复/清理/烹调）：18 簇
     - `Consumption`（消耗/饮食/阅读）：10 簇
     - `Motion to Goal`（趋向目标全程位移，统一用 `完`）：6 簇
  2. **非终结活动类（`macro_class = "atelic"`，共 40 簇，160 条主实验题）**：
     - `Pure Unbounded Activity`（纯无界持续活动材料类，`A_pure`）：20 簇
     - `Goal-Prone / Planned Activity`（带常见计划/任务量程的活动材料类，`A_plan`）：20 簇
- **`A_plan` 与 `A_pure` 的事前分类判据、任务补全说明与解释边界（回应 `c` R1 疑问 1 与 R2 建议 2）**：
  - 事前分类判据：在接触任何模型输出前，按日常汉语词汇—语用常规将非终结持续活动划分为两类材料——(a) `A_plan`：体育训练、器械练习、路线推进、清洁整理或研习背诵等在日常语境中常伴随单次训练/作业量程的活动，在语法上接受完结补语 `完`（`V完了O`）；其中 `A_plan_02`（`推那辆抛锚的轿车`）、`A_plan_05`（`骑公路自行车`）、`A_plan_10`（`划皮划艇`）、`A_plan_12`（`骑动感单车`）、`A_plan_21`（`打悬挂沙袋`）已统一采用自然动宾搭配（消除了早期草稿中「练习动感单车」等生硬表达），且需明确标注：**此类无内在自然终点的活动搭配完结补语 `完`（如「骑完了公路自行车」「划完了皮划艇」「推完了那辆抛锚的轿车」）在汉语语用中依赖读者/模型补出隐含的单次训练或作业任务量程（即以「语用任务补全」本身作为研究对象）**；(b) `A_pure`：散步、乘凉、晒太阳、赏景、抚摸宠物等无预设工作配额的休闲/感官持续活动，在语法上以主观满足度补语 `够/足`（`V够/足了O`）标记有界化。
  - 解释边界：`A_plan` 与 `A_pure` **仅解释为事前预定的两类词汇—材料子类（连同各自配对的补语类型 `完` vs `够/足`）**；前提句中不写入显式数字配额（以免把非终结活动直接改成终结性受限事件），因此不将 `A_plan` 与 `A_pure` 的差异过度解读为对施事者内在心理意图的纯粹单因素操纵。

### 2.2 句法模具与五项硬性护栏（由 `validate_materials.py` 逐簇强制核验并经 9 项负向突变自检）
1. **同一观察期与唯一施事/受事锁定**：每簇全部 6 个句子必须以完全相同的观察期时间锚点 `temporal_anchor`（如 `"那天下午"`）加中文逗号 `"，"` 开头，并包含完全相同的唯一施事者 `agent`。
2. **进行体前提禁漏任何补语（回应 `c` R2 阻断 5）**：`p_no_int` 固定使用 `"正在"` + 动作短语，必须包含核心动词 `verb_root`，且严禁出现 `verb_root + m`（其中 `m` 遍历全补语表 `ALL_COMP_MARKERS` 共 23 个结果/完结/满足/趋向补语标记：`"完", "好", "干净", "熟", "光", "够", "足", "上", "下", "进", "出", "开", "碎", "满", "透", "通", "穿", "掉", "成", "干", "断", "平整", "锋利"`，不仅拦截当前簇的 `comp_marker`，也拦截任何其他补语如 `"正在……盖完"` 的泄漏）。
3. **中断前提（`p_int`）必须先启动实施、再于早期中途停止、且封闭整个观察期（回应 `c` R1 阻断 2、R2 阻断 1）**：
   - `p_int` 必须以 `p_no_int[:-1] + "，"` 为严格前缀；
   - 中断发生前必须明确交代**核心动作已实际开展了片刻或开头一小部分**；特别地，对 `Motion to Goal` 全部 6 簇（`T_10, T_66, T_67, T_68, T_70, T_71`），中断位置明确锚定在**该段路径/石阶/岩壁的起点处**（`刚爬了那段石道的开头一小截`、`刚登了那段石阶的头几级`、`刚攀上那面岩壁底部两米高`、`刚跑了那段石道的开头二十米`、`刚登了那段石阶的头几级`、`刚爬了那段长石阶的头十级`），确保中断严格发生在该有界路径终点之前；
   - 中断原因不得包含任何暗示后续重做或恢复的词语（禁用 `"重做"`, `"重来"`, `"买漆"`, `"找备用拍"`）；
   - 每条 `p_int` 句尾统一强制闭合观察期：**`，且直到{temporal_anchor}结束都没再继续。`**，从逻辑上排除「暂停后又在同一观察期内恢复并完成」的可能。
4. **配对假设（`h_comp` vs `h_bare`）严格单点插入最小对（回应 `c` R1 阻断 3）**：
   - `h_comp` 必须包含 `f"{verb_root}{comp_marker}了"`，`h_bare` 必须包含 `f"{verb_root}了"`；
   - `h_bare` 严禁残留 `ALL_COMP_MARKERS` 中的任何补语（拦截一切 `f"{verb_root}{m}了"`）；
   - **逐字全等铁律**：`h_comp.replace(f"{verb_root}{comp_marker}了", f"{verb_root}了", 1) == h_bare` 必须对全部 100 簇 100% 成立，确保 `h_comp` 与 `h_bare` 除 `comp_marker` 外无任何词汇、把字句或语序差异。
5. **诊断语境（`p_diag_pos` / `p_diag_neg`）逐字由 `p_no_int` 与 `h_comp` 谓语确定性派生并强制全等核验（回应 `c` R1 阻断 4、R2 阻断 5）**：
   - 设 `hc_pred = h_comp[len(f"{temporal_anchor}，{agent}"):]` 为 `h_comp` 去掉时间锚点与施事后的完整谓语（如 `"盖好了那座木亭。"`、`"晒足了太阳。"`、`"摸够了自家的橘猫。"`），`hc_pred_neg = hc_pred.replace(f"{verb_root}{comp_marker}了", f"{verb_root}{comp_marker}", 1)` 为去掉补语后紧跟的 `"了"` 的未完成谓语（如 `"盖好那座木亭。"`、`"晒足太阳。"`、`"摸够自家的橘猫。"`）；
   - `validate_materials.py` 逐簇强制要求 `p_diag_pos == f"{p_no_int[:-1]}，并且在{temporal_anchor}结束前就{hc_pred}"` 且 `p_diag_neg == f"{p_no_int[:-1]}，但直到{temporal_anchor}结束都还没有{hc_pred_neg}"` 逐字全等（任何将谓语篡改为 `"……就回家了。"` 或 `"……还没有回家。"` 的突变均被直接拦截）。

### 2.3 簇内 4 个主实验条件格（2 前提 × 2 假设）及其测量定位（回应 `c` R2 阻断 1、R3 建议 4）
每个簇 $k$ 展开为 4 条主实验题（记为簇内 4 槽 `(slot_name, premise_key, hyp_key)`）：
1. **`NI_COMP`（`p_no_int` + `h_comp`）**：无中断进行体下询问结果/完结/满足补语假设（终结类对应英文 C 组；因 `p_no_int` 仅陈述动作正在进行而未交代观察期内是否达到终点或满足界限，未保证 `h_comp` 成立）。
2. **`NI_BARE`（`p_no_int` + `h_bare`）**：无中断进行体下询问光杆 `V了` 假设（检验动作发生读法在终结类与非终结类上的可接受度；在非终结活动类上对应英文 D 组）。
3. **`INT_COMP`（`p_int` + `h_comp`）**：早期中途停止且观察期内未再继续下询问补语假设：
   - **不将全集 `INT_COMP` 预设为单一 `False` 正确标签（回应 `c` R2 阻断 1、R3 建议 4）**：
     - 在**终结类（`T`，60 簇）**中，`p_int` 明确交代受事或有界路径仅开展了开头一小部分（如仅砌了三层砖、仅刷了半幅门板、仅爬了那段石道的开头一小截）即被迫停止且直到观察期结束未再继续，与结果/完结补语 `h_comp` 相冲突；
     - 在**非终结活动类（`A_plan` 与 `A_pure`，40 簇）**中，为了避免在 `p_int` 中直接写入「还没推完」「还没晒足」等显式词汇否定（否则会把 `INT_COMP` 变成表面反义词匹配），`p_int` 仅交代动作刚开展极短时间或极短距离（如刚晒/泡/养神/烤火了两分钟、刚往前推了两米、刚骑出去一公里）即被迫中断且观察期内未再继续。由于前提未显式给定任务总配额或主观满足阈值，**对非终结活动类的 `INT_COMP` 不预设单一正确标签**，在分析中直接报告模型输出的完整 `{True, False, Unknown}` 三标签分布，并以配对机率差 `INT_BARE - INT_COMP`（`E2_H3`）度量中断语境下光杆 `V了` 与有界补语 `h_comp` 的读数分离。
4. **`INT_BARE`（`p_int` + `h_bare`）**：早期中途停止且观察期内未再继续下询问光杆 `V了` 假设（非终结类对应英文 B 组，动作已实际发生片刻但未完结全程；终结类检验半途而废时中文光杆 `V了` 的残留可接受度）。

### 2.4 开发集与正式集分层分割及真实来源说明（`split.json`，种子 `2026110202`）
- **材料产生与分割流程说明（回应 `c` R1 建议 1）**：100 簇材料由 `a` 起草 18 组种子簇、`Gemini 3.8 Flash` 扩写 102 组候选簇后，先经 `curate_100_clusters.py` 统一筛选、去重并完成全集 100 簇的语言学与句法模具修订，再由 `split_e2.py` 按固定种子 `2026110202` 分层分割为开发集（20 簇）与正式集（80 簇）。因此，正式集 80 簇的准确表述为：**「经全集统一语言学整理与机械校验后分层划出的保留集，在 S5 冻结前 100% 未参与任何受测模型预览（S1）、冒烟（S3）或开发集试跑（S4），无任何模型输出泄漏」**。
- **分层配额（6 个子类严格按 20% / 80% 比例切分，回应 `c` R2 建议 1）**：
  - **开发集（`dev`，20 簇 = 80 条主实验题 + 40 条诊断语境题）**：含全部 18 组种子簇（`T_01..T_10, A_pure_01..04, A_plan_01..04`）+ 分层随机抽出的 **`T_15`**（`Creation`）与 **`T_47`**（`Change of State`）。6 个子类簇数为：`Creation` 5、`Change of State` 4、`Consumption` 2、`Motion to Goal` 1（合计 $n_{T,\text{dev}} = 12$）；`Pure Unbounded Activity` 4、`Goal-Prone / Planned Activity` 4（合计 $n_{A,\text{dev}} = 8$）。
  - **正式集（`formal`，80 簇 = 320 条主实验题）**：6 个子类簇数为：`Creation` 21、`Change of State` 14、`Consumption` 8、`Motion to Goal` 5（合计 $n_T = 48$）；`Pure Unbounded Activity` 16、`Goal-Prone / Planned Activity` 16（合计 $n_A = 32$）。

---

## 3. 任务、中文提示模板与输出协议

### 3.1 任务与提示组合（每条主实验题 13 个单元，与实验 1 完全同构）
- **任务**：`L`（严格逻辑三分类标签 + 标签首字母位置对数空间三标签归一化分数区间 `[q_L, q_U]`）、`Ps`（严格逻辑必然性机率，仅跑 `Z`）、`P`（常识单点机率）、`M`（常识 5 估计加权/等权多估计）。
- **提示**：`Z`（零样本）、`DAP`（加语言学体貌定义）、`CoT`（先分析事件时间状态与终点再作答）、`CF`（先列举 3 个动作发生但结果未达成的现实情境再作答）。
- **单元规模**：
  - 开发集主实验：`80 题 × 13 条件 = 1,040 单元`；另开发集诊断语境：`20 簇 × 2 诊断前提（Pos/Neg，固定配 h_comp）× 3 零样本任务（L/Z, P/Z, M/Z）= 120 诊断单元`。
  - 正式集主实验：`320 题 × 13 条件 = 4,160 单元`（与实验 1 正式集单元数完全一致）。

### 3.2 逐字中文提示模板与 `PARSE_VERSION = 2` 兼容规范（回应 `c` R1 阻断 1 与建议 4）
所有中文提示均由 `exp2-zh/prompts_zh.py` 渲染，并经 `prompts_zh.py:verify_parser_compatibility()` 对照本实验独立解析器副本 `exp2-zh/parse.py`（SHA-256 `b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342`，`PARSE_VERSION = 2`）完成回归核验：

1. **三标签公共定义块（`LABEL_DEFS_ZH`，在 `L/Z, L/DAP, L/CoT, L/CF` 及 `Ps/Z` 系统提示中逐字共用，忠实对齐上游 P1）**：
   ```text
   - 如果仅根据所给前提，该假设必然为真，请输出 "True"。
   - 如果该假设与所给前提相矛盾（必然为假），请输出 "False"。
   - 如果该假设可能为真，但并未被所给前提明确保证，请输出 "Unknown"。
   ```
2. **语言学定义段（`DAP_RULE_ZH`，用于 `L/DAP`、`P/DAP`、`M/DAP`）**：
   ```text
   重要语言学规则：请注意区分“终结性动作”与“持续性活动”。
   - 对于有特定目标或自然终点的动作（例如“正在盖”“正在写”），进行体（“正在……”）并不蕴含该动作最终完成。
   - 对于无特定自然终点的持续性活动（例如“正在跑”“正在散步”），进行体即蕴含该活动已经发生。
   ```
   *适配说明*：上游英文模板举例为 `"was running", "was singing"`；因本实验非终结材料以 `"正在跑"`、`"正在散步"` 为代表，此处将第二个例子适配为 `"正在散步"`，且未提及任何实验操纵形式（未剧透 `h_comp` vs `h_bare`）。
3. **`L` 任务四提示模板（已移除 `v0.2` 中 `L/Z` 与 `L/DAP` 额外添加的「请严格区分动作已经发生与完成」提示语，确保 `L/Z` 为纯净的上游 P1 中文基线；`L/CF` 严格使用 `"possible_interruptions"` 键名）**：
   - **`L/Z` 系统提示**：
     `你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n{LABEL_DEFS_ZH}\n不要做任何常识性假设，仅使用所提供的文本信息。`
   - **`L/DAP` 系统提示**：
     `你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n{LABEL_DEFS_ZH}\n\n{DAP_RULE_ZH}\n\n不要做任何常识性假设，仅使用所提供的文本信息。`
   - **`L/Z` 与 `L/DAP` 用户消息**：
     `输入：前提：{premise} 假设：{hypothesis}\n请仅回答以下三个选项之一："True"、"False" 或 "Unknown"。`
   - **`L/CoT` 系统提示**：
     `你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n{LABEL_DEFS_ZH}\n不要做任何常识性假设，仅使用所提供的文本信息。\n请先分析前提中事件的时间状态：该动作是否有明确的终点？它是否已经完成？然后再给出最终标签。\n请严格输出一个 JSON 对象，依次包含两个键："reasoning"（你的简短中文分析字符串）和 "label"（取值为 "True"、"False" 或 "Unknown" 之一，且 "label" 必须作为最后一个键）。`
   - **`L/CF` 系统提示**：
     `你是一位严格的逻辑学家。你的任务是仅根据给定的“前提（Premise）”判断“假设（Hypothesis）”是否必然为真。\n{LABEL_DEFS_ZH}\n不要做任何常识性假设，仅使用所提供的文本信息。\n在判断假设是否必然为真之前，请先列出 3 个现实中可能发生的情境，使得前提中的动作正在发生，但假设中的结果最终未能实现（例如突发中断或意外失败）。然后再判断假设是否必然为真。\n请严格输出一个 JSON 对象，依次包含两个键："possible_interruptions"（包含 3 个非空中文情境字符串的 JSON 数组）和 "label"（取值为 "True"、"False" 或 "Unknown" 之一，且 "label" 必须作为最后一个键）。`
   - **`L/CoT` 与 `L/CF` 用户消息**：
     `输入：前提：{premise} 假设：{hypothesis}`
4. **`Ps/Z`（P-strict）**：
   - **系统提示**：与 `L/Z` 系统提示逐字相同。
   - **用户消息**：`输入：前提：{premise} 假设：{hypothesis}\n仅根据前提，该假设必然为真的机率是多少？\n\n请在回答的最后一行，严格按以下格式给出答案：\nProbability: NN%\n其中 NN 是 0 到 100 之间的数字（允许小数），后面必须紧跟百分号 %。`
5. **`P` 与 `M` 任务（仅 `user` 消息，段间以 `\n\n` 连接）**：
   - S1 段：`这里有一个情境：{premise}`
   - R 段（仅 `DAP`）：`{DAP_RULE_ZH}`
   - Q 段：`根据日常常识，下面这句话为真的可能性有多大？\n陈述：{hypothesis}`
   - T 段（仅 `CoT`）：`请先简要分析情境中事件的时间状态：该动作是否有明确的终点？它是否已经完成？然后再给出你的答案。`
   - T 段（仅 `CF`）：`请先简要列出 3 个现实中可能发生的情境，使得情境中的动作发生了，但陈述中的结果最终没有达成（例如中途被打断或失败）。然后再给出你的答案。`
   - A 段（`P` 用 `ASK_DIRECT_ZH`，`M` 用 `ASK_MULTI_ZH`，逐字见 `prompts_zh.py` 与 `s1_preview_zh.md`）。

---

## 4. 主确认检验家族（方案 E2，`m = 4`，$\alpha_{\text{fam}} = 0.05$）与封闭统计规范

### 4.1 四个主确认假设（`m = 4`）与严谨结论措辞（回应 `c` R1 建议 5 与疑问 2）

| 编号 | 检验对象与簇集 | 统计量定义 $\theta_j$ | 零假设与备择方向 | 确认性结论用语（拒绝 $H_0$ 时） |
| :--- | :--- | :--- | :--- | :--- |
| **`E2_H1`**<br>终结类无中断之结果补语效应 | 正式集终结簇 `T`<br>（$n_T = 48$ 簇）<br>前提：`p_no_int` | $\mu_T(\text{NI\_BARE}; P/\text{Z}) - \mu_T(\text{NI\_COMP}; P/\text{Z})$ | $H_0: \theta_1 \le 0$<br>$H_1: \theta_1 > 0$（单侧，整簇 bootstrap） | **方向确认**：「在无中断终结事件上，结果/完结补语假设 `h_comp` 的 `P/Z` 机率读数显著低于光杆 `V了` 假设 `h_bare`」。 |
| **`E2_H2`**<br>终结类结果补语之多估计读数差 | 正式集终结簇 `T`<br>（$n_T = 48$ 簇）<br>条件：`NI_COMP` | $\mu_T(\text{NI\_COMP}; P/\text{Z}) - \mu_T(\text{NI\_COMP}; M_U/\text{Z})$ | $H_0: \theta_2 \le 0$<br>$H_1: \theta_2 > 0$（单侧，整簇 bootstrap） | **方向确认**：「在无中断终结事件的结果/完结补语假设 `NI_COMP` 上，多估计等权平均 `M_U/Z` 的机率读数显著低于单点机率 `P/Z`」（仅称**接口读数下降**，不单独由 `E2_H2` 断言「去偏」）。 |
| **`E2_H3`**<br>非终结活动中断下「光杆发生 vs 有界补语」读数差 | 正式集非终结簇 `A`<br>（$n_A = 32$ 簇）<br>前提：`p_int` | $\mu_A(\text{INT\_BARE}; P/\text{Z}) - \mu_A(\text{INT\_COMP}; P/\text{Z})$ | $H_0: \theta_3 \le 0$<br>$H_1: \theta_3 > 0$（单侧，整簇 bootstrap） | **方向确认**：「在中断且观察期内未再继续的非终结活动上，光杆 `V了`（`INT_BARE`）的 `P/Z` 机率读数显著高于有界补语形式（`INT_COMP`）」（正文中必须紧跟并列报告 `A_plan`［`V了` vs `V完了`，$n=16$］与 `A_pure`［`V了` vs `V够/足了`，$n=16$］两个子类的分解效应）。 |
| **`E2_H4`**<br>非终结活动 `L/CoT` 下「光杆发生 vs 有界补语」`True` 判定率差 | 正式集非终结簇 `A`<br>（$n_A = 32$ 簇）<br>前提：`p_no_int` | $\Pr_A(\text{True on NI\_BARE}; L/\text{CoT}) - \Pr_A(\text{True on NI\_COMP}; L/\text{CoT})$ | $H_0: \theta_4 \le 0$<br>$H_1: \theta_4 > 0$（单侧，认证精确 Tango） | **方向确认**：「在无中断非终结活动的 `L/CoT` 任务下，光杆 `V了`（`NI_BARE`）的 `True` 判定率显著高于有界补语形式（`NI_COMP`）」（正文中必须并列报告 `A_plan` 与 `A_pure` 的分解效应，以及 `L/Z` 与 `L/CoT` 下的完整 `{True, False, Unknown}` 三标签比例；`E2_H4` 本身只确认 `L/CoT` 内部两槽的 `True` 率差，不单独断言差异全部来自 `Unknown` 或完全由 `CoT` 引起）。 |

### 4.2 封闭统计推断规范（回应 `c` R1–R4 全部统计审查项）

1. **推断目标总体、两大类整簇多项式重抽与统计保证边界（回应 `c` R1 疑问 3、R2 阻断 2、R3 阻断 1）**：
   - **推断目标**：本实验的推断目标定义为当前 6 子类构式配额设计下终结大类 `T`（正式集 $n_T = 48$，开发集 $n_{T,\text{dev}} = 12$）与非终结大类 `A`（正式集 $n_A = 32$，开发集 $n_{A,\text{dev}} = 8$）的簇平均效应（不越界宣称向任意未抽样中文动词总体外推）。
   - **按两大类（`telic` / `atelic`）整簇多项式重抽（对齐总计划 `PLAN.md` §4.2 与实验 1 `core_a.py`）**：
     - 统计推断的整簇 bootstrap 重抽按总计划 `PLAN.md` §4.2（「终结簇与非终结簇分层各自重抽，$B = 5,000$」）在**两大类（`telic` $n_T$ 簇与 `atelic` $n_A$ 簇）层面上各自独立做等权多项式重抽**：
     - 固定重抽次数 **`B = 5000`**；正式集种子 **`FORMAL_ANALYSIS_SEED_E2 = 2026110301`**，开发集种子 **`DEV_ANALYSIS_SEED_E2 = 2026110302`**；
     - 使用单一共享随机流 `rng = np.random.Generator(np.random.PCG64(seed))`：
       1. 先对按 `cluster_id` 字典序升序排列的 $n_T$ 个终结簇抽取权重矩阵 `w_T = rng.multinomial(n_T, np.full(n_T, 1.0 / n_T), size=B) / float(n_T)`（形状 `(B, n_T)`）；
       2. 再对按 `cluster_id` 字典序升序排列的 $n_A$ 个非终结簇抽取权重矩阵 `w_A = rng.multinomial(n_A, np.full(n_A, 1.0 / n_A), size=B) / float(n_A)`（形状 `(B, n_A)`）；
       3. 第三层探索性分析中针对 `A_plan`（$n=16$）或 `A_pure`（$n=16$）单子类的重抽，各自在子集内部按 `cluster_id` 升序调用 `rng.multinomial(n_sub, np.full(n_sub, 1.0 / n_sub), size=B) / float(n_sub)`。
   - **关于合并重抽与固定子类配额的统计声称边界（回应 `c` R3 阻断 1）**：
     - 鉴于普通等权多项式 bootstrap 的条件方差为 $\operatorname{Var}_*(\bar{d}^*) = \frac{n-1}{n}\frac{s_d^2}{n}$，且方差大小本身不能直接推出尾概率、分位数区间覆盖率或离散检验拒绝域的保序关系，本计划**不宣称大类合并重抽对固定子类配额具有解析上的自动向上保守包络保证**。
     - 遵循 `PLAN.md` §4.2「冻结稿里关于保护水平的措辞，按验证实际达到的水平写，不写高于验证结果的说法」的硬性纪律：两大类合并重抽（`hybrid_pct_tango_e2` 及伴随 `hybrid_bessel_t_tango_e2`）严格定位为**待校准的有限样本近似推断程序**；其在同质与固定配额子类异质情景下的第一类错误率与覆盖率结论，完全限定于 S4 校准矩阵（§4.2 第 6 条，含固定配额子类异质情景 `DGP4_het`）实测验证通过的范围。

2. **连续配对差（`E2_H1`、`E2_H2`、`E2_H3`）的两套候选推断方法与逐行对齐 `core_a.py` 的退化规则（回应 `c` R2 阻断 2、R3 建议 2）**：
   - **簇内配对差与观测点估计**：对第 $i$ 个簇，设被比较两单元的上下界为 $[X_{i,\text{lower}}, X_{i,\text{upper}}]$ 与 $[Y_{i,\text{lower}}, Y_{i,\text{upper}}]$，定义簇内配对差下界 $d^L_i = X_{i,\text{lower}} - Y_{i,\text{upper}} \in [-100, 100]$ 与上界 $d^U_i = X_{i,\text{upper}} - Y_{i,\text{lower}} \in [-100, 100]$。观测均值上下界为 $\hat{\theta}^L_j = \frac{1}{n}\sum_{i=1}^n d^L_i$，$\hat{\theta}^U_j = \frac{1}{n}\sum_{i=1}^n d^U_i$；重抽均值序列为 $\theta^{*,L}_{j,b} = \sum_{i=1}^n w_{b,i} d^L_i$ 与 $\theta^{*,U}_{j,b} = \sum_{i=1}^n w_{b,i} d^U_i$（$b = 0, \dots, B-1$，$B = 5000$）。
   - **候选方法 1（默认主方法 `hybrid_pct_tango_e2`：未插值次序统计量 Percentile Bootstrap）**：
     - 对各自独立升序排序后的 $B = 5000$ 个下界重抽值 $s_{\text{low},(0)} \le \dots \le s_{\text{low},(4999)}$ 与上界重抽值 $s_{\text{high},(0)} \le \dots \le s_{\text{high},(4999)}$：
       - **单项双侧 98.75% Bonferroni 同时置信区间**（对应 $m = 4$ 项家族的**单项显著性水平 $\alpha_{\text{ind}} = \alpha_{\text{fam}} / 4 = 0.05 / 4 = 0.0125$**，双侧单尾各 $\alpha_{\text{ind}} / 2 = 0.00625$，对应 **95% 家族同时覆盖目标 $\alpha_{\text{fam}} = 0.05$**）：取 0-based 下标 **`idx_lo = 31`**（1-based 第 32 个）与 **`idx_hi = 4968`**（1-based 第 4969 个），即 $\bigl[\text{ci\_lo}, \text{ci\_hi}\bigr] = \bigl[s_{\text{low},(31)},\; s_{\text{high},(4968)}\bigr]$；
       - **单项双侧 95% 伴随置信区间**（单项 $\alpha = 0.05$）：取 0-based 下标 **`idx_lo_95 = 124`** 与 **`idx_hi_95 = 4875`**，即 $\bigl[s_{\text{low},(124)},\; s_{\text{high},(4875)}\bigr]$；
     - **单侧 p 值（检验 $H_0: \theta_j \le 0$ vs $H_1: \theta_j > 0$）**：若 $\hat{\theta}^L_j \le 0$（点估计下界未落在备择方向），直接设 $p_j = 1.0$；若 $\hat{\theta}^L_j > 0$，则：
       $$p_j = \frac{1 + \#\{b \in \{0,\dots,B-1\} : \theta^{*,L}_{j,b} \le 0.0\}}{B + 1}$$
   - **候选方法 2 / 伴随敏感度方法（`hybrid_bessel_t_tango_e2`：基于同一重抽流的保序 Bessel-$t$ 中心外扩 Bootstrap）**：
     - 严格沿用实验 1 封存的 `core_a.py:infer_hybrid_bessel_t_tango_a` 数学定义（**不是参数法单样本 $t$ 检验**，而是对同一组重抽均值围绕观测点估计做保序向外扩展）：
     - 设当前假设所属大类的簇数为 $n$（正式集终结类 $n_T = 48, \text{df} = 47$；正式集非终结类 $n_A = 32, \text{df} = 31$；子类分解 $n = 16, \text{df} = 15$；开发集 $n = 12, \text{df} = 11$ 与 $n = 8, \text{df} = 7$），针对单项双侧 98.75% 置信水平（单尾分位点 $1 - \alpha_{\text{ind}}/2 = 0.99375$），定义有限样本 Bessel-$t$ 扩展因子：
       $$c_n = \sqrt{\frac{n}{n - 1}} \cdot \frac{t_{n - 1,\, 0.99375}}{z_{0.99375}} > 1$$
       经 70 位有效数字高精度求根（`decimal`）锁定常数为：
       - $c_{48} = 1.0509502165481253$（$\text{df} = 47$）
       - $c_{32} = 1.0787284625848519$（$\text{df} = 31$）
       - $c_{16} = 1.1729390393815105$（$\text{df} = 15$）
       - $c_{12} = 1.2465119462060201$（$\text{df} = 11$）
       - $c_{8} = 1.4275423213691008$（$\text{df} = 7$）
     - 对每次重抽 $b \in \{0, \dots, B-1\}$，构造保序向外扩展重抽界：
       $$\tilde{\theta}^{*,L}_{j,b} = \min\Bigl(\theta^{*,L}_{j,b},\; \hat{\theta}^L_j + c_n\bigl(\theta^{*,L}_{j,b} - \hat{\theta}^L_j\bigr)\Bigr), \qquad \tilde{\theta}^{*,U}_{j,b} = \max\Bigl(\theta^{*,U}_{j,b},\; \hat{\theta}^U_j + c_n\bigl(\theta^{*,U}_{j,b} - \hat{\theta}^U_j\bigr)\Bigr)$$
     - 单侧 p 值与置信区间在与候选方法 1 完全相同的规则与下标（`31 / 4968` 及 `124 / 4875`）下对排序后的扩展序列 $\tilde{s}_{\text{low}}, \tilde{s}_{\text{high}}$ 计算。
   - **逐行对齐 `core_a.py` 的贪心锚点唯一值计数与退化保护规则（在裁剪至 `[-100.0, 100.0]` 之前执行，回应 `c` R2 阻断 2、R3 建议 2）**：
     - **贪心锚点互异值计数（`_greedy_distinct_1d_sorted`，`core_a.py:235-245`）**：对已升序排序的一维重抽序列 $s_{(0)} \le \dots \le s_{(B-1)}$，初始化 `anchor = s[0], c = 1`，依次遍历 $v \in s_{(1..B-1)}$，仅当 `v - anchor > TOL_DUST`（其中 **`TOL_DUST = 1e-12`**）时令 `c += 1, anchor = v`；由此分别求得下界流互异重抽均值数 `u_low` 与上界流互异重抽均值数 `u_high`。
     - **四项退化判据（`core_a.py:641-644, 862-875`）**：对任一连续假设 $j \in \{1, 2, 3\}$，设未裁剪区间为 $[\text{raw\_ci\_lo}, \text{raw\_ci\_hi}] = [s_{\text{low},(31)}, s_{\text{high},(4968)}]$，在裁剪到参数域 `[-100.0, 100.0]` **之前**检查：
       1. **互异值不足**：`u_low < 20` 或 `u_high < 20`（当样本方差 $s_d = 0$ 时，无论 $\bar{d} = 0$ 还是 $\bar{d} > 0$，必有 `u_low = u_high = 1 < 20`）；
       2. **下界流或上界流自身分位跨度退化**：$|s_{\text{low},(4968)} - s_{\text{low},(31)}| \le 10^{-12}$ 或 $|s_{\text{high},(4968)} - s_{\text{high},(31)}| \le 10^{-12}$；
       3. **区间端点非有限或反序**：`not (isfinite(raw_ci_lo) and isfinite(raw_ci_hi))` 或 `raw_ci_lo > raw_ci_hi`；
       4. **（对 `hybrid_bessel_t_tango_e2`）外扩原始区间与参数域 `[-100.0, 100.0]` 交集为空**：`raw_ci_lo > 100.0` 或 `raw_ci_hi < -100.0`。
     - 满足以上任一条即判定该连续槽退化（`degenerate = True`），不作任何确认性拒绝声明，**单侧 p 值强制置为 `p = 1.0`**，其确认性置信区间**强制回退至完整参数域 `[-100.0, 100.0]`**；仅当 `degenerate == False` 时，对 `hybrid_bessel_t_tango_e2` 执行 `np.clip(raw_ci, -100.0, 100.0)`。上述规则将在 S2 单元测试中通过固定数组逐分支验证。

3. **离散配对比例差（`E2_H4`）的认证精确无条件 Tango (1998) 规范及模型假设边界（覆盖 $n \in \{8, 12, 16, 32, 48\}$，回应 `c` R2 疑问 1、R3 阻断 1、R3 建议 3）**：
   - 对非终结类簇 $i \in \{1, \dots, n_A\}$（正式集 $n_A = 32$，开发集 $n_{A,\text{dev}} = 8$，子类分解 $n = 16$），设 $I_{i,\text{BARE}} = \mathbb{I}(\text{label}_{i,\text{NI\_BARE}} = \text{True}) \in \{0, 1\}$，$I_{i,\text{COMP}} = \mathbb{I}(\text{label}_{i,\text{NI\_COMP}} = \text{True}) \in \{0, 1\}$，定义簇内配对三值差：
     $$d_i = I_{i,\text{BARE}} - I_{i,\text{COMP}} \in \{-1, 0, +1\}$$
     计 $x = \#\{i : d_i = +1\}$，$y = \#\{i : d_i = -1\}$。
   - **独立认证查表清单**：由本实验目录下的 `exp2-zh/exact_tango_e2.py` 预先构建并认证 `exp2-zh/manifests/exact-tango-tables-e2.npz`（`file_sha256 = 2eb9bfd0db577301c44e5a49ad5ed1d4296b33031db7b54c78710e11043115a6`，`payload_sha256 = 18946c579cf191188a7b2c3c9b9ac967a3823e32db4544879933f81741bc323b`）及 `exact-tango-tables-e2-meta.json`，完整覆盖 **`SUPPORTED_NS = (8, 12, 16, 32, 48)`** 五种样本量（15/15 项 `Fraction` 左截断证书通过，0 单调性违例）。
   - **单侧调用与缺失回退**：调用 `infer_exact_tango_slot(d_lower, d_upper, one_sided=True)`：
     - 单侧 p 值：当 $x_{\text{lower}} > y_{\text{lower}}$ 时取认证上尾界 $p_4 = F^+_{\text{cert}}(x_{\text{lower}}, y_{\text{lower}}; \theta_0 = 0)$，否则 $p_4 = 1.0$；
     - 单项双侧 98.75% Bonferroni 精确置信区间（单项水平 $\alpha_{\text{ind}} = 0.0125$）：取 $[\theta_{L,\text{cert}}(x_{\text{lower}}, y_{\text{lower}}; \alpha_{\text{ind}}=0.0125),\; -\theta_{L,\text{cert}}(y_{\text{upper}}, x_{\text{upper}}; \alpha_{\text{ind}}=0.0125)]$（在报告表格中同时给出比例尺度 `[-1, 1]` 与乘以 100 后的百分点尺度 `[-100, 100]`）；若区间退化或无效，回退至完整参数域 `[-1.0, 1.0]`（百分点尺度 `[-100.0, 100.0]`）且 $p_4 = 1.0$。
   - **关于 `E2_H4` 精确保证的模型假设条件与子类异质性边界说明（回应 `c` R2 疑问 1、R3 阻断 1、R3 建议 3）**：
     - `exact-tango-tables-e2.npz` 的**无条件解析精确（unconditional exact）上包络保证，仅在「被检验的 $n$ 个簇的配对三值差 $d_i \in \{-1, 0, +1\}$ 独立同分布于同一个共同三项分布 $(\pi_+, \pi_-, \pi_0) \in \Delta_3$」这一统计模型假设下成立**（适用于在单子类内部独立同分布模型假设下的 `A_plan` $n=16$ 与 `A_pure` $n=16$ 子类检验，以及两子类共享同一三项分布假设下的汇总 $n_A=32$ 检验；将多个事件簇划入同一词汇—材料子类本身并不证明独立同分布假设）。
     - 当 `A_plan`（16 簇）与 `A_pure`（16 簇）固定配额抽样且两子类三项分布不同（$\boldsymbol{\pi}_{\text{plan}} \ne \boldsymbol{\pi}_{\text{pure}}$）时，本计划**不对汇总 $n_A = 32$ 的 Tango 查表声称解析上的无条件精确保证或基于方差缩减的自动尾部保护**；汇总 $n_A = 32$ 检验在固定配额异质三项分布下的第一类错误率与 98.75% 置信区间覆盖率，统一作为待校准性质在 `calibrate_e2.py` 的 `DGP4_het` 中接受实证模拟核验，且结论措辞严格限定于模拟验证通过的范围。

4. **`L` 首字母标签分数 `q`、单元四终结状态 `status`、标签可用性及最不利缺失界限传播（完全对齐实验 1 `PLAN-E1.md` §3.2 第 287–292 行与 §4.2(4)，回应 `c` R2 阻断 3、R3 阻断 2、R4 建议 2）**：
   - **`L` 首字母 token 标签分数 `q`（`score.py`，`VERSION = 1`，`TOP_N = 100`，对齐 `PLAN-E1.md:287`）**：
     - 定位生成 token 序列中覆盖 `char_start`（已解析标签词 `"True" | "False" | "Unknown"` 首字母）的下标 `j`（`Z, DAP` 要求 `j` 之前不含任何字母字符；`CoT, CF` 条件于已生成推理，要求 `reasoning_ok`、`label_last` 且无转义），在原始前缀 `prompt_ids + generated_ids[:j]` 处读取 **`top-100`** 未采样对数概率（`j == 0` 直接复用首次生成 `first_topN`，`j > 0` 发一次 `n_predict=1, n_probs=100` 前缀计分请求）；
     - 按冻结的三标签候选集 `label_tokens_qwen3-8b.json`（涵盖 **`"True"`、`"False"`、`"Unknown"` 三个标签的全部 18 个候选 token**）在对数空间计算三标签归一化下的保守闭区间 `[q_L, q_U]`：
       - **全部 18 个候选 token 均出现在 `top-100` 内**：记 `q_status = "full"`；
       - **部分候选不在 `top-100` 内（但至少命中一个候选）**：已报告 `top-100` 列表的最低值 $p_{100}$ 为每个未命中候选 token 提供单 token 概率**上界**（即每个未命中候选的概率范围为 $[0, p_{100}]$），由此在对数空间构造严格闭区间 `[q_L, q_U]`，记 `q_status = "bounded"`（回应 `c` R4 建议 2）；
       - **未命中任何候选或未满足定位前置条件/发生异常**：记 `q_status = "missing:<reason>"`。
   - **单元四终结状态映射（`run.py:214-249`，4 个互斥取值，逐字对齐 `PLAN-E1.md:288-292`）**：
     1. `missing_transport`：生成阶段连续 3 次传输错误耗尽（`parsed = None, protocol = None`）；
     2. `missing_format`：**`truncated == True`（即生成达到 `MAX_TOKENS = 1024` 且 `stop_type != "eos"`）**，或语义读数（`label` / `value`）为 `None`；
     3. `missing_score`：仅 `L` 任务，语义 `label` 解析成功且未截断（`truncated == False`），但 `q_status not in ("full", "bounded")`；
     4. `ok`：其余全部可用单元（即 `truncated == False`、主语义读数解析成功，且对 `L` 任务 `q_status in ("full", "bounded")`）。
   - **`L` 任务离散标签可用性 `label_available`**：当且仅当 `status in ("ok", "missing_score")`（即未截断且 `label in ("True", "False", "Unknown")`）时 `label_available = True`。
   - **主确认分析与伴随敏感度分析的完整映射规则**：
     - **主确认分析统一规则（严格 `status == "ok"` 准则）**：在全部 4 项主确认检验（`E2_H1..E2_H4`）中，**仅当单元终结状态 `status == "ok"` 时**代入其观测点值（连续机率 `[X_i, X_i]`，或 `E2_H4` 中离散标签指示变量 `[I_i, I_i]`，其中 $I_i = \mathbb{I}(\text{label}_i = \text{True})$；`q_status == "bounded"` 的单元其 `status == "ok"` 故保留精确标签 `[I_i, I_i]`）；凡 **`status != "ok"`**（含 `missing_transport`、`missing_format`［含截断］及 `missing_score`）的单元，在主确认分析中一律代入最不利极值界（连续机率代入 **`[0.0, 100.0]`**，离散标签指示变量代入 **`[0, 1]`**）。
     - **`E2_H4` 的预设伴随诊断（`label_available` 准则，对齐 `PLAN-E1.md` §4.2.4 第 2 条）**：若非终结簇的 `L/CoT` 单元中出现 `status == "missing_score"`（生成未截断且语义 `label` 已成功解析，仅 `q` 计分缺失），报告中固定并列输出一行将 `status in ("ok", "missing_score")` 单元的已解析 `label` 纳入 `E2_H4` 计数的伴随精确 Tango 检验结果。
   - **簇内配对差界限传播**：对任意簇内配对差 $D_i = X_i - Y_i$，逐簇计算：
     $$D_{i,\text{lower}} = X_{i,\text{lower}} - Y_{i,\text{upper}}, \qquad D_{i,\text{upper}} = X_{i,\text{upper}} - Y_{i,\text{lower}}$$
     所有单侧 $H_1: \theta_j > 0$ 的确认性 p 值一律在最不利下界路径 $\{D_{i,\text{lower}}\}$ 上计算；所有确认性置信区间一律取下界路径的低端与上界路径的高端 $[\text{CI}_{\text{lo}}(D_{\text{lower}}),\; \text{CI}_{\text{hi}}(D_{\text{upper}})]$。

5. **Holm 逐步多重检验流程（`m = 4`，家族错误率 $\alpha_{\text{fam}} = 0.05$）**：
   - 将 4 项单侧原始 p 值 $(p_1, p_2, p_3, p_4)$ 从小到大稳定排序为 $p_{(1)} \le p_{(2)} \le p_{(3)} \le p_{(4)}$（并列时按固定编号顺序 `E2_H1, E2_H2, E2_H3, E2_H4` 破平）；
   - 逐步检验阈值依次为 $\alpha_{\text{fam}} / (4 - k + 1)$，即第 1 步 `0.0125`、第 2 步 `0.016667`、第 3 步 `0.025`、第 4 步 `0.05`；
   - 调整后 Holm p 值为 $p_{\text{Holm},(k)} = \min\bigl(1.0,\; \max_{1 \le j \le k} (4 - j + 1) p_{(j)}\bigr)$；自第一个满足 $p_{(k)} > \alpha_{\text{fam}} / (4 - k + 1)$ 的位置 $k$ 起，该项及后续所有项均不拒绝零假设。

6. **S4 统计校准核验的联合单元生成 16 格矩阵、共享缺失传播与明确退出条件（回应 `c` R2 阻断 4、R3 阻断 3–4、R4 阻断 1 与建议 1）**：
   - **模拟参数与正式推断严格同构（回应 `c` R3 阻断 4）**：在 S4 开发集跑完后、S5 冻结前，运行独立校准脚本 `exp2-zh/calibrate_e2.py`，使用固定模拟种子 **`CALIB_SEED_E2 = 2026110311`**，针对正式集精确簇数（终结类 $n_T = 48$［子类配额 $21, 14, 8, 5$］，非终结类 $n_A = 32$［子类配额 `A_plan` $16$, `A_pure` $16$］）及 4 项家族（`E2_H1..E2_H4`），在 **4 类数据生成分布家族（DGP 1–4）$\times$ 4 类真值/缺失配置（Cfg A–D）= 16 个校准格**上，每格运行 **`R = 2000`** 次蒙特卡洛模拟，且**每次模拟内部调用与正式集完全相同的重抽次数 `B = 5000` 及完全相同的 0-based 次序统计量下标 `idx_lo = 31, idx_hi = 4968`**（$\text{SE}_{\text{sim}} = \sqrt{0.05 \times 0.95 / 2000} \approx 0.0048734$）。
   - **保留共享实验单元 `NI_COMP(P/Z)` 的簇内联合生成机制（回应 `c` R4 阻断 1 与建议 1）**：
     - 在正式实验中，终结类（`T`，$n_T = 48$）上的 `E2_H1`（$d_{1,i} = P_{\text{bare},i} - P_{\text{comp},i}$）与 `E2_H2`（$d_{2,i} = P_{\text{comp},i} - M_{\text{comp},i}$）**共享同一个实验单元 $P_{\text{comp},i} = \text{NI\_COMP}(P/\text{Z})$**。为严格保持这一联合结构，校准矩阵在每个终结簇 $i \in \{1, \dots, 48\}$ 上**先联合生成唯一的三个单元读数 $(P_{\text{bare},i}, P_{\text{comp},i}, M_{\text{comp},i}) \in [0, 100]^3$**，再由同一 $P_{\text{comp},i}$ 计算 $d_{1,i}$ 与 $d_{2,i}$：
       - 对任意目标真值 $(\theta_1, \theta_2) \in \{(0.0, 0.0), (20.0, 0.0), (0.0, 15.0)\}$ 与有界扰动对 $(\varepsilon_{1,i}, \varepsilon_{2,i}) \in [-35.0, +35.0]^2$（在 `DGP1_emp..DGP3_ties` 中每簇 $\mathbb{E}[\varepsilon_{j,i}] = 0$；在 `DGP4_het` 中每簇期望为子类偏移 $\mathbb{E}[\varepsilon_{j,i}] = \delta_{h(i)}$，而**大类配额加权平均期望 $\frac{1}{n}\sum_{i=1}^n \mathbb{E}[\varepsilon_{j,i}] = \sum_h w_h \delta_h = 0$**；回应 `c` R4 建议 1），定义该终结簇的三个唯一单元读数为：
         $$P_{\text{comp},i} = 50.0 + \frac{\theta_2 - \theta_1}{2} + \frac{\varepsilon_{2,i} - \varepsilon_{1,i}}{2} \in [5.0, 95.0] \subset [0, 100]$$
         $$P_{\text{bare},i} = P_{\text{comp},i} + \theta_1 + \varepsilon_{1,i} = 50.0 + \frac{\theta_1 + \theta_2}{2} + \frac{\varepsilon_{1,i} + \varepsilon_{2,i}}{2} \in [5.0, 95.0] \subset [0, 100]$$
         $$M_{\text{comp},i} = P_{\text{comp},i} - \theta_2 - \varepsilon_{2,i} = 50.0 - \frac{\theta_1 + \theta_2}{2} - \frac{\varepsilon_{1,i} + \varepsilon_{2,i}}{2} \in [5.0, 95.0] \subset [0, 100]$$
       - **精确恒等式与边界保证**：由唯一共享的 $P_{\text{comp},i}$ 直接相减，恒有：
         $$d_{1,i} = P_{\text{bare},i} - P_{\text{comp},i} = \theta_1 + \varepsilon_{1,i} \in [-35.0, +55.0], \qquad d_{2,i} = P_{\text{comp},i} - M_{\text{comp},i} = \theta_2 + \varepsilon_{2,i} \in [-35.0, +50.0]$$
         且两差之和恒满足 $|d_{1,i} + d_{2,i}| = |P_{\text{bare},i} - M_{\text{comp},i}| = |\theta_1 + \theta_2 + \varepsilon_{1,i} + \varepsilon_{2,i}| \le 20.0 + 70.0 = 90.0 \le 100.0$，三个底层单元读数全部严格落在 $[5.0, 95.0] \subset [0, 100]$ 内，无需任何事后裁剪且大类均值期望恒等于 $(\theta_1, \theta_2)$。
     - 在非终结类（`A`，$n_A = 32$）上，`E2_H3` 使用中断前提下的两个独立 `P/Z` 单元 $X_{3,i} = \text{INT\_BARE}(P/\text{Z})$ 与 $Y_{3,i} = \text{INT\_COMP}(P/\text{Z})$（与 `E2_H4` 使用的无中断 `L/CoT` 单元完全不相交）：对 $\theta_3 \in \{0.0, 25.0\}$ 与 $\varepsilon_{3,i} \in [-35.0, +35.0]$，令：
       $$X_{3,i} = 50.0 + \frac{\theta_3 + \varepsilon_{3,i}}{2} \in [20.0, 80.0] \subset [0, 100], \qquad Y_{3,i} = 50.0 - \frac{\theta_3 + \varepsilon_{3,i}}{2} \in [20.0, 80.0] \subset [0, 100]$$
       则 $d_{3,i} = X_{3,i} - Y_{3,i} = \theta_3 + \varepsilon_{3,i} \in [-35.0, +60.0] \subset [-100, 100]$，大类均值期望恒等于 $\theta_3$。
     - **离散槽（`E2_H4`，目标真值 $\theta_4 \in \{0.0, 0.35\}$）**：对任意给定基准不一致率 $\tau_0 \in [0.15, 0.80]$ 与目标均值 $\theta_4 \in [-0.60, +0.60]$，采用合法单纯形参数化：
       $$\tau(\theta_4) = \max\bigl(\tau_0,\; |\theta_4| + 0.10\bigr) \in [0.15, 0.80], \qquad \pi_+ = \frac{\tau(\theta_4) + \theta_4}{2} \ge 0.05, \qquad \pi_- = \frac{\tau(\theta_4) - \theta_4}{2} \ge 0.05, \qquad \pi_0 = 1 - \tau(\theta_4) \ge 0.20$$
       再由三项分布 $(\pi_+, \pi_-, \pi_0)$ 生成单元对 $(I_{i,\text{BARE}}, I_{i,\text{COMP}}) \in \{(1,0), (0,1), (0,0)\}$。
   - **4 类数据生成分布家族（DGP 1–4）的精确数学定义（回应 `c` R3 阻断 3、R4 阻断 1 与建议 1）**：
     1. **`DGP1_emp`（开发集中心化有界经验残差）**：取 S4 开发集在对应槽位 $j \in \{1, 2, 3\}$ 上的观测簇差 $e_{j,1}, \dots, e_{j,n_{\text{dev}}}$，减去其样本均值 $\bar{e}_j$ 得中心化残差 $r_{j,k} = e_{j,k} - \bar{e}_j$（满足 $\sum_k r_{j,k} = 0$），再乘以有界缩放系数 $\kappa_j = \min\bigl(1.0,\; 35.0 / \max(10^{-12}, \max_k |r_{j,k}|)\bigr)$；在终结簇上按同一开发集终结簇下标 $k \in \{1, \dots, 12\}$ 成对抽取 $(\varepsilon_{1,i}, \varepsilon_{2,i}) = (\kappa_1 r_{1,k}, \kappa_2 r_{2,k}) \in [-35.0, +35.0]^2$（保留开发集 `E2_H1` 与 `E2_H2` 簇内经验相关性，且每簇 $\mathbb{E}[\varepsilon_{j,i}] = 0$），在非终结簇上从 $\{\kappa_3 r_{3,1}, \dots, \kappa_3 r_{3,8}\}$ 中等概有放回抽取 $\varepsilon_{3,i} \in [-35.0, +35.0]$；`E2_H4` 的基准不一致率取开发集观测不一致率裁剪至 $\tau_0 = \text{clip}(\hat{\tau}_{\text{dev}}, 0.15, 0.80)$，代入 $\tau(\theta_4) = \max(\tau_0, |\theta_4| + 0.10)$。
     2. **`DGP2_skew`（有界强偏斜且簇内相关分布）**：在每个终结簇上由二元标准正态 $(Z_1, Z_2)$（相关系数 $\rho = 0.5$）经标准正态分布函数 $\Phi$ 与 $\text{Beta}(2, 8)$ 逆分布函数变换得边际严格服从 $\text{Beta}(2, 8)$（精确均值 $0.2$）的 $(U_1, U_2) \in [0, 1]^2$，令 $\varepsilon_{m,i} = 40.0 \times (U_{m,i} - 0.2) \in [-8.0, +32.0] \subset [-35.0, +35.0]$（$m \in \{1, 2\}$，**每簇精确均值 $0$，无需任何裁剪**）；在非终结簇上独立抽取 $U_3 \sim \text{Beta}(2, 8)$ 并令 $\varepsilon_{3,i} = 40.0 \times (U_{3,i} - 0.2) \in [-8.0, +32.0]$；`E2_H4` 取基准不一致率 $\tau_0 = 0.50$（当 $\theta_4 = 0$ 时 $(\pi_+, \pi_-, \pi_0) = (0.25, 0.25, 0.50)$；当 $\theta_4 = 0.35$ 时 $(\pi_+, \pi_-, \pi_0) = (0.425, 0.075, 0.50)$）。
     3. **`DGP3_ties`（高并列离散三点分布与低不一致率）**：连续扰动 $\varepsilon_{j,i}$ 在 $\{-30.0, 0.0, +30.0\} \subset [-35.0, +35.0]$ 上按概率 $(0.30, 0.40, 0.30)$ 独立抽取（**每簇精确均值 $0$，且即便 $\varepsilon_{1,i} = \varepsilon_{2,i} = +30.0$、$\theta_1 = 20, \theta_2 = 0$，仍有 $P_{\text{comp},i} = 40.0, P_{\text{bare},i} = 90.0, M_{\text{comp},i} = 10.0 \in [0, 100]$ 且 $d_{1,i} + d_{2,i} = 80.0 \le 100.0$**）；`E2_H4` 取基准不一致率 $\tau_0 = 0.15$，按 $\tau(\theta_4) = \max(0.15, |\theta_4| + 0.10)$ 计算合法三项概率（当 $\theta_4 = 0$ 时为 $(0.075, 0.075, 0.850)$；当 $\theta_4 = 0.35$ 时为 $(0.400, 0.050, 0.550)$）。
     4. **`DGP4_het`（6 子类固定配额强异质性分布，各子类内期望为 $\delta_h$、大类配额加权平均期望精确为 $0$）**：
        - **终结类（$n_T = 48$，4 子类固定配额 $21, 14, 8, 5$）**：令 4 个子类的层间基线偏移分别为 `Creation`（$21$ 簇）$\delta_1 = +8.0$、`Change of State`（$14$ 簇）$\delta_2 = -12.0$、`Consumption`（$8$ 簇）$\delta_3 = +7.5$、`Motion to Goal`（$5$ 簇）$\delta_4 = -12.0$——**其大类配额加权平均期望恒等于 $\frac{21(8.0) + 14(-12.0) + 8(7.5) + 5(-12.0)}{48} = \frac{168 - 168 + 60 - 60}{48} = 0.0$**；每簇扰动为 $\varepsilon_{j,i} = \delta_{h(i)} + \eta_{j,i}$，其中 $\eta_{j,i} \sim \text{Uniform}(-20.0, +20.0)$（子类内期望 $\mathbb{E}[\varepsilon_{j,i}] = \delta_{h(i)}$，支持 $\varepsilon_{j,i} \in [-32.0, +28.0] \subset [-35.0, +35.0]$，大类真实配额均值恒为 $\theta_j$）。
        - **非终结类连续槽（`E2_H3`，$n_A = 32$，`A_plan` $16$ 簇、`A_pure` $16$ 簇）**：令 $\delta_{\text{plan}} = +12.0, \delta_{\text{pure}} = -12.0$（大类配额加权平均期望 $\frac{16(12.0) + 16(-12.0)}{32} = 0.0$），$\varepsilon_{3,i} = \delta_{h(i)} + \eta_{3,i} \in [-32.0, +32.0] \subset [-35.0, +35.0]$（$\eta_{3,i} \sim \text{Uniform}(-20.0, +20.0)$）。
        - **非终结类离散槽（`E2_H4`，$n_A = 32 = 16_{\text{plan}} + 16_{\text{pure}}$，覆盖 $\bar{\theta}_4 = 0.0$ 与 $\bar{\theta}_4 = 0.35$ 全部配置）**：固定两子类不一致率均为 $\tau_{\text{sub}} = 0.70$，令两子类真实均值分别为 $\theta_{4,\text{plan}} = \bar{\theta}_4 + 0.25$ 与 $\theta_{4,\text{pure}} = \bar{\theta}_4 - 0.25$（等权均值恒为 $\bar{\theta}_4$）：
          - 当 $\bar{\theta}_4 = 0.0$（`CfgA, CfgB, CfgD`）时：`A_plan` 为 $(0.475, 0.225, 0.300)$，`A_pure` 为 $(0.225, 0.475, 0.300)$；
          - 当 $\bar{\theta}_4 = 0.35$（`CfgC`）时：`A_plan` 为 $(0.650, 0.050, 0.300)$，`A_pure` 为 $(0.400, 0.300, 0.300)$。
   - **4 类真值与底层共享单元缺失配置（Cfg A–D，回应 `c` R4 阻断 1）**：
     1. `CfgA_all_null_comp`：全零假设 $\boldsymbol{\theta} = (0.0, 0.0, 0.0, 0.0)$（真零假设下标集 $I_0 = \{1,2,3,4\}$），0% 缺失；
     2. `CfgB_half_null_comp`：部分零假设 $\boldsymbol{\theta} = (20.0, 0.0, 25.0, 0.0)$（$I_0 = \{2, 4\}$），0% 缺失；
     3. `CfgC_alt_null_comp`：互补部分零假设 $\boldsymbol{\theta} = (0.0, 15.0, 0.0, 0.35)$（$I_0 = \{1, 3\}$），0% 缺失；
     4. `CfgD_all_null_miss2`：全零假设 $\boldsymbol{\theta} = (0.0, 0.0, 0.0, 0.0)$（$I_0 = \{1,2,3,4\}$），**在底层实验单元层面上独立以概率 $0.01$ 注入缺失并复用共享单元缺失掩码**：
        - 在每个终结簇 $i \in \{1, \dots, 48\}$ 上，对三个底层单元 $(P_{\text{bare},i}, P_{\text{comp},i}, M_{\text{comp},i})$ 各自独立抽取 1 个 $\text{Bernoulli}(0.01)$ 缺失指示变量；被标为缺失的单元代入 `[0.0, 100.0]`。**特别是当共享单元 $P_{\text{comp},i}$ 被标为缺失时，`E2_H1`（$d^L_{1,i} = P_{\text{bare},i,\text{lower}} - P_{\text{comp},i,\text{upper}}$）与 `E2_H2`（$d^L_{2,i} = P_{\text{comp},i,\text{lower}} - M_{\text{comp},i,\text{upper}}$）同时复用该同一个缺失的 $P_{\text{comp},i} = [0.0, 100.0]$**；
        - 在每个非终结簇 $i \in \{1, \dots, 32\}$ 上，对 `E2_H3` 的两个底层单元 $(X_{3,i}, Y_{3,i})$ 各自独立抽取 $\text{Bernoulli}(0.01)$ 缺失指示变量（缺失代入 `[0.0, 100.0]`），对 `E2_H4` 的两个底层单元 $(I_{i,\text{BARE}}, I_{i,\text{COMP}})$ 各自独立抽取 $\text{Bernoulli}(0.01)$ 缺失指示变量（缺失代入 `[0, 1]`）。由此每个配对差槽位均有 $1 - 0.99^2 = 1.99\% \approx 2\%$ 的簇承受最不利缺失界限拓宽，且完全保留 `E2_H1` 与 `E2_H2` 在共享单元 $P_{\text{comp},i}$ 上的联合缺失耦合。
   - **四项准入硬闸门（必须在全部 16 格——含 2% 缺失格 `CfgD_all_null_miss2`——上以逻辑与 AND 同时通过）**：
     1. `fwer_passed`（家族错误率硬闸门）：在每一格上，Holm 流程拒绝至少一个真零假设（$\exists j \in I_0 : \text{rejected}_j$）的经验比例满足 **$\text{FWER} \le 0.05 + 2\text{SE}_{\text{sim}} = 0.059747$**；
     2. `simultaneous_coverage_9875_passed`（家族同时覆盖率硬闸门，**涵盖全部 16 格，含 2% 缺失格 `CfgD_all_null_miss2`**）：在每一格上，全部 4 项双侧 98.75% 置信区间同时覆盖各自真实参数 $\theta_j$ 的经验比例满足 **$\text{Simultaneous Coverage} \ge 0.95 - 2\text{SE}_{\text{sim}} = 0.940253$**；
     3. `individual_coverage_9875_passed`（单项覆盖率硬闸门）：在每一格上，每一项 $j \in \{1,2,3,4\}$ 的双侧 98.75% 置信区间覆盖率均满足 **$\ge 0.975$**（退化实验按回退区间 `[-100, 100]` / `[-1, 1]` 计入全分母 $R=2000$，并单独报告 `degeneracy_rate`）；
     4. `screen05_passed`（单项名义 0.05 筛查硬闸门）：在每一格上，对每个真零假设 $j \in I_0$，未调整单侧 $p_j \le 0.05$ 的经验误拒率均满足 **$\le 0.075$**。（未调整单侧 $p_j \le 0.0125$ 的经验误拒率作为非阻断诊断指标报告。）
   - **候选家族的确定性选择顺序、槽位降级上限与失败停止（Stop S5）规则（回应 `c` R2 阻断 4、R3 阻断 4）**：
     - **判定准则**：一个候选家族通过 S4 校准，**当且仅当上述第 1–4 项硬闸门在全部 16 格中 100% 通过**。
     - **第 1 步（评估 `Candidate 1 = hybrid_pct_tango_e2`）**：若 `Candidate 1` 在 16 格全部通过四项硬闸门，则锁定 `hybrid_pct_tango_e2` 为正式集主推断方法，`hybrid_bessel_t_tango_e2` 作为伴随敏感度方法。
     - **第 2 步（若 `Candidate 1` 未通过，整体切换并重验 `Candidate 2 = hybrid_bessel_t_tango_e2`）**：将全部 3 项连续假设 `E2_H1..E2_H3` 统一切换为保序 Bessel-$t$ 扩展 Bootstrap（`E2_H4` 仍为认证精确 Tango），在同一 16 格模拟流上重验完整四项家族。若 `Candidate 2` 在 16 格全部通过四项硬闸门，则锁定 `hybrid_bessel_t_tango_e2` 为正式集主推断方法。
     - **第 3 步（若 `Candidate 2` 未通过且离散槽 `E2_H4` 单项全部通过，执行一次性的未过关连续槽降级重验，固定保留 `m = 4` 分母）**：
       - 若在 `Candidate 2` 下，**离散槽 `E2_H4` 在任一格违反了单项硬闸门**（`individual_coverage_9875 < 0.975` 或 `screen05 > 0.075`），**不得降级 `E2_H4`，直接进入第 4 步终止条件（停止 S5）**；
       - 若 `E2_H4` 的单项硬闸门在 16 格全部通过，则在连续槽 $\{\text{E2\_H1}, \text{E2\_H2}, \text{E2\_H3}\}$ 中找出所有违反单项硬闸门（`individual_coverage_9875 < 0.975` 或 `screen05 > 0.075`）的槽位集合 $D$（若三个连续槽的单项硬闸门均通过而仅家族硬闸门 `1` 或 `2` 未通过，则取 16 格上最低单项 98.75% 覆盖率最小的那 1 个连续槽——并列按 `E2_H3 -> E2_H2 -> E2_H1` 破平——作为 $D$）；
       - 若 $|D| == 3$（即三个连续槽全部违反单项闸门），**不得将三个连续槽全部降级，直接进入第 4 步终止条件（停止 S5）**；
       - 若 $1 \le |D| \le 2$，将 $j \in D$ 降级为第三层探索性描述指标，同时**确认性家族规模固定维持 `m = 4` 与 Bonferroni/Holm 分母不变**（被降级槽在确认性家族中恒定设为 `p_raw = 1.0`、`ci_9875 = [-100.0, 100.0]`），在同一 16 格上对降级后的家族执行唯一一次重验：若 16 格全部通过四项硬闸门，则锁定该配置进入 S5；**若该次重验仍未通过，不再继续循环降级，直接进入第 4 步终止条件（停止 S5）**。
     - **第 4 步（明确终止分支 `CALIBRATION_FAILED_STOP_S5`，回应 `c` R3 阻断 4）**：一旦触发上述任一未通过情形，校准脚本立即返回非零退出码并标记 **`status = "calibration_failed_stop_s5"`**，**严禁进入 S5 冻结或启动 S6 正式集运行**，必须停下返回 `a -> c` 与用户重新修订统计推断方案。

### 4.3 第三层描述性与探索性分析（预先锁定，不占确认性 $\alpha$）
1. **非终结活动内部子类分解（`A_plan` 带常见计划活动 16 簇［`完`］ vs `A_pure` 纯无界活动 16 簇［`够/足`］）**：在全部 13 个 `(task, prompt)` 条件下，分别报告两个子类的四槽轨迹、`INT_BARE - INT_COMP` 配对差及 `L/CoT` 下 `NI_BARE - NI_COMP` 的单子类精确 Tango（$n = 16$，在单子类内部独立同分布三项模型的假设下成立）估计与置信区间。
2. **跨动词大类同构对比（`T` vs `A`，回应 `c` R3 建议 1）**：严格按 `PLAN.md` 第 6 节规定，仅在相同假设形式（同为 `h_bare` 光杆 `V了`［正式集 `T` 48 簇 vs `A` 32 簇］，或**正式集 `T` 中 `完` 补语 12 簇子集［全集 16 簇，其中开发集 4 簇、正式集 12 簇］ vs 正式集 `A_plan` 的 `完` 补语 16 簇**）下报告组间 `AUC` 与中断降幅 `NI - INT`。
3. **13 条件全矩阵与三标签完整分布表**：报告 `L`（`{True, False, Unknown}` 各自比例及首字母 token 分数区间 `[q_L, q_U]`）、`Ps/Z`、`P`、`M_U`、`M_W` 及自报权重偏差 $\Delta = M_W - M_U$ 在 `Z / DAP / CoT / CF` 下的完整点估计与 95% CI。

---

## 5. 阶段、闸门与停止规则（S0–S7）

| 阶段 | 内容 | 闸门与停止规则 |
| :--- | :--- | :--- |
| **S0** | 锁定 100 簇材料 `clusters_100_curated.json`、分层分割 `split.json` 及精确 Tango 表 `exact-tango-tables-e2.npz` 的 SHA-256 | `validate_materials.py` 100/100 零错误且 9/9 负向自检通过；开发集 20 簇与正式集 80 簇互斥；`exact-tango-tables-e2.npz` 覆盖 `n in (8, 12, 16, 32, 48)` 且 0 单调性违例 |
| **S1** | 只用开发集生成各任务 × 提示 × 槽位的中文提示全文预览 `s1_preview_zh.md` | `prompts_zh.py` 通过 `PARSE_VERSION = 2` 全 13 格兼容自检；`a` 与用户核对语感无误 |
| **S2** | 构建 `exp2-zh/` 独立运行器、解析器、统计核心 `core_e2.py` 与单测；用假模型跑通全开关 | 单元测试全过（含贪心锚点唯一值计数与四项退化判据的固定数组测试）；首 token 互斥核验通过 |
| **S3** | Mac mini 真实冒烟（开发集代表簇 × 13 条件 + 诊断语境 Pos/Neg 核验） | 任一单元不可用则停下诊断；诊断语境 `Pos > Neg` 方向正确 |
| **S4** | 开发集完整运行（`1,040` 主单元 + `120` 诊断单元）+ 20 单元确定性重跑 + `calibrate_e2.py`（`R=2000, B=5000`）统计校准核验 | 任一格首次可用率 $< 90\%$ 或整体缺失率 $> 2\%$ 则停下修解析；诊断语境 `P/Z` 下 `mean(Pos) >= 80` 且 `mean(Neg) <= 20`；`calibrate_e2.py` 按 §4.2 第 6 条通过全部 16 格四项硬闸门，否则触发 `calibration_failed_stop_s5` 停止进入 S5 |
| **S5** | 冻结 `exp2-zh/PLAN-E2.md`（生成 `freeze.json`），先推公开预注册补充/记录，再开跑 S6 | `c` 审查无阻断 + 用户确认冻结 |
| **S6** | Mac mini 正式集 80 簇（`320 题 × 13 = 4,160` 单元）执行 | `statistics.json` 闸门 `pass` |
| **S7** | 正式集统计分析、独立复现核账与报告生成 | 双端逐位一致 |

---

## 6. 对 `c` 历轮审查意见的逐项回应表

### 6.1 第一至第三轮已闭合项目汇总
- 第一轮全部 5 项阻断、5 项建议、3 项疑问，第二轮阻断 1、2、3、5 与建议 1–3，以及第三轮阻断 1、2、4 与建议 1–4 均已在第四轮复核（`review-plan-e2-r4-codex.md`）中确认为**闭合**。

### 6.2 第四轮意见闭合表（`review-plan-e2-r4-codex.md`）

| `c` R4 编号 | 类别 | 处理结论与落位 |
| :--- | :--- | :--- |
| **R4 阻断 1** | 校准矩阵尚未保留 `E2_H1` 与 `E2_H2` 共用的同一个实验单元 `P_comp = NI_COMP(P/Z)` 及共享缺失掩码 | **已完全修复**（§4.2 第 6 条）：① 在每个终结簇 $i \in \{1,\dots,48\}$ 上先联合生成唯一的三个单元读数 $P_{\text{comp},i} = 50 + \frac{\theta_2 - \theta_1}{2} + \frac{\varepsilon_{2,i} - \varepsilon_{1,i}}{2}$、$P_{\text{bare},i} = P_{\text{comp},i} + \theta_1 + \varepsilon_{1,i}$、$M_{\text{comp},i} = P_{\text{comp},i} - \theta_2 - \varepsilon_{2,i}$，并将扰动支持统一收紧至 $\varepsilon_{j,i} \in [-35.0, +35.0]$（`DGP1` 缩放上限 $35.0$ 并按同一开发簇成对抽样；`DGP2` 为 $40(U-0.2) \in [-8, +32]$；`DGP3` 为 $\{-30, 0, +30\}$；`DGP4` 为层间偏移 $(+8, -12, +7.5, -12)$ 加 $\text{Uniform}(-20, +20)$，支持 $[-32, +28]$），使三个单元读数恒落在 $[5.0, 95.0] \subset [0, 100]$，且由同一个 $P_{\text{comp},i}$ 导出的 $d_{1,i} = P_{\text{bare},i} - P_{\text{comp},i} = \theta_1 + \varepsilon_{1,i}$、$d_{2,i} = P_{\text{comp},i} - M_{\text{comp},i} = \theta_2 + \varepsilon_{2,i}$ 恒满足 $|d_{1,i} + d_{2,i}| = |P_{\text{bare},i} - M_{\text{comp},i}| \le 90.0 \le 100.0$；② 在 `CfgD_all_null_miss2` 中，改为对底层实验单元 $(P_{\text{bare},i}, P_{\text{comp},i}, M_{\text{comp},i})$ 各自独立以 $0.01$ 概率注入缺失，**当共享单元 $P_{\text{comp},i}$ 缺失时，`E2_H1` 与 `E2_H2` 同时复用该同一个缺失单元 `[0.0, 100.0]`**。 |
| **R4 建议 1** | 区分 `DGP1..DGP3` 的每簇零均值与 `DGP4_het` 的大类配额加权零均值 | **已采纳**（§4.2 第 6 条）：明确写出 `DGP1_emp..DGP3_ties` 满足每簇 $\mathbb{E}[\varepsilon_{j,i}] = 0$，而 `DGP4_het` 满足各子类内期望为 $\mathbb{E}[\varepsilon_{j,i}] = \delta_{h(i)}$、大类配额加权平均期望为 $\frac{1}{n}\sum_{i=1}^n \mathbb{E}[\varepsilon_{j,i}] = \sum_h w_h \delta_h = 0$。 |
| **R4 建议 2** | 澄清 `top-100` 第 100 名概率 $p_{100}$ 对未命中候选的作用 | **已采纳**（§4.2 第 4 条）：明确写为「已报告 `top-100` 列表的最低值 $p_{100}$ 为每个未命中候选 token 提供单 token 概率**上界**（即每个未命中候选的概率范围为 $[0, p_{100}]$）」。 |
