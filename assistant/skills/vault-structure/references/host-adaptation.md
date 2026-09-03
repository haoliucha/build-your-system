# 宿主适配契约

本契约规定共享 assistant skill 如何使用宿主提供的路径、活动数据和交互能力。业务语义保持一致，宿主差异只在入口、数据源和提问方式体现。

## 活动、健康与会话入口

唯一活动分析入口是：

~~~bash
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/analyze-activity.py" [YYYY-MM-DD] [--host auto|claude|codex|all] [--json-only]
~~~

健康检查入口：

~~~bash
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/vault-health.py" [--nudge]
~~~

会话上下文入口：

~~~bash
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/session-context.py"
~~~

skill、command 和 hook 不再调用旧的宿主专用活动脚本。需要活动数据时，统一调用 analyze-activity.py；需要健康提示时调用 vault-health.py；需要会话注入时调用 session-context.py。

## --host 语义与自动检测

--host 支持 auto、claude、codex、all：

- claude：只读取 Claude 本地活动，报告 origin: claude-local。
- codex：只读取 Codex 本地活动，报告 origin: codex-local。
- all：读取两侧并按时间合并；报告 origin: mixed。
- auto：按下列优先级自动选择单一宿主。

自动检测优先级固定为：

~~~text
--host > 环境变量 ASSISTANT_HOST > 存在 CLAUDECODE 时选择 claude > 否则选择 codex
~~~

这里的 --host 优先级高于 ASSISTANT_HOST；未显式指定 --host 时才读取环境变量。--host auto 表示执行上述自动检测，--host all 表示明确要求双宿主合并，不受自动检测结果改写。

## 插件根目录与宿主提供的能力

ASSISTANT_PLUGIN_ROOT 由当前宿主提供，skill 只依赖这个统一变量：

- Claude 的薄 command 文本里已注入 `${CLAUDE_PLUGIN_ROOT}`；该变量不会进入 Bash 子进程环境，因此 skill 不得依赖 `${CLAUDE_PLUGIN_ROOT}`。SessionStart hook 会打印插件根目录，供宿主侧诊断。
- Codex 的插件根目录约定为 $HOME/plugins/assistant；宿主应将它提供为 ASSISTANT_PLUGIN_ROOT，或在调用入口处展开为同一目录。

交互提问由当前宿主支持的方式完成。--auto 模式禁止提问，遇到选择时采取保守分支，并把低置信度内容留待确认。文件写入始终使用相对于 Vault 根目录的路径，不把某一宿主的原始会话路径写入另一宿主的缓存。

在 Codex 下，slash 命令名表示同名 skill；共享规则只引用 skill 名，不假设某一宿主的交互命令语法。
