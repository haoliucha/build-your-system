# Changelog

## 4.0.1 (2026-08-19)

### Documentation and metadata

- 重写插件 README，以双宿主能力矩阵说明共享的 `x-unfollow`、`x-image` 和 Claude-only `x-follow`。
- 补充 Codex / Claude Code 安装、X 账号工作流前置条件、四种 `x-unfollow` 模式、当前态数据路径和安全边界。
- 修正 `/x-unfollow` 命令文档中的列表扫描节奏：真实分页响应间隔 1–3 秒，每 25 个响应暂停 10 秒，单表使用 45 分钟看门狗。
- 同步 Claude、Codex、marketplace 和仓库总览中的插件版本；本版本不包含运行时行为变化。

## 4.0.0 (2026-08-13)

### Dual-host plugin architecture

- 新增 Codex plugin manifest，将 `x` 作为统一的 Claude Code + Codex 顶层插件发布。
- `x-unfollow` 与 `x-image` 由两个宿主共享同一份业务真源；`x-follow` 移入 `claude-components/`，仅由 Claude Code 加载。
- Codex 原生加载 `x-image` 与 `x-unfollow`，Claude 的 `/x:image` 继续通过 Codex Rescue 完成原生 ImageGen 工作流。

## 3.0.1 (2026-08-13)

### x-unfollow v4 safety and pagination

- 受控 Chrome 默认使用无头模式，只有显式设置 `XU_HEADLESS=0` 才进入可见调试，且无头失败时不自动回退。
- 列表扫描改为被动解析页面自己的 Followers / Following 响应，以连续 Bottom cursor 链验证完整性。
- 网络响应启动后只采用响应账号集合；DOM 仅在完全无响应时兜底，并新增 1–3 秒分页节奏、每 25 个响应长暂停和 45 分钟看门狗。

## 3.0.0 (2026-08-09)

### Current relationship state

- 用 `current/` 中的 following、followers 与 relationships 最新状态替代逐日历史快照。
- 新扫描先写入 `.staging/<run-token>/`，校验完成后原子晋升 current 和 latest reports，失败时保留旧状态。
- 新增 `followers-report` 和 `relationships-report`，一次完整 followers 扫描即可输出新增、确认移除、待确认移除和证据冲突。
- 连续未回关状态压缩进最新关系行，仅相邻自然日的有效观察会延续。

## 2.2.1 (2026-08-08)

### Signal handling

- 修正中断信号处理，确保异常退出时清理浏览器上下文和 staging，并释放网络运行锁。

## 2.2.0 (2026-08-08)

### Serialized runs and bulk verification

- 同一数据目录只允许一个 x-unfollow 网络流程；移除跨流程时间冷却，前一流程退出后可立即重跑。
- 取关完成后改为一次完整 following 扫描和本地集合差验证，不再逐账号访问主页复查。
- 新增增量动作日志、精确取关控件与确认框校验、互关保护和统一限速策略。

## 2.0.0 (2026-07-16)

### Breaking changes

- 移除 `/x:cover` 与 `x-cover` skill,不保留兼容入口。
- 新增 `/x:image` 与 `x-image`,同时支持 X 文章封面和正文插图。

### Image workflow

- Claude 通过 `codex:codex-rescue` 把完整任务交给原生 Codex `x-image`。
- 每个图片资产只调用一次内置 ImageGen,不自动重试。
- 禁止图片后处理;只允许把原始输出复制到目标位置并做只读 QA。
- 支持 2.5:1、16:9、3:2、3:4、1:1 建议比例和不宽于 3:1 的自定义比例。
- 新增 `terminal-tech`、`editorial-material`、`data-editorial` 三个受控风格预设。
- 支持文件、目录、直接文本、数据和 brief 输入,以及 `-v2`、`-v3` 防覆盖命名。

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
