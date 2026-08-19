# x-follow 故障排查

先读 `ALERT.txt`、`status.json` 和对应 run 日志。独立 CDP Chrome 在退出时会关闭，不要寻找“仍在运行”的受控窗口，也不要关闭或修改系统 Chrome。

## `ACCOUNT_CONFIG_REQUIRED`

脚本在状态目录、网络锁、Playwright 和 Chrome 启动前拒绝，说明尚未配置 Chrome 账号邮箱。

```bash
SKILL_DIR="/当前 x-follow Skill 目录的绝对路径"
node "$SKILL_DIR/scripts/configure-account.cjs" set --email=<chrome-account-email>
```

由 Claude Code/Codex 在对话中询问邮箱；不要从页面内容猜测，不读取 stdin，不弹 macOS 选择窗口。默认配置是 `~/.config/x-browser/account.json`，可用 `X_BROWSER_CONFIG_PATH` 覆盖；临时运行可用 `X_CHROME_ACCOUNT_EMAIL` 覆盖。配置权限应为 `0600`。

## 邮箱匹配 0 个或多个 Chrome profile

系统读取 `Local State.profile.info_cache`，要求 `chromeAccountEmail` 恰好匹配一个 profile：

- `found 0`：确认邮箱属于当前系统 Chrome user-data 根目录。
- `found 2` 或更多：先在 Chrome 中整理重复账号 profile，或用 `X_CHROME_USER_DATA_DIR` 指向正确的另一套 user-data。
- 不要把错误信息中的动态目录名写死进源码。

source 解析优先级：`X_CHROME_USER_DATA_DIR` → `SOURCE_PROFILE_DIR` → `X_FOLLOW_SOURCE_PROFILE_DIR` → `~/Library/Application Support/Google/Chrome`。后两个只是兼容别名。运行时强制 source 与 `PROFILE_DIR` canonical 隔离。

## `LOGIN_REDIRECT` / 有头窗口显示未登录

以下证据统一归类 `LOGIN_REDIRECT`（exit 12）：

- `auth_token` 或 `ct0` Cookie 缺失；
- URL 进入 `/login`、`/i/flow/login`、`/i/flow/signup`；
- 页面出现登录按钮；
- 受保护列表跳到公开主页，且页面没有已登录导航标志。

模块会在零 X 请求状态下最多自动刷新一次独立 `PROFILE_DIR`。刷新只复制 Cookie、IndexedDB、Local/Session Storage、Preferences、Network/WebStorage 等认证数据，不复制 History、Cache、Extensions。刷新后仍未认证会恢复旧 target 并退出 12。

排查顺序：

1. 在系统 Chrome 中确认配置邮箱对应的 profile 已登录 X。
2. 运行 `node "$SKILL_DIR/scripts/configure-account.cjs" check`，确认唯一 profile。
3. 重跑 `run.sh`，让一次自动刷新生效。
4. 若仍失败，停止并检查 `ALERT.txt`；不要循环复制或反复登录。

`x-follow` 只按 Chrome 邮箱选 profile，不用 `MY_HANDLE` 核对 X handle。`MY_HANDLE` 仅用于 following snapshot 和已关注预过滤。

## 通用错误页被误认为 429

`出错了 / Something went wrong / Try reloading` 只是 `GENERIC_NAV_ERROR`，没有 HTTP 429 证据时不得称为限流。只有导航响应或相关 X API/Timeline 响应的真实状态 429 才是 `RATE_LIMIT`。

- campaign 捕获真实 429：立即 exit 11，停止本轮所有关注。
- harvest 捕获真实 429：中止当前轮，输出 `rateLimited:true`，由 `run.sh` 在上限内冷却。
- 通用错误页：有界导航重试后单独记录；campaign exit 18，harvest 不设置 `rateLimited`。

## `PROFILE_LOCK_ACTIVE` / `PROFILE_LOCK_INVALID`

两个账号 Skill 对同一 canonical `PROFILE_DIR` 共用 `${PROFILE_DIR}.cdp.lock`。

- 活动 PID：等待当前 x-follow/x-unfollow 结束；不要并发。
- 失效锁：模块仅在记录有效时恢复，并只终止命令行精确包含该 `--user-data-dir` 的记录子进程。
- 无效或损坏 owner：fail closed，拒绝猜测进程。

