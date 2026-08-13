---
name: insights
description: Use only when the user explicitly invokes $insights to review how they work across prior local Codex sessions.
---

# Codex /insights

复盘用户在 Codex 中做什么、怎样协作、什么最有效、哪里受阻，以及下一步可直接尝试什么。入口必须由用户显式输入 $insights；普通“总结”或“复盘”请求不得触发历史扫描。

本 Skill 以本机 Claude Code 2.1.228 的可观察 /insights 语义为基准，适配 Codex 的 JSONL、AGENTS.md 和可用功能。不要把适配或安全护栏反向宣称为 Claude 产品实现。

## 语义来源边界

- **Claude 可观察语义**：标准化会话、长会话分块摘要、native-facet-v1 核心字段、确定性聚合、七个异构 lens、独立 At-a-Glance 和固定报告信息架构。
- **Codex 表面适配**：读取 Codex JSONL；统计 Task/MCP/Web；facet 增加 user_instructions_to_codex 与 evidence_anchors；建议映射为 AGENTS.md additions、Codex features 和 usage patterns。
- **Codex 安全增强**：输入脱敏、安全项目标签、opaque key/source fingerprint、版本化缓存、长驻 helper-owned run、严格静态 HTML、锁/CAS/staging/备份/回滚/state-last 和事务提交。这些不是新的洞察阶段。详见 references/privacy-contract.md。

## 参数与范围

- MAX_NEW_SESSIONS 默认 200，合法范围 0–200；可用 $insights MAX_NEW_SESSIONS=10 小范围运行。官方文档承诺最多分析 200 个此前未分析会话；本机 Claude Code 2.1.228 可观察实现每轮最多新建 50 个 facet。Codex 版采用官方 200 上限，并把模型 job 分成每批最多 50 个。`new` 指当前没有“版本匹配、source fingerprint 匹配且缓存文件有效”的 facet。先过滤有效会话，再按 `updated_at` 从新到旧、opaque session key 降序打破平局，只从未缓存队列选前 N 条。
- LANGUAGE=zh-CN；只有用户显式提供合法 BCP 47 标签时覆盖。helper 把该语言写入所有本次模型 prompt 和报告；语言变化不使已缓存 facet 失效。
- 只读 $CODEX_HOME/sessions/ 与 archived_sessions/；只写 $CODEX_HOME/usage-data/insights/。
- 排除当前任务、Insights 自分析任务、少于 2 条用户消息或跨度不足 60 秒的任务。
- helper 保证每次 next_jobs 最多返回 50 个 job：chunk 和 facet 分批为 50，lens 为 7，At-a-Glance 为 1。调用方不传 limit，也不自行扩批。

## 分析逻辑

    本机会话
      → 确定性会话统计
      → 长会话分块摘要
      → 每会话 native-facet-v1
      → 确定性全局聚合
      → 7 个专属 lens
      → 独立 At-a-Glance
      → 固定模板 report.html

1. **确定性会话统计**：消息、时长、工具名、语言、Token、Git commit/push、代码增删行、文件、错误类别、中断、响应时间、Task/MCP/Web 使用、消息时段和 30 分钟多任务并行。
2. **长会话**：用户文本每条最多 500 字符、助手文本最多 300 字符，工具只保留名称。标准化文本超过 30,000 字符时固定按 25,000 字符连续切块；每块独立总结，按原顺序拼接后再提取 facet，不得漏尾部。
3. **每会话 facet**：只计算用户明确提出的目标，只依据显式反馈推断满意度；输出目标计数、结果、满意度计数、claude_helpfulness、会话类型、摩擦计数与说明、主要成功类型和摘要。Codex 扩展记录重复用户指令与短事件锚点。详见 references/facet-contract.md。
4. **全局聚合**：消息、工具、代码行等确定性统计覆盖当前发现的全部合格 meta；目标、结果、摩擦等语义统计只覆盖已有 facet 的缓存会话与本轮分析会话。叙事材料最多使用 50 条摘要、20 条摩擦说明和 15 条重复指令；若仍有 remaining，会在 lens 输入和报告中明确覆盖局限。
5. **7 个专属 lens**：project_areas、interaction_style、what_works、friction_analysis、suggestions、on_the_horizon、fun_ending。每个 lens 有不同 schema，禁止压成同一种 claim。
6. **At-a-Glance**：七个 lens 全部完成后再独立综合 whats_working、whats_hindering、quick_wins、ambitious_workflows。

