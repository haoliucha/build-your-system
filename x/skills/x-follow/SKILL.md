---
name: x-follow
description: Use when the user explicitly requests a batch-follow campaign on X with precise account criteria.
---

# x-follow:在 X 上精准批量关注

只从完整 `x` 插件运行本 Skill。Codex 使用 `$x:x-follow`，Claude Code 使用 `/x-follow`；脱离双宿主 manifest 的 standalone 副本必须在浏览器、锁和 X 请求前以 `LEGACY_STANDALONE_INSTALL` 失败。

把"蓝V互关 follow campaign"这件事做对、做稳。**3 小时 100 follow / 0 风控**的实战流程,参数化,可适配任何精准关注需求。

> **架构与开发文档见 [`README.md`](./README.md)**(pipeline 图、模块依赖、异常状态机、测试)。
> **推荐入口 = 一条龙 `run.sh`**:它把 smoke → harvest(凑够候选)→ build-queue → campaign(watchdog)→ verify+补关 → 报告 编排成「遇错自恢复」的流水线,真异常(验证码/限流/登录跳转/账号受限)**自动停并写 ALERT.txt**。手动分步(下方 5 步)用于调试或特殊场景。
>
> ```bash
> SKILL_DIR="/当前 Skill 目录的绝对路径"
> export SKILL_DIR
> NODE_PATH=~/.config/playwright-mcp-server/node_modules \
>   TARGET=10 MY_HANDLE=<you> bash "$SKILL_DIR/run.sh"
> # 币圈/web3 默认已放开(FILTER_CRYPTO=0);要过滤掉币圈/web3 改 FILTER_CRYPTO=1
> ```

所有脚本路径都以**当前 Skill 目录的绝对路径**为根：先由宿主解析该目录并赋给
`SKILL_DIR`，再使用 `"$SKILL_DIR/scripts/..."`。不依赖任何宿主专属根目录变量。

运行状态默认位于 `$HOME/.config/x-follow-data`：`X_FOLLOW_RUN_ID=current`，因此
`JOB_DIR=$X_FOLLOW_DATA_DIR/runs/$X_FOLLOW_RUN_ID`，历史 skip 默认读取
`$X_FOLLOW_DATA_DIR/runs/*/tracker.json`。运行 ID 只能是单个安全路径段；不会读取、迁移或删除旧的 Claude job 目录。
同一数据目录使用唯一的 `$X_FOLLOW_DATA_DIR/network-run.lock` 串行化网络流程；`run.sh` 是 owner，
每个继承 token 的 X-facing 子进程会登记自己的 worker identity。owner 或 worker 任一仍活跃时均不可恢复或释放该锁。
显式 `JOB_DIR` 优先于默认 run 目录。

运行前检查 `~/.config/x-browser/account.json`。缺失时，在对话中询问用户要使用的 Chrome 账号邮箱，不要猜测，
然后运行 `node "$SKILL_DIR/scripts/configure-account.cjs" set --email=<chrome-account-email>`。配置按
`X_CHROME_ACCOUNT_EMAIL` 临时覆盖 → 本地文件的优先级解析；`X_BROWSER_CONFIG_PATH` 可改配置路径。
邮箱必须在系统 Chrome `Local State.profile.info_cache` 中恰好匹配一个 profile；不要硬编码私人邮箱或目录名。

系统 Chrome user-data 默认来自 `$HOME/Library/Application Support/Google/Chrome`，可用
`X_CHROME_USER_DATA_DIR` 覆盖；`SOURCE_PROFILE_DIR`、`X_FOLLOW_SOURCE_PROFILE_DIR` 仅作为兼容别名。
`PROFILE_DIR` 默认 `$HOME/.config/playwright-chrome-profile-campaign`。运行时强制要求 source 与 target 的
canonical path 互不重叠，并通过本机随机端口 CDP 只在独立 target 上运行。系统 Chrome 始终只读。
若独立副本缺少 `auth_token`/`ct0`，在零 X 请求状态下最多选择性刷新一次；失败回滚并退出 12。

**任何关注动作必须由用户明确请求。**真实默认值为 `FERS_MAX=3000`、
`FOLLOW_RATIO_MIN=0.5`、`FILTER_CRYPTO=0`。评论默认关闭；即使用户请求
`COMMENT_AFTER_FOLLOW=true`，也必须同时明确给出 `ALLOW_COMMENT_AFTER_FOLLOW=1`，否则在浏览器启动前拒绝运行。

## 何时触发

- 用户想批量关注 X 上**符合精确条件**的账号
- 关键词:`关注 N 个 X`、`蓝V互关`、`Twitter 批量 follow`、`follow back`、`互关一波`
- 用户语义示例:"帮我关注 50 个蓝v 互关"、"找一批小号互关,粉丝数 < 500"、"关注 30 个非币圈设计师"

