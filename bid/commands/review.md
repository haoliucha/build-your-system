---
description: "一键多透镜收口审校:按交付物类型装配透镜(文档=一致性/脱敏/去AI味/溯源,财务表=算术配平,视觉=逐页目检)并行扇出 → 汇总裁决 → 修复复验,commit 只预览。详见 skill adversarial-review"
argument-hint: "[交付物路径...]"
---

# /bid:review

参数：`$ARGUMENTS`

加载本插件的 `bid-review` skill，把 `$ARGUMENTS` 作为本次输入透传，并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件以 skill 为唯一真源。
