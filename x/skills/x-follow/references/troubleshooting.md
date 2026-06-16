# 12 个常见故障 + 修复

按"首次实战可能遇到的概率"排序。

## 1. Chrome 启动失败,`Failed to launch chromium`

**症状**:Node 报错 SingletonLock 冲突或 Chrome 进程已存在。

**原因**:profile copy 里残留了 SingletonLock 文件,或 X 实际登录的浏览器没关。

**修复**:
```bash
rm -f $PROFILE_DIR-campaign/{SingletonLock,SingletonCookie,SingletonSocket}
# 确认没有其他 Chrome 进程占用同 profile dir
ps aux | grep -i chrome | grep -i playwright-chrome-profile
```

---

## 2. `navigator.webdriver === true`,smoke test RED

**症状**:smoke-test.cjs 报 `webdriver=true,启动参数失效`。

**原因**:Playwright 默认带 `--enable-automation`,需手动去掉。

**修复**(检查 campaign.cjs 的 launch 配置):
```js
ignoreDefaultArgs: ['--enable-automation'],
args: ['--disable-blink-features=AutomationControlled'],
```
两个都要,缺一不可。

---

## 3. 跳转到 /login,smoke test 失败

**症状**:`https://x.com/home` 跳到 `https://x.com/i/flow/login`。

**原因**:profile 里没登录态(可能是空 profile,或 cookies 过期)。

**修复**:
- 检查原 profile(`PROFILE_DIR`)是否真的登录了 X
- 用 MCP 浏览器打开原 profile,确认能进 /home
- 然后重新 cp 到 campaign

---

## 4. `not_blue` 漏判(实际是蓝V 却被拒)

**症状**:script 反复把蓝V 用户判为 `reject:not_blue`,通过 MCP 二次访问看 profile 实际有蓝V 标。

**原因**:script 在 SVG 渲染前就查询了 DOM。

**修复**:在 `verifyAndFollow` 函数加双段等待:
```js
// 段 1:等 UserName
for (let i = 0; i < 12; i++) {
  if (document.querySelector('div[data-testid="UserName"]')) break;
  await s(500);
}
// 段 2:等 button OR badge
for (let i = 0; i < 10; i++) {
  if (document.querySelector('button[data-testid$="-follow"], svg[aria-label="认证账号"]')) break;
  await s(500);
}
```

如果 tracker.rejected 里已经有大量 `not_blue` 误判,**先清理**再重跑:
```python
t['rejected'] = [r for r in t['rejected'] if 'not_blue' not in r['r']]
```

---

## 5. Click 后 verify 失败但 X 实际已 follow

**症状**:log 显示 `pass` 但没 `✅ FOLLOW` 标记。MCP 二次验证发现实际已关注。

**原因**:click 触发后,X 服务端处理 + 前端 DOM update 是异步的;script 检查太快。

**修复**:已在最新 verify 函数实现:
- post_click_settle_ms: 2500 (初始等)
- fallback: 若 follow btn 不存在 → `followed_assumed`,当成功记
- 详见 `verify-logic.md` 第 4 段

历史已漏判的可通过 MCP 单独补 tracker。

---

## 6. 大量 `already_following` rejects

**症状**:script 处理 100 candidates 里有 50 个返回 `already_following`,看着是浪费。

**原因**:my_handle 已有 200+ following,在 蓝V互关 圈子重叠严重。

**修复**:
```bash
# 一次性抓自己的 /following,加入 skip set
node scripts/snapshot-following.cjs YOUR_HANDLE > /tmp/my-following.json
# 把 handles 加进 tracker.rejected (reason: pre_existing_follow)
python3 -c "
import json
t = json.load(open('tracker.json'))
my = json.load(open('/tmp/my-following.json'))
for h in my['handles']:
    if h not in {f['handle'] for f in t['followed']}:
        t['rejected'].append({'h': h, 'r': 'pre_existing_follow'})
json.dump(t, open('tracker.json','w'), indent=2)
"
```

本次实战这一步省了 30% 时间。

---

## 7. Crypto bio 漏过滤(CryptoDaddyCoco 这种 case)

