#!/usr/bin/env node
/* AI 味确定性扫描器（通用版）
 *
 * 对中文文档统计 18 类 AI 写作痕迹（tell），输出每文件每类计数、
 * 归一密度（每千 CJK 字）、分类命中矩阵与带行号取证示例。
 *
 * 重要：这是「毛统计」取证层——相当比例命中是正当用法（引用括注、
 * 术语加粗、版式分隔符等），且正则抓不到结构性 tell（段末升华、
 * 对仗标题、拟物化）。必须叠加语义判读扣除误报、补录结构性 tell，
 * 得到净口径后再动手改写。详见 skill 正文与 references/measurement.md。
 *
 * 用法：
 *   node aiflavor-scan.cjs <文件或目录>... [--json <输出路径.json>]
 *
 * 目录参数递归收集 .md / .html（跳过隐藏目录与 node_modules）；
 * 文件参数不限扩展名（.html 剥离标签后计数，其余按纯文本处理）。
 * --json 可选，把机器可读结果写到指定路径供后续 workflow 引用。
 */
const fs = require('fs');
const path = require('path');

// ---- CLI 参数 ----
const argv = process.argv.slice(2);
const inputs = [];
let jsonOut = null;
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--json') {
    jsonOut = argv[++i];
    if (!jsonOut) { console.error('错误：--json 需要一个输出路径参数'); process.exit(1); }
    continue;
  }
  inputs.push(argv[i]);
}
if (!inputs.length) {
  console.error('用法: node aiflavor-scan.cjs <文件或目录>... [--json <输出路径.json>]');
  process.exit(1);
}

// ---- 收集待扫描文件 ----
const SCAN_EXT = new Set(['.md', '.html']);
const collectDir = (dir) => {
  let out = [];
  for (const name of fs.readdirSync(dir)) {
    if (name.startsWith('.') || name === 'node_modules') continue;
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) out = out.concat(collectDir(p));
    else if (SCAN_EXT.has(path.extname(name).toLowerCase())) out.push(p);
  }
  return out;
};

let files = [];
for (const input of inputs) {
  const abs = path.resolve(input);
  if (!fs.existsSync(abs)) { console.error(`[warn] 路径不存在，跳过: ${input}`); continue; }
  if (fs.statSync(abs).isDirectory()) files = files.concat(collectDir(abs));
  else files.push(abs);
}
files = [...new Set(files)];
if (!files.length) { console.error('没有可扫描的文件。'); process.exit(1); }

