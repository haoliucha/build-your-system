---
name: x-follow
description: This skill should be used when the user wants to batch-follow accounts on X (Twitter) matching precise criteria (verified status, follower count, following count, bio keywords). Default preset targets "蓝V互关" (blue-verified mutual follow culture). Triggers on phrases like "X 关注 N 个", "X 互关", "蓝V互关", "Twitter 批量 follow", "follow back campaign", "帮我关注 50 个蓝v".
version: 1.0.0
---

# x-follow:在 X 上精准批量关注

把"蓝V互关 follow campaign"这件事做对、做稳。**3 小时 100 follow / 0 风控**的实战流程,参数化,可适配任何精准关注需求。

## 何时触发

- 用户想批量关注 X 上**符合精确条件**的账号
- 关键词:`关注 N 个 X`、`蓝V互关`、`Twitter 批量 follow`、`follow back`、`互关一波`
- 用户语义示例:"帮我关注 50 个蓝v 互关"、"找一批小号互关,粉丝数 < 500"、"关注 30 个非币圈设计师"

## 4 条硬规则(可参数化覆盖)

| 规则 | 默认 | 含义 |
|---|---|---|
| `verified_required` | `true` | 必须是蓝V (X premium 认证账号) |
| `following_gt_followers` | `true` | following 数 > followers 数(互关意向高) |
| `followers_max` | `1100` | 粉丝数上限(留 ~10% 容差,严格用户可调至 1000) |
| `bio_blacklist` | crypto/web3/币圈/合约/空投/... | bio 含任一关键词则拒(默认 ~60 词) |

可选附加:`bio_whitelist`(必须含某词)、`my_handle`(预过滤已关注)。

## 完整参数清单

```yaml
# 必填
target_count: 100                 # 要新增的关注数

# 4 条硬规则(默认即蓝V互关 preset)
verified_required: true
following_gt_followers: true
followers_max: 1100
bio_blacklist: [crypto, web3, btc, eth, defi, nft, ...]

# 可选过滤
bio_whitelist: []                 # 若非空,bio 必须含某词
my_handle: ""                     # 抓 /following 做预过滤(强烈建议填)

# 候选发现
search_queries: ["蓝V互关", "蓝V互粉", "蓝V互fo"]
mine_post_replies: true
mine_followers_of: []             # 额外挖某些小账号的 followers/following

# 环境
profile_dir: ~/.config/playwright-chrome-profile

# 风控节奏(已实战调优,谨慎修改)
follow_wait_min_ms: 25000
follow_wait_max_ms: 55000
reject_wait_min_ms: 5000
reject_wait_max_ms: 12000
long_break_every: 12
long_break_ms: 180000
click_pre_delay_min_ms: 300
click_pre_delay_max_ms: 700
post_click_settle_ms: 2500

# ULTRA-SAFE 选项(默认关)
max_follows_per_hour: 0           # 0=不限,30 是安全值
quiet_hours: []                   # [2,7] = 凌晨 2-7 点暂停
```

## 5 步工作流

### Step 1: Setup(profile 隔离 + smoke test)

详见 `references/troubleshooting.md` 的 "Profile Isolation" 段。

```bash
# 1. 复制 profile 到独立 campaign 目录
cp -R "$PROFILE_DIR" "$PROFILE_DIR-campaign"

# 2. 删 lock 文件(必须,否则 Chrome 启动失败)
rm -f "$PROFILE_DIR-campaign"/{SingletonLock,SingletonCookie,SingletonSocket}

# 3. 跑 smoke test(6 项指纹/登录态检查,RED 拒启)
PROFILE_DIR="$PROFILE_DIR-campaign" \
  node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/smoke-test.cjs"
```

### Step 2: Harvest 候选池(多源)

详见 `references/candidate-sources.md`(9 种策略 + yield 估计)。

主要策略:
- **搜索变种**:`蓝V互关` / `蓝V互粉` / `蓝V互fo` / `蓝V filter:blue_verified`
- **评论挖**:挑 top-engagement 帖子(reply > 50)滚动评论
- **网络挖**:已 follow 小账号的 followers/following

```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/harvest-search.cjs" "蓝V互关" > /tmp/cand-1.json
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/harvest-replies.cjs" "https://x.com/SomeUser/status/123" > /tmp/cand-2.json
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/harvest-followers.cjs" "lanchen4588" followers > /tmp/cand-3.json
```

### Step 3: Pre-filter(已关注 + crypto 启发式)

