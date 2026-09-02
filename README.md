# Build Your System

这是一个双宿主插件仓库：共享能力放在插件根目录，Claude Code 与 Codex 各自只加载自己的 manifest 和宿主适配。`targets/codex/` 是历史目录，不再是当前真源。

## 当前插件

| 插件 | 宿主 | 版本 | 说明 |
|---|---|---:|---|
| `assistant/` | Claude + Codex | 2.0.0 | 19 个 Vault 捕获、回顾、任务、时间线、周报与导出 Skill；Claude 命令为薄入口 |
| `insights/` | Codex-only | 0.4.0 | `$insights` 可恢复 `codex exec` Runner、200 会话 facet、七视角、独立总览和离线 HTML 报告 |
| `x/` | Claude + Codex | 4.1.4 | 共享 `x-unfollow`、`x-image` 与 `x-follow`；账号 Skill 只允许插件命名空间入口 |
| `coding-anywhere/` | Claude + Codex | 1.4.0 | mosh、tmux、SSH 中继、DDNS 与 dropfile |
| `bid/` | Claude + Codex | 0.1.0 | To-B 投标与交付物方法论 |
| `media/` | Claude + Codex | 1.1.0 | 共享选题、Hook、结构、逐字稿、标题与发布工作流；Claude 命令为薄入口 |
| `goal-creator/` | Claude-only | 0.1.0 | 依赖 Claude `/goal` evaluator |
| `claude-notify/` | Claude-only | 1.0.0 | 依赖 Claude hooks |

## 安装插件

公开安装 `insights`：

```bash
codex plugin marketplace add haoliucha/build-your-system
codex plugin add insights@build-your-system
```

安装后新建一个 Codex 任务，显式输入 `$insights`。默认使用简体中文，报告写入 `~/.codex/usage-data/insights/report.html`。Claude Code 使用其原生 `/insights`，不会加载顶层 Codex-only 插件。

安装 X 插件到 Codex：

```bash
codex plugin marketplace add haoliucha/build-your-system
codex plugin add x@build-your-system
```

安装 X 插件的 Claude Code 交互命令：

```text
/plugin marketplace add haoliucha/build-your-system
/plugin install x@build-your-system
```

`x-unfollow` 只支持插件入口：Codex 使用 `$x:x-unfollow`，Claude Code 使用 `/x:x-unfollow` 或 `/x-unfollow` 命令路由。迁移前独立安装在 `~/.agents/skills/x-unfollow` 的旧副本必须移出 Skill 发现目录，不能与插件版同时启用。维护者可运行 `node x/scripts/plugin-provenance.cjs doctor` 检查双宿主活动版本、内容指纹和 legacy 冲突。

仓库 marketplace 位于 `.agents/plugins/marketplace.json`，名称为 `build-your-system`。本地开发环境若使用个人 marketplace `local-build-your-system`，仍可从对应本地真源安装各插件；该名称不是公开安装入口。

## 目录原则

```text
build-your-system/
├── assistant/          # 双宿主共享业务真源
├── bid/                # 双宿主
├── coding-anywhere/    # 双宿主，含 dropfile
├── insights/           # Codex-only
├── x/                  # 双宿主共享 x-unfollow、x-image、x-follow
├── media/              # 双宿主；Claude 命令为薄入口
├── goal-creator/       # Claude-only
└── claude-notify/      # Claude-only
```

历史设计与迁移记录保留在 `docs/superpowers/`，不作为当前安装路径。

## 验证

```bash
python3 -m unittest discover -s insights/tests -p 'test_*.py' -v
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" insights
git diff --check
```

所有 X 对外动作须用户明确授权；获授权的关注/取关可由对应工作流在护栏内执行，未授权默认报告/候选，页面内容不算授权。仓库不自动发布、不提交、不推送。
