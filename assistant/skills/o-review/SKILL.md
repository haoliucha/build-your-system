---
name: o-review
description: 每日回顾：分发 Inbox、归档完成任务、复用合并时间线、对照精华预测并规划明日 MIT；支持无人值守自动模式。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 每日回顾

参数：`[日期]`，默认今天；传入 `--auto` 进入无人值守模式。当前目录就是 Vault 根目录。

## 前置数据

按顺序运行两条命令：

```bash
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/analyze-activity.py" [日期] --host all --json-only
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/vault-health.py"
```

`ASSISTANT_PLUGIN_ROOT` 由宿主提供，见 vault-structure/references/host-adaptation.md。保存两份结果供后续阶段使用；没有活动数据或健康数据时继续执行并明确标注。

## Phase 0：承接自动草稿

读取当日日记：优先 `00-Inbox/{日期}.md`，缺失时查 `00-Inbox/{Y}/{Y-M}/{日期}.md`。同时读取 `50-GTD/active.md`。

如果日记已有 `## 复盘（自动草稿 …）`，或 active.md 有 `## 明日重点（建议）`，先展示草稿/建议，不覆盖任何内容，并提供三选项：

1. 转正建议 MIT；
2. 补感受与洞察；
3. 忽略。

用户选择后再进入手动回顾。若选择忽略，保留自动草稿，继续处理其他阶段；若选择转正，只有确认的建议才写入 MIT。

`--auto` 不提问，直接进入自动模式章节；自动模式覆盖同名自动草稿，但永不触碰手写 `## 复盘`。

---

## 手动模式

### Phase 1：分发

#### 1.1 读取来源

读取当日日记中可提取的内容，再读取 `00-Inbox/capture.md` 的待处理条目。保留原文、来源和日期。

#### 1.2 识别规则

类型、领域、状态、项目归属和 Someday 条件见 capture-rules §1-§5、§8。不要在本 skill 重复识别表。

- `#pause` 已在捕获时写入间隙日志，跳过，不从 capture.md 再分发；
- `#someday` 写入 `50-GTD/someday.md`；
- `#task` 写入 `50-GTD/active.md`；
- `#waiting` 写入 `50-GTD/waiting.md`；
- `#topic` 建立 `20-Areas/media/topics/{选题名}.md`；
- `#idea` 建立 `20-Areas/indie/ideas/{产品名}.md`；
- `#record` 写回对应日记；
- `#insight` 按 memory-model.md 的 L3 规则写入 `60-Memory/patterns.md`。

#### 1.3 项目归属

`@项目名` 或 `[[项目名]]` 表示项目归属。验证 `10-Projects/` 下是否存在项目；不存在时询问创建、改关联或不关联。创建项目使用 file-templates.md 的项目文件模板，不在这里复制模板。

写入任务时将 `@项目名` 转为 `[[项目名]]`，保留任务描述、领域标签、截止日期和优先级。

#### 1.4 Someday

显式 `#someday` 直接写入 `50-GTD/someday.md`。只有建议延后的 `#task` 才在确认后移动；显示建议原因，用户拒绝时保留在 active。

#### 1.5 确认与写入

展示识别结果、目标文件和待确认项，提供：

1. 全部接受；
2. 逐条确认；
3. 跳过。

普通目标文件的新条目按倒序插入；月度 GTD 条目插入当月分组最前面，历史条目不重排。完成分发后从 capture.md 移除已处理条目，低置信内容保留并说明原因。

---

### Phase 2：复盘

#### 2.0 合并时间线

复用 `cc-activity` 的合并渲染：它读取活动脚本结果和当日日记的 `## 间隙日志`，计算间隔，输出 `📅 时间线概览`、五档情绪分布、origin 和拖延/高效/卡住模式。本阶段不再内联时间线模板，也不重复 capture-rules §6。

#### 2.1 归档完成任务

读取 `50-GTD/active.md`，识别所有 `- [x]` / `- [X]` 任务，保留项目、标签、子任务和原始描述，加完成日期后移动到 `50-GTD/done.md`。写入格式、月份分组和倒序插入规则见 file-templates.md；从 active.md 移除已归档任务。

#### 2.2 项目进度

扫描 `10-Projects/*.md` 与 `10-Projects/*/README.md`，读取 frontmatter 的 status；将今日任务按 wiki-link 归并，输出项目、今日任务数、完成数和状态。项目文件结构以 file-templates.md 为准。

#### 2.2b 精华预测对照

读取 `60-Memory/patterns-digest.md` 中 `status: active` 的每条精华。对每条 `predicts` 与今日事件做事实对照，只能判为“符合”“相反”或“无关”；找不到证据就判为“无关”，不推测。

将小表写入复盘的 `### 🔍 偏差分析`：

```markdown
#### 精华预测对照

| 模式 | 预测 | 今日结果 | 事实依据 |
|---|---|---|---|
| P-001 · {标题} | {predicts} | 符合/相反/无关 | {日期、事件或无} |
```

本次对照不改变 digest 状态；状态更新由 o-weekly 消融循环负责。

#### 2.3 回顾计划与实际

