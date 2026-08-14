# 聚合、Lens 与 At-a-Glance 契约

本页的确定性聚合、七个异构 lens、独立 At-a-Glance 及其报告职责属于 Claude Code 2.1.229 的可观察 /insights 语义；字段中的 AGENTS.md、Codex features、Task/MCP/Web 和 user_instructions_to_codex 是 Codex 表面适配。脱敏、缓存与事务不属于本页分析阶段。

helper 同时计算 eligible 全量统计与 analyzed-only 统计。页首、项目计数、Lens 和 12 张行为图一律使用已有有效 facet 的 analyzed-only 主会话，不能把 200 个 eligible 会话的消息数描述成来自 171 个 analyzed 会话。eligible 全量与 remaining 只在方法区交代。subagent、automation、headless 只在方法区统计。报告与 lens material 必须携带 eligible/cached/selected/remaining，remaining 大于零时明确说明叙事结论仅覆盖已分析子集。

七个 lens 共用压缩材料：完整主会话统计与项目分布；按项目、时间、结果、成功、摩擦和反馈分层选出的最多 50 条 facet 摘要；20 条多样化摩擦说明；15 条带次数、首末日期的 user_instructions_to_codex。后来的明确纠正覆盖较早的冲突要求。它们必须分别返回：

| Lens | 结构 |
|---|---|
| project_areas | areas：name、project_ids、description；session_count 由 helper 根据项目分布计算 |
| interaction_style | narrative、key_pattern |
| what_works | intro、impressive_workflows：title、description |
| friction_analysis | intro、categories：本地化 title、description、examples |
| suggestions | agents_md_additions、features_to_try、usage_patterns；每组 2–3 项 |
| on_the_horizon | intro、opportunities：title、whats_possible、how_to_try、copyable_prompt |
| fun_ending | headline、detail |

suggestions 的 item 字段：

- AGENTS.md：addition、why、prompt_scaffold
- Codex 功能：feature、one_liner、why_for_you、example_code
- 使用模式：title、suggestion、detail、copyable_prompt

七个 lens 完成后才生成独立 At-a-Glance：

    whats_working
    whats_hindering
    quick_wins
    ambitious_workflows

语气是具体、克制的使用教练；不堆统计，不空泛赞美，不补造案例。摩擦不得强制按 Codex、用户、外部三个责任桶组织，应优先提炼“过早宣称完成”“缺少直接证据的诊断”等可行动问题模式。中文报告不得暴露 snake_case 枚举标题。
