---
name: e-export
description: 将当前对话整理成 Vault 中的知识笔记和完整对话记录，并保持宿主来源标识一致。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 导出对话

将当前对话保存为一份知识笔记和一份完整记录，路径均相对于 Vault 根目录。

## 宿主标识

先判断当前宿主，只允许 `claude-code` 或 `codex`。知识笔记和完整对话记录的 frontmatter 中，`source` 与 `tags` 必须使用同一个宿主标识；不得一个写 `claude-code`、另一个写 `codex`。

例如当前宿主为 `codex` 时，两份文件都使用：

```yaml
source: codex
tags: [codex, ...]
```

## 文件

文件名为 `YYYYMMDD-{主题}`。

### 知识笔记

保存到 `00-Inbox/YYYYMMDD-{主题}.md`，保留以下 frontmatter 字段：

```yaml
---
date: YYYY-MM-DD HH:mm
source: {宿主标识}
type: knowledge
tags: [{宿主标识}, {领域标签}]
---
```

正文包括背景、前置条件、实现步骤、完整代码或配置、常见问题、要点总结和指向完整记录的链接。领域标签从 `60-Memory/tag-mapping.md` 选择。

### 完整记录

保存到 `30-Resources/conversations/YYYYMMDD-{主题}-对话.md`：

```yaml
---
date: YYYY-MM-DD HH:mm
source: {宿主标识}
type: conversation
tags: [{宿主标识}, raw]
related: [[00-Inbox/YYYYMMDD-{主题}]]
---
```

保留完整用户消息、助手回复、关键工具输出和代码块，并链接回知识笔记。

## 保存检查

- 两个文件的 `source` 完全一致；
- 两个文件的 `tags` 都包含相同宿主标识；
- 使用 GMT+8 日期时间；
- 两个文件互相可追溯；
- 不把未确认推测包装成事实。
