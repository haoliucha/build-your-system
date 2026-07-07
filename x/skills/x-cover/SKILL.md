---
name: x-cover
description: This skill should be used when the user wants to generate an X (Twitter) article cover image with one command — reads the article, distills a visual prompt, and produces a 2.5:1 cover via codex imagegen (gpt-image-2) full-image direct generation with Chinese text, plus aspect-ratio gate, 375px thumbnail, and QC. Triggers on phrases like "/x:cover", "给文章做封面", "生成 X 封面", "封面重出", "article cover", "make a cover for this article".
version: 1.0.0
---

# x-cover — X 文章封面一键生成

给任何 X 文章(Markdown)一键生成 **2.5:1 封面**:读文章 → 蒸馏画面 prompt → codex imagegen(gpt-image-2)**整张直出(含全部中文文字)** → 比例门禁 + 375px 缩略图 + 原图留档 → QC 报告。

## 为什么是这个形态(硬事实,别退回老路)

- **X 文章封面框 = 2.5:1**(CDN 实存 900×360)。非此比例上传会被 X 中心裁切,顶/底内容直接丢失。
- **gpt-image-2 支持任意 WIDTHxHEIGHT**(边 16 倍数、比例 ≤3:1),2.5:1 可直出;headless 下内置 image_gen 的 size 参数不透传,靠 prompt 描述"2.5:1 横幅构图"控比例(实测精确命中)。
- **整张一次性直出含文字 = 唯一路线**(gpt-image-2 CJK ~99%);禁事后本地叠字/SVG/渲染脚本。
- 出图纪律(禁 glow/带单位/单曲线/中文逐字/自查重出 ≤1 次)**由脚本注入**,不靠人抄——真源 = `scripts/cover-gen.sh` 的 gen 注入段。

## 4 条硬规则

| # | 规则 | 说明 |
|---|---|---|
| 1 | 绝不发布 | 只产出本地图片文件,不碰任何发布/上传动作 |
| 2 | prompt 只写画面内容 | 纪律句脚本注入,人工重复/改写纪律 = 破坏单一真源 |
| 3 | QC 不可省 | 单次生成有文字方差(实测出过单字错字),必须 Read 缩略图逐字核对 |
| 4 | 配额保护 | codex 报 usage/rate limit → 立即 STOP 报告;整体失败最多重试 1 次 |

## 工作流(6 步)

### ① 解析参数

`$ARGUMENTS` = `<文章.md 或文章目录> [风格/版式备注]`

- 参数是 **md 文件** → 文章目录 = 该文件所在目录(产物落 `<目录>/images/`)。
- 参数是 **目录** → 直接用;优先读其中 `publish.md` / `draft.md` / 唯一的 md。
- **无参数** → 从当前会话上下文找正在写的文章;找不到就问用户(仅此一问)。
- 其余文本 = 风格/版式偏好备注(如"暗色玻璃拟态""用对比表版式")。

### ② 读文章,蒸馏画面内容

从文章提取(这是本 skill 的核心智力活):

- **主标题 ≤7 字**(封面大字,不必等于文章标题,要的是钩子)。
- **副标一句**(375px 缩略图可读的下限来定字号感)。
- **主数字带单位**(如 `48,000+ stars`,没有就不硬造)。
- **单一图形钩子 = 文章核心观察的视觉化**(一张封面只有一个焦点;想不出说明文章观点不够锋利,如实告知用户)。
- **版式**(信息怎么摆),8 类速查:排行榜 / 大数字 / 趋势曲线 / 对比 / 数据网格 / 结构关系 / 标注拆解 / 清单。数据类文章先定版式再定皮肤。
- **配色皮肤**:用户备注优先;op-x 项目用 terminal 皮肤(青 #34dcf0 / 金 #ffd75e / 绿 #28c840 / 红 #ff5f57 / 深 navy 渐变 #13203a→#0b1322);其余默认深色科技风(深底 + ≤2 主色 + 1 强调色)。

### ③ 写 prompt 文件(只写画面内容)

按 `references/prompt-template.md` 的 A 骨架填空,写入临时文件(如 `/tmp/cover-prompt.txt`)。**不写**任何纪律句/尺寸声明(脚本会注入)。

### ④ 生成(2-5 分钟)

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/x-cover/scripts/cover-gen.sh" gen <文章目录> /tmp/cover-prompt.txt
```

脚本自动完成:纪律注入 → codex exec headless 直出 → 产物新鲜度校验 → 比例门禁(2.45–2.55,近轴 2.25–3.0 自动居中裁到精确 2.5:1,3:2 旧安全带图裁中央兜底)→ `images/cover.png` + `images/thumb-375.png` + 原图/旧封面留档。

### ⑤ QC(Read 缩略图逐项核)

Read `<文章目录>/images/thumb-375.png`,逐项:

1. 主标题 + 主数字清晰可读?中文**逐字**正确(生成方差会出错字)?英文/仓库名逐字符正确?
2. 无 glow/外发光/霓虹光晕?文字锐利实心?
3. 大数字带单位?曲线单条干净(不是散点+阶梯拼的伪图表)?
4. 单一焦点成立?

**硬伤**(乱码/错字/伪图表/glow/焦点崩)→ 修 prompt 重跑一次(仅一次);**微瑕**(字距/微偏移)→ 不重跑,如实报告。

### ⑥ 交付

报告:cover.png 路径 + 尺寸/比例 + QC 逐项结论 + 一句提醒:**X 上传封面会弹 2.5:1 裁切框,必须点「应用」;本图已是 2.5:1,应用 = 无操作裁切**。封面上印的数字/榜位是时效 peg,草稿滞留后发布前要重核。

## 兜底路径

- **headless 不可用**(codex 未装 / image_gen 不可用 / 无配额):把 `references/prompt-template.md` B 段全文 + 画面内容交给用户贴 Codex 桌面 app,出图后跑:
  ```bash
  bash "${CLAUDE_PLUGIN_ROOT}/skills/x-cover/scripts/cover-gen.sh" from <原图> <文章目录>
  ```
- **脚本自检**(改脚本后/怀疑环境坏):
  ```bash
  bash "${CLAUDE_PLUGIN_ROOT}/skills/x-cover/scripts/cover-gen.sh" selftest
  ```

## 已知坑(踩过的,别再踩)

- codex 想"先出底图再本地叠字"/写渲染脚本绕 → 注入段已硬禁,日志见此苗头即算失败。
- 要求精确像素值会让 codex 反复重试烧配额 → 注入段已改锁比例区间。
- 别信模型自报路径 → 脚本已做产物存在性 + mtime 新鲜度校验。
- `codex exec` 需 `--skip-git-repo-check` + `-c service_tier="fast"`(config 解析坑)→ 已内置。

## 依赖

codex CLI(≥0.142,headless 直出)+ 内置 imagegen skill(gpt-image-2)+ ImageMagick(`magick`)+ macOS `sips`。
