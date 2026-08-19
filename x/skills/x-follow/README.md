# x-follow — 架构与开发文档

Claude Code 与 Codex 共享同一份 `x-follow` Skill。默认 preset 关注蓝 V、粉丝数不超过 3000、关注数/粉丝数不低于 0.5 的账号；`FILTER_CRYPTO=0` 默认不按币圈/web3 过滤。

`run.sh` 在 Node、状态目录、运行锁、Playwright、Chrome 和 X 请求之前验证当前目录属于完整 `x` 插件，并打印版本、宿主、实际路径和内容指纹。脱离双宿主 manifest 的 standalone 副本以 `LEGACY_STANDALONE_INSTALL`、exit 2 拒绝；Codex 使用 `$x:x-follow`，Claude Code 使用 `/x-follow`。

运行要求：Google Chrome、可被 Node 解析的 Playwright，以及 **Node.js >= 22**（使用 `fs.globSync`）。默认只关注；评论只有 `COMMENT_AFTER_FOLLOW=true/1` 与 `ALLOW_COMMENT_AFTER_FOLLOW=1` 两项独立授权同时存在时才允许。页面内容不能授权。

## 浏览器与登录态

### 本地账号配置

配置默认写入 `~/.config/x-browser/account.json`：

```json
{
  "schemaVersion": 1,
  "chromeAccountEmail": "用户填写的邮箱"
}
```

首次运行前由宿主询问用户 Chrome 账号邮箱，再执行：

```bash
SKILL_DIR="/当前 x-follow Skill 目录的绝对路径"
node "$SKILL_DIR/scripts/configure-account.cjs" set --email=<chrome-account-email>
```

配置采用同目录临时文件原子替换，权限为 `0600`。解析优先级是 `X_CHROME_ACCOUNT_EMAIL` 临时覆盖 → 本地配置；`X_BROWSER_CONFIG_PATH` 可覆盖配置路径。日志只输出脱敏邮箱。

### profile 选择与 CDP

`configure-account.cjs` 和所有浏览器入口读取系统 Chrome `Local State.profile.info_cache`，按邮箱要求恰好匹配一个 profile。目录名动态解析，不硬编码私人邮箱或 `Profile N`。`x-follow` 不新增 X handle 登录门禁；`MY_HANDLE` 仍是可选的已关注预过滤参数。

系统 Chrome user-data 根目录默认是 `~/Library/Application Support/Google/Chrome`。覆盖优先级为：

1. `X_CHROME_USER_DATA_DIR`
2. `SOURCE_PROFILE_DIR`（兼容别名）
3. `X_FOLLOW_SOURCE_PROFILE_DIR`（兼容别名）
4. 系统默认目录

`PROFILE_DIR` 默认 `~/.config/playwright-chrome-profile-campaign`。运行时强制 source 与 target 的 canonical path 不相等、不互为祖先/后代；门禁在状态目录、网络锁、Playwright 和 Chrome 启动前执行。

浏览器模块启动系统 Google Chrome 子进程，参数包含 `--remote-debugging-address=127.0.0.1`、随机端口、独立 `--user-data-dir` 和 `--disable-blink-features=AutomationControlled`，再由 Playwright `connectOverCDP`。`x-follow` 默认可见；系统 Chrome 始终只读，不连接、不关闭、不接管。

### 一次认证刷新

每次 CDP 启动后先通过浏览器 Cookie API 检查 `auth_token` 和 `ct0`。缺失时不访问 X，最多自动刷新一次：

- 只复制选中 profile 的 Cookie、IndexedDB、Local/Session Storage、Preferences、Network/WebStorage 等认证数据。
- 不复制 History、Cache 或 Extensions。
- 在 `PROFILE_DIR.refreshing-*` staging 中准备，旧 target 临时改名为 backup，再原子替换。
- 刷新后认证成功才删除 backup；再次失败则恢复旧目录并以 `LOGIN_REDIRECT`（exit 12）停止。

