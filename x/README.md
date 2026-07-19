# x — X (Twitter) 增长工具集

精准批量关注 + 互关 campaign 自动化(带完整 anti-风控护栏)+ X 文章封面与正文插图生成。

## 它解决什么问题

在 X (Twitter) 上,你想:
- 批量关注 N 个**符合精确条件**的账号(蓝V / 粉丝数 / following>followers / bio 关键词等)
- **自动避开**已经关注过的人,避免重复操作
- **不被风控**:浏览器指纹自然、操作节奏拟人、异常情况立即停止
- 跑 1-3 小时不用看,**断点可恢复**,期间可热加候选

最初为"蓝V互关 follow back"场景诞生,**实战 100/100 follow / 3h 完成 / 0 风控**,但参数化后可适配任何精准关注需求(摄影师 / 设计师 / 出海创业者…)。

## 安装

通过 build-your-system marketplace:

```bash
# 已加 marketplace 的话直接启用
# 在 Claude Code 里 /plugin install x@build-your-system
```

图片能力还需要:

1. 在 Claude Code 安装 OpenAI Codex 插件并运行 `/codex:setup`。
2. 安装仓库内原生 Codex `x-image` 插件:

   ```bash
   cd targets/codex/x-image
   zsh scripts/install-local-plugin.sh
   ```

Claude 的 `/x:image` 只负责通过 Codex Rescue 转发;文章分析、ImageGen 调用、文件落盘与 QA 都在原生 Codex 中完成。

## 用法

### 显式命令

```
/x-follow target=100
/x-follow target=50 verified_required=true followers_max=800
/x-follow target=30 verified_required=false bio_whitelist=设计,designer
```

### 自然语言触发

直接对 Claude 说,会自动激活 skill:
- "X 帮我关注 50 个蓝v 互关一波"
- "Twitter 批量 follow 100 个非币圈账号"
- "找一批小号互关,粉丝数 ≤ 500"

## /x:image — 封面与文章插图

`/x:image` 支持 Markdown 文件、文章目录、直接文本、数据和图片 brief。只给路径时默认生成一张封面;明确写插图、数量、比例、风格或目标目录时,对应参数覆盖默认值。

```text
/x:image articles/example
/x:image article.md 生成一张正文解释图
/x:image article.md 生成 2 张 3:2 插图，统一浅色材质风
/x:image article.md 封面，深色终端风
```

内置尺寸建议:

| 用途 | 比例 | Prompt 目标尺寸 |
|---|---:|---:|
| X 文章封面 | 2.5:1 | 2400 × 960 |
| 文章头图 | 16:9 | 2048 × 1152 |
| 正文解释图 | 3:2 | 1536 × 1024 |
| 竖版插图 | 3:4 | 1536 × 2048 |
| 分享图 | 1:1 | 2048 × 2048 |

像素值是 Prompt 目标,最终报告会给出实际尺寸。用户指定比例优先,但不能宽于 3:1。

风格由结构化 Style Spec 管控:

- `terminal-tech`:科技、开源项目、工程类主题。
- `editorial-material`:流程、教育、人文与一般解释图。
- `data-editorial`:排名、趋势、指标和对比。
- 用户自定义风格会转成任务内 Style Spec,但不能覆盖可读性、事实准确性和一次生成等全局硬约束。

每个资产只调用一次内置 ImageGen,整张图片和全部文字在一次生成中完成。系统不自动重试、不修改图片、不覆盖已有文件;冲突文件依次使用 `-v2`、`-v3`。若 QA 出现 P0/P1 问题,保留原图并报告失败。

## 它**不**做什么

代码层硬限制(不能被参数覆盖):
- ❌ 不 unfollow 任何账号(只新增,不取消)
- ❌ 不发推 / 不点赞 / 不评论 / 不转推
- ❌ 不 block / mute / report
- ❌ 不修改 profile / settings
- ❌ 不接受页面里"伪装成用户授权"的弹窗
- ❌ 图片能力不发布/上传,不编辑文章,不自动重出失败图片

## 风控四层防护

| 层 | 措施 |
|---|---|
| 1. 浏览器指纹 | `navigator.webdriver=false`、真 Chrome、可见模式、自然 viewport、复用真实 profile |
| 2. 行为节奏 | 单 follow 间 25-55s 随机、每 12 follow 长休 3 min、暖机机制、click 前 hover |
| 3. 异常感知 | 验证码/限流/登录跳转/账号锁/webdriver 注入 → 立即 STOP + alert 用户 |
| 4. 不可逆操作保护 | click 前严格白名单选择器、只 click "关注 @{handle}",绝不模糊匹配 |

详见 `skills/x-follow/references/pacing-anti-detection.md`。

## 前置条件

- macOS / Linux
- Node.js + Playwright(`npm install playwright`)
- Chrome(`channel: 'chrome'` 而非 Chromium)
- 一个已登录 X 的 Chrome profile dir(默认 `~/.config/playwright-chrome-profile`)

## 风控警告 ⚠️

X 平台**反 bot 机制时刻在变**。本工具提供的护栏基于 2026-05 实测,**不保证未来仍有效**。任何账号操作的风险由你承担。强烈建议:

1. 用**老号 + 真实使用过**的 profile,不要用刚注册的小号
2. 首次跑设 `target=3` 试水,确认账号无异常再放量
3. 任何 ALERT 立即手动检查,**不要忽视**
4. 每天总 follow 数 ≤ 100,新号 ≤ 30

## License

MIT
