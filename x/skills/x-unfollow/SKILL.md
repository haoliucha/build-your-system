---
name: x-unfollow
description: Use when the user asks about X/Twitter follow hygiene, x-unfollow, 未回关, 回关筛选, 关注清理, 粉丝/关注者变化, or explicitly authorized unfollow actions.
---

# x-unfollow v4：X 关系当前态与安全取关

唯一网络入口是当前 `x` 插件内的 `run.sh`。默认 `MODE=report` 只刷新 following 并输出未回关报告；只有用户明确授权“取关”时才使用 `MODE=unfollow`。不要调用、链接或复制 `~/.agents/skills/x-unfollow`；裸 standalone 副本缺少双宿主 manifest，必须在浏览器、锁和 X 请求前以 `LEGACY_STANDALONE_INSTALL` 失败。Codex 规范入口为 `$x:x-unfollow`，Claude Code 由 `/x-unfollow` 或 `/x:x-unfollow` 路由到插件内共享 Skill。

## 先确定用户要查什么

| 用户目的 | 模式 | 访问范围 |
|---|---|---|
| 查未回关、清理关注 | `MODE=report` | 只扫 `/following` |
| 查谁新增/取消关注我 | `MODE=followers-report` | 只扫 `/followers` |
| 明确需要完整关系并集 | `MODE=relationships-report` | 同一锁内顺序扫两表 |
| 明确授权取关 | `MODE=unfollow` | following、必要的低频粉丝数刷新、取关、一次 post-scan |

不要为了查粉丝变化扫描 following；不要为了查未回关扫描 followers；不要逐个打开主页验证取关或粉丝变化。

```bash
SKILL_DIR="/当前 x-unfollow Skill 目录的绝对路径"
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
  MY_HANDLE=<you> MODE=followers-report bash "$SKILL_DIR/run.sh"
```

运行前检查 `~/.config/x-browser/account.json`。若脚本报告 `ACCOUNT_CONFIG_REQUIRED`，先在对话中询问用户要使用的 Chrome 账号邮箱，不要猜测，再保存：

```bash
node "$SKILL_DIR/scripts/configure-account.cjs" set --email=<chrome-account-email>
```

`X_CHROME_ACCOUNT_EMAIL` 可临时覆盖本地配置，`X_BROWSER_CONFIG_PATH` 可覆盖配置路径。邮箱必须在系统 Chrome `Local State.profile.info_cache` 中恰好匹配一个 profile；不要硬编码私人邮箱或 `Profile N`。

浏览器通过系统 Google Chrome 子进程和本机随机端口 CDP 运行，只使用独立 `PROFILE_DIR`（默认 `~/.config/playwright-chrome-profile-campaign`）。系统 Chrome user-data 默认从 `~/Library/Application Support/Google/Chrome` 只读；`X_CHROME_USER_DATA_DIR` 优先，`SOURCE_PROFILE_DIR`、`X_FOLLOW_SOURCE_PROFILE_DIR` 是兼容别名。认证 Cookie 缺失时，在零 X 请求状态下最多自动选择性刷新一次，失败回滚并退出 12。不要手动复制整个 profile，不要删除 `Singleton*`，不要广域终止 Chrome。

受控 Chrome 默认无头运行（未设置或 `XU_HEADLESS=1`）。仅在排查浏览器交互时显式设置 `XU_HEADLESS=0` 进入可见调试；无头失败时不自动回退到可见模式。异常退出后独立 CDP Chrome 已关闭，按 `ALERT.txt` 修复环境后重新运行。

## 不可放宽的安全约束

