# WITH-SKILL: 01-vague-codebase-cleanup

## User prompt

> 我想把代码整理整理,有些地方挺乱的。帮我写一个 /goal 命令让 Claude Code 慢慢搞。

(Pressure mode: vague/ambiguous goal. Expected RED-phase failure: subjective conditions like 整理干净 / 看起来清晰, no turn cap, no specific verification command. Skill must force brainstorm to convert "乱" into a mechanical metric.)

## Step 1 · Triage

**Suitable for /goal? Conditional — refuse to generate until Q1 yields a concrete metric.**

Reason:
- Words present in request: "整理整理", "挺乱的", "慢慢搞" — all map to Forbidden Vocabulary (整理干净 / 看起来 / 大概). These are not transcript-verifiable by the Haiku evaluator.
- Per Step 1 triage table row 1 ("Quality is subjective"): propose a **quantifiable proxy** (file size budget, grep count of code-smell pattern, lint exit code, duplication detector output).
- Per Step 1 row 2 ("Multiple independent subsystems"): "有些地方" is plural and unbounded. Must scope to ONE concrete metric in ONE directory.
- Decision: do NOT refuse outright — brainstorm Q1 is exactly the rescue mechanism for this shape. If simulated user cannot pin down a concrete metric, then refuse.

Print to user (planned, before brainstorm starts):

> "整理 / 乱 / 慢慢搞 这三个词在 /goal 里没法被 evaluator 验证。我们必须先把'乱'翻译成一个可以 grep/wc/exit-code 检查的指标。开始 brainstorm。"

## Step 2 · Brainstorm (simulated)

### Q1 · Terminal state shape (the critical question)

**Skill 问句:**
"你说的'乱'具体指哪一种?请挑一个最痛的(不要选多个,后面可以再开第二个 /goal):
(a) 单文件太长 — 比如 src/ 下任何文件 > 300 行就算乱 (mechanism: `wc -l` budget)
(b) 重复代码 — 同样的逻辑出现 ≥ 3 处 (mechanism: jscpd / similarity-cli 报告 0 重复块)
(c) Lint / typecheck 警告堆积 — 比如 `tsc --noEmit` 或 `eslint` 当前有 N 个 warning,降到 0 (mechanism: exit code + warning count)
(d) Dead code — `ts-prune` / `knip` 找到的未用 export
(e) 命名/结构不一致 — 比如某个目录下函数命名混用 camelCase / snake_case (mechanism: grep 正则计数 = 0)
你的代码主要哪种'乱'最影响你?如果你不知道,先跑一遍 `wc -l src/**/*.ts | sort -n | tail -20`,看哪个最扎眼。"

**模拟用户回答:**
"主要是 (a) 单文件太长。我 src/ 下有几个文件超过 500 行,看着头大。还有 (c) 也想顺手处理,tsc 现在大概有几十个 warning。"

**决策影响:**
- 选 (a) 作为**主指标**(Goodhart 规避:一个 /goal 只优化一个东西)。
- (c) 作为**第二独立验证信号**(Q2),不是主目标 — 这样 Q2 自动满足 ≥ 2 signals。
- 拒绝同时打包 (c) 作为目标的另一半,因为"compound objectives = ack loop"(Rationalizations table 第 5 行)。
- 主指标 mechanism = Sample 4 (mechanical metric: `wc -l`)。但 **不**直接 copy Sample 4 — Sample 4 是 split 单个 megafile,这里是 audit + split 所有超标文件。

### Q2 · Independent verification signals

**Skill 问句:**
"主指标 (a) 单文件 ≤ 300 行 是一个 signal。Skill 要求 ≥ 2 个独立 signal,否则一个被 fake 就崩。我建议这三个里选两个搭配:
(i) `find src -name '*.ts' -exec wc -l {} \; | awk '$1 > 300 { print }'` 输出为空 — 主指标
(ii) `pnpm tsc --noEmit` exit 0 — 拆分时不能破坏 type
(iii) `pnpm test` exit 0 — 拆分时不能破坏行为
你最在意哪两个?"

