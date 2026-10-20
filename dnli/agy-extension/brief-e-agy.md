# 任务书：经 agy 调用更多受测模型的模块（δ-NLI 补强版；给 e，经 codex）

- 实例：`#connecting-dots`；计划树 P7.8；日期 2026-10-13；写者 a。
- 依据：用户 2026-10-13：agy 走 Google 账号订阅额度；各模型额度互相独立、限流较严，可以分几个礼拜慢慢跑完。可选模型（`agy models`，agy 1.3.3）：`gemini-3.8-flash-{low,medium,high}`、`claude-opus-5-5-{low,medium,high}`、`claude-sonnet-5-5-{low,medium,high}`、`gpt-oss-120b-medium`。
- 已知的 agy 行为：`personas/architect/dispatch-agy.md`（1.3.3 实测：`search_web` 在无头模式**不用授权就能用**；名单外的 `read_url` 会被自动拒绝且整轮结束、stdout 可能为空而退出码仍为 0；stream-json 的工具步骤带名称、参数、状态；正文在最后的 `result.response`；可从 stdin 用 `--input-format stream-json` 送提示）；派发脚本 `tools/agy_dispatch.py` 里有可参考的 stream-json 解析。
- 主实验的做法：`connecting-dots/dnli/`（PLAN v0.7.1、`run.py`、`codex_subject.py`、`parse.py`、`prompts.py`、`analysis.py`、`analyse.py`）。

## 最重要的规矩

1. **`connecting-dots/dnli/` 一个字都不能改。** 主实验的正式运行与分析冻结绑定这些文件的哈希。补强版放在新目录 `connecting-dots/dnli-agy/`：需要的代码从 `dnli/` **复制**过来再改（文件头注明来源与改动），题目清单与题面**只读引用** `dnli/split.json`、`dnli/raw/items_text.json`，并在指纹里记它们的哈希。
2. **本轮不发任何受测调用，也不发任何 agy 调用**（`agy --help`、`agy models` 这类不调模型的命令可以）。全部测试用替身 agy（一个按设定输出 stream-json 的脚本）。真实探针另行由 a 批准。
3. 不改 `~/.gemini` 下任何文件（包括允许名单 `settings.json`，那只由用户改）；不改 `~/.codex`；不用 `--dangerously-skip-permissions`；不提交 git；删 `__pycache__`；中文文件用 `python -X utf8` 读；测试逐模块用 `F:\conda-envs\llm\python.exe -X utf8 -B -m unittest <模块>`。
4. PLAN 或本任务书没写清楚、必须做决定的地方，停下写进回报。

## 要做的事

1. **调用适配器 `agy_subject.py`**：每次调用开一个全新的 agy 对话（不用 `--continue`、`--conversation`），工作目录是每次新建的空临时目录；`--model <模型名>`、`--print`、`--output-format stream-json`、`--sandbox`；提示由 stdin 送入。提示文字与主实验**逐字相同**（直接问法、多估计问法；含末行 `Do not use any tools; answer directly.`）。保存原始 stream-json 与 stderr。
2. **最终纳入规则**（仿 `dnli/codex_subject.py` 的 `final_inclusion`，写清每一条）：
   - **工具使用 → 污染**：只要 stream-json 出现任何工具步骤（`search_web`、`read_url`、命令、文件读写……，不论成败），这次尝试作废并重采；同一 unit 连续污染达上限（定为 3）就停下该模型的流程（会话不作废）。
   - 恰好一个最终回答、`result` 事件存在且成功、没有截断；否则按类型判失败或重采。
   - **限流**：识别 agy 的限流／额度讯息（429、RESOURCE_EXHAUSTED、quota、rate limit 等，具体字样写成可配置的清单，探针后再补）→ 判 `rate_limited`：**不算失败、不算缺失、不消耗重采次数**；按退避等待（起始 5 分钟、倍增、上限 60 分钟），连续限流超过一个可配置的时长（默认 6 小时）就让该模型的流程休眠到次日 00:10 再试。
   - 断线、超时：作废重采，规则同主实验的断线处理思路（连续达上限才停、会话不作废）。
   - 每次调用记下：日期时间、agy 版本、stream-json 里回报的模型名称与任何版本资讯、耗时、token（若有）。
3. **跑题 `run_agy.py`**：
   - 配置名形如 `agy:gemini-3.8-flash-low`；可同时开多个模型的流程（每个模型一个进程，彼此独立），每个模型内一次一个 unit。
   - 调度、续跑、会话登记、单一写入沿用主实验的做法；**能跨日续跑、电脑重开机后接着跑**（结果逐条追加，重跑时跳过已完成的 unit）。
   - 开发集与正式集的计划集合与主实验相同（开发 30 对；正式集先跑 block A 的 120 对，是否跑 block B 由 a 之后决定，做成参数）。
   - 每天在日志里写一行进度（每个模型已完成数、今天被限流的次数与总等待时间、回报的模型名称是否和之前不同）。**回报的模型名称一旦改变就停下该模型的流程**，等 a 判定（服务端更新的警讯）。
