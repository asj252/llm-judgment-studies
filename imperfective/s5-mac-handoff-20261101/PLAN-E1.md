# 实验 1（英文 ImperfectiveNLI）S5 正式运行与统计分析冻结规范（`PLAN-E1.md`）

- **项目与计划节点**：`#imperfective` / `P16.4.7`（实验 1：英文 `ImperfectiveNLI`，单受测配置 `qwen3-8b@macmini-m6`）
- **起草日期**：`2026-11-01`（`Asia/Shanghai`）
- **当前治理状态**：S5 候选冻结规范。本文件存放于 `connecting-dots/imperfective/s5-mac-handoff-20261101/PLAN-E1.md` 期间，`S5_frozen = False`。前置双通道独立冻结前审查记录分别为同目录下的 `review-plan-e1-freeze-codex.md`（Codex 独立批判者 `c` 终审）与 `review-plan-e1-freeze-crossfamily.md`（依 `PLAN.md` §10.4 跨家族独立子 agent 终审），两份记录均须达到 `总体判定：无阻断`（`c_blockers = 0`）并随本目录归档入库。仅当用户在 Mac 工作区 `~/ClaudeProjects/research-imperfective` 审阅确认后，将 `PLAN-E1.md` 与 `review-plan-e1-freeze-codex.md` 复制到 `exp1-en/` 并执行完整命令 `exp1-en/run.py freeze qwen3-8b@macmini-m6 --status pass --plan exp1-en/PLAN-E1.md --review exp1-en/review-plan-e1-freeze-codex.md --confirmed-at <YYYY-MM-DDTHH:MM:SS+08:00> --c-blockers 0 --user-confirmed`，生成不可变快照 `exp1-en/freeze/qwen3-8b@macmini-m6/895f4e6f/PLAN-E1.frozen.md`、`c-review.md`（`review-plan-e1-freeze-codex.md` 的冻结副本）与 `freeze.json` 时，本规范才正式生效并解锁 `formal` 阶段。
- **实验隔离原则（对照总计划 `connecting-dots/imperfective/PLAN.md` §7）**：本文件独立包含实验 1 配置 `qwen3-8b@macmini-m6` 的全部材料哈希、13 条件逐字提示规范、解析／协议／计分规则、运行器与 S6/S7 入口脚本哈希、模型与服务参数、随机种子、重抽次数 `B`、计划 `unit` 清单、主验证假设族及判读边界。运行与统计分析只读取实验 1 自身目录、本交接包与封存统计引擎，不读取 `exp2-zh/`、`dnli/` 或 `psych3/`。

---

## 0. 研究问题、前置演进链路与用户特批选项 III 冻结前例外声明

### 0.1 实验 1 测量问题定位
在 Ma & Miyao (2026, arXiv `2601.09373` v3, ACL 2026 Best Paper) 的英文 `ImperfectiveNLI` 材料上，原研究仅观测三分类离散标签（`True` / `False` / `Unknown`），发现指令模型在零样本（`Z`）下对无中断终结事件（C 组，金标准 `Unknown`）高频误判 `True`（目的论偏见），而加入思维链（`CoT`）或反事实（`CF`）提示后，虽然压低了 C 组的 `True` 比例，却同时把无中断非终结活动（D 组，金标准 `True`）大量改判为 `Unknown`（原文所称“校准危机”）。

实验 1 在保持贪婪解码确定性的前提下，并列采集离散标签任务（`L`，含首字母 token 对数空间概率分数区间 `[q_L, q_U]`）、严格逻辑框架口述概率（`Ps/Z`）、常识框架单一口述概率（`P`）与常识框架五候选多估计口述概率（`M`），并在**方案 A（2×2 多维权衡框架）**下通过四项簇级配对主指标检验多估计等权候选均值（`M_U`）与思维链提示（`CoT`）在终结事件与非终结活动上的多维权衡：（1）`SA1`：零样本 `M_U/Z` 能否比单点思维链 `P/CoT` 更强地压低无中断终结事件（C 组）的高置信端点率（$\ge 95\%$）；（2）`SA2`：单点 `P/CoT` 与零样本 `M_U/Z` 在终结事件配对中断敏感度差 `(C - A)` 上的差异方向与幅度（定义为 `(C - A)_{P/CoT} - (C - A)_{M_U/Z}`）；（3）`SA3`：在相同 `CoT` 提示下，`M_U/CoT` 相对 `P/CoT` 在非终结活动配对中断差 `(D - B)` 上的保持度差异（定义为 `(D - B)_{M_U/CoT} - (D - B)_{P/CoT}`）；（4）`SA4`：离散标签 `L/CoT` 相对 `L/Z` 在无中断非终结活动（D 组）上的有效蕴涵（`"True"`）坍塌幅度。所有对比均严格界定为**特定任务与提示框架下的可观测读数差异**，不解释为模型内部潜在信念或因果心理机制。

### 0.2 开发集（`dev`）探索演进链路与正式集（`formal`）严格隔离记录
1. **S0–S4 数据与开发集采集（已完成，零接触 `formal`）**：在配置 `qwen3-8b@macmini-m6`（完整运行指纹 `895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2`）上，`smoke`（52 单元）与 `dev`（40 簇 = 80 题 × 13 条件 = 1,040 单元）全部 `status = "ok"`（`missing = 0`，`truncated = 0`），固定种子 `20261092` 抽取的 20 个开发集单元重跑 `generated_ids_raw` `20 / 20` 逐 token 一致（`exp1-en/report-s4-autonomous.md`）。
2. **原 V4 `m = 10`（`AUC` 主导）方案的冻结前校准淘汰（依 `PLAN.md` §4.2 规则）**：在冻结前统计模拟（`exp1-en/report-prefreeze-statistics.md`、`resolution-sample-size-20261031/`）中，原 `PLAN.md` §4.1 的 10 项 `AUC` 主导家族在正式集样本量 `n = 80` 下未能通过 88 格综合校准与功效核验（`percentile` 综合仅过 `25 / 88` 格、`studentized` 综合仅过 `21 / 88` 格，且提示／接口对比 `ΔAUC` 在经验分布下的 Holm 检出功效仅 `1.9% ~ 16.0%`）。依 `PLAN.md` §4.2“不通过就换方法或降为描述，在冻结前写明，不靠加大 `B` 过关”的规则，原 V4 `m = 10` 全部退居 S7 描述性历史归档。
3. **开发集机制拆解与方案 A（`m = 4`）重构**：基于 `dev` 数据的冻结前机制诊断（`candidate-decomposition-20261031/`、`m-vs-cot-20261031/`、`revision-scheme-20261031/`）发现，`M` 相对 `P` 的读数差异主要由**五候选池展开（等权均值 `M_U`）**承载，模型自报权重（`M_W - M_U`）仅起次要收缩作用；同时单点 `P/CoT` 与多估计 `M_U/Z` 呈现多维权衡（`dev` 上 `M_U/Z` 更强压低 C 组高置信端点率，`P/CoT` 则具有更大的 `C - A` 幅度，叠加 `M/CoT` 并未全面优于零样本 `M_U/Z`）。据此在零接触 `formal` 的前提下，将主确认族重构为聚焦 `M_U` 的 4 项簇级配对指标 `SA1..SA4`（总水平 Holm `alpha = 0.05`，单槽名义 `98.75%` 置信区间）。**由于 `M_U` 标量与 `SA1..SA4` 假设族均在审阅 `dev` 后提出，`dev`（40 簇）在论文与报告中严格定性为探索性构建集，不提供任何确认性证据；与之完全不相交的 160 簇 `formal` 分割作为唯一一次性的确认性检验集。**
4. **Step 5a（`P16.4.5`）与 Step 5b（`P16.4.6`）混合连续—离散推断校准事实**：
   - 在 Step 5a（`scheme-a-calibration-20261031/`，独立种子银行 `2026103101`）纯重抽验证中，簇配对 `percentile` 通过 `83 / 88` 格（`studentized` `46 / 88`），但离散配对三值槽 `SA1, SA4`（$d_i \in \{-1, 0, +1\}$）在低异号／近天花板分布下因互异重抽均值数 `< 20` 触发保守退化（`empirical-observed` 上 `SA4` 功效跌至 `0.0315`）。
   - 在 Step 5b（`scheme-a-hybrid-calibration-20261101/`，验证种子银行 `2026110101`、功效种子银行 `2026110111`，封存 8 模块组合哈希 `code_sha256 = 4e7030de928ec5a7a9fe398c557795ccd4f34a1693c7cebda475a675386537b1`，认证查表 `exact_tango_tables_sha256 = 090bfbb5a859238ad05100443b4727c61644e030fd2d5e05359c5d575f4c46bf`）中，离散槽 `SA1, SA4` 升级为基于 Tango (1998) 得分排序的认证无条件精确查表，连续槽 `SA2, SA3` 并列评估候选 1 `hybrid_pct_tango`（簇配对 `percentile`）与候选 2 `hybrid_bessel_t_tango`（有限样本自由度保序外扩，$c_{80} = 1.0298684039340296$）。
   - Step 5b 实测结果（参见 `scheme-a-hybrid-calibration-20261101/results/candidate-selection-summary.json`；独立批判者 `c` 终审 `scheme-a-hybrid-calibration-20261101/c-final.md`：`总体判定：无阻断`）：
     * **贴边退化门禁 `D_j`**：两项混合候选均为 **`5 / 5` PASS**（全矩阵 `576,000` 次离散槽评估 `0` 次退化）；
     * **双银行功效充分性门禁 `P_j`**：两项混合候选均为 **`17 / 17` PASS**。在 `#83 empirical-observed` 经验效应格（`validation` 银行 `2026110101`，`R = 2000, B = 5000, n = 80`）上，`hybrid_pct_tango` 四槽联合检出功效 **`all4 = 0.9945`**（单槽 Holm 检出率：`SA1 = 1.0000`、`SA2 = 0.9955`、`SA3 = 0.9990`、`SA4 = 1.0000`），`hybrid_bessel_t_tango` 四槽联合检出功效 **`all4 = 0.9925`**（单槽 Holm 检出率：`SA1 = 1.0000`、`SA2 = 0.9935`、`SA3 = 0.9990`、`SA4 = 1.0000`），而共享流纯重抽 `percentile` 的 `all4` 仅为 `0.0315`（受限于 `SA4 = 0.0315`）；在 `#85 empirical-attenuated-75pct` 经验 75% 衰减效应格上，`hybrid_pct_tango` 仍保持 `all4 = 0.8100`（`SA1 = 0.9205`、`SA2 = 0.8720`、`SA3 = 0.9520`、`SA4 = 1.0000`），`hybrid_bessel_t_tango` 保持 `all4 = 0.7955`（`SA1 = 0.9170`、`SA2 = 0.8580`、`SA3 = 0.9440`、`SA4 = 1.0000`）；
     * **家族级与边际覆盖五项判据**：两项混合候选在 `validation` 全部 **`88 / 88`** 格（含 Block 5 全部 `14 / 14` 个 `2%` 与 `4%` 缺失机制压力格）上均通过 `fwer_passed`（最大 `0.0570 <= 0.05 + 2*MCSE`）、`family_direction_passed`（最大 `0.0570`；纯非零反号 `wrong_direction_rate` 最大 `0.0055`）、`individual_coverage_9875_passed`（最小 `0.9785 >= 0.975`）、`simultaneous_coverage_9875_passed`（候选 1 最小 `0.9440`，候选 2 最小 `0.9465`，均 `>= 0.95 - 2*MCSE`；共享流 `percentile` 仅 `83 / 88`）与 `screen05_passed`（最大 `0.0645 <= 0.075`）；
     * **未加 MCSE 缓冲的单槽原假设尾部筛查 `screen0125 <= 0.01875`（`R = 2000` 下要求拒绝计数 `<= 37`）**：两项混合候选均停于 **`C_j = 82 / 88` FAIL**，在相同的 6 格（`#0 regular-null` 的 `SA1 = 38/2000 = 0.0190`，其精确有理三项参数 `(7/97, 83/97, 7/97)` 下真实第一类错误率经精确有理枚举为 `0.01136770 < 0.0125`；以及 5 个 `{0, 50, 100}` 步长 `0.625` 规则晶格连续槽 `#4 SA2 = 38`、`#48 SA3 = 42`、`#64 SA2 = 38`、`#67 SA2 = 40`、`#68 SA3 = 43/2000 = 0.0215`）超出 `37 / 2000`，因此按预注册确定性主选函数落入 **`branch_id = 4`**（`(E_1, E_2) = (False, False)`，`recommended_method = null`，预留 `confirmation` 种子银行 `2026110102` 全程硬禁用未运行）。

