# agy 探针结果（a，2026-10-14）

- 原定 10-13 00:00 由一次性后台启动器自动跑；电脑 21:49 重启（Windows 更新前后），启动器被结束，没跑。
- 用户同意改为 10-14 早上跑。08:27 首跑：第 1 次调用后删除临时目录遇 WinError 32，崩溃且原始输出未落盘 →
  修正（`ec53ce7`：先落盘再删、退避重试、失败只记录）→ 08:33–08:39 重跑，16 次全部完成，每次约 17–29 秒（含两次 `--version` 快照）。
- 只用自编中性提示（17+25；干燥街道／早上下过雨，直接与多估计格式；第 4 题要求用网络搜索查日期）。结果不进任何分析。

## 观察

| | gpt-oss-120b-medium | claude-sonnet-5-5-medium | gemini-3.8-flash-low | gemini-3.8-flash-high |
|---|---|---|---|---|
| 第 1–3 题工具步骤 | 无 | 无 | 无 | 无 |
| 第 4 题 | search_web | search_web | search_web | search_web |
| 直接问法解析（v2） | 20%（加粗 `**Probability: 20%**`，成功） | 12% | 20% | 20% |
| 多估计解析（v2） | **失败**：U+202F 窄空格 | 14.05 | 19.75 | 14.8 |
| thinking_tokens（第 2 题） | 0 | 0 | 0 | 1589 |
| 输入 token（含缓存） | 约 2.2 万 | 约 3.9 万 | 约 2.5 万 | 约 2.5 万 |
| stderr ／ error 事件 ／ 限流 | 空／无／无 | 同 | 同 | 同 |

1. **格式**：事件只有 `init`、`step_update`、`result`；步骤类型 `user_input`、`agent_response`、`tool`。`init.model` 就是请求的模型名，没有更细的版本号。
2. **原规则误判**：16 次全判污染。原因是 `init.tools`（60 个可用工具的清单）被当成使用，且白名单没有 `agent_response` 与 `text_delta` 等实际字段。已交 e 修（`brief-e-agy-probe-fixes.md`）。修后用 16 个原始流当夹具：第 1–3 题应 ok，第 4 题应 contaminated。
3. **`--sandbox` 不挡网络搜索**：第 4 题四个模型都直接用了 search_web，没有请求许可。主实验的提示有「Do not use any tools; answer directly.」，第 2、3 题都遵守了。用了工具就作废重采；连续 3 次就停。
4. **受测者是「agy 代理外壳里的模型」**：每次调用都带约 2–4 万 token 的外壳系统提示与 60 个工具定义，我们控制不了。这与 codex（同样是代理外壳）类似，但与本地模型（只有我们的提示）不同。论文须写明。
5. **Unicode 空白**：gpt-oss 在多估计格式里用了 U+202F。决定（a）：只在 agy 扩展里，解析前把 Unicode Zs 空白换成 ASCII 空格；`parse.py` 不改；同时记录原文能否解析，供报告。这是看到中性探针后、看任何实验题之前定下的格式规则。
6. 没有观察到限流；限流字样仍是事先定的通用规则，无法用真实讯息核对。第一晚要盯日志。

## 规模估计

每模型约 1700 个 unit（开发 300 ＋ 正式 block A 1400，同 codex），每次约 22 秒 → 不限流时约 10.4 小时，即每模型 1.3 晚左右；四个模型约 6 晚。实际取决于限流。

## c 第三轮（`review-agy-codex-r3.md`）

无阻断。已知边界：Unicode 空白规范化只替换字符，但可能让原本认不出的一组 Estimate 1–5 成为「末组」，因而改变最终解析选择；以规范化结果为准，报告时同列 `parse_raw_ok`。

## 改用无工具自定义 agent 之后（09:33–09:38 重跑，`raw/probe/`；默认外壳那次移到 `raw/probe_default_harness_0833/`）