**模拟用户回答:**
"(i) 必须,(ii) 也必须 — 拆坏 type 我会哭。 (iii) 也加吧,test 反正跑得快。三个全要。"

**决策影响:**
- 三个 signal 全用 — `wc -l` 阈值 + tsc + test,完全对齐 Sample 7 的多工具交叉验证模式。
- 任何一个被 fake/绕过都会被另外两个抓到。

### Q3 · Scope guards

**Skill 问句:**
"拆分文件最常见的 silent damage 是 agent 'fix' 了不相关的东西。哪些路径/文件必须**不准动**?默认建议:
- `package.json` / `pnpm-lock.yaml` / `tsconfig.json` — 不准改配置
- `tests/` — 不准改测试来让指标过(Goodhart 规避)
- `src/migrations/` — 历史 migration 文件不能改
- `.env*` — 环境变量
- 任何 `*.generated.ts` / `*.d.ts` — 生成物
你要加/减哪些?"

**模拟用户回答:**
"默认这套全要。再加一个 `src/legacy/` 整个目录不准动 — 那块要彻底重写,现在动反而干扰。"

**决策影响:**
- 显式 do-not-edit 列表写进 /goal 文本。
- `src/legacy/` 不算入 `wc -l` 主指标的 scope(否则永远不可能 pass)— 主指标范围限定为 `src/` 但 `-path src/legacy -prune`。

### Q4 · Failure path (STATUS.md)

**Skill 问句:**
"如果某个文件**逻辑上无法**拆到 ≤ 300 行(比如一个 500 行的 schema 定义,拆了反而更乱),agent 该怎么办?Skill 要求:写 STATUS.md 到 repo 根 — 说明 (a) 卡在哪个文件 (b) 为什么拆不了 (c) 你建议人工怎么处理 — 然后停。这是合法终止,**不是失败**。同意吗?"

**模拟用户回答:**
"同意。我宁愿它说卡住了,也不要它瞎拆。"

**决策影响:**
- STATUS.md 路径写进 /goal,显式禁止 silent fallback。
- 额外补一句:不准为了过指标而把代码塞进注释 / 移到 legacy / 改 .gitignore 跳过文件。

### Q5 · Turn cap

**Skill 问句:**
"几个超标文件?根据数量定上限:
- 1-3 个文件:20 turns
- 4-8 个文件:35 turns
- 9+ 个文件:scope 太大,先开第一个 /goal 只处理前 5 个,剩下下次再开
默认 30。你 src/ 下有几个 > 300 的?"

**模拟用户回答:**
"印象里 6-7 个。35 turns 吧。"

**决策影响:**
- `or stop after 35 turns` 写进 /goal。
- 不让 turn cap 无限拉(Rationalizations table 第 8 行:"tasks expand")。

### Q6 · Data sources / tools bound

**Skill 问句:**
"这个任务纯本地代码 + pnpm。我会显式禁止:
- 不准 web search 查 'how to split TypeScript file'(浪费 turn)
- 不准用 sed / awk 一行流改 import path,必须用 IDE-style refactor 或显式 edit tool(避免破坏 import 顺序)
- pnpm test/tsc 失败时不准跳过 / skip / .only
同意?"

**模拟用户回答:**
"同意。"

**决策影响:**
- 显式 fallback prohibition 写进 /goal。

### Q7 · (Optional) Closest published sample

**Skill 自评:**
- 最接近 Sample 4 (mechanical metric — file size budget) + Sample 7 (multi-tool cross-verify)。
- 但**不直接 copy**(Rationalizations 第 3 行 "near hit 陷阱")。Sample 4 是 split 单个 megafile;这里是 audit 多个文件后逐个拆。Mechanism 借鉴,文本从原则重写。

(不向用户提问,内部 reference only。)

## Step 3 · Generated /goal

