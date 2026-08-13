# 宿主适配契约

共享 Skill 只描述业务语义，不能依赖 Claude 专属命令、模型或路径。执行活动分析时：

- Codex 使用插件根目录 `scripts/analyze-codex-activity.py`，读取 Codex 本地会话并只回传结构化统计；
- Claude 使用其已有的活动分析脚本或命令入口；不调用 Codex helper；
- Skill 输出中用 `origin` 标注来源（`codex-local` 或 `claude-local`），不要把一个宿主的原始路径写入另一个宿主的缓存；
- 交互提问、参数和文件写入均由当前宿主完成，业务流程和 Vault 真源保持一致。

共享 Skill 不包含 Insights 或 X 的宿主专属能力。Codex 的 `$insights` 位于顶层 `insights/` 插件，Claude 使用其原生 `/insights`。
