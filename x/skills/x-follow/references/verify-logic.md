# 验证函数详解 + 选择器表 + 4 条规则 rationale

## X DOM 选择器表(2026-05 实测)

| 数据 | Selector | 备注 |
|---|---|---|
| User name 整块 | `div[data-testid="UserName"]` | profile 上方,包含 display name + @handle + verified badge |
| Display name + handle | `div[data-testid="UserName"]`.innerText | 第一行 display name,第二行 `@handle` |
| 蓝V badge | `div[data-testid="UserName"] svg[aria-label="认证账号"]` | **必须 scope 到 UserName**;否则评论页会匹配到 OP 的 badge |
| 金V / 机构 badge | `... svg[aria-label="Verified organization"]`,`... svg[aria-label="Government account"]` | 用来排除官号 |
| Bio | `div[data-testid="UserDescription"]` | 可能不存在(用户没填) |
| Followers 链接 | `a[href$="/followers"]` 或 `/verified_followers` | innerText 含数字 + "关注者" |
| Following 链接 | `a[href$="/following"]` | innerText 含数字 + "正在关注" |
| Follow 按钮(profile 主人) | `button[data-testid$="-follow"][aria-label="关注 @{handle}"]` | testid 前缀是数字 user_id,所以用 aria-label 锁定 |
| Unfollow / 已关注 按钮 | `button[data-testid$="-unfollow"][aria-label*="@{handle}"]` | aria-label 是 `正在关注 @{handle}` |
| Confirm dialog(私密账号) | `div[data-testid="confirmationSheetConfirm"]` | follow 私密账号会弹这个,需自动点 |
| 已经 suspended/lock | `div[data-testid="empty_state_header_text"]` | 账号被封 / 不存在 |
| Captcha iframe | `iframe[src*="captcha"]` | 高优 STOP signal |

## 重要陷阱

### 1. Blue badge 必须 scope 到 `User-Name`

**错误**:
```js
const blue = !!art.querySelector('svg[aria-label="认证账号"]');
```

在评论页,`article[role="article"]` 同时包含 OP 帖子和 reply 帖子,每个都有自己的 user-name 区域。直接在 article 范围找 badge,会把 OP 的 badge 误算给 reply 用户。

**正确**:
```js
const nameEl = art.querySelector('div[data-testid="User-Name"]');
const blue = !!(nameEl && nameEl.querySelector('svg[aria-label="认证账号"]'));
```

注意 `User-Name`(有连字符)是 article 里 reply 用户区域;**profile 页**用的是 `UserName`(无连字符)。两个 testid 不同!

### 2. Follow button 必须用精确 aria-label

X 的 profile 页除了主用户的 follow 按钮,**右侧还有"推荐关注" sidebar**,每个推荐用户也有自己的 follow 按钮。

**错误**(会随机点中 sidebar):
```js
const fB = document.querySelector('button[data-testid$="-follow"]');
fB.click();
```

**正确**(精确锁定 profile 主人):
```js
const H = 'targetHandle';
const fB = document.querySelector(`button[data-testid$="-follow"][aria-label="关注 @${H}"]`);
```

testid 用 `$=` 后缀匹配,因为前缀是数字 user_id。aria-label 必须**完全匹配** `关注 @handle` 字符串。

### 3. 等待 DOM 渲染齐(不是 UserName 出现就行)

`page.goto` 完成 ≠ 页面交互可用。X 是 SPA,UserName 可能很快出现,但 follow 按钮 + badge 是异步加载。

**等待序列**(双段):
```js
// 段 1:等 UserName 出现
for (let i = 0; i < 12; i++) {
  if (document.querySelector('div[data-testid="UserName"]')) break;
  await sleep(500);
}
// 段 2:等 button OR badge 出现
for (let i = 0; i < 10; i++) {
  const hasBtn = document.querySelector('button[data-testid$="-follow"], button[data-testid$="-unfollow"]');
  const hasBadge = document.querySelector('div[data-testid="UserName"] svg[aria-label="认证账号"]');
  if (hasBtn || hasBadge) break;
  await sleep(500);
}
```

总等待 max 11s。如果还没出现,基本是网络问题或被 X 拒绝服务。

### 4. Click 后 verify 必须 3-retry + fallback

Click 触发后,X 服务端处理 + 前端 DOM update 是异步的。一次检查可能漏报。

