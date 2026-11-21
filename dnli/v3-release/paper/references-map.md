# references-map：引用标记 → BibTeX 键 → 核验网址 → 状态

- 日期 2026-10-15，角色 d。对应文件 `references.bib`（35 条）。
- 范围：`intro-related-zh.md` 的全部引用与文末对照表；`methods-zh.md`、`results-zh.md`、`discussion-zh.md`、`abstract-zh.md` 中的引用标记（只有 Rudinger et al., 2020；Zhang et al., 2025；Ross & Pavlick, 2019；Jiang & de Marneffe, 2019，后两处在 discussion 节）。
- 状态：verified = 作者、题目、年份、期刊／会议在权威来源上对上；partially verified = 有一项未能确认（见备注）；not found = 无。本次没有 not found。
- 核验来源：ACL Anthology 的 .bib 记录、arXiv API 与摘要页、Crossref API（DOI）、ICLR 官网、OpenAlex。

## 标记对照表

| 引用标记（草稿原样） | 出处 | BibTeX 键 | 核验网址 | 状态 |
|---|---|---|---|---|
| Rudinger et al. 2020 ／ Rudinger et al., 2020 | intro、methods | `rudinger2020thinking` | https://aclanthology.org/2020.findings-emnlp.418/ | verified |
| 2502.08080 | intro 2.1 | `srikanth2025nli` | https://aclanthology.org/2025.naacl-long.130/ ；https://arxiv.org/abs/2502.08080 | verified |
| Chen et al. 2020 | intro | `chen2020uncertain` | https://aclanthology.org/2020.acl-main.774/ | verified |
| Wang et al. 2025, Always Tell Me The Odds ／ Wang et al. 2025 | intro 1、2.1 | `wang2025always` | https://arxiv.org/abs/2505.01595 | verified（只有 arXiv 预印本，页面未列发表地点） |
| Feng et al. 2025 | intro 2.1 | `feng2025bird` | https://proceedings.iclr.cc/paper_files/paper/2025/hash/19452e14fe6e0a8ac00410f1eebcbded-Abstract-Conference.html ；https://arxiv.org/abs/2404.12494 | verified（ICLR 2025 Oral；无页码） |
| Kamath et al. 2026 | intro | `kamath2026humans` | https://aclanthology.org/2026.tacl-1.93/ ；https://arxiv.org/abs/2602.23546 | verified（TACL 14:2057–2080） |
| Wilie et al. 2024 | intro 2.1 | `wilie2024belief` | https://aclanthology.org/2024.emnlp-main.586/ | verified |
| Vasileiou et al. 2026 | intro 1、2.1 | `vasileiou2026humans` | https://kclpure.kcl.ac.uk/portal/en/publications/3fb5be93-1aa8-4225-b67e-7019f586b65f ；https://api.openalex.org/works/W7202329059 | partially verified（见下） |
| Yuan et al. 2025 | intro | `yuan2025evolvecast` | https://arxiv.org/abs/2509.23936 | verified（仅 arXiv；题目已改，见下） |
| 2507.17951 | intro 2.2 | `imran2025bayes` | https://arxiv.org/abs/2507.17951 ；https://icml.cc/virtual/2025/49148 | verified（ICML 2025 研讨会，非存档） |
| Kim et al. 2025 | intro | `kim2025evidence` | https://aclanthology.org/2025.naacl-long.531/ | verified |
| Chen et al. 2026 | intro 2.2 | `chen2026leap` | https://arxiv.org/abs/2609.01337 | verified（预印本；arXiv 注明 EMNLP 2026 接收，未找到会议论文页） |
| Ross & Pavlick 2019 ／ Ross & Pavlick, 2019 | intro、discussion | `ross2019well` | https://aclanthology.org/D19-1228/ | verified |
| Jiang & de Marneffe 2019 ／ Jiang & de Marneffe, 2019 | intro、discussion | `jiang2019know` | https://aclanthology.org/P19-1412/ | verified（内容问题见下） |
| Basmov et al. 2024 | intro 2.3 | `basmov2024simple` | https://arxiv.org/abs/2305.14785 | verified（仅 arXiv；2024 为 v2 年份） |
| Zhou et al. 2023 | intro | `zhou2023navigating` | https://aclanthology.org/2023.emnlp-main.335/ | verified |
| Belém et al. 2024 | intro | `belem2024perceptions` | https://aclanthology.org/2024.emnlp-main.483/ | verified |
| Du et al. 2026 | intro | `du2026say` | https://aclanthology.org/2026.acl-long.142/ | verified（ACL 2026） |
| Schuster et al. 2026 | intro | `schuster2026whose` | https://aclanthology.org/2026.acl-long.1357/ | verified（ACL 2026；对照表只记 arXiv，已有正式版本） |
| Bajaj & Tiganj 2026 | intro | `bajaj2026trust` | https://arxiv.org/abs/2602.13568 | verified（仅 arXiv） |
| Ashkinaze et al. 2026 | intro | `ashkinaze2026discernment` | https://arxiv.org/abs/2607.19355 | verified（仅 arXiv） |
| Karakaş & Şimşek 2026 | intro | `karakas2026turkish` | https://aclanthology.org/2026.cmcl-1.25/ ；https://arxiv.org/abs/2604.24665 | verified（CMCL 2026；Anthology 姓氏无变音符） |
| Hovland & Weiss 1951 | intro | `hovland1951source` | https://doi.org/10.1086/266350 | verified（页码 635–650，终止页来自二手检索） |
| Pornpitakpan 2004 | intro | `pornpitakpan2004persuasiveness` | https://doi.org/10.1111/j.1559-1816.2004.tb02547.x | verified（Crossref；对照表原记「仅题录」，现已核到 DOI） |
| Harris et al. 2016 | intro | `harris2016appeal` | https://doi.org/10.1111/cogs.12276 | verified（Crossref 在线日期 2015-09，卷期为 40(6)，印刷年 2016） |
| Xiong et al. 2024 | intro | `xiong2024llms` | https://iclr.cc/virtual/2024/poster/18135 ；https://arxiv.org/abs/2306.13063 | verified（ICLR 2024；无页码） |
| Tian et al. 2023 | intro | `tian2023just` | https://aclanthology.org/2023.emnlp-main.330/ | verified |
| Zhang et al. 2025 ／ Zhang et al., 2025 | intro、methods、discussion | `zhang2025verbalized` | https://arxiv.org/abs/2510.01171 | partially verified（发表地点未证实，见下） |
| Wang et al. 2025b | intro 1、2.4 | `wang2025distribute` | https://arxiv.org/abs/2511.14275 | verified（仅 arXiv；题目已改，见下） |
| Wang & Stengel-Eskin 2026 | intro 2.4 | `wang2026dinco` | https://www.iclr.cc/virtual/2026/poster/10007320 ；https://arxiv.org/abs/2509.25532 | verified（ICLR 2026 海报） |
| Meister et al. 2024 | intro 2.4 | `meister2025benchmarking` | https://aclanthology.org/2025.naacl-long.2/ | verified（正式版为 2025，见下） |
| Haran et al. 2010 | intro 2.4 | `haran2010simple` | https://doi.org/10.1017/S1930297500001637 | verified |
| Vul & Pashler 2008 | intro 2.4 | `vul2008crowd` | https://doi.org/10.1111/j.1467-9280.2008.02136.x | verified（对照表原记「经重复研究转引」，现已核到原论文 DOI） |
| Herzog & Hertwig 2009 | intro 2.4 | `herzog2009wisdom` | https://doi.org/10.1111/j.1467-9280.2009.02271.x | verified |
| Litvinova et al. 2020 | intro 2.4 | `litvinova2020inner` | https://doi.org/10.1037/dec0000119 | verified（Decision 7(3):183–211；作者共 5 人，含 Pleskac） |

