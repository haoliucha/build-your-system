---
description: "一键按接收工具定制原型交接包:先吃透工具输入模型定包形态(prompt+知识库 vs 令牌+组件)→ 组装逐字合规文案 + 全量真实 copy + 实测取样视觉参考 + 宿主双层令牌 → P0/P1/P2 分批放行说明 → 交付前审校与最劣环境核验;写盘/commit 一律只预览。详见 skill prototype-handoff"
argument-hint: "[接收工具名] [原型范围]"
---

# /bid:handoff

参数：`$ARGUMENTS`

加载本插件的 `bid-handoff` skill，把 `$ARGUMENTS` 作为本次输入透传，并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件以 skill 为唯一真源。
