# PLAN-addendum: LHF supplementary local reanalysis

日期：2026-11-08。执行范围：LHF-NLP-1a/1b/2/3 与 LHF-PSYCH-1..5。

所有分析仅基于既有冷冻产物，零 API 调用，不改变预注册主检定、刺激、提示、解析器、统计代码或任何 analysis_freeze 指纹。六个新增脚本与三个独立输出目录构成独立补充层。D-NLI 四个 cohort 严格分开；psych3 正式、参考开发、OLMo-2 探索开发、Stage 2C 单列。

新补充检验为双尾探索性检验；95% 百分位 cluster bootstrap B=2000、seed=20261108（按图片/题目聚类有放回抽样，保留簇内全部观察），未作额外多重比较校正。原有正式端点和缺失保护保持其原始定义、区间与多重比较地位。HC3 使用包含全部题目/运行虚拟变量的完整设计杠杆率、残差自由度和双尾 t 检验；缺失、低样本、常数预测量或秩亏均显式报告不可估。

候选权重为模型在同次调用内自报的权重，不是序列概率；Top-1 平手主读数取并列候选均值，D-NLI 另列首个平手敏感度。Consistency 的摘要差/倍数比为描述性计算，保留既有记录级配对推论作为独立证据。禁止预设改善结论。

执行：PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/lhf_deps OPENBLAS_NUM_THREADS=1 python3 -B -X utf8 <新增脚本>。NumPy/SciPy 隔离安装于 /tmp/lhf_deps，不更改仓库依赖。默认拒绝输出碰撞（exit 2），只有显式 --overwrite-lhf 允许覆盖本次补充产物；测试在临时目录验证碰撞不修改现有文件。
