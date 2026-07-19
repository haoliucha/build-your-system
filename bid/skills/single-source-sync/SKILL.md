---
name: single-source-sync
description: Use when working on a To-B bid or deliverable project where numbers, labels, and wording live in a single source (data file + generator) and fan out into xlsx/PDF/HTML/diagram artifacts — whenever changing a price, tier, headcount, term or claim, regenerating artifacts, reconciling a user's hand-edited spreadsheet back into its generator, or committing generated outputs. Triggers on phrases like "改口径", "口径级联", "同步所有交付物", "重新生成 xlsx", "我手改了表格", "捕捉我改了什么", "残留 grep", "逐项加总不等于小计", "文件没更新", "投标交付物同步", "回捕生成器".
---

# single-source-sync — 单一真源与口径级联纪律

To-B 投标/交付物项目的核心纪律:全部数字、称谓、口径只存在于「数据文件 + 生成器」这一个真源;xlsx/PDF/HTML/图都是产物,只能重生成,绝不手改后 commit。任何口径变更按固定链级联到全部消费端。

## 1 生成器纪律

- 派生展示值(小计/合计/斜率/表头档位/散文里的数字)一律由参数实时计算,禁止硬编码——散文模板里写死的数字在下一次口径变更时必然腐烂失同步。
- 报价表的显要金额列必须逐项可见加总 = 小计;小计由条目数组 reduce 实算,汇总(首年/多年)再从小计派生。反模式:逐项与小计各自硬编码 → 客户两次抓到「子项加总 ≠ 小计」。
- 单元格双写 `cell.value = { formula, result }`:公式呈现可审计的加总关系,实算值保证不重算公式的查看器也显示正确。完整范式见 references/generator-template.md。
- 把硬编码路径的构建工具用于新产物时,新建 CLI 参数化版本,不改已支撑既有交付物的旧脚本。
- 构建脚本一律用绝对路径:cwd 漂移会静默在错误目录用旧产物重建而不报错。

## 2 手改产物回捕(铁律)

用户直接手改了生成的 xlsx/图时,绝不 commit 手改产物、绝不在产物上叠改。反模式:演示前夜发现两份手改表只改了一半——头条数字对不上(一份 100、一份 130)、公式 #REF!,投屏必穿帮。正确做法(详见 references/cascade-checklist.md):

1. 备份手改版。
2. 从源干净重生成一份对照版,用 scripts/xlsx-dump.cjs 做逐格逻辑值 diff 捕捉改动意图——办公软件保存会重排内部 XML,raw diff 噪声大不可用;drawio 类 GUI 文件改用几何/结构 diff。
3. 与用户确认哪套数字是权威口径、删除类改动是有意还是误删。
4. 把意图逐项落回生成器源(参数默认值/删行),再从源重生成——保证改参数格仍自动重算,产物永不成为唯一真源。
5. 默认怀疑派生字段:手改往往主表改全了,但汇总曲线、结论行、颜色标注、备注漏改成自相矛盾,落源时逐项排查修复,矛盾状态拒绝 commit。

**重生成前必查写句柄**(macOS:`lsof <file.xlsx>`):桌面办公软件(WPS/Excel)开着文件,会在脚本重生成后把内存旧副本回存覆盖——此坑实测复发 3 次。检出即停,让用户「关闭不保存」后再生成。

## 3 口径级联固定链

任何口径变更(数字/档位/称谓/标签/说辞)走固定七步:改源 → 重跑生成器核对控制台数字 → 全库 grep 旧值残留逐条判读 → 同步叙事文档 → 重生成受影响产物 → 更新 memory → 分组提交。要点:

- **先映射爆炸半径**:grep 全库,区分「公式驱动(自动级联重算)」与「硬编码副本(逐处手改清单)」。封面/目录模板常藏在构建脚本里,兄弟文档、memory 同属级联对象——某次封面旧值残留,就是因为它模板化在脚本内,历次级联都漏掉。
- 共享数据源的标签改动要追到全部渲染端(参数表/封面/名册/甘特/负载行/散文),不能只改被点名的那张表。
- 小计对了,明细行仍可能陈旧:上一轮参数算出的残值最易漏,要逐行对抗复核,不能只验汇总。
- grep 命中逐条判读:数字子串(365 含 65)、改动说明自述、同词多义(清「平台迁移」时,「数据迁移」「迁移测试」是合法用法)都是合法误报,不误伤。
- 批量 replace 后重读每个替换点语境,定「表格用短标签、散文用完整措辞」双规范,防病句、防修补时复活废弃旧标签。
- 指令若反转用户已锁定的决策、或使头条数字大幅移动:先算出级联后的完整数字表呈给用户,确认意图与同步范围再动手。前提被推翻(如部署/租户模型)时先让用户拍板,不在旧前提上缝补数字。

## 4 重生成验证

- 命令零退出 ≠ 产物已更新(管线某步会静默失败)。重生成后抽验内容特征:新口径字符串已出现、旧字符串已消失、单元格 numFmt/页数符合预期。
- xlsx 字节级非确定(内嵌时间戳):判断是否真更新,用 xlsx-dump 比内容,不看 mtime/git modified;用户报「文件没更新」先核实磁盘实态,表象背后常藏另一个真 bug。
- 图/SVG 类保持确定性渲染:重跑后未涉及产物字节零变化,git diff 即改动范围守恒的证据。
- 客户演示前从生成器重出全部表格,交叉核对各文件头条数字与公式健康度;手改过的文件是最高风险源。

## 5 提交纪律

- 显式列文件路径暂存,禁 `git add -A`;commit 前列出暂存集,确认无关预存改动全部在外。
- 与本任务无关的工作区改动不碰不提交,向用户点名报告;用户自建/来源不明的文件只提示,不代提交。
- 运行会写仓的外部工具前,先把相关目录提交成干净 git 基线,工具改动即成可审可回退的 diff。
- 字面「提交所有」默认仍走排除纪律;仅当用户在被告知排除方案后强调式重申,才视为知情覆盖、全量提交。
- 分组提交后逐组核对 pathspec(文件改名产生的删除易被并入错组导致后组失败)。

## 工具

路径约定：先定位本 SKILL.md 所在目录，再从该目录解析 `scripts/...`；不要相对于进程 CWD 解析。

```bash
node scripts/xlsx-dump.cjs 手改版.xlsx > /tmp/a.tsv
node scripts/xlsx-dump.cjs 重生成版.xlsx > /tmp/b.tsv
diff /tmp/a.tsv /tmp/b.tsv   # 逻辑值对比,可选第二参数指定 sheet
```

输出行格式 `sheet!addr\tvalue\tformula\tnumFmt`。依赖 exceljs:`npm i exceljs`,或 `NODE_PATH=<含 exceljs 的 node_modules>` 运行。

## 延伸资料

- references/generator-template.md — exceljs 生成器范式模板(数据文件→生成器→xlsx、{formula,result} 双写、派生值实算)
- references/cascade-checklist.md — 级联七步详单、手改回捕 SOP、grep 误报判读清单、提交细则、对客场景加固
