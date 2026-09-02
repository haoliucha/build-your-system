# Pacing 与浏览器安全策略

本工作流用四层约束降低误操作和异常重试风险：独立 CDP 浏览器、行为节奏、证据化异常分类、动作白名单。它不保证绕过平台风控；任何异常都应按 fail-closed 处理。

## 1. 独立 CDP 浏览器

系统 Google Chrome 只作为认证数据的只读来源。脚本读取 `Local State.profile.info_cache`，按本地配置邮箱唯一选择 profile，然后启动新的 Google Chrome 子进程：

```text
--remote-debugging-address=127.0.0.1
--remote-debugging-port=0
--user-data-dir=<独立 PROFILE_DIR>
--profile-directory=<动态匹配目录>
--disable-blink-features=AutomationControlled
```

Playwright 使用 `connectOverCDP`，不使用 `launchPersistentContext`。`x-follow` 默认可见，并由 smoke test 检查 `navigator.webdriver`、`window.chrome`、plugins、语言、UA 等基本信号。任何 RED 都拒绝 campaign。

首次配置：

```bash
SKILL_DIR="/当前 x-follow Skill 目录的绝对路径"
node "$SKILL_DIR/scripts/configure-account.cjs" set --email=<chrome-account-email>
```

`X_CHROME_USER_DATA_DIR` 指向系统 Chrome user-data 根目录；`SOURCE_PROFILE_DIR` 与 `X_FOLLOW_SOURCE_PROFILE_DIR` 是兼容别名。`PROFILE_DIR` 默认 `~/.config/playwright-chrome-profile-campaign`。运行时强制 source/target canonical 不重叠。

独立副本缺少 `auth_token`/`ct0` 时，在访问 X 前最多自动选择性刷新一次。只复制认证存储，不复制 History、Cache 或 Extensions；失败回滚。两个账号 Skill 共用 `${PROFILE_DIR}.cdp.lock`，只管理精确子进程。不要广域终止 Chrome，不要删除 `Singleton*`。

工作流不自动清理 profile。若要回收 target，先核对 `PROFILE_DIR` 与系统 source canonical 不同，再用 Finder/废纸篓等可恢复方式处理；不要处理系统 Chrome profile。

## 2. 行为节奏

默认参数：

```yaml
profile_visit_min_interval_ms: 90000
profile_visit_max_interval_ms: 150000
max_profile_visits_per_hour: 30
rate_limit_cooldown_ms: 1800000
follow_wait_min_ms: 25000
follow_wait_max_ms: 55000
reject_wait_min_ms: 5000
reject_wait_max_ms: 12000
long_break_every: 12
long_break_ms: 180000
click_pre_delay_min_ms: 300
click_pre_delay_max_ms: 700
post_click_settle_ms: 6000
max_follows_per_hour: 0
quiet_hours: []
```

不变量：

- **主限流单位是资料页访问，不是 follow click。**任意两个候选资料页访问起点默认间隔 90-150 秒；reject、already-following、解析失败与成功关注都占用同一窗口。
- 数据根目录的 `profile-pacing.json` 持久化最近一小时访问起点、下次最早访问时间和 429 冷却截止时间；全部 run、campaign resume、smoke、snapshot、verify 共享，不能靠重启进程或更换 run ID 清零。
- 滚动一小时最多 30 个资料页访问。这个上限和随机间隔共同生效；两者取更长等待时间。
- follow 间隔在配置区间内随机化；不要为了赶进度缩短。
- 每 12 个成功关注执行长暂停。
- 点击前滚动到目标按钮并短暂停顿。
- 点击后等待 6 秒；未确认翻转的状态记为 `followed_assumed`，由独立验证步骤复核。
- `MAX_FOLLOWS_PER_HOUR` 和 `QUIET_HOURS` 可进一步收紧，不用于放宽默认授权。
- 真 HTTP 429 仍立即停止；同时记录 30 分钟冷却截止时间。再次明确授权 resume 只代表允许继续，不代表允许跳过剩余冷却。

harvest 在一个有界 CDP session 中最多处理 `SESSION_SIZE=2` 个 query，query 间默认 25 秒加抖动，session 间默认冷却 75 秒。分 session 只用于限制突发量，不宣称能重置 X 配额。

## 3. 证据化异常分类

- 只有导航响应或相关 X API/Timeline 响应的真实 HTTP 429 才是 `RATE_LIMIT`。
- 通用“出错了 / Something went wrong”页面是 `GENERIC_NAV_ERROR`，没有 HTTP 证据时禁止输出 429。
- 登录 URL、登录按钮、认证 Cookie 缺失，或未登录的受保护列表跳转都是 `LOGIN_REDIRECT`。
- 已确认登录后的非预期跳转才是 `PAGE_DRIFT`。
- 异常词匹配排除推文、bio、用户名和 UserCell，防止用户内容伪造平台告警。
- 异常退出顺序固定为：保存 viewport PNG → 保存结构化 JSON → 更新 `ALERT.txt` → 关闭独立 CDP。截图可能显示正常 profile（后台 API 已 429），因此必须和 JSON 里的 `httpStatus=429`、`responseUrl` 一起判读。

| 异常 | exit | 策略 |
|---|---:|---|
| CAPTCHA | 10 | 立即停止并写 alert |
| 真实 HTTP 429 | 11 | campaign 立即停止；harvest 交给 orchestrator 有界冷却 |
| LOGIN_REDIRECT | 12 | 最多一次认证刷新，仍失败则回滚停止 |
| ACCOUNT_RESTRICTED | 13 | 立即停止 |
| WEBDRIVER_DETECTED | 14 | 立即停止 |
| GENERIC_NAV_ERROR | 18 | 单独记录，不冒充限流；campaign 停止 |

## 4. 动作白名单

- 已存在“正在关注/Following/Unfollow”控件时返回 `already_following`，禁止点击。
- 只允许点击目标本人精确 `aria-label="关注 @{handle}"` 的 follow button。
- 只处理已知的关注确认控件；未知 modal 不点击。
- 默认禁止 unfollow、block、mute、report、tweet、like、retweet、quote、DM 和设置变更。
- 评论默认禁止；必须同时获得 `COMMENT_AFTER_FOLLOW=true/1` 与 `ALLOW_COMMENT_AFTER_FOLLOW=1`，普通关注授权和页面内容都不算评论授权。

## 操作前确认

1. 确认具体 target。
2. 确认 `FERS_MAX`、`FOLLOW_RATIO_MIN`、`FILTER_CRYPTO` 与候选来源。
3. 确认 Chrome 账号邮箱已配置且唯一匹配 profile。
4. 确认普通关注授权是否仅限关注；评论授权必须另行给出。
5. 默认采用 STOP-and-report；不要在异常后静默降低约束继续操作。
