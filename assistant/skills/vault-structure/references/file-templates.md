# 文件模板集

本文件是 Vault 文件的模板索引。所有路径相对于 Vault 根目录；日期使用
YYYY-MM-DD，时间使用 HH:MM。项目、选题和产品想法的新文件应保留对应模板的
frontmatter 字段，不要另起一套字段名。

## 项目文件模板

位置：10-Projects/{项目名}.md 或 10-Projects/{项目名}/README.md

项目 frontmatter 只有以下字段，area 只能取列出的五个值：

~~~yaml
---
status: active | paused | completed
created: YYYY-MM-DD
target: YYYY-MM-DD  # 可选，预期完成日期
area: indie | media | outsourcing | life | learning
tags: [project]
---
~~~

~~~markdown
# 项目名称

## 目标

一句话描述项目要达成的目标。

## 背景

项目启动的原因和背景。

## 关键成果

- [ ] 关键成果 1
- [ ] 关键成果 2
- [ ] 关键成果 3

## 任务

> 任务可在 50-GTD/active.md 中列出，也可使用 [[项目名]] 关联。

- [ ] 任务 1 📅 YYYY-MM-DD
- [ ] 任务 2

## 进度记录

### YYYY-MM-DD

- 完成了……
- 下一步……

## 相关资源

- [[相关文档1]]
- [[相关文档2]]
~~~

状态说明：active 正在进行，paused 因明确原因暂停，completed 已完成待归档。
生命周期为 active → paused → active → completed → 40-Archives/{项目名}/。

## 选题文件模板

位置：20-Areas/media/topics/{选题名}.md

status 只能取 idea | evaluating | scripted | ready | published | dropped。

~~~yaml
---
type: topic
title: 选题标题
status: idea | evaluating | scripted | ready | published | dropped
category: 分类
priority: high | medium | low
created: YYYY-MM-DD
published: YYYY-MM-DD  # 发布后填写
tags: [topic, media]
---
~~~

~~~markdown
# 选题标题

## 核心观点

一句话描述核心观点。

## Hook 想法

- [ ] Hook 版本 1
- [ ] Hook 版本 2

## 结构要点

1. ……
2. ……

## 相关选题

- [[相关选题1]]
- [[相关选题2]]

## 逐字稿

- 状态：未开始 | 进行中 | 已完成
- 文件：[[20-Areas/media/逐字稿/日期-选题名]]

## 发布记录

- 平台：
- 日期：
- 数据：
~~~

## 产品想法文件模板

位置：20-Areas/indie/ideas/{产品名}.md

~~~yaml
---
status: idea | researched | building | shipped | archived
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [indie, idea]
---
~~~

~~~markdown
# 产品名称

## 概述

一句话描述产品解决的问题。

## 痛点

用户遇到的具体问题是什么？

## 解决方案

产品如何解决这个问题？

## 竞品调研

| 产品 | 核心功能 | 定价 | 差异点 |
|---|---|---|---|
| …… | …… | …… | …… |

## 差异化优势

- ……

## 可行性评估

- **技术难度**：
- **MVP 预估**：

## 下一步

- [ ] ……
~~~

## 日记文件模板

位置：00-Inbox/{YYYY-MM-DD}.md。

间隙日志固定置于标题之后，最新记录在上；实时流水账写入日志，回顾加工写入复盘。

~~~yaml
---
date: YYYY-MM-DD
tags: [daily]
---
~~~

~~~markdown
# {YYYY-MM-DD} 星期X

## 间隙日志

> 最新在上。

### HH:MM

- **完成**：……
- **感受**：待记录
- **下一步**：……

## 日志

……

## 复盘

> 由 o-review 生成于 {HH:MM}

### 📅 时间线摘要

……

### 📊 活动数据

- 活动时段：{开始} - {结束}
- 消息总数：{N} 条
- 间隙记录：{N} 条
- origin：claude-local | codex-local | mixed

### 🎯 MIT 完成情况

| MIT 计划 | 状态 | 实际投入 |
|---|---|---|
| {任务1} | ✅/⏸️ | {时间} |

完成率：{N/M}

### 🎯 项目进度

