#!/usr/bin/env node
'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const ROOT = path.join(__dirname, '..');
const SCRIPTS = path.join(ROOT, 'scripts');
let passed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ✅ ${name}`); }
  catch (error) { console.error(`  ❌ ${name}\n${error.stack}`); process.exitCode = 1; }
}

console.log('\nx-unfollow v4 suite');
test('完整 current-state / scan-guard 测试通过', () => {
  const result = spawnSync(process.execPath, [path.join(__dirname, 'v3-current-state.test.cjs')], { encoding: 'utf8' });
  assert.strictEqual(result.status, 0, result.stderr || result.stdout);
});

test('分页响应 / cursor / 单次粉丝变化报告测试通过', () => {
  const result = spawnSync(process.execPath, [path.join(__dirname, 'v4-pagination.test.cjs')], { encoding: 'utf8' });
  assert.strictEqual(result.status, 0, result.stderr || result.stdout);
});

test('运行锁只阻止并发，不包含时间冷却', () => {
  const policy = require(path.join(SCRIPTS, 'lib', 'rate-policy.cjs'));
  assert.strictEqual('FULL_RUN_COOLDOWN_MS' in policy, false);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-v3-lock-'));
  const cli = path.join(SCRIPTS, 'run-lock.cjs');
  const env = { ...process.env, XU_DATA_DIR: dir, XU_RUN_OWNER_PID: String(process.pid) };
  const first = spawnSync(process.execPath, [cli, 'claim'], { env, encoding: 'utf8' });
  assert.strictEqual(first.status, 0, first.stderr);
  assert.strictEqual(JSON.parse(fs.readFileSync(path.join(dir, 'network-run-state.json'))).status, 'active');
  const second = spawnSync(process.execPath, [cli, 'claim'], { env, encoding: 'utf8' });
  assert.strictEqual(second.status, 18, second.stderr);
  assert.strictEqual(spawnSync(process.execPath, [cli, 'release', first.stdout.trim()], { env }).status, 0);
  assert.strictEqual(JSON.parse(fs.readFileSync(path.join(dir, 'network-run-state.json'))).status, 'idle');
  assert.strictEqual(spawnSync(process.execPath, [cli, 'claim'], { env }).status, 0);
});

test('following 的 badge 证据不降级；followers membership 不依赖按钮', () => {
  const C = require(path.join(SCRIPTS, 'lib', 'cell-parse.cjs'));
  const cell = { avatarTestId: 'UserAvatar-Container-Alice', hrefs: ['/Alice'], hasFollowIndicator: true, hasActionButton: false, nameText: 'Alice', innerText: '关注了你' };
  const map = new Map();
  C.mergeObservation(map, C.parseCell(cell));
  C.mergeObservation(map, C.parseCell({ ...cell, hasFollowIndicator: false, hasActionButton: true, innerText: '' }));
  assert.strictEqual(map.get('alice').isFollowingMe, true);
  assert.deepStrictEqual(C.parseMembershipCell({ ...cell, hasFollowIndicator: false, hasActionButton: false }), { handle: 'Alice', name: 'Alice' });
});

test('订阅按钮永远不被识别为取关按钮', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowControl({ ariaLabel: '订阅 到 @yangyi', text: '订阅', testid: '3122661542-unfollow' }, 'yangyi'), false);
  assert.strictEqual(U.isExactUnfollowControl({ ariaLabel: '取消关注 @yangyi', text: '' }, 'yangyi'), true);
});

test('异常词只出现在用户内容时不误报平台限流', () => {
  const A = require(path.join(SCRIPTS, 'lib', 'anomaly.cjs'));
  assert.strictEqual(A.classifyAnomaly({ bodyText: 'x'.repeat(80) + ' 请稍后再试', userText: '请稍后再试', path: '/home' }), null);
  assert.strictEqual(A.EXIT_CODES.PAGE_DRIFT, 15);
  assert.strictEqual(A.EXIT_CODES.COUNT_ANOMALY, 17);
});

test('受控浏览器默认无头，只有 XU_HEADLESS=0 显式进入可见调试', () => {
  let Browser = {};
  try { Browser = require(path.join(SCRIPTS, 'lib', 'browser-launch.cjs')); } catch {}
  assert.strictEqual(typeof Browser.resolveHeadless, 'function');
  assert.strictEqual(typeof Browser.persistentContextOptions, 'function');
  assert.strictEqual(Browser.resolveHeadless({}), true);
  assert.strictEqual(Browser.resolveHeadless({ XU_HEADLESS: '1' }), true);
  assert.strictEqual(Browser.resolveHeadless({ XU_HEADLESS: '0' }), false);
  assert.throws(() => Browser.resolveHeadless({ XU_HEADLESS: 'false' }), /XU_HEADLESS must be 0 or 1/);
  assert.strictEqual(Browser.persistentContextOptions({ width: 1400, height: 1000 }, {}).headless, true);
});

test('扫描和取关入口统一使用共享浏览器配置，不硬编码可见模式', () => {
  for (const file of ['list-snapshot.cjs', 'unfollow.cjs']) {
    const source = fs.readFileSync(path.join(SCRIPTS, file), 'utf8');
    assert.match(source, /browser-launch\.cjs/, file);
    assert.match(source, /persistentContextOptions/, file);
    assert.doesNotMatch(source, /headless:\s*false/, file);
  }
});

test('run.sh 在任何 X 请求前校验并报告浏览器模式', () => {
  const run = fs.readFileSync(path.join(ROOT, 'run.sh'), 'utf8');
  assert.match(run, /XU_HEADLESS/);
  assert.match(run, /browser=headless/);
  assert.match(run, /browser=headed-debug/);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-invalid-headless-'));
  const result = spawnSync('bash', [path.join(ROOT, 'run.sh')], {
    env: {
      ...process.env,
      MY_HANDLE: 'haoliucha',
      XU_HEADLESS: 'false',
      XU_DATA_DIR: dir,
      PROFILE_DIR: path.join(dir, 'missing-profile'),
    },
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2, result.stderr || result.stdout);
  assert.match(`${result.stdout}\n${result.stderr}`, /XU_HEADLESS must be 0 or 1/);
});

test('异常提示假定受控上下文已关闭，不要求打开仍在运行的窗口', () => {
  const A = require(path.join(SCRIPTS, 'lib', 'anomaly.cjs'));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-alert-copy-'));
  const file = path.join(dir, 'ALERT.txt');
  A.writeAlert(file, { type: 'CAPTCHA', text: 'challenge' });
  const alert = fs.readFileSync(file, 'utf8');
  assert.doesNotMatch(alert, /Open the Chrome window \(still running\)/);
  assert.match(alert, /controlled browser context has closed/i);
});

test('技能说明声明默认无头、显式调试覆盖和禁止自动回退', () => {
  const skill = fs.readFileSync(path.join(ROOT, 'SKILL.md'), 'utf8');
  assert.match(skill, /默认无头/);
  assert.match(skill, /XU_HEADLESS=0/);
  assert.match(skill, /不自动回退到可见模式/);
});

test('活动实现不再引用 snapshots 或 dated reports', () => {
  const files = ['run.sh', 'scripts/list-snapshot.cjs', 'scripts/classify.cjs', 'scripts/promote-current.cjs', 'scripts/profile-counts.cjs', 'scripts/verify-unfollow.cjs'];
  const source = files.map((file) => fs.readFileSync(path.join(ROOT, file), 'utf8')).join('\n');
  assert.doesNotMatch(source, /snapshots\//);
  assert.doesNotMatch(source, /non-recip-reasons-/);
  assert.doesNotMatch(source, /profile-refresh-/);
  assert.doesNotMatch(source, /verify-unfollow-/);
});

test('所有网络脚本都要求唯一 run token', () => {
  for (const file of ['list-snapshot.cjs', 'profile-counts.cjs', 'unfollow.cjs']) {
    assert.match(fs.readFileSync(path.join(SCRIPTS, file), 'utf8'), /assertRunToken\(\)/, file);
  }
});

test('本地验证不导入 Playwright、不访问个人主页', () => {
  const source = fs.readFileSync(path.join(SCRIPTS, 'verify-unfollow.cjs'), 'utf8');
  assert.doesNotMatch(source, /playwright|https:\/\/x\.com/);
});

test('SKILL.md 只保留运行时指令，维护者验证与同步流程留在 README', () => {
  const skill = fs.readFileSync(path.join(ROOT, 'SKILL.md'), 'utf8');
  const readme = fs.readFileSync(path.join(ROOT, 'README.md'), 'utf8');
  assert.doesNotMatch(skill, /^## 开发与验证$/m);
  assert.doesNotMatch(skill, /node tests\/run-tests\.cjs|bash -n run\.sh|同步脚本/);
  assert.match(readme, /node tests\/run-tests\.cjs/);
});

process.on('exit', () => {
  if (!process.exitCode) console.log(`\n${passed} top-level checks passed`);
});