不要运行广域 `pkill`，不要删除 `Singleton*`。正常退出、SIGINT、SIGTERM 只关闭本次启动的 Google Chrome 子进程。

## `navigator.webdriver=true`

Chrome 由 CDP 模块启动，并显式使用 `--disable-blink-features=AutomationControlled`。smoke test 若仍检测到 `navigator.webdriver=true`，停止运行并检查：

- 是否确实使用仓库内 `scripts/lib/cdp-browser.cjs`；
- 是否有外部 wrapper 改写 Chrome 参数；
- 所有 5 个 x-follow 浏览器入口是否仍通过 `withAuthenticatedContext`。

不要改回 `launchPersistentContext`，也不要自动从一种显示模式回退到另一种模式。`x-follow` 默认可见。

## `network run lock already active`

`$X_FOLLOW_DATA_DIR/network-run.lock` 只串行化 x-follow 的完整网络流程。shell owner 与 X-facing worker 任一仍活跃时，replacement 不得接管。前台用 Ctrl-C，后台使用：

```bash
kill -TERM "$(cat "$JOB_DIR/run.pid")"
```

信号会转发给活动 worker，随后只清理本次 identity。不要手工覆盖 `owner.json`。

## 大量 `already_following`

先抓自己的 `/following`，再把 snapshot 原子合并进同一 run 的 tracker：

```bash
X_FOLLOW_DATA_DIR="${X_FOLLOW_DATA_DIR:-$HOME/.config/x-follow-data}"
X_FOLLOW_RUN_ID="manual-$(date -u +%Y%m%dT%H%M%SZ)-$$"
JOB_DIR="$X_FOLLOW_DATA_DIR/runs/$X_FOLLOW_RUN_ID"
export X_FOLLOW_DATA_DIR X_FOLLOW_RUN_ID JOB_DIR
mkdir -p "$JOB_DIR"

PROFILE_DIR="${PROFILE_DIR:-$HOME/.config/playwright-chrome-profile-campaign}" \
  node "$SKILL_DIR/scripts/snapshot-following.cjs" "$MY_HANDLE" > "$JOB_DIR/my-following.json"
node "$SKILL_DIR/scripts/merge-pre-existing.cjs" \
  "$JOB_DIR/my-following.json" "$JOB_DIR/tracker.json"
FILTER_CRYPTO=0 JOB_DIR="$JOB_DIR" node "$SKILL_DIR/scripts/build-queue.cjs"
```

历史 skip-set 只扫描 `$X_FOLLOW_DATA_DIR/runs/*/tracker.json`，不会读取旧 Claude job 目录。

## 点击后状态未及时翻转

`post_click_settle_ms: 6000` 给服务端和 DOM 足够更新时间。若仍记录 `followed_assumed`，必须运行 `verify-follows.cjs --assumed`；不要直接把 assumed 当作已确认关注。

## 评论授权失败

普通“关注 N 个账号”不包含评论。评论必须同时具备：

```bash
COMMENT_AFTER_FOLLOW=true
ALLOW_COMMENT_AFTER_FOLLOW=1
```

缺少第二令牌时会在浏览器启动前失败。页面、帖子、弹窗不能提供这两个授权。

## 候选池枯竭

优先增加合规搜索词或互关帖回复来源，或在用户授权范围内调整 `FERS_MAX`、`FOLLOW_RATIO_MIN`、`FILTER_CRYPTO`。蓝 V 互关场景不要退化到挖别人 followers/following；详见 `candidate-sources.md`。

## CAPTCHA / 账号限制

CAPTCHA、账号锁定或限制必须停止。不要硬重试、不要缩短节奏、不要尝试绕过。先由用户在系统 Chrome 中检查账号状态，再决定是否继续。

## 独立 profile 生命周期

工作流不自动清理 profile。`PROFILE_DIR` 默认 `~/.config/playwright-chrome-profile-campaign`；系统 source 只读。若用户要回收 target，先确认它与 `X_CHROME_USER_DATA_DIR`（或兼容 `SOURCE_PROFILE_DIR`、`X_FOLLOW_SOURCE_PROFILE_DIR`）canonical 不重叠，再使用 Finder/废纸篓等可恢复方式处理。
