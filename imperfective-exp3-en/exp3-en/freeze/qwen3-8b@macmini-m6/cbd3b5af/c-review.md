〔c 评论家 #imperfective〕

# P16.6 / 实验 3：第 2 轮 S5 冻结前独立复核

审查日期：2026-11-04。按用户指定范围，复核 `report-s3-s4-autonomous.md` 和新增同步的 20 份 `determinism_calls/*.json`，对照第 1 轮审查、既有准入/分析/校准产物及 `PLAN-E3.md` §4.2(5) 明确继承的 `../exp2-zh/PLAN-E2.md` §4.2(6)。本上下文未参与作者修订或 S3/S4 执行。本轮仅进行本机离线核查。

## 总体判定

**无阻断。第 1 轮唯一阻断 B1 及建议 1–3 均已 100% 闭环，可作为“c 无阻断”的复核依据提交用户确认进入 S5（冻结与公开预注册）。**

修订后的阶段报告与现有数值证据一致。受保护文件匹配既定指纹，smoke/dev 账本及分析、校准产物的 SHA-256 与第 1 轮证据一致；未发现需要修改方案、代码、材料或重跑模型/模拟的问题。本轮未执行 S5、发布或正式集运行。

## 第 1 轮 B1 与建议 1–3 逐条复核表

以下路径均相对于 `exp3-en/`；配置为 `qwen3-8b@macmini-m6`，指纹目录为 `cbd3b5af`。

| 项目 | 复核位置与鉴别依据 | 复核结果 | 判定 |
| :--- | :--- | :--- | :--- |
| B1：H3 测量对象 | 阶段报告 §2.2、`PLAN-E3.md` §4.1、未变的 `core_e3.py` 与 `analysis.json` | 已统一为 `NI_PLAN(M_U/CoT) - INT_PLAN(M_U/CoT)`；未再用另一项元语言/对象层对比解释 H3。 | 已闭环 |
| B1：20 簇差值 | 阶段报告 §2.2、§3；第 1 轮从 dev 全账本独立提取的结果及本轮相同账本 SHA | 17 簇为 `0.0`；`025` 为 `-1.0`、`046` 为 `+7.0`、`085` 为 `+30.0`，均值 `+1.80`，与原始经验池相符。 | 已闭环 |
| B1：单侧 p 值及方法归属 | 阶段报告 §2.2 表头与 H3 行、`analysis.json` 两套 family | 四项原始 p 均明确为单侧。H3 百分位法为 `0.1277744451109778`（报告 `0.1278`）；Bessel-t 为 `0.13917216556688664`（报告 `0.1392`），两列区间和方法对应正确。 | 已闭环 |
| B1：Step 1/2 全部失败指标 | 阶段报告 §3；逐格重新按四项硬阈值判定保存的 60 项候选/降级格 | Step 1 为 `15/20`，Step 2 为 `17/20`；H3 单槽覆盖率、联合覆盖率及 CfgB 的 FWER 失败均已完整列出，详见下表。 | 已闭环 |
| B1：Step 3 规则与层级 | 阶段报告 §3、E3 §4.2(5)、继承的 E2 §4.2(6)、未变的统计核心 | 实际单项失败集合仅 H3；H4 单项通过；唯一一次降级重验 `20/20`。H3 降为第 3 层探索性描述指标，确认性家族仍为 `m=4`、Holm 分母 `4/3/2/1`，H3 固定确认性 `p=1`、98.75% CI=`[-100,100]`。 | 已闭环 |
| 建议 1：元数据引用 | 阶段报告 §1、§2.1、§3；S1 准入 JSON、审查文件实际 SHA、dev `sessions.json`、`admission.py` 与方案 | S1 审查 SHA 为 `6014a87a190d8446411df53db475fbbab9cd5b9e629231ac5b15adc6d11a5d1e`；dev 会话为 `93493887588049ab96e4f2f8cf2b850b`；种子为 `2026110392`；章节引用为 E3 §4.2(5)，继承 E2 §4.2(6)。四项全部匹配。 | 已闭环 |
| 建议 2：第二次生成档案 | `data/raw/admission/qwen3-8b@macmini-m6/cbd3b5af/determinism_calls/`、`determinism.json`、冻结提示渲染 | 完整解析 20 份档案，20/20 唯一对应到准入清单的单元，20/20 原始 token 序列摘要匹配首跑摘要；调用内部 token 数组与端点响应逐元素全等，无缺档、重复单元或多余单元。 | 已闭环 |
| 建议 3：描述性结论边界 | 阶段报告 §2.2 跨实验同簇比较段、E3 §4.3(2) | 已改为开发集描述性结果与假说相容，未据此断言内部机制已获证明；正式验证性结论明确留待冻结后 S6/S7 的 80 簇正式集。 | 已闭环 |