### 0.3 用户特批选项 III 冻结前例外与三层统计声称边界（`2026-11-01`）
2026-11-01 用户审阅 Step 5b 终稿后明确作出架构裁决：**采用选项 III（特批直接进入正式集冻结准备）**，不事后篡改或抹除 Step 5b 的 `C_j = 82 / 88` 与 `branch_id = 4` 记录，不动用 `confirmation` 银行 `2026110102`，在完整透明披露上述校准边界的前提下锁定：
- **主确认统计程序**：封存的 **`hybrid_pct_tango`**（第一顺位候选：`SA1, SA4` 用认证无条件精确 Tango，`SA2, SA3` 用分层整簇配对 `percentile` bootstrap，`m = 4` Holm `alpha = 0.05`，单槽名义 `98.75%` 区间）；
- **预注册敏感度伴随程序**：封存的 **`hybrid_bessel_t_tango`**（第二顺位候选：`SA1, SA4` 同上，`SA2, SA3` 用有限样本自由度保序外扩常数 $c_{80} = 1.0298684039340296$，在同一共享重抽流上并列输出，专门核查正式集连续槽结论对有限样本尾部分位外扩的稳健性）。

遵循 `PLAN.md` §4.2“冻结稿里关于保护水平的措辞，按验证实际达到的水平写，不写高于验证结果的说法”的硬性纪律，S7 正式集报告与论文正文必须严格区分三层统计保证：
1. **离散配对三值槽（`SA1, SA4`）**：享有连续单纯形 $\Delta_3$ 分段解析单调性、IEEE-754 向外有向舍入与 `fractions.Fraction` 左截点共同保证的**有限样本认证无条件精确第一类错误率上界与覆盖率下界**（含 `[0, 1]` 有界缺失样本路径包络）；
2. **连续配对均值差槽（`SA2, SA3`）及四槽联合家族**：属于非参数整簇配对重抽（及 Bessel-`t` 尺度外扩）近似推断，其声称边界严格限定为 **Step 5b `88 + 56` 格有限模拟矩阵（`R = 2000, B = 5000, n = 80`）实测达到的频率性质**（`88 / 88` 格通过 `FWER <= 0.05 + 2*MCSE`〔最大 `0.0570`〕、`SimultCov9875 >= 0.95 - 2*MCSE`〔候选 1 最小 `0.9440`，候选 2 最小 `0.9465`〕、`IndCov9875 >= 0.9785`、`screen05 <= 0.0645`；同时如实披露固定无缓冲单槽尾筛 `screen0125 <= 0.01875` 为 `82 / 88`，最大实测值 `0.0215`），**严禁写成连续槽具有任意总体非渐近精确保证，亦严禁写成自动通过了 Step 5b `E_j` 准入门禁**；
3. **开发集（`dev`，`n = 20`）与描述性观察剖面**：开发集读数仅作方法构建背景；S7 观察剖面中的其余条件对比、`M_W`、`AUC`、`DAP / CF` 与历史 V4 `m = 10` 指标一律定性为预指定描述性／探索性证据，不承载主家族错误率保护声称。

---

## 1. 实验材料、配对簇分割与正式集计划单元清单

### 1.1 原始材料与授权边界
- **上游来源**：GitHub `boleima/ImperfectiveParadox`，固定 commit `938ef893c3368f3a597e6add2cfebdad02fddebf`（取得与核对日期 `2026-10-26`，详见 `exp1-en/data-provenance.md`）。
- **锁定材料文件 SHA256（位于本地 `exp1-en/data/`，Git 排除；S6 启动前由 `gpu_s6_formal_stage_macos.py` 强制重算核验）**：
  - `exp1-en/data/imperfectiveNLI.json`：`ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a`（400 条，4 组各 100 条：`A` 终结＋中断〔金标准 `False`〕、`B` 非终结＋中断〔金标准 `True`〕、`C` 终结＋无中断〔金标准 `Unknown`〕、`D` 非终结＋无中断〔金标准 `True`〕）。
  - `exp1-en/data/run_inference.py.txt`：`5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880`（仅用 Python `ast.parse` 静态提取 `PROMPT_TEMPLATES` 字面量，从不执行上游脚本；提取后 `PROMPT_TEMPLATES` 规范化 JSON SHA256 为 `6573fa60c8043f87dda67c616460afcfb60dd75759b4a1c7d6647dd3b614ae3b`）。
- **版权与不落盘纪律**：材料依据论文 v3 `Artifact Usage` 节 `CC BY-NC 4.0` 声明仅供研究使用（上游仓库无独立 `LICENSE` 文件）；`exp1-en/data/` 与 `exp1-en/raw/` 严格排除在 Git 之外，S7 生成的可入库分析摘要（`formal-unit-index.json`、`formal-analysis-results.json`、`report-s7-formal.md`）**不得拷贝题目原文 `premise` / `hypothesis`，亦不得保留模型自由生成文本或非白名单 JSON 键名**。