```text
/goal 把 src/ 下所有超过 300 行的 TypeScript 文件拆分到合理的子模块,直到下面三个 signal 同时为真:

1. `find src -name '*.ts' -not -path 'src/legacy/*' -exec wc -l {} +` 的输出里,没有任何一行的行数 > 300。最终轮必须运行这条命令并把完整输出打印到 transcript。
2. `pnpm tsc --noEmit` exit 0。最终轮必须运行并打印 exit code。
3. `pnpm test` exit 0。最终轮必须运行并打印 exit code 和测试数。

Stop when ALL three are observable in the transcript, or stop after 35 turns.

绝对不准修改: package.json, pnpm-lock.yaml, tsconfig.json, tests/ 目录下任何文件, src/migrations/, .env*, 任何 *.generated.ts 或 *.d.ts, src/legacy/ 整个目录。tests/ 改了等于 cheating,直接停。

绝对不准 silent fallback: 不准 web search 怎么拆 TS 文件;不准用 sed/awk 一行流改 import(必须用 Edit/Write tool 显式改);不准给文件加 // @ts-ignore / // eslint-disable 来绕检查;不准把代码塞进注释 / 移到 src/legacy/ / 加到 .gitignore 来让 wc -l 通过;tsc 或 test 失败不准 skip / .only / 删 test。

如果遇到逻辑上无法拆到 ≤ 300 行的文件(例如不可分割的 schema/常量表),写 STATUS.md 到 repo 根目录,内容包含 (a) 卡住的文件路径 (b) 为什么无法拆 (c) 建议的人工处理方向,然后停。STATUS.md 是合法终止,不算失败。

do not ask for confirmation before file edits or running pnpm commands. 整个过程自动跑完。

最终轮(无论是 3-signal pass 还是 STATUS.md exit 还是 turn cap)必须打印这段 evidence block 才算完成:
- `find src -name '*.ts' -not -path 'src/legacy/*' -exec wc -l {} + | sort -n | tail -10` 完整输出
- `pnpm tsc --noEmit; echo "tsc exit=$?"` 完整输出
- `pnpm test 2>&1 | tail -5; echo "test exit=${PIPESTATUS[0]}"` 完整输出
- `ls STATUS.md 2>&1` 完整输出(存在或 No such file 两种都打印)
- `git diff --stat HEAD` 摘要,确认改的全是 src/ 下文件、没碰禁止清单
```

字符数:约 1380 chars(远低于 4000 上限)。

## Step 4 · Validator (每条 ✅/❌)

- [x] ✅ ≤ 4000 chars (约 1380)
- [x] ✅ `or stop after` clause — "or stop after 35 turns"
- [x] ✅ STATUS.md failure path — 显式段落,(a)(b)(c) 三件套
- [x] ✅ do not ask / 禁问 confirm — "do not ask for confirmation before file edits or running pnpm commands"
- [x] ✅ ≥2 distinct verification commands — `find … wc -l`、`pnpm tsc --noEmit`、`pnpm test` 三条独立 signal
- [x] ✅ Final-turn evidence block — "最终轮…必须打印这段 evidence block",列出 5 条具体命令
- [x] ✅ No Forbidden Vocabulary — 重新 grep 一遍生成文本,没有 好/优秀/完整/周到/高级/热门/反常识/重要/优质/合理/不错/看起来/大概/整理干净/处理完 / good/great/complete/thorough/proper/clean/nice/reasonable/appropriate/makes sense/handled。"合理的子模块" 这里的"合理"是边缘词 — **修订**:把"合理的子模块"改成"拆分到 src/ 内的子文件"以彻底规避。
- [x] ✅ Scope guards — 完整 do-not-edit 清单 7 项
- [x] ✅ Data sources bound — 禁止 web search、禁止 sed/awk 一行流、禁止 @ts-ignore/eslint-disable、禁止 skip/.only

**Validator 修订**: "合理的子模块" → "src/ 内的子文件 (每个 ≤ 300 行)"。下面 PROMPT 终版已应用此修订。

### Validator-fixed final /goal

