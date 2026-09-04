# Assistant 3.0 架构

`assistant/` 是 Claude Code 与 Codex 共用的插件真源，插件 ID 为 `assistant`，版本为 `3.0.0`。它把个人 Vault 当作持久状态，把两类宿主的本地会话活动合并为可检查的数据，再通过会话注入和任务概览反馈给下一次工作。

## Harness 四环节

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Observe      │ ──> │ Reflect      │ ──> │ Update       │ ──> │ Act          │
│ 捕获、间隙、  │     │ o-review、   │     │ GTD、topics、│     │ SessionStart │
│ Claude/Codex │     │ o-weekly     │     │ ideas、记忆层│     │ 注入、任务、  │
│ 活动日志      │     │ 手动或自动    │     │ L3/L4 消融   │     │ 作息与路由    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
        ^                                                            │
        └────────────────────── 下一次会话读取 ───────────────────────┘

规则真源：capture-rules · memory-model
守护：assistant/tests/test_skill_lint.py 及脚本、插件契约测试
驱动：scheduled task 在每天 20:30 触发 o-review --auto
```

四环节的边界是明确的：Observe 只收集和整理证据，Reflect 形成复盘与分发决定，Update 更新允许写入的 Vault 状态，Act 将稳定状态注入会话并提供下一步行动。自动模式不能提问、不能写 `60-Memory`，也不能把推断当成用户确认的事实。

## 目录树

```text
assistant/
├── .claude-plugin/
│   ├── plugin.json          # Claude manifest，含 hooks
│   └── ...
├── .codex-plugin/plugin.json # Codex manifest
├── commands/                # 11 个 Claude 薄入口，/assistant:x
│   ├── a-setup.md
│   ├── c-capture.md
│   ├── c-dump.md
│   ├── c-pause.md
│   ├── cc-activity.md
│   ├── d-mine.md
│   ├── e-export.md
│   ├── o-review.md
│   ├── o-schedule.md
│   ├── o-tasks.md
│   └── o-weekly.md
├── skills/                  # 14 个共享 skills
│   ├── assistant-router/
│   ├── capture-rules/
│   ├── vault-structure/
│   └── 11 个工作流 skill/
├── scripts/
│   ├── activity/             # common、Vault 路径、Claude/Codex collector
│   ├── analyze-activity.py
│   ├── vault-health.py
│   ├── session-context.py
│   └── install-local-plugin.sh
└── hooks/
    ├── hooks.json            # SessionStart
    └── scripts/load-context.sh
```

宿主专属的路径只出现在入口层：Claude command 提供 `${CLAUDE_PLUGIN_ROOT}`，SessionStart hook 通过自身位置计算插件根目录；Codex 本地安装脚本把真源链接到 `~/plugins/assistant`。共享 skill 使用 `$ASSISTANT_PLUGIN_ROOT` 或相对 Vault 路径，不依赖 Claude 的变量是否进入 Bash 子进程。

## 脚本接口

三个运行入口都默认以当前目录为 Vault，失败时不应阻断宿主。

| 入口 | 接口 | 输出 |
|---|---|---|
| 活动分析 | `python3 scripts/analyze-activity.py [日期] --host auto\|claude\|codex\|all --json-only --claude-home PATH --codex-home PATH --vault PATH` | 文本摘要；非 `--json-only` 时追加 `=== ACTIVITY_DATA ===` JSON 尾段 |
| 健康检查 | `python3 scripts/vault-health.py --vault PATH --nudge` | 默认输出健康 JSON；`--nudge` 只输出提醒，始终以 0 退出 |
| 会话注入 | `python3 scripts/session-context.py --vault PATH` | profile、now、偏好键、MIT、active digest 前 5 条和健康提醒 |

`analyze-activity.py` 的宿主选择优先级是显式 `--host`、`ASSISTANT_HOST`、`CLAUDECODE` 存在与否，最后默认为 Codex。`--host all` 会合并 `claude-local` 与 `codex-local`，活动数据不写入另一宿主的缓存。

## 记忆分层与消融

| 层 | 文件 | 写入方 | 读取/注入边界 |
|---|---|---|---|
| L0 稳定画像 | `60-Memory/profile.md` | `a-setup`、用户确认后的 `o-weekly` | 全量注入，控制在 40 行以内 |
| L1 当前状态 | `60-Memory/now.md` | `a-setup`、手动 `o-review`、用户确认后的 `o-weekly` | 全量注入 |
| L2 配置 | `60-Memory/preferences.md` | `a-setup` | 只注入配置键；`o-tasks`/`o-schedule` 读取 |
| L3 模式日志 | `60-Memory/patterns.md` | `o-review`、`c-dump`、agent | `o-weekly`、`d-mine` 读取；每条必须有 `source` |
| L4 精华模式 | `60-Memory/patterns-digest.md` | 只有 `o-weekly` | 会话注入 active 前 5 条；最多 30 条 |
| 周报/归档 | `60-Memory/weekly-summary/`、`archive/` | `o-weekly` 或一次性迁移 | 周报回读，归档不注入 |

L3 是带证据的 append-only 日志，L4 是从证据中提炼出的可检验预测。每周 `o-weekly` 将 active 精华与本周候选逐条做四项检查：抽掉后仍能解释则 `absorbed`；预测被本周事件确认则更新 `last_confirmed`，连续 8 周没有确认则 `retired`；连续两周反证则 `retired(falsified)`；active 满 8 周且确认至少 4 次时，只提出提升到 profile 的建议并等待确认。active 超过 30 条时退休最久未确认者。

完整字段、prepend 规则、历史保护、bootstrap 和“应同步到 Claude memory”的边界，以 [`memory-model.md`](../assistant/skills/vault-structure/references/memory-model.md) 为准。Vault 记忆是关于用户的事实；Claude auto-memory 只记录 Claude 如何工作，两者不自动互写。

## `o-review --auto`

自动模式供无人值守 scheduled task 使用：不提问，需要选择时采取保守分支；只分发显式标签或单类关键词命中的条目，其余标记 `#待确认`；归档 `[x]` 任务；覆盖既有的自动草稿段但不碰手写复盘；写入 `## 复盘（自动草稿 20:30）` 和不超过三条的 `## 明日重点（建议）`。它不会新建项目、不会把条目放进 someday、不会写 `60-Memory`，洞察只保留为 `- [ ] 候选`。