### 1.2 冻结分割（`exp1-en/split.json`）与正式集 160 簇清单
- **分割文件**：`exp1-en/split.json`，SHA256 `6821a3b3ad2378d51c683b8abc8a5b45d402b9997e3c8957bcda95cd0ef289b7`，分割种子 `20261090`。
- **簇结构**：`A_<id>` 与 `C_<id>` 共享同一终结动词与假设句，组成 1 个终结配对簇（`AC` 簇）；`B_<id>` 与 `D_<id>` 共享同一非终结活动动词与假设句，组成 1 个非终结配对簇（`BD` 簇）。
- **三阶段规模与计划清单哈希（`common.digest(context.plan(stage))`，调度打乱种子 `20261091`）**：
  - `smoke`：4 题（`A_003, B_011, C_003, D_011`）× 13 条件 = `52` 单元，`planned_units_sha256 = d4d04e7d73ea13d88fdb05b74ef581d1e152c0ef55961c883d7f150be119c630`；
  - `dev`：20 个 `AC` 簇 + 20 个 `BD` 簇 = 80 题 × 13 条件 = `1,040` 单元，`planned_units_sha256 = 14d5521f2f187ab4e1cf87f31c71ac35fc452a5d5388cc545698507192627881`；
  - `formal`：**80 个 `AC` 终结簇 + 80 个 `BD` 非终结簇 = 160 簇 = 320 题 × 13 条件 = `4,160` 单元**，`planned_units_sha256 = bb1cf2bb220ecab977f747dae1e24ee7f80aaf174ac5bce16e4dc5e06d8f92b7`。
- **`formal` 80 个终结簇编号（`telic_clusters`，对应 `A_<id>` 与 `C_<id>` 共 160 题；动词子类计数：`Change_of_State = 35`、`Creation = 31`、`Consumption = 7`、`Motion_to_Goal = 7`）**：
  `001, 002, 004, 005, 006, 008, 011, 012, 013, 014, 016, 019, 020, 022, 023, 024, 025, 026, 027, 029, 030, 031, 032, 033, 035, 036, 038, 039, 040, 042, 043, 044, 045, 046, 047, 048, 049, 050, 051, 052, 053, 055, 056, 057, 059, 060, 061, 063, 064, 065, 066, 067, 068, 069, 070, 072, 073, 074, 075, 076, 077, 078, 079, 080, 081, 082, 083, 085, 086, 087, 088, 089, 092, 093, 094, 096, 097, 098, 099, 100`。
- **`formal` 80 个非终结簇编号（`atelic_clusters`，对应 `B_<id>` 与 `D_<id>` 共 160 题；全部为 `Activity = 80`）**：
  `001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 012, 013, 014, 015, 016, 018, 019, 020, 021, 022, 023, 024, 026, 027, 028, 029, 030, 031, 032, 033, 034, 035, 038, 040, 041, 042, 043, 044, 045, 049, 050, 051, 052, 053, 054, 055, 057, 058, 059, 060, 061, 062, 063, 066, 067, 068, 069, 070, 071, 072, 074, 075, 076, 079, 080, 083, 086, 087, 088, 089, 090, 091, 092, 093, 094, 095, 096, 097, 098, 100`。
- **固定调度顺序**：320 个 `formal` 题号按字典序排序后经 `random.Random(20261091).shuffle(ids)` 一次性打乱；每题内部按固定 13 组合顺序连续执行：`L/Z -> L/DAP -> L/CoT -> L/CF -> Ps/Z -> P/Z -> P/DAP -> P/CoT -> P/CF -> M/Z -> M/DAP -> M/CoT -> M/CF`。

---

## 2. 受测模型、主机资产、运行程序哈希与前置准入证据链

### 2.1 受测模型、分词模板与推理服务冻结参数
- **配置标识**：`qwen3-8b@macmini-m6`（主机 `host_id = "macmini-m6"`，Mac mini Apple Silicon M6，24 GB 统一内存，macOS Metal 后端）。
- **完整运行指纹 ID（`context.fp`）**：`895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2`（命名空间前缀 `fp8 = 895f4e6f`）。
- **模型与分词器身份（`exp1-en/config_models.json`、`exp1-en/config_assets_macmini-m6.json`）**：
  - 上游模型仓库与固定 commit：`Qwen/Qwen3-8B` @ `b968826d9c46dd6066d109eabc6255188de91218`；
  - 量化权重文件：`/Volumes/2026General_Space/imperfective/models/gguf/Qwen3-8B-b968826d-Q8_0.gguf`，SHA256 `5a337baa986cf2bf23564cf31276593421b1865288a221427703ab45ea0ff47b`；
  - HF 分词器（离线缓存 `HF_HOME=/Volumes/2026General_Space/imperfective/hf`，`HF_HUB_OFFLINE=1`）：
    - `tokenizer.json`：`aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4`；
    - `tokenizer_config.json`：`d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101`；
    - `chat_template_sha256`：`a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8`（客户端通过 `transformers` `5.19.0` 执行 `apply_chat_template(..., tokenize=False, add_generation_prompt=True, enable_thinking=False)` 后编码为原始 token ID 数组直传 `/completion`，服务端不再二次套模板）；
  - 冻结首字母标签 token 集合（`exp1-en/label_tokens_qwen3-8b.json`，480 种标准上下文两两不相交核验通过，`not_applicable = 0`）：
    - `"True"`：`[830, 1866, 2514, 3007, 8214, 20611]`；
    - `"False"`：`[895, 3557, 3849, 4049, 7833, 30351]`；
    - `"Unknown"`：`[9788, 13790, 16088, 21693, 51378, 61395]`。
- **`llama-server` 二进制与冻结启动参数**：
  - 二进制路径：`/Volumes/2026General_Space/imperfective/opt/llama.cpp/b11560/llama-server`；
  - 二进制 SHA256：`1bf5602a2be50097c44282a6ecc63234d94ee8f96d39fd45fed6eff4e74b6b41`；
  - 版本与构建号：`version: 0.6.0-dev (build 11560, commit b13a93a3d)`（`/props` `build_info = "b11560-b13a93a3d"`）；
  - 服务参数：`["/Volumes/2026General_Space/imperfective/opt/llama.cpp/b11560/llama-server", "-m", "/Volumes/2026General_Space/imperfective/models/gguf/Qwen3-8B-b968826d-Q8_0.gguf", "--port", "18080", "-c", "16384", "-ngl", "999", "--parallel", "1", "--host", "127.0.0.1", "--no-webui", "--seed", "0"]`。
- **贪婪解码与生成上限（`exp1-en/subject.py`）**：
  - `SAMPLING = {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0, "samplers": ["temperature", "top_k"], "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0, "dry_multiplier": 0.0, "xtc_probability": 0.0, "typical_p": 1.0, "top_n_sigma": -1.0, "mirostat": 0, "dynatemp_range": 0.0}`；
  - 请求级固定种子 `SEED = 20261091`；`n_probs = 100`，`post_sampling_probs = false`，`cache_prompt = false`；
  - 停止符：`{eos_token_id}` 并入 `("<|im_end|>", "<|endoftext|>")`；
  - **全条件统一输出上限 `MAX_TOKENS = 1024`**（与 Ma & Miyao 原论文 `512` 上限不同，论文与报告必须显式说明此差异；`stop_type != "eos"` 一律判 `truncated = True`）。

### 2.2 冻结运行器源码、主机适配、封存统计引擎与 S6/S7 入口脚本 SHA256 总表

