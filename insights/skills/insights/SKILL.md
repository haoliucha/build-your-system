---
name: insights
description: Use only when the user explicitly invokes $insights to review how they work across prior local Codex sessions.
---

# Codex /insights

复盘用户在 Codex 中做什么、怎样协作、什么最有效、哪里受阻，以及下一步可直接尝试什么。仅在用户显式输入 `$insights` 时运行；普通“总结”或“复盘”请求不得扫描历史。

本 Skill 以本机 Claude Code 2.1.229 可观察的分析语义为基准，并适配 Codex。Claude 的直接模型调用、长会话完整分块、每会话 facet、七个异构 lens、独立 At-a-Glance 和 best-effort 输出是语义基线；SQLite 恢复、总体进度、隔离执行和事务提交是 Codex 工程增强，不得冒充 Claude 原生实现。

## 默认范围

- `MAX_NEW_SESSIONS=200`，合法范围 0–200；仅用户显式提供时覆盖。
- `LANGUAGE=zh-CN`；仅合法 BCP 47 标签可覆盖。
- 只读 `$CODEX_HOME/sessions/` 与 `archived_sessions/`；只写 `$CODEX_HOME/usage-data/insights/`。
- 排除当前任务、Insights 自分析任务、少于 2 条用户消息或跨度不足 60 秒的任务。
- 语义样本只包含 `primary` 与无来源标记且无 fork 的 `legacy_primary`。`subagent`、`automation` 与非用户来源的 `codex_exec/exec` 只在方法区计数，不作为独立人工协作样本。
- 最近 200 条未缓存合格主会话按 4 个最多 50 条的波次分析。200 是最近样本，不宣称随机统计代表性。
- 分析版本变化使旧 facet 失效；语言变化不使 facet 失效。
- `prepare` 完成时冻结一份脱敏分析材料快照并记录快照时间。运行期间源 JSONL 可以继续追加；当前报告始终基于该快照，变化后的 source fingerprint 只使下一轮缓存失效。

## 分析语义

    确定性清单与全量 meta
      → 长会话分块摘要
      → 每会话 native-facet-v2
      → 确定性全局聚合
      → 7 个专属 lens
      → 独立 At-a-Glance
      → 固定模板 HTML
      → state-last commit

1. 确定性会话统计（meta）：消息、时长、工具名、语言、Token、Git、代码增删行、文件、错误类别、中断、响应时间、Task/MCP/Web、时段及 30 分钟多任务并行。
2. 长会话：用户单条最多 500 字符，助手单条最多 300 字符，工具保留名称；标准化材料超过 30,000 字符时按 25,000 字符连续切块，Luna/low 完整摘要后按顺序拼接。
3. Facet：Terra/medium 只统计用户明确目标与显式反馈，生成固定枚举的 native-facet-v2；字段与判定见 `references/facet-contract.md`。
4. 聚合：确定性统计覆盖全部本次发现的合格主会话 meta；语义统计覆盖已有有效 facet 与本轮成功 facet。叙事材料从全部主会话 facet 中按项目、时间、结果、成功、摩擦与反馈分层选择最多 50 条摘要、20 条多样化摩擦说明和 15 条带次数与日期的重复指令，并明确 remaining。
5. 七 lens：Sol/high 分别生成 `project_areas`、`interaction_style`、`what_works`、`friction_analysis`、`suggestions`、`on_the_horizon`、`fun_ending`，禁止压成通用 claim。
6. At-a-Glance：Sol/high 独立综合四部分。不要插入 Repeat/Contradiction/Evolution、模型自报评分或无限修订循环。

模型失败采用 best-effort：chunk 最终失败使用该块前 2,000 字符并标记降级；facet 失败跳过会话；lens/At-a-Glance 失败省略或显示 concern。锁、Insights state CAS、hash、隐私或事务失败禁止提交，旧报告保持不变。

## 报告

输出 `report.html` 与 `report-YYYYMMDDTHHMMSSZ.html`。默认简体中文，页首用一行显示消息、已分析会话、主会话总数与日期范围；随后是线性四段总览、顶部导航、五项核心统计、七个语义章节、12 类行为图、AGENTS.md 建议、Codex 功能、可复制工作流、未来机会和难忘时刻。单文件静态 HTML 使用约 800px 居中单栏和扁平章节；单一内联 CSS、严格 CSP、零脚本与外部资源、动态文本转义、打印和移动样式。详见 `references/report-contract.md`。

## 执行

先完整读取 `references/protocol-contract.md`。令 `INSIGHTS_SKILL_DIR` 为本文件目录，然后在前台启动确定性 Runner；不要由主 Agent 生成 facet、调度子代理或维持 PTY JSON 协议：

    python3 -u "$INSIGHTS_SKILL_DIR/scripts/runner.py" --max-new-sessions 200 --language zh-CN

发布或升级分析版本时，正式 200 会话运行之前必须依次通过：合成报告结构对比、3 条主会话非提交 Facet 探针、现有主会话缓存的 Lens-only 预览，以及用户对预览的目检确认。预览固定写入 `previews/<version>/`，不得改正式 report/state/manifest/facet。普通用户已确认版本下的 `$insights` 不重复运行这些发布门禁。

开发态正式运行还需要 `release-receipt.json`，其用户确认标记及预览/对比哈希必须匹配；未确认或任一门禁失败时不得启动 200。插件正式发布后普通 `$insights` 不要求开发凭据。

只有用户显式传参时替换 200 或 zh-CN。Runner 默认 Fast，自己启动 6–12 个隔离、只读、Schema 约束的 `codex exec`；主 Agent 只转呈控制台进度和最终结果。不要创建项目内或 `/tmp` 中继文件，不要后台运行，不要为 Runner 或单 Job 设置 timeout/TTL。

Runner 每 60 秒显示心跳，每 5 分钟显示完整仪表盘，始终包含总体百分比、所有阶段、语义覆盖、并发、吞吐、P50/P90 和 ETA。10 分钟无模型事件只告警，不中断。用户主动暂停时立即向前台 Runner 发送中断；Runner 终止在途进程、删除 partial、把 running 恢复 queued，保留 succeeded。

若启动返回 `resume_choice_required`，把未完成 run-id 告知用户并询问恢复还是新建；不得自行选择。恢复使用 `--resume <run-id>`，明确新建使用 `--new`。恢复直接读取 SQLite 中带 hash 的脱敏分析材料快照，不重新扫描活跃 JSONL；快照不兼容、损坏或 Insights state 已被其他运行提交时停止，不伪造恢复。

成功后返回可点击的 `report_path`、归档路径、运行耗时、性能门结果，以及两个恒等式：

    eligible = analyzed + skipped + remaining
    selected = succeeded + skipped

主动计算目标不超过 90 分钟、端到端不超过 120 分钟；超过时运行仍继续且报告可保留，但不得据此发布新版本。失败时给出最后成功阶段与唯一阻断原因。