### Step 1/2 失败指标复核

阈值：FWER ≤ `0.059747`；联合覆盖率 ≥ `0.940253`；单槽覆盖率 ≥ `0.975`；screen05 ≤ `0.075`。下表列出全部未通过指标；A/B/C 分别对应 `CfgA_all_null_comp`、`CfgB_half_null_comp`、`CfgC_alt_null_comp`，其余指标通过。

| 步骤 | DGP / Cfg | H3 单槽覆盖率失败值 | 联合覆盖率失败值 | FWER 失败值 |
| :--- | :--- | ---: | ---: | ---: |
| Step 1 | DGP1_emp / A | 0.9565 | 0.9245 | — |
| Step 1 | DGP1_emp / B | 0.9590 | 0.9180 | 0.0650 |
| Step 1 | DGP1_emp / C | 0.9685 | 0.9320 | — |
| Step 1 | DGP2_skew / B | — | 0.9390 | — |
| Step 1 | DGP2_skew / C | — | 0.9400 | — |
| Step 2 | DGP1_emp / A | 0.9610 | 0.9320 | — |
| Step 2 | DGP1_emp / B | 0.9650 | 0.9270 | 0.0625 |
| Step 2 | DGP1_emp / C | 0.9705 | 0.9375 | — |

Step 3 保存的 20 格全部通过：FWER 范围 `0.0095–0.0400`，联合覆盖率 `0.9605–0.9925`，最小活跃单槽覆盖率 `0.9815`，最大 screen05 `0.0645`。选择仍为 `selected_step=3`、`selected_family=hybrid_bessel_t_tango_e3`、`demoted_slots=["E3_H3"]`。这是对保存产物的核对，本轮未重新模拟。

## 20 份确定性调用的完整性与关联

每份 JSON 均为 `phase=generation`、`attempt=1`。以其端点响应中保存的提示内容，对照冻结材料渲染出的消息逐项匹配；20 份均唯一对应一个被抽中的单元。此步骤排除了相同简短标签输出造成的摘要多对一歧义。每份提示的 canonical SHA-256 也均与该调用的 `rendered_sha256` 一致。

对每份完整、有序的整数 token 数组，使用项目的 `common.digest` 计算摘要，均与对应 `determinism.json` 的 `original_sha256` 一致；20 项 `match=true` 且无 errors。每份 `result.generated_ids_raw` 与 `result.raw_response.tokens` 逐元素相同，token 数与两个计数字段一致，均为 `eos` 且无截断。

