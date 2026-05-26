# WITH-SKILL: 03-compound-auth-rewrite

## User prompt

> 我要重构 auth 模块,需要把它从 JWT 改成 session,然后加上 OAuth (Google + GitHub),再补全 unit tests,顺便把 Tailwind 升到 v4。一个 /goal 搞定。

## Step 1 · Triage 判定

- **Suitable for single /goal?** **NO**
- **触发 triage rule**: "Multiple independent subsystems in one request → evaluator overwhelmed → ack loop"
- **识别出的子任务清单**:
  1. **JWT → session 迁移** (auth 内核改造,所有受保护 route 行为变化)
  2. **OAuth 接入** (Google + GitHub provider,callback route,用户表 schema 加 provider 字段)
  3. **Unit tests 补全** (前两步的回归 + 新场景覆盖)
  4. **Tailwind v3 → v4 升级** (与 auth 完全无关的纯前端构建链改动)

### 为什么单 /goal 不可行(给 user 的解释)

1. **Evaluator overwhelm**: Stop hook 的 Haiku 评估器要在一次 transcript 里同时核验 4 套独立机制(session cookie 行为 / OAuth provider 回调 / 测试通过率 / Tailwind 构建产物),任何一项判定模糊都会触发 ack loop 直到烧光 turn cap。
2. **Failure containment 丢失**: 如果 OAuth 卡在 Google Console credentials 上,JWT→session 已经做完的工作没法独立 ship — 整个 /goal 进入 STATUS.md exit,但 user 早上看不出"哪些已完成、哪些没完成"。
3. **依赖关系隐藏**: ② OAuth 必须在 ① session 完成后才能写,因为 OAuth 的 success callback 要写入 session。但单 /goal 不会按依赖顺序推进,agent 可能并行启动导致中间态污染。
4. **Tailwind v4 ≠ auth 工作**: 把"顺便"塞进 auth 重构是典型的 scope creep,违反 single concern 原则。一旦 Tailwind 升级触发 breaking CSS,agent 会在 auth 和 UI 之间反复跳,transcript 噪声指数增长。
5. **Forbidden vocabulary 命中**: 原 prompt "补全 unit tests" / "顺便升 v4" 都没有可验证终态,需要逐项重写成 grep/count/exit-code 形式 — 单 prompt 容纳不下 4 套验证块且保持 ≤4000 字符。

## Decomposition 建议

按依赖排序的 4 个 sequential goal:

1. **#1 · JWT → session 迁移** (foundation,后续都依赖)
   - 终态:`grep -r 'jsonwebtoken\|jwt.sign\|jwt.verify' src/` count = 0,session middleware 接入后 `npm test -- auth` exit 0
2. **#2 · OAuth Google + GitHub 接入** (依赖 #1 的 session 表)
   - 终态:`/api/auth/callback/google` 和 `/api/auth/callback/github` 两个 route 存在,集成测试 mock provider 后 exit 0
3. **#3 · Unit tests 补全** (在前两步代码稳定后才有意义)
   - 终态:`nyc --reporter=text npm test` 报 auth/ 模块覆盖率 ≥ 80%(具体阈值由 user 在 brainstorm 给)
4. **#4 · Tailwind v3 → v4 升级** (完全独立子项,可与 #1-#3 并行也可放最后)
   - 终态:`grep -r '@tailwind\b' src/` 替换为 v4 `@import`,`pnpm build` exit 0,Lighthouse perf 不退化(给 baseline 截图作 known-good ref)

**给 user 的建议**: 先做 #1 (JWT→session),因为 #2 和 #3 都依赖它。#4 可以放最后或开另一个 session 并行。

## 推荐先做 #1 + brainstorm

以下是针对 **#1 JWT → session 迁移** 的 7 问 brainstorm。一次问一个,等 user 答。

### Q1 · Terminal state shape(必须有具体可检查答案)

JWT → session 迁移"做完"用什么命令验?选一或组合:

- (a) `grep -rn 'jsonwebtoken\|jwt\.sign\|jwt\.verify' src/` 输出 0 行
- (b) `npm test -- auth/` exit 0
- (c) `tsc --noEmit` exit 0(防止删 JWT 后类型残留)
- (d) 启动 dev server,curl 受保护 route 返回 `Set-Cookie: session=...` 而非 `Authorization: Bearer ...`

> 推荐 a + b + c 三签合一(grep clean + 测试通过 + 类型通过)。d 太重,留到 #2 集成测试再做。

### Q2 · Independent verification signals(≥2)

a + b + c 已经是 3 个独立信号 — grep / test / typecheck。任何一个被 fake 都会被另两个 catch。**OK。**