4. **解析与分析**：解析直接用 `dnli/parse.py` 的 v2 规则（复制，不改规则）；分析复制 `dnli/analysis.py`、`analyse.py`，配置清单换成 agy 的模型，其余假设、侧、最小有意义效应、bootstrap、Holm、缺失保护、台词敏感度分析与主实验相同。另加一个描述项：**同一模型不同推理档位**（如 Gemini Flash low 对 high）在 H1、H2、H4a、H4b 上的差，只作描述，不进 Holm。
5. **启动脚本 `run_agy.sh`**：每个模型一个后台流程；写日志；适合用 PowerShell `Start-Process` 脱离会话启动（参考 `dnli/raw/relaunch_formal.sh` 的做法）。若要用 Windows 工作排程器做开机自启，只写好说明与命令，**不要建立排程**（那是持久设定，须用户同意）。
6. **测试**（全部用替身 agy）：
   - 正常回答 → 纳入；
   - 出现 `search_web`／`read_url` 工具步骤 → 污染重采，连续 3 次停下；
   - 限流讯息 → 等待（测试里把时间缩短）、不计缺失、不消耗重采次数；连续超时长 → 休眠到次日；
   - 回报的模型名称改变 → 停下；
   - stdout 为空但退出码 0（被拒的情形）→ 不纳入；
   - 续跑跳过已完成 unit；多个模型流程同时跑时各自的结果文件互不干扰；
   - 提示与主实验逐字相同（对 `dnli/prompts.py` 渲染结果比对哈希）。
7. **记录**：`connecting-dots/dnli-agy/README.md`：设计、与主实验的异同、纳入规则、限流策略、跨日续跑与开机后怎么接、已知限制（服务端更新、外壳差异、工具不可完全关闭）、需要的真实探针清单（a 批准后才做：每个模型 3–5 次中性提示，记下真实的 stream-json 格式、模型名称栏位、限流讯息字样）。

## 回报

最后的回复用中文写给 a：README 的要点、测试清单与逐模块结果、需要 a 决定或需要真实探针确认的事项。

## a 的判定（2026-10-13，回应 `report-e-agy.md`）

采用 e 建议的**每个完成 unit 一个独立、已收尾的检查点会话**：
- 每个模型一个进程、一次一个 unit、单一写入；先存尝试原始记录，再写结果，核对完成后原子写入该 unit 的会话登记（收尾）。重启后跳过已登记且收尾核对通过的 unit，只重做崩溃时未收尾的那一个。分析只纳入已收尾、指纹匹配、未失效的检查点会话。
- **补一条保护**（取代主实验「检查失效作废整个会话」的作用）：每个 unit 开始前记录环境快照——agy 版本、`settings.json` 允许名单的哈希（只读取哈希，不改文件）、回报的模型名称；与该模型流程的第一个快照比较，任何一项改变就停下该模型的流程，并在日志写明从哪个 unit 起改变，由 a 判定该时间点之后的 unit 是否作废。检查失效（完整性异常、工具使用之外的可疑情形）只作废该 unit 并停下该模型的流程。
- 在 README 里写清这条规则与主实验的差别及理由（长时间、跨日、限流下运行，整段会话作废代价过高；环境快照比较承担原本的保护作用）。

继续实现第 1–7 项。

## a 对 c 第一轮审查的判定（2026-10-13；审查全文 `review-agy-codex-r1.md`）

照 c 的三项阻断与建议修改，全部用替身测试，不发真实调用：

1. **B1 工具识别改成白名单**：stream-json 里只允许已知、确定无副作用的步骤类型（使用者输入、模型回答／推理等；清单写在 `configs.py`，探针后再补）；**任何未知步骤类型、任何带工具名称的步骤（不论字段名是 tool、tool_call 或其他）**都判污染。`result.denied_actions` 非空也判污染。补 c 的两个反例为测试（`step_type="tool_call", name="search_web"`；SUCCESS result 带非空 `denied_actions`）。
2. **B2 限流只看可信来源**：限流只从 stderr 的诊断行与 stream-json 的 error 类事件判断，**不扫描回答正文与 token 数字**；字样用精确模式（如独立的 `429`、`RESOURCE_EXHAUSTED`、明确的 rate limit／quota exceeded 讯息），清单在 `configs.py`、启动时校验为非空字符串清单。**有 SUCCESS result 且恰好一个最终回答时一律不判限流**；完整性异常优先于限流，不被限流豁免。补 c 的反例为测试（正常回答带 `input_tokens=1429`；正文含 quota；未知事件含 quota）。另外，同一 unit 连续判限流超过可配置的总时长（默认 3 天）就停下该模型的流程并记录，避免把真正的失败当限流无限等下去。
3. **B3 启动时的完整性失效要持久登记**：`valid_records()` 等启动检查失败时，把具体的失效 unit、原因、时间写进会话登记（标 invalid）与停止状态文件，之后重启不得绕过；只有 a 手动清除停止状态才能续跑（清除方式写进 README）。补测试：异常字节恢复后重启仍停下。
4. **建议**：同一模型只允许一个进程（加锁文件，启动时检查，过期锁的处理写清楚）并补双进程测试；预算报告分开「限流等待时间」与「真正的重采次数」。
5. `report-e-agy-implementation.md` 加一节记录本轮修改与逐模块测试结果。

## a 对 c 第二轮复核的判定（2026-10-13；全文 `review-agy-codex-r2.md`）

B2、B3、进程锁已通过。修 B1 的剩余漏洞：
- 工具检查改为**递归**：对每个 stream-json 事件的整个 JSON 树（所有层级的 dict 与 list）检查；任何一层出现 `step_type`（或同类的类型字段）不在白名单、或出现任何工具迹象（工具名称字段、command、url、query、function、action 等，以及值为已知工具名的字段），都判污染。白名单步骤内部也一样递归检查。
- 无法确认的嵌套结构（白名单步骤里出现未在 `configs.py` 登记的子结构类型）一律判污染（fail closed），不判 ok。
- 补 c 的两个变体为测试：外层 `step_type="response"`、`message` 内嵌 `{"step_type":"tool_call","command":"curl https://example.com","status":"SUCCESS"}`；内嵌未知步骤类型。都必须判污染。
- `report-e-agy-implementation.md` 追加一节；逐模块测试结果。