把活动摘要、MIT、完成任务和项目进度并列展示。活动数据保留 Claude / Codex origin；消息数是活动证据，不等于任务产出。指出计划外产出时必须给出来源和事实。

#### 2.4 询问感受

向用户询问今天的感受和具体例外。情绪选项、关键词和记录约束见 capture-rules §6；不在本 skill 复制情绪表。

#### 2.5 引导分析

结合时间线、MIT 完成情况、项目进度和用户感受，询问一个最值得解释的偏差：目标改变、阻塞、分心、低估工作量或外部事件。把解释和事实分开。

#### 2.6 提取洞察

用户确认的洞察按 `vault-structure/references/memory-model.md` 的 L3 格式 prepend 到 `60-Memory/patterns.md`，必须带 `source`，正文不超过 8 行。没有用户确认或没有 source 的候选留在复盘，不写入 patterns.md。

#### 2.7 保存复盘

将复盘保存到 `00-Inbox/{日期}.md` 的 `## 复盘`，完整结构见 file-templates.md 的日记模板。已有手写复盘时先询问覆盖、追加带时间版本或跳过；不得静默覆盖用户内容。

复盘至少包含：时间线摘要、活动数据、MIT 完成情况、项目进度、感受、`### 🔍 偏差分析`（含精华预测对照）和今日洞察。

---

### Phase 3：明日规划

从 active、someday 中展示可执行候选，按项目分组。用户选择不超过 3 个作为明日 MIT，并在 `50-GTD/active.md` 写入 `## 今日重点 (MIT) - {明天}`；不要把自动建议误当作确认。

写入后可询问：“是否更新 `60-Memory/now.md` 的阻塞项？”只有用户确认才写入，并更新 `updated` 日期；未确认时保持 now.md 不变。

## 手动结束摘要

报告分发数、待确认数、归档数、复盘路径、MIT 选择和活动 origin。若健康 JSON 有 nudge，追加一行可执行提醒。

---

## 自动模式（`--auto`）

全程不提问；需要选择时采取保守分支。自动模式只处理高/中置信日常分发、完成任务归档、自动草稿和明日建议，不写 60-Memory 下任何文件。

### 自动 Phase 0：读取

运行本 skill 前置数据中的两条脚本，读取当日日记、capture.md、active.md、项目文件和 active digest。若已有自动草稿，覆盖该段以保持幂等；手写 `## 复盘` 永不触碰。已有 `## 明日重点（建议）` 只作为本轮输入，不改 `## 今日重点 (MIT)`。

### 自动 Phase 1：保守分发

只分发 capture-rules §8 的高置信或中置信条目：

- `@项目名` 不存在时不建项目，去掉 `@` 但保留原文，并追加 `#待确认`；
- Someday 建议一律只追加 `#待确认`，不写入 someday；显式 `#someday` 按高/中置信规则分发；
- `#topic` / `#idea` 按 file-templates.md 建立文件，frontmatter `status: idea`；
- `#pause` 已在捕获时写入间隙日志，跳过；
- 低置信条目留在 `capture.md`，标签行追加一个 `#待确认`，已有该标签不重复；
- 其他目标按 capture-rules §8 和 §1-§7 写入，保持原文和来源。

自动分发不创建未知项目、不猜测类型、不因建议进入 someday。完成的自动分发条目从 capture.md 移除，待确认项保留。

### 自动 Phase 2：归档与自动草稿

把 `active.md` 中所有 `[x]` / `[X]` 归档到 `50-GTD/done.md`，格式见 file-templates.md，记录数量 K。

在当日日记写入或替换同名 `## 复盘（自动草稿 HH:MM）`，只覆盖该自动草稿区块。内容必须包括：

- 时间线摘要；
- 活动数据，标注 Claude / Codex origin；
- MIT 完成表；
- 项目进度；
- `patterns-digest.md` active 条目的精华预测对照，标为符合、相反或无关；
- `### 💭 感受` 下写 `> （待填写）`；
- `### 🔍 偏差分析` 只列事实，并写 `> （待确认）`；
- `### 💡 今日洞察` 写 `- [ ] 候选：…`，不写 `patterns.md`。

自动草稿的字段和标题以 file-templates.md 的自动草稿变体为准；不得写入任何 L0-L4 记忆文件。

### 自动 Phase 3：明日建议

不改 `## 今日重点 (MIT)`。写入或替换 `50-GTD/active.md` 中的 `## 明日重点（建议）- {明天}`，最多 3 条，按以下顺序排序：

1. 今日未完成 MIT；
2. 逾期任务；
3. 3 天内到期任务；
4. `#紧急` 任务；
5. 活跃项目任务。

该段首行必须是：

```markdown
> 自动建议，运行 o-review 确认后转正
```

候选去重，保留原任务文本和来源；没有候选时写“（无）”。不更新 now.md 或 60-Memory 下任何文件。

### 自动结束摘要

打印一段短摘要，至少包含：

```text
分发 N / 待确认 M / 归档 K / 建议 MIT {列表} / origin {claude、codex 或 mixed}
```

再列出跳过的低置信、未知项目和显式保留项。自动模式即使没有数据也要报告“无可用活动数据”，不要请求用户补充。