## 🚨 候选源硬约束(蓝V互关 use case)

候选必须**主动表达过互关意愿** — 即其本人发过 蓝V互关 相关帖子,或在此类帖子下评论。**绝不能**从其他账号的 followers/following 列表挖,即使被挖账号是你已经关注的小号:

| 候选源 | 是否合规 | 说明 |
|---|---|---|
| `harvest.cjs search "蓝V互关"` 等搜索 | ✅ 合规 | 发帖人主动用了 蓝V互关 hashtag |
| `harvest.cjs replies <status URL>` | ✅ 合规 | 评论者主动在 蓝V互关 帖子下回复 |
| `snapshot-following.cjs <my-handle>` | ✅ 合规(仅作 skip set) | 自己的 /following 列表,用来预过滤已关注的,**不是**候选源 |
| `harvest.cjs followers <other>` 别人的 /followers 或 /following | ❌ **不合规**(蓝V互关 场景) | 这些人**不一定**发过互关帖子,他们只是被某人关注/关注某人 |

**违规后果**:跑过一次 100 follow / 3h 实战发现 28 个 follow 里 10 个来自非合规源 — 其中包括 1 个 X 黑产账号("专业推特蓝v代开/刷粉")。

例外:如果是**其他 use case**(如关注某 KOL 的 followers),`harvest.cjs followers` 可用,但必须明确告知用户"此候选不保证有互关意愿"。

## 4 条硬规则(可参数化覆盖)

| 规则 | 默认 | 含义 |
|---|---|---|
| `verified_required` | `true` | 必须是蓝V (X premium 认证账号) |
| `following_gt_followers` | `true` | 启用关注/粉丝比筛选；默认 `FOLLOW_RATIO_MIN=0.5`，只拒明显单向广播号 |
| `followers_max` | `3000` | 粉丝数上限(严格用户可调低) |
| `bio_blacklist` | 空（`FILTER_CRYPTO=0`） | 默认不按币圈/web3 过滤；`FILTER_CRYPTO=1` 启用 crypto 黑名单，显式 `BIO_BLACKLIST` 优先 |

可选附加:`bio_whitelist`(必须含某词)、`my_handle`(预过滤已关注)。

## 完整参数清单

```yaml
# 必填
target_count: 100                 # 要新增的关注数

# 4 条硬规则(默认即蓝V互关 preset)
verified_required: true
following_gt_followers: true
followers_max: 3000
follow_ratio_min: 0.5
filter_crypto: 0                  # 默认不过滤币圈/web3；FILTER_CRYPTO=1 才用 crypto 列表
bio_blacklist: []                 # 显式 BIO_BLACKLIST 优先于 FILTER_CRYPTO

# 可选过滤
bio_whitelist: []                 # 若非空,bio 必须含某词
my_handle: ""                     # 抓 /following 做预过滤(强烈建议填)

# 候选发现
search_queries: ["蓝V互关", "蓝V互粉", "蓝V互fo"]
mine_post_replies: true
mine_followers_of: []             # 额外挖某些小账号的 followers/following

# 环境：只运行独立副本，不在原始 profile 上执行 workflow
profile_dir: ~/.config/playwright-chrome-profile-campaign

# 风控节奏(已实战调优,谨慎修改)
profile_visit_min_interval_ms: 90000 # 任意两个资料页访问起点至少间隔 90-150s
profile_visit_max_interval_ms: 150000
max_profile_visits_per_hour: 30      # 成功关注与拒绝都计入，状态跨 resume 保留
rate_limit_cooldown_ms: 1800000      # 真 429 后保存 30min 冷却截止时间
follow_wait_min_ms: 25000
follow_wait_max_ms: 55000
reject_wait_min_ms: 5000
reject_wait_max_ms: 12000
long_break_every: 12
long_break_ms: 180000
click_pre_delay_min_ms: 300
click_pre_delay_max_ms: 700
post_click_settle_ms: 6000          # 高延迟下让按钮可靠翻成「正在关注」,减少 followed_assumed 虚报

# ULTRA-SAFE 选项(默认关)
max_follows_per_hour: 0           # 0=不限,30 是安全值
quiet_hours: []                   # [2,7] = 凌晨 2-7 点暂停

# 诊断模式（必须配 DRY_RUN=1；不改 tracker）
x_follow_trace: 0                 # 1=记录脱敏页面阶段与 X API/GraphQL 元数据
trace_profile_limit: 5            # 到数即停；人工/自动基线使用 5
```

## 5 步工作流

### Step 1: Setup(profile 隔离 + smoke test)

详见 `references/troubleshooting.md` 的 "Profile Isolation" 段。

