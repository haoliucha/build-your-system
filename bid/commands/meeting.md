---
description: "一键会议流程:会后归档纪要打标+提取口径变更落 memory(默认);--prep 会前生成准备包五件套(讲解脚本/数字速查卡/模拟Q&A/『别说』红线/口径桥)。详见 skill bid-playbook 与 presales-tactics"
argument-hint: "[会议日期或纪要文件] [--prep 会前模式]"
---

# /bid:meeting

参数：`$ARGUMENTS`

加载本插件的 `bid-meeting` skill，把 `$ARGUMENTS` 作为本次输入透传，并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件以 skill 为唯一真源。