| 类别 | 仓库相对路径 | 冻结 SHA256 |
|---|---|---|
| 运行器指纹文件（1/18） | `exp1-en/common.py` | `012ae4efd15aa2c338f93d994495cd3209bc032657e8178b4e37d52f1858e8de` |
| 运行器指纹文件（2/18） | `exp1-en/provenance.py` | `6beed0b5791d234f36b20bfc989fea50361a9d1deb845998f60bdbf4013e10a8` |
| 运行器指纹文件（3/18） | `exp1-en/split.py` | `6a7174420097a1bcb9e41dace3c3b8ac7787f8598b268a0b3f3d8fc97ec65c4b` |
| 运行器指纹文件（4/18） | `exp1-en/prompts.py` | `f7cdd0fb5e9ec7979d9f6180943c6cc0ae1f1be1df92e6d77d1778a3a7818343` |
| 运行器指纹文件（5/18） | `exp1-en/prompt_parts.py` | `027a6329088a71bb18fe2d4ac8d4999bec00f34af707092c659d54d5f69b8e41` |
| 运行器指纹文件（6/18） | `exp1-en/parse.py` | `b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342` |
| 运行器指纹文件（7/18） | `exp1-en/protocol.py` | `398669f4bdc20c15878d16520b5558e2de98d45c5584add05bde9aedb8efc61e` |
| 运行器指纹文件（8/18） | `exp1-en/score.py` | `06a5d845c5a9878640d3562f7f85dc6e9fe8b81a96f9956d6dee96a16c5a6c5e` |
| 运行器指纹文件（9/18） | `exp1-en/run.py` | `a4c5d3ccaa2fda541e8d48d571a134f295dc238765d80d4f149f84878ad182ef` |
| 运行器指纹文件（10/18） | `exp1-en/subject.py` | `aed0e039b8594678f652680cdc1f0c061ed81f90cb9e368b88aaa69a98cfe339` |
| 运行器指纹文件（11/18） | `exp1-en/host.py` | `f66209831b6fd3513269a07bde2b8dbcc0feac8c446868c62a3ce30eb460c147` |
| 运行器指纹文件（12/18） | `exp1-en/admission.py` | `5e32b7091ee411fd6b46fc74f4f602c7826e262b06c1277e93c2a970f9ce5fd9` |
| 运行器指纹文件（13/18） | `exp1-en/ledger.py` | `4b2da3e94bb1a6edf4e32943efef226662e3de69ae000302080ee33cc916871a` |
| 运行器指纹文件（14/18） | `exp1-en/gates.py` | `2b3c57616a2d0135a8eda30fc9e8189a9931f964e54a37c4930ad3c36fe0c718` |
| 运行器指纹文件（15/18） | `exp1-en/deadline.py` | `1c74b4fb02417719c54e3ce1ddd2341eebaba245f6063628be53e3a0c327e370` |
| 运行器指纹文件（16/18） | `exp1-en/dry_stub.py` | `c0b7dae1c45bc32446713840ad406a24709fece7a9f127c09486c5e7b954660d` |
| 运行器指纹文件（17/18） | `exp1-en/check_tokens.py` | `0f8cc6cf08f4942687d80265174ecf99ad371326365f6a59dffe22ff676bb2fe` |
| 运行器指纹文件（18/18） | `exp1-en/split.json` | `6821a3b3ad2378d51c683b8abc8a5b45d402b9997e3c8957bcda95cd0ef289b7` |
| 主机与资产配置 | `exp1-en/host_macos.py` | `ff6971a7443b31fcb452c54a93c7806170d6e6908725262503de506ac4d4880b` |
| 主机与资产配置 | `exp1-en/config_models.json` | `64e2eba87ecd4173caa7cce8734e57517bd704a7c217638107e144319acdb1c4` |
| 主机与资产配置 | `exp1-en/config_assets_macmini-m6.json` | `6af91feeafd4d82597133b7eabeea65a4d2296f8e1fbf2fed71c730326703ca1` |
| 主机与资产配置 | `exp1-en/host_paths_macmini-m6.json` | `98a6ce3cb989a723b4833f48dfa4596b79a7d7a140e078cad87feea18f6f4ea4` |
| 主机与资产配置 | `exp1-en/label_tokens_qwen3-8b.json` | `db388dec0a0ecfc93d8bc55e6fa66da460a153bfdd01c1b54f23214b04691259` |
| GPU 队列预检与工具 | `exp1-en/gpu_preflight_macos.py` | `cd613ac6b1fe3b2158f3fb0fb90372452f2139cd998b70dc9c55b02372b06e73` |
| Mac `~/gpu-queue/bin/gpujob` | `~/gpu-queue/bin/gpujob` | `b4e6e7e8844800dafcafd5925c5c95680b6226e91f97de8b4e9c84e6ca5c4bfc` |
| **S6 正式阶段启动器（绑定清单核验）** | `s5-mac-handoff-20261101/gpu_s6_formal_stage_macos.py` | `eaf842c43b2a326565666ae7f583783d4f3c922e5d97d6e16726b0be97644f49` |
| **S7 正式统计与报告引擎（绑定清单核验）** | `s5-mac-handoff-20261101/run_s7_formal_analysis.py` | `604f84a7adb07b2c92149fa6f39b4fd360c7b529eba7c45eb0b3a4298b581d77` |
| 封存统计核心（组合哈希） | `scheme-a-hybrid-calibration-20261101/code/`（8 模块） | `4e7030de928ec5a7a9fe398c557795ccd4f34a1693c7cebda475a675386537b1` |
| 封存统计模块（1/8） | `.../code/inputs.py` | `e0b741ba5cf9425384ea264d8df35125e69a0c2de6718b86cb24f90f8e72e1cf` |
| 封存统计模块（2/8） | `.../code/exact_tango.py` | `ee77b072b9afbb2fa729186508e44bc2f689fc5542ca39b90e541dd03e77ce29` |
| 封存统计模块（3/8） | `.../code/core_a.py` | `7186dc975a11ac5d6af54d0b336e03e3bff7a3a875d7a444e2d8e250542ecbe7` |
| 封存统计模块（4/8） | `.../code/dgp_a.py` | `418398245f6c503fd19146ecc566084ceb155adbd8a5f93c0936b67d5df52832` |
| 封存统计模块（5/8） | `.../code/manifest_a.py` | `bb8a3543185e4f94004752fba9106f988e4c92c830a1993fd6afeb1858c5bfef` |
| 封存统计模块（6/8） | `.../code/run_sim.py` | `997df243297a1d038d299b6d03f61e9ce9997efbf944fbceec813662f4b17314` |
| 封存统计模块（7/8） | `.../code/summarize_sim.py` | `601c248f0e11ed07dc4f83085bdf1d92696aeec04e2ed3a8fef6696ddad2159a` |
| 封存统计模块（8/8） | `.../code/formal_engine.py` | `628fa960b06c9079af8eb64066f1a9150e54d451e94fbafc7cbd8c8f886b9b9e` |
| 认证精确 Tango 查表文件 | `.../manifests/exact-tango-tables.npz` | `090bfbb5a859238ad05100443b4727c61644e030fd2d5e05359c5d575f4c46bf` |
| 认证精确 Tango 数组载荷 | `exact-tango-tables.npz` 内部规范化载荷 | `696ee99245213ad6e7c9fe13d45b1cd239a6e62462888bba86e54a50f82dd89a` |

- **无循环双向密码学绑定与确认性运行参数硬锁（`s5-mac-handoff-20261101/s6-s7-execution-manifest.json`）**：
  - 为防止 `PLAN-E1.frozen.md` 被任意无关文档加自洽 `freeze.json` 顶替，或 S6/S7 入口脚本在冻结后被改动，同目录配有无循环绑定清单 `s6-s7-execution-manifest.json`（`schema_version = "exp1-s6-s7-execution-manifest-v1"`），同时记录本文件 `PLAN-E1.md` 的精确 SHA256（`expected_frozen_plan_sha256`）以及 `gpu_s6_formal_stage_macos.py`（`eaf842c4...`）与 `run_s7_formal_analysis.py`（`604f84a7...`）的精确 SHA256。
  - 在任何非 `dev` 阶段启动时，`gpu_s6_formal_stage_macos.py` 与 `run_s7_formal_analysis.py` 均实时自检自身与配对入口脚本的磁盘 SHA256 必须等于 `s6-s7-execution-manifest.json["entrypoints"]`，同时核验 `PLAN-E1.frozen.md` 的 SHA256 同时等于 `freeze.json["frozen_plan_sha256"]` 与 `s6-s7-execution-manifest.json["expected_frozen_plan_sha256"]`，且 `PLAN-E1.frozen.md` 正文嵌入上述两项入口脚本哈希；任一不符立即以 `PermissionError` 阻断。
  - `run_s7_formal_analysis.py` 在确认性 `--stage formal` 模式下硬性锁定生产参数与标准输入路径：`config = "qwen3-8b@macmini-m6"`、`expected_fp = "895f4e6f..."`、`B = 5000`、`FORMAL_ANALYSIS_SEED = 2026110201`、`allow_non_ok = True`、锁定默认绑定清单 `s6-s7-execution-manifest.json`、禁止 `--unit-index-json` / `--results-jsonl` / `--split` 路径覆盖（必须从 `exp1_root` 标准命名空间直接流式校验 `results.jsonl` + `sessions.json` + `fingerprint.json` + `statistics.json`），并锁定与封存 `exact_tango.DEFAULT_GRID_CONFIGS` 一致的分段 Tango 认证网格（`n <= 20` 取 `G = 1200, M = 1024`；`n > 20` 取 `G = 2000, M = 2048`）。任何参数或输入路径覆盖仅允许在显式传入 `--diagnostic-non-confirmatory` 隔离标志时运行；一切非确认性运行（含 `--diagnostic-non-confirmatory` 与 `--stage dev`）强制置 `confirmatory_valid = False`，并在落盘前统一执行跨通道、大小写不敏感的输出文件名保护——禁止 `--out-json`、`--out-report` 或 `--write-unit-index` 中任一输出通道占用 `formal-analysis-results.json`、`report-s7-formal.md` 或 `formal-unit-index.json`（含跨通道互换与大小写变体）。

