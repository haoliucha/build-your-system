#!/usr/bin/env node
/**
 * xlsx-dump.cjs — ExcelJS 逐格「逻辑值」dump 工具
 *
 * 用途:把 xlsx 按逻辑值(值/公式/数字格式)逐格导出为稳定的行文本,
 * 供 diff 对比「手改版 vs 干净重生成版」,精确捕捉用户手改意图。
 * 办公软件(WPS/Excel)保存时会重排 xlsx 内部 XML,raw 字节 diff
 * 噪声极大不可用;逻辑值 dump 是唯一可靠的对比手段。
 *
 * 用法:
 *   node xlsx-dump.cjs <file.xlsx> [sheetName]
 *
 * 输出:每格一行,TAB 分隔四列
 *   sheet!addr <TAB> value <TAB> formula <TAB> numFmt
 *   (value 对公式格取其缓存结果;富文本拼接为纯文本;
 *    值内的 TAB/换行转义为 \t \n,保证一行一格可 diff)
 *
 * 依赖 exceljs,二选一:
 *   1) 就地安装:在本脚本目录或调用目录 `npm i exceljs`
 *   2) 复用已有安装:`NODE_PATH=/path/to/node_modules node xlsx-dump.cjs ...`
 *
 * 典型回捕流程(配合 SKILL.md 第 2 节):
 *   cp 手改版.xlsx 手改版.xlsx.bak                       # 先备份
 *   node gen-xxx.cjs                                     # 干净重生成对照版
 *   node xlsx-dump.cjs 手改版.xlsx.bak > /tmp/hand.tsv
 *   node xlsx-dump.cjs 重生成版.xlsx   > /tmp/clean.tsv
 *   diff /tmp/hand.tsv /tmp/clean.tsv                    # 差异 = 手改意图
 */
/*
 * 已知行为:合并单元格会按每个成员格重复输出主格的值(ExcelJS 语义),
 * 两侧 dump 行为一致,不影响 diff。
 */
'use strict';

const path = require('path');

// 管道下游提前关闭(如 | head)时静默退出,不抛 EPIPE 堆栈
process.stdout.on('error', (err) => {
  if (err && err.code === 'EPIPE') process.exit(0);
  throw err;
});

let ExcelJS;
try {
  ExcelJS = require('exceljs');
} catch (e) {
  console.error(
    '缺少依赖 exceljs。请执行 `npm i exceljs`,' +
    '或用 `NODE_PATH=<含 exceljs 的 node_modules 路径> node xlsx-dump.cjs ...` 运行。'
  );
  process.exit(2);
}

/** 单元格逻辑值 → 纯文本(公式格取缓存 result,富文本拼接) */
function fmtValue(v) {
  if (v === null || v === undefined) return '';
  if (v instanceof Date) return v.toISOString();
  if (typeof v === 'object') {
    if (Array.isArray(v.richText)) return v.richText.map((r) => r.text).join('');
    if (v.formula !== undefined || v.sharedFormula !== undefined) return fmtValue(v.result);
    if (v.hyperlink !== undefined) return String(v.text != null ? v.text : v.hyperlink);
    if (v.error !== undefined) return String(v.error);
    return JSON.stringify(v);
  }
  return String(v);
}

/** 提取公式文本(共享公式标注前缀,便于肉眼区分) */
function fmtFormula(v) {
  if (v && typeof v === 'object') {
    if (v.formula) return v.formula;
    if (v.sharedFormula) return 'shared:' + v.sharedFormula;
  }
  return '';
}

/** 转义 TAB/换行,保证一格一行 */
function esc(s) {
  return String(s).replace(/\\/g, '\\\\').replace(/\t/g, '\\t').replace(/\r?\n/g, '\\n');
}

async function main() {
  const [, , file, sheetArg] = process.argv;
  if (!file) {
    console.error('用法: node xlsx-dump.cjs <file.xlsx> [sheetName]');
    process.exit(1);
  }

  const wb = new ExcelJS.Workbook();
  await wb.xlsx.readFile(path.resolve(file));

  let sheets = wb.worksheets;
  if (sheetArg) {
    sheets = sheets.filter((ws) => ws.name === sheetArg);
    if (!sheets.length) {
      console.error(
        `找不到 sheet「${sheetArg}」。现有 sheet: ` +
          wb.worksheets.map((w) => w.name).join(', ')
      );
      process.exit(1);
    }
  }

  for (const ws of sheets) {
    ws.eachRow({ includeEmpty: false }, (row) => {
      row.eachCell({ includeEmpty: false }, (cell) => {
        const v = cell.value;
        process.stdout.write(
          [
            `${ws.name}!${cell.address}`,
            esc(fmtValue(v)),
            esc(fmtFormula(v)),
            esc(cell.numFmt || ''),
          ].join('\t') + '\n'
        );
      });
    });
  }
}

main().catch((err) => {
  console.error(err && err.message ? err.message : err);
  process.exit(1);
});
