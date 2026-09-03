---
name: vault-structure
description: This skill should be used when the user asks about Vault paths, file locations, task formats, frontmatter templates, memory layers, or how to navigate the personal knowledge base.
---

# Vault 结构导航（PARA + GTD + 记忆层）

## Vault 根目录与路径原则

当前宿主提供的 Vault 根目录是所有相对路径的基准。共享 skill 只使用相对路径，不把宿主、机器或会话的绝对路径写入 Vault。宿主入口、活动分析和上下文注入的差异见 references/host-adaptation.md。

## 目录结构

~~~text
Vault/
├── 00-Inbox/
│   ├── {YYYY-MM-DD}.md       # 当日日记、间隙日志与复盘
│   ├── {Y}/{Y-M}/            # 历史日记归档位置
│   └── capture.md            # 待分发捕获内容
├── 10-Projects/
│   ├── {项目名}.md            # 单文件项目
│   └── {项目名}/README.md     # 复杂项目
├── 20-Areas/
│   ├── media/
│   │   ├── topics/            # 选题
│   │   ├── 逐字稿/             # 逐字稿
│   │   └── 方法论库/           # 方法论
│   └── indie/ideas/           # 产品想法
├── 30-Resources/
│   ├── conversations/         # 对话资料
│   └── summaries/             # 摘要资料
├── 40-Archives/               # 不活跃内容
├── Clippings/                 # 外部剪藏
├── 50-GTD/
│   ├── active.md              # 活跃任务与 MIT
│   ├── waiting.md             # 等待中
│   ├── someday.md              # 将来/也许
│   └── done.md                 # 已完成任务
└── 60-Memory/
    ├── profile.md             # L0 稳定画像
    ├── now.md                 # L1 当前状态
    ├── preferences.md         # L2 配置
    ├── patterns.md            # L3 模式日志
    ├── patterns-digest.md     # L4 精华模式
    ├── tag-mapping.md         # 领域标签映射
    ├── weekly-summary/        # 周报与记忆消融记录
    └── archive/               # 迁移或过期的记忆
~~~

目录编号固定为 00-Inbox、10-Projects、20-Areas、30-Resources、40-Archives、50-GTD、60-Memory。历史日记使用 00-Inbox/{Y}/{Y-M}/，不要把新日记直接写入历史归档目录。

脚本层检查的标准文件路径为：`60-Memory/profile.md`、`60-Memory/now.md`、`60-Memory/preferences.md`、`60-Memory/patterns.md`、`60-Memory/patterns-digest.md`、`60-Memory/tag-mapping.md`、`50-GTD/active.md`、`50-GTD/waiting.md`、`50-GTD/someday.md`、`50-GTD/done.md`、`00-Inbox/capture.md`。

## Obsidian Tasks 格式

~~~markdown
- [ ] 任务描述 [[项目名]] #领域 📅 YYYY-MM-DD ⏫
~~~

| 部分 | 格式 | 必选 | 说明 |
|---|---|---|---|
| 复选框 | - [ ] / - [x] | 是 | 任务状态 |
| 描述 | 文本 | 是 | 可执行的任务描述 |
| 项目关联 | [[项目名]] | 否 | 关联 10-Projects/ 中的项目 |
| 领域标签 | #media / #indie 等 | 否 | 分类用途，来自 tag-mapping |
| 截止日期 | 📅 YYYY-MM-DD | 否 | Obsidian Tasks 识别的 due date |
| 优先级 | ⏫ / 🔼 / 🔽 | 否 | 排序用途 |

### Emoji 含义

| Emoji | 含义 |
|---|---|
| 📅 | 截止日期（due） |
| ⏳ | 计划日期（scheduled） |
| 🛫 | 开始日期（start） |
| ⏫ | 高优先级 |
| 🔼 | 中优先级 |
| 🔽 | 低优先级 |
| 🔁 | 循环任务 |
| ✅ | 完成日期 |

## 文件格式索引

项目、选题、产品想法、日记、GTD、记忆层和周报模板统一见 references/file-templates.md。项目 frontmatter 也以该文件为准，不在本入口重复定义，避免出现多个规范。

## 记忆层索引

60-Memory/ 按 L0–L4 分层：稳定画像、当前状态、配置、模式日志和精华模式；周报负责消融记录，archive 只保存迁移或过期内容。完整的写入方、读取方、注入边界、条目格式、prepend 和 bootstrap 规则见 references/memory-model.md。

## 宿主适配

宿主适配见 references/host-adaptation.md；记忆层规范见 references/memory-model.md。
