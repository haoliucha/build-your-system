#!/usr/bin/env node
// discount-check.cjs — 折扣标签反算互证
//
// 采用任何带折扣标签的第三方价格前,先跑这一步:
// 每条 价格:折扣 反算隐含列表价(价格÷折扣),各路径与声称列表价互证,
// 偏差超过阈值即 FAIL(整行撤回,不是修数)。
//
// 用法:
//   node discount-check.cjs [声称列表价|-] <价格:折扣> [价格:折扣 ...] [--tol=0.5]
//
//   声称列表价  已知的官网列表价;未知则传 "-",仅做各路径之间互证
//   价格:折扣   如 400:0.4(包年 4 折 400)、500:0.5(首购 5 折 500)
//   --tol       允许偏差百分比,默认 0.5(严格场景用 0.05)
//
// 示例(教学值):
//   node discount-check.cjs 1000 500:0.5 400:0.4          → PASS(两路径均还原 1000)
//   node discount-check.cjs 1000 250:0.8                  → FAIL(标称8折实为2.5折,整行撤回)
//   node discount-check.cjs - 500:0.5 400:0.4             → PASS(互证,隐含列表价一致)
//
// 退出码:0 = PASS,1 = FAIL,2 = 参数错误

'use strict';

const rawArgs = process.argv.slice(2);
let tol = 0.5;
const args = [];
for (const a of rawArgs) {
  const m = a.match(/^--tol=([\d.]+)$/);
  if (m) tol = parseFloat(m[1]);
  else args.push(a);
}

function usageExit(msg) {
  if (msg) console.error(`错误: ${msg}\n`);
  console.error('用法: node discount-check.cjs [声称列表价|-] <价格:折扣> [价格:折扣 ...] [--tol=0.5]');
  console.error('示例: node discount-check.cjs 1000 500:0.5 400:0.4');
  process.exit(2);
}

if (args.length < 2) usageExit('至少需要 声称列表价(或 -) 和一条 价格:折扣');

const claimedRaw = args[0];
const claimed = claimedRaw === '-' ? null : parseFloat(claimedRaw);
if (claimedRaw !== '-' && (!isFinite(claimed) || claimed <= 0)) usageExit(`声称列表价无效: ${claimedRaw}`);

const paths = [];
for (const p of args.slice(1)) {
  const m = p.match(/^([\d.]+):([\d.]+)$/);
  if (!m) usageExit(`价格:折扣 格式无效: ${p}(应如 400:0.4)`);
  const price = parseFloat(m[1]);
  const disc = parseFloat(m[2]);
  if (!(price > 0)) usageExit(`价格无效: ${p}`);
  if (!(disc > 0 && disc <= 1)) usageExit(`折扣应为 (0,1] 小数(4折=0.4): ${p}`);
  paths.push({ price, disc, implied: price / disc });
}

console.log(`阈值: 偏差 <= ${tol}%`);
if (claimed !== null) console.log(`声称列表价: ${claimed}`);
for (const p of paths) {
  console.log(`  ${p.price} ÷ ${p.disc} = 隐含列表价 ${p.implied.toFixed(2)}`);
}

const refs = claimed !== null ? [claimed, ...paths.map(p => p.implied)] : paths.map(p => p.implied);
const min = Math.min(...refs);
const max = Math.max(...refs);
const devPct = ((max - min) / min) * 100;

console.log(`最大偏差: ${devPct.toFixed(3)}%`);

if (refs.length < 2) {
  console.log('WARN: 只有一条路径且无声称列表价,无法互证——找第二来源或硬锚点(用户截图/官网价)。');
  process.exit(1);
}

if (devPct <= tol) {
  console.log('PASS: 折扣标签自洽。仍需确认基准是列表价而非活动价(活动价再折 = 双重打折)。');
  process.exit(0);
} else {
  console.log('FAIL: 折扣标签对不上,整行撤回,不得进入成本模型;回到硬锚点重建价格阶梯。');
  process.exit(1);
}
