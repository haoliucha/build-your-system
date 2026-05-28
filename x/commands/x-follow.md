---
description: "在 X 上启动一次精准批量关注 campaign。默认 preset 蓝V互关。参数: target / verified_required / followers_max / bio_blacklist 等。详见 skill x-follow"
argument-hint: "target=100 [verified_required=true] [followers_max=1100] [bio_whitelist=...]"
---

# /x-follow — X 精准批量关注

**$ARGUMENTS**

## 执行流程

1. **激活 skill** `x-follow`,把上面的参数透传给它。如果用户没指定参数,skill 会用默认 preset(蓝V互关:`verified_required=true, followers_max=1100, following_gt_followers=true, bio_blacklist=[crypto关键词]`)
2. **跟用户对齐**(skill 内部):确认 target、profile_dir、异常处理偏好
3. **跑 smoke test**(`scripts/smoke-test.cjs`)拒启不通过的环境
4. **执行 5 步 campaign**:Setup → Harvest → Pre-filter → Verify+Follow loop → Cleanup
5. **报告结果**:followed 列表、rejected breakdown、需 review 的边缘 case

## 常用 preset 速查

| 场景 | 命令 |
|---|---|
| 蓝V互关(默认) | `/x-follow target=50` |
| 关注非币圈设计师 | `/x-follow target=30 bio_whitelist=设计,designer search_queries=设计师 互关` |
| 关注小号(粉<500) | `/x-follow target=20 followers_max=500` |
| ULTRA-SAFE 新号 | `/x-follow target=10 max_follows_per_hour=15 quiet_hours=2,7` |

## 安全保证

skill 内部强制护栏:
- 永不 unfollow / 发推 / 点赞 / 评论 / 修改 settings
- 异常(验证码/限流/登录跳转)立即 STOP + 找用户
- 严格 click 选择器,不模糊匹配按钮