### 2.3 Mac 上已通过的前置准入证据（同指纹 `895f4e6f`，`run.py` 启动 `formal` 前自动重算核对）
- `raw/admission/qwen3-8b@macmini-m6/895f4e6f/s1_review.json`：`a866c19b2ec74224305adf721a14d4bae362eaba4f86234db0f6a0af4ccecc94`（对应 S1 题面人工审查预览文件 `preview_S1.md` SHA256 `4229b7fd7f6501870d9930f1c992fa204223bcff24cb632967b14fe1ed8764cf`）
- `raw/admission/qwen3-8b@macmini-m6/895f4e6f/s2_acceptance.json`：`0c523a83a202af9667e6e7a16cdd21c1ea8567592d820cb4a619997e9a3350f5`
- `raw/admission/qwen3-8b@macmini-m6/895f4e6f/verify_vocab.json`：`0fc05b2563aae4c82d7353e66aaac53418b7eee8ddd0792c50df767693d918ec`
- `raw/admission/qwen3-8b@macmini-m6/895f4e6f/verify_probs.json`：`a9046964804d81f3a14640a312dc315ee6b993f32587348dbd330b2ed62f1ae1`
- `raw/admission/qwen3-8b@macmini-m6/895f4e6f/verify_greedy.json`：`5a65550d0987f12798ce86c88ca51538bc8d80a927f63329470132b5d8904520`
- `raw/dev/qwen3-8b@macmini-m6/895f4e6f/fingerprint.json`：`947a18d0055cf0238f85653244eca825a442b568a379970bb147f3afbe003c38`
- `raw/dev/qwen3-8b@macmini-m6/895f4e6f/results.jsonl`：`412c0360621743feb83922d41b1d937607707968eef0e462fa63999eb7cdf5b4`（1,040 条有效闭合记录）
- `raw/dev/qwen3-8b@macmini-m6/895f4e6f/gate.json`：`aa80dd8c8d17aec182513964f443e37bc3b0120565c8dafd8857dbc870a32a12`（`status = "pass"`）
- `raw/admission/qwen3-8b@macmini-m6/895f4e6f/determinism.json`：`54ca4d64b9ad7f263942d7401a91d2b31c05402e88fe62f14f9bfcf04c56cd57`（种子 `20261092`，`20 / 20` 匹配，`status = "pass"`）

---

## 3. 逐字提示模板、语义解析／严格协议／计分规则与 S6 正式运行规程

### 3.1 13 个（任务 × 提示）条件的逐字题面规范（`exp1-en/prompts.py`、`exp1-en/prompt_parts.py`）
1. **`L` 任务（`Z, DAP, CoT, CF` 四种提示，消息角色 `["system", "user"]`）**：
   - `system` 与 `user_format` 由 `prompts.original_templates()` 从 `exp1-en/data/run_inference.py.txt`（SHA256 `5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880`）的 `PROMPT_TEMPLATES` 字典字面量（规范化 JSON SHA256 `6573fa60c8043f87dda67c616460afcfb60dd75759b4a1c7d6647dd3b614ae3b`）无修改提取，`premise` 与 `hypothesis` 原样代入 `user_format.format(premise=item["premise"], hypothesis=item["hypothesis"])`（不经 `terminate()`；不含任何数据集原题文本的逐字模板如下）：
   - **`L/Z`（对应 `PROMPT_TEMPLATES["zero-shot"]`）**：
     - `system`（同时亦用于 `L/CoT`、`L/CF` 与 `Ps/Z`）：
       ```text
       System Prompt: You are a strict logician. Your task is to determine if a Hypothesis is necessarily true given a Premise.
       If the Hypothesis MUST be true based only on the Premise, output "True".
       If the Hypothesis is contradicted by the Premise, output "False".
       If the Hypothesis might be true but is not explicitly guaranteed by the Premise, output "Unknown".
       Do not use common sense assumptions. Only use the text provided.
       ```
     - `user_format`（同时亦用于 `L/DAP`）：
       ```text
       User Input: Premise: {premise} Hypothesis: {hypothesis}
       Please respond with ONLY one of the following options: "True", "False", or "Unknown".
       ```
   - **`L/DAP`（对应 `PROMPT_TEMPLATES["dap"]`）**：
     - `system`：
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
     - `user_format`：与 `L/Z` 逐字相同。
   - **`L/CoT`（对应 `PROMPT_TEMPLATES["cot"]`）**：
     - `system`：与 `L/Z` 逐字相同。
     - `user_format`（注：模板字面量中的双花括号 `{{` / `}}` 经 Python `.format(...)` 渲染后成为单花括号 `{` / `}`）：
       ````text
       Premise: {premise}
       Hypothesis: {hypothesis}

       Instruction: First, analyze the temporal status of the event in the premise. Does the action have a defined endpoint? Was it completed? Then, provide your final label (True, False, or Unknown).

       Output Requirement: You must output your response in strict JSON format containing exactly two keys:
       1. "reasoning": A string explaining your step-by-step logic.
       2. "label": The final judgment ("True", "False", or "Unknown").

       Do not include markdown formatting (like ```json). Return ONLY the JSON object.
       Example Format:
       {{
         "reasoning": "The premise describes a process...",
         "label": "True" / "False" / "Unknown"
       }}
       ````
   - **`L/CF`（对应 `PROMPT_TEMPLATES["counterfactual"]`）**：
     - `system`：与 `L/Z` 逐字相同。
     - `user_format`（注：第 4 行 `Instruction: ` 末尾保留上游字面量原有的 **1 个 ASCII 空格**，双花括号 `{{` / `}}` 经 `.format(...)` 渲染为单花括号 `{` / `}`）：
       ````text
       Premise: {premise}
       Hypothesis: {hypothesis}

       Instruction: 
       1. First, list 3 possible real-world scenarios where the action in the premise occurs but the result in the hypothesis is NOT achieved (e.g., interruptions, failures).
       2. Based on these possibilities, determine if the hypothesis is necessarily true.

       Output Requirement: You must output your response in strict JSON format containing exactly two keys:
       1. "possible_interruptions": a list of three strings for 3 possible real-world scenarios.
       2. "label": The final judgment ("True", "False", or "Unknown").

       Do not include markdown formatting (like ```json). Return ONLY the JSON object.
       Example Format:
       {{
         "possible_interruptions": ["..."],
         "label": "True" / "False" / "Unknown"
       }}
       ````
2. **`Ps` 任务（仅 `Ps/Z`，消息角色 `["system", "user"]`）**：
   - `system`：与上方 `L/Z`（`PROMPT_TEMPLATES["zero-shot"]["system"]`）逐字相同；
   - `user`（`premise` 与 `hypothesis` 原样代入，末尾无换行）：
     ```text
     User Input: Premise: {premise} Hypothesis: {hypothesis}
     What is the probability that the Hypothesis is necessarily true given only the Premise?

     On the last line of your answer, give the answer strictly in the following format:
     Probability: NN%
     where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
     ```
3. **`P` 与 `M` 任务（各含 `Z, DAP, CoT, CF` 四种提示，消息角色仅 `["user"]`）**：
   - `{P} = terminate(item["premise"])`，`{H} = terminate(item["hypothesis"])`（去掉首尾空白后若末尾无 `[.!?]["'”’)]*$` 则补英文句号 `.`）；各段落以单个空行 `\n\n` 连接，末尾无换行（逐字黄金测试基准锁定于 `exp1-en/test_prompt_golden.json`）：
     - 段 `S1`：`Here is a situation: {P}`
     - 段 `R`（仅 `DAP`）：
       ```text
       Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.
       - For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.
       - For activities (e.g., "was running", "was singing"), the process implies the action occurred.
       ```
     - 段 `Q`：
       ```text
       Using common sense, how likely is it that the following statement is true?
       Statement: {H}
       ```
     - 段 `T`（仅 `CoT`）：`First, analyze the temporal status of the event in the situation. Does the action have a defined endpoint? Was it completed? Then give your answer.`
     - 段 `T`（仅 `CF`）：`First, list 3 possible real-world scenarios where the action in the situation occurs but the result in the statement is NOT achieved (e.g., interruptions, failures). Then give your answer.`
     - 段 `A`（`P` 用 `ASK_DIRECT`，`M` 用 `ASK_MULTI`）：
       - `ASK_DIRECT`：
         ```text
         What is the probability that the statement is true?

         On the last line of your answer, give the answer strictly in the following format:
         Probability: NN%
         where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.
         ```
       - `ASK_MULTI`：
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
   - 段落顺序：`Z = [S1, Q, A]`；`DAP = [S1, R, Q, A]`；`CoT = [S1, Q, T(CoT), A]`；`CF = [S1, Q, T(CF), A]`。

