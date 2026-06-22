# x-follow — 架构与开发文档

X (Twitter) 精准批量关注 skill。默认面向「蓝V互关」场景:关注**蓝V认证、粉丝数 < 1100、关注数 > 粉丝数、非币圈** 的小号,用人类化节奏 + 异常自停,安全地完成 N 个关注。

> 安全红线:**只点 `aria-label="关注 @{handle}"` 的关注按钮**,绝不 unfollow / 发推 / 点赞 / 评论 / 改设置;遇到验证码 / 限流 / 登录跳转 / 账号受限 **立即停止并写 `ALERT.txt`**,等人工确认。

---

## 1. Pipeline 总览

`run.sh` 是唯一入口,把各阶段编排成一条「遇错能自恢复」的流水线:

```
                ┌────────────────────────────── run.sh (orchestrator) ──────────────────────────────┐
                │                                                                                     │
  prior         │   ┌─────────┐   ┌──────────┐   ┌──────────────┐   ┌───────────┐   ┌─────────────┐  │
  trackers ─────┼──▶│ skipset │──▶│  smoke   │──▶│ harvest LOOP │──▶│ build     │──▶│  campaign   │  │──▶ tracker.json
  (~/.claude/   │   │ (union) │   │  test    │   │ until queue  │   │ queue     │   │  (watchdog) │  │    (followed[],
   jobs/...)    │   └─────────┘   └────┬─────┘   │ >= TARGET*8  │   │ +crypto   │   └──────┬──────┘  │     rejected[])
                │                      │RED       └──────────────┘   │  toggle   │          │         │
                │                      ▼                             └───────────┘          ▼         │
                │                  refuse launch          ┌── exit 0 & < target ───▶ harvest more ────┘
                │                                          │── exit 10-14 (anomaly) ─▶ HALT + ALERT.txt
                │                                          └── transient exit ───────▶ retry (pause)
                │                                                                                     │
                │   ┌──────────────────────────── verify & top-up (×3) ───────────────────────────┐  │
                │   │ verify-follows --assumed  ──▶ demote unconfirmed ──▶ campaign top-up ──▶ loop │  │
                │   └──────────────────────────────────────────────────────────────────────────────┘ │
                └─────────────────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
                                          report: follows / actions / rejects
```

**为什么是这个形状**(吸取 6 轮实战经验):

- **harvest 是循环,不是单次**:跑到第 N 轮后,新搜索与历史 skip-set 重叠很高(常 ~50% inSkip),单次 6 query 往往凑不够候选,所以「harvest → build → 数量够没?不够再 harvest」。
- **campaign 退出 0 但 < target = 队列耗尽**,不是成功——回到 harvest 补候选再续跑(`tracker.json` 让已关注的被跳过,天然幂等续跑)。
- **verify & top-up 不可省**:`followed_assumed`(点了但 DOM 没及时翻成「正在关注」)会**虚报**;实测 4 个里坏过 2 个。跑完必须复核、把没成的踢回去重关,直到「确认数 == target」。

---

## 2. 模块依赖

```
run.sh ─┬─ scripts/smoke-test.cjs ───────┐
        ├─ scripts/harvest.cjs ──────────┤
        ├─ scripts/build-queue.cjs ──────┤
        ├─ scripts/campaign.cjs ─────────┤
        ├─ scripts/verify-follows.cjs ───┤
        └─ scripts/snapshot-following.cjs┘
                                          │ require
                       ┌──────────────────┴───────────────────┐
                       ▼            ▼            ▼             ▼
              lib/nav-helper  lib/anomaly  lib/filters   lib/skipset
              (gotoRobust)    (classify+   (parseCount,  (tracker
                  │            detect+      isCrypto,     union)
                  └── uses ──▶ writeAlert)  decide,
                     filters.              backoffMs)
                     backoffMs
```

- **`lib/` 全是纯逻辑或薄封装**,被 `tests/run-tests.cjs` 直接 import 做单测(无需浏览器)。
- **`scripts/*.cjs` 各管一件事**,只通过 stdout JSON 通信,方便编排与测试。
- 浏览器内运行的 `VERIFY_JS`(在 `campaign.cjs` 里)无法 require lib,所以它的判定顺序**必须**和 `lib/filters.decide()` 一致——单测锁住这份契约。

---

## 3. 健壮性机制(遇错恢复)

