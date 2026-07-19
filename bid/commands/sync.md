---
description: "一键口径级联同步:lsof 写句柄检查 → 手改回捕 → 跑生成器 → 内容抽验 → 全库 grep 残留 → memory 核对 → 分组提交预览。详见 skill single-source-sync"
argument-hint: "[口径变更描述]"
---

# /bid:sync

参数：`$ARGUMENTS`

加载本插件的 `bid-sync` skill，把 `$ARGUMENTS` 作为本次输入透传，并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件以 skill 为唯一真源。
