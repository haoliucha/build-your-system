# Assistant 当前架构

`assistant/` 是 Claude Code 与 Codex 共用的插件根目录，ID 统一为 `assistant`，版本 `2.0.0`。共享业务在 `skills/`；Claude 的 15 个 `/assistant:*` 文件只负责参数透传；Codex 使用 Skill 入口。

```text
assistant/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── commands/                 # Claude 薄入口
├── skills/                   # 19 个共享工作流，唯一真源
├── scripts/                  # 宿主活动分析适配
└── hooks/                    # Claude-only hooks
```

活动分析由 `skills/vault-structure/references/host-adaptation.md` 分流：Codex 读取自己的本地会话，Claude 使用 Claude 数据源。`insights/` 不在 Assistant 中，Codex 的 `$insights` 位于顶层 Codex-only 插件；`x-unfollow` 也不再复制到 Assistant。

本地 Codex 入口为 `~/plugins/assistant`，缓存版本为 `~/.codex/plugins/cache/local-build-your-system/assistant/2.0.0`。这些目录由 Codex CLI 管理，仓库真源始终是 `assistant/`。