### 3.2 语义解析（`PARSE_VERSION = 2`）、严格协议检查（`VERSION = 1`）与 `L` 首字母计分（`VERSION = 1`）
- **语义解析器（`exp1-en/parse.py`，`PARSE_VERSION = 2`）**：
  - `P` / `Ps`（`parse_direct`，`exp1-en/parse.py:42-45, 68-120, 202-211`）：先由 `strip_thinking` 剥离闭合 `</think>`（仅保留最后一个 `</think>` 之后的文本；含未闭合 `<think>` 则以 `thinking_unterminated` 失败），再按 `_FIELD = r"(?P<pre>[*_]*)(?P<key>probability)(?P<post>[*_]*)[ \t]*(?P<colon>[:：])"`（大小写不敏感，允许前后 Markdown `*` / `_`、空格／制表符及半角 `:` 或全角 `：`）查找全部字段匹配；若存在匹配，**仅截取最后一个匹配起点到该行换行符前的单行文本** `candidate = final[fields[-1].start():].split("\n", 1)[0]` 送入 `parse_direct_v1`。在冒号后的同单行剩余文本 `line_rest` 上，按 `_VALUE = r"[ \t*_]*(?P<num>[-+]?\d+(?:\.\d+)?)(?P<sp> ?)%"` 匹配开头数值：允许跳过前导空格、制表符与 `*` / `_`（例如 `Probability: **50%**` 解析成功），数字与 `%` 之间**至多允许 1 个半角空格 `' '`**（制表符 `\t` 或多个空格均失败，例如 `Probability: 50\t%` 失败），数值须有限且位于 `[0, 100]`，且 `%` 之后的同一行剩余文本不得再出现任何阿拉伯数字或 `%`（`_DIGIT_OR_PCT = r"[\d%]"`，例如 `Probability: 50% plus 2` 即便没有第二个 `%` 亦判 `range_or_extra_number` 失败）；若最后一个 `Probability:` 所在单行未通过上述任一检查，**直接返回失败（`ok = False, value = None`），绝不回退读取前文早先出现的 `Probability:` 字段**；
  - `M`（`parse_multi`）：剥离闭合 `</think>` 后取末尾一组完整 `Estimate 1..5` 行，每行 `p_k in [0, 100]`（带 `%`）、`w_k in [0, 1]` 且五项权重总和 `sum(w_k) > 0`，按正权重和归一化 $w^{\text{norm}}_k = w_k / \sum_{r=1}^5 w_r$：
    - **模型自报加权均值（`M_W`）**：`val_w = sum(w_norm_k * p_k)`（即运行账本中的 `row["value"]`，同时记录 `weight_sum_in_tolerance = (0.95 <= sum(w_k) <= 1.05)`）；
    - **五候选等权算术均值（`M_U`，方案 A 锁定主标量）**：`val_u = (p_1 + p_2 + p_3 + p_4 + p_5) / 5.0`；
  - `L`（`Z, DAP` 用 `parse_label_plain`；`CoT, CF` 用顶层 JSON 对象扫描器 `parse_label_json`）：提取 `"True" | "False" | "Unknown"` 及其精确字符偏移 `char_start`、格式形态（`exact` / `loose`）与推理键完整性（`reasoning_ok`, `label_last`, `escape`, `n_interruptions`）。
- **独立严格协议检查（`exp1-en/protocol.py`，`VERSION = 1`）**：在生成完成的单元（`status != "missing_transport"`）上，与语义可用状态 `status` 正交记录布尔值 `protocol_ok` 及来自 16 项固定枚举白名单的不合规原因列表 `reasons`（`last_line`, `estimate_lines`, `estimate_range`, `weight_sum`, `loose`, `none`, `ambiguous`, `label_form`, `fenced`, `dup_key`, `json`, `not_object`, `no_reasoning`, `label_first`, `extra_keys`, `n_interruptions`）；`missing_transport` 单元因未完成生成，`protocol` 为 `None`（记为 `unchecked`，不混入 `strict_protocol_fail`）。`protocol_ok == False` 且 `status == "ok"` 的单元在主分析中按有效语义读数计入，不得改计为 `missing`，并在 S7 成本与格式剖面中单独完整统计。
- **`L` 首字母 token 标签分数 `q`（`exp1-en/score.py`，`VERSION = 1`，`TOP_N = 100`）**：定位生成 token 序列中覆盖 `char_start`（标签词首字母）的下标 `j`（`Z, DAP` 要求 `j` 之前不含任何字母字符；`CoT, CF` 要求 `reasoning_ok`、`label_last` 且无转义），在原始前缀 `prompt_ids + generated_ids[:j]` 处读取 `top-100` 未采样对数概率（`j == 0` 直接复用首次生成 `first_topN`，`j > 0` 发一次 `n_predict=1, n_probs=100` 前缀计分请求），按冻结候选集 `label_tokens_qwen3-8b.json` 在对数空间计算保守闭区间 `[q_L, q_U]`（全部 18 个候选都在 `top-100` 内记 `q_status = "full"`，部分不在记 `"bounded"`，无任何候选或异常记 `"missing:<reason>"`）。
- **终结状态映射（`exp1-en/run.py:214-249`）**：每个已提交单元唯一落入四种互斥终结状态之一：
  1. `missing_transport`：生成阶段连续 3 次传输错误耗尽（`parsed = None, protocol = None`；记录后当前会话以 `reason = "transport_exhausted"` 安全收尾停止，续跑时跳过已提交记录继续剩余单元）；
  2. `missing_format`：`truncated == True` 或语义读数（`label` / `value`）为 `None`；
  3. `missing_score`：仅 `L` 任务，语义 `label` 解析成功且未截断，但 `q_status not in ("full", "bounded")`；
  4. `ok`：其余全部可用单元。

### 3.3 S6 正式阶段（`formal`）运行、收尾完备性门禁与闭合白名单脱敏规则
- **排队、互斥执行与 24 GB 内存流式护栏**：在 Mac 上一律通过 `~/gpu-queue/bin/gpujob submit --project imperfective --need-gib 12 --preflight .../exp1-en/gpu_preflight_macos.py --max-wait 1200` 串行持锁启动 `s5-mac-handoff-20261101/gpu_s6_formal_stage_macos.py`（保持同一 PID 与队列锁文件描述符不断开，自动核验 `s6-s7-execution-manifest.json`、上游 `exp1-en/data/` 文件 SHA256 与 `freeze.json`，并导出 `HF_HOME=/Volumes/2026General_Space/imperfective/hf` 与 `HF_HUB_OFFLINE=1`）。启动器对磁盘上全部 `exp1-en/*.py` 保持零字节修改（`context.fp = 895f4e6f...` 不变），默认启用进程内流式内存护栏（`--launch-mode in_process_streaming`）：`Ledger.commit` 先将含完整 `raw_response` / `topN` 的未修改记录全量写入并 `fsync` 至 `results.jsonl`，随后仅在内存中的 `formal` 副本剥离 `gates.compute` 从不读取的多兆字节 `raw_response` / `topN` / 自由文本字段，并将 `Ledger.load` 升级为逐行二进制流式扫描（保留原尾部损坏隔离修复语义与 `smoke` / `dev` 全量校验，并在 `admission.check_stage` 完成后、`llama-server` 启动前执行 `gc.collect()`），从而在磁盘产物逐字节等价的前提下避免 4,160 条 `formal` 记录在 24 GB 统一内存机器上产生约 `38–56 GiB` 的 Python 堆峰值。
- **无中途暂停裁剪（`exp1-en/gates.py:30-41`）**：与 `smoke` / `dev` 不同，`formal` 阶段不设中途 `PAUSE` 提前终止阈值；若设定了可选绝对截止时间 `--deadline-at <YYYY-MM-DDTHH:MM:SS+08:00>`，截止前 900 秒起不开新单元（`reason = "cutoff"`）或到点由原子看门狗中断未获准提交单元（`reason = "deadline"`），再次提交同一命令即可幂等续跑未执行单元，直至 `4,160` 个计划单元全部拥有有效闭合会话中的唯一终结记录。
- **S6 完成核账条件（进入 S7 时由 `run_s7_formal_analysis.py` 强制逐项校验，缺一即报错阻断）**：
  1. `exp1-en/raw/formal/qwen3-8b@macmini-m6/895f4e6f/` 下无 `run.lock`、无 `PAUSED.json`；
  2. `fingerprint.json` 必须存在且 `fingerprint_id == "895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2"`；
  3. `sessions.json` 中不存在任何 `state == "open"` 的未闭合会话，且至少存在一个 `state == "closed"` 会话；
  4. 流式扫描 `results.jsonl`：`commit_seq` 严格递增，有效闭合会话中的终结记录恰好唯一覆盖 `formal` 全部 `4,160` 个计划 `unit_key`（0 重复、0 遗漏、0 `E1-DRY-` 记录，且每条记录的 `stage == "formal"`、`config == "qwen3-8b@macmini-m6"`、`fingerprint_id == "895f4e6f..."`）；
  5. `statistics.json` 必须存在，`stage == "formal"`、`config == "qwen3-8b@macmini-m6"`、`fingerprint_id == "895f4e6f..."`，且与按 `gates.compute("formal", plan("formal"), valid_records)` 独立重算的结果逐字段完全一致（`status == "pass", complete == True, executed == 4160, planned == 4160, pause == None`）。
- **S7 导出 `formal-unit-index.json` 的严格闭合白名单脱敏规则**：仅允许保留受控数值／枚举标量与固定白名单键；除剥离 `raw_response`、`first_topN`、`q["topN"]`、`messages`、`text`、`prompt_ids`、`generated_ids*` 与 `parsed["object"]` 外，对模型在 `L/CoT` 或 `L/CF` JSON 中可能额外输出的任意键名列表 `parsed["extra_keys"]` **严禁原样落盘**，一律折叠为整数 `extra_key_count` 与 64 位十六进制摘要 `extra_keys_sha256`，彻底杜绝原题片段或自由生成文本经异常 JSON 键名混入版本库。

---

## 4. 锁定的主确认假设族（方案 A，`m = 4`）与统计推断规则