| 项目 | 今日任务 | 完成 | 状态 |
|---|---|---:|---|
| [[项目名]] | X | Y | active |

### 💭 感受

……

### 🔍 偏差分析

……

#### 精华预测对照

| 模式 | 预测 | 今日符合/相反 |
|---|---|---|
| P-001 · {模式} | {predicts} | 符合/相反 |

### 💡 今日洞察

- ……
~~~

### 日记复盘自动草稿变体

自动模式只覆盖同名自动草稿区块，不覆盖手写复盘；不确定内容保留待确认标记。

~~~markdown
## 复盘（自动草稿 20:30）

> 由 o-review 生成于 {HH:MM}

### 📅 时间线摘要

……

### 📊 活动数据

- 活动时段：{开始} - {结束}
- 消息总数：{N} 条
- 间隙记录：{N} 条
- origin：claude-local | codex-local | mixed

### 🎯 MIT 完成情况

| MIT 计划 | 状态 | 实际投入 |
|---|---|---|
| {任务1} | ✅/⏸️ | {时间} |

### 🎯 项目进度

| 项目 | 今日任务 | 完成 | 状态 |
|---|---|---:|---|
| [[项目名]] | X | Y | active |

### 💭 感受

> （待填写）

### 🔍 偏差分析

……

#### 精华预测对照

| 模式 | 预测 | 今日符合/相反 |
|---|---|---|
| P-001 · {模式} | {predicts} | 符合/相反 |

### 💡 今日洞察

- [ ] 候选：……
~~~

## Inbox 条目格式

位置：00-Inbox/capture.md。

~~~markdown
---
### {月}-{日} {时}:{分}
{内容}
{类型标签} {领域标签} {状态标签}
---
~~~

新增条目写在已有条目之前，保留历史条目原文。#pause 不写入该文件，直接写入
当日日记的间隙日志。

## GTD 文件模板

### 50-GTD/active.md

~~~markdown
---
updated: YYYY-MM-DD
---

# 任务中心

## 今日重点 (MIT) - YYYY-MM-DD

- [ ] 今日最重要任务 1 ⏫
- [ ] 今日最重要任务 2

## 明日重点（建议）- YYYY-MM-DD

> 自动建议，运行 o-review 确认后转正

- [ ] 建议任务 1
- [ ] 建议任务 2

## 本周任务

- [ ] 其他活跃任务 [[项目名]] #领域 📅 YYYY-MM-DD
~~~

明日重点（建议）区块可选；确认后转为正式 MIT，未确认前不修改今日 MIT。

### 50-GTD/waiting.md

~~~markdown
# 等待清单

## 当前等待

- [ ] 等待对象或结果 [[项目名]] 📅 YYYY-MM-DD
  - 最近跟进：YYYY-MM-DD
~~~

### 50-GTD/someday.md

将来/也许条目按月份分组；新条目插入当月分组最前面，已有月份不存在时创建在顶部。

~~~markdown
# 将来/也许

## YYYY-MM

- [ ] 将来再做的任务 #领域

## YYYY-MM

- [ ] 更早的条目
~~~

### 50-GTD/done.md

已完成任务按完成月份分组；新条目插入当月组最前面，不重排历史月份。

~~~markdown
# 已完成任务归档

## YYYY-MM

- [x] 已完成任务 [[项目名]] ✅ YYYY-MM-DD #领域
  - 子任务或完成备注

## YYYY-MM

- [x] 更早的已完成任务 ✅ YYYY-MM-DD
~~~

## 记忆层文件模板

详细的分层、写入方、读取方、注入边界和消融规则见
vault-structure/references/memory-model.md。

### 60-Memory/profile.md（L0）

骨架不超过 40 行；稳定画像按章节更新，不把短期状态塞回画像。最后一行固定保留
Claude memory 指针。

~~~markdown
---
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# 用户画像

## 基本信息
- 称呼：
- 身份：
- 关注领域：

## 助手使用偏好
- 主要场景：
- 语言：zh-CN

## 性格特点
- （由长期证据确认后填写）

## AI 助手注意事项
- 先说明事实边界、证据和待确认项。
- 保留用户已确认的格式与约束。

