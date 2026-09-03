---
name: o-weekly
description: 扫描本周 Vault 内容生成周报，并按记忆层规范执行精华模式消融；支持首次 digest 引导迁移。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 每周整合

参数为 `--bootstrap-digest` 或空参数。周范围使用 ISO 周：周一至周日。周报保存到
`60-Memory/weekly-summary/{年}W{周}.md`，模板见 file-templates.md。

## 步骤 0：回读上周记忆记录

找到上周周报，回读其中的 `## 记忆消融记录` 与 `## 记忆更新建议`。没有上周周报时记录“无上周记录”，不要补写历史。

## 步骤 1：读取本周数据

扫描本周日记、`50-GTD/active.md`、`50-GTD/done.md` 和 `00-Inbox/capture.md`。

## 步骤 2：整理本周事实

提取完成事项、未完成事项、项目进展、捕获想法、洞察和下周候选重点。日记中的间隙日志是证据，不直接改写成模式。

## 步骤 3：生成周报主体

按周报模板写本周范围、亮点、完成事项、待跟进、想法收集和下周展望。所有结论链接到可追溯的日期或文件。

## 步骤 4：补充活动证据

逐日运行活动入口并保存摘要：

```bash
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/analyze-activity.py" [日期] --host all --json-only
```

`ASSISTANT_PLUGIN_ROOT` 由宿主提供，见 vault-structure/references/host-adaptation.md。将活动摘要与间隙日志、done 条目对照；保留 origin，不把活动消息数当作产出量。

## 步骤 5：记忆消融循环

本步骤按 `vault-structure/references/memory-model.md` 逐字执行，`patterns-digest.md` 是唯一写入方。

### 输入

构造证据集 E：

- 本周日记中的复盘与间隙日志；
- `analyze-activity.py` 逐日 `--host all` 的摘要；
- `50-GTD/done.md` 本周条目；
- `60-Memory/patterns.md` 本周新条目。

同时读取当前精华集合 D：`60-Memory/patterns-digest.md` 的所有条目。归纳本周候选集合 C，逐条处理 D ∪ C。

### 四项检验

| 检验 | 动作 |
|---|---|
| 冗余 | 抽掉该条后本周事件仍被其余模式解释，标为 `absorbed→P-0xx`，合并 evidence 与 sources。 |
| 必要 | 本周出现符合 `predicts` 的事件，更新 `last_confirmed`；连续 8 周无符合事件，标为 `retired(silent)`。 |
| 反证 | 事件与 `predicts` 相反，记录 `counter_evidence`；连续 2 周成立，标为 `retired(falsified)`。 |
| 提升 | active 至少 8 周且 confirmed 至少 4 次，提出 `promoted→profile`；必须用户确认，不能自动写 profile。 |

active 超过 30 条时，按 `last_confirmed` 最旧者退休，保留状态变更日期和来源。历史 L3/L4 原文不改写；新条目和状态证据按 memory-model.md 的 prepend / 历史保护规则处理。

在周报写入：

```markdown
## 记忆消融记录

| 条目 | 检验 | 结论 | 证据 |
|---|---|---|---|
| P-001 · {标题} | 必要 | {结论} | {日期与来源} |
```

然后按 L4 条目格式写回 `60-Memory/patterns-digest.md`，active 总数不超过 30。

## 步骤 6：记忆更新建议

在周报写入 `## 记忆更新建议`，每层最多 3 条，只建议不落盘：

```markdown
| 层 | 建议 | 应同步到 Claude memory |
|---|---|---|
| profile | {最多 3 条或无} | 是/否，理由 |
| now | {最多 3 条或无} | 是/否，理由 |
| preferences | {最多 3 条或无} | 是/否，理由 |
| tag-mapping | {最多 3 条或无} | 是/否，理由 |
```

不得因该列自动修改 Claude memory、profile、now、preferences 或 tag-mapping。

## `--bootstrap-digest` 模式

当 `patterns-digest.md` 不存在或为空时，读取全部 `60-Memory/patterns.md`，按主题聚类。每簇合成 1 条 digest 条目：`evidence` 取各来源日期，`sources` 链接原 L3 条目。

逐簇向用户确认后才写入；未确认簇不得标为 active。日志原文不动，没有可靠证据的簇不强行合并。确认后的条目使用 memory-model.md 的完整 L4 字段和递增 P 编号。

## 结束

报告周报路径、证据日期范围、消融条数、待确认提升数和 digest active 数。没有数据时仍生成最小周报并明确标注。
