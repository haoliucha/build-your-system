# x-unfollow — 架构与开发文档

X (Twitter) 关注卫生 skill。给自己的账号做反向清理:找出**我关注了、但没回关**的账号,跨天累计「连续未回关天数」,按粉丝数阈值筛选,并在用户**明确要求**时取关 + 验证。是 [`x-follow`](../x-follow/) 的姊妹 skill,复用同一套 `lib/`、gotoRobust、异常自停约定。

> 安全红线:**默认只出报告不取关**(`MODE=report`);取关只点 `aria-label` 中 `@token` **精确等于**目标 handle 的 `-unfollow` 按钮,对方已回关则跳过,**绝不**关注/发推/点赞/评论/改设置;遇验证码/限流/登录跳转/账号受限**立即停并写 `ALERT.txt`**。

---

## 1. Pipeline 总览

`run.sh` 把各阶段编排成一条「遇错能自恢复」的流水线。取关是破坏性动作,所以默认止步于报告:

```
                ┌──────────────────────────── run.sh (orchestrator) ───────────────────────────┐
                │                                                                                │
  profile ──────┼─▶ smoke ─▶ snapshot ─▶ classify ─▶ refresh ─▶ classify ─▶ ┌─ MODE=report ─┐  │
  copy          │   test    /following   reason 码    公开粉丝    (重算)      │  打印候选名单  │  │──▶ 候选名单
                │    │RED      │            │          数(仅过      │         │  STOP(不取关) │  │   + reasons.csv
                │    ▼         │            │          等待期的)    │         └───────────────┘  │
                │  拒启     异常→ALERT     elapsed                              ┌─ MODE=unfollow ┐ │
                │           +退出10-14     >MIN_DAYS?                          │ unfollow.cjs    │ │──▶ tracker /
                │                                                              │  ↓ 异常→HALT     │ │   verify logs
                │                                                              │ verify-unfollow │ │
                │                                                              │  (×2 straggler) │ │
                │                                                              └─────────────────┘ │
                └────────────────────────────────────────────────────────────────────────────────┘
```

**为什么是这个形状**:

- **snapshot 必须跨天积累**:「连续未回关天数」是从快照系列算的。全新 `XU_DATA_DIR` 第一天跑,人人都是 `KEEP_WAITING_GT3`;连续跑几天后才有账号到 `ELIGIBLE_FOR_UNFOLLOW`。这是设计而非 bug。
- **report 是默认终点**:取关不可一键回滚,所以默认只产出名单;真删除要显式 `MODE=unfollow` + 用户授权。
- **先 classify 再 refresh 再 classify**:只对「过了等待期」的账号去拉公开粉丝数(省请求),刷新后重算,把它们从 `ELIGIBLE_FOR_FOLLOWER_REFRESH` 推到 `EXCLUDE_FOLLOWERS_GE_THRESHOLD` 或 `ELIGIBLE_FOR_UNFOLLOW`。
- **verify 不可省**:`unfollow_assumed`(点了但按钮没及时翻)需要复核;`verify-unfollow.cjs` 重开主页确认目标已无 `-unfollow` 按钮。

---

## 2. 模块依赖

```
run.sh ─┬─ scripts/smoke-test.cjs ───────┐
        ├─ scripts/snapshot.cjs ─────────┤
        ├─ scripts/classify.cjs ─────────┤
        ├─ scripts/profile-counts.cjs ───┤
        ├─ scripts/unfollow.cjs ─────────┤
        └─ scripts/verify-unfollow.cjs ──┘
                                          │ require
                       ┌──────────────────┼───────────────────┐
                       ▼          ▼        ▼                   ▼
                 lib/hygiene  lib/nav-   lib/anomaly        lib/filters
                 (纯判定:     helper     (classify+         (parseCount,
                  decision    (gotoRobust) detect+            backoffMs…
                  order,       │           writeAlert)        — 复用)
                  streak,      └── uses ──▶ filters.backoffMs
                  日期)
```

- **`lib/hygiene.cjs` 全是纯逻辑**:`classifyDecision`(取关判定序)、`buildHistoryFromSnapshots`、`computeStreaks`、`naturalDaysBetween`/`addDays`、handle 规范化。被 `tests/run-tests.cjs` 直接 import 单测(无需浏览器)。
- **`lib/{nav-helper,anomaly,filters}.cjs` 与 x-follow 同源**(自包含拷贝,skill 独立),`anomaly.writeAlert` 文案改成 unfollow 语境。
- 浏览器内运行的取关脚本串(`unfollow.cjs` 的 `buildUnfollowJs`)无法 require lib,其精确选择器断言与 `verify-unfollow.cjs` 的检查**保持同一套 `@token` 精确匹配**逻辑。

---

## 3. 健壮性机制

