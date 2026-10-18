# Assistant

`assistant/` 是 Claude Code 与 Codex 共用的个人助手插件真源，插件 ID 统一为 `assistant`，版本 `3.1.1`。

共享 `skills/` 保存 14 个 skills，其中 11 个工作流由 Claude 命令和 Codex 自然语言路由共同使用。Claude 的 `/assistant:x` 命令只是薄入口；Codex 用自然语言触发同名 skill。SessionStart hook 注入会话上下文，活动与健康数据由本插件脚本生成。

## 命令与 Skill

| 工作流 | Claude Code | Codex |
|---|---|---|
| `a-setup` | `/assistant:a-setup` | 自然语言触发 `a-setup` |
| `c-capture` | `/assistant:c-capture` | 自然语言触发 `c-capture` |
| `c-dump` | `/assistant:c-dump` | 自然语言触发 `c-dump` |
| `c-pause` | `/assistant:c-pause` | 自然语言触发 `c-pause` |
| `cc-activity` | `/assistant:cc-activity` | 自然语言触发 `cc-activity` |
| `d-mine` | `/assistant:d-mine` | 自然语言触发 `d-mine` |
| `e-export` | `/assistant:e-export` | 自然语言触发 `e-export` |
| `o-review` | `/assistant:o-review` | 自然语言触发 `o-review` |
| `o-schedule` | `/assistant:o-schedule` | 自然语言触发 `o-schedule` |
| `o-tasks` | `/assistant:o-tasks` | 自然语言触发 `o-tasks` |
| `o-weekly` | `/assistant:o-weekly` | 自然语言触发 `o-weekly` |

`assistant-router`、`capture-rules`、`vault-structure` 是共享规则与路由 skills，不单独对应命令。

## 脚本

| 入口 | 作用与主要参数 |
|---|---|
| `scripts/analyze-activity.py` | 活动分析；`[日期] --host auto\|claude\|codex\|all --json-only --claude-home PATH --codex-home PATH --vault PATH`；输出时间线外加 `goals` / `flow` / `unplanned` / `mit.progress`（目标分组、MIT 关联、估算时长） |
| `scripts/vault-health.py` | Vault 健康 JSON；`--vault PATH --nudge` |
| `scripts/session-context.py` | 会话启动上下文；`--vault PATH` |

完整架构、目录约定、记忆层和安装流程见 [`docs/assistant-architecture.md`](../docs/assistant-architecture.md)。

Insights 和 X 关注卫生不属于本插件：Codex 的 `$insights` 位于顶层 `insights/`，`x-unfollow` 位于顶层 `x/`；Claude 继续使用原生 `/insights`。

## 安装范围：只装在 Vault 里

**Vault = 在项目级安装了 assistant 的目录**，可以有一个或多个。assistant 不全局安装：全局安装会让每个项目的会话都跑 SessionStart hook。hook 也只认安装记录（`.claude/settings*.json` 或 `.codex/config.toml` 启用了 assistant），不看目录结构；其他目录静默退出。

Claude Code（在 Vault 目录里执行，写入该项目的 `.claude/settings.json`）：

```bash
claude plugin install assistant@build-your-system --scope project
```

Codex：全局 `~/.codex/config.toml` 不写 assistant 条目（不写即视为未安装），只在每个 Vault 的 `.codex/config.toml` 写 `[plugins."assistant@build-your-system"] enabled = true`（项目需在 Codex 中为 trusted）。在 Vault 内外分别跑 `codex plugin list`，应分别显示 `installed, enabled` / `not installed`。注意 `codex plugin add`（含升级重装）会往全局写入 `enabled = true`，add 后要删掉这个全局条目。

安装 Codex 版本：

```bash
./scripts/install-local-plugin.sh
```

## 双宿主脚本调用

活动分析默认采集 Claude Code 与 Codex；`--host auto` 仅保留为显式兼容选项。先从已加载技能定位插件目录，再用 `scripts/run-script.py` 运行分析、健康或上下文脚本，运行器会在同一次调用中校验并设置根目录。无需启用 SessionStart hook。

报告包含分宿主 `source_health`：采集不可用不能当作当天无活动。当前 Vault 的插件停用声明优先；停用 media 时不恢复其动作或创建替代产线。


## 双宿主一致性

Claude Code 的 command 和 Codex 的 skill 入口都调用同一套 `skills/` 与 `scripts/`。每个技能主动读取当前 Vault 的 `60-Memory/preferences.md`；「工作流边界」保存该 Vault 的启用/停用等选择，`session-context.py` 也原样展示该章节。无需开启 hook，无需额外的宿主指令文件，也不从任何宿主私有记忆补齐配置。宿主安装缓存的版本与内容仍需分别验证，源码修改不等于已安装版本更新。


## 初始化共享入口

安装插件不改目标 Vault。运行 `a-setup` 时，使用 `scripts/setup-entrypoints.py --apply` 从 `templates/AGENTS.md` 创建或更新 Assistant 托管区块，并建立 `CLAUDE.md -> AGENTS.md` 相对软链接。标记外内容逐字保留；独立正文、异常链接或损坏标记先报告冲突。`--check`（默认）只读校验，退出码 0/1/2 分别表示一致/待更新/冲突或错误。模板不包含个人信息、浏览器配置或默认 Git 发布策略。


## 运行时文案边界

生成的工作区指令只回答“这里做什么、读什么、遵守什么”。跨宿主兼容、链接关系、安装路径及区块更新机制由初始化实现和维护文档处理，不写进运行时指令正文，也不以独立的“插件说明”章节增加使用负担。机器维护标记仍用于限定更新范围，正文无需解释这些标记。
