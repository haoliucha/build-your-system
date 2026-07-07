#!/usr/bin/env node
/**
 * add-outline.cjs — 将本地 HTML 导出为带书签大纲(outline)的 PDF。
 *
 * 背景:
 *   Chrome 打印引擎(printToPDF / Cmd+P)导出的 PDF 天然不写 outline 书签。
 *   Playwright 的 page.pdf() 提供 outline: true,可从 HTML 的 h1-h6 标题层级
 *   自动生成层级书签,并支持 tagged(结构化/无障碍)PDF。
 *   长文档交付默认走这条路径,并把本脚本固化进构建链以便随时重生成。
 *
 * 依赖:
 *   - Node.js >= 18
 *   - playwright-core(`npm i playwright-core`,不需要下载浏览器)
 *   - 本机已安装 Chrome(脚本用 channel: 'chrome' 调系统 Chrome;
 *     macOS/Windows/Linux 桌面机均可。无 Chrome 的环境可改 channel
 *     或安装 playwright 自带 chromium 后去掉 channel 参数)
 *
 * 用法:
 *   node add-outline.cjs <input.html> <output.pdf>
 *
 *   <input.html>  本地 HTML 文件路径(相对/绝对均可),也接受 file:// 或 http(s):// URL
 *   <output.pdf>  输出 PDF 路径
 *
 * 参数说明(按需在下方调整):
 *   - preferCSSPageSize: 沿用 HTML 内 CSS @page 声明的纸张与边距(如 A4)
 *   - printBackground:   保留背景色/表头填充(深色封面必需)
 *   - tagged:            输出结构化/无障碍 PDF
 *   - outline:           从 h1-h6 生成层级书签
 *
 * 注意:
 *   - 导出后必须逐字核对本脚本打印的成功行,并打开 PDF 抽验本次新改的内容;
 *     导出链路静默失败会留下陈旧 PDF 冒充新版。
 *   - 嵌图请用内联 2x PNG;含 blur 等滤镜的内联 SVG 会使打印直接报
 *     Printing failed(症状:仅输出一个裸 '}')。
 *   - 中文文档字体栈必须 CJK-first,详见 skill 正文与 references/pdf-export-cjk.md。
 */
'use strict';

const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

function toUrl(input) {
  if (/^(https?|file):\/\//i.test(input)) return input;
  const abs = path.resolve(input);
  if (!fs.existsSync(abs)) {
    console.error(`输入文件不存在: ${abs}`);
    process.exit(1);
  }
  return 'file://' + abs;
}

const [, , htmlArg, pdfArg] = process.argv;
if (!htmlArg || !pdfArg) {
  console.error('用法: node add-outline.cjs <input.html> <output.pdf>');
  process.exit(1);
}

const url = toUrl(htmlArg);
const pdfPath = path.resolve(pdfArg);

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.emulateMedia({ media: 'print' });
  await page.pdf({
    path: pdfPath,
    preferCSSPageSize: true, // 沿用 CSS @page 的纸张与边距
    printBackground: true,   // 保留背景色/表头填充
    tagged: true,            // 结构化/无障碍 PDF
    outline: true,           // 从 h1-h6 生成大纲书签
  });
  await browser.close();

  const size = fs.statSync(pdfPath).size;
  console.log(`PDF (with outline) -> ${pdfPath} (${(size / 1024 / 1024).toFixed(2)} MB)`);
  console.log('提醒: 请打开 PDF 核验书签层级与关键页渲染,勿以本行输出替代目检。');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
