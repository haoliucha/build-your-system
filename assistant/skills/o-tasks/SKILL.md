---
name: o-tasks
description: 查看当前任务、MIT、等待事项和到期任务，并用健康检查结果给出简短建议。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 任务概览

当前目录即 Vault 根目录，读取 `50-GTD/active.md`、`waiting.md`、`someday.md` 和 `00-Inbox/capture.md`。

## 时段提示

调用 o-schedule 的时段判断，只输出一行；不要在本 skill 复制时段逻辑或作息配置规则。

## 展示内容

按以下顺序输出：

1. Inbox 待分发条目，最多 5 条；
2. `## 今日重点 (MIT)` 中的任务；
3. 等待中的事项；
4. 未来 3 天内到期的任务；
5. 活跃项目任务的简短分组。

## 健康概览

运行：

```bash
python3 "$ASSISTANT_PLUGIN_ROOT/scripts/vault-health.py"
```

`ASSISTANT_PLUGIN_ROOT` 由宿主提供，见 vault-structure/references/host-adaptation.md。读取 JSON 中的 inbox 积压、MIT 年龄、逾期数、复盘间隔和记忆卫生，展示为一行健康概览；健康检查失败时不阻断任务概览。

```text
健康概览：Inbox {N} | MIT 年龄 {N} 天 | 逾期 {N} | 距上次复盘 {N} 天 | 记忆 active {N}
```

## 建议

根据健康 JSON 给出 1–2 条可执行建议：积压达到阈值时建议运行 o-review，有逾期时建议调整或执行，缺少 MIT 时建议从 active 或 Inbox 选择 1–3 项。不要替用户改动任务。

## 快捷操作

- c-capture：添加捕获；
- o-review：完成每日回顾；
- o-schedule：查看当前时段；
- cc-activity：查看某日合并活动。