| 调用档案（`.json`） | 对应 id / task / prompt | 原始 token 数 |
| :--- | :--- | ---: |
| `016b53a59fb3464493489d6807c3d7b2` | `INT_PLAN_081/L/CF` | 48 |
| `0e62533140cc432eb0f6a8b990a2b247` | `INT_PLAN_077/M/DAP` | 377 |
| `10bf12bbd6bd46108c2285147fd99e7b` | `NI_OCC_065/P/CF` | 327 |
| `21ed8c4cb0724c30a209cead129f60a5` | `NI_PLAN_036/M/CoT` | 531 |
| `396938b3c6ff4482915f067f4e07c879` | `INT_PLAN_056/P/CF` | 320 |
| `46dc0c58206c4dde88ca47c3b44173ab` | `INT_OCC_048/Ps/Z` | 244 |
| `51207af400594860b95a0362d45b3faf` | `INT_OCC_056/L/DAP` | 2 |
| `7af7a782ab474ff493b1b36210354afc` | `INT_PLAN_081/P/Z` | 298 |
| `868541f2d5904ac0968075515c218bd8` | `NI_PLAN_047/Ps/Z` | 104 |
| `8c67f662ebd448b88f855ead05112261` | `INT_OCC_046/M/DAP` | 515 |
| `954fc435774e4f6cad783894d60231ce` | `INT_PLAN_048/L/DAP` | 2 |
| `971da817d9604f62a1848ec980444158` | `INT_PLAN_078/L/Z` | 2 |
| `9f91c8ceb257474691867a1a24a1e3ca` | `NI_OCC_073/P/CF` | 327 |
| `a6e81a3b7434489aae676e5ca7ba39b2` | `DIAG_POS_077/L/Z` | 2 |
| `b6c1d5323a2c46228a0c49da0ef6f2a2` | `NI_PLAN_085/L/CoT` | 88 |
| `bfa914e3e1a940e2bc82284f6f9aa8db` | `DIAG_NEG_056/L/Z` | 2 |
| `c36312718e8d48958a1eb641d5cb40c0` | `NI_OCC_085/L/CF` | 66 |
| `f92a26cfd7f94576ba8f5d277aa9a250` | `INT_PLAN_084/M/DAP` | 451 |
| `fd9796901b0341e591470271d0fd433d` | `DIAG_POS_064/L/Z` | 2 |
| `ff634aa5a82a4853935d5e5bf25a9859` | `NI_OCC_017/P/CF` | 280 |

**证据边界：** 本轮按任务要求不再解析 2.3 GB dev 账本全文。首跑序列与 `original_sha256` 的绑定沿用第 1 轮全量独立审计，并以本轮相同的 dev 文件 SHA-256 保全；本轮新完成第二次调用档案、提示关联及 token 摘要的核验。因此，“与首跑一致”由未变账本及逐项序列摘要连接证明，不冒称本轮重新加载两次完整数组作直接比较。档案内部两处 token 数组则已直接逐元素比较。本地文件的一致性不构成对历史执行不可伪造的外部认证。

## 受保护文件、既有产物与零泄漏

以实际配置、材料、token 清单和 `host_macos.py` 构造 `Context(..., read_only=True)`，完整重建指纹 `cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3`；与 smoke/dev 两份 `fingerprint.json` 全等。指纹 `files` 的 23 项逐文件 SHA 均匹配，模型配置、采样参数、host 实现、token 清单及渲染材料摘要一致；`verify_sources()` 七项通过。S2 第 4 轮明确公布的九项文件摘要全部匹配，`calibrate_e3.py` 也匹配第 3 轮公布的摘要。第 3 轮中已被后续修订取代的旧代码摘要不作为当前基线。

阶段报告 §4 实际列出 18 项文件 SHA，本轮逐文件核验 `18/18` 匹配。关键不变值如下：

| 文件 | 本轮 SHA-256（与第 1 轮依据一致） |
| :--- | :--- |
| `PLAN-E3.md` | `ec4137b4a280b34977a26d755bd414b81392ec3419f6b9a84e4e6de941f3082b` |
| `data/raw/smoke/qwen3-8b@macmini-m6/cbd3b5af/results.jsonl` | `abf6610293d9efddb5732444a35aaffec3a00bb0adb40313931dbe13275a517e` |
| `data/raw/dev/qwen3-8b@macmini-m6/cbd3b5af/results.jsonl` | `d777f42e6cf04f3851ae4473d077a60a7b60960ba4ccb6e90f060db9e210ce3a` |
| `data/raw/dev/qwen3-8b@macmini-m6/cbd3b5af/analysis.json` | `18245a03a113e8a8f4fdcefac3c9d0b0b7fa00ef9217d0b490b8fd9f13c2effa` |
| `data/raw/calibration_e3.json` | `0719bb94336a2b18e1795aae7767714169ddf94c60502aa542b14454a0a44806` |
| `data/raw/admission/qwen3-8b@macmini-m6/cbd3b5af/determinism.json` | `9d3e8a527a36ca5ed3cf1c3e8457369d1769c3d15868c8826f3ea1be32a4e98d` |

