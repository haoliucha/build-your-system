# Assistant 使用指南

## Codex

安装后通过自然语言或 `/skills` 选择 Assistant 工作流：捕获、脑暴、间隙记录、每日回顾、任务概览、周报、选题挖矿和对话导出。

```bash
codex plugin add assistant@local-build-your-system
python3 "$HOME/plugins/assistant/scripts/analyze-activity.py" --host codex
```

需要复盘历史 Codex 会话时，显式使用顶层 `insights` 插件的 `$insights`，不要把 Insights 逻辑塞回 Assistant。

## Claude Code

Claude 使用 `/assistant:a-setup`、`/assistant:c-capture`、`/assistant:o-review` 等命名空间命令；命令只做参数透传，业务流程由同一份共享 Skill 提供。Claude 的 `/insights` 仍使用 Claude 原生实现。

## Vault 真源

Vault 路径、Inbox、Memory、GTD 和对话导出规则以 `skills/vault-structure/` 与当前 Vault 配置为准。宿主适配不改变这些业务路径，也不把宿主的原始会话路径写入另一宿主的缓存。
