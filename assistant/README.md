# Assistant

`assistant/` 是 Claude Code 与 Codex 共用的个人助手插件真源，插件 ID 统一为 `assistant`，版本 `2.0.0`。

共享 `skills/` 保存 19 个 Vault 工作流；Claude 的 `/assistant:*` 命令只是薄入口，Codex 通过 `$skill` 显式调用。活动分析遵循 `skills/vault-structure/references/host-adaptation.md`：Codex 使用本插件的本地分析脚本，Claude 使用 Claude 适配层。

Insights 和 X 关注卫生不属于本插件：Codex 的 `$insights` 位于顶层 `insights/`，`x-unfollow` 位于顶层 `x/`；Claude 继续使用原生 `/insights`。

安装 Codex 版本：

```bash
./scripts/install-local-plugin.sh
```
