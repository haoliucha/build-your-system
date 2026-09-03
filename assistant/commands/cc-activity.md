---
description: "活动分析 - 分析当日对话记录，生成时间线和目标统计"
argument-hint: "[YYYY-MM-DD]"
---

插件根目录：${CLAUDE_PLUGIN_ROOT}（作为 ASSISTANT_PLUGIN_ROOT 传给 skill 中的脚本调用）

执行 `cc-activity` skill，透传 `$ARGUMENTS`；活动数据统一读取 Claude 与 Codex。
