# 候选挖掘策略 + yield 估计

候选池的多样性直接决定 campaign 能否凑够 target。本次实战 yield 数据如下,可用作 capacity planning。

## 🚨 硬约束:候选必须**主动表达过互关意愿**

蓝V互关 use case 下,候选**只能**来自 蓝V互关 搜索/评论 — 即此人**亲自发过**互关帖,或**亲自在**互关帖下评论。这是 spec 的硬约束,不可妥协。

不要从其他账号的 followers/following 列表挖候选 — 那些人可能根本没参与过互关 culture。本次实战教训:28 个 follow 里 10 个来自非合规源,其中 1 个是 "**专业推特蓝V代开/刷粉**" 黑产账号(@braggartw1)。

## 合规策略对比表(✅ 用这些)

| # | 策略 | 命令 / URL | 单次 yield(原始 → 蓝V 非币圈 NEW) | 适用阶段 |
|---|---|---|---|---|
| 1 | 主搜索:`蓝V互关` latest | `harvest.cjs search "蓝V互关"` | 100 → 65 → 50 | 启动期 |
| 2 | 搜索变种:`蓝V互粉` | `harvest.cjs search "蓝V互粉"` | 60 → 40 → 15 | 启动期补充 |
| 3 | 搜索变种:`蓝V互fo` | `harvest.cjs search "蓝V互fo"` | 50 → 30 → 10 | 启动期补充 |
| 4 | 高级搜索 OR | `harvest.cjs search "(蓝V互关 OR 蓝V互粉 OR 蓝V互fo) -filter:replies since:YYYY-MM-DD"` | 200 → 162 → 17 | 启动期 |
| 5 | 评论挖掘(top 帖) | `harvest.cjs replies <status URL>` | 30-150 → 20-100 → 5-60 | 中期(主力) |
| 6 | 评论挖掘(中等帖,reply 20-50) | 同上 | 10-25 → 6-18 → 3-10 | 中后期 |
| 7 | 搜索 hot tab 找 top 帖 URL | `harvest.cjs search "蓝V互关" --tab top` | (用于找 #5 的输入,不直接出候选) | 中期 |

## ❌ 禁用策略(蓝V互关 use case 下绝不用)

| 策略 | 工具 | 为什么不行 |
|---|---|---|
| 别人的 `/followers` 挖掘 | `harvest.cjs followers <handle> followers` | followers 不一定参与过互关,违反 spec |
| 别人的 `/following` 挖掘 | `harvest.cjs followers <handle> following` | 同上,且可能挖到对方的 spam 关注 |
| X 推荐侧栏 / "Who to follow" | 任何方式 | 推荐算法选的,与互关 culture 无关 |

`harvest.cjs followers` 工具本身仍保留 — 如果用户**明确**想做"关注某 KOL 的 followers"这种 use case(非 蓝V互关 preset),可用,但需明确告知用户"此候选不保证有互关意愿"。

## 自己的 /following:用作 skip set 不是候选源

`snapshot-following.cjs <my-handle>` 抓自己的 /following 列表,**仅用于预过滤**(把已关注的加入 skip set 避免重复访问),**不是**候选源。本次实战这一步省了 30% 时间。

## yield 折损规律

- **预过滤折损 ~30%**:crypto handle / display name 启发式过滤
- **already_following 折损 ~30%**:如果 my_handle 已有 100+ following,大概率重叠
- **profile 验证折损 ~50%**:followers>1100、following<=followers、bio 含 crypto 等
- **总 pass rate ~14-25%**(看 my_handle 既有网络重叠程度)

**Capacity planning 公式**:`target / 0.18 ≈ 候选总需求`(蓝V互关 use case)
- target=100 → 候选 ~556
- target=50 → 候选 ~278

## 推荐挖掘顺序(本次实战验证)

```
1. harvest.cjs search "蓝V互关"           # 100 候选
2. snapshot-following.cjs MY_HANDLE       # 抓 /following 进 skip
3. ↓ campaign 开始跑,候选 ~50 个
4. harvest.cjs search "蓝V互粉"           # 补 +15
5. harvest.cjs search "蓝V互fo"           # 补 +10
6. harvest.cjs search <OR query>          # 补 +17
7. harvest.cjs replies <top post 1>       # 补 +30(主力补给)
8. harvest.cjs replies <top post 2>       # 补 +20
9. harvest.cjs replies <top post 3>       # 补 +15
... 期间不断挖,campaign 自动 reload queue.json
```

如果搜索 + 评论挖到深处仍不够,**不要** fallback 到 followers/following 列表。改用:
- 换更多搜索变种(`蓝v` 大小写 / `互关必回` / `认证互关`)
- `since:` 限近 24h(找最新发帖人,网络新血)
- `蓝V filter:blue_verified` 全平台 + 时间窗(发现新晋蓝V)

## 高 yield post 识别

挖评论效果好的帖子特征:
- **reply > 100**(大候选池)
- **OP 非币圈**(commenters 多样性高)
- **发帖 < 24h**(commenters 还在线 = profile 数据准)
- **OP follower < 5000**(避开大 KOL 的回粉 spam)

最近 reply 高的 蓝V互关 帖子可通过 `harvest.cjs search "蓝V互关" hot` 或在 search f=top 找。

## "搜索 → 评论"双层结构

数据上,**搜索是宽广基础**(占总候选 70%),**评论是质量补给**(30%)。这两层都满足"候选必须发过互关帖"的硬约束。**不要**追加"网络层"(followers/following 挖) — 这一层违反 spec。

如果搜索 + 评论枯竭,改用更激进的搜索(如降低 followers_max 阈值放宽筛选,或换关键词如 `互关必回`),而不是降低候选源标准。

## 注意

- 每个 harvest 命令是**独立调用**,不会重复 X 浏览(不增加风控压力)
- harvest 跑在你的 MCP 浏览器(原 profile),与 campaign 跑在 profile copy 并行不冲突
- 但**总 X 流量**累计计入账号(harvest 也算"我访问 X"),太凶猛仍可能触发限流。建议 harvest 在 campaign 长休时段做
