---
name: bid-research
description: Use when gathering evidence for a To-B bid or proposal — competitor teardowns, benchmark verification, screen-recording frame analysis, open-source license audits, structured research output, and multi-chain triangulation of major technical decisions. It governs how to collect evidence (adversarial review of finished drafts is a sibling skill). Triggers on phrases like "竞品调研", "竞品拆解", "对标分析", "录屏拆解", "录屏分析", "开源选型", "license 审查", "调研取证", "投标调研", "证据链验证".
---

# bid-research — To-B 投标调研取证

管「怎么取证」;成稿核查归 review 类 skill,不在本 skill 范围。写给执行调研的宿主 agent,聚焦公开检索、一手素材、录屏拆解、license 审查、证据链的程序性纪律。

## 三条铁律

| # | 铁律 | 一句话 |
|---|---|---|
| 1 | 无一手素材不臆写 | 公开信息近零 → 停下报阻塞索要素材,绝不基于近似名产品或猜测硬写 |
| 2 | 断言以查证为界 | 只落可证事实,推断性断言不落纸 |
| 3 | 亲测 > 转述 | 子 agent 结论矛盾、链接死活、UI 细节,一律以亲测为准 |

## 1. 公开信息近零 → 索要一手素材(高频翻车点)

反模式:全网检索目标竞品只命中名字相近的无关产品,仍硬写分析 → 整篇失真,比空白更害人。
正确做法:停下,向用户声明这是真实 blocker;索要录屏/截图,并直接附上 `references/shooting-checklist.md` 的拍摄清单模板;拿到素材后基于实测帧写作;文末单列「录屏没拍到、需补拍」清单。一段两三分钟的完整录屏足以支撑整篇拆解。

## 2. 对标/竞品先实证,再定打法

第一步核实运营主体、商业模式、真实护城河——护城河常是合规资质而非表面 AI 能力。不采信需求文本的印象式定性:写着「轻量打卡小工具」的对标,实证后可能是一家老牌厂商的企业服务获客漏斗。纠偏结论以「重要纠偏」显式标出——它可能颠覆整个方案重心。竞品普遍语焉不详的合规空白,可反做己方先行完成的稀缺信任卖点列 P0,以公开执法先例佐证必要性。查证路径见 `references/competitor-verification.md`。

## 3. 攻击话术自检 +『别说』红线

每条攻击话术落纸前过三问:可查证吗(只允许「公开渠道查无备案/声称」句式)/ 会自打脸吗(自身口径是否同款短板)/ 对方该维度是否反而更强。过不了的列入『别说』红线,随交付物单列。典型红线:不断言对方套壳、不用备案攻击、不引战资质对比。

## 4. 录屏拆解

固定节奏抽帧 + 带帧号标签的 contact sheet,建「帧号→时间」映射:

路径约定：先定位本 SKILL.md 所在目录，再从该目录解析 `scripts/...`；不要相对于进程 CWD 解析。

```bash
bash scripts/extract-frames.sh <录屏.mp4> <输出目录> [fps] [cols]
```

要点(详见 `references/screen-recording.md`):

- **别用帧差/场景检测去重**:滚动与转场动画会击穿帧差法(阈值高了漏真切换,低了爆冗余),固定节奏(默认 1fps)最稳。
- macOS 下 `montage` 标签不显式指定字体文件路径会**静默不渲染帧号**(脚本已内置);**先打开并检查第一张 sheet 的可读性,再批量读取**。
- contact sheet 只做定位;关键画面回读 `frames/` 下全分辨率原帧锁定精确文案。
- 主动追竞品在安全/合规关键时刻(如高风险信号)的真实处理路径——录屏可实证的短板是方案最有力的正面差异化打点;与不可实证的架构猜测严格分区(不可实证的断言最终会被全删,别写)。

## 5. 链接亲测与自动化采集止损

- 案例链接逐一亲自打开验证并截图;已下线的标『借鉴形式勿引链接』;区分「可实测清单」与「仅借鉴形式」两档。
- 人机验证墙会指纹识别一切自动化附加的浏览器(自动化启动、CDP 附加、真人在自动化窗口里手点,全都无效)。**两种技术路径失败即止损**:禁止伪造数据;用既有旧资产兜底;例外显式列入交付报告;给用户可直接执行的手工采集说明(要什么内容 + 几种截法 + 交回方式)。
- 营销 H5 的标题/按钮常绘制在 canvas 上、CSS module 类名逐屏变化 → 文本选择器与固定类选择器都不可靠;改坐标 tap,或每屏 dump DOM 取实际类名;视口外按钮需强制点击。

## 6. 开源选型:穿透 license 继承链

仓库协议宽松 ≠ 权重可商用。逐项核查:微调权重继承底座模型协议;代码/数据集/权重许可各自独立;警惕 GPL 开核套路。常见结局:真正可商用复用的只有数据集与方法论,而非权重。审查步骤与判定决策树见 `references/license-audit.md`。

## 7. 重大选型三角验证

重大技术路线用多条互相独立的证据链互证后再定论——典型组合:学术实证 + 法规条款 + 业界工程实践;明示各链作用域与 caveat。把可溯源/可删除等合规属性当架构选型的一等依据,不是事后附加。大范围调研拆多路并行子任务(方法论/开源生态/竞品),各路独立完成后交叉验证,单路结论不直接进报告。

## 8. 结构化输出 schema

每条量化结论按六字段落纸:**区间 / 典型值 / 主驱动 / 来源 / 置信度 / caveat**。联网检索到的金额只取定性(量级/趋势),不当精确输入;查不到的显式留白并附核验路径。模板与示例见 `references/research-schema.md`。

## 9. 方案前解剖原始工件

承诺任何卖点前,先解剖客户的原始工件与真实样本(文件内部结构、实拍凭证形态)。解析库全挂时把 xlsx 按 zip 解压直读 XML。真实瓶颈往往藏在原始证据里而非需求描述里——「自动识别」类诱人卖点,在亲眼看到揉皱、褪色、倒置的实拍件之前,谁承诺谁埋雷。

## 延伸资料

| 文件 | 内容 |
|---|---|
| `references/shooting-checklist.md` | 索要一手素材时直接发给用户的拍摄清单模板 |
| `references/screen-recording.md` | 录屏抽帧 / contact sheet / 取证三档边界详解 |
| `references/competitor-verification.md` | 运营主体查证路径 +『别说』红线生成法 |
| `references/license-audit.md` | license 三层分离审查与商用判定决策树 |
| `references/research-schema.md` | 六字段 schema 定义、示例、三角验证登记表 |

## 依赖

`scripts/extract-frames.sh` 需 ffmpeg + ImageMagick(macOS:`brew install ffmpeg imagemagick`);contact sheet 字体默认取 macOS 系统字体,其他平台用 `FONT=/path/to/font` 环境变量传入。
