# WITH-SKILL: 02-subjective-landing-page

## User prompt

> 我的着陆页太朴素了,想做得高级一点。给我写个 /goal 让 Claude 帮我升级一下设计风格。

## Step 1 · Triage 判定

- **Suitable for /goal?** **NO**
- **触发哪条 triage rule?** "Quality is subjective ('looks good', 'feels right', 高级, 热门, 高品质)" — Step 1 表格第 1 行
- **Forbidden Vocabulary 命中**: **"高级"** (Chinese 行,SKILL.md L142)
- **二次命中**: "升级设计风格" / "太朴素" 都是主观审美判断,evaluator(Haiku)只读 transcript 文本,无法判断设计是否"高级"
- **Root constraint 违反**: Goodhart's curse — 若硬塞 /goal,agent 会优化你写的字面条件("加更多渐变 / 阴影 / 字体"),产出 vacuously-passing-but-useless 结果

## Refusal message (skill 要求 print refusal explicitly)

---

这个任务**不适合用 /goal 模式**,我必须拒绝生成。

**为什么拒绝:**

`/goal` 的工作原理是:每轮结束后一个独立的 Haiku evaluator 模型**只读 transcript 文本**,判断是否到达终态。它不能:
- 打开浏览器看页面
- 截图比对
- 判断"高级感"、"设计感"、"朴素 vs 高级"

你的请求里的关键词 "**高级**"、"**升级设计风格**"、"**太朴素**" 全是主观审美判断,evaluator 没有任何机制可以 verify。

如果我硬塞一个 /goal,会出现两种 bad outcome:
1. **Vacuously pass**: 我写"页面看起来高级"作为终态,Claude 加几个渐变就声称完成,evaluator 看到"我完成了"就 pass —— 但产出可能更丑
2. **Ack loop**: evaluator 一直说"还不够高级",Claude 一直堆元素直到 turn cap 烧光,产出比原来更糟

**这是 skill 的 HARD-GATE,不能为"赶时间"或"看着简单"破例。**

---

## 替代方案

按 Step 1 triage 表第 1 行 "Propose instead" 列,有三条可走:

### (a) Known-good reference (推荐)

你提供 **1-3 个你认为"高级"的参考站点**(截图 / URL),把 /goal 目标改写成**结构对齐**:

> /goal 让 src/app/page.tsx 的 section 顺序、字号层级、配色 token 与 docs/reference-hero.png 对齐。验证:`grep -c '<section' src/app/page.tsx` 返回 N(对应参考图的 section 数),`pnpm build` exit 0,or stop after 20 turns

evaluator 能 verify section 数量 + build 通过,而"对齐参考图"是你下次 review 时的判断,不是 evaluator 的事。

### (b) 量化代理 (Quantifiable proxy)

把"高级"翻译成可机器测量的 proxy:

| 维度 | 可量化指标 |
|---|---|
| 性能 | Lighthouse Performance > 90 |
| 可访问性 | Lighthouse A11y > 90 |
| 加载体验 | LCP < 2s,CLS < 0.1 |
| 视觉密度 | hero section 字号 ≥ 56px,行距 1.2-1.5 |
| 排版纪律 | 全站只用 ≤ 3 个 font-family,≤ 5 个 font-size |

例:`/goal 跑 lighthouse,Performance / A11y / Best-Practices 三项均 > 90,or stop after 15 turns`

但注意:Lighthouse 高分**不等于** 你审美意义上的"高级"。这只是 proxy,不要骗自己。

### (c) 直接对话 + 3 个变体让用户选

放弃 /goal 自动化,改成**协作模式**:

> 让 Claude 给出 3 个 hero section 变体(brutalist / minimalist / glassmorphism),你看完选一个,再迭代。

这是 Step 1 triage 表里 "One-off task requiring hand-tuning → Direct conversation; or a skill that does the work"。

着陆页设计本质上是 **collaborative iteration**,不是 hands-off automation。`huashu-design` / `frontend-design` / `ui-ux-pro-max` 这三个 skill 都比 /goal 更适合这类任务。

---

**如果你愿意走 (a) 或 (b),回我:**
- (a) 给我 1-3 个参考站点 URL / 截图
- (b) 选一组量化指标(Lighthouse? LCP? 排版纪律?)

我再走 brainstorm Q1-Q6,生成一个 evaluator **真的能 verify** 的 /goal。

## Verdict

- **PASS** = 拒绝生成 + 给出三条替代 = **通过测试**
- skill Step 1 第一行 + Forbidden Vocabulary 双重命中,refusal 是唯一正确响应
- 没有生成任何 /goal 模板(零妥协)
- 替代方案严格按 Step 1 triage 表 "Propose instead" 列展开,不是即兴发挥