## 需要作者决定或处理的事项

1. **同名标记**：草稿里的「Wang et al. 2025」（Always Tell Me The Odds，2.1 节与引言）与「Wang et al. 2025b」（Let the Model Distribute Its Doubt，2.4 节）。正式稿要改成 2025a／2025b（natbib／biblatex 会自动处理，但文中手写标记要统一）。另外「Chen et al. 2020」（UNLI）与「Chen et al. 2026」（LEAP）年份不同，不冲突。
2. **以 arXiv 编号当标记的两处**：2.1 节的「2502.08080」应改为 Srikanth & Rudinger 2025（NAACL 2025），2.2 节的「2507.17951」应改为 Imran et al. 2025。
3. **年份要改的标记**：
   - 「Meister et al. 2024」：arXiv 版 2024 年 11 月，正式版为 NAACL 2025（`2025.naacl-long.2`），键用 2025。按「优先正式版」原则，建议文中改为 Meister et al. 2025。
   - 「Basmov et al. 2024」：仅有 arXiv（v1 2023 年 5 月，题目是 ChatGPT and Simple Linguistic Inferences；v2 2024 年 4 月改题）。保留 2024，但引的是 v2。
   - 「Harris et al. 2016」：在线首发 2015 年 9 月，印刷卷期 40(6) 属 2016 年，保留 2016。