// ---- 18 类词法/标点 tell（正则可精确捕捉的硬指标；核心资产，勿改动） ----
const TELLS = [
  ['破折号——', /——/g],
  ['不是X而是Y', /不是[^，。；、\n]{1,28}[，,]?(?:而是|，是)/g],
  ['既是…也/又是', /既[是要][^，。；\n]{1,18}[，,]?(?:[也又还]是|[也又]要)/g],
  ['不仅…还/而且/更', /(?:不仅|不光|不只)[^，。；\n]{1,22}[，,]?(?:还|而且|更|也)/g],
  ['元话语(综上/换言之/值得注意)', /(?:值得(?:注意|一提)|需要(?:指出|强调|说明)|总而言之|综上所述|简而言之|一言以蔽之|换句话说|换言之|总的来说|总体而言|不难看出|显而易见|某种(?:意义|程度)上)/g],
  ['"一句话"收束', /一句话/g],
  ['强调填充(真正/本质/核心在于)', /(?:真正(?:的|地)?|本质上|核心在于|关键在于|说到底|归根结底|从根本上|某种程度上)/g],
  ['从X到Y框架', /从[^，。、；\n]{1,12}到[^，。、；\n]{1,12}/g],
  ['不做X，做Y', /不(?:做|搞|拼|追求)[^，。；\n]{1,20}[，,](?:做|搞|拼|追求|要)/g],
  ['越X越Y', /越[^，。；\n]{1,6}越/g],
  ['这(就)是…的(关键/生命线)', /这(?:就)?是[^，。；\n]{1,22}的(?:理由|差异|关键|生命线|心脏|良心|前提|底气|护城河|根本|核心)/g],
  ['buzzword(护城河/飞轮/闭环…)', /(?:护城河|数据飞轮|飞轮|闭环|抓手|底座|心智|沉淀|赋能|对齐|拉满|打法|链路|颗粒度|破圈|长尾|卡位|生态位|加持|端到端|全链路|一体化|降维|心法|势能|杠杆|痛点|抓住)/g],
  ['营销最高级(极致/碾压/遥遥领先)', /(?:极致|顶级|最强|王炸|碾压|吊打|遥遥领先|降维打击|完爆|秒杀|天花板)/g],
  ['装饰符(✓★◆▼→…)', /[✓✅★☆◆◇▼▲►▶▷→⇒⟶✦●○※❖➤»]/g],
  ['冒号式副标题(标题含：)', /^#{1,6}\s.*[：:].+$/gm],
  ['中点排比(A · B · C)', /·/g],
  ['括号补充（…）', /（[^）\n]{1,40}）/g],
  ['粗体**…**', /\*\*[^*\n]{1,60}\*\*/g],
];

const stripForText = (s, isHtml) => {
  if (isHtml) s = s.replace(/<style[\s\S]*?<\/style>/g, '').replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ');
  return s;
};
const cjk = (s) => (s.match(/[一-鿿]/g) || []).length;
const lineOf = (raw, idx) => raw.slice(0, idx).split('\n').length;

// ---- 扫描 ----
const results = [];
for (const abs of files) {
  const label = path.relative(process.cwd(), abs) || abs;
  const raw = fs.readFileSync(abs, 'utf8');
  const isHtml = abs.toLowerCase().endsWith('.html');
  const text = stripForText(raw, isHtml);
  const chars = cjk(text);
  const row = { label, file: abs, chars, cats: {}, total: 0, examples: {} };
  for (const [name, re] of TELLS) {
    let target = name.startsWith('粗体') ? raw : (name.startsWith('冒号') ? raw : (isHtml ? text : raw));
    if (name.startsWith('粗体') && isHtml) { // html 粗体：strong/b 标签 + 内联 bold
      const m = raw.match(/<(?:strong|b)\b[^>]*>|font-weight\s*:\s*(?:bold|[6-9]00)/gi) || [];
      row.cats[name] = m.length; row.total += m.length; row.examples[name] = []; continue;
    }
    if (name.startsWith('装饰符') && isHtml) target = text; // 不数 css 里的符号
    re.lastIndex = 0;
    const hits = []; let m;
    while ((m = re.exec(target)) !== null) { hits.push([m.index, m[0]]); if (m[0].length === 0) re.lastIndex++; }
    row.cats[name] = hits.length; row.total += hits.length;
    row.examples[name] = hits.slice(0, 3).map(([i, s]) => `L${lineOf(target, i)}: ${s.replace(/\s+/g, ' ').slice(0, 36)}`);
  }
  row.density = chars ? +(row.total / chars * 1000).toFixed(1) : 0;
  results.push(row);
}

// ---- 输出 ----
const cats = TELLS.map((t) => t[0]);
const pad = (s, n) => String(s).padEnd(n);
const padN = (s, n) => String(s).padStart(n);
const shortLabel = (r) => path.basename(r.label).replace(/\.(md|html)$/i, '').slice(0, 6);

console.log('\n══════ AI 味确定性扫描（每千 CJK 字密度） ══════\n');
console.log(pad('文档', 40), padN('CJK字', 7), padN('命中', 6), padN('密度/千字', 9));
results.forEach((r) => console.log(pad(r.label.slice(0, 40), 40), padN(r.chars, 7), padN(r.total, 6), padN(r.density, 9)));
const allChars = results.reduce((a, r) => a + r.chars, 0);
const allTotal = results.reduce((a, r) => a + r.total, 0);
console.log(pad('—— 合计', 40), padN(allChars, 7), padN(allTotal, 6), padN(allChars ? (allTotal / allChars * 1000).toFixed(1) : 0, 9));

console.log('\n── 分类命中矩阵（行=类别，列=文档） ──\n');
console.log(pad('类别', 30), results.map((r) => padN(shortLabel(r), 8)).join(''), padN('合计', 7));
cats.forEach((c) => {
  const per = results.map((r) => r.cats[c] || 0);
  const sum = per.reduce((a, b) => a + b, 0);
  console.log(pad(c, 30), per.map((v) => padN(v, 8)).join(''), padN(sum, 7));
});

console.log('\n── 各类别取证示例（前 3） ──');
cats.forEach((c) => {
  const exs = results.flatMap((r) => (r.examples[c] || []).map((e) => `[${shortLabel(r)}] ${e}`));
  if (exs.length) { console.log('\n· ' + c + '：'); exs.slice(0, 4).forEach((e) => console.log('    ' + e)); }
});

console.log('\n[提醒] 以上为毛统计。约六成以上命中可能是正当用法，且未覆盖结构性 tell；');
console.log('       须叠加语义判读得净口径后再改写（见 skill 正文「双层测量」）。');

if (jsonOut) {
  fs.writeFileSync(path.resolve(jsonOut), JSON.stringify(results, null, 2));
  console.log(`\n[stats] -> ${jsonOut}`);
}
