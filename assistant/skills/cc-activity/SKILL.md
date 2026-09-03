---
name: cc-activity
description: 分析指定日期的 Claude 与 Codex 活动，合并间隙日志，输出带 origin 的时间线、情绪分布和模式识别。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 活动分析

这是唯一的 Observe 入口。参数为日期，默认今天；日期使用 `YYYY-MM-DD`。

## 执行

1. 运行唯一活动脚本：

   ```bash
   python3 "$ASSISTANT_PLUGIN_ROOT/scripts/analyze-activity.py" [日期] --host all --json-only
   ```

   `ASSISTANT_PLUGIN_ROOT` 由宿主提供，见 vault-structure/references/host-adaptation.md。
2. 读取当日日记：优先 `00-Inbox/{日期}.md`，缺失时查
   `00-Inbox/{Y}/{Y-M}/{日期}.md`。
3. 读取日记中的 `## 间隙日志` 区块；记录字段和情绪映射见 capture-rules §6。
4. 把脚本 JSON 的 timeline 与间隙记录按时间合并。活动行必须保留 origin：`claude` 或
   `codex`；若脚本报告为本地来源，可显示为 `claude-local` / `codex-local`。

## 输出

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
- 复盘需要时间线时，o-review 复用本 skill 的合并渲染，不复制模板。