不要把 Repeat / Contradiction / Evolution、模型自报评分或无限修订循环插入主流程；它们不是此版本观察到的 Claude /insights 实现。

Claude Code 2.1.228 对个别 facet/lens 失败采用 best-effort；本 Codex 版为了避免把缺段报告误作完整洞察，要求当前签发批次和七个 lens 全部有效，否则修正该批或停止。这是 Codex 完整性增强，不是 Claude 的故障语义。

## 报告内容

报告顶部是四格 At-a-Glance，随后是“用户消息、代码行、文件、活跃天数、日均消息”五项统计。正文按项目领域、协作方式、有效做法、摩擦与根因、功能建议、工作流建议、未来机会七个导航章节组织，并展示 12 类行为图：目标、工具、语言、会话类型、响应时间、多任务并行、消息时段、工具错误、有效帮助、结果、摩擦和推断满意度。

suggestions 必须保留三组可行动内容：AGENTS.md additions、Codex features、usage patterns；功能、新用法与未来机会都要包含原因、示例或可复制提示。最后显示定性的难忘时刻。

输出是默认简体中文的单文件静态 HTML：report.html 与 report-YYYYMMDDTHHMMSSZ.html。桌面左侧粘性导航，640px 以下顶部导航；单一内联 CSS、严格 CSP、零 JavaScript/外部资源、动态文本转义和打印样式。详见 references/report-contract.md。

## 执行协议

执行前读取 references/protocol-contract.md。令 `INSIGHTS_SKILL_DIR` 为当前 SKILL.md 所在目录，精确启动：

    python3 "$INSIGHTS_SKILL_DIR/scripts/insights.py"

不要加 `--request`；保持同一进程和 stdin/stdout 打开。每行发送一个 JSON 请求并读取一行 JSON 响应。第一条请求为：

    {"op":"prepare","max_new_sessions":10,"language":"zh-CN"}

仅在 `ok` 为 true 时推进。`result.next` 是下一请求对象：next_jobs 和 commit 原样发送；submit_jobs 的 `results` 值是 `"<job results>"` 哨兵，只把该哨兵替换为当前 jobs 的结果数组。每项精确为 `{"job_id":"...","result":{...}}`；`result` 必须是 JSON 对象，不得是 JSON 字符串。

- 对每个 job，只使用其 prompt 和 schema 生成结果；不要交占位 facet、合成结论或 fallback 冒充模型分析。
- 可把互斥 job 分给子代理；只有主代理持有 helper 进程并提交结果。
- helper 未收齐全部 chunk 时不会发 facet；未收齐全部 facet 时不会发 lens；未收齐七 lens 时不会发 At-a-Glance；只有 ready_to_commit 才能 commit。
- commit 只接受 helper-owned run_id 和匹配语言，不接受调用方重传 facet、lens、目录或 prepared state。
- submit_jobs 逐批原子校验；某项失败则整批零接受。只有 `ok:false` 明确返回同 run_id 的 next_jobs，且能从同一已签发 jobs 生成真实合规结果时，才修正整批并重试。无法生成真实结果时发送 abort；源/state 漂移、隐私、锁、CAS、HTML、事务、非 JSON、EOF、未知/过期 run 等不可恢复错误立即停止，不自动 prepare、不扩大范围、不绕过，也不提交占位结果。

commit 成功响应必须含 generation、report_path、timestamp_report_path、manifest_path、facet_count 和 coverage。完成后把响应中的 report_path 原值做成可点击的本地报告链接，同时返回 timestamp_report_path、覆盖恒等式 `eligible = cached + selected + remaining` 是否成立，以及 `remaining > 0`（是否仍有未处理会话）；最后邀请用户继续深挖报告中的某一节。不要自行构造路径或计数。完整 JSONL、job envelope 与闭环样例见 references/protocol-contract.md；聚合结构见 references/aggregation-contract.md。