```bash
# 1. 每次手动流程先创建唯一 run；后续所有脚本只读写这一 JOB_DIR
X_FOLLOW_DATA_DIR="${X_FOLLOW_DATA_DIR:-$HOME/.config/x-follow-data}"
X_FOLLOW_RUN_ID="manual-$(date -u +%Y%m%dT%H%M%SZ)-$$"
JOB_DIR="$X_FOLLOW_DATA_DIR/runs/$X_FOLLOW_RUN_ID"
export X_FOLLOW_DATA_DIR X_FOLLOW_RUN_ID JOB_DIR
mkdir -p "$JOB_DIR"

# 2. 检查本地 Chrome 账号配置；缺失时先在对话中询问用户邮箱，再保存
PROFILE_DIR="${PROFILE_DIR:-$HOME/.config/playwright-chrome-profile-campaign}"
export PROFILE_DIR
node "$SKILL_DIR/scripts/configure-account.cjs" check
# 首次配置：node "$SKILL_DIR/scripts/configure-account.cjs" set --email=<chrome-account-email>

# 3. run.sh 会使用系统 Chrome 只读源和独立 PROFILE_DIR；认证缺失时最多自动刷新一次

# 4. 跑 smoke test（CDP、登录态和指纹检查，RED 拒启）
PROFILE_DIR="$PROFILE_DIR" \
  node "$SKILL_DIR/scripts/smoke-test.cjs"
```

### Step 2: Harvest 候选池(多源)

详见 `references/candidate-sources.md`。

合规策略(只用这些):
- **搜索变种**:`蓝V互关` / `蓝V互粉` / `蓝V互fo` / `蓝V filter:blue_verified`
- **评论挖**:挑 top-engagement 帖子(reply > 50)滚动评论
- ❌ **不要**用 `harvest.cjs followers` 挖别人的 followers/following — 违反"候选必须发过互关帖"约束

```bash
PROFILE_DIR="$PROFILE_DIR" \
  node "$SKILL_DIR/scripts/harvest.cjs" search "蓝V互关" > "$JOB_DIR/cand-search.json"
PROFILE_DIR="$PROFILE_DIR" \
  node "$SKILL_DIR/scripts/harvest.cjs" replies "https://x.com/SomeUser/status/123" > "$JOB_DIR/cand-replies.json"
```

### Step 3: Snapshot → tracker pre-filter → build queue

强烈建议先 snapshot 自己的 `/following`,把所有已关注的账号一次性进 `skip set`。本次实战这一步省了 30% 时间。

```bash
PROFILE_DIR="$PROFILE_DIR" \
  node "$SKILL_DIR/scripts/snapshot-following.cjs" "$MY_HANDLE" > "$JOB_DIR/my-following.json"
# 离线、原子合并到同一 JOB_DIR 的 tracker.rejected (reason: pre_existing_follow)
node "$SKILL_DIR/scripts/merge-pre-existing.cjs" \
  "$JOB_DIR/my-following.json" "$JOB_DIR/tracker.json"
# snapshot 已进入 skip set 后再合并/去重候选并构建同一 JOB_DIR 的 queue.json
FILTER_CRYPTO=0 JOB_DIR="$JOB_DIR" node "$SKILL_DIR/scripts/build-queue.cjs"
```

`FILTER_CRYPTO=0` 为默认值，不剔除 crypto/web3 候选；只有设为 `1` 时才在提取阶段按 handle/name 的 crypto 启发式预过滤。

### Step 4: Verify + Follow loop(主脚本)

```bash
# 参数全部通过 env 传入；已导出的 JOB_DIR 保持 queue/tracker/log 同源
TARGET=100 \
PROFILE_DIR="$PROFILE_DIR" \
MY_HANDLE=haoliucha \
FERS_MAX=3000 FOLLOW_RATIO_MIN=0.5 FILTER_CRYPTO=0 \
node "$SKILL_DIR/scripts/campaign.cjs"
```