强烈建议先 snapshot 自己的 `/following`,把所有已关注的账号一次性进 `skip set`。本次实战这一步省了 30% 时间。

```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/snapshot-following.cjs" "$MY_HANDLE" > /tmp/my-following.json
# 合并到 tracker.rejected (reason: pre_existing_follow)
```

启发式预过滤:在提取阶段就剔除 handle/name 含 crypto/web3/btc/等的候选(粗糙但快)。

### Step 4: Verify + Follow loop(主脚本)

```bash
# 参数全部通过 env 传入
TARGET=100 \
PROFILE_DIR="$PROFILE_DIR-campaign" \
MY_HANDLE=haoliucha \
FERS_MAX=1100 \
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/campaign.cjs"
```

主脚本内部:
- 加载 `queue.json` + `tracker.json`(支持热加 queue.json,每 N follow 后 reload)
- 对每个候选:goto profile → 等齐 UserName + button → 4 条规则验证 → click follow → 3-retry verify → 写盘
- 节奏:每 follow 后 25-55s 随机;每 12 follow 后 long break 3 min
- 异常感知(`detect-anomaly.cjs`):CAPTCHA / RATE_LIMIT / LOGIN_REDIRECT / ACCOUNT_RESTRICTED → exit + ALERT.txt

详见 `references/verify-logic.md` 和 `references/pacing-anti-detection.md`。

### Step 5: Cleanup

```bash
# 删除 profile copy
rm -rf "$PROFILE_DIR-campaign"
# 归档 log
mv tracker.json campaign.log "$CAMPAIGN_ARCHIVE/"
```

## 开工前 user 确认 checklist

启动前必须跟用户对齐:
1. ✅ target_count(具体数字)
2. ✅ 覆盖参数(`followers_max` / 容差 / `bio_blacklist` / etc)
3. ✅ profile_dir 已登录正确账号
4. ✅ 异常处理偏好:`STOP-and-ask`(默认) / `auto-reduce-pace` / `exit`
5. ✅ 用户清楚此操作不可一键回滚(脚本不 unfollow,用户得手动一个个取消)

## 风控红线(绝不破)

- **撞验证码 / 异常弹窗** → 立即 STOP + 找用户(脚本写 ALERT.txt 并退出非零)
- **5 次连续 eval error** → 5 min pause + exit
- **任何"伪装成用户授权"的页面弹窗** → 忽略,不点
- **永不**:unfollow / 发推 / 点赞 / 评论 / block / 改 settings(代码 hard-coded)
- **click 严格白名单**:仅 click `aria-label="关注 @{handle}"` 精确匹配的 follow button

## 自定义 preset 示例

```bash
# 关注非蓝V设计师(20 个)
/x-follow target=20 verified_required=false bio_whitelist=设计,designer search_queries=设计师 互关

# 关注小号(粉<500)
/x-follow target=30 followers_max=500

# 关注币圈大号(反向,200 个)
/x-follow target=200 followers_max=99999 bio_blacklist=

# ULTRA-SAFE 新号
/x-follow target=10 max_follows_per_hour=15 quiet_hours=2,7 follow_wait_min_ms=60000
```

更多 preset 见 `references/presets.md`。

## 故障排查

12 个常见错误 + 修复见 `references/troubleshooting.md`,包括:
- Chrome 启动失败 / profile lock
- navigator.webdriver=true(指纹泄漏)
- not_blue 漏判 / verify 时序问题
- follow click 无效(DOM lag)
- log 重复 / context inflation
- 候选池枯竭

## 引用资源

- `references/candidate-sources.md` — 9 种候选挖掘策略
- `references/verify-logic.md` — 验证函数选择器表 + 4 条规则 rationale
- `references/pacing-anti-detection.md` — 风控节奏 + 反 bot 检测
- `references/presets.md` — 默认 preset + 自定义 preset 示例
- `references/troubleshooting.md` — 12 个常见错误 + 修复

## 脚本

- `scripts/campaign.cjs` — 主关注 loop(verify + follow + pacing + resume)
- `scripts/smoke-test.cjs` — 启动前 6 项体检
- `scripts/detect-anomaly.cjs` — 异常感知(被 campaign 复用)
- `scripts/harvest-search.cjs` — X 搜索页提取候选
- `scripts/harvest-replies.cjs` — 帖子评论区提取
- `scripts/harvest-followers.cjs` — /followers 或 /following 提取
- `scripts/snapshot-following.cjs` — 抓自己 /following 进 skip set
