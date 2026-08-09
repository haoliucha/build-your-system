---
name: x-unfollow
description: Use when the user asks about X/Twitter follow hygiene, x-unfollow, 未回关, 回关筛选, 关注清理, 粉丝/关注者变化, or explicitly authorized unfollow actions.
---

# x-unfollow v3：X 关系当前态与安全取关

唯一网络入口是 `run.sh`。默认 `MODE=report` 只刷新 following 并输出未回关报告；只有用户明确授权“取关”时才使用 `MODE=unfollow`。

## 先确定用户要查什么

| 用户目的 | 模式 | 访问范围 |
|---|---|---|
| 查未回关、清理关注 | `MODE=report` | 只扫 `/following` |
| 查谁新增/取消关注我 | `MODE=followers-report` | 只扫 `/followers` |
| 明确需要完整关系并集 | `MODE=relationships-report` | 同一锁内顺序扫两表 |
| 明确授权取关 | `MODE=unfollow` | following、必要的低频粉丝数刷新、取关、一次 post-scan |

不要为了查粉丝变化扫描 following；不要为了查未回关扫描 followers；不要逐个打开主页验证取关或粉丝变化。

```bash
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
  MY_HANDLE=<you> MODE=followers-report bash run.sh
```

## 不可放宽的安全约束

- 所有 X-facing 脚本要求 `run.sh` 颁发的活动 token；同一数据目录仅允许一个运行实例。没有 24 小时冷却，前一实例退出并释放锁后可立即重跑。
- 列表滚动每轮 8–12 秒，每 10 轮暂停至少 60 秒，硬上限 160 轮；启动前必须显示目标列表及单表最坏约 37–48 分钟。
- 页面 URL 必须精确是 `/<handle>/following` 或 `/<handle>/followers`。顶层导航、轮前、轮后和最终均检查；用户点击导致页面漂移时不抢回页面，立即关闭受控上下文、删除 staging、保留 current、写 `ALERT.txt`，退出 15。
- 唯一 handle 数只能单调增长，不使用 `scrollHeight` 重置稳定轮数；连续 8 轮无新增且覆盖率≥95%才稳定停止。低覆盖最多恢复两次；异常数量或低覆盖退出 17。
- “消失/取关”属于负向结论，只能在稳定停止且覆盖率≥99%时输出。
- 验证码、429、登录跳转、账号限制、webdriver 异常立即停止（10–14）。
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

新扫描先写 `.staging/<run-token>/`；校验通过后才原子替换对应 current/latest 文件，失败或中止删除 staging、保留旧 current。following 与 followers 是两张原始表，`relationships` 只是大小写无关的派生并集。

关系行至少包含：`handle`、`name`、`inFollowing`、`inFollowers`、`relationship`、两侧观察时间、`followsMeBadge`、`evidenceConflict`、`nonRecipSince`、`consecutiveDays`。只有一张表时 `complete:false`；两表同一完整扫描 token 时 `coherent:true`。

连续未回关状态压缩在最新关系行。仅相邻自然日都观察为未回关时延续；日期间断会从新观察日重新计时。

## 粉丝变化结论

比较旧 followers current 与新 staging：

- 新出现：`new_follower`
- 消失且当前 following badge 明确为 false：`confirmed_unfollowed`
- 消失但无 following 证据/可能冻结：`unresolved_removed`
- followers 缺失但 following badge 仍为 true：`evidence_conflict`，禁止说对方取关
- 首次刷新：`baseline_created`，只建基线

followers-report 不访问个人主页、不刷新公开粉丝数、不改变任何关注关系。

## 取关规则

默认 `MIN_DAYS=3`（严格大于）和 `FOLLOWER_THRESHOLD=2000`（严格小于才候选）。`MODE=report` 不访问个人主页；`MODE=unfollow` 才会对已过等待期且缺少计数的账号按每次最多 5 个、30–60 秒间隔刷新公开粉丝数。

取关后只追加一次完整 following 扫描，然后用本地大小写无关集合差验证全部目标，不逐主页复查。

## 开发与验证

```bash
node tests/run-tests.cjs
bash -n run.sh
```

修改规范源码后运行仓库同步脚本，确保 Claude 镜像与 Codex 源码逐字一致。详见 [`README.md`](./README.md)。
