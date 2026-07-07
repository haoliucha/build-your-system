# exceljs 生成器范式模板

适用范围:To-B 投标/交付物项目的一切 xlsx 产物(报价表、成本测算、排期表、预算清单)。核心不变式:**数据文件 → 生成器 → xlsx**,产物永不成为真源;任何手改都必须回捕进生成器(见 SKILL.md 第 2 节)。

## 目录形态

```
build/
  budget-data.cjs    # 单一真源:参数 + 条目数组(纯数据,无 IO)
  gen-budget.cjs     # 生成器:require 数据 → 实算派生 → 写 xlsx
docs/
  成本测算.xlsx       # 产物:只由生成器写出,git 跟踪但绝不手编后 commit
```

多个交付物共享同一批口径数字时,让多个生成器 require 同一个数据文件——这是「派生简版文件逐数一致」的结构性保证。

## 注释化模板(注释即规范,示例数字均为教学值)

```js
#!/usr/bin/env node
// gen-quote.cjs — 报价表生成器
// 运行: node gen-quote.cjs      依赖: npm i exceljs
'use strict';
const path = require('path');
const ExcelJS = require('exceljs');

// ── 1. 单一真源:所有会变的数字只允许出现在这里(或独立 data.cjs) ──
// 规范:表头、备注、console 输出、散文模板里需要数字的地方一律从
// 这里派生。用户手改产物里的参数后,回捕动作 = 把新值写进这里。
const P = {
  unitPrice: 100,     // 人月单价(教学值)
  months: 10,         // 计费工期
  headcount: 4,
  utilization: 0.8,   // 利用率是参数,不是写死的结果
};

// ── 2. 条目数组:显要金额列的唯一来源 ──
// 规范:每行金额 = 函数(P),不写死;增删行只动这里,
// 生成器自动重排小计公式范围。低档为 0 之类的特殊口径要带备注字段。
const items = [
  { name: '开发人力',
    low:  P.unitPrice * P.months * P.headcount * P.utilization,
    high: P.unitPrice * P.months * P.headcount,
    note: '低=按利用率折算,高=满负荷' },
  { name: '基础设施', low: 200, high: 300, note: '' },
  { name: '安全整改', low: 0,   high: 100, note: '低档由客户自有资源承担,故计 0' },
];

// ── 3. 派生值一律实算,禁止硬编码 ──
// 反模式:逐项与小计各自硬编码 → 口径变更后「逐项Σ ≠ 小计」,
// 对客表格被当场抓到。汇总(首年/多年)必须再从小计派生,
// 杜绝两处硬编码各自漂移。
const subtotalLow  = items.reduce((s, it) => s + it.low, 0);
const subtotalHigh = items.reduce((s, it) => s + it.high, 0);
const firstYearLow  = subtotalLow  + 1000;  // 1000 = 其他年度成本,同样应来自参数
const firstYearHigh = subtotalHigh + 2000;

(async () => {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('报价');
  ws.addRow(['条目', '金额低', '金额高', '备注']);

  items.forEach((it) => {
    const r = ws.addRow([it.name, it.low, it.high, it.note]);
    r.getCell(2).numFmt = '0.00';   // 全表统一数字格式(如 2 位小数),
    r.getCell(3).numFmt = '0.00';   // 精度口径也是口径,零散格式必翻车
  });

  // ── 4. 小计行:{ formula, result } 双写 ──
  // formula:让打开表格的人看到「逐项加总 = 小计」的可审计关系;
  // result:必须同时写实算值——很多查看器/无头管线不重算公式,
  //         只写 formula 会显示 0 或空。两者由同一数组派生,天然一致。
  const first = 2, last = 1 + items.length;
  const sub = ws.addRow([
    '小计',
    { formula: `SUM(B${first}:B${last})`, result: subtotalLow },
    { formula: `SUM(C${first}:C${last})`, result: subtotalHigh },
    '',
  ]);
  sub.getCell(2).numFmt = '0.00';
  sub.getCell(3).numFmt = '0.00';

  // ── 5. 控制台验证输出:重生成即自带核对 ──
  // 口径变更后先看这里的数字对不对,再谈重生成;
  // 「只改呈现不改口径」的重构,以这里逐一相同为验收线。
  console.log(`[gen-quote] 小计 低=${subtotalLow.toFixed(2)} 高=${subtotalHigh.toFixed(2)}`);
  console.log(`[gen-quote] 首年 低=${firstYearLow.toFixed(2)} 高=${firstYearHigh.toFixed(2)}`);

  // ── 6. 写盘:绝对路径(防 cwd 漂移),写盘前确认文件未被办公软件占用 ──
  // macOS: lsof <file>,检出写句柄即停,让用户「关闭不保存」(SKILL.md 第 2 节)。
  await wb.xlsx.writeFile(path.join(__dirname, '..', 'docs', 'quote.xlsx'));
  console.log('[gen-quote] written.');
})();
```

## 生成器检查清单

- [ ] 所有会变的数字集中在参数对象/数据文件,产物中零硬编码副本
- [ ] 显要金额列逐项可见加总 = 小计;小计 reduce 实算;汇总从小计派生
- [ ] 小计/合计单元格 `{ formula, result }` 双写,两者同源
- [ ] numFmt 全表统一(精度也是口径)
- [ ] console 打印关键数字,作为口径验证与「呈现重构零变动」的比对基准
- [ ] 路径全绝对;写盘前 lsof 查占用(macOS/办公软件场景)
- [ ] 重生成后用 scripts/xlsx-dump.cjs 抽验单元格实值与格式(命令零退出 ≠ 已更新)
- [ ] 用户手改过的值已回捕为参数默认值;用户删的行在数据文件中保持删除

## 变体说明

- **驱动别的产物的共享数据**(团队名册/任务包/里程碑):同样收进共享数据文件,标签改动只改一处,全部渲染端(参数表/封面/甘特/负载行)自动跟随。
- **图类产物**(SVG/drawio):同一范式——代码 spec 是真源,GUI 手工排版调整用几何 diff 反向移植回 spec 重生成,绝不让 GUI 文件变成新数据源。
- **确定性输出**:生成器不写时间戳等噪声时,重跑后未涉及产物字节零变化,git diff 即改动范围守恒证据。xlsx 内嵌时间戳做不到这点,故 xlsx 验证走逻辑值 dump。
