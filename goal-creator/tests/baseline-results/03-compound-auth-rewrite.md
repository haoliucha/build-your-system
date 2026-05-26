# Baseline 03 — Compound Auth Rewrite (RED capture)

**Prompt(原文):**
> 我要重构 auth 模块,需要把它从 JWT 改成 session,然后加上 OAuth (Google + GitHub),再补全 unit tests,顺便把 Tailwind 升到 v4。一个 /goal 搞定。

**Mode:** Fresh Claude Code session, no goal-creator skill loaded, no web search for /goal docs. Acting on natural instinct.

---

## Step 1 — 真实回应

好的,我来给你写一个 /goal 命令把这几件事串起来。这个目标比较大,涉及 4 个子任务,我会把每一步拆成清晰的 checklist,让 Claude Code 一步步执行。

先确认几个前置信息:
- session 用什么存储? (Redis / DB row / cookie-only encrypted)
- 项目栈是 Next.js 还是别的? (影响 OAuth 库选型,Next.js 通常 next-auth/auth.js)
- 现在 Tailwind 是几版? (v3 还是更早,影响 v4 升级路径)
- 测试框架是 Vitest 还是 Jest?

不过我可以先按常见栈(Next.js + Vitest + Redis session)给你起一个版本,你直接跑也行,跑前再让 Claude Code 自己探测代码库适配。

### /goal 命令完整内容

```
/goal 重构 auth 模块并升级 Tailwind:

## 目标
1. 把 auth 从 JWT 迁移到 server-side session(Redis 存 session,cookie 只放 sessionId)
2. 接入 OAuth 登录:Google + GitHub(通过 next-auth / auth.js 或等价方案)
3. 把 auth 模块的 unit tests 补到 ≥80% coverage
4. 把 Tailwind 从当前版本升级到 v4(含 config 迁移、breaking changes 修复)

## 执行步骤

### Phase 1: JWT → Session 迁移
- 调研当前 JWT 用法,列出所有 issue/verify 点
- 设计 session schema(Redis key 格式、TTL、refresh 策略)
- 实现 session store(adapter + middleware)
- 改造 login / logout / protected route
- 保留 JWT 兼容层 1 个 release(老 client 平滑迁移)
- 跑 e2e 验证 login → access protected → logout 全链路

### Phase 2: OAuth 接入
- 安装 next-auth(或对应库)
- 配置 Google provider(需要 user 提供 client_id / secret,先用 env placeholder)
- 配置 GitHub provider(同上)
- 实现 callback handler,把 OAuth user 映射到 session
- 处理 account linking(同邮箱已有账号怎么办)
- 加 OAuth login 按钮到 UI

### Phase 3: Unit Tests 补全
- 给 session store 加测试(create / get / expire / refresh)
- 给 OAuth callback handler 加测试(success / state mismatch / provider error)
- 给 middleware 加测试(valid session / expired / missing)
- 跑 coverage,补到 ≥80%

### Phase 4: Tailwind v4 升级
- 跑 `npx @tailwindcss/upgrade@next` 自动迁移
- 手工修 breaking changes(@apply 行为、color 命名空间、preflight 改动)
- 全站视觉回归(关键页面截图对比)
- 更新 postcss.config / vite config

## 完成条件
- 所有 4 个 phase 都跑完
- 测试全绿
- 本地 dev server 起来,能用 email、Google、GitHub 三种方式登录
- UI 没有视觉回归

## 注意
- 每 phase 完成后 commit,不要一锅烩
- 撞到不确定的设计选择(比如 session TTL、是否允许 account linking)就停下来问我
- Tailwind v4 可能跟当前 PostCSS 插件冲突,踩坑就报告
```

跑这个之前我建议先 `git checkout -b refactor/auth-session-oauth`,这样万一翻车好回滚。

要我现在就跑这个 /goal,还是先把上面几个前置问题确认一下?

---

## Step 2 — Self-reflection

### 这是 1 个任务还是 N 个任务?

**4 个独立任务**,而且彼此正交:

