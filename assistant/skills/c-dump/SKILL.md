---
name: c-dump
description: 以自由对话倾倒脑暴内容，结束时提取任务、想法和可验证洞察。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 脑暴倾倒

让用户连续表达，不在中途打断整理；可选参数为主题。当前目录即 Vault 根目录。

## 过程

1. 先让用户完整倾倒，除非用户明确要求，否则不提前分类或评价。
2. 结束时按 capture-rules §1-§5、§8 提取任务、等待、someday、topic、idea、record 和 insight。
3. 可行动项与原始脑暴写入 `00-Inbox/capture.md`；需要日记记录的内容写入当天日记。
4. 若形成可验证洞察，按 `vault-structure/references/memory-model.md` 的 L3 格式 prepend 到
   `60-Memory/patterns.md`，必须带 `source: 脑暴 {日期}`；没有可靠 source 就留在待确认区。

## 结束输出

给出：捕获条数、识别出的类型、待确认条数，以及下一步建议。不要在脑暴过程中自动创建项目或更新 L0-L2/L4 记忆。

## 边界

完整标签、置信度和间隙记录规则只从 capture-rules 读取；模板只从 file-templates.md 读取。
