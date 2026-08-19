---
description: "在 X 上启动共享 x-follow 精准批量关注 campaign。默认 FERS_MAX=3000、FOLLOW_RATIO_MIN=0.5、FILTER_CRYPTO=0；默认只关注。"
argument-hint: "target=100 [verified_required=true] [followers_max=3000] [bio_whitelist=...] [FILTER_CRYPTO=0]"
---

# /x-follow — X 精准批量关注

**$ARGUMENTS**

## 执行流程

1. 激活当前 `x` 插件内共享的 `skills/x-follow` Skill，把上面的参数透传给它；不得使用脱离双宿主 manifest 的 standalone 副本。
2. **跟用户对齐**(skill 内部):确认 target、筛选条件、异常处理偏好和独立评论授权
3. **检查 Chrome 账号配置**。缺少 `~/.config/x-browser/account.json` 时，在对话中询问 Chrome 账号邮箱，再调用共享 Skill 的 `scripts/configure-account.cjs set --email=...`；邮箱必须唯一匹配系统 Chrome profile。随后跑 `scripts/smoke-test.cjs`，拒启不通过的环境
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
- 默认只关注；不 unfollow / 发推 / 点赞 / 修改 settings
- 评论默认禁用；仅在 `COMMENT_AFTER_FOLLOW=true`（或 `1`）与 `ALLOW_COMMENT_AFTER_FOLLOW=1` 均由用户独立明确授权时执行
- 默认使用可见的独立 CDP Chrome；系统 Chrome 只读。认证 Cookie 缺失时零 X 请求、最多自动选择性刷新一次，失败回滚
- 只有导航或相关 X API/Timeline 的真实 HTTP 429 才是限流；通用错误页单独记录，不得伪报 429
- 异常(验证码/真实限流/登录跳转/通用导航错误)立即 STOP + 找用户
- 严格 click 选择器,不模糊匹配按钮