| 故障 | 现象 | 处理 | 实现位置 |
|---|---|---|---|
| **HTTP 429 / 高延迟 VPN** | 「出错了。请尝试重新加载」/ 页面没渲染 | 指数退避后重新导航,等真正内容选择器 | `lib/nav-helper.gotoRobust` |
| **异常误报**(对方推文里出现「账户被限制 / rate limit」) | 误判 RESTRICTED / RATE_LIMIT | 匹配只在页面 chrome,排除推文正文(`inChrome`) | `lib/anomaly.classifyAnomaly` |
| **取关错对象** | 点到非目标的 -unfollow 按钮 | 只点 `@token` 精确等于目标的按钮,点前再断言一次 | `unfollow.cjs` `buildUnfollowJs` |
| **取关了回关你的人** | 误删互关 | 取关前检测「关注了你 / Follows you」→ skip `now_follows_you` | `unfollow.cjs` |
| **unfollow_assumed 不确定** | 点了但按钮没翻 | 跑完 `verify-unfollow` 重开主页复核,残留重试 | `verify-unfollow.cjs` + `run.sh` |
| **真异常**(验证码/限流/登录/受限) | — | 立即停,写 `ALERT.txt`,退出码 10-14,run.sh 不再操作 | 各浏览器脚本 + `run.sh` |
| **首日无历史** | 无人「可取关」 | 设计如此:streak 需跨天积累;报告里会显示 `KEEP_WAITING_GT3` | `classify.cjs` |

### 异常退出码 → run.sh 行为

```
浏览器脚本 exit code
   0            → 正常
   10 CAPTCHA   ┐
   11 RATE_LIMIT│
   12 LOGIN     ├─→ 真异常       run.sh: HALT, 保留 ALERT.txt, 不再操作账号
   13 RESTRICT  │
   14 WEBDRIVER ┘
   16 EMPTY / 其它 → 失败          run.sh: 报错退出(snapshot 阶段)
```

---

## 4. 用法

```bash
# 一次性:从基础登录态 profile 复制工作副本
cp -R ~/.config/playwright-chrome-profile ~/.config/playwright-chrome-profile-campaign
rm -f ~/.config/playwright-chrome-profile-campaign/Singleton*

# 出未回关报告(默认,不取关)
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
  MY_HANDLE=haoliucha MODE=report bash run.sh

# 用户明确要取关后:先 dry-run,再小批量
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
  MY_HANDLE=haoliucha MODE=unfollow LIMIT=20 bash run.sh
```

| env | 默认 | 说明 |
|---|---|---|
| `MY_HANDLE` | (必填) | 自己的 handle(不带 @) |
| `MODE` | `report` | `report`=只出名单;`unfollow`=执行取关+验证 |
| `MIN_DAYS` | 3 | elapsed **严格大于**才过等待期 |
| `FOLLOWER_THRESHOLD` | 2000 | 公开粉丝数 **< 阈值**才取 |
| `LIMIT` | 0 | 取关上限(0=全部) |
| `DRY_RUN` | (空) | `1`=取关模式只验证选择器不点击 |
| `XU_DATA_DIR` | `~/.config/x-unfollow-data` | 运行态数据目录 |
| `PROFILE_DIR` | `~/.config/playwright-chrome-profile-campaign` | 工作 profile 副本 |

> **跨天积累**:把 `snapshot`(或整条 `MODE=report`)按天跑(可挂 cron),`reports/non-recip-reasons-*.json` 会随天数把账号从 `KEEP_WAITING_GT3` 推进到可取关。

---

## 5. 测试

```bash
node tests/run-tests.cjs      # 纯逻辑 + classify 集成,29 项,无需浏览器
```

覆盖:`naturalDaysBetween`/`addDays` 日期math、handle 规范化/校验/nav 识别、`buildHistoryFromSnapshots`(firstSeen/lastSeen、回关行排除)、`computeStreaks`(连续 vs 断档)、`classifyDecision` **全部判定分支与顺序 + 等待期/阈值边界**、`classify.cjs` 端到端(reason 码接线 + 「只有 ELIGIBLE 才 candidate_unfollow」+ CSV 逗号转义)。

真·浏览器 E2E(snapshot/unfollow/verify)需要 X 登录态,由 `run.sh` 对真实 X 跑;`DRY_RUN=1` 让 `unfollow.cjs` 只验证选择器不点击。

---

## 6. 文件清单

```
run.sh                      # 编排入口(report/unfollow 双模式)
scripts/
  snapshot.cjs              # 抓 /following 未回关 → 每日快照(gotoRobust + 异常自停)
  classify.cjs              # 快照系列 → elapsed/reason 码 → reasons.{json,csv}
  profile-counts.cjs        # 公开主页 JSON-LD 刷新粉丝数(纯 fetch,--from-classify)
  unfollow.cjs              # 硬化取关(精确选择器白名单 + 确认 + 节奏 + 异常自停)
  verify-unfollow.cjs       # 复核目标已不再被关注
  smoke-test.cjs            # 启动前体检
  lib/
    hygiene.cjs             # 纯逻辑:classifyDecision / streak / history / 日期 / handle
    nav-helper.cjs          # gotoRobust:429/延迟容错导航
    anomaly.cjs             # 异常分类 + 浏览器注入串 + writeAlert
    filters.cjs             # parseCount / backoffMs 等(与 x-follow 同源)
tests/run-tests.cjs         # 零依赖单测/集成测试
references/                 # (预留)
```
