# Pacing & Anti-Detection 完整方案(4 层)

X 平台的反 bot 机制包含三个维度:**浏览器指纹**(navigator.webdriver / chrome 版本 / WebGL / canvas)、**行为节奏**(单位时间 action 数 / 间隔规律性)、**会话异常**(短时多设备 / 异常地理 / 模板化 click 坐标)。本方案在每一层都给出对策。

## 第 1 层:浏览器指纹(代码硬保障)

### 启动参数

```js
const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
  channel: 'chrome',                       // ✅ 真 Chrome 而非 Chromium
  headless: false,                         // ✅ 必须可见(headless 的 WebGL/canvas 指纹会被 X 识别)
  viewport: { width: 1280, height: 820 },  // ✅ 自然尺寸,避开 1920x1080/800x600 等机器人常用值
  ignoreDefaultArgs: ['--enable-automation'],          // ✅ 关键 1:去掉 automation flag
  args: ['--disable-blink-features=AutomationControlled'], // ✅ 关键 2:让 navigator.webdriver=false
});
```

### Smoke test 强制门控

```js
const sig = await page.evaluate(() => ({
  webdriver: navigator.webdriver,                  // 必须 false
  hasChrome: !!window.chrome,                      // 必须 true
  hasPlugins: navigator.plugins.length,            // 必须 > 0
  hwConcurrency: navigator.hardwareConcurrency,    // 必须 > 0 且 < 32
  languages: navigator.languages,                  // 必须有 zh/en
  userAgent: navigator.userAgent,                  // 必须含 Chrome/ 而非 HeadlessChrome
}));

if (sig.webdriver === true) FAIL('webdriver=true,启动参数失效');
if (!sig.hasChrome) FAIL('hasChrome=false,浏览器异常');
if (sig.hasPlugins === 0) FAIL('plugins=0,Chrome 异常');
if (sig.hwConcurrency < 1 || sig.hwConcurrency > 32) FAIL('hwc out of range');
if (!sig.languages.some(l => /^(en|zh)/.test(l))) FAIL('lang 异常');
if (/HeadlessChrome/.test(sig.userAgent)) FAIL('UA 暴露 Headless');
```

RED 的任何一项 → 拒绝启动 campaign。

### Profile 复用 vs 新建

**永远复用**用户已登录 + 浏览过的 profile。不要让脚本自己 login。

复用步骤:
1. `cp -R "$ORIG" "$ORIG-campaign"` (复制,保留 cookies/history/localStorage)
2. `rm -f "$ORIG-campaign"/{SingletonLock,SingletonCookie,SingletonSocket}` (必须,否则 Chrome 拒启)
3. 启动时指定 `--user-data-dir=$ORIG-campaign`
4. 用完 `rm -rf "$ORIG-campaign"`(原 profile 不动)

这样 X 服务端看到的是"我熟悉的浏览器(cookies match) + 自然 fingerprint",过审。

## 第 2 层:行为节奏(参数 + 随机化)

### 默认值(本次实战 100/3h 验证有效)

```yaml
follow_wait_min_ms: 25000      # 单 follow 之间最少 25s
follow_wait_max_ms: 55000      # 最多 55s,实际值在区间内均匀随机
reject_wait_min_ms: 5000       # reject(无 follow 动作)间隔更短
reject_wait_max_ms: 12000
long_break_every: 12           # 每 12 个 follow 强制长休
long_break_ms: 180000          # 3 min
click_pre_delay_min_ms: 300    # click 前 scrollIntoView + 300-700ms 模拟人犹豫
click_pre_delay_max_ms: 700
post_click_settle_ms: 2500     # click 后等 X 服务端处理 + DOM 渲染
```

### 节奏不变量

1. **单 follow 间隔永远随机化**。固定间隔是 bot 最强信号
2. **Long break 之后暖机**:前 5 个 follow 用 40-90s 间隔(避免"歇完立刻爆冲")
3. **Click 前必 hover**:`scrollIntoView({block:'center'})` + 300-700ms sleep
4. **不要追求速度**。25-55s/follow 是 X 容忍区间的中位

### ULTRA-SAFE 可选附加(默认关)

```yaml
max_follows_per_hour: 30     # 硬限,默认 0 不开
quiet_hours: [2, 7]          # 凌晨 2-7 点暂停,默认空
```

### X follow 配额参考(社区经验,非官方)

| 账号类型 | 24h 上限 | 1h 安全区 | 备注 |
|---|---|---|---|
| 老号(>180天 + 真实使用) | 400 | 30-60 | 本次实战 @haoliucha 这一档 |
| 中等号 | 250 | 20-30 | |
| 新号(<30天) | 150 | 10-15 | 强烈建议 quiet_hours 开启 |

本次实战:`100 follow / 3h ≈ 33/h`,**正好踩在最安全区间**。

## 第 3 层:异常感知(主动检测+短路退出)

详见 `scripts/lib/anomaly.cjs`。每个 follow **后**都跑一次。

### 检测信号

