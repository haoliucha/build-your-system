# Media 创作助手

`media/` 是 Claude Code 与 Codex 共用的短视频创作插件，版本 `1.1.0`。业务流程只有一份：`skills/` 下的选题评估、热点、关键词、Hook、结构、逐字稿、标题、发布检查，以及 Jenny Hoyos、字幕清理和 YouTube 字幕方法论。

宿主入口：

- Claude Code：`/media:m-topic` 等命令是薄入口，只透传参数。
- Codex：从 `/skills` 选择对应 Skill，或显式使用 `$media:m-topic` 等入口。

共享 Skill 遵循 `references/host-adaptation.md`，不依赖宿主专属根路径或工具名称。联网检索、提问和文件能力由当前宿主提供；插件只准备内容，不自动发布外部平台。
