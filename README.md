# Build Your System

个人效率系统插件仓库,"单仓多目标"结构:Claude Code 插件(marketplace)在仓库根目录,Codex 目标在 `targets/codex/` 下统一版本管理。

## 当前目标

| 宿主 | 目标 | 版本 | 说明 |
|------|------|------|------|
| Claude Code | `assistant/` | 1.0.0 | 个人 AI 助手:任务捕获、每日回顾、知识分发(基于 Obsidian Vault) |
| Claude Code | `media/` | 1.0.0 | 短视频创作工作流:选题评估、Hook 设计、逐字稿生成 |
| Claude Code | `claude-notify/` | 1.0.0 | macOS 通知与跳转辅助(任务完成/需要权限时提醒) |
| Claude Code | `x/` | 1.0.2 | X (Twitter) 增长工具集:`/x:x-follow` 精准批量关注、`/x:x-unfollow` 关注卫生、**`/x:cover` 文章封面一键生成**(codex/gpt-image-2 直出 2.5:1 含中文整张 + 门禁 + QC) |
| Claude Code | `goal-creator/` | 0.1.0 | `/goal` 命令提示词工程辅助(引导式 brainstorm) |
| Claude Code | `coding-anywhere/` | 1.0.0 | 远程开发栈:mosh + tmux + SSH 中继一键搭建 |
| Claude Code | `bid/` | 0.1.0 | To-B 投标/交付物方法论:单一真源生成器、口径级联、成本/排期、对抗审校、去AI味、图表与中文PDF管线;10 skills + 6 命令(`/bid:init·meeting·sync·handoff·review·status`),附 HTML 方法论导读(含系统动态演示) |
| Codex | `targets/codex/build-your-system-assistant/` | — | Obsidian Vault 助手的 Codex 适配版 |

## 为什么是单仓多目标

- `build-your-system` 作为唯一 source of truth
- 停止维护独立的 `build-your-system-codex` 副本
- 保留各宿主自己的包装层,不强行合并为同一原生插件格式
- 后续接入 Cursor 或 MCP 共享层可在同一仓库演进

## 安装方式

### Claude Code

```bash
# 在 Claude Code 中运行
/plugin

# Add Marketplace:
haoliucha/build-your-system

# 然后安装需要的插件:
# assistant / media / claude-notify / x / goal-creator / coding-anywhere
```

### Codex

Codex 目标位于 `targets/codex/build-your-system-assistant`,仓库内已提供 repo marketplace(`.agents/plugins/marketplace.json`)。本机直接安装:

```bash
cd targets/codex/build-your-system-assistant
./scripts/install-local-plugin.sh
```

## 首次设置

- **assistant(Claude Code)**:在 Vault 目录里运行 `/a-setup`。推荐 Vault 结构:`00-Inbox / 10-Projects / 20-Areas / 30-Resources / 40-Archives / 50-GTD / 60-Memory`。
- **Codex**:在 Vault 目录用自然语言触发,详见 `targets/codex/build-your-system-assistant/README.md` 与 `docs/user-guide.md`。
- 各插件的用法见对应目录的 `README.md`(如 `x/README.md`)。

## 仓库结构

```text
build-your-system/
├── .claude-plugin/
│   └── marketplace.json          # Claude marketplace(插件清单 + 版本)
├── .agents/
│   └── plugins/marketplace.json  # Codex repo marketplace
├── assistant/                    # Claude 插件(下同:.claude-plugin/ + commands/ + skills/)
├── media/
├── claude-notify/
├── x/                            # x-follow / x-unfollow / cover(封面一键生成)
├── goal-creator/
├── coding-anywhere/
├── targets/codex/build-your-system-assistant/
├── scripts/
│   ├── sync-to-cache.sh          # 源码 → Claude Code 运行时 cache
│   └── githooks/post-commit      # 提交后自动跑 sync(见下)
├── examples/minimal-vault/
└── docs/
```

## 开发说明(改插件必读)

1. **本地统一路径 = `~/Projects/build-your-system`**;git 身份 haoliucha(origin 走 SSH alias `github.com-haoliucha`)。
2. Claude Code **不直接加载本仓库**,它按 `~/.claude/plugins/installed_plugins.json` 钉死的版本目录加载 `~/.claude/plugins/cache/build-your-system/<plugin>/<version>/`。改完源码必须同步:
   ```bash
   bash scripts/sync-to-cache.sh   # 只同步本机已安装且版本目录存在的插件
   ```
3. **自动同步 hook**(每个 clone 启用一次,之后每次 commit 自动同步):
   ```bash
   git config core.hooksPath scripts/githooks
   ```
4. **版本纪律**:插件有实质变更 → bump `<plugin>/.claude-plugin/plugin.json` 的 `version`,并同步根 `.claude-plugin/marketplace.json` 对应条目(两处都要改)。注意:bump 后 cache 里还没有新版本目录,`sync-to-cache.sh` 会跳过该插件——本机立即生效需 push 后走 `/plugin` 更新,或手动把源码 rsync 进当前钉死的版本目录。
5. Codex 相关改动落在 `targets/codex/build-your-system-assistant/`;Claude 与 Codex 尚未共享同一套内部实现,共享 core/脚本/MCP 层是下一阶段。

## 许可证

MIT License - 见 [LICENSE](LICENSE)