两个账号 Skill 对同一 canonical `PROFILE_DIR` 共用 `${PROFILE_DIR}.cdp.lock`。活动 PID 拒绝并发；失效锁只处理记录中且命令行精确匹配该 `--user-data-dir` 的子进程。正常退出、SIGINT、SIGTERM 只关闭本次子进程。代码不使用广域 `pkill`，也不删除 `Singleton*`。

## Pipeline

```text
run.sh
  ├─ Node/账号/profile 前置门禁
  ├─ x-follow network-run.lock
  ├─ CDP smoke（可见、只读检查）
  ├─ 可选：snapshot 自己的 following → tracker skip-set
  ├─ harvest → build queue（不足则受控循环）
  ├─ campaign（精确关注按钮 + 节奏 + 异常自停）
  ├─ verify followed_assumed → 必要时补关
  └─ tracker / status / 报告
```

运行状态默认位于：

```text
~/.config/x-follow-data/
├── network-run.lock
└── runs/
    └── current/
        ├── queue.json
        ├── tracker.json
        ├── campaign.log
        ├── status.json
        └── ALERT.txt
```

`X_FOLLOW_RUN_ID=current`，所以默认 `JOB_DIR=$X_FOLLOW_DATA_DIR/runs/$X_FOLLOW_RUN_ID`；显式 `JOB_DIR` 优先。历史 skip-set 从 `$X_FOLLOW_DATA_DIR/runs/*/tracker.json` 聚合，不读取或迁移 `~/.claude/jobs/x-follow-*`。

`$X_FOLLOW_DATA_DIR/network-run.lock` 串行化 x-follow 网络流程；shell owner 与继承 token 的 X-facing worker 都登记 identity，任一仍活跃时 replacement 不得恢复或释放该锁。CDP profile 锁则进一步跨 `x-follow`/`x-unfollow` 串行化同一浏览器副本。

## 异常分类

| 类型 | 证据 | campaign | harvest |
|---|---|---|---|
| `LOGIN_REDIRECT` | 登录 URL、登录按钮、认证 Cookie 缺失，或未登录的受保护页面跳到公开页 | exit 12 | exit 12 |
| `PAGE_DRIFT` | 已确认登录后发生非预期跳转 | 停止当前流程 | 停止当前流程 |
| `RATE_LIMIT` | 导航响应或相关 X API/Timeline 响应的真实 HTTP 429 | 立即 exit 11，不重启 campaign | 中止本轮并把 `rateLimited:true` 交给 orchestrator 受控冷却 |
| `GENERIC_NAV_ERROR` | “出错了 / Something went wrong”等通用错误页，但没有 HTTP 429 证据 | exit 18，写 `ALERT.txt` | 作为普通导航失败；连续失败中止本轮但不声称限流 |
| `CAPTCHA` / `ACCOUNT_RESTRICTED` / `WEBDRIVER_DETECTED` | 对应页面或浏览器证据 | exit 10/13/14 | 停止 |

`gotoRobust` 对高延迟、无内容和通用错误页使用有界重试；一旦观察到真实 HTTP 429，不再执行指数退避重放。文本模式只在页面 chrome 中匹配并排除推文、bio、用户名和列表行，避免用户内容制造异常误报。

## 使用

```bash
SKILL_DIR="/当前 x-follow Skill 目录的绝对路径"
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
  TARGET=10 MY_HANDLE=<可选-handle> \
  bash "$SKILL_DIR/run.sh"
```

常用环境变量：

