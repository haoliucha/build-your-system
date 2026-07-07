---
name: prototype-handoff
description: This skill should be used when preparing a prototype handoff package for an AI design/prototyping tool in a To-B bid or delivery project — first reverse-engineering the receiving tool's input model to choose between a prompt+knowledge-base package (Form A) and a design-tokens+components package (Form B), locking compliance copy verbatim, calibrating host-platform visuals via screencast frame extraction and pixel sampling, and releasing multi-screen prototypes in P0/P1/P2 batches. Triggers on phrases like "原型交接包", "交接给 AI 设计工具", "prototype handoff", "给设计工具准备输入材料", "宿主视觉校正", "录屏抽帧", "分批生成原型", "设计交接".
version: 0.1.0
---

# prototype-handoff — 原型交接包

为 AI 设计/原型工具准备交接包。核心纪律:**先吃透接收工具的输入模型,再定交接物形态**——包不是给人看的文档,是喂给另一个工具的输入,做错形态等于白做。

## 第 0 步:研究接收工具,定包形态

动手前先回答:接收工具吃什么输入(文件上传?含图?稠密 prompt?tokens/组件代码)?它的概念分层(可复用品牌层 vs 一次性原型生成层各吃什么)?它自身设计能力强弱?调研方法见 references/receiver-input-models.md。

两种典型形态,**不可互换**:

| 形态 | 接收工具特征 | 包的主体 |
|---|---|---|
| A:prompt+知识库 | 吃文件上传(含图),稠密结构化 prompt 远胜模糊描述,自带设计 craft | master prompt + 全量真实文案 + 带借鉴注记的参考图板 |
| B:令牌+组件 | 读 tokens.css/组件库代码,面向可复用设计系统 | 设计令牌 + 组件规范 + 示例组件代码 |

反模式(实战翻车):对着吃令牌+组件的同步命令,喂简报+prompt 形态的包 → 只得到很薄的仅令牌系统。正确做法:识别出两条路径后分别建包,并向用户说明两包各服务品牌层与原型生成层、如何配合。

形态 A 的价值序:**内容完整的真实文案 > 稠密结构化 master prompt > 带借鉴注记的视觉参考图 > 逐像素规范**。设计令牌当护栏不当圣经——有 craft 的工具自己的判断常好于死抠数值。

## 合规文案:逐字锁定,绝不留给工具编造

AI 设计工具会自行编造貌似合理的界面文案。强合规行业(医疗/心理/金融/政务)的锁定语句——标准化量表/问卷题干、危机干预话术、免责声明、知情同意、监管固定措辞——必须在包内**逐字提供**并标注「逐字使用,禁止改写」;生成后对产物逐字核对。类别清单与核对法见 references/compliance-copy-lockdown.md。

## 宿主视觉:实测为准,不信官方 VI

反模式(踩过的最大坑):嵌入某宿主 App 的原型按官方 VI 假设深蓝大面积顶栏,实测 App 内渲染为更亮的蓝、二级页默认白顶栏蓝色仅作点睛,整体视觉方向跑偏。

正确做法:向用户要真实录屏 → 固定节奏抽帧 → 像素取样校正色值,得出「蓝是点睛不是底色」这类只能实测得出的结论;tokens 用双层令牌(`--host-*` 宿主 chrome 层 / 自有品牌层)隔离;真实参考帧直接入包。

## 长录屏抽帧:固定节奏 + contact sheet 两级阅读

固定节奏抽帧(默认每 3 秒一帧)+ 编号 contact sheet:先通读 sheet 建全局地图,再放大文字密集帧细读。**禁用运动检测去重(mpdecimate)**——滚动动画会击穿它,几十 MB 录屏炸出上千冗余帧。

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/prototype-handoff/scripts/extract-frames.sh"
bash "$S" frames <录屏.mp4> <帧目录> 3   # 固定节奏抽帧
bash "$S" sheet <帧目录> <sheet目录>     # 编号 contact sheet
bash "$S" pixel <帧.jpg> <x> <y>         # 像素 hex 取样
```

依赖 ffmpeg + ImageMagick 7(macOS:`brew install ffmpeg imagemagick`)。细节见 references/screencast-frame-sampling.md(与竞品调研类 skill 共用的方法片段)。

## 索要素材:附拍摄清单

向用户索要录屏/截图时随附拍摄清单,列全所需模块让对方一次录全;分析产出文末单列「本次没拍到、待补拍」的模块,避免多轮补拍。

## 多屏原型:P0/P1/P2 分批放行

几十屏原型按优先级分批让工具生成:P0 核心流程先出、审过再放行 P1/P2。一次生成全部会爆上下文,且跨屏一致性崩。分批计划写进包的 README。

## 交付核验:按用户真实打开方式跑最劣环境

交付 HTML/演示物前按用户实际打开方式核验:双击本地文件(file:// 协议下 SVG 可能不加载 → 嵌图换 PNG)、现场断网(CDN 依赖备本地兜底文件)。亲自双击/起服务打开并截图确认,不信「应该能开」。

## 延伸资料

- references/receiver-input-models.md — 接收工具调研法 + 形态 A/B 判定与配合
- references/package-a-template.md — 形态 A 的 7 文件包示例模板
- references/compliance-copy-lockdown.md — 合规锁定类别清单、标记法与核对
- references/screencast-frame-sampling.md — 抽帧+取样方法片段(跨 skill 共享)
