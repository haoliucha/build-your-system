---
name: assistant-router
description: 在个人 Vault 中路由捕获、复盘、任务、作息、活动分析、选题挖矿、导出和周报请求。
---

# Personal Assistant 总入口

优先遵守当前 Vault 的 `AGENTS.md` / `AGENTS.override.md`。当前目录即 Vault 根目录；需要写文件时使用相对路径。

## 工作流 skill

以下 11 个工作流 skill 与 `commands/` 同名：

- `a-setup`：初始化目录、文件和用户配置；
- `c-capture`：捕获内容并识别标签；
- `c-dump`：自由倾倒脑暴并提取行动项；
- `c-pause`：记录任务转换点的间隙日志；
- `cc-activity`：合并 Claude、Codex 和间隙记录的当日活动；
- `d-mine`：从近期材料挖掘选题素材；
- `e-export`：导出知识笔记和完整对话；
- `o-review`：每日分发、复盘和明日规划；
- `o-schedule`：判断作息、发布间隔和惩罚；
- `o-tasks`：查看任务和健康概览；
- `o-weekly`：生成周报并执行记忆消融。

## 规则 skill

- `capture-rules`：唯一的捕获、标签、间隙记录和置信度规则真源；
- `vault-structure`：Vault 路径、模板、记忆层和宿主契约。

## 脚本与宿主

脚本入口、`ASSISTANT_PLUGIN_ROOT`、活动来源和宿主交互见 `vault-structure/references/host-adaptation.md`。需要活动数据时使用 `analyze-activity.py`，需要健康数据时使用 `vault-health.py`，需要会话注入时使用 `session-context.py`。