Claude memory：~/.claude/projects/-Users-jliu-Projects-vault/memory/MEMORY.md
~~~

### 60-Memory/now.md（L1）

~~~yaml
---
updated: YYYY-MM-DD
---
~~~

~~~markdown
# 当前状态

## 主线

### 主线 1：{名称}
- 截止：YYYY-MM-DD 或无
- 阻塞：无 / {阻塞事项}

### 主线 2：{名称}
- 截止：YYYY-MM-DD 或无
- 阻塞：无 / {阻塞事项}

### 主线 3：{名称}
- 截止：YYYY-MM-DD 或无
- 阻塞：无 / {阻塞事项}

## 本周关注

- ……
~~~

### 60-Memory/preferences.md（L2）

YAML frontmatter 固定包含六个键；正文保存可读说明，不重复发明另一套键名。

~~~yaml
---
wake: HH:MM
deep_work: HH:MM-HH:MM
end_work: HH:MM
bedtime: HH:MM
language: zh-CN
penalty_per_day: 0
---
~~~

~~~markdown
# 偏好配置

## 作息

- 起床：{wake}
- 深度工作：{deep_work}
- 收工：{end_work}
- 睡觉：{bedtime}

## 晚间流程

- ……

## 任务格式

- 使用 Obsidian Tasks 复选框、项目 wiki-link、领域标签和日期。

## 日常记录

- 间隙记录使用间隙日志，最新在上。
~~~

### 60-Memory/patterns.md（L3）

新条目 prepend，历史条目不改写；每次写入必须带 source: 和日期。

~~~markdown
### YYYY-MM-DD · 标题
tags: #领域
source: [[YYYY-MM-DD]] 复盘
正文最多 8 行，描述可观察事实或模式。
~~~

### 60-Memory/patterns-digest.md（L4）

只由 o-weekly 维护；新条目 prepend，最多保留 30 个 active 条目。

~~~markdown
### P-001 · 标题
status: active | absorbed→P-0xx | retired(原因) | promoted→profile
predicts: 可观测的行为预测
evidence: YYYY-MM-DD, YYYY-MM-DD
sources: [[patterns#YYYY-MM-DD · 标题]]
last_confirmed: YYYY-Www
~~~

### 60-Memory/weekly-summary/{年}W{周}.md

周一至周日按 ISO 周生成；以下为现有周报结构，并固定追加记忆消融和更新建议两节。

~~~markdown
# {年}年第{周数}周总结

> {周一日期}（周一）~ {周日日期}（周日）

## 本周亮点
- ……

## 完成事项
- ……

## 待跟进
- ……

## 想法收集
- ……

## 下周展望
- ……

## 记忆消融记录

| 条目 | 检验 | 结论 | 证据 |
|---|---|---|---|
| P-001 · {标题} | 冗余/必要/反证/提升 | {结论} | {日期与来源} |

## 记忆更新建议

| 层 | 建议（每层最多 3 条） | 应同步到 Claude memory |
|---|---|---|
| profile | 无 / …… | 是/否，理由 |
| now | 无 / …… | 是/否，理由 |
| preferences | 无 / …… | 是/否，理由 |
| tag-mapping | 无 / …… | 是/否，理由 |
~~~

### 60-Memory/tag-mapping.md（L2 辅助配置）

与 a-setup 生成的模板一致：每个领域使用 ## #tag 领域名，下一行使用
关键词：，只生成用户选择的领域。

~~~markdown
---
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# 领域标签映射

> 根据你的关注领域自动生成，可随时编辑。

## #media 自媒体
关键词：视频、自媒体、选题、拍摄、剪辑、发布、抖音、B站

## #indie 独立开发
关键词：产品、独立开发、SaaS、indie、上线、用户、App、工具

## #learning 学习
关键词：学习、课程、书、读书、培训、知识

## #life 生活
关键词：生活、家、个人、健康、运动、财务

## #outsourcing 外包
关键词：客户、外包、项目、甲方、交付、需求、合同
~~~

实际文件只保留用户选择的领域；可按同样格式增加新的 ## #tag 领域名 区块。