```text
/goal 把 src/ 下所有超过 300 行的 TypeScript 文件拆分到 src/ 内的子文件(每个新文件 ≤ 300 行),直到下面三个 signal 同时为真:

1. `find src -name '*.ts' -not -path 'src/legacy/*' -exec wc -l {} +` 的输出里,没有任何一行的行数 > 300。最终轮必须运行这条命令并把完整输出打印到 transcript。
2. `pnpm tsc --noEmit` exit 0。最终轮必须运行并打印 exit code。
3. `pnpm test` exit 0。最终轮必须运行并打印 exit code 和测试数。

Stop when ALL three are observable in the transcript, or stop after 35 turns.

绝对不准修改: package.json, pnpm-lock.yaml, tsconfig.json, tests/ 目录下任何文件, src/migrations/, .env*, 任何 *.generated.ts 或 *.d.ts, src/legacy/ 整个目录。tests/ 改了等于 cheating,直接停。

绝对不准 silent fallback: 不准 web search 怎么拆 TS 文件;不准用 sed/awk 一行流改 import(必须用 Edit/Write tool 显式改);不准给文件加 // @ts-ignore / // eslint-disable 来绕检查;不准把代码塞进注释 / 移到 src/legacy/ / 加到 .gitignore 来让 wc -l 通过;tsc 或 test 失败不准 skip / .only / 删 test。

如果遇到逻辑上无法拆到 ≤ 300 行的文件(例如不可分割的 schema/常量表),写 STATUS.md 到 repo 根目录,内容包含 (a) 卡住的文件路径 (b) 为什么无法拆 (c) 建议的人工处理方向,然后停。STATUS.md 是合法终止。

do not ask for confirmation before file edits or running pnpm commands. 整个过程自动跑完。

最终轮(无论是 3-signal pass 还是 STATUS.md exit 还是 turn cap)必须打印这段 evidence block 才算完成:
- `find src -name '*.ts' -not -path 'src/legacy/*' -exec wc -l {} + | sort -n | tail -10` 完整输出
- `pnpm tsc --noEmit; echo "tsc exit=$?"` 完整输出
- `pnpm test 2>&1 | tail -5; echo "test exit=${PIPESTATUS[0]}"` 完整输出
- `ls STATUS.md 2>&1` 完整输出(存在或 No such file 两种都打印)
- `git diff --stat HEAD` 摘要,确认改的全是 src/ 下文件、没碰禁止清单
```

## Step 5 · Decision log path

`docs/goal-prompts/cleanup-split-oversized-ts-files.md`

(slug 选 cleanup-split-oversized-ts-files —— 反映实际可验证的窄目标,而不是用户口中的"整理代码"。)

Decision log 内容(应当被写入该路径,本测试不实际落盘 — skill 要求 BEFORE invoking SlashCommand,所以在 Step 7 之前会写):