用户提出想关掉搜索。settings 没有对应的键，改用工作区自定义 agent（`agent/dnli-subject.md`，`--agent dnli-subject`）。4 个模型 × 5 题，20 次全部 `ok`，没有任何工具步骤（第 4 题要求上网查日期，也都直接作答）。

| | gpt-oss-120b-medium | claude-sonnet-5-5-medium | gemini-3.8-flash-low | gemini-3.8-flash-high |
|---|---|---|---|---|
| 每次耗时 | 12–15 秒 | 11–13 秒 | 10–17 秒 | 11–22 秒 |
| 输入 token（第 1 题，含外壳） | 约 1.4 千 | 约 2.9 千 | 约 1.7 千 | 约 1.7 千 |
| 直接问法 | 15%（U+202F，原文也能解析） | 10% | 15% | 15% |
| 多估计 | 25.5（U+202F，原文也能解析） | 11.3 | 24.0 | 22.5 |
| 自述可用工具（第 5 题） | 5 个 | 5 个 | 5 个 | 5 个 |

四个模型自述的工具清单一致：gemini-api 插件的两个文档检索工具（`mcp_gemini-api_gemini-api-docs_gemini_search_docs`、`…_gemini_get_doc`），以及 `list_resources`、`read_resource`、`manage_task`。没有 search_web、浏览器或命令。若被调用，仍判污染重采。

这次探针同时显示外壳提示从约 2.5 万 token 降到 1–3 千：受测者更接近「只看到我们的提示」。agent 的正文只有一句 "Answer the user's question directly."，论文须写明。

c 第四轮（`review-agy-codex-r4.md`）找到 2 个阻断项：可以绕过 init 检查；同一个工作目录被多个进程共用时，清理可能删到别人的目录。已交 e 修。

按每次约 15 秒估算，每个模型约 1700 次调用约 7 小时，不限流时差不多一晚跑完一个模型。

最终代码（de0327b）上用 gemini-3.8-flash-low 实跑 5 题复验（`raw/probe_final_check/`）：5/5 `ok`，临时目录与会话子目录都已清掉。

## agy 自动更新的处理（用户 2026-10-14 决定）

10-14 傍晚 agy 在一次调用中途自动从 1.3.4 更新到 1.3.5（s 派发的第一次尝试因此被判 `environment_changed_during_call`）。今晚的夜间队列在第一次调用时才建立环境基准，所以以 1.3.5 为准。之后若再自动更新，照现行规则：正在跑的模型判环境改变、停下、标「待检查」，等 a 看过再解除。a 提了「跨夜更新照常继续、只记版本、论文按版本分层」的选项，用户答「延后一晚无所谓」，所以**维持更新就停**。


## 2026-10-15：新出现的 `step_type: "unknown"`（a）

- 现象：s 题目轮（11:0x）三次调用都在 step 1 出现 `{"step_type":"unknown","state":"DONE","duration_seconds":0}`，harness 依规则判 `contaminated`（`tool_step`）。
- 探针（`raw/probe_unknown_1122/`、`raw/probe_unknown_other/`，trivial 加法题）：
  - T1 自定义 agent、默认 workroot（本会话 LOCALAPPDATA 被 MSIX 虚拟化到 `Packages\Claude_…\LocalCache`）：有 unknown。
  - T2 自定义 agent、workroot 移到 `<LOCAL_PATH>`（非虚拟化）：有 unknown。
  - T3 不用自定义 agent：gemini-3.8-flash-low、gpt-oss-120b-medium、claude-sonnet-5-5-medium 都有 unknown；gpt-oss 另外真的调用了 `view_file`，读的是 `~/.gemini/config/plugins/data-agent-kit-plugin/skills/dak-setup/SKILL.md`。