**症状**:Handle 含 `Crypto` 但 bio 是空的,script 判 pass 实际是币圈号。

**原因**:bio 用 `\bcrypto\b` 词边界匹配,handle 没参与匹配。

**修复**:双层检查:
```js
const matchBio = bioRegex.test(bio) || zhTokens.find(k => bio.includes(k));
const matchHandle = enTokens.find(k => H.toLowerCase().includes(k));  // substring
if (matchBio || matchHandle) return 'reject:crypto_bio';
```

---

## 8. Context 爆炸(LLM 端)

**症状**:LLM 每次都 inline 80 行 JS evaluate,context 用量飙升。

**修复**(已实现):用 localStorage 缓存 verify 函数:
```js
// 首次:写
localStorage.setItem('vf', VERIFY_JS_SRC);
// 后续每次 evaluate 只需:
await eval('(' + localStorage.getItem('vf') + ')')();
```

LocalStorage 跨页面持久化(同 origin),所以 X 内部导航都能复用。

---

## 9. Log 重复

**症状**:campaign.log 每行重复 2 次。

**原因**:Node 脚本既写 log file 又 stdout,shell `> log` 又把 stdout 重定向。

**修复**:启动用 `> /dev/null 2>&1` 而非 `>> campaign.log`,让脚本自己管 log。

---

## 10. 跑 30 分钟后突然 5+ consecutive errors

**症状**:连续报 `page.goto: Target page, context or browser has been closed`。

**原因**:浏览器进程崩了(可能内存不足、Chrome update、用户手动关 window)。

**修复**:
- script 已有 5 次连续 error 退出兜底
- 重启 script 会自动从 tracker 恢复进度
- 如果反复发生,检查 Chrome 内存(`Activity Monitor`)和 disk

---

## 11. 候选池枯竭

**症状**:script 跑到一半 `unprocessed=0`,但 target 还没到。

**原因**:harvest 不够。

**修复**:
1. 临时:挖更多 source(`harvest.cjs replies` 多挖几个 top post)
2. 长期:在 `presets.md` 调整 search_queries / followers_max 放宽筛选

---

## 12. CAPTCHA 弹出 / 账号被限制

**症状**:script 退出 code 10/11/13,ALERT.txt 报 CAPTCHA 或 ACCOUNT_RESTRICTED。

**原因**:
- 节奏太快(降低 follow_wait_min/max)
- 新号配额耗尽(等 24h 再跑)
- X 算法本次激进(等几天)
- profile 异常(浏览器太干净,无 history)

**修复**:
- **不要硬重试**,这会加剧风控
- 等 24h 后重新跑 1-3 个试水(`target=1`)
- 持续异常 → 换 profile / 检查账号状态

---

## 13. (bonus) `evaluate returned undefined,skipping`

**症状**:log 显示这条信息,后续处理失败。

**原因**:`page.evaluate(VERIFY_JS_STR)` 传入的字符串只评估了**函数定义**,没调用。

**修复**:VERIFY_JS_STR 必须是 IIFE:
```js
// ❌ 错(只返回函数引用)
const VERIFY_JS = `async () => { ... }`;
// ✅ 对(立即调用 returns Promise)
const VERIFY_JS = `(async () => { ... })()`;
```

---

## Profile Isolation 完整步骤

```bash
ORIG=~/.config/playwright-chrome-profile
COPY=$ORIG-campaign

# 1. 复制(保留 cookies/history/localStorage)
cp -R "$ORIG" "$COPY"

# 2. 删除 singleton 锁(必须)
rm -f "$COPY"/SingletonLock "$COPY"/SingletonCookie "$COPY"/SingletonSocket

# 3. 校验
ls -la "$COPY"/Cookies > /dev/null || { echo "ERR: no cookies"; exit 1; }

# 4. 用 COPY 启动 chromium(代码层)
chromium.launchPersistentContext(COPY, { ... })

# 5. campaign 结束清理
rm -rf "$COPY"
```

如果 MCP playwright 还在跑(占着原 profile),copy 之后两个 Chrome 实例可以并行运行,因为是不同 profile 目录。X 服务端看到的是"同 account 两个 session",合规。