### 4.1 四项簇级配对主假设定义（全在 `formal` 160 簇：`n_ac = 80` 终结簇，`n_bd = 80` 非终结簇；完全对齐封存 `core_a.py`）

| 槽位编号 | 目标对比与测量角色 | 所在分层与簇样本量 | 第 $i$（或 $j$）个配对簇的观测变量定义（完全观测时） | 原假设 $H_{0,k}$ 与备择方向 | 主确认推断引擎（`hybrid_pct_tango`） | 预注册敏感度伴随（`hybrid_bessel_t_tango`） |
|---|---|---:|---|---|---|---|
| **`SA1`** | C 组高置信端点率（$\ge 95\%$）压低效应：`M_U/Z` 相对 `P/CoT` | 终结簇 `AC`（`n_ac = 80`） | $d_{1,i} = \mathbb{I}(P_{\text{CoT}}(C_i) \ge 95) - \mathbb{I}(M_{U,\text{Z}}(C_i) \ge 95) \in \{-1, 0, +1\}$；总体均差 $\theta_1 = \mathbb{E}[d_{1,i}] \in [-1, 1]$ | **单侧复合原假设** $H_{0,1}: \theta_1 \le 0$ vs $H_{1,1}: \theta_1 > 0$（$\theta_1 > 0$ 表示 `M_U/Z` 在无中断终结事件上的高置信端点率低于 `P/CoT`） | 认证无条件精确 Tango 查表（`n = 80`） | 与主程序完全相同（精确 Tango） |
| **`SA2`** | 终结事件中断敏感度差（`C - A`）对比：`P/CoT` 相对 `M_U/Z` | 终结簇 `AC`（`n_ac = 80`） | $y_{2,i} = \bigl(P_{\text{CoT}}(C_i) - P_{\text{CoT}}(A_i)\bigr) - \bigl(M_{U,\text{Z}}(C_i) - M_{U,\text{Z}}(A_i)\bigr) \in [-200, 200]$；总体均差 $\theta_2 = \mathbb{E}[y_{2,i}]$ | **双侧点零假设** $H_{0,2}: \theta_2 = 0$ vs $H_{1,2}: \theta_2 \ne 0$（$\theta_2 > 0$ 表示 `P/CoT` 的终结中断敏感度差 `C - A` 高于 `M_U/Z`，$\theta_2 < 0$ 表示 `M_U/Z` 的 `C - A` 高于 `P/CoT`） | 分层整簇配对 `percentile` bootstrap（`B = 5000`） | 有限样本 Bessel-`t` 保序外扩（$c_{80} = 1.0298684039340296$） |
| **`SA3`** | `CoT` 提示下非终结活动配对中断差（`D - B`）保持度对比：`M_U/CoT` 相对 `P/CoT` | 非终结簇 `BD`（`n_bd = 80`） | $y_{3,j} = \bigl(M_{U,\text{CoT}}(D_j) - M_{U,\text{CoT}}(B_j)\bigr) - \bigl(P_{\text{CoT}}(D_j) - P_{\text{CoT}}(B_j)\bigr) \in [-200, 200]$；总体均差 $\theta_3 = \mathbb{E}[y_{3,j}]$ | **双侧点零假设** $H_{0,3}: \theta_3 = 0$ vs $H_{1,3}: \theta_3 \ne 0$（量化 `CoT` 下五候选多估计相对单点概率在非终结活动配对中断差 `D - B` 上的偏移；$\theta_3 < 0$ 表示 `M_U/CoT` 的 `D - B` 小于 `P/CoT`，$\theta_3 > 0$ 反之） | 分层整簇配对 `percentile` bootstrap（`B = 5000`） | 有限样本 Bessel-`t` 保序外扩（$c_{80} = 1.0298684039340296$） |
| **`SA4`** | 离散标签 `L` 任务在 `CoT` 下 D 组有效蕴涵坍塌幅度：`L/CoT` 相对 `L/Z` | 非终结簇 `BD`（`n_bd = 80`，仅 D 组） | $d_{4,j} = \mathbb{I}(\text{label}_{L,\text{CoT}}(D_j) = \text{"True"}) - \mathbb{I}(\text{label}_{L,\text{Z}}(D_j) = \text{"True"}) \in \{-1, 0, +1\}$；总体均差 $\theta_4 = \mathbb{E}[d_{4,j}] \in [-1, 1]$ | **双侧点零假设** $H_{0,4}: \theta_4 = 0$ vs $H_{1,4}: \theta_4 \ne 0$（$\theta_4 < 0$ 确认离散标签在 `CoT` 下发生非终结有效蕴涵准确率下降） | 认证无条件精确 Tango 查表（`n = 80`） | 与主程序完全相同（精确 Tango） |

### 4.2 预注册重抽种子、线程护栏、多重检验、置信区间与缺失边界规则
1. **固定正式集重抽种子与执行环境**：
   - 重抽次数 `B = 5000`，批次大小 `batch = 256`；
   - **正式集唯一预注册重抽种子**：**`FORMAL_ANALYSIS_SEED = 2026110201`**，通过 `np.random.default_rng(np.random.SeedSequence([2026110201, 0]))` 生成 `AC -> BD` 交错多项式簇权重流（与开发集干跑种子 `2026110199` 及全部模拟种子银行 `2026103101 / 2026110101 / 2026110111 / 2026110102` 完全隔离）；
   - 运行时强制单线程数值护栏（`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1`）并执行 `verify_ieee754_rn_and_subnormals()`（验证 binary64 Round-to-Nearest-Even 与次正规数保活），同时实时校验 Step 5b 封存 8 模块哈希 `4e7030de...`、查表文件哈希 `090bfbb5...` 与 6 组 `Fraction` 左截点。
2. **`m = 4` Holm 逐步降序多重检验与置信区间水平**：
   - 四槽原始 $p$ 值 $(p_1, p_2, p_3, p_4)$ 按 `(p_k, k)` 升序稳定排序（并列时按槽位下标 `SA1 -> SA2 -> SA3 -> SA4` 确定性破平），依次与 $\alpha / (4 - r) \in \{0.0125, 0.016\overline{6}, 0.025, 0.05\}$（总水平 $\alpha = 0.05$）比较，遇到首个不满足 $p_{(r)} \le \alpha / (4 - r)$ 的位置立即停止，其后一律不拒绝；同时按封存 `core_a.holm_adjust` 输出单调包络校正后 $p^{\text{Holm}}_k = \max_{j \le r(k)} \min(1, (4 - j) p_{(j)})$。
   - **主报告同时置信区间**：四槽统一采用名义 **`98.75%`** 置信区间（对应单槽双侧水平 $\alpha_{\text{ind}} = 0.05 / 4 = 0.0125$；在 `B = 5000` 不插值逆经验分布下取 0-based 秩 `[31, 4968]`，即 1-based 第 `32` 与第 `4969` 个有序重抽统计量；离散槽查 `exact-tango-tables.npz` 的 `n80_theta_L_0125`）。历史 `99.5%`（$\alpha = 0.005$，0-based `[12, 4987]`）区间一并归档备查。
3. **连续槽退化保护规则（严格对齐封存 `core_a.py:42, 641-645, 761-764, 862-895`）**：
   - 对 `SA2` 或 `SA3`，满足以下任一条件即判定重抽分布退化：
     1. 下界流或上界流按容差 **`TOL_DUST = 1e-12`**（$10^{-12}$）计数的互异重抽均值数少于 `20` 个（`unique_low < 20` 或 `unique_high < 20`）；
     2. 下界流自身的名义 `98.75%` 原始分位跨度 $\theta^{*,L}_{(4969)} - \theta^{*,L}_{(32)} \le 10^{-12}$，或上界流自身的名义 `98.75%` 原始分位跨度 $\theta^{*,U}_{(4969)} - \theta^{*,U}_{(32)} \le 10^{-12}$；
     3. 区间端点出现非有限值（`NaN` / `Inf`）或反序（`ci_lo > ci_hi`）；
     4. 对伴随程序 `hybrid_bessel_t_tango`，还包括在裁剪到参数域 `[-200, 200]` 之前，外扩后的原始区间与 `[-200, 200]` 交集为空（即 `raw_ci_lo > 200.0` 或 `raw_ci_hi < -200.0`）。
   - 一旦触发退化，该连续槽统一置 $p = 1.0$、置信区间回退至整个参数域 **`[-200, 200]`**（`SA2` 与 `SA3` 均为 `[-200, 200]`），结论记为 **`"证据不足（重抽分布退化）"`**。
