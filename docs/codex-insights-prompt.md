你现在执行 Codex 版 `$insights`：复盘我在本机 Codex 中做什么、怎样协作、什么最有效、哪里受阻，以及下一步可以直接尝试什么。

如果已安装 `insights` Skill，完整读取并严格执行它。不要让主 Agent 或子代理承担分析调度；只启动 Skill 内的确定性 `codex exec` Runner，并把控制台总体进度持续展示给我。

默认：
- `MAX_NEW_SESSIONS=200`
- `LANGUAGE=zh-CN`
- Fast
- 只读本机 Codex sessions/archived_sessions
- 只写 `$CODEX_HOME/usage-data/insights/`
- 语义分析只选择用户主会话（primary 与 legacy_primary）；subagent、automation、headless 只在方法区计数

分析顺序固定为：主会话全量确定性 meta → 长会话完整分块摘要 → 每会话固定枚举 native facet → 分层代表证据聚合 → 七个专属 lens → 独立 At-a-Glance → 静态 HTML → state-last commit。

Runner 必须：
- 用 4 个最多 50 会话的持久化波次；
- 清单完成时冻结脱敏分析材料并记录快照时间；运行中的 JSONL 追加不阻断当前报告，只使下一轮对应缓存失效；
- chunk 用 Luna/low，facet 用 Terra/medium，lens/总览用 Sol/high；
- 从 6 并发自适应增长到 12；限流等待不计重试；
- 不设置 Runner timeout、Job timeout、停滞中断或 TTL；
- 每 60 秒输出心跳，每 5 分钟输出完整仪表盘；每次都显示总体百分比、全部阶段、语义覆盖、并发、吞吐、P50/P90 和 ETA；
- 10 分钟无事件只告警，不中断；
- 暂停时立即终止在途进程、清理 partial、将 running 重排 queued，并保留 succeeded；
- 普通错误最多额外重试两次；chunk 最终降级、facet 跳过、lens/总览显示 concern；锁、Insights state CAS、hash 或事务错误禁止提交。

报告必须是默认简体中文的单文件静态 HTML：约 800px 居中单栏，页首只有标题和一行“消息数、已分析会话、主会话总数、日期范围”，随后依次为黄色线性四段总览、顶部导航、五项横向统计、七个扁平语义章节、独立难忘时刻和页尾方法区。12 类行为图按项目领域、协作方式、有效做法、摩擦四章归位；所有机器枚举映射为中文。报告还应完整呈现 AGENTS.md 建议、Codex 功能、工作流和未来机会。最新报告为 `report.html`，归档为 `report-YYYYMMDDTHHMMSSZ.html`。

如果发现未完成运行，先让我选择恢复或新建，不要替我决定。成功后给出可点击报告路径、归档路径、实际耗时、性能门（主动计算 ≤90 分钟、端到端 ≤120 分钟）及恒等式：
`eligible = analyzed + skipped + remaining`
`selected = succeeded + skipped`