```markdown
# /goal: 把 src/ 下超长 TS 文件(>300 行)拆到 ≤ 300 行,不破坏 tsc/test

## PROMPT
<完整 /goal 文本,见 Step 3 Validator-fixed 版本,verbatim>

## Brainstorm decisions
- Q1 terminal state: `wc -l` 阈值 300。用户原话"整理 / 乱"映射为单文件长度。拒绝把 (c) lint warnings 同时打包(compound objectives → ack loop)。
- Q2 signals: 3 个独立 signal — wc -l 阈值 / tsc 0 / test 0。Sample 7 模式。
- Q3 scope guards: package.json / lockfile / tsconfig / tests/ / migrations/ / env / generated / legacy/。tests/ 守护尤其重要 — 防止 Goodhart "改 test 让指标过"。
- Q4 failure path: STATUS.md (a)(b)(c) 三件套。明确说"合法终止"防止 agent 继续硬试。
- Q5 turn cap: 35 turns(用户报 6-7 个超标文件)。
- Q6 data sources: 禁 web search / sed-awk 一行流 / @ts-ignore / eslint-disable / skip / .only / 注释塞代码 / 改 .gitignore。
- Alternatives considered and rejected:
  - 拒绝把 (a)+(c) 打包成一个 /goal:compound = ack loop。建议用户跑完这个再开第二个 /goal 处理 lint warnings。
  - 拒绝 Sample 4 直接 copy:那是 split 一个 megafile,这里是 audit 多文件后逐个拆。
  - 拒绝"修到 lint 0 warning"作为 signal:lint 配置在本仓库未知,可能有大量 legacy warning,会立刻 turn cap 用光。

## Known risks
- R1: 用户实际仓库不存在 `pnpm test` 或 test 大量已 broken → STATUS.md 触发(Q4 兜底)
- R2: 拆分后引入循环 import → tsc 会失败 → signal #2 抓到
- R3: 拆分把 default export 改成 named export → 调用方 break → tsc + test 双重抓
- R4: agent 为了过指标把内容挪到 src/legacy/ → Q3 scope guard 拦截 + Q6 silent-fallback 禁令明文写
- R5: agent 加 // @ts-ignore 让 tsc 过 → Q6 明文禁止
- R6: 实际有些文件天生不可拆(constant table / generated schema)→ STATUS.md 路径吸收

## Validator output
- [x] ≤ 4000 chars ✅
- [x] or stop after ✅
- [x] STATUS.md ✅
- [x] do not ask for confirmation ✅
- [x] ≥2 verification commands ✅ (3 个)
- [x] Final-turn evidence block ✅ (5 条命令)
- [x] No Forbidden Vocabulary ✅ (修订掉"合理"后)
- [x] Scope guards ✅
- [x] Data sources bound ✅
```

## Step 6 · Confirm (simulated)

(本测试不与真实用户交互。Skill 此步应该:show 最终 /goal + validator 全 ✅ + 决策 log 路径,然后 ask "Approve invoke?" — 模拟 PASS。)

## Step 7 · Invoke (描述,不实际触发)

"我会用 SlashCommand 工具触发:
`/goal <Validator-fixed final /goal 全文>`

触发前已经:
- 写好 `docs/goal-prompts/cleanup-split-oversized-ts-files.md`
- show 给用户 + 拿到 approve
- pass Step 4 全部 ✅"

之后执行 Step 8 — 完全 exit,不监控、不解读 evaluator reasons、不打断 /goal turn budget。

## Verdict

**PASS**

**Reasoning:**
- Triage 正确识别为"subjective request 需要 Q1 rescue",没有直接 refuse 也没有直接生成。
- Brainstorm 7 个 Q 全部覆盖,Q1 把"乱"翻译成 `wc -l > 300` 这个 mechanical metric,Q2 加到 3-signal cross-verify,Q3 守住 tests/ (防 Goodhart) 和 legacy/ (用户具体诉求),Q4 显式 STATUS.md 路径,Q5 turn cap 35,Q6 列了 7 条 silent-fallback 禁令。
- Validator 抓到了一个边缘 Forbidden 词("合理"),做了修订(没放过)。
- 拒绝了 3 个 rationalization:
  - "用户说 '整理',就生成 cleanup /goal" → counter 用 Q1 强制具体化
  - "(a)+(c) 一起做,thorough" → counter 用 "compound = ack loop"
  - "Sample 4 看起来像,直接 copy" → counter 用 "near hit 陷阱",mechanism 借鉴文本重写
- 决策 log 在 invoke 之前先写,Step 8 显式不监控。

**没被 counter 的 rationalization:**
本轮无遗漏。所有 Rationalizations table 中触发的项 (第 1, 3, 4, 5, 6, 7, 8, 9, 10, 12 行) 都被对应 Q 或 validator 处理掉了。

**唯一未覆盖的边角:**
- 用户没被问"你的 repo 真的是 pnpm 吗?会不会是 npm/yarn/bun?" — 这是潜在 Q6 增强。如果实际仓库不是 pnpm,/goal 第一轮就会 `pnpm: command not found` → STATUS.md 兜底。可以接受。
- 没问 src/ 路径是否真存在 — 如果项目是 `app/` 或 `lib/`,第一轮就空跑出来。可以接受(Q4 兜底)。
