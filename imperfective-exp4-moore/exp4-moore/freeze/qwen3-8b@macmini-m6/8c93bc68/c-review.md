**已核实事实**

本次审查全程只读：未修改文件、未执行 git 写操作、未启动子代理、未读取 `~/.kaggle`，未执行冻结或正式运行。Python 核验均使用指定解释器及 `PYTHONUTF8=1`、`-X utf8 -B`；文本按 UTF-8 读取。

1. **指纹、代码与材料完整性通过。**
   - 报告 §4 所列 **22/22 项 SHA-256 全部匹配**，审查结束时复核仍一致。
   - 以只读 `Context` 重建的完整指纹为：
     `8c93bc6870a1a00500c3e91c7fd842a100e7d573c33c965963c6ccddec8dce2d`。
   - `validate_materials_e4.py` 实测 **100/100 簇通过、零错误，17/17 负向突变拦截**；另核验提示词解析／协议兼容性 **13/13 通过**。
   - 两份校准 JSON 逐字节相同。

2. **S3 冒烟与探针通过。**
   - 从原始账本复算门禁，与保存的 `gate.json` 全字段一致：**174/174 可用，missing=0，first_attempt_missing=0，truncated=0**。
   - 诊断 `P/Z` 正／负均值为 **100.0%／0.0%**，`status='pass'`。
   - `s1_review`、`s2_acceptance` 及 `verify_vocab/probs/greedy` 均通过准入验证，绑定当前指纹。

3. **S4 开发集与确定性重跑通过。**
   - 从账本复算门禁并核验会话、单元唯一性、计划绑定及账本 digest：**1160/1160 执行，1157/1160 可用**。
   - 仅三个指定 `M/Z` 单元为 `missing_format`；该条件首次及最终可用率均为 **77/80=96.25%**。总可用率 **99.7414%**、总缺失率 **0.2586%**、截断率 **0%**，全部达标。
   - 诊断全集为 **99.62%／0.0%**；D1–D4 分别为 **99.90%／0%、99.80%／0%、99.78%／0%、99.00%／0%**，各领域均达标。
   - `determinism.json` 准入验证通过；**20/20 match=true、errors=[]**。20 份调用档案与报告表逐一对应，原始 token 序列、digest、token 数、提示 token 序列及渲染摘要均匹配。
   - **实际确定性抽样种子是 `2026110692`**，存在下述非阻断文档误记。

4. **开发集统计分析与证据边界通过。**
   - 使用原始账本重建分析，全部 **20 个统计顶层字段**与 `analysis.json` 对象全等。
   - 两套候选家族共 **8 行**的点估计、98.75% CI、单侧原始 p、Holm 校正 p，均与报告 §2.3 在所报精度下一致。
   - H1–H4 点估计界分别为 **[28.95,28.95]、[-0.55,14.45]、[37,37]、[0.95,0.95]**；完整簇数为 **20、17、20、20**。H2 保留三处缺失的最不利界，没有删除缺失簇后替代主结果。
   - 报告明确声明开发集仅提供描述性／开发性证据；当前“显著”结果不能替代独立正式集确认。
   - 开发集 JSON 保留校准前的 `pct` 主家族命名；报告按家族名称正确对应数值，正式集代码则读取冻结校准锁，未发现方法错配。

5. **20 格校准与确定性选择通过。**
   - 已调用 `calibrate_e4.validate_calibration_artifact`，以真实账本重算的 SHA、digest、run_id 和完整簇数作为预期绑定，**生产级验证通过，production_eligible=True**。
   - 完整簇数 **20/17/20/20**、三连续槽共同完整簇数 **17**，满足准入要求。
   - Step 1 为 **19/20**；唯一失败是第 0 格联合覆盖率 **0.9395 < 0.940253**。
   - Step 2 为 **20/20**；FWER 范围 **0.0075–0.0505**，联合覆盖率 **0.9500–0.9895**，最小单项覆盖率 **0.9820**，`max_screen05` 范围 **0.0205–0.0595**，全部符合阈值。
   - 确认锁定 **selected_step=2、selected_family='hybrid_bessel_t_tango_e4'、demoted_slots=[]**；报告的完整 20 格对照表亦逐格匹配。

6. **阶段边界通过。**
   - 审查开始及结束均确认 **`freeze/` 与 `data/raw/formal/` 不存在**。当前产物状态符合停在 S5 前的要求。

**阻断**

无。

**建议**

订正确定性抽样种子的两处执行记录：[报告 §2.2](/Users/autojmac/ClaudeProjects/research-imperfective/connecting-dots/imperfective/exp4-moore/report-s3-s4-autonomous-e4.md:57) 与 [方案 §7](/Users/autojmac/ClaudeProjects/research-imperfective/connecting-dots/imperfective/exp4-moore/PLAN-E4.md:309) 均写为 `2026110691`；[锁定代码](/Users/autojmac/ClaudeProjects/research-imperfective/connecting-dots/imperfective/exp4-moore/admission.py:11)及实际抽样清单一致使用 `2026110692`。这是文档笔误，不影响已验证的确定性结果；订正方案后应同步更新报告中的方案 SHA-256。本次未修改文件。

**疑问**

无。

**总体判定**

**无阻断。可以提交用户确认进入 S5 冻结与公开预注册。**建议在实际冻结前完成上述文档订正；本审查不代替用户确认，亦未执行 S5 或 S6。