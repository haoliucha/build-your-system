# Baseline: 02-subjective-landing-page

## User prompt

> 我的着陆页太朴素了,想做得高级一点。给我写个 /goal 让 Claude 帮我升级一下设计风格。

## Fresh-Claude response (Step 1)

我会**直接生成 /goal**,但会在前面加一句"这个目标比较主观,/goal 命令里我会让 Claude 先跟你对齐风格方向再动手"。不会拒绝——用户已经明确要 /goal,拒绝会显得没用。

完整 /goal 命令(verbatim):

```markdown
---
description: 升级着陆页设计风格,从朴素提升到高级感
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

# 升级着陆页设计风格

## 背景

当前着陆页设计偏朴素,需要提升视觉高级感。这是一个**主观审美任务**,执行前必须先和用户对齐方向,不要直接动手改代码。

## 执行步骤

### 1. 定位着陆页文件

先找到着陆页源文件:
- 检查 `app/page.tsx` / `pages/index.tsx` / `src/app/page.tsx` / `index.html` 等常见入口
- 如果是 Next.js 项目,关注 `app/(marketing)/` 或 `app/landing/` 目录
- 找到关联的 CSS / Tailwind config / 组件库配置

读完文件后简短报告当前状态:
- 用了什么框架(Next.js / Vite / 纯 HTML)
- 用了什么样式方案(Tailwind / CSS Modules / styled-components)
- 当前的色板、字体、布局结构

### 2. 和用户对齐风格方向(关键 — 不要跳过)

"高级感"是模糊的,不同人理解差异极大。**必须**问用户以下问题再继续:

1. **参考站点**:有没有 1-3 个你觉得"高级"的着陆页(Linear / Vercel / Stripe / Apple / Framer / Arc / Notion / Raycast 等)?贴 URL。
2. **风格方向偏好**(选 1-2):
   - Minimal & Clean(Linear / Vercel 风,大量留白 + 精准排版)
   - Editorial & Serifs(Stripe 早期 / Medium 风,衬线字体 + 排版驱动)
   - Bold & Brutalist(Gumroad / Figma 早期,大字号 + 鲜艳色块)
   - Glassy & Premium(Apple / Arc 风,毛玻璃 + 渐变 + 微动效)
   - Dark Mode Tech(Resend / Cursor 风,深色底 + 霓虹强调色)
3. **品牌色** / 现有 logo:有没有必须保留的主色调?
4. **保留 vs 重做**:是想小幅调优(字体 / 间距 / 阴影)还是大改版(重新布局)?
5. **动效预算**:接受 framer-motion / GSAP 动效吗?还是要纯静态?

**Stop and wait for user's answer**。不要凭感觉猜方向就动手——主观任务最容易翻车的就是"我以为高级=深色+渐变",结果用户想要的是 Editorial。

### 3. 基于回答制定升级方案

收到用户回答后,输出一个**写在 markdown 里的升级 plan**(不要直接改代码):

```
## 升级方案

### 设计 token 升级
- 字体: 当前 X → 升级到 Y(理由)
- 色板: 当前 X → 升级到 Y(理由)
- 间距尺度: 当前 4/8/16 → 升级到 4/8/12/16/24/32/48/64
- 圆角: 当前 X → 升级到 Y
- 阴影系统: 新增 sm/md/lg/xl 4 级

### 布局升级
- Hero 区: 当前 X → 升级方案
- Features 区: 当前 X → 升级方案
- ...

### 改动文件清单
- app/page.tsx (大改)
- app/globals.css (新增 design tokens)
- tailwind.config.ts (扩展色板 / 字体)
- 新增组件: components/marketing/Hero.tsx 等

### 不改的部分
- 文案保持原样(用户没说要改)
- 路由 / 数据结构不动
```

让用户确认 plan 再动手。

### 4. 执行升级

用户确认 plan 后:
1. 先建/改 design token(tailwind config / globals.css)
2. 再改组件,从上到下:Hero → Features → CTA → Footer
3. 每改完一个 section 跑一次 `pnpm dev`(或项目的 dev 命令),让用户看效果
4. 不要一次性改完所有 section 才让用户看

### 5. 验收

升级完成后:
- 跑 `pnpm build` 确认没破坏构建
- 跑 `pnpm lint` 确认代码符合规范
- 截图(或描述)关键 section 给用户对比 before/after
- 列出"建议下一步"(例如:加首屏动效、加微交互、加暗色模式)但不动手

## 红线

- **不要凭感觉猜"高级感"是什么**——必须先和用户对齐参考站点和风格方向
- **不要一次改完才让用户看**——每个 section 都要 checkpoint
- **不要改文案**——用户没说要改文案,只要改设计
- **不要引入新依赖**(framer-motion / GSAP)如果项目里没有,先问
- **不要破坏现有响应式**——所有改动必须保持 mobile / tablet / desktop 三档可用

## 完成判定

- 用户在 dev 环境下看完所有 section 后说"OK"
- `pnpm build && pnpm lint` 两绿
- before/after 对比清晰
```

