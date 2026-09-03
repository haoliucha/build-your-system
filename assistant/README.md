# Assistant

`assistant/` 是 Claude Code 与 Codex 共用的个人助手插件真源，插件 ID 统一为 `assistant`，版本 `3.0.0`。

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
| `scripts/analyze-activity.py` | 活动分析；`[日期] --host auto\|claude\|codex\|all --json-only --claude-home PATH --codex-home PATH --vault PATH` |
| `scripts/vault-health.py` | Vault 健康 JSON；`--vault PATH --nudge` |
| `scripts/session-context.py` | 会话启动上下文；`--vault PATH` |

完整架构、目录约定、记忆层和安装流程见 [`docs/assistant-architecture.md`](../docs/assistant-architecture.md)。

Insights 和 X 关注卫生不属于本插件：Codex 的 `$insights` 位于顶层 `insights/`，`x-unfollow` 位于顶层 `x/`；Claude 继续使用原生 `/insights`。

安装 Codex 版本：

```bash
./scripts/install-local-plugin.sh
```