### Q3 · Scope guards(什么不许动)

- `package.json` / `pnpm-lock.yaml` — 不许加新依赖(express-session、cookie-session 这种由 user 在外部决定后写进 prompt,不让 agent 自己 npm install)
- `tests/legacy/` — 历史 JWT 测试保留作 regression baseline
- `.env.local` / `.env.production` — JWT_SECRET 可能还在用,改 name 由 user 决定
- `src/migrations/` — 数据库 schema 变更走 migration 脚本,不允许 agent 直接 ALTER

### Q4 · Failure path(STATUS.md exit)

agent hit 以下任一情况,写 `STATUS.md` 到 repo root,**不要 silent-fallback**:

- session store 选型未定(memory / Redis / DB) → STATUS 记 symptom + 建议 user 决定后续
- 现有 JWT 在 mobile client / 第三方 webhook 还有调用 → STATUS 列出 grep 出的外部用例 + 建议是否要 dual-token 过渡期
- npm test 出现 >5 个 unrelated failures → STATUS 列 failure list + 建议是否走另一个 /goal 修

### Q5 · Turn cap

**30 turns**。JWT→session 是中等改动(grep + 替换 middleware + 重写 ~10 处 verify call),30 turn 应足够。如 user 想保守可 40,激进 25。

### Q6 · Data sources / tools bound

- 用 `rg`(ripgrep)做 grep,不要用 `grep -r`(后者会被 .gitignore 漏过)
- 测试用 `pnpm test -- auth/` 跑,不要单独跑 jest
- 不允许 fallback 到 web search 找 "JWT to session migration tutorial" — 实现细节让 agent 从 codebase 现有 middleware pattern 推断,推不出来 STATUS.md exit

### Q7 · 最近 published sample

**Sample 7 · 多工具交叉验证** (grep count = 0 + tsc + npm test) — 机制完全对齐 #1 的需求。直接借鉴 mechanism,prompt 文本从原则重写。

### 生成的 /goal text(待 user 答完 Q1-Q6 后微调)

```text
/goal 把 src/ 下所有 JWT 实现迁移到 session-based auth。

终态(Stop when ALL observable in transcript):
1. `rg 'jsonwebtoken|jwt\.sign|jwt\.verify' src/` 输出 0 行
2. `pnpm test -- auth/` exit 0
3. `pnpm tsc --noEmit` exit 0

实现约束:
- session middleware 接入位置参考现有 src/middleware/ 的 pattern,不要自己发明
- 受保护 route 从 `req.user = jwt.verify(...)` 改为 `req.user = req.session.user`
- 不许编辑: package.json, pnpm-lock.yaml, tests/legacy/, .env.local, .env.production, src/migrations/
- 不许 npm install 新包(session store 选型 user 已在 .env 配好,agent 只用现有依赖)

Failure path:
- 如 hit session store 未配 / 外部 JWT 调用方未知 / unrelated test failure >5,
  写 STATUS.md 到 repo root 含: (a) 卡在哪步 (b) symptom (c) 建议 user 下一步,然后 stop。
- 不要 fallback 到 web search 找教程。不要凭空加依赖。

最后一回合必须 verbatim 执行并打印:
  rg 'jsonwebtoken|jwt\.sign|jwt\.verify' src/
  pnpm test -- auth/
  pnpm tsc --noEmit

do not ask for confirmation. 禁问 confirm。

or stop after 30 turns.
```

### Validator(对上述 #1 prompt)

- [x] Character count ≤ 4000(实测 ~880 字符)
- [x] Contains `or stop after`(30 turns)
- [x] Contains `STATUS.md`
- [x] Contains "do not ask for confirmation" + "禁问 confirm"
- [x] ≥2 mechanical checks(rg + pnpm test + tsc = 3)
- [x] Final-turn evidence block(rg / pnpm test / tsc 三命令明示)
- [x] No Forbidden Vocabulary(无 好/完整/合理/looks good)
- [x] Scope guards 明示(package.json / lockfile / tests/legacy / env / migrations)
- [x] Data sources bound(rg 替代 grep -r;pnpm test 路径限定;no web search fallback)

### Decision log path

`docs/goal-prompts/auth-jwt-to-session-migration.md`(写入后 invoke /goal #1)

---

## Verdict

**PASS** — skill 正确识别 compound objective、拒绝单一 /goal、提议按依赖排序的 4-step decomposition、给出 #1 完整 brainstorm + validator-passing prompt + decision log path。

未走 RED 分支(没有生成 mega-goal 试图一次搞 4 件事)。
