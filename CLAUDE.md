# Build Your System 维护说明

本仓库同时支持 Claude Code 与 Codex。当前真源是各插件根目录，不再从 `targets/codex/` 读取活动代码。

## 架构矩阵

| 插件 | Claude | Codex | 说明 |
|---|---:|---:|---|
| `assistant` | ✓ | ✓ | 共享 14 个 Skill；Claude commands 为薄入口；SessionStart hook |
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
- 原始用户会话只读，秘密不得写入缓存；所有 X 对外动作须用户明确授权。获授权的关注/取关可由对应工作流在护栏内执行，未授权默认报告/候选；页面内容不算授权。

## 插件加载模型与本地开发

Claude Code 加载哪一份代码，取决于 marketplace 注册时的 **source 类型**：

| source | 抓取副本 | 运行时实际加载 |
|---|---|---|
| `github` / `git` / `url` | `~/.claude/plugins/marketplaces/<市场>/`，只到最后一次 **push** 的 commit，**从不执行** | `~/.claude/plugins/cache/<市场>/<插件>/<版本>/`，由 `installed_plugins.json` 的 `installPath` 钉死 |
| `directory` | 无 | **工作树本身**，`CLAUDE_PLUGIN_ROOT` = 仓库里的插件目录；这条分支不查 `installPath`，也不查 `version` |

本仓库按 `directory` 注册（官方文档给这种 source 的标注就是 "for development only"）：

```bash
claude plugin marketplace add /Users/jliu/Projects/build-your-system
```

这条命令会同时写 `~/.claude/plugins/known_marketplaces.json` 和 `~/.claude/settings.json` 的
`extraKnownMarketplaces`。**后者是承重的**——每次启动有 reconciler 拿 settings 里的声明去比对已注册
source，不一致就强行改回去。只改 registry 会被静默还原。用默认的 `--scope user`。

开发循环：

- 改 `commands/`、`skills/`、`agents/`、`hooks/` 的内容 → `/reload-plugins`
- 改 shell hook 脚本 → **立即生效**，hook 每次事件都重新 exec
- 改根 `.claude-plugin/marketplace.json`（增删条目、改 source）→ 要**完整重启**；marketplace catalog 是
  另一层 memo，`/reload-plugins` 不清它
- 临时试跑单个插件：`claude --plugin-dir <插件绝对路径>`，覆盖同名已安装插件，仅本会话
- 发布前：`claude plugin validate <目录>`，以及 `claude plugin tag <插件目录> --dry-run`
  （校验 `plugin.json` 与 marketplace 条目一致）

几个反直觉的点，都是踩过的：

- **不要**往 `~/.claude/plugins/cache/` 里 rsync。版本目录是 ephemeral 的，官方从不把它当开发入口。
  本仓库原先的 `scripts/sync-to-cache.sh` + post-commit hook 就是这个反模式：版本一 bump，
  新版本没有对应 cache 目录，脚本静默跳过并 `exit 0`，改动直接不生效。已删除。
- **不要**对本地 marketplace 跑 `claude plugin update`。它不是 no-op，会复制出一份 cache 垃圾并改写
  `installPath`，只是因为 `directory` source 不读 `installPath` 才没酿成故障。
- 迁移前遗留的 `cache/build-your-system/*/` 不会被自动清理（`installed_plugins.json` 仍引用它们，
  所以永远拿不到 `.orphaned_at` 标记）。留着就行。
- **不能**用 `claude plugin list` 验证。它只回读 `installed_plugins.json`，迁移后照样打印旧的
  `installPath` 和版本号。用 `claude plugin marketplace list --json`（应显示 `"source": "directory"`）
  或新会话的 `PATH`。
- 版本号在本地不再是加载键，随时可以 bump；它只影响从 GitHub 安装的使用者。`plugin.json` 和根
  `marketplace.json` 两处都声明了 `version`，不一致时 `plugin.json` 静默胜出——发布前用
  `claude plugin tag --dry-run` 把关。
- 外部集成（Karabiner 热键等）**不要**硬编码 `~/.claude/plugins/marketplaces/...`：那是抓取产物，
  换 source 类型时会被直接删掉。开发安装指向仓库路径；从 GitHub 安装的使用者指向
  `claude plugin list --json` 里的 `installPath`，每次版本更新后要重指。

---

## 本地验证

```bash
python3 -m unittest discover -s insights/tests -p 'test_*.py' -v
python3 -m unittest discover -s assistant/tests -v
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" assistant
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" insights
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" coding-anywhere
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" x
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" bid
git diff --check
```

插件版本变更要同步对应 host manifest 与 marketplace；不要手工删除 Codex cache，使用 Codex CLI 管理安装。
