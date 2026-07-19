---
name: diagram-pdf-pipeline
description: Use when producing diagrams for To-B bid/delivery documents and exporting them as Chinese-language PDFs — covers diagram toolchain selection (mermaid is banned with root cause), spec-driven single-source SVG/PNG generation, headless Chrome PDF export with CJK-first font stacks, inline 2x PNG embedding, bookmark/outline injection, and page-by-page visual acceptance. Triggers on phrases like "出架构图", "交付物配图", "画流程图/分层图", "导出 PDF", "PDF 中文丢字/标点错乱", "PDF 加书签大纲", "mermaid 中文丢失", "图表管线".
---

# diagram-pdf-pipeline — 交付物图表与中文 PDF 导出管线

To-B 投标/交付物的配图与中文 PDF 导出是强耦合的一条管线:CJK 字体问题贯穿两域,SVG 滤镜会崩打印,图的编号被 PDF 索引硬引用。按「出图 → 导出 → 验收」三段执行,反模式全部来自真实翻车。

## 一、出图

**锁方案前先全网对比调研,取优胜者。**
- 反模式:直接 fork 自己熟悉的既有生成器铺开全量。某 To-B 投标项目中曾被叫停,要求重新调研;结论反直觉——风格层已达标,问题只在布局层。
- 正确做法:列出外部候选与内部方案,逐项对比能力/风险/丢失项 → 取优胜者或 Hybrid → 先在最复杂的一张图上端到端试点(spec → 渲染 → 嵌入 → PDF 页),通过再批量。批量后仍逐张打开并检查(曾抓出一张拓扑被画成串行链)。

**把图的质量拆成风格层与布局层两个独立问题。** 连线交叉/重叠是布局问题,换自动布局引擎(如 elkjs)即可根治,不必整体换工具丢掉已验证的 CJK/矢量/多页能力。流程图走自动布局;分层/分区图按 band 手摆(构造上零重叠)。

**绝不用 mermaid 出交付物配图。** 根因:浏览器打印 PDF 时 mermaid 不内嵌 CJK 字体,中文节点标签整体丢失——HTML 预览里看着正常,PDF 里全部架构图中文变空白,自检极易漏过。改用可栅格化管线:drawio 或程序化 SVG → PNG 内嵌。

**每张图 = 一份代码 spec,同源出三件套**(展示 SVG / 内嵌用 2x PNG / 可编辑源)。改图只改 spec,一键重出全量。GUI 里手改过的文件用语义级 diff 把改动反移植回 spec,绝不让 GUI 文件变成数据源。

**程序生成 XML 图源时,属性值内的富文本必须整体转义**(裸 `<` 和引号会使整个 XML 非法、文件打不开),交付前跑 `xmllint` 校验。

**编号纪律**:向既有编号体系插新图,选纯新增编号(如「图 0」),绝不 renumber——重编会级联破坏正文嵌入、图索引和跨文档硬引用。两张近似总览图并存时,核实超集关系后以超集为准、退役另一张(删 spec + 删产物),收口单一事实源。

## 二、导出

**字体栈必须 CJK-first。** 根因:Latin-first 栈按字形逐个匹配,汉字在西文字体里 miss 后回退正常,但全角标点(如全角括号/冒号)在部分西文字体里有字形,直接取错——症状是"汉字正常、仅标点坏"(括号变弧线、冒号上浮),极难定位。且引擎回退策略不同:Chrome 能正确回退,部分排版引擎不能。修复必须落到全局导出配置/样式源头,不是只重出当次文件。

**headless 出中文 PDF 前,先探测该环境实际可渲染的 CJK 字体。** 系统惯用字体名在 headless 环境不一定可解析(正文中文整页空白的典型根因)。跑字体探测页逐一实测,字体栈以实测可用的 CJK 字体打头、以能兜中文的通用族收尾;字体本地化,不依赖外链 CDN(曾卡死导出)。

**嵌图一律内联 2x PNG,不用带滤镜的内联 SVG。** 根因:Chrome printToPDF 对含 blur 等 filter 的内嵌 SVG 直接报 Printing failed。SVG 与 drawio 保留作可编辑源,进打印面的全部位图化。

**长文档 PDF 默认带书签大纲**(Chrome 打印引擎天然不写 outline),用本 skill 的导出脚本并固化进构建链:

路径约定：先定位本 SKILL.md 所在目录，再从该目录解析 `scripts/...`；不要相对于进程 CWD 解析。

```bash
node scripts/add-outline.cjs <input.html> <output.pdf>
```

依赖 playwright-core + 本机 Chrome,`page.pdf({ outline: true, tagged: true })` 从 h1-h6 自动生成层级书签。若需为已有 PDF 按文本搜索注入书签:用只前进的有序游标,防目录同页与正文交叉引用错锚(短标题如「附录」最易撞)。

**导出反复失败按二分定位**:极简 HTML 验证打印本身可用 → ASCII 路径排除编码 → 内容二分锁定崩溃源。不要连环猜方向(headless 模式、中文路径都曾是误猜)。

## 三、验收

**静默失败会留陈旧产物冒充新版。** 反模式:看到 PDF 文件生成就报完成——曾有导出报错只输出一个裸 `}`,PDF 停在旧版,直到页面出现源文件里已删除的旧图题才暴露。正确做法:逐字核对导出日志的成功行 + 抽验一处本次新改的内容确在 PDF 中。

**终稿逐页人工目检;构建成功与 grep 清零不能替代亲眼看。** 逐图核对:中文完整、边线路由正确(横穿/误连/汇入点——生成器里死三元这类 bug 只有肉眼能兜)、图不跨页、无重复标题。文本工具数页码会漂,以渲染为准:直接渲染嵌图所在页及相邻页确认。

**图修复走固定闭环**:按截图定位问题 → 读生成器源码找几何根因 → 改 spec → 重渲全部产物 → 逐张目视复核。不跳最后一步。

竖屏截图入 A4 要限高约半页并居中,防跨页割裂;内部草稿的 ASCII 图参差不做脆弱手工重排,像素级精修只花在对外正式图上。

## 延伸资料

- `references/diagram-pipeline.md` — 出图细节:选型对比流程、spec 同源三件套、布局几何根因、XML 转义、编号与收口案例
- `references/pdf-export-cjk.md` — 导出细节:CJK-first 根因机理、字体探测页写法、书签注入算法、引擎 trade-off、全角边界强调标记修复
- `references/acceptance-checklist.md` — 验收清单:逐页目检项、静默失败排查、页码漂移处理、修复闭环

## 环境说明

经验取自 macOS + 系统 Chrome(playwright-core `channel: 'chrome'`)。Linux CI 等无桌面环境下,字体探测更是必做——可用 CJK 字体集与桌面机差异更大。