| 故障 | 现象 | 处理 | 实现位置 |
|---|---|---|---|
| **HTTP 429**(SearchTimeline / UserByScreenName 配额) | 页面「出错了。请尝试重新加载」 | **指数退避**(20s→40s→80s→…→300s 封顶 + jitter)后**重新导航**,等待即恢复;绝不 reload 硬刷(那是给 429 喂请求) | `lib/nav-helper.gotoRobust` |
| **高延迟 VPN** | 固定 sleep 后页面还没渲染 → EMPTY_PAGE / 0 结果 / eval 报错 | 等真正的内容选择器(`waitForSelector`)而非定时器 | `gotoRobust(needSel)` |
| **异常误报**(对方推文里出现「账户被限制 / rate limit」) | 误判 ACCOUNT_RESTRICTED / RATE_LIMIT | 匹配只在页面 chrome,排除 `article`/`tweetText`(`inChrome`) | `lib/anomaly.classifyAnomaly` |
| **EMPTY_PAGE 误报**(/home SPA 壳 <50 字) | 启动体检 RED | 启动门控排除 EMPTY_PAGE + 等登录态元素 | `campaign.cjs` / `smoke-test.cjs` |
| **followed_assumed 虚报** | 计数 50 实际 48 | 跑完 `verify-follows --assumed` 复核,踢回未成的重关 | `verify-follows.cjs` + `run.sh` |
| **真异常**(验证码 / 限流 / 登录跳转 / 账号受限) | — | **立即停**,写 `ALERT.txt`,退出码 10-14,watchdog 不再重启 | `campaign.cjs` + `run.sh` |
| **连续报错 / profile 锁** | 浏览器卡死 / exit 99 级联 | 连续 5 错即停;每次启动前 kill 残留 Chrome + 删 SingletonLock | `campaign.cjs` / `run.sh` |
| **harvest 反复开关浏览器** | 每个搜索词冷启动 Chrome 一次 → ~6 次冷启 + 每次一波 429 | **一次 launch 跑完所有 query**(`search-multi`,同 context 顺序导航) | `harvest.cjs` |
| **non-blue 候选浪费 profile 访问** | 非蓝V 占 campaign 拒绝 ~50%,每个都要开 profile 才发现 | harvest 已带 `blue` 徽章 → `DROP_NONBLUE` 在 build-queue 阶段就丢掉(零浏览器) | `build-queue.cjs` |
| **候选池枯竭后空转** | queue 长期 0-4 仍反复 harvest+campaign(曾空转 1.5h) | 连续 `POOL_DRY_ROUNDS` 轮净增 `<POOL_MIN_GAIN` → 判定枯竭,优雅停止 | `run.sh` |
| **瞬时错误被永久拉黑** | 429/临时不可用记成 reject → 永久 skip 误杀合格账号 | skip-set **分级**:transient 永不 skip、soft(阈值)按 `SOFT_TTL_DAYS` 过期释放、permanent 永久 | `lib/skipset.cjs` |
| **tracker 无界膨胀** | 每轮把全部历史 skip 冻结成 `pre_existing` 复制进新 tracker | 新 tracker 只存本轮决策;skip-set 每次从 `SKIP_GLOB` 动态(分级)重算 | `build-queue.cjs` / `run.sh` |
| **后台跑看不到进度** | 只能 tail 日志 | 每账号/每阶段写单文件 `status.json`(含心跳 `ts`,可测卡死) | `campaign.cjs` / `run.sh` |

### 异常退出码 → watchdog 行为

```
campaign.cjs exit code
   0            → 干净退出(达标 或 队列耗尽)   run.sh: 达标则结束, 否则 harvest 续跑
   10 CAPTCHA   ┐
   11 RATE_LIMIT│
   12 LOGIN     ├─→ 真异常              run.sh: HALT, 保留 ALERT.txt, 不再操作账号
   13 RESTRICT  │
   14 WEBDRIVER ┘
   15 CONSEC_ERR / 16 EMPTY / 其它 → transient   run.sh: 暂停 20s 重试(上限 MAX_CAMPAIGN_ATTEMPTS)
```

---

## 4. 用法

```bash
# 一次性:从基础登录态 profile 复制一份工作副本(基础 profile 不被 MCP 占用时执行)
cp -R ~/.config/playwright-chrome-profile ~/.config/playwright-chrome-profile-campaign
rm -f ~/.config/playwright-chrome-profile-campaign/Singleton*

# 跑一轮(默认 target=10,蓝V互关 preset)
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
TARGET=10 MY_HANDLE=haoliucha JOB_DIR=/tmp/xf-run1 \
bash run.sh
```