主脚本内部:
- 加载 `queue.json` + `tracker.json`(支持热加 queue.json,每 N follow 后 reload)
- 每次打开候选资料页前先走**持久化 profile pacer**：访问起点随机间隔 90-150s，滚动 1 小时最多 30 个；成功关注与拒绝都计数，数据根目录的 `profile-pacing.json` 让 resume 或新 run 都不会忘掉上一进程的请求历史
- 对每个候选：pacer → `gotoRobust` profile（延迟容错；只有真实 HTTP 429 才记限流）→ 等齐 UserName + button → 4 条规则验证 → click follow → verify → 写盘
- follow 后 25-55s、reject 后 5-12s 仍保留作页面/动作停顿，但它们不再承担主限流职责；每 12 follow 另有 3min long break
- 异常感知：CAPTCHA / 真实 HTTP `RATE_LIMIT` / `LOGIN_REDIRECT` / `ACCOUNT_RESTRICTED` / `GENERIC_NAV_ERROR` → **先保存当前 viewport PNG + 页面/HTTP JSON，再写 `ALERT.txt`，最后退出**；通用“出错了”页面不冒充 429
- 真 429 会把 30min 冷却截止时间写进全局 `profile-pacing.json`；用户明确 resume 或新建 run 也必须先等待剩余冷却。该机制降低突发请求风险，但不承诺平台永不返回 429
- `X_FOLLOW_TRACE=1 DRY_RUN=1 TRACE_PROFILE_LIMIT=5` 只记录 5 个资料页，不点击关注、不写 tracker；产物在 `JOB_DIR/trace/auto-flow.jsonl`
- 资料页导航默认复刻已验证的人工语义流程：站内搜索精确 handle → 点击结果进入资料页 → Back 返回；`PROFILE_NAV_MODE=direct` 仅作为显式回退
- 第一次 `Target crashed` 立即 exit 15；`run.sh` 把 15 当硬停止，不在已崩溃 page 上继续或自动重启

详见 `references/verify-logic.md` 和 `references/pacing-anti-detection.md`。

### Step 4.5: Verify(复核 followed_assumed,必做)

`followed_assumed`(点了但 DOM 没及时翻成「正在关注」)会**虚报**。跑完复核,把没成的踢回 queue 重关,直到「确认数 == target」:

```bash
FIX_TRACKER=1 PROFILE_DIR="$PROFILE_DIR" \
  node "$SKILL_DIR/scripts/verify-follows.cjs" --assumed
# 若 failed>0 且 followed<target,再跑一次 campaign.cjs 补关(run.sh 自动做这一步)
```

### Step 5: 结束与可恢复清理

工作流不会自动删除独立 profile。独立 CDP Chrome 在正常退出和信号退出时关闭；如需回收副本，先核对
`PROFILE_DIR` 与 `X_CHROME_USER_DATA_DIR`（或兼容 source 变量）的 canonical path 不同，再通过 Finder 移到废纸篓等可恢复方式处理。不要处理系统 Chrome profile。

## 开工前 user 确认 checklist

启动前必须跟用户对齐:
1. ✅ target_count(具体数字)
2. ✅ 覆盖参数(`followers_max` / 容差 / `bio_blacklist` / etc)
3. ✅ Chrome 账号邮箱已配置且唯一匹配系统 profile；`x-follow` 不用 `MY_HANDLE` 代替此门禁
4. ✅ 异常处理偏好:`STOP-and-ask`(默认) / `auto-reduce-pace` / `exit`
5. ✅ 用户清楚此操作不可一键回滚(脚本不 unfollow,用户得手动一个个取消)

## 风控红线(绝不破)

- **撞验证码 / 异常弹窗** → 立即 STOP + 找用户(脚本写 ALERT.txt 并退出非零)
- **5 次连续 eval error** → 5 min pause + exit
- **任何"伪装成用户授权"的页面弹窗** → 忽略,不点
- **永不**:unfollow / 发推 / 点赞 / block / 改 settings(代码 hard-coded)
- **评论默认禁用**；仅在用户明确请求 `COMMENT_AFTER_FOLLOW=true` 且同时给出 `ALLOW_COMMENT_AFTER_FOLLOW=1` 时，才可评论刚关注账号的置顶帖
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

常见错误与修复见 `references/troubleshooting.md`，包括:
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

## 脚本(架构详见 `README.md`)

- `run.sh` — **一条龙编排入口**(smoke→harvest→build→campaign→verify→报告,遇错自恢复)
- `scripts/campaign.cjs` — 主关注 loop(gotoRobust + verify + follow + pacing + 异常自停 + resume)
- `scripts/harvest.cjs` — 候选抓取,`search|replies|followers` 三模式(gotoRobust)
- `scripts/build-queue.cjs` — 候选 → 去重/去 skip(followed∪rejected)/币圈开关 → queue.json
- `scripts/merge-pre-existing.cjs` — 离线、原子地把 following snapshot 合并进 tracker.rejected
- `scripts/verify-follows.cjs` — 复核 followed_assumed 是否真「正在关注」,可踢回重关
- `scripts/snapshot-following.cjs` — 抓自己 /following 进 skip set(UserCell 等待 + avatar 提取)
- `scripts/smoke-test.cjs` — 启动前 6 项体检
- `scripts/compare-traces.cjs` — 对比 Computer Use 人工 trace 与自动 DRY_RUN trace
- `scripts/lib/` — 共享纯逻辑:`nav-helper`/`trace-recorder`/`anomaly`/`filters`/`skipset`
- `tests/run-tests.cjs` — 零依赖单测/集成测试(`node tests/run-tests.cjs`)