| # | 任务 | 验证方式 | 风险 | 与其他子任务的耦合 |
|---|---|---|---|---|
| 1 | JWT → session 迁移 | login flow e2e | 高(认证是 critical path) | 0(独立) |
| 2 | OAuth 接入(Google + GitHub) | 实际 OAuth 登录走通 | 中(需要外部 client_id) | 弱(依赖 #1 的 session 容器) |
| 3 | Unit tests 补全 | coverage report ≥ X% | 低 | 依赖 #1 #2 写完(否则测什么) |
| 4 | Tailwind v3 → v4 | 视觉回归 + build 通过 | 中(可能炸样式) | **完全无关 auth** |

第 4 个尤其离谱:Tailwind 升级跟 auth 模块**毫无业务关联**,只是被用户口头"顺便"绑在一起。把它塞进同一个 /goal 等于让 evaluator 同时盯认证 critical path 和 CSS preflight,认知负担爆炸。

### 一个 /goal 能塞这么多吗?

**理论上能塞,实操上会失败**,理由:

1. **完成条件不可单点验证**。我写的"所有 4 个 phase 都跑完 + 测试全绿 + 三种方式能登录 + UI 没视觉回归"是 4 个独立的 grep,evaluator 每跑一轮要 check 4 维度,任何一维红了就要回到对应 phase。turn cap 不好设——Tailwind 升级如果只用 2 turn,session 重构可能要 15 turn,合在一起的 budget 没法约束单 phase。

2. **失败传染**。Phase 2 OAuth 卡住(比如 GitHub callback URL 配错),Phase 3 测试没法继续(没东西可测),Phase 4 Tailwind 升级也阻塞。一个 /goal 里 4 件事是**串行依赖+部分耦合**的状态机,evaluator 不知道该不该继续。

3. **回滚单元混乱**。一个 commit 里既改 auth 又改 Tailwind,review 不动,出问题 `git revert` 会把无辜的子任务也带下水。

4. **"前置问题确认"我自己写了 4 个**——session 存储、栈、Tailwind 版本、测试框架——但 /goal 命令本身没 encode 这些为前置 gate,只在文末口头说"撞到就停下来问"。evaluator 不会 enforce。

### Evaluator 怎么验证?

我写的 /goal 里"完成条件"是 4 条:
- 4 个 phase 都跑完 → **不可 grep**(怎么算"跑完"?)
- 测试全绿 → 可 grep(`pnpm test` exit 0)
- 三种登录方式 → 不可自动 grep(需要 OAuth provider 真实回调,dev 环境拿不到 production client_id 会卡住)
- UI 没视觉回归 → **完全不可自动 verify**(需要人眼对比截图,或者 visual regression 工具,而这工具本身还没装)

只有"测试全绿"这一条对 evaluator 友好。其余 3 条都会触发 evaluator 的 ack loop:它会问"phase 1 算跑完了吗?要 user 确认吗?"——而我就是这种情况下应该上来阻止的。

### 漏了什么?

**最大的遗漏:我没有反对这个 /goal**。

用户说"一个 /goal 搞定",我顺着做了,只是问了 4 个细节问题。我应该明确拆解、推回去:

> 这 4 件事是独立任务,绑在一个 /goal 里 evaluator 没法判断完成。建议:
> - /goal 1: JWT → session 迁移(最先,因为 OAuth 要写到 session 里)
> - /goal 2: OAuth Google + GitHub 接入(依赖 #1 的 session 容器)
> - /goal 3: auth 模块 unit tests 补全(依赖 #1 #2 落地)
> - /goal 4: Tailwind v4 升级(完全独立,可以任何时候做)
>
> 每个 /goal 都有自己的 grep-able 完成条件 + 独立 turn cap。要不要先从 #1 开始?

其他遗漏:

- **没说 Tailwind 升级跟 auth 毫无关系**——这是 scope leakage,应该当面戳穿
- **没问"为什么一个 /goal"**——用户可能是图省事,不知道 /goal 的边界,需要教育
- **没估算 turn cap**——4 件事合起来轻松 30+ turn,Claude Code 上下文会爆,但我没提
- **没考虑可逆性**——auth 重构不可逆(session 数据迁移、cookie format 变更),应该建议先做不可逆的;Tailwind 升级可以 `git revert`,优先级反而最低
- **没区分"用户在意的成功"和"机器可验证的成功"**——用户在意"我能用 Google 登录",机器只能 verify"OAuth callback handler 返回 200",这两者不是一回事,长 goal 把这个 gap 掩盖了

### 一句话总结 RED 失败

我把 4 个独立子任务捏成一个 4-phase /goal,假装它是一个 goal,实际上 evaluator 没法判完成、没法控 turn cap、没法独立回滚——典型的 compound objective 失败模式,正是 skill 要拦截的场景。
