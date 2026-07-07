---
name: deai-writing
description: This skill should be used when the user wants to detect and strip AI-flavored writing ("AI 味") from Chinese To-B bid/deliverable documents — proposals, requirement analyses, research reports, presentation copy. Runs a bundled 18-category regex tell scanner for gross evidence, layers semantic review to net out false positives and catch structural tells (paragraph-ending uplift, parallel headings, anthropomorphic diction), then rewrites under a zero-information-loss rule with adversarial diff verification and client-facing acceptance checks. Triggers on phrases like "去AI味", "去味改写", "AI味检测", "扫一下AI味", "这段太像AI写的", "交付物去AI痕迹", "检查AI味密度", "deai writing".
version: 0.1.0
---

# deai-writing — 投标交付物去 AI 味

对中文 To-B 投标/交付物(方案书、需求分析、调研报告、PPT 文案)做去 AI 味改写。与通用 AI 检测工具的区别:通用工具输出「像不像 AI」的分数;本 skill 关心**评审人视角下的可信度损伤**——投标语境里,误删领域术语、压平排名标记比留下几个 buzzword 更致命。全程红线:**信息零损失,只改外壳**。

## 第一步:双层测量,拿净口径再动手

先跑正则毛统计取证:

```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/deai-writing/scripts/aiflavor-scan.cjs" docs/ 封面.html --json /tmp/aiflavor-stats.json
```

接收文件/目录参数(目录递归 .md/.html),输出 18 类 tell 的每文件计数、每千 CJK 字密度、分类矩阵与带行号取证示例。

然后叠加语义判读:毛命中约**六成以上是正当用法**(引用括注、术语加粗、表格勾选符、并列版式点号都会命中),逐文档扣掉误报;再补录正则抓不到的**结构性 tell**——段末口号升华、对仗/排比式标题、拟物化/道德化词汇、过度自证堆砌。得到净口径后才决定动哪里。

**反模式(高权重)**:毛密度 70+/千字直接照单去味 → 大量误伤正当学术引用与版式符号。实测净密度仅约毛数三分之一。别追毛密度指标本身,毛数只做取证与前后对比。

## 第二步:先砍性价比最高的两刀

1. 删段末口号式升华句(收束时拔高到愿景/价值观的那句);
2. 清拟物化/道德化词汇(把系统说成生命体、把工程选择说成品德)。

这两刀近零信息损失,却去掉最强指纹。其余 tell 按净口径酌情处理,导航价值高的版式符号可保留。

## 第三步:改写,守三条红线

- **信息零损失**:排名/强弱标记(双勾 vs 单勾)、领域术语、数字与单位、引用出处一律不动。
- **义务强度变更单独申报**:「必须→建议」「应→可」级别的口径变化不得混入「语义等价」的自称,单独列表交作者拍板(这是与对抗审校流程的接口)。
- **过度自证也是 AI 味**:防御性定语正文重复多次=空话堆砌;证据在表格内具体引用一次,免责尾巴全文只留一处。

## 第四步:对抗 diff 复核(必做,勿信改写者自评)

由与改写者**不同的实例/子代理**(不带改写会话上下文)对 git diff 逐段专查四类:排名标记被压平、正当术语被系统性软化、生造缩略词、替换旧比喻时新引入的比喻。

**反模式(高权重)**:改写 agent 自称「语义等价」,对抗复核抓出上述四类各一处真问题,逐项回修。

## 第五步:客户向验收(grep 清零)

- 禁「甲方/乙方」合同式称谓:要主语用「我们」,纯所有格直接删,归属用「完全自有/自主可控」。`grep` 清零才算过。**反模式(高权重)**:全套交付物数十处「甲方」,被用户判为「太见外太生硬」。
- 术语/量表/法规缩写首现给定义+联网核实的 reference;不确定宁可不加。
- 标题/目录/封面脱括注须自足:正文靠括注澄清的词在标题会被读成更强主张。
- 按转发链条的终端读者写:直接收件人常会转给真正评审人。

## 延伸资料

- `references/measurement.md` — 18 类 tell 逐类误报特征、结构性 tell 详解、脚本输出解读
- `references/rewrite-protocol.md` — 零损失清单、义务强度申报、对抗复核操作、口述经历转写四动作
- `references/acceptance.md` — 称谓/引用/标题自足/终端读者的验收清单与 grep 命令

## 依赖

Node.js ≥ 16(脚本零第三方依赖);对抗复核依赖 git diff。