- agy 版本仍为 1.3.5；昨天的 fixtures 没有 unknown。`~/.gemini/config/plugins/` 在 **2026-10-14 22:43–22:45** 新增 `data-agent-kit-plugin` 与 `gemini-api` 两个插件，`config.json` 同时修改。时间与现象出现相符，推测 unknown 步骤与新插件（技能载入）有关；尚未证实。
- 处置：harness 规则不放宽。`~/.gemini` 由用户自己改；请用户确认这两个插件的来源，停用后 a 重跑同一探针。
- **11:4x 复测（用户停用两个插件后）**：T2（自定义 agent）`ok`，10 秒，步骤只有 user_input、agent_response；T3（不用自定义 agent）也没有 unknown。**证实 unknown 步骤来自新插件**，检查规则不需改。今晚夜间队列照常。
- 后续建议（harness 改动，须送 c）：环境快照目前只记 `antigravity-cli/settings.json`、agent 与版本，没有记插件状态（`~/.gemini/config/config.json` 与 plugins 目录）；建议把它们的哈希加入快照，插件一变就停下，而不是靠逐次作废来发现。

## 2026-10-16 下午：agy 1.4.0、锁定版本、24 小时运行（a）

- 14:19 agy 自动更新 1.3.5 → 1.4.0；14:26 在 a 的会话里短跑，四个模型都因 `environment_changed` 停下（正确）。另有 `temporary cleanup path outside expected parent`：a 的会话把 LOCALAPPDATA 映射到 Claude 应用的套件目录，路径解析不一致；由工作排程启动不会出现。**以后不要从 a 的会话直接跑队列**，用 `Start-ScheduledTask`。
- 关自动更新：环境变量 `AGY_CLI_DISABLE_AUTO_UPDATE=true`（值 `1` 无效；log 见 `auto_updater.go:247`）。已加进 `night_queue.ps1`。
- 1.4.0 探针（`raw/probe_v140/`，20 次）：全部 `ok`，步骤类型与栏位路径和旧探针完全相同，没有 unknown 步骤。
- 新实验边界：1.3.5 下的 369 个开发 unit 连同 run_meta、尝试档封存到 `raw/archive_agy-1.3.5_20261016/`，不进分析；`queue_state.json` 四个模型重设为 dev、0，记一笔 `boundaries`。
- 依用户「直接 24 小时接着跑」：工作排程 `DNLI-agy-night-queue` 的参数改为 `-Deadline 23:55`，执行时间上限由 8 小时 20 分改为 23 小时 59 分；15:12 用 `Start-ScheduledTask` 立刻启动（本次实例仍沿用旧上限，约 23:30 会被结束，00:00 再起）。

## 2026-10-18：Google 内容安全过滤造成的阻挡（a）

- flash-low 正式集的 `3730011701.jpg#0r1n|stated|S|multi|r0`（小女孩坐在女士脚边；加强句「女士用手机拍这个女孩」）连续三次被 Google 内容安全过滤挡下：串流出现 `error_message` 步骤、result.error 为 "Your previous response was blocked by content safety filters…"。harness 把 error_message 当成工具步骤，判 contaminated，三次后停止。截至 19:1x，flash-low 共有 6 个 unit 被挡过，其余重试都通过。
- 用户决定：采 **(a) 记为缺失**（厂商阻挡，非随机缺失），以人工登记＋补遗处理，不动指纹文件；全部跑完后一次统计各模型被挡的 unit，再定细节并送 c。

## 2026-10-19：别的专案暂改全局权限 → environment_changed；排程改回夜间

- 09:23:45 skills-hub（`#hub`）的 agy 派发在 `~/.gemini/antigravity-cli/settings.json` 的 `permissions.allow` 暂时加了两条 `command(python tasks/WF-T009/...)`，flash-high 在 09:30 下一个单元开跑前的快照比对到 permissions 哈希改变而停下（单元未调用，无数据受影响）。去掉这两条后哈希恰回到基线。
- 用户决定：agy 实验只在 00:00–08:00 跑；先快照设定。排程改为 00:00 起每 30 分钟、持续 7h40m、`-Deadline 07:55`、ExecutionTimeLimit PT8H30M（改前定义与 settings 快照在主目录 `raw/review_backup_20261019/`）。
- 同日 09:04 另有一次结果档 Errno 13，可能是 a 用 grep 扫根目录 `*.jsonl` 撞到附加写入；以后队列在跑时不直接读结果档。
