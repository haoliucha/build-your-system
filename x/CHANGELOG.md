# Changelog

## 1.0.1 (2026-05-29)

### Bug fixes
- **parseCount 解析 `亿`(1e8)单位**:之前的 regex `[万千KMB]?` 漏了 `亿`,导致 1.07亿(107M)粉丝被解析成 `1.07`,绕过 `followers_max` 检查。实战暴露:误关注 @narendramodi(印度总理,1.07亿粉)。修复后所有 mega-account 正确 reject。

### Documentation / spec
- **明确候选源硬约束**:`SKILL.md` / `references/candidate-sources.md` 现在硬规定 — 蓝V互关 use case 下,候选**只能**来自 `harvest-search.cjs`(搜索)或 `harvest-replies.cjs`(评论挖掘),**不能**用 `harvest-followers.cjs` 挖别人的 followers/following 列表。后者违反 spec("候选必须发过 蓝V互关 帖子")。
  - 实战教训:跑过 28 follow 里 10 个来自违规源,其中包括 1 个 X 黑产账号("专业推特蓝v代开/刷粉")。
  - `harvest-followers.cjs` 工具本身仍保留 — 如果是**其他 use case**(如关注某 KOL 的 followers,非互关 preset),可用,但必须明确告知用户"此候选不保证有互关意愿"。

## 1.0.0 (2026-05-28)

初始发布。

### Features
- skill + command `x-follow`:在 X 上参数化批量关注。默认 preset 蓝V互关。
- 7 个 Node 脚本:campaign / smoke-test / detect-anomaly / harvest-search / harvest-replies / harvest-followers / snapshot-following
- 5 篇 references:candidate-sources / verify-logic / pacing-anti-detection / presets / troubleshooting
- 4 层 anti-风控:浏览器指纹 + 行为节奏 + 异常感知 + 不可逆操作保护
- 双 host 兼容:Claude Code + Codex
- 实战验证:100/100 follow / 3h / 0 风控触发
