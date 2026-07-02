---
name: x-unfollow
description: This skill should be used when the user wants to do X (Twitter) follow hygiene for their own account — snapshot who they follow that does not follow back, track how many consecutive days each has stayed non-reciprocal, filter by follower count, and (only on explicit request) unfollow eligible accounts with verification. Triggers on phrases like "x-unfollow", "X 取关", "未回关", "回关筛选", "关注清理", "粉丝数阈值", "连续未关注天数", "clean up who I follow".
version: 1.0.0
---

# x-unfollow:X 关注卫生(取关未回关的小号)

姊妹 skill 是 [`x-follow`](../x-follow/SKILL.md)(批量关注);本 skill 负责反向的「关注卫生」:找出**我关注了、但对方没回关**的账号,跨天累计「连续未回关天数」,按粉丝数阈值筛选,并在用户**明确要求**时取关 + 验证。

> **架构与开发文档见 [`README.md`](./README.md)**(pipeline 图、模块依赖、异常状态机、state 目录布局、测试)。
> **推荐入口 = 一条龙 `run.sh`**。默认 `MODE=report` 只出名单**不取关**;取关要显式 `MODE=unfollow`。
>
> ```bash
> NODE_PATH=~/.config/playwright-mcp-server/node_modules \
>   MY_HANDLE=<you> MODE=report bash run.sh        # 只快照 + 分类 + 候选名单
> # 用户明确说"取关"后,再:
> NODE_PATH=~/.config/playwright-mcp-server/node_modules \
>   MY_HANDLE=<you> MODE=unfollow LIMIT=20 bash run.sh
> ```

## 核心规则(最重要)

- **只有用户明确要"取关 / unfollow"时才执行删除。** 用户说「筛选 / 统计 / 报告 / 看看 / 谁没回关」→ 跑到候选名单**就停**(`MODE=report`),报告后等指令。
- **取关不可一键回滚**(脚本不会替用户重新关注)。执行前与用户对齐数量、阈值、等待天数。
- **不读 Chrome cookie / localStorage / 密码 / session 文件**;只用可见的 X UI、已登录的 profile 副本、公开主页、本地日志。

## 何时触发

- 用户想清理自己的关注列表:`X 取关`、`未回关`、`回关筛选`、`关注清理`、`谁没回关我`
- 用户语义示例:"看看谁没回关我"、"把关注了超过 3 天还没回关、粉丝<2000 的取关"、"先出个未回关名单"

## 判定规则(可参数化)

| 规则 | 默认 | 含义 |
|---|---|---|
| `MIN_DAYS` | `3` | 自然天**严格大于**此值才算「超过等待期」(elapsed > MIN_DAYS) |
| `FOLLOWER_THRESHOLD` | `2000` | 刷新后的公开粉丝数 **< 阈值**才可取关(≥ 阈值保留,大号不取) |
| 回关豁免 | 总是 | 取关前若对方已「关注了你 / Follows you」→ 跳过,记 `now_follows_you` |

「连续未回关天数」需要**跨天积累快照**:全新数据目录首跑,所有账号都是 `KEEP_WAITING_GT3`,要连续几天跑 snapshot 才会有账号到「可取关」。

## reason 码 → decision

| reason_code | decision | 含义 |
|---|---|---|
| `EXCLUDE_INVALID_HANDLE` | do_not_unfollow | handle 格式无效 |
| `EXCLUDE_NAV_OR_MISCRAPE` | do_not_unfollow | 页面导航/误抓(home/search/i…),非账号 |
| `EXCLUDE_ALREADY_UNFOLLOWED` | do_not_unfollow | 之前已确认取关,不重复 |
| `KEEP_WAITING_GT3` | keep_waiting | 还在等待期(elapsed ≤ MIN_DAYS),报告下次评估日期 |
| `ELIGIBLE_FOR_FOLLOWER_REFRESH` | refresh_profile_count | 过了等待期,但还没刷新公开粉丝数 |
| `EXCLUDE_FOLLOWERS_GE_THRESHOLD` | do_not_unfollow | 刷新后粉丝数 ≥ 阈值,不取 |
| `ELIGIBLE_FOR_UNFOLLOW` | **candidate_unfollow** | 过等待期且粉丝数 < 阈值,**可取关** |

**只有 `candidate_unfollow` 会被 `unfollow.cjs` 执行。**

## 工作流(run.sh 编排)

