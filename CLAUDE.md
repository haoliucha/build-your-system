# Build Your System 维护说明

本仓库同时支持 Claude Code 与 Codex。当前真源是各插件根目录，不再从 `targets/codex/` 读取活动代码。

## 架构矩阵

| 插件 | Claude | Codex | 说明 |
|---|---:|---:|---|
| `assistant` | ✓ | ✓ | 共享 19 个 Skill；Claude commands 为薄入口 |
| `bid` | ✓ | ✓ | 共享业务实现 |
| `coding-anywhere` | ✓ | ✓ | 共享远程开发与 dropfile |
| `insights` | — | ✓ | Codex `$insights`，Claude 使用原生 `/insights` |
| `x` | ✓ | ✓ | 共享 `x-unfollow`、`x-image` 与 `x-follow` |
| `media` | ✓ | ✓ | 共享 12 个创作 Skill；Claude 命令为薄入口 |
| `goal-creator` | ✓ | — | 依赖 Claude `/goal` evaluator |
| `claude-notify` | ✓ | — | 依赖 Claude hooks |

## 修改规则

- 共享业务只改插件根目录的 `skills/`、`scripts/` 和文档；不要复制到 `targets/codex/`。
- 宿主适配放在 manifest、薄 command 或 `claude-components/`；通过 `references/host-adaptation.md` 说明来源和参数。
- `insights/` 是 Codex-only，禁止添加 `.claude-plugin` 或 Claude command。
- `x/skills/x-unfollow` 与 `x/skills/x-follow` 都是双宿主共享业务源；Claude 的 `/x-follow` 仅为共享 Skill 的薄命令入口。
- 原始用户会话只读，秘密不得写入缓存；所有 X 对外动作由用户手动执行。

## 本地验证

```bash
python3 -m unittest discover -s insights/tests -p 'test_*.py' -v
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" assistant
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" insights
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" coding-anywhere
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" x
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" bid
git diff --check
```

插件版本变更要同步对应 host manifest 与 marketplace；不要手工删除 Codex cache，使用 Codex CLI 管理安装。