本次待审阶段报告 SHA-256 为 `2084adfe01bef92833149e33ac437db2b4c6247c250e8e29f5f5b5b61f9b7b0a`。对全部既有产物的本轮写入保全以审查开始时的 89 个非 pycache 文件逐文件快照为准；报告交付后再次计算，全部字节不变，唯一新增持久文件为本复核报告。未修改任何 `.py`、方案、材料、既有账本、准入或校准产物。

交付后运行 `F:\conda-envs\llm\python.exe -B -X utf8 validate_materials_e3.py`，退出码 `0`：`100/100 clusters PASS (0 errors); 0 upstream leaks outside data/; negative mutations killed: 15/15`。扫描覆盖全部非 `data/` 文件，无目录或扩展名豁免，包含本报告。本报告仅引用编号、槽位和脱敏统计，编码为纯 UTF-8 LF、无 BOM。

沿用第 1 轮已通过的完整账本摘要、门禁、统计复算、确定性抽样及生产校准契约结果；相应文件 SHA 未变。本轮没有重新运行模型、模拟、账本修复或正式分析。运行指纹与已公布历史摘要的匹配范围，仍不等同于对全部文件另有独立签署的 S2 历史快照。本地 `freeze/` 与 `data/raw/formal/` 均不存在，未检查其他主机或公开仓库状态。

## 阻断项

无。

## 建议项

无。

## 疑问项

无。

## 收尾与局部进度

本次无新增可迁移工具坑，无 skill 规则问题；未开展外部文献查询，未产生新的模型效果或统计方法发现。复核仅关闭既有解释和归档问题，结果保存在本报告；c 不改写待审物、a/d 的知识库、计划或其他角色记忆。

下图沿用 `PLAN-E3.md` 的阶段划分，结合已核验证据标示本轮位置，不更新法定进度源。SVG 已渲染并目视检查。

<svg xmlns="http://www.w3.org/2000/svg" width="880" height="160" viewBox="0 0 880 160" role="img" aria-label="P16.6 E3 round 2 pre-freeze review progress">
  <rect width="880" height="160" fill="#ffffff"/>
  <g font-family="Segoe UI,Arial,sans-serif" text-anchor="middle">
    <text x="440" y="25" font-size="17" fill="#172033">P16.6 / E3: round 2 independent review</text>
    <rect x="20" y="45" width="190" height="62" rx="8" fill="#e6f4eb"/>
    <rect x="235" y="45" width="190" height="62" rx="8" fill="#e6f4eb"/>
    <rect x="450" y="45" width="195" height="62" rx="8" fill="#e6f4eb"/>
    <rect x="670" y="45" width="190" height="62" rx="8" fill="#fff0d8"/>
    <g font-size="16" fill="#172033">
      <text x="115" y="70">S3: verified</text><text x="330" y="70">S4: verified</text>
      <text x="547" y="70">R2: no blockers</text><text x="765" y="70">S5: pending</text>
    </g>
    <g font-size="13" fill="#3d485a">
      <text x="115" y="93">174 / 174</text><text x="330" y="93">20 / 20 calibrated cells</text>
      <text x="547" y="93">B1 + advice 1-3 closed</text><text x="765" y="93">User confirmation</text>
    </g>
    <text x="440" y="139" font-size="14" fill="#3d485a">Next: submit S5 freeze and public preregistration for user confirmation.</text>
  </g>
</svg>

白话三问：我们已确认报告改正、20 份复测档案齐全，原有实验结果保持原样；下一步可把冻结与公开预注册交用户确认；确认并完成 S5 后，才可按冻结方案进入正式集，取得正式验证证据。

## 可提交用户确认进入阶段 S5（冻结与公开预注册）的判定结论

**可以提交。** 第 1 轮 B1 与建议 1–3 均已闭环，本轮没有新增阻断、建议或疑问。S5 的实际冻结和公开预注册仍须用户确认，并在执行时核对公开提交证据及其早于正式运行的时间顺序；本报告只给出独立复核结论，不执行或授权 S5/S6。

**无阻断。**
