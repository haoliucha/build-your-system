# 候选挖掘的 9 种策略 + yield 估计

候选池的多样性直接决定 campaign 能否凑够 target。本次实战 yield 数据如下,可用作 capacity planning。

## 策略对比表

| # | 策略 | 命令 / URL | 单次 yield(原始 → 蓝V 非币圈 NEW) | 适用阶段 |
|---|---|---|---|---|
| 1 | 主搜索:`蓝V互关` latest | `harvest-search.cjs "蓝V互关"` | 100 → 65 → 50 | 启动期 |
| 2 | 搜索变种:`蓝V互粉` | `harvest-search.cjs "蓝V互粉"` | 60 → 40 → 15 | 启动期补充 |
| 3 | 搜索变种:`蓝V互fo` | `harvest-search.cjs "蓝V互fo"` | 50 → 30 → 10 | 启动期补充 |
| 4 | 高级搜索 OR:`(蓝V互关 OR 蓝V互粉 OR 蓝V互fo) -filter:replies` | `harvest-search.cjs "..."` | 200 → 162 → 17 | 启动期 |
| 5 | `蓝V filter:blue_verified` 全平台 | `harvest-search.cjs "..."` | 106 → 105 → 20 | 中期 |
| 6 | 评论挖掘(top 帖,reply > 100) | `harvest-replies.cjs <status URL>` | 30-70 → 18-45 → 5-15 | 中期 |
| 7 | 评论挖掘(中等帖,reply 20-50) | 同上 | 10-25 → 6-18 → 3-10 | 中后期 |
| 8 | 小账号 followers 挖 | `harvest-followers.cjs <handle> followers` | 30-50 → 25-40 → 5-30 | 后期补给 |
| 9 | 小账号 following 挖 | `harvest-followers.cjs <handle> following` | 50-200 → 40-150 → 10-50 | 后期补给 |

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
1. harvest-search.cjs "蓝V互关"           # 100 候选
2. snapshot-following.cjs MY_HANDLE       # 抓 /following 进 skip
3. ↓ campaign 开始跑,候选 ~50 个
4. harvest-search.cjs "蓝V互粉"           # 补 +15
5. harvest-search.cjs "蓝V互fo"           # 补 +10
6. harvest-search.cjs <OR query>          # 补 +17
7. harvest-replies.cjs <top post 1>       # 补 +30
8. harvest-replies.cjs <top post 2>       # 补 +20
... 期间不断挖,campaign 自动 reload queue.json
9. harvest-followers.cjs <已 follow 小号> # 后期补给
```

## 高 yield post 识别

挖评论效果好的帖子特征:
- **reply > 100**(大候选池)
- **OP 非币圈**(commenters 多样性高)
- **发帖 < 24h**(commenters 还在线 = profile 数据准)
- **OP follower < 5000**(避开大 KOL 的回粉 spam)

最近 reply 高的 蓝V互关 帖子可通过 `harvest-search.cjs "蓝V互关" hot` 或在 search f=top 找。

## "搜索 →  评论 → 网络"金字塔

数据上,**搜索是宽广基础**(占总候选 60%),**评论是质量补给**(30%),**网络是边际优化**(10%)。但小号网络挖往往出最纯净的非币圈候选,值得后期投入。

## 注意

- 每个 harvest 命令是**独立调用**,不会重复 X 浏览(不增加风控压力)
- harvest 跑在你的 MCP 浏览器(原 profile),与 campaign 跑在 profile copy 并行不冲突
- 但**总 X 流量**累计计入账号(harvest 也算"我访问 X"),太凶猛仍可能触发限流。建议 harvest 在 campaign 长休时段做
