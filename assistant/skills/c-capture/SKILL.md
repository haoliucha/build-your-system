---
name: c-capture
description: 将用户内容捕获到 Vault Inbox，并按唯一规则真源识别类型、领域、状态与间隙记录。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 快速捕获

将用户提供的内容直接写入当前 Vault，不在捕获阶段做 GTD 分发。当前目录即 Vault 根目录，所有路径使用相对路径。

## 执行流程

### 0. 检查初始化

检查 `60-Memory/profile.md`。缺失时提示运行 `a-setup`，停止写入。

### 1. 识别标签

类型、领域、状态、项目归属与置信度统一见 capture-rules §1-§4、§8；领域关键词读取
`60-Memory/tag-mapping.md`。不要在本 skill 复制关键词表。

如果内容属于间隙记录，触发条件、情绪判断和写入位置全部见 capture-rules §6。

### 2. 写入

- 普通捕获：写入 `00-Inbox/capture.md`，新条目置于 `## 待处理` 后、既有条目前，保持最新在上。
- `#pause`：捕获时直接写入当日日记的 `## 间隙日志`，不写入 `capture.md`；格式和区块位置见 capture-rules §6。
- 每次只做一次直接写入，不要求用户确认；无法判断的类型仍按规则写入并保留待确认标记。

普通捕获条目至少保留日期、时间、原文和识别标签。不要改写用户原文，不要在此阶段创建项目、topic 或 idea 文件。

### 路径处理

当日日记优先使用 `00-Inbox/{YYYY-MM-DD}.md`；若不存在，使用
`00-Inbox/{Y}/{Y-M}/{YYYY-MM-DD}.md`。缺失日记时按日记模板创建，再写入间隙日志。

## 反馈

普通捕获只报告已写入的类型和领域标签；间隙记录只报告时间、已保存和下一步摘要。情绪字段遵守 capture-rules §6。

## 例子

- “明天给客户发报价单” → 按 capture-rules 识别后写入 `capture.md`；
- “等客户回复报价确认” → 按规则识别为等待事项；
- “刚完成初稿，下一步准备开会” → 按规则写入当日日记的间隙日志。

## 边界

`o-review` 才负责分发；`cc-activity` 只读并渲染间隙日志。捕获规则的完整定义只维护在 capture-rules。