```js
async function detectAnomaly(page) {
  return await page.evaluate(() => {
    // a) Captcha / human-verification 模态
    const captcha = document.querySelector('iframe[src*="captcha"], div[data-testid*="captcha"], div[id*="recaptcha"]');
    if (captcha) return { type: 'CAPTCHA' };
    
    // b) Rate limit 文本
    const body = document.body.innerText.slice(0, 2000).toLowerCase();
    const rlPatterns = ['rate limit', '操作太频繁', 'try again later', 'temporary restriction', 'limit reached', '你目前无法关注'];
    for (const p of rlPatterns) if (body.includes(p.toLowerCase())) return { type: 'RATE_LIMIT', text: p };
    
    // c) 跳到登录页
    if (window.location.pathname.includes('/login') || window.location.pathname.includes('/i/flow')) {
      return { type: 'LOGIN_REDIRECT', text: window.location.pathname };
    }
    
    // d) Account suspended / locked
    if (body.includes('account has been locked') || body.includes('账号被锁定') 
        || body.includes('account suspended') || body.includes('账号已被冻结')) {
      return { type: 'ACCOUNT_RESTRICTED' };
    }
    
    // e) webdriver 突然变 true(被反向注入)
    if (navigator.webdriver === true) return { type: 'WEBDRIVER_DETECTED' };
    
    return null;
  });
}
```

### 响应策略

| 异常 | 立即响应 | exit code | 后续 |
|---|---|---|---|
| `CAPTCHA` | 立即 exit + 写 ALERT.txt + screenshot | 10 | LLM 通知用户人工处理 |
| `RATE_LIMIT` | 暂停 30 min,自动重试一次。若再次 RATE_LIMIT 则 exit | 11 | LLM 报告 + 询问减半 pace |
| `LOGIN_REDIRECT` | 立即 exit + ALERT | 12 | 用户需重新登录 profile |
| `ACCOUNT_RESTRICTED` | 立即 exit + ALERT | 13 | 严重,可能账号已被限制 |
| `WEBDRIVER_DETECTED` | 立即 exit | 14 | 启动参数有问题 |
| 5+ 连续 eval error | 暂停 5 min + exit | 15 | 浏览器不稳定 |
| 单次 follow_failed | 跳过 + retry budget 1 次 | (continue) | 防漏判 |

ALERT.txt 包含:时间戳、异常类型、相关 handle、当前 URL、最近 5 个操作、profile path。LLM/用户能立即定位。

## 第 4 层:操作不可逆性的保护

### Hard-coded 不做清单

代码层硬限制,不能通过参数覆盖:

```js
const FORBIDDEN_ACTIONS = [
  'unfollow',           // 即使在 cleanup 也不
  'block', 'mute', 'report',
  'tweet', 'reply', 'like', 'retweet', 'quote',
  'update_profile', 'update_settings',
  'message', 'dm',
];
// click 函数对每个目标做 aria-label 检查,只允许 "关注 @{handle}"
```

### Click 前严格门控

```js
// 已 follow → 立即返回,绝不点击(防 click 触发 unfollow)
if (unfollow_btn_exists) return 'reject:already_following';

// 找 follow btn:精确 aria-label 匹配
const fB = document.querySelector(
  `button[data-testid$="-follow"][aria-label="关注 @${H}"]`
);
if (!fB) return 'reject:no_follow_btn';

// 永远只 click 这一个目标,绝不模糊匹配
fB.click();
```

### Confirm dialog 处理

只识别**已知**的 confirm dialog:
- `div[data-testid="confirmationSheetConfirm"]` — 私密账号 follow 确认(自动点 OK)

任何其他 modal(role="dialog" 但 testid 不在白名单)→ skip + log + 不点。

### 启动时声明 + 验证

campaign.cjs 启动时打印 SAFETY MANIFEST 到 stderr:
```
SAFETY MANIFEST:
- Will only click follow buttons matching 'aria-label="关注 @{handle}"'
- Will NEVER click unfollow / block / report / like / tweet / dm
- Will exit on any anomaly without retry beyond budget
- Will preserve original profile, work on copy only
```

供用户/审计回溯。

## 操作前 user 确认门(skill 强制)

skill 启动 campaign **之前**必须跟用户对齐 5 项:

1. ✅ 确认 target_count(具体数字)
2. ✅ 确认 followers_max / 容差
3. ✅ 确认 bio_blacklist 覆盖默认?
4. ✅ 确认 profile_dir 已登录正确账号(查看 /home 显示用户名)
5. ✅ 确认遇异常时的处理偏好:`STOP-and-ask`(默认) / `auto-reduce-pace` / `exit`

跑动中,任何异常**不静默处理**,必须 ALERT.txt + 终止运行让 LLM 立即通知用户。

## Smoke test 必跑步骤

`node scripts/smoke-test.cjs`,6 项检查,全 GREEN 才能 campaign:

1. ✅ 启动 chromium 拿到 navigator 各项指纹
2. ✅ goto x.com/home 确认登录态(URL 非 /login + handle 匹配预期)
3. ✅ 抓自己的 /following 数(snapshot 一次,用于后续 pre-filter)
4. ✅ 测试可访问 /search(确认基础功能正常)
5. ✅ 访问一个无害账号 profile,只**读取** follow button 存在,不点击
6. ✅ 检测 detectAnomaly() 各项 selector 在当前 X DOM 仍生效

RED → 拒启 + 输出修复指引(典型:profile 没登录、Chrome 没装、navigator.webdriver=true、参数缺失)。