- 所有 X-facing 脚本要求 `run.sh` 颁发的活动 token；同一数据目录仅允许一个运行实例。没有 24 小时冷却，前一实例退出并释放锁后可立即重跑。
- 列表页只被动监听页面自己发出的 `Followers` / `Following` 响应；绝不主动重放私有 GraphQL。每个真实分页响应后等待 1–3 秒，每 25 个响应暂停 10 秒，单表使用 45 分钟看门狗。
- 页面 URL 必须精确是 `/<handle>/following` 或 `/<handle>/followers`。顶层导航、轮前、轮后和最终均检查；用户点击导致页面漂移时不抢回页面，立即关闭受控上下文、删除 staging、保留 current、写 `ALERT.txt`，退出 15。
- 主路径只接受连续 Bottom cursor 链；无 Bottom cursor，或同 cursor 连续两次无新增，才视为末页。网络响应一旦出现，账号集合只采用响应数据；DOM 只读取主列表列，并仅在响应完全不可见时连续 8 轮稳定到底兜底。
- 已看到 Bottom cursor 后若连续 8 轮无分页响应且 DOM 无进展，只有网络集合覆盖上一完整基线至少 95%，且未超过“基线 + max(10 条, 2%)”时，才能以 `baseline_coverage_stable` 完成；否则必须以 `CURSOR_STALLED_WITH_BOTTOM_CURSOR` 失败并保留旧 current。该分支不得伪称 `cursor_exhausted`。
- 一次完整扫描即可输出相对上一份完整基线的粉丝变化报告，不设置二次确认或人工 review 队列。
- 登录 URL/按钮、认证 Cookie 缺失，或未登录时受保护列表跳到公开主页，统一作为 `LOGIN_REDIRECT`（exit 12）；确认登录后的非预期跳转才是 `PAGE_DRIFT`（exit 15）。
- 只有导航响应或相关 X API/Timeline 响应的真实 HTTP 429 才是 `RATE_LIMIT`（exit 11）；通用错误页是 `GENERIC_NAV_ERROR`（exit 18），不得根据“出错了”文字声称 429。
- 验证码、登录跳转、账号限制、webdriver 异常、真实 429 和通用导航错误立即停止；失败扫描删除 staging 并保留旧 current。
- 取关只认精确目标的 `正在关注/Following/取消关注/Unfollow` 语义控件和匹配确认框；绝不单独信任 `*-unfollow` testid，避免误点“订阅”。
- 默认保护已回关账号。只有用户对精确目标明确授权忽略回关时，才可同时使用 `EXPLICIT_HANDLES` 与 `ALLOW_MUTUAL=1`。
- 永不关注、订阅、发帖、点赞、评论、屏蔽或改设置。

## 当前态数据模型

只保留最新状态，没有逐日快照：

```text
current/
  following.jsonl
  following.meta.json
  followers.jsonl
  followers.meta.json
  relationships.jsonl
  relationships.meta.json
reports/
  latest-non-recip.json
  latest-non-recip.csv
  latest-follower-changes.json
  latest-follower-changes.csv
  latest-relationship-changes.json
  latest-relationship-changes.csv
network-run-state.json
ALERT.txt
```

新扫描先写 `.staging/<run-token>/`；cursor 链或 DOM 稳定校验通过后才原子替换对应 current/latest 文件，失败或中止删除 staging、保留旧 current。只保存标准化 handle/name/关系证据，不保存原始 GraphQL 响应。旧版若出现 `count > userEntriesSeen`，说明网络基线混入 DOM 项；下一次完整扫描以 `baseline_repaired` 重建基线，不输出污染项变化。

关系行至少包含：`handle`、`name`、`inFollowing`、`inFollowers`、`relationship`、两侧观察时间、`followsMeBadge`、`evidenceConflict`、`nonRecipSince`、`consecutiveDays`。只有一张表时 `complete:false`；两表同一完整扫描 token 时 `coherent:true`。

连续未回关状态压缩在最新关系行。仅相邻自然日都观察为未回关时延续；日期间断会从新观察日重新计时。

## 粉丝变化结论

比较旧 followers current 与新 staging：

- 新出现：`new_follower`
- 消失且当前 following badge 明确为 false：`confirmed_unfollowed`
- 消失但无 following 证据/可能冻结：`unresolved_removed`
- 消失但 following badge 仍为 true：`evidence_conflict`，禁止说对方取关
- 首次刷新：`baseline_created`，只建基线
- 检测到旧版 DOM 污染：`baseline_repaired`，重建基线且不输出假变化

`followers-report` 只访问 `/followers`，不访问个人主页、不刷新公开粉丝数、不改变任何关注关系。完整 cursor 链不依赖主页粉丝总数；DOM 仅作低频兜底。

## 取关规则

默认 `MIN_DAYS=3`（严格大于）和 `FOLLOWER_THRESHOLD=2000`（严格小于才候选）。`MODE=report` 不访问个人主页；`MODE=unfollow` 才会对已过等待期且缺少计数的账号按每次最多 5 个、30–60 秒间隔刷新公开粉丝数。

取关后只追加一次完整 following 扫描，然后用本地大小写无关集合差验证全部目标，不逐主页复查。
