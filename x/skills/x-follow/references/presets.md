# 默认 preset 和自定义 preset 示例

## 默认 preset:蓝V互关

适用场景:你是 X 蓝V 创作者,想找一批同样是蓝V 的、规模小、有互关意向的、非币圈账号一起涨粉。

```yaml
verified_required: true
following_gt_followers: true
followers_max: 1100
bio_blacklist:
  # 英文 crypto 词(词边界匹配)
  - crypto, web3, btc, eth, sol, defi, nft, blockchain, binance, okx, bybit, coinbase
  - airdrop, ordinal, memecoin, wallet, staking, gamefi, layer2, tokenomic
  - bitcoin, ethereum, solana, sui, aptos, arbitrum, optimism
  - mining, hashrate, ico, ido, launchpad, presale, hyperliquid, perp
  - trader, quant, onchain, altcoin, shitcoin, pumpfun
  # 中文 crypto 词(substring 匹配)
  - 币圈, 币安, 合约, 空投, 铭文, 打新, 钱包
  - 量化, 操盘, 建仓, 加仓, 止盈, 撸毛, 羊毛
  - 空投党, 矿工, 矿池, 去中心化, 链上, 加密
search_queries: ["蓝V互关", "蓝V互粉", "蓝V互fo"]
my_handle: ""  # 强烈建议填,用于预过滤已关注
```

调用:
```
/x-follow target=100
```

## 预置变体

### 1. 关注摄影师(非蓝V 也行)

```yaml
verified_required: false
bio_whitelist: [摄影, photographer, photography, 摄影师, 拍照, 风光, 人像]
search_queries: ["摄影 互关", "摄影师 互关", "摄影社区"]
followers_max: 3000
```

```
/x-follow target=30 verified_required=false bio_whitelist=摄影,photographer search_queries=摄影 互关
```

### 2. 关注独立开发者 / Indie hacker

```yaml
verified_required: false
bio_whitelist: [indie, solo, vibe coding, build in public, 独立开发, 一人公司, indiehacker, 副业]
search_queries: ["独立开发 互关", "indie 互关", "solopreneur"]
followers_max: 5000
following_gt_followers: false  # 这类账号常单向
```

### 3. 关注出海 / 跨境

```yaml
verified_required: false
bio_whitelist: [出海, 跨境, 海外, overseas, expat, 数字游民]
search_queries: ["出海 互关", "跨境 互关"]
followers_max: 2000
```

### 4. 关注 AI 从业者(过滤 AI + crypto 重叠)

```yaml
verified_required: true
bio_whitelist: [AI, 人工智能, GPT, Claude, agent, LLM, 机器学习]
bio_blacklist: [crypto, web3, 币圈]  # 排除 AI+crypto 重叠
search_queries: ["AI 互关", "AGI 互关"]
followers_max: 5000
```

### 5. ULTRA-SAFE 新号 mode

```yaml
target_count: 10           # 一次少点
follow_wait_min_ms: 60000  # 间隔 60-120s
follow_wait_max_ms: 120000
long_break_every: 5        # 每 5 follow 长休
long_break_ms: 300000      # 5 min
max_follows_per_hour: 15   # 硬限
quiet_hours: [2, 7]        # 凌晨暂停
```

```
/x-follow target=10 follow_wait_min_ms=60000 follow_wait_max_ms=120000 long_break_every=5 long_break_ms=300000 max_follows_per_hour=15 quiet_hours=2,7
```

### 6. 高价值大号(反向,关注 KOL)

```yaml
verified_required: true
followers_max: 99999             # 不限粉丝数
following_gt_followers: false    # KOL 通常 followers 远大于 following
bio_blacklist: []                # 不过滤
search_queries: ["蓝V"]
target_count: 50
```

### 7. 关注 OnlyFans / NSFW(谨慎)

⚠️ 用户需自己判断合规性。代码不做内容审核。

```yaml
verified_required: false
bio_whitelist: [hot, tempting, 18+, NSFW, OF, OnlyFans]
followers_max: 50000
```

## 参数组合矩阵

| use case | verified | fers_max | fing>fers | bio_blacklist | bio_whitelist |
|---|---|---|---|---|---|
| 蓝V互关 (默认) | ✅ true | 1100 | ✅ | crypto list | - |
| 摄影师 | ❌ false | 3000 | ✅ | - | 摄影 |
| Indie dev | ❌ false | 5000 | ❌ | - | indie/solo |
| 出海 | ❌ false | 2000 | ✅ | - | 出海/跨境 |
| AI | ✅ true | 5000 | ❌ | crypto | AI |
| KOL | ✅ true | 99999 | ❌ | - | - |
| 新号试水 | ✅ true | 1000 | ✅ | crypto | - |

## 自定义新 preset 的步骤

1. 复制最接近的预置变体
2. 替换 search_queries(决定候选池大小)
3. 调整 followers_max(决定候选纯度)
4. 决定 verified_required(决定候选稀有度)
5. bio_whitelist / blacklist 微调
6. 用 `target=5` 先试水 5 个,看 pass rate 和 follow 结果
7. 满意后放量到目标 target_count

## bio_blacklist / whitelist 匹配语义

- **bio_blacklist**:bio 含**任一**词 → reject
- **bio_whitelist**:bio 必须含**至少一**词(如果非空)→ pass
- 都填:先 blacklist 后 whitelist(blacklist 优先)
- 都空:不做 bio 过滤

匹配规则:
- 中文词:`substring` 匹配(`"摄影" in bio.text`)
- 英文词:`\b(word|word2|...)\b` 词边界 + case insensitive
- handle 也参与 blacklist substring 匹配(防 `CryptoDaddyCoco` 漏过滤)