1. **Setup**:profile 副本检查 + 清锁 + `smoke-test`(登录态/webdriver/`/following` 渲染,RED 拒启)。
2. **Snapshot**:`snapshot.cjs` 抓 `MY_HANDLE` 的 `/following`,记录所有「未回关」账号 → `snapshots/YYYY-MM-DD.jsonl`(gotoRobust 容错 429/延迟;异常即 STOP)。
3. **Classify**:`classify.cjs` 读跨天快照系列,算 firstSeen / elapsed,套 reason 码 → `reports/non-recip-reasons-YYYY-MM-DD.{json,csv}`。
4. **Refresh**:对过了等待期的(`ELIGIBLE_FOR_FOLLOWER_REFRESH`)用 `profile-counts.cjs --from-classify` 拉公开粉丝数,再 classify 一次。
5. **Report**(`MODE=report`,默认):打印候选名单,**停**。
   **Unfollow**(`MODE=unfollow`,需用户明确授权):`unfollow.cjs` 逐个取关 → `verify-unfollow.cjs` 复核(最多 2 轮)。

手动分步(调试用):

```bash
MY_HANDLE=you node scripts/snapshot.cjs
node scripts/classify.cjs --min-days=3 --follower-threshold=2000
node scripts/profile-counts.cjs --from-classify
node scripts/classify.cjs --min-days=3 --follower-threshold=2000     # 刷新后重算
# 仅在用户明确要取关时:
DRY_RUN=1 node scripts/unfollow.cjs --limit=2   # 先 dry-run 验证选择器
node scripts/unfollow.cjs --limit=20
node scripts/verify-unfollow.cjs
```

## 开工前 user 确认 checklist

1. ✅ 这次是要**出报告**还是**真取关**?(默认只报告)
2. ✅ `MY_HANDLE` 已登录到 profile 副本
3. ✅ 取关阈值:`MIN_DAYS`(默认 3)、`FOLLOWER_THRESHOLD`(默认 2000)
4. ✅ 用户清楚取关不可一键回滚
5. ✅ 异常处理偏好:`STOP-and-ask`(默认)

## 风控红线(绝不破)

- **撞验证码 / 限流 / 登录跳转 / 账号受限** → 立即 STOP,写 `ALERT.txt`,退出码 10-14,不继续操作账号。
- **click 严格白名单**:取关只点 `aria-label` 中 `@` token **精确等于**目标 handle 的 `data-testid$="-unfollow"` 按钮;不匹配 → `safety_abort_btn_mismatch`,不点。确认弹窗用 `confirmationSheetConfirm`。
- **对方已回关 → 跳过**,绝不取关回关了你的人。
- **永不**:关注 / 发推 / 点赞 / 评论 / block / 改 settings(代码 hard-coded)。
- 取关后**独立验证**目标已无对应 `-unfollow` 按钮(`verify-unfollow.cjs`)。

## 数据位置(不进仓库)

运行态数据写在独立 state 目录(默认 `~/.config/x-unfollow-data/`,可用 `XU_DATA_DIR` 覆盖):

```
$XU_DATA_DIR/
  snapshots/YYYY-MM-DD.jsonl                 # 每日未回关快照(streak 来源)
  reports/non-recip-reasons-YYYY-MM-DD.json  # 分类 + reason 表
  reports/non-recip-reasons-YYYY-MM-DD.csv
  reports/profile-refresh-YYYY-MM-DD.json    # 公开粉丝数刷新
  reports/unfollow-YYYY-MM-DD.json           # 取关动作日志
  reports/verify-unfollow-YYYY-MM-DD.json    # 取关验证
  ALERT.txt                                  # 异常时写
```

## 脚本(架构详见 `README.md`)

- `run.sh` — 一条龙编排(report / unfollow 双模式)
- `scripts/snapshot.cjs` — 扫 /following 全量 UserCell → 每日快照(真实 isFollowingMe,徽章走 userFollowIndicator testid + everTrue 合并,覆盖率对照 header;gotoRobust + 异常自停)
- `scripts/classify.cjs` — 快照系列 → elapsed/reason 码 → 报告(json+csv;互关行跳过)
- `scripts/clean-snapshots.cjs` — 回溯清洗:按权威粉丝名单移除误报行(先备份 snapshots-bad/)
- `scripts/profile-counts.cjs` — 公开主页 JSON-LD 刷新粉丝数(纯 fetch)
- `scripts/unfollow.cjs` — 硬化取关执行(精确选择器白名单 + 确认 + 节奏 + 异常自停)
- `scripts/verify-unfollow.cjs` — 复核目标已不再被关注
- `scripts/smoke-test.cjs` — 启动前体检
- `scripts/lib/` — 共享逻辑:`hygiene`(纯判定/streak/日期)、`nav-helper`(gotoRobust)、`anomaly`、`filters`
- `tests/run-tests.cjs` — 零依赖单测/集成测试(`node tests/run-tests.cjs`)