常用 env(详见 `run.sh` 头部 / `references/presets.md`):

| env | 默认 | 说明 |
|---|---|---|
| `TARGET` | 10 | 目标关注数 |
| `MY_HANDLE` | (空) | 自己的 handle,用于 already-following 预过滤 |
| `PROFILE_DIR` | `~/.config/playwright-chrome-profile-campaign` | 工作 profile 副本 |
| `JOB_DIR` | `$(pwd)/.run` | tracker/queue/日志输出目录 |
| `QUERIES` | 求互关,互相关注,回关,求关注,蓝V互关,蓝V互粉 | harvest 搜索词 |
| `FILTER_CRYPTO` | 0 | **默认 0 = 不过滤币圈/web3**(允许关注);设 `1` 恢复过滤(蓝V互关 经典 preset) |
| `FERS_MAX` | 1100 | 粉丝上限 |
| `CAND_MULT` | 8 | harvest 到 `TARGET*CAND_MULT` 候选才开跑 |
| `VERIFIED_REQUIRED` | true | 仅蓝V;为 true 时自动开启 `DROP_NONBLUE`(build-queue 阶段丢非蓝V) |
| `SOFT_TTL_DAYS` | 30 | 软拒绝(粉丝/关注比阈值)过期天数,过期后重新评估 |
| `POOL_DRY_ROUNDS` / `POOL_MIN_GAIN` | 2 / 5 | 连续 N 轮 harvest 净增 < M → 判定候选池枯竭并停止 |

进度查看:`cat $JOB_DIR/status.json`(单行 JSON:phase / followed / target / 心跳 ts)。停止整轮:`kill -9 $(cat $JOB_DIR/run.pid)`。

> **币圈/web3 默认放开**(`FILTER_CRYPTO=0`):多轮跑下来非币圈蓝V小号会枯竭,放开币圈能让候选池和通过率保持健康。要恢复过滤改 `FILTER_CRYPTO=1`。无论开关,**蓝V / 粉丝<1100 / 关注>粉丝 始终生效**——「放开币圈 ≠ 放开大号」(币圈大号仍被 `FERS_MAX` 挡掉)。底层用 `NOCRYPTO`(build-queue)+ `BIO_BLACKLIST`(campaign,空串会回退默认词表故用占位 token)实现,`run.sh` 已封装成单一 `FILTER_CRYPTO` 开关。

---

## 5. 测试

```bash
node tests/run-tests.cjs      # 纯逻辑 + build-queue 集成,45 项,无需浏览器
```

覆盖:`parseCount`(万/亿/K/M/B/逗号/异常)、`isCryptoHandle`、`decide` 全部判定分支与顺序、`backoffMs` 退避表 + 封顶、`buildSkipSet` 并集去重、`classifyAnomaly`(尤其 **推文正文不误触发** 这条核心修复)、`build-queue` 的 followed∪rejected 跳过 + 币圈开关。

真·浏览器 E2E 需要 X 登录态,由 `run.sh` 对真实 X 跑(见用法);CI 能跑的部分由上面的单测锁定。`DRY_RUN=1` 可让 campaign 只验证选择器+不点击。

---

## 6. 文件清单

```
run.sh                      # 编排入口
scripts/
  campaign.cjs              # 主关注 loop(gotoRobust + 异常自停 + 节奏 + verify)
  harvest.cjs               # 候选抓取(search|search-multi|replies|followers,单浏览器多 query,gotoRobust)
  build-queue.cjs           # 候选 → 去重/去 skip(followed∪rejected)/币圈开关 → queue.json
  verify-follows.cjs        # 复核 followed_assumed 是否真「正在关注」,可踢回重关
  snapshot-following.cjs    # 抓 /following(UserCell 等待 + avatar testid 提取)
  smoke-test.cjs            # 启动前 6 项体检
  lib/
    nav-helper.cjs          # gotoRobust:429/延迟容错导航(指数退避)
    anomaly.cjs             # 异常分类(纯 classifyAnomaly + 浏览器注入串 + writeAlert)
    filters.cjs             # parseCount / isCryptoHandle / decide / backoffMs / CRYPTO_TOKENS
    skipset.cjs             # 历史 tracker 并集 → skip-set
tests/run-tests.cjs         # 零依赖单测/集成测试
references/                 # preset / 候选源 / 节奏反检测 / 排错 / 判定逻辑 说明
```