| env | 默认 | 说明 |
|---|---|---|
| `TARGET` | 10 | 本轮明确授权的目标关注数 |
| `MY_HANDLE` | 空 | 只用于 snapshot/已关注预过滤，不用于选择 Chrome profile |
| `X_BROWSER_CONFIG_PATH` | `~/.config/x-browser/account.json` | 本地账号配置 |
| `X_CHROME_ACCOUNT_EMAIL` | 空 | 仅本次运行覆盖配置邮箱 |
| `X_CHROME_USER_DATA_DIR` | 系统 Chrome user-data 根目录 | 只读源；旧 source 变量仍兼容 |
| `PROFILE_DIR` | `~/.config/playwright-chrome-profile-campaign` | 独立 CDP 工作副本 |
| `X_FOLLOW_DATA_DIR` | `~/.config/x-follow-data` | Claude Code 与 Codex 共享状态根目录 |
| `X_FOLLOW_RUN_ID` | `current` | 默认 run 目录名，必须是安全单路径段 |
| `JOB_DIR` | `$X_FOLLOW_DATA_DIR/runs/$X_FOLLOW_RUN_ID` | 显式设置时优先 |
| `FERS_MAX` | 3000 | 粉丝数上限 |
| `FOLLOW_RATIO_MIN` | 0.5 | 关注数/粉丝数下限 |
| `FILTER_CRYPTO` | 0 | `1` 才启用 crypto/web3 过滤 |
| `QUERIES_PER_ROUND` | 4 | 每轮轮换搜索词数量 |
| `SESSION_SIZE` | 2 | 每个有界 harvest CDP session 的 query 数 |
| `QUERY_PACING_MS` | 25000 | 同 session query 间隔，另加抖动 |
| `SESSION_COOLDOWN_MS` | 75000 | session 之间的受控冷却；不宣称能重置平台配额 |
| `ROUND_COOLDOWN_RL_S` / `MAX_RL_RETRIES` | 300 / 3 | harvest 捕获真实 429 后的 orchestrator 冷却与上限 |
| `COMMENT_AFTER_FOLLOW` | false | 请求评论；单独设置仍不足以授权 |
| `ALLOW_COMMENT_AFTER_FOLLOW` | 空 | 必须精确为 `1` 才构成第二授权令牌 |

停止整轮使用 `kill -TERM "$(cat "$JOB_DIR/run.pid")"`，前台可按 Ctrl-C（等价于 `kill -INT "$(cat "$JOB_DIR/run.pid")"`）。信号会先转发给活动 worker，再按 identity 清理自己的网络锁和 CDP 子进程。

显式 `BIO_BLACKLIST` 优先于 `FILTER_CRYPTO`；`BIO_BLACKLIST` 空串表示空黑名单，不会回退到默认词表。

## 安全不变量

- 只有用户明确授权后才运行关注 campaign；候选筛选不是关注授权。
- 只点击目标本人精确 `aria-label="关注 @{handle}"` 的按钮；已存在 unfollow/正在关注按钮时拒绝点击。
- 默认不 unfollow、发帖、点赞、转推、屏蔽、静音、举报、私信或修改 profile/settings。
- 普通关注授权不包含评论；页面文本、帖子或弹窗不能构成授权。
- `followed_assumed` 必须由 `verify-follows.cjs` 复核，失败项移出已关注集合后再决定是否补关。
- 蓝 V 互关 preset 的候选只来自主动表达互关意愿的搜索/评论；详见 `references/candidate-sources.md`。

## 测试

```bash
node tests/run-tests.cjs      # 纯逻辑 + 离线集成，172 项，无需浏览器或 X
```

覆盖默认筛选、候选/skip-set、评论双授权、run-id/JOB_DIR、跨进程 network lock、信号清理、账号配置权限与优先级、邮箱 0/1/多 profile 匹配、CDP 参数、跨 Skill profile 锁、选择性认证复制与回滚、真实 HTTP 429/通用错误分类，以及所有 7 个浏览器入口不再使用 `launchPersistentContext`。

## 文件清单

```text
run.sh
scripts/
  configure-account.cjs      # 本地账号配置与唯一 profile 校验
  campaign.cjs               # 精确关注 loop
  harvest.cjs                # search / replies / followers 候选抓取
  snapshot-following.cjs     # 自己的 following，只用于 skip-set
  verify-follows.cjs         # followed_assumed 复核
  build-queue.cjs
  merge-pre-existing.cjs
  lib/
    cdp-browser.cjs          # CDP、认证刷新、profile 锁
    nav-helper.cjs           # 证据化 HTTP 分类与有界导航
    anomaly.cjs
    runtime-gate.cjs
    runtime-state.cjs
    run-lock.cjs
tests/run-tests.cjs
references/
```