```js
fB.scrollIntoView({block:'center'});
await sleep(300 + Math.random() * 400);  // 拟人 hover
fB.click();
await sleep(2500);                        // 初始等待

const uX = document.querySelector(`button[data-testid$="-unfollow"][aria-label*="@${H}"]`);
if (uX) {
  result.action = 'followed';
} else {
  // 私密账号会弹 confirm
  const cf = document.querySelector('div[data-testid="confirmationSheetConfirm"]');
  if (cf) {
    cf.click();
    await sleep(2000);
    const uY = document.querySelector(`button[data-testid$="-unfollow"][aria-label*="@${H}"]`);
    result.action = uY ? 'followed_via_confirm' : 'click_initiated_no_verify';
  } else {
    // Click 触发了但 verify 没看到 unfollow btn — X DOM 滞后,假设成功
    result.action = 'followed_assumed';
  }
}
```

`followed_assumed` 在本次实战触发了 4 次,**全部经 MCP 二次验证确认实际已 follow**。X 服务端先行,前端 DOM 慢一拍。

## 4 条硬规则的设计 rationale

### Rule 1: `verified_required = true`(默认)

- 蓝V = X premium 用户,通常对账号有更高维护意愿
- 蓝V 之间互关 = X 推广的"high quality 互动"
- 关闭(`false`)适合"广撒网"场景

### Rule 2: `following_gt_followers = true`(默认)

- 这是"互关意向"的核心信号
- 关注多 > 粉丝多 = 此人主动出击型,follow-back 概率高
- 关闭适合关注大 KOL(单向)

### Rule 3: `followers_max = 1100`(默认,容差 10%)

- 1000 是"小号正在成长"的心理门槛
- 1100 容差避免漏掉刚过 1000 的边缘账号(本次 user 允许)
- 设小一点(如 500)拿更纯净的小号;设大(99999)放开

### Rule 4: `bio_blacklist`(crypto 默认)

- 为了过滤 @haoliucha 不感兴趣的币圈账号
- 双层匹配:handle 用 substring,bio 用词边界 `\bword\b`
- 仅词边界会漏 `CryptoDaddyCoco`(handle 有 Crypto,bio 空)— 实战教训

```js
const enRegex = new RegExp('\\b(' + enTokens.join('|') + ')\\b', 'i');
const cm = bio.match(enRegex)?.[0] 
       || zhTokens.find(k => bio.includes(k))                       // bio 词边界
       || enTokens.find(k => H.toLowerCase().includes(k));          // handle substring
```

## 完整 verify 函数 cheatsheet

```js
async function verifyAndFollow() {
  const H = window.location.pathname.slice(1).split('/')[0];
  const s = ms => new Promise(r => setTimeout(r, ms));
  
  // 1. 等齐 DOM
  for (let i = 0; i < 12; i++) {
    if (document.querySelector('div[data-testid="UserName"]')) break;
    await s(500);
  }
  for (let i = 0; i < 10; i++) {
    const hasBtn = document.querySelector('button[data-testid$="-follow"], button[data-testid$="-unfollow"]');
    const hasBadge = document.querySelector('div[data-testid="UserName"] svg[aria-label="认证账号"]');
    if (hasBtn || hasBadge) break;
    await s(500);
  }
  
  // 2. 抽取
  const UN = document.querySelector('div[data-testid="UserName"]');
  const UD = document.querySelector('div[data-testid="UserDescription"]');
  if (!UN) return { error: 'no_username' };
  const blue = !!UN.querySelector('svg[aria-label="认证账号"]');
  const gold = !!UN.querySelector('svg[aria-label="Verified organization"], svg[aria-label="Government account"]');
  const bio = UD ? UD.innerText : '';
  
  // 3. 解析数字(中文 "万" 等)
  // ...(parseCount 函数,见 campaign.cjs)
  
  // 4. 找按钮
  const fB = document.querySelector(`button[data-testid$="-follow"][aria-label="关注 @${H}"]`);
  const uB = document.querySelector(`button[data-testid$="-unfollow"][aria-label*="@${H}"]`);
  
  // 5. 决策
  if (!blue) return 'reject:not_blue';
  if (gold) return 'reject:gold_org';
  if (uB) return 'reject:already_following';        // ❗严禁 click(防误 unfollow)
  if (!fB) return 'reject:no_follow_btn';
  if (fN > FERS_MAX) return 'reject:fers_too_many';
  if (fgN <= fN) return 'reject:fing_not_gt_fers';
  if (matchCrypto(bio, H)) return 'reject:crypto_bio';
  
  // 6. 行动 + verify
  // (见 click 后 verify 段)
}
```

完整源码:`scripts/campaign.cjs` 里 `VERIFY_JS` 常量。
