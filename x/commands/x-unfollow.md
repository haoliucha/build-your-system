---
description: "X 关注卫生:找出我关注了但没回关的账号,按连续未回关天数 + 粉丝数阈值筛选,出名单;仅在明确要求时取关。详见 skill x-unfollow"
argument-hint: "[report|followers-report|relationships-report|unfollow] [min_days=3] [follower_threshold=2000] [limit=N]"
---

# /x-unfollow — X 关注卫生(取关未回关)

**$ARGUMENTS**

## 执行流程

1. **激活插件内共享 Skill** `skills/x-unfollow`,把上面的参数透传给它。不得调用或链接 `~/.agents/skills/x-unfollow`；默认 `MODE=report`(只出名单不取关)。
2. **跟用户对齐**(skill 内部):这次是出报告还是真取关?`MY_HANDLE`、`min_days` / `follower_threshold` 阈值?用户清楚取关不可一键回滚?
3. **检查 Chrome 账号配置**。缺少 `~/.config/x-browser/account.json` 时，在对话中询问用户的 Chrome 账号邮箱，再调用 `scripts/configure-account.cjs set --email=...`；邮箱必须唯一匹配系统 Chrome profile。随后跑本地 smoke test，拒启不通过的环境。
4. **按需扫描**:`report` 只刷新 following；`followers-report` 只刷新 followers；`relationships-report` 顺序刷新两表；新数据先进入 staging，校验后才晋升 current。
5. **report 模式**:打印最新未回关名单后停，不访问个人主页。**unfollow 模式**(需明确授权):按需刷新候选粉丝数 → 取关 → 一次 following 全量扫描 → 本地集合差验证。

## 常用用法

| 场景 | 命令 |
|---|---|
| 出未回关名单(默认) | `/x-unfollow report` |
| 查新增/取消关注我的账号 | `/x-unfollow followers-report` |
| 刷新完整关系并集 | `/x-unfollow relationships-report` |
| 改阈值出名单 | `/x-unfollow report min_days=7 follower_threshold=1000` |
| 真取关(小批量，硬上限 5) | `/x-unfollow unfollow limit=5` |

## 安全保证

skill 内部强制护栏:
- **默认只报告**,取关需用户明确说"取关"
- 取关只点目标本人且 `aria-label` 明确为 `正在关注/Following/取消关注/Unfollow @目标` 的按钮；绝不信任会被“订阅”复用的 `*-unfollow` testid，**对方已回关则跳过**
- 永不 关注 / 发推 / 点赞 / 评论 / block / 改 settings
- 使用独立 `PROFILE_DIR` 和本机随机端口 CDP；系统 Chrome 只读。认证 Cookie 缺失时零 X 请求、最多自动选择性刷新一次，失败回滚
- 登录 URL/按钮、Cookie 缺失和未登录受保护列表跳转都归类 `LOGIN_REDIRECT`；只有真实导航或相关 X API/Timeline HTTP 429 才归类限流，通用错误页不得声称 429
- 异常(验证码/真实限流/登录跳转/账号受限/通用导航错误)立即 STOP + 写 ALERT.txt + 找用户
- 取关后只拉一次完整关注列表，在本地验证全部目标；禁止逐主页验证
- 同时只允许一个完整流程；前一流程退出释放锁后可立即重跑
- 列表扫描按真实分页响应等待 1–3 秒，每 25 个响应暂停 10 秒，单表使用 45 分钟看门狗；页面漂移立即退出 15；粉丝数仅在取关流程按需刷新，每次最多 5 个、30–60 秒/个
