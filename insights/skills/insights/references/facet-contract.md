# `facet_v2` 契约

每个 work item 恰好产生一个 JSON facet。顶层键集合必须精确为：

```text
schema_version, session_key, source_hash, date, project_alias, session_origin,
deterministic_stats, privacy_redactions, underlying_goal, goal_categories,
outcome, user_satisfaction_counts, helpfulness, session_type, friction_counts,
friction_detail, primary_success, brief_summary, evidence_anchors
```

helper-owned 字段必须原样复制，且 `session_key` 只能是 `session-` 加 16 位小写十六进制，`project_alias` 只能是 `project-` 加 8 位小写十六进制。`source_hash` 为 64 位小写 SHA-256。`deterministic_stats` 必须包含事件数、用户/助手消息数、时长、字符数、源文件数、工具、错误、文件改动和子代理计数，均为非负整数。

模型只填写目标、类别、结果、用户正负/纠正信号、帮助度、会话类型、摩擦、成功点、摘要和简短事件锚点。枚举值、数组长度、文本长度和隐私规则由 helper 严格校验。事件锚点只写可脱敏的短标签，不复制长原文。