4. **最不利缺失界限传播与方向判读规则**：
   - **主分析缺失口径（与 `exp1-en/gates.py` 的 `usable` 定义及封存 `formal_engine.py` 严格一致）**：单元 `status == "ok"` 时取精确观测值；任意 `status != "ok"`（含 `missing_transport`、`missing_format`、`missing_score`）的单元一律代入最不利闭区间——连续概率（`P, Ps, M_U, M_W`）代入 `[0.0, 100.0]`，离散二值指示量（`L` 标签正确率指示量、`>= 95%` 端点指示量）代入 `[0.0, 1.0]`，按各对比线性或单调系数的正负精确传播为簇级上下界 `(lower_i, upper_i)`：
     * 离散槽 `SA1, SA4`：在 `(d_lower, d_upper)` 上由封存 `infer_exact_tango_slot` 计算最不利精确 $p$ 值与最宽包络区间；
     * 连续槽 `SA2, SA3`：在同一重抽权重下同步计算下界版重抽统计量 $\theta^{*,L}_b$ 与上界版重抽统计量 $\theta^{*,U}_b$，受保护区间取 $[\theta^{*,L}_{(32)}, \theta^{*,U}_{(4969)}]$，双侧 $p = \min(1, 2 \min(p_+, p_-))$，其中 $p_+ = (1 + \#\{\theta^{*,L}_b \le 0\}) / (B + 1)$、$p_- = (1 + \#\{\theta^{*,U}_b \ge 0\}) / (B + 1)$（候选 2 按封存公式围绕 $\hat{\theta}^L, \hat{\theta}^U$ 外扩）。
   - **四槽结论用语映射**：
     * 未被 Holm 拒绝（含退化槽）：不作方向确认声明，记 `"未拒绝原假设（证据不足）"`（退化槽标 `"证据不足（重抽分布退化）"`）；
     * 被 Holm 拒绝（`SA1` 仅在 $\hat{\theta}^L_1 > 0$ 单侧正方向可拒绝，记 `"方向确认（θ_1 > 0）"`；双侧槽 `SA2, SA3, SA4` 若 $p_+ < p_-$ 且点估计区间不跨反号即 $\hat{\theta}^L_k \ge 0$，记 `"方向确认（θ_k > 0）"`；若 $p_- < p_+$ 且 $\hat{\theta}^U_k \le 0$，记 `"方向确认（θ_k < 0）"`；若缺失导致点估计上下界跨零 $\hat{\theta}^L_k < 0 < \hat{\theta}^U_k$ 或 $p_+ = p_-$，不作方向符号声明，记 `"证据不足（缺失跨零）"`）。
   - **两项预指定缺失伴随诊断（当正式集出现 `non_ok_count > 0` 时自动并列输出；当 `non_ok_count == 0` 时与主分析恒等并记 `"not_triggered_zero_missing"`）**：
     1. **完整簇子集诊断（`PLAN.md` §4.2）**：仅剔除主假设涉及通道中含有 `status != "ok"` 单元的配对簇后重跑 `Scheme A`（若剔除后样本量 $n_{\text{cc}} \notin \{20, 80\}$，由封存 `exact_tango.build_certified_tables_for_n` 按与 `DEFAULT_GRID_CONFIGS` 一致的分段完整认证网格——`n <= 20` 取 `G = 1200, M = 1024`〔单样本量 `< 5` 秒〕，`n > 20` 取 `G = 2000, M = 2048`〔$20 < n_{\text{cc}} < 80$ 单样本量首次构建预计耗时约 `15–25` 分钟〕——实时构建精确 Tango 查表，耗时与网格参数由 Mac 本机 `runtime_telemetry` 独立实测记录）；
     2. **`L` 任务纯语义标签可用诊断**：若 `D_*/L/{CoT,Z}` 出现 `status == "missing_score"` 但生成未截断且语义 `label in {"True", "False", "Unknown"}` 已成功解析的单元，另报将该语义标签纳入 `SA4` 计数的伴随结果。

---

## 5. 预指定描述性观察剖面与硬性解释禁令

### 5.1 共享随机流（`SeedSequence([2026110201, 0])`）描述性观察剖面
S7 分析脚本 `s5-mac-handoff-20261101/run_s7_formal_analysis.py` 调用封存模块 `formal_engine.compute_observation_profile` 与四状态解耦合规统计器 `compute_four_status_compliance_profile`，在同一正式集重抽流上完整输出（附点估计／缺失区间、名义 `95%` `[125, 4875]` 与 `98.75%` `[32, 4969]` 簇重抽区间，以及全部单分层配对三值对比的认证精确 Tango 区间）：
1. **单条件与 2×2 配对对比全剖面**：覆盖 `P, Ps, M_U, M_W` 在 `Z, DAP, CoT, CF` 下共 13 个表示条件的四组均值（`mean_A..D`, `mean_all`）、配对中断差（`c_minus_a`, `d_minus_b`）、差中差（`did`）、组间排序分离度 `AUC(D > C)`、高置信端点率 `ep_high_C`（$\ge 95\%$）与双侧端点率 `ep_dual_C`（$\le 5\%$ 或 $\ge 95\%$），以及 13 组核心配对条件差和 `M_U / M_W` 的 2×2 交互项 `(M_CoT - M_Z) - (P_CoT - P_Z)`。
2. **候选池展开 vs 自报权重解耦剖面（`M_W - M_U`）**：在 `Z, DAP, CoT, CF` 四种提示下对称报告同一输出内的 `M_W - M_U` 配对差及端点变化。
3. **离散 `L` 任务全提示剖面**：在 `Z, DAP, CoT, CF` 下报告 `ACC_A..D`、`ACC_overall`、`TBR_C`、`TBR_A`、$\Delta_{\text{AA}} = \text{ACC}_D - \text{TBR}_C$、三标签分布计数，以及 `CoT - Z`、`DAP - Z`、`CF - Z` 的配对精确 Tango 与重抽区间。
4. **成本、耗时、截断、四终结状态解耦与严格协议合规性剖面（外加运行时遥测）**：
   - 13 个原始任务×提示条件及 19 组配对条件差的 `n_out_tokens`（均值、中位数、四分位距、最大占比 `/ 1024`）、`generation_seconds`、`unit_seconds` 与 `truncation`；
   - **四种终结状态严格正交拆解（不把 `missing_transport` 或 `missing_score` 混同为 `semantic_parse_fail`）**：总不可用率 `overall_unavailable`（`status != "ok"`）精确分解为 `generation_fail`（`missing_transport`）+ `semantic_parse_fail`（`missing_format`，再细分为截断与未截断空值）+ `scoring_fail`（`missing_score`，仅 `L` 任务首字母分数缺失而语义标签已解析成功）；
   - **严格协议三态划分**：`strict_protocol` 精确划分为 `checked_ok` + `checked_fail`（按 `reason_counts` 逐项拆解）+ `unchecked`（`missing_transport` 未进入协议检查，绝不计入 `strict_protocol_fail`）；
   - **`M` 任务权重和容差 `[0.95, 1.05]` 三态与区间传播**：精确划分为 `known_in_tolerance` + `known_out_of_tolerance` + `unknown`（当存在传输／截断／解析失败导致权重未知时，按最不利边界 `[known_in / n, (known_in + unknown) / n]` 传播区间，绝不把 `unknown` 当作容差超标）；当 `non_ok_count == 0` 时保留封存 `observation_profile` 原结构逐位一致，当 `non_ok_count > 0` 时同步将 `observation_profile["cost_and_format"]` 对齐至上述无混同口径；
   - **运行时遥测（`runtime_telemetry`）**：记录 Python、NumPy 与操作系统版本、进程峰值内存 `peak_rss_mib`，并分开记录零缺失核心／剖面耗时与动态精确 Tango 查表构建耗时。
5. **终结动词四子类描述性分解与材料歧义讨论**：当本地存在 `exp1-en/data/imperfectiveNLI.json` 时，按 `Change_of_State (35)`、`Creation (31)`、`Consumption (7)`、`Motion_to_Goal (7)` 输出无原文聚合均值；材料歧义遵循 `PLAN.md` §2 与 §10.6 已锁定口径，在讨论中引用 Han & Sun (2026) 的严格 NLI 与母语者另解比例（`A` 组 `76% / 38%`，`C` 组 `29%`）。
6. **历史参考与旧版归档（严格标为描述性归档）**：并列归档 `m = 4` 纯重抽 `percentile`、`studentized` 以及原 `PLAN.md` §4.1 的 V4 `m = 10`（`H1..H6b`）输出，仅作方法学透明对账，**严禁从归档指标中事后挑选显著项升级为确认性结论**。

### 5.2 硬性解释禁令
1. **禁止事后概率转离散标签调优**：严禁在 `P`、`Ps` 或 `M` 的 `[0, 100]` 概率读数上事后设定或搜索切分阈值将其折算成离散 `True / False / Unknown` 准确率，不得宣称连续口述概率任务在离散三分类准确率上“击败” `L` 任务。
2. **禁止跨模型或跨上限等价推断**：本实验受测模型为 `Qwen3-8B`（`Q8_0`，`llama.cpp` Metal，`MAX_TOKENS = 1024`），未包含原论文 7 个模型，不得将正式集读数解释为对原论文表 3 数值的逐模复现。
3. **禁止机制与因果过度外推**：`AUC(D > C)` 包含动词词汇与句长差异，仅称“该基准上的组间排序分离度”；`C - A`、`D - B` 与 `DiD` 仅称“配对语境读数差”，不称纯粹终结性因果效应；任务与提示间差异仅称“任务／提示框架下的可观测读数差异”。
