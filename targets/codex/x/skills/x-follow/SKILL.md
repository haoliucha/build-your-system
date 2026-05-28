---
name: x-follow
description: This skill should be used when the user wants to batch-follow accounts on X (Twitter) matching precise criteria (verified status, follower count, following count, bio keywords). Default preset targets "蓝V互关" (blue-verified mutual follow culture). Triggers on phrases like "X 关注 N 个", "X 互关", "蓝V互关", "Twitter 批量 follow", "follow back campaign", "帮我关注 50 个蓝v".
---

# Codex 适配说明

- 这是 Claude `x` plugin 的 `x-follow` skill 的 Codex 适配版本。
- 文中提到的 `/x-follow` slash command 在 Codex 没有原生对应,直接通过本 skill 调用即可。
- 脚本路径 `${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/` 在 Codex 安装下指向本 plugin root。
- 与 Claude 版本共享 references 和 scripts(通过 symlink),内容完全一致,只是入口包装层不同。
- 跟用户对齐参数时,优先使用 Codex 支持的选项式提问。

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
bio_whitelist: []
my_handle: ""                     # 强烈建议填,用于预过滤已关注

# 候选发现
search_queries: ["蓝V互关", "蓝V互粉", "蓝V互fo"]

# 环境
profile_dir: ~/.config/playwright-chrome-profile

# 风控节奏(已实战调优)
follow_wait_min_ms: 25000
follow_wait_max_ms: 55000
long_break_every: 12
long_break_ms: 180000

# ULTRA-SAFE 选项(默认关)
max_follows_per_hour: 0
quiet_hours: []
```

## 5 步工作流

### Step 1: Setup
```bash
cp -R "$PROFILE_DIR" "$PROFILE_DIR-campaign"
rm -f "$PROFILE_DIR-campaign"/{SingletonLock,SingletonCookie,SingletonSocket}
PROFILE_DIR="$PROFILE_DIR-campaign" \
  node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/smoke-test.cjs"
```

### Step 2: Harvest
```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/harvest-search.cjs" "蓝V互关"
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/harvest-replies.cjs" "<status URL>"
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/harvest-followers.cjs" "<handle>" followers
```

### Step 3: Pre-filter
```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/snapshot-following.cjs" "$MY_HANDLE"
```

### Step 4: Verify + Follow loop
```bash
TARGET=100 PROFILE_DIR="$PROFILE_DIR-campaign" MY_HANDLE=haoliucha FERS_MAX=1100 \
  node "${CLAUDE_PLUGIN_ROOT}/skills/x-follow/scripts/campaign.cjs"
```

### Step 5: Cleanup
```bash
rm -rf "$PROFILE_DIR-campaign"
```

## 开工前对齐 checklist

1. ✅ target_count(具体数字)
2. ✅ 覆盖参数(`followers_max` / 容差 / `bio_blacklist` / etc)
3. ✅ profile_dir 已登录正确账号
4. ✅ 异常处理偏好
5. ✅ 用户清楚不可一键回滚

## 风控红线

- 撞验证码 / 异常弹窗 → STOP + 找用户
- 5 次连续 eval error → 5 min pause + exit
- **永不**:unfollow / 发推 / 点赞 / 评论 / block / 改 settings(代码 hard-coded)
- click 严格白名单:仅 `aria-label="关注 @{handle}"` 精确匹配

## 引用资源

- `references/candidate-sources.md` — 9 种候选挖掘策略
- `references/verify-logic.md` — 验证函数选择器表 + 4 条规则 rationale
- `references/pacing-anti-detection.md` — 风控节奏 + 反 bot 检测
- `references/presets.md` — 默认 preset + 自定义 preset
- `references/troubleshooting.md` — 12 个常见错误 + 修复

## 脚本

- `scripts/campaign.cjs` — 主关注 loop
- `scripts/smoke-test.cjs` — 启动前 6 项体检
- `scripts/detect-anomaly.cjs` — 异常感知
- `scripts/harvest-search.cjs` — 搜索页提取候选
- `scripts/harvest-replies.cjs` — 帖子评论区提取
- `scripts/harvest-followers.cjs` — followers/following 提取
- `scripts/snapshot-following.cjs` — 抓自己 following 列表
