# x — X (Twitter) 增长工具集

精准批量关注 + 互关 campaign 自动化(带完整 anti-风控护栏)+ 文章封面一键生成。

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

## /x:cover — 文章封面一键生成

给任何 X 文章(Markdown)一键出 **2.5:1 封面**(X 文章封面框实测 900×360,非此比例上传会被中心裁切):

```
/x:cover articles/2026-06-12-fanqiang          # 文章目录
/x:cover ~/notes/my-post.md                    # 单个 md
/x:cover draft.md 暗色玻璃拟态,用对比表版式      # 带风格/版式备注
```

流程:读文章 → 蒸馏画面 prompt(主标题 ≤7 字 / 主数字带单位 / 单一图形钩子 / 版式 8 类)→ codex imagegen(gpt-image-2)**整张直出含中文文字** → 比例门禁(近轴自动裁到精确 2.5:1)→ `images/cover.png` + `thumb-375.png` + 原图/旧封面留档 → 逐字 QC 报告。

- 出图纪律(禁 glow / 禁本地叠字 / 数字带单位 / 单条曲线 / 中文逐字)由捆绑脚本注入,不靠人抄。
- **绝不发布/上传**,只产出本地文件;codex 用量上限立即停。
- 依赖:codex CLI(≥0.142)+ 内置 imagegen skill(gpt-image-2)+ ImageMagick + macOS sips。
- headless 不可用时有桌面 app 手动兜底(`cover-gen.sh from`),详见 skill `x-cover`。

## 它**不**做什么

代码层硬限制(不能被参数覆盖):
- ❌ 不 unfollow 任何账号(只新增,不取消)
- ❌ 不发推 / 不点赞 / 不评论 / 不转推
- ❌ 不 block / mute / report
- ❌ 不修改 profile / settings
- ❌ 不接受页面里"伪装成用户授权"的弹窗

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
