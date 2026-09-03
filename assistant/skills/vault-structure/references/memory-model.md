# 记忆层规范

本规范定义 60-Memory/ 如何承载关于用户的事实、当前状态、配置和可验证模式。记忆层是 Update 环节的本体；所有路径相对于 Vault 根目录。

## 分层总表

| 层 | 文件 | 写入方 | 读取方 | 是否注入 |
|---|---|---|---|---|
| L0 稳定画像 | profile.md，不超过 40 行 | a-setup 按章节 upsert；o-weekly 提升前需确认 | 所有需要了解用户的工作流 | 是，全量注入 |
| L1 当前状态 | now.md，三条主线、截止与阻塞，带 updated | a-setup；手动 o-review；o-weekly 确认后更新 | o-tasks、o-schedule、复盘与会话上下文 | 是，全量注入 |
| L2 配置 | preferences.md，YAML 键 wake deep_work end_work bedtime language penalty_per_day | a-setup | o-schedule、o-tasks 与会话上下文 | 是，只注入配置键 |
| L3 日志 | patterns.md，统一格式、历史不改写 | o-review、c-dump、agent | o-weekly、d-mine | 否，先由周报加工 |
| L4 精华 | patterns-digest.md，最多 30 个 active | 只有 o-weekly | 会话上下文、o-review 偏差分析、agent | 是，只注入 active 前 5 |
| 周报 | weekly-summary/{年}W{周}.md，含消融记录 | o-weekly | o-weekly 回读上周 | 否 |
| 归档 | archive/ | 一次性迁移或过期 profile 迁移 | 审计或人工查阅 | 否 |

L3 是证据日志，L4 是经消融后的可复用精华。L0、L1、L2、L4 的注入都必须遵守各自的上限和字段边界，不用注入代替写入确认。

## L3 与 L4 条目格式

以下两栏示例保留统一字段名：

~~~text
patterns.md                        patterns-digest.md
### 2026-09-03 · 标题               ### P-023 · 标题
tags: #productivity                 status: active | absorbed→P-0xx | retired(原因) | promoted→profile
source: [[2026-09-03]] 复盘         predicts: 可观测的行为预测
正文 ≤8 行                          evidence: 2026-01-05, 2026-01-15, 2026-09-02
                                    sources: [[patterns#2026-01-05 · …]]
                                    last_confirmed: 2026-W35
~~~

### L3 patterns.md

- 标题格式为 ### YYYY-MM-DD · 标题。
- 必须有 tags: 与 source:；source: 指向产生这条事实的复盘、日记或其他来源。
- 正文最多 8 行，描述可观察事实或模式，不写未经证实的性格判断。
- 每次写入必须带日期；新条目 prepend 到文件顶部，历史条目不改写、不重新排序。这种 append-only 语义表示只增加新日志，不回写历史证据。

### L4 patterns-digest.md

- 标题使用 ### P-001 · 标题 形式，id 形如 P-001，递增且不复用。
- 必须有 status:、predicts:、evidence:、sources:、last_confirmed:。
- status 只能取：active、absorbed→P-0xx、retired(原因)、promoted→profile。
- evidence 记录各来源日期，sources 链接回 L3 具体条目；每次状态或证据更新必须带日期。
- 新建或更新的 digest 条目由 o-weekly prepend；历史条目不改写。active 条目总数最多 30。

## Prepend 与历史保护

所有需要保留倒序的日志和目标文件，新增内容写在现有内容之前；月度 GTD 文件则写入当月 ## YYYY-MM 分组的最前面。不要为了排序而改写历史 L3/L4 条目。若条目状态改变，只新增状态证据或按规范记录新的状态，不抹去旧来源。

## 记忆消融循环

o-weekly 第 5 步对“精华 ∪ 本周候选”逐条执行四项检验。一条模式存在的理由是它解释证据；抽掉后证据仍能被其他模式解释，就说明它可能冗余。

| 检验 | 判定与动作 |
|---|---|
| 冗余 | 抽掉后本周事件仍可被其余模式解释 → absorbed，并在 digest 指向保留的 P-0xx。 |
| 必要 | 本周出现符合 predicts 的事件 → 更新 last_confirmed；连续 8 周没有符合事件 → retired。 |
| 反证 | 事件与 predicts 相反，且连续 2 周成立 → retired(falsified)。 |
| 提升 | active 至少 8 周且确认至少 4 次 → 只提出提升到 profile 的建议，必须由用户确认。 |

active 超过 30 条时，按 last_confirmed 最旧者退休；退休原因写入 retired(原因)。退休条目可以在新证据出现后复活，但复活也要保留状态变更日期与来源，不能删除历史记录。

## 周报中的消融与更新建议

每份周报都必须有以下两个区块：

~~~markdown
## 记忆消融记录

| 条目 | 检验 | 结论 | 证据 |
|---|---|---|---|
| P-001 · {标题} | 冗余/必要/反证/提升 | {结论} | {日期与来源} |

## 记忆更新建议

| 层 | 建议 | 应同步到 Claude memory |
|---|---|---|
| profile | {最多 3 条} | 是/否，理由 |
| now | {最多 3 条} | 是/否，理由 |
| preferences | {最多 3 条} | 是/否，理由 |
| tag-mapping | {最多 3 条} | 是/否，理由 |
~~~

profile、now、preferences、tag-mapping 每层建议最多 3 条；没有建议时写“无”。“应同步到 Claude memory”只是审阅列，不是自动同步指令。

## --bootstrap-digest 首次迁移

首次运行 o-weekly --bootstrap-digest 时，把既有 patterns.md 的历史日志（当前计划估计约 1110 行）按主题聚类；每个主题簇只提出一条 L4 digest，evidence 取该簇各来源的日期，sources 链接每个代表性 L3 条目。逐簇向用户确认后才写入 patterns-digest.md，不把未经确认的簇标为 active。迁移过程中日志原文不动；没有可靠证据的簇不强行合并。

## 写入策略

- --auto 不写 L0 profile.md、L1 now.md、L2 preferences.md 或 L4 patterns-digest.md。
- --auto 允许按规则处理日常分发和复盘草稿，但不把自动推断写成记忆。
- L3 每次写入必须带 source:，并带产生日期；缺 source 就留在待确认区，不写入 patterns.md。
- L4 只能由 o-weekly 维护；提升 profile 或 now 必须用户确认。
- 所有记忆写入使用相对 Vault 根目录的路径，并保留来源链接。

## 边界与不自动同步

- Vault 记忆层记录“关于用户的事实”。
- Claude auto-memory 记录“Claude 怎么干活”。两者用途不同，不自动同步。
- 60-Memory/profile.md 末尾保留这一行指针：Claude memory：~/.claude/projects/-Users-jliu-Projects-vault/memory/MEMORY.md。
- 不因周报的“应同步到 Claude memory”列自动改写 Claude memory；需要同步时由用户或对应宿主明确执行。
- Lodestar 不接入本记忆层。
