# 宿主适配契约

当前目录就是 Vault 根目录。业务流程共享；插件脚本的位置与当前目录分别确定，不能互相代替。

## 当前 Vault 的边界

每个技能执行前主动读取当前 Vault 的 `60-Memory/preferences.md`，包括作息配置与「工作流边界」章节；缺失时采用技能的默认行为，不能从某一宿主的私有记忆补出配置。用户当前明确指令优先。

这里的 `60-Memory/` 是 Vault 自己的共享数据目录，两个宿主读取相同文件；它不是 Codex 或 Claude 的私有记忆。插件不要求 `AGENTS.override.md`、`AGENTS.md` 或 `CLAUDE.md` 存在，也不把这些宿主入口当作插件业务配置。宿主已经提供的项目约束仍然遵守。

通用流程、路径定位与缺省行为在本插件的共享 skills/scripts 中维护；Vault 专属选择只在共享配置中维护。不得把本轮对话、Codex 私有记忆或 Claude auto-memory 作为运行所需依赖。领域标签只是分类，不代表插件启用或动作授权。

当 media 插件被明确停用：保留普通捕获、任务、标签和状态整理；跳过发布检查、断更与惩罚计算、选题挖掘、旧选题目录写入和插件交接。不建议安装或恢复，不在 Assistant 中实现替代产线。`#topic` 保留原捕获，复盘不重复追加或分发；不迁移或清空历史文件。其他 Vault 未停用时继续使用原有规则。

SessionStart hook 的目录检测与上下文注入是可选能力；用户未启用时保持原状态。所有手动技能和下列脚本入口均不依赖 hook。

## 同一次调用内定位并运行脚本

从当前已加载 `SKILL.md` 的实际路径定位所属插件根目录（包含 `.codex-plugin/plugin.json` 和 `scripts/`）。不要猜测缓存版本，不把工作目录当作插件目录。

使用该实际根目录下的 `scripts/run-script.py`，将下面示例中的 `<已加载插件根目录>` 替换成已观察的绝对路径：

```bash
python3 "<已加载插件根目录>/scripts/run-script.py" analyze-activity.py [YYYY-MM-DD] --host all --json-only
python3 "<已加载插件根目录>/scripts/run-script.py" vault-health.py
python3 "<已加载插件根目录>/scripts/run-script.py" session-context.py
python3 "<已加载插件根目录>/scripts/run-script.py" setup-entrypoints.py --check
```

运行器在同一进程环境中校验并设置 `ASSISTANT_PLUGIN_ROOT`，然后执行目标脚本：

1. 指定了 `--plugin-root` 或非空 `ASSISTANT_PLUGIN_ROOT` 时使用该路径；无效则明确报错，不静默改用另一份插件。
2. 未显式指定时，从运行器自身位置定位插件根目录；这覆盖源码、安装缓存以及路径含空格的情况。
3. 仅当上述隐式位置无效时，检查 `$HOME/plugins/assistant` 兼容路径。校验插件名和目标脚本后才使用。

不要假设前一次 shell 中设置的变量会传到下一次调用。不要直接运行空变量展开后的 `/scripts/…`。

Claude 薄 command 中的 `${CLAUDE_PLUGIN_ROOT}` 是宿主展开的路径提示，不保证存在于普通 Bash 环境。需要显式传入时使用运行器的 `--plugin-root` 参数。Codex 同样可以直接使用已加载技能所属的插件路径，无需设置全局环境变量或启用 hook。

入口维护仅由 `a-setup` 显式使用 `setup-entrypoints.py --apply` 写入；安装插件、普通工作流和只读 `--check` 都不会创建或更新入口。模板在插件 `templates/AGENTS.md`，写入规则见 `a-setup`。

## 活动来源与完整性

`analyze-activity.py` 无参数默认采集 Claude Code 与 Codex；工作流显式传入 `--host all`。

- `all`：双侧汇总，顶层 `origin: mixed`，逐条保留 `claude-local` / `codex-local`。
- `claude` / `codex`：只采集指定侧，用于诊断。
- 显式 `auto`：保留兼容语义，优先读取 `ASSISTANT_HOST`，否则存在 `CLAUDECODE` 时选择 Claude，其他情况选择 Codex。该环境设置不改变默认双侧采集。

Codex 从活动与归档 rollout 读取用户消息，兼容 history；系统注入不算活动。同一消息的不同来源表示只计一次，不合并独立会话中的相同请求。

报告的 `source_health` 按宿主提供 `status`、`message_count` 和 `sources`。状态为 `ok`、`no_activity`、`partial`、`stale` 或 `unavailable`。每个来源包含路径、可用性、已读文件数、最新已读记录时间、是否早于请求日期及读取错误。`latest_record_at` 是已读记录时间，不是最后一次用户工作的证明。

展示报告时明确指出不完整或不可用的一侧；兼容 history 停更但 rollout 可读时，不把整个 Codex 数据源判死。只有停更 history 而无可读 rollout 时标为 `stale`。`partial` / `stale` / `unavailable` 不能表述为“用户当天没有活动”。消息数也不等于产出量。

## 交互与写入

使用当前宿主的提问能力，不依赖 Claude slash command。`--auto` 模式不提问，低置信度事项保留待确认。写入路径相对于 Vault 根目录；宿主来源标识保持一致，不写入另一宿主的原始会话缓存。
