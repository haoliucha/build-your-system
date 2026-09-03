---
name: o-schedule
description: 读取作息配置，判断当前时段，检查内容发布间隔，并按配置计算断更惩罚。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 作息状态

## 1. 读取配置

读取 `60-Memory/preferences.md` 的 YAML frontmatter 键：`wake`、`deep_work`、`end_work`、`bedtime`、`language`、`penalty_per_day`。
兼容旧正文中的 `- 起床时间:`、`- 深度工作:`、`- 结束工作:` 或 `- 结束时间:` 行。

缺少作息时提示运行 a-setup，并只输出可判断的部分。

## 2. 判断时段

使用 GMT+8 当前时间，依据起床、深度工作和收工时间判断早间准备、深度工作、常规工作、休息或非工作时段。输出当前时段和一行建议，不复制到其他 skill。

## 3. 检查发布间隔

扫描 `20-Areas/media/topics/*.md` 的 `published:` 字段，取最新发布日期。发布字段契约来自 media 插件 `m-publish`；只使用有效的 `YYYY-MM-DD`。

断更天数为今天减最新发布日期。读取 `penalty_per_day`：缺失时默认 200，设为 0 时关闭惩罚；否则累计惩罚为 `max(0, 断更天数 - 1) × penalty_per_day`。

## 4. 输出

```text
=== 作息状态 ({当前时间} GMT+8) ===
🕐 当前时段：{时段}
📋 当前建议：{任务或休息建议}
📊 最近发布：{日期或暂无} | 断更：{N} 天 | 惩罚：{金额或已关闭}
```

深度工作时段和超过收工时间时分别给出一行保护或休息提示。发布日期缺失时明确写“暂无可验证发布日期”，不要估算。