4. **题目变动**：Yuan et al. 的 arXiv v3 题目是「Do Language Models Update their Forecasts with New Information?」，v1 题目是「Assessing Large Language Models in Updating Their Forecasts with New Information」；草稿用 EvolveCast 称呼，正文可保留，但参考文献条目用最新题目。Wang et al. 2025b 的 v1 题目是「Don't Miss the Forest for the Trees: In-Depth Confidence Estimation for LLMs via Reasoning over the Answer Space」，现用 v2 题目。
5. **部分核实的条目**
   - Vasileiou et al. 2026：题目、作者、COLM 2026 来自 OpenAlex 与伦敦国王学院研究门户记录；作者 PDF（yeoh-lab 网站）因证书错误没能打开，故题目与 PDF 正文的对应只靠文件名（colm-VasileiouRMY26）与作者姓名首字母相符。第三作者的重音拼写（María Vanina Martínez）来自 OpenAlex，门户记录写作 Martinez。没有页码。
   - Zhang et al. 2025（Verbalized Sampling）：只有 arXiv（v4 2026 年 7 月）。有二手新闻说 ICML 2026 接收，官方页面没查到，所以按预印本引用；若作者想引正式版，需另查 ICML 2026 论文集。
6. **内容层面的小提醒（不影响题录）**
   - 引言 2.3 节写「CommitmentBank 研究说话人承诺在否定、情态……环境下的变化 [Jiang & de Marneffe 2019]」：该文题为「Do You Know That Florence Is Packed with Visitors? Evaluating State-of-the-art Models of Speaker Commitment」，是在 CommitmentBank 上**评测模型**的论文；CommitmentBank 本身是 de Marneffe, Simons & Tonhauser (2019, Sinn und Bedeutung) 的数据集。建议改成「在 CommitmentBank 上评测说话人承诺模型」，或另加数据集的引用（本次没有核查该数据集论文，未收入 bib）。
   - Wilie et al. 2024 的正式题目是「Belief Revision: The Adaptability of Large Language Models Reasoning」，草稿用「Belief-R」称呼其基准，二者对应，无需改。
   - Schuster et al. 2026：对照表只记录 arXiv，实际已在 ACL 2026 发表（页码 29430–29459）；搜索摘要提示 arXiv v2 与 ACL 版数字不同（模型数、缓解幅度），草稿若引用具体数字需核对正式版（草稿未引数字）。
   - Ashkinaze et al. 2026：arXiv 编号 2607.19355，但 arXiv API 给出的首次提交日期是 2026-05-22，编号与日期不一致；年份 2026 不受影响。
7. **未收入的作品**：草稿正文提到 SNLI、δ-SNLI 数据集、COPA／ProbCOPA 数据集，但没有对 SNLI（Bowman et al. 2015）单独加引用标记，所以未收入。若正式稿要引 SNLI 或 CommitmentBank，需补。方法节提到的 GitHub 仓库（rudinger/defeasible-nli）不是文献引用。
8. **没有 DOI 的会议论文**：ICLR 条目（Xiong 2024、Feng 2025、Wang & Stengel-Eskin 2026）没有 DOI 与页码，bib 里用 ICLR 官网网址代替。


## a 补充（2026-10-15）

| [Bowman et al. 2015] | bowman2015large | https://aclanthology.org/D15-1075/ | 待核 |
| [de Marneffe et al. 2019] | demarneffe2019commitmentbank | https://doi.org/10.18148/sub/2019.v23i2.601 | 待核 |
| [Steyvers et al. 2025] | steyvers2025know | https://doi.org/10.1038/s42256-024-00976-7 | 已核（NMI 7(2):221-231, arXiv:2401.13835） |
| [Kalai et al. 2025] | kalai2025hallucinate | https://arxiv.org/abs/2509.04664 | 已核（arXiv:2509.04664） |

