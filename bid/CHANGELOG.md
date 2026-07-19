# Changelog

## 0.1.0 (2026-07-07)

首个版本。方法论挖掘自一个真实 To-B 投标项目的 9 个 AI-coding 全周期实战会话(318 条经验、16 个经验域),案例线已全部化名重构。

### Codex support (2026-07-18)

- 增加直接可安装的 `.codex-plugin/plugin.json`,无需维护第二份 skill 源。
- 六个流程工作流由 Claude Code command 和 Codex skill 入口共享,宿主只负责入口与能力映射。
- 本地安装器增加 marketplace 名称/条目 preflight、Codex CLI 失败精确回滚和受测试的 `--uninstall` 事务流程,保留无关内容与既有文件权限。
- bundled 脚本和 references 改用相对拥有者 `SKILL.md` 的宿主中立路径规则。
- 修复 macOS ImageMagick 未配置默认字体时原型 contact sheet 生成失败,并验证带空格路径的显式 `FONT` 覆盖、标签区域与画面内容。
- 明确 `0.1.0` 为本集成批准的基础版本;本地更新使用受跟踪 manifest 中的 `+codex.<cachebuster>` build metadata,不提升基础版本。
- README 扩展为 Claude Code / Codex 双宿主安装、调用、更新、卸载和安全指南。

- 10 个 skill:bid-playbook / single-source-sync / bid-costing / bid-scheduling / adversarial-review / deai-writing / diagram-pdf-pipeline / prototype-handoff / bid-research / presales-tactics
- 6 个流程节点 command:/bid:init · /bid:meeting · /bid:sync · /bid:handoff · /bid:review · /bid:status
- 附带工具脚本:aiflavor-scan.cjs(18 类 AI 味正则扫描)、xlsx-dump.cjs(逐格逻辑值 dump 供手改 diff)、level.cjs(PERT+资源平衡排期)、add-outline.cjs(PDF 书签注入)
- docs/bid-methodology.html:方法论导读(含「系统动态演示」可播放流水线动画)
