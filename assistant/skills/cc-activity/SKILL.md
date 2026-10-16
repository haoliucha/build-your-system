---
name: cc-activity
description: 分析指定日期的 Claude 与 Codex 活动，合并间隙日志，输出带 origin 的时间线、按目标分组的估算时长、情绪分布和模式识别。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 活动分析

执行前读取当前 Vault 的 `60-Memory/preferences.md`（若存在），遵守其中的「工作流边界」；共享约定见 vault-structure/references/host-adaptation.md。不依赖会话 hook 或宿主私有记忆。

这是唯一的 Observe 入口。参数为日期，默认今天；日期使用 `YYYY-MM-DD`。

## 执行

1. 运行唯一活动脚本：

   ```bash
   python3 "<已加载插件根目录>/scripts/run-script.py" analyze-activity.py [日期] --host all --json-only
   ```

   先按 vault-structure/references/host-adaptation.md 定位实际插件根目录，运行器在同一次调用中设置环境。
2. 读取当日日记：优先 `00-Inbox/{日期}.md`，缺失时查
   `00-Inbox/{Y}/{Y-M}/{日期}.md`。
3. 读取日记中的 `## 间隙日志` 区块；记录字段和情绪映射见 capture-rules §6。
4. 把脚本 JSON 的 timeline 与间隙记录按时间合并。活动行必须保留 origin：`claude` 或
   `codex`；若脚本报告为本地来源，可显示为 `claude-local` / `codex-local`。
   `sessions[].aux` 为 true 的自动化子会话（SDK 入口的安全审查等）不进时间线，只写一行
   「N 个自动化子会话已归并到对应目标」。
5. 目标数据直接取脚本 JSON，不自行重算：`goals`（按目标分组）、`flow`（活动流水，每行一个
   会话段）、`mit.progress` / `mit.completion`（MIT 关联与完成率）、`unplanned`（计划外）。
   会话按「会话标题 → 显式目标切换（`目标：…`、`Do this task here: “…”`、assistant 命令）」
   切段；MIT 来自 `50-GTD/active.md` 当日区块，归档后来自 `50-GTD/done.md` 中带
   `MM-DD MIT` 标记的条目。

## 输出

先检查 `source_health`，明确报告采集不完整或不可用的一侧；不能把采集不可用写成没有活动。

按以下顺序渲染，避免只给原始 JSON：

### 📅 时间线概览

每条间隙记录显示为：

```text
HH:MM 📝 内容 情绪
```

每条机侧活动显示为：

```text
HH:MM 💻 [origin] 内容
```

相邻记录之间计算间隔，并按间隔上下文标注：

```text
↓ 深度工作 N 分钟
```

无法判断活动性质时，只显示实际间隔，不编造深度工作结论。

### 🎯 目标分组

按 `goals` 渲染，时长列标题写「估算时长」，表下附 `goal_meta.duration_method` 原文：

```text
| 目标 | 估算时长 | 消息 | 关联 | 会话 |
|---|---|---|---|---|
| 版本 1.1.0 发布 | ~104 分钟 | 16（+51 子会话） | 奇镜 1.1.0 发布 | 版本 1.1.0 发布 |
| Two-layer env config … | ~24 分钟 | 4（+18 子会话） | 计划外 | 版本 1.1.0 发布 |
```

关联列：`mit_match` 非空写 MIT 名；`category` 为 `unplanned` 写「计划外」，`routine` 写
「日常」。消息数和时长都只是活动证据，不等于产出；不要把估算时长写成实际工时。

### 🔍 情绪分布

按 capture-rules §6 的五档情绪统计数量；没有间隙记录时明确写“无间隙记录”，不要从机侧活动推断情绪。

### 模式识别

根据合并后的时间线标出事实依据，并最多给出以下三类模式：

- 拖延：连续分心或频繁切换；
- 高效：连续活动间隔较长且有完成记录；
- 卡住：连续卡住记录或同一事项反复出现。

模式识别是当日观察，不写入记忆层。

## 无数据

脚本没有活动且日记没有间隙记录时，输出“今天没有可用活动数据”，说明已检查 Claude、Codex
和当日日记，并建议使用 `c-pause` 记录下一次任务转换。只有一侧有数据时，明确标注另一侧为空。

## 约束

- 不调用旧的宿主专用活动脚本。
- 不修改日记、GTD 或记忆文件。
- 复盘需要时间线或目标分组时，o-review 复用本 skill 的合并渲染，不复制模板。