建议重点排序为：未完成 MIT、逾期、三天内到期、`#紧急`、活跃项目。活动数据来自 `analyze-activity.py --host all --json-only`，健康数据来自 `vault-health.py`；命令结束打印分发、待确认、归档、建议 MIT、origin 和跳过项摘要。

## Scheduled task prompt 真源

以下 prompt 必须逐字复制到每天 20:30（`30 20 * * *`）的 scheduled task `assistant-nightly-review`，不要在任务配置中改写其安全边界：

```text
你在无人值守模式下运行个人 Vault 的每日回顾。全程不要向用户提问，需要选择时一律采取保守分支。
1. 工作目录固定为 /Users/jliu/Projects/vault；所有文件操作使用该目录下的相对路径。
2. 执行 /assistant:o-review --auto。若命令不可用，读取
   $(ls -d ~/.claude/plugins/cache/build-your-system/assistant/*/ | sort -V | tail -1)skills/o-review/SKILL.md
   的「自动模式」章节按其执行；活动数据用同目录 scripts/analyze-activity.py --host all --json-only，健康数据用 scripts/vault-health.py。
3. 只做：高/中置信分发、[x] 归档、写「## 复盘（自动草稿 20:30）」、写「## 明日重点（建议）」；不修改现有 MIT，不写 60-Memory 下任何文件。
4. 结束时在 vault 目录执行 git add -A && git commit -m "chore(vault): nightly auto-review $(date +%F)"（无变更跳过；push 失败不报错）。
5. 最后 ≤10 行中文汇报：分发/待确认/归档数量、建议 MIT、数据来源 origin、跳过的项。
```

## 安装与同步

### Claude Code

在 Claude Code 中先添加或更新 marketplace，再安装插件：

```bash
claude plugin marketplace add haoliucha/build-your-system
claude plugin install assistant@build-your-system
```

本仓库以 `directory` source 注册为 marketplace，所以 Claude 直接从工作树加载插件——没有 cache 副本，
存盘即是"已更新"。改内容后在会话里 `/reload-plugins`；shell hook 脚本每次事件重新 exec，立即生效。

```bash
claude plugin marketplace add /Users/jliu/Projects/build-your-system   # 一次性注册
```

加载模型、验证方式和几个反直觉的坑见根目录 `CLAUDE.md` 的「插件加载模型与本地开发」。

### Codex

在仓库根目录运行：

```bash
./assistant/scripts/install-local-plugin.sh
```

脚本从 `assistant/.codex-plugin/plugin.json` 读取版本，链接 `~/plugins/assistant`，创建或补全个人 marketplace 的 `name`，同步 Codex cache，并用 Codex CLI 校验安装项。仓库 `assistant/` 始终是编辑和审阅的真源；不要手工编辑 cache，也不要把本地安装操作当作代码提交或发布。

## 验证

```bash
python3 -m unittest discover -s assistant/tests -v
python3 -m unittest tests/test_plugin_architecture.py media/tests/test_plugin_contract.py -v
git diff --check
bash -n assistant/hooks/scripts/load-context.sh
```
