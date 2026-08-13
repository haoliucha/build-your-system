---
name: insights
description: Use only when the user explicitly invokes `$insights` to analyze patterns across prior local Codex sessions.
---

# Codex /insights

这是 Codex-only 的本机会话复盘 Skill。它不读取云端、不调用 Claude Code，也不修改任何项目仓库。默认语言为简体中文，入口必须由用户显式输入 `$insights`；不要因为普通的“总结”“复盘”请求而隐式扫描历史。

## 参数与边界

- `MAX_NEW_SESSIONS=200`：每轮最多选择最近的 200 条尚未缓存、符合资格的会话；测试或小范围运行可用 `$insights MAX_NEW_SESSIONS=10`。
- `LANGUAGE=zh-CN`：默认简体中文。只有用户显式提供合法 BCP 47 标签（例如 `en-US`）时覆盖；语言变化不会使既有 facet 缓存失效。
- 默认读取 `$CODEX_HOME/sessions/` 与 `$CODEX_HOME/archived_sessions/`，输出只写 `$CODEX_HOME/usage-data/insights/`。
- 排除当前会话、含 `$insights` 的会话、少于 2 条用户消息或持续少于 60 秒的会话。自动化与子代理会话可以被标记为来源类型，但不能压过人工协作结论。
- 原始路径、原始 session ID、密钥、Cookie、Bearer、邮箱、IP、私人绝对路径和长段原文不得进入模型请求以外的持久化对象；检测命中即 fail closed。

## 五层洞察逻辑

```text
L1 确定性事实
  → L2 长会话完整 Map-Reduce
  → L3 单会话 facet_v2
  → L4 Repeat / Contradiction / Evolution
  → L5 七个独立 lens
  → 11 章 HTML 草稿
  → 五项质检（最多修订一次）
  → report.html
```

### L1：事实层

helper 从 JSONL 提取日期、项目别名、来源（active/archived/mixed）、消息和事件数、时长、字符数、工具/错误/文件改动/子代理计数，并派生不可逆的 `session-<16hex>` 与 `project-<8hex>`。这些字段由 helper 负责，模型不得改写。

### L2：完整长会话层

脱敏后的会话若超过 30,000 字符，按事件边界切成约 25,000 字符的连续块。每块都必须完成一次结构化判断，再由同一主代理做一次 reduce；不得只看开头，不得丢掉最后的用户反馈、错误或结果。

### L3：`facet_v2` 层

每个 work item 恰好生成一个 facet。helper-owned 字段必须原样复制：`schema_version`、`session_key`、`source_hash`、`date`、`project_alias`、`session_origin`、`deterministic_stats`、`privacy_redactions`。模型-owned 字段为：

- `underlying_goal`、`goal_categories`、`outcome`（完成/部分完成/未完成/不确定）；
- `user_satisfaction_counts`（positive/negative/correction）、`helpfulness`、`session_type`；
- `friction_counts` 与 `friction_detail`（误解请求、错误方案、代码问题、用户否决、过度改动、工具失败、外部问题、重复指令、缺少上下文）；
- `primary_success`、`brief_summary`、`evidence_anchors`。

只记录会话能支持的事实、用户明确反馈和带条件的推论；同一事件的摩擦只计一次。详细字段限制见 `references/facet-contract.md`。

### L4：跨会话聚合层

每 50 个 facet 为一批生成 `aggregation_v1`，分别寻找：

- `repeat`：反复目标、失败、返工、指令、工具或有效做法；
- `contradiction`：相似目标下相反的做法、结果或反馈；
- `evolution`：项目、行为和协作方式随时间的变化。

“规律、常见、反复”等跨会话判断至少引用两个不同 opaque session key；单例必须明确写“单例”，不得从一条会话外推。

### L5：七个 lens 层

主代理基于 facets 与聚合材料独立生成七组 `aggregation_v1` lens：`project_areas`、`interaction_style`、`what_works`、`friction_analysis`、`suggestions`、`on_the_horizon`、`fun_ending`。每条包含 `claim`、`evidence`、`action`、`success_criteria`、`confidence`；只有主代理负责最终合成报告。

## 质检与报告

报告固定 11 章：总览、项目领域、协作方式、有效做法、摩擦与根因、功能与工作流、AGENTS.md 建议、新用法、未来机会、难忘时刻、方法与覆盖量。五项 `quality_v1` 分数为覆盖、证据、隐私、可行动性、增量一致性，范围 1–5：隐私、证据、增量必须 ≥4，否则不提交；覆盖或可行动性低于 4 时只允许修订一次并复评。仍偏低时可以交付，但必须在方法章节显示 concern；禁止无限循环或补造证据。

`report.html` 是 UTF-8 单文件静态 HTML：`lang` 默认为 `zh-CN`，单一内联 CSS，严格 CSP，零脚本、零外部资源，所有模型文本先 HTML 转义。桌面约 220px 左侧粘性导航和约 800px 正文，640px 以下变为顶部导航；导航覆盖全部 11 个锚点，并包含打印样式。归档名为 `report-YYYYMMDDTHHMMSSZ.html`。

## 长驻协议

Skill 目录中的 `scripts/insights.py` 是确定性 helper。真实运行必须启动一个长驻进程，并按返回的 `next` 模板依次执行；`op` 是规范字段，同时兼容单独出现的旧 `action` 别名。完整 prepared、输出路径、缓存和 generation 只保存在 helper 进程内。

```json
{"op":"prepare","max_new_sessions":10,"language":"zh-CN","current_thread_id":"<current-thread-id>"}
{"op":"aggregate","run_id":"<run-id>","facets":["<每个 work item 的 facet_v2>"]}
{"op":"validate_patterns","run_id":"<run-id>","patterns":"<aggregation_v1>"}
{"op":"validate_lenses","run_id":"<run-id>","lenses":"<七组 lens>"}
{"op":"validate_quality","run_id":"<run-id>","quality":"<quality_v1>"}
{"op":"commit","run_id":"<run-id>","facets":["<同一批 facets>"],"patterns":"<已校验>","lenses":"<已校验>","quality":"<已校验>","language":"zh-CN"}
```

`run_id` 一次性消费；commit 不接受调用方提供 `output_dir` 或 `prepared`。每次协议响应都会返回下一请求模板，避免把旧的 `action` 字段或字段顺序抄错。单次 `--request` 进程不能跨进程 commit。

提交使用锁、generation CAS、staging、备份、回滚和 state-last；任一校验、源变化、隐私扫描、报告冲突或写入失败都保持安全状态并报告唯一阻断原因。

详细契约：`references/facet-contract.md`、`references/aggregation-contract.md`、`references/privacy-contract.md`、`references/report-contract.md`、`references/quality-contract.md`。
