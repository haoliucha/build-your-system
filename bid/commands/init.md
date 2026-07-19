---
description: "一键投标项目立项脚手架:判定线索状态(新线索/成单/重组)→ 客户向·内部双层目录 + build 生成器骨架 + meeting 编年 → P0 问题清单(数据授权第 0 步)→ memory 索引初始化;重组既有目录前先审计脚本路径耦合。详见 skill bid-playbook"
argument-hint: "[项目名]"
---

# /bid:init

参数：`$ARGUMENTS`

加载本插件的 `bid-init` skill，把 `$ARGUMENTS` 作为本次输入透传，并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件以 skill 为唯一真源。
