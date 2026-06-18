---
description: "X 关注卫生:找出我关注了但没回关的账号,按连续未回关天数 + 粉丝数阈值筛选,出名单;仅在明确要求时取关。详见 skill x-unfollow"
argument-hint: "[report|unfollow] [min_days=3] [follower_threshold=2000] [limit=N]"
---

# /x-unfollow — X 关注卫生(取关未回关)

**$ARGUMENTS**

## 执行流程

1. **激活 skill** `x-unfollow`,把上面的参数透传给它。默认 `MODE=report`(只出名单不取关)。
2. **跟用户对齐**(skill 内部):这次是出报告还是真取关?`MY_HANDLE` 已登录?`min_days` / `follower_threshold` 阈值?用户清楚取关不可一键回滚?
3. **跑 smoke test**,拒启不通过的环境。
4. **执行 pipeline**:snapshot `/following` → classify(reason 码)→ refresh 公开粉丝数 → 候选名单。
5. **report 模式**:打印候选名单后停。**unfollow 模式**(需明确授权):取关 → 验证 → 报告。

## 常用用法

| 场景 | 命令 |
|---|---|
| 出未回关名单(默认) | `/x-unfollow report` |
| 改阈值出名单 | `/x-unfollow report min_days=7 follower_threshold=1000` |
| 真取关(小批量) | `/x-unfollow unfollow limit=20` |

## 安全保证

skill 内部强制护栏:
- **默认只报告**,取关需用户明确说"取关"
- 取关只点目标本人的 `-unfollow` 按钮(`@token` 精确匹配),**对方已回关则跳过**
- 永不 关注 / 发推 / 点赞 / 评论 / block / 改 settings
- 异常(验证码/限流/登录跳转/账号受限)立即 STOP + 写 ALERT.txt + 找用户
- 取关后独立验证目标已不再被关注
