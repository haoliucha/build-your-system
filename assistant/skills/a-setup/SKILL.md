---
name: a-setup
description: 初始化并检查 Vault 目录、标准文件和用户配置；已有文件按章节安全更新。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 初始化与配置

帮助用户验证当前 Vault、补齐标准结构、填写画像和作息配置。当前目录就是 Vault 根目录，所有路径使用相对路径。

## 1. 目录检查

检查并按需创建以下 7 个目录：

```text
00-Inbox/
10-Projects/
20-Areas/
30-Resources/
40-Archives/
50-GTD/
60-Memory/
```

并创建 `60-Memory/weekly-summary/` 与 `60-Memory/archive/`。不删除已有目录或文件。

## 2. 标准文件

将下面的清单视为 `STANDARD_FILES`；逐个检查，缺失时按本 skill 的最小骨架或 file-templates.md 创建：

```text
60-Memory/profile.md
60-Memory/now.md
60-Memory/preferences.md
60-Memory/patterns.md
60-Memory/patterns-digest.md
60-Memory/tag-mapping.md
50-GTD/active.md
50-GTD/waiting.md
50-GTD/someday.md
50-GTD/done.md
00-Inbox/capture.md
```

项目、选题、产品想法、日记和周报使用 `vault-structure/references/file-templates.md`；不要在本 skill 另起格式。

## 3. 用户问卷

用当前宿主的提问能力收集：

1. 称呼、身份、关注领域；
2. 主要使用场景；
3. 起床时间 `wake`；
4. 深度工作时段 `deep_work`；
5. 收工时间 `end_work`；
6. 上床时间 `bedtime`；
7. 语言 `language`（默认 `zh-CN`）；
8. 断更惩罚金额 `penalty_per_day`（默认 200，填 0 关闭）。

可选询问当前正在推进的主线、截止日期和阻塞项。用户跳过时写“（未填写）”，不编造事实。

## 4. 写入硬规则：按章节 upsert

这是硬规则：`profile.md`、`preferences.md`、`now.md` 已存在时，先解析二级标题或 frontmatter，只更新模板拥有的章节；其余章节原样保留、顺序不变。不得用整文件模板覆盖用户内容，不得删除未知字段、评论、段落或自定义章节。

### 4.1 profile.md

只维护“基本信息”和“助手使用偏好”两节，正文不超过 40 行。骨架如下，末尾指针必须保留：

```markdown
---
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# 用户画像

## 基本信息
- 称呼：{称呼}
- 身份：{身份}
- 关注领域：{领域}

## 助手使用偏好
- 主要场景：{场景}
- 语言：{language}

Claude memory：~/.claude/projects/-Users-jliu-Projects-vault/memory/MEMORY.md。
```

若已有自定义章节，保留其原位置和内容；只更新上述两个模板拥有的章节以及 frontmatter 的 `created` / `updated`。

### 4.2 now.md

缺失时创建以下模板；已有文件只 upsert `## 主线` 与 `## 本周关注`，并更新 `updated`：

```markdown
---
updated: YYYY-MM-DD
---

## 主线
- 名称：{主线}；截止：{日期或无}；阻塞：{阻塞或无}

## 本周关注
- {关注事项}
```

主线最多三条；没有信息写“（未填写）”。

### 4.3 preferences.md

frontmatter 必须包含且只依赖以下配置键；正文可保留用户自定义内容：

```yaml
---
wake: HH:MM
deep_work: HH:MM-HH:MM
end_work: HH:MM
bedtime: HH:MM
language: zh-CN
penalty_per_day: 200
---

# 偏好配置
```

更新问卷对应键，不把作息再复制成旧的正文键值。`o-schedule` 仍兼容旧正文。

## 5. 其余最小骨架

缺失时创建；已有文件不重排、不清空：

- `patterns.md`：`# 模式日志`，新 L3 条目由 o-review 或 c-dump 按 memory-model.md 写入；
- `patterns-digest.md`：`# 精华模式`，仅由 o-weekly 写入；
- `tag-mapping.md`：按用户关注领域写领域标签和关键词；
- `50-GTD/active.md`：`# 任务中心`、`## 今日重点 (MIT) - {今天}`、`## 本周任务`；
- `50-GTD/waiting.md`：`# 等待中`；
- `50-GTD/someday.md`：`# 将来/也许`；
- `50-GTD/done.md`：按 file-templates.md 的最小归档骨架；
- `00-Inbox/capture.md`：`# 待处理`。

需要完整字段时回读 file-templates.md，不在这里复制项目或日记模板。

## 6. 检查与报告

再次检查目录和 `STANDARD_FILES`，报告新增、保留和缺失项；报告画像、当前状态和配置是否更新。已有用户内容被保留时明确说明。

## 注意事项

- 初始化必须幂等：再次运行不会覆盖用户自定义章节；
- 不把 `a-setup` 当作每日回顾，不分发 Inbox；
- 不写入 `patterns-digest.md` 的 active 条目；
- 后续可使用 `o-tasks`、`o-review`、`o-weekly` 继续工作。