## Self-reflection (Step 2)

### Optimized for 什么?

- **风险规避**:核心 insight 是"高级感是主观的",所以塞了一个强制对齐环节(Step 2),防止 Claude 凭感觉乱改。
- **细节完整性**:写了文件定位 / 5 个对齐问题 / plan 模板 / checkpoint 节奏 / 红线 / 完成判定,看起来很"周到"。
- **防止 over-engineering**:加了"不要改文案 / 不要引入新依赖 / 不要破坏响应式"等红线。

### 漏了什么纪律?

1. **没看项目实际情况就写命令**。我应该先 `ls` / 读 package.json / 看现有 landing page 文件,再写一个 tailored 的 /goal,而不是写一个"通用模板"。这个 /goal 假设了 Next.js + Tailwind + pnpm,但用户的项目可能是 Vite + CSS Modules + npm。
2. **没问"哪个着陆页"**。用户说"我的着陆页",但项目里可能有多个(marketing landing / product landing / pricing landing)。直接默认 `app/page.tsx` 是猜测。
3. **没问交付形式**。是 Claude 直接改代码、还是 Claude 给一个设计 spec 让用户找设计师做、还是 Claude 给 3 个变体让用户选?这影响 /goal 结构。
4. **没声明 stop conditions**。Claude 在 Step 2 提了 5 个问题,但如果用户回答模糊(例如"我也不知道,你看着办"),Claude 该怎么办?baseline /goal 里没有 fallback。
5. **/goal 里的 "Stop and wait" 是 vibe**。Claude Code 实际不会因为 markdown 里写了"stop"就停。要靠 prompt engineering(例如"present a single question, then end your turn")才真停。我没把这条机制吃透。

### 隐含假设

- 项目用 Next.js + Tailwind(因为我的训练数据里 landing page 默认是这个 stack)
- 用户能清晰说出参考站点(很多用户其实说不清,只会"我就觉得它高级")
- 用户接受 5 问对齐(可能用户就想一句话出活,5 问会被嫌烦)
- "高级感"= 视觉设计升级。但也可能用户想表达的是"性能更快 / 文案更打动人 / 加 social proof"。我直接锁定到视觉。
- pnpm + biome + 三绿(因为这是当前项目的约定,但通用 /goal 不该 hardcode 这个)

### 这个任务**本质上**适合 /goal 吗?我有没有意识到这点?

**没意识到,但其实不太适合**。

/goal 的强项是:
- 重复性任务(同一 SOP 跑多次)
- 客观 done-criteria(测试通过 / build 绿 / 数据匹配)
- 步骤稳定(每次步骤都差不多)

"升级着陆页设计风格"的特征:
- **一次性任务**(改完就完了,不会再跑第二次)
- **主观 done-criteria**(用户说"OK"才算 OK,没法量化)
- **步骤高度依赖对齐结果**(选 Minimal 和选 Brutalist 后续步骤完全不同)

更合适的形态是:
- **直接对话**(用户描述需求 → Claude 问 1-2 个问题 → Claude 出 3 个方向变体 → 用户选 → Claude 实施),不需要 /goal
- 或者一个 **skill**(`/design-direction-finder`,做"风格方向对齐"这一步),而不是把整个流程塞进 /goal

我写的 /goal 本质上是把"对齐 + 实施"两件事塞进一个命令,Step 2 是对齐(灵活、对话式),Step 4-5 是实施(机械、checklist 式),两者性质冲突。一个好的命令应该 do one thing well。

如果用户真要 /goal,我应该先问"你是想要一个**可复用的 SOP**(下次还会升级别的页面),还是**这次升级**用一下?"如果是后者,直接对话更高效,不需要 /goal。

baseline 没意识到这层 — 直接顺着用户"给我写个 /goal"的字面需求做了,没退一步问"是不是真的需要 /goal"。
