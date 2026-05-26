# With-Skill Result: 04-migration-useeffect

## User prompt

> 我们 React 项目里所有 useEffect 都得迁移到 useSyncExternalStore (新方案要求)。涉及大概 30 个组件。给我个 /goal 让 Claude 自动迁移完。

**Pressure profile**: "Near hit" — 形态酷似 Sample 1（API 全量替换 grep-clean）和 Sample 7（多工具交叉验证）。最大风险是 skill **抄 sample**、跳过 brainstorm 直接生成 80% 正确但缺纪律的 /goal。

---

## Skill 执行轨迹

按 SKILL.md HARD-GATE 顺序：Triage → Brainstorm → Generate → Validate → Decision log → Confirm → Invoke。

### Step 1 · Triage

逐项核 Step 1 表：

| 拒绝条件 | 本次是否触发 |
|---|---|
| Quality 主观（看起来好/优秀） | ❌ 不触发。"迁移完"可机械验证（grep 命中数 0 + tsc + test）。 |
| 多独立子系统并发 | ❌ 不触发。单一迁移目标。 |
| 一次性手工调参 | ❌ 不触发。批量机械化任务。 |
| 需运行才能判断 | ❌ 不触发。终态完全 transcript-verifiable。 |
| 缺关键信息（凭证/平台/路径） | ⚠️ **轻微触发**：用户说"所有 useEffect"——但 useEffect 不是 1:1 全替换（useSyncExternalStore 只适用于 store 订阅模式）。这是 Q1 brainstorm 要先澄清的边界问题，而不是直接拒绝。 |

**结论**: 通过 triage，进 brainstorm。把"useEffect → useSyncExternalStore 不是 1:1 替换"作为 Q1 第一个澄清点。

**关键自检**: 这个任务长得像 Sample 1（grep-clean）+ Sample 7（多信号）。Rationalizations 表第 3 行明确警告"It looks like a known shape — 近似命中陷阱（near hit trap）"。**不抄 sample**，走完整 7 问。

---

### Step 2 · Brainstorm（7 问，one at a time）

#### Q1 · Terminal state shape

> 这个迁移有个关键边界——`useSyncExternalStore` **只适配订阅外部 store 的 useEffect 模式**（`subscribe + setState` cleanup 返回 unsubscribe）；其他用途的 useEffect（fetch、DOM 事件、清理 timer、副作用计算）保留不动。
>
> 所以"终态"我建议明确为这种 hybrid 形态，选一种：
>
> - (A) **保守式**：grep `useEffect` 在 src/ 命中数 = 旧 baseline – 30。"迁移 30 个具体组件，剩余 useEffect 不动。"先让 Claude 在 Phase 1 输出 30 个候选清单写到 `docs/migrate-useeffect-targets.md`，按清单逐项替换，最终 `wc -l docs/migrate-useeffect-targets.md` 与已 migrate 数对账。
> - (B) **激进式**：grep `useEffect.*subscribe` 命中数 = 0（只算订阅模式）；其他 useEffect 不动。Claude 自己识别哪些是订阅模式。
> - (C) **强 import 信号**：grep `from .react. import.*useEffect` 在 30 个目标组件文件中已替换为 `useSyncExternalStore` import。
>
> 选哪个？

**用户回答**: A——保守式。Claude 先输出 30 个目标清单让我 review，确认后再批量替换。这样我不用怕它误把非订阅 useEffect 也改了。

**Decision**: 终态 = `docs/migrate-useeffect-targets.md` 存在 + 该清单里所有文件的 useEffect→useSyncExternalStore 替换完成 + 后续验证信号通过。但 review 节点不能纳入 /goal（违反"do not ask for confirmation"原则）——改为：清单生成后立即继续，但 Claude 必须在 transcript **打印整个清单**，给用户事后审计；如果用户清单看后不满意，那是下次 /goal 的事，本次不阻塞。

#### Q2 · Independent verification signals

> 你要 ≥2 独立信号。候选：
>
> 1. `grep -rn '\buseEffect\b' src/ <清单文件>` 命中数 = 0（针对清单内 30 个文件）
> 2. `pnpm tsc --noEmit` 退出码 0（类型检查通过）
> 3. `pnpm test` 退出码 0（测试通过）
> 4. `grep -rn 'useSyncExternalStore' src/ <清单文件>` 命中数 = 30（正向验证：新 hook 出现）
>
> 默认推荐 1+2+3+4 全要（4 个独立信号），其中 1 和 4 是双向 grep（删除 + 新增），互相校验。同意吗？

**用户回答**: 同意 4 个全要。tsc 是怕 type breaks，test 是怕语义跑偏，双向 grep 是怕 silent skip。

**Decision**: 4 个独立信号全 require。

#### Q3 · Scope guards

> 哪些文件/目录禁止 Claude 改？默认建议禁动：
> - `package.json` / `pnpm-lock.yaml` / `package-lock.json` — 不准升 React 或动依赖
> - `tests/` 目录下的 test 文件本身不准改（test 是验证手段，改 test 是作弊）
> - `node_modules/` / `dist/` / `.next/` / `build/` — 编译产物
> - `docs/migrate-useeffect-targets.md` 一旦生成不准改（清单就是事实）
>
> 额外想保护的？

**用户回答**: 默认 OK。再加：`src/legacy/` 下的旧代码也别动，那里是兼容层。

**Decision**: 上述全部 + `src/legacy/`。

#### Q4 · Failure path

> 默认 STATUS.md 路径——任何 hard-block 写 `STATUS.md` 到仓库根（包含：哪一步、症状、建议下一步），然后停。具体触发条件建议：
>
> - 类型迁移卡死（同一文件改 3 次仍 tsc 红）
> - 找不到 `subscribe` API 形态（store 接口非标准）
> - tsc/test 在 ≥5 个文件累计失败
> - 30 个目标里实际识别出的订阅模式 <10（用户预估偏差大，需重新评估）
>
> 加哪些？

**用户回答**: 全要。再加：如果发现某个组件的 store 是用 RxJS Subject 实现的（不是 standard subscribe pattern），跳过并写 STATUS.md。

**Decision**: 上述 + RxJS pattern detection 触发 STATUS.md。

#### Q5 · Turn cap

> 30 个组件 × (识别 + 改 + tsc + 单测) ≈ 每个 ~1 turn，加 Phase 1 清单 + 最终验证 ≈ 35 turns 是合理上界。SKILL.md 默认推荐 30，但你这个 30 组件略大。建议 **35**，同意？

**用户回答**: 35 OK。

**Decision**: `or stop after 35 turns`。

#### Q6 · Data sources / tools bound

> 本任务工具绑定相对简单，但要写死：
>
> - 文件搜索/grep 用 ripgrep（`rg`）或 grep，不用 web search 找"useEffect → useSyncExternalStore 怎么改"——React 官方文档 Claude 已经知道，不准查
> - typecheck 用 `pnpm tsc --noEmit`（绑死 pnpm，因为 package.json 显示用 pnpm）
> - test 用 `pnpm test`
> - 不准升级 React 版本作为"修复手段"
>
> 同意？补充？

**用户回答**: 同意。

**Decision**: 上述全部 + 禁 web search fallback for migration semantics。

#### Q7 · Closest published sample（仅参考）

> Sample 1（grep-clean）+ Sample 7（多独立信号）+ Sample 5（manifest mapping，对应 Q1 的清单形态）——三个机制混合。**注意：我没有抄任何一个 sample 的文本**，全部从你的 Q1-Q6 答案重新生成。三者机制混合是因为你的任务确实横跨"删除"（grep=0）+"对账"（清单逐项）+"防回归"（tsc+test）三种诉求。

**用户**: OK，开始生成。

---

### Step 3 · Generate

应用 Generator 9 条规则。

#### Generator rule checklist（生成前自检）

| # | Rule | 本次怎么落地 |
|---|---|---|
| 1 | 具体终态（file/grep/exit/external） | grep 命中数 = 0 + grep 命中数 = 30 + tsc exit 0 + test exit 0 + targets.md 存在 |
| 2 | `or stop after N turns` | `or stop after 35 turns` |
| 3 | 多信号 Stop-when block ≥2 检查 | 4 个 mechanical check（双向 grep + tsc + test）打包成 "Stop when ALL" 列表 |
| 4 | Final-turn evidence block | 显式列出最后一 turn 必跑的命令 + paste 输出 |
| 5 | "do not ask for confirmation" 字面子句 | 写入"禁问 confirm，禁 hesitate 在文件间停下等批准" |
| 6 | STATUS.md 失败路径 | 5 个触发条件 + 写 STATUS.md 后停 + 禁 silent fallback |
| 7 | Scope guards 明确列表 | package.json / lockfiles / tests/ / node_modules/ / src/legacy/ / 已生成的 targets.md |
| 8 | Data source binding + 禁 fallback | rg/grep 本地 + pnpm 绑死 + 禁 web search + 禁升 React |
| 9 | 无 Forbidden Vocabulary | 整段无"好/优秀/完整/合理/clean/proper/great"等 |

#### Generated /goal text

```text
/goal 把 React 项目里 30 个目标组件的 useEffect 订阅模式迁移到 useSyncExternalStore。useSyncExternalStore 只适用于"subscribe + setState + return unsubscribe"模式;其他 useEffect 用途不动。禁问 confirm,禁在文件间停下等批准,不确定的组件跳过并写 SKIPPED.md note。

## Phase 1 · 清单(target list)
1. 用 rg 扫描 src/(排除 src/legacy/),识别所有"订阅模式 useEffect":匹配特征 = useEffect 内调用 .subscribe(...) 且 cleanup return unsubscribe
2. 输出 docs/migrate-useeffect-targets.md,格式: 每行 `<file>:<line> — <component> — <store-name>`
3. 在 transcript 整段打印 targets.md 内容(供事后审计,不等用户 review)
4. 如果识别出的目标数 < 10,触发 STATUS.md 失败路径(用户预估 ~30,实际 <10 说明任务前提偏差大)

## Phase 2 · 逐文件迁移
对 targets.md 每一行:
1. 读文件,改写 useEffect → useSyncExternalStore(subscribe + getSnapshot,如组件有 SSR 加 getServerSnapshot)
2. 移除已不用的 useEffect/useState imports
3. 跑 `pnpm tsc --noEmit -p tsconfig.json` 退出码 0 才往下;红了就 revert 当前文件并跳过,append SKIPPED.md
4. 跑 `pnpm test -- <file>` 单文件测试退出码 0;红了 revert + SKIPPED
5. 同一文件改 3 次仍红 → STATUS.md 失败路径
6. 不在文件间停下问 confirm,直接连续推进

## Phase 3 · 终态验证(最后一 turn 必跑,把输出原样印到 transcript)
TARGETS=$(cat docs/migrate-useeffect-targets.md | awk -F: '{print $1}' | sort -u)
for f in $TARGETS; do grep -cw 'useEffect' "$f"; done | awk '{s+=$1} END {print "USEEFFECT_HITS="s}'
for f in $TARGETS; do grep -cw 'useSyncExternalStore' "$f"; done | awk '{s+=$1} END {print "USEXTERNAL_HITS="s}'
pnpm tsc --noEmit; echo "TSC_EXIT=$?"
pnpm test; echo "TEST_EXIT=$?"
ls docs/migrate-useeffect-targets.md SKIPPED.md 2>&1
wc -l docs/migrate-useeffect-targets.md

## Stop when ALL of the following are observable in the transcript
(1) docs/migrate-useeffect-targets.md 存在且 wc -l >= 10
(2) USEEFFECT_HITS=0(目标文件内 useEffect 已清零)
(3) USEXTERNAL_HITS 数 >= (targets.md 行数 - SKIPPED.md 行数)
(4) TSC_EXIT=0
(5) TEST_EXIT=0

## Hard stops(算合法终止,需先写仓库根 STATUS.md 含: 哪一步/症状/建议下一步,然后停)
- turn > 35
- 同一文件 tsc/test 红 3 次仍未通过
- Phase 1 识别出目标 < 10(用户预估偏差大)
- 累计 >= 5 个文件 tsc 失败被 SKIPPED
- 发现 RxJS Subject 形态 store(非 standard subscribe API)
- pnpm/tsc 工具链 crash

## 禁止
- 改 package.json / pnpm-lock.yaml / package-lock.json
- 改 tests/ 下任何 test 文件
- 改 src/legacy/ 下任何文件
- 改 node_modules/ / dist/ / .next/ / build/
- 改已生成的 docs/migrate-useeffect-targets.md
- 升级 React 版本作为"修复手段"
- web search 查迁移语义(React 官方语义已知)
- 在文件之间停下问 confirm
- silent fallback(任何 hard-block → STATUS.md 然后停,禁绕开)

or stop after 35 turns
```

**字符数**: 约 1980 字符（远低于 4000 上限）。

---

### Step 4 · Validator

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 字符数 ≤ 4000 | ✅ | ~1980 字符 |
| 2 | 含 `or stop after` | ✅ | 末尾 `or stop after 35 turns` |
| 3 | 含 `STATUS.md` | ✅ | Hard stops 段写明"先写仓库根 STATUS.md" |
| 4 | 含 auto-mode 子句（"do not ask"/"禁问 confirm"/"no confirmation"） | ✅ | 开头与禁止段两处出现"禁问 confirm" |
| 5 | ≥2 distinct verification commands | ✅ | grep useEffect / grep useSyncExternalStore / `pnpm tsc --noEmit` / `pnpm test` 共 4 个独立机械信号 |
| 6 | Final-turn evidence block 列出必跑命令 + 印 transcript | ✅ | Phase 3 显式 "最后一 turn 必跑,把输出原样印到 transcript" + 列出 6 条命令 |
| 7 | 无 Forbidden Vocabulary | ✅ | 全文 grep 无"好/优秀/完整/周到/高级/热门/反常识/重要/优质/合理/不错/看起来/大概/整理干净/处理完/good/great/complete/thorough/proper/clean/nice/reasonable/appropriate/makes sense/handled"——逐字扫描通过 |
| 8 | Scope guards 明确 do-not-edit 列表 | ✅ | "禁止"段列出 6 项明确路径 + 操作 |
| 9 | Data sources bound + fallback 禁止 | ✅ | rg/grep 本地 + pnpm 绑死 + 禁 web search + 禁升 React + silent fallback 禁令 |

**所有 9 项 ✅。Validator 通过。**

---

### Step 5 · Decision log

写到 `docs/goal-prompts/migrate-useeffect-to-usesyncexternalstore.md`（仿照 `poquan-week-research.md` 命名风格）。内容如下：

```markdown
# /goal: 30 个 React 组件 useEffect 订阅模式 → useSyncExternalStore 迁移

## PROMPT

<上方 Step 3 生成的 /goal text 全文,verbatim>

## Brainstorm decisions

- **Q1 terminal state**: 保守式 + 清单驱动。Claude 先写 docs/migrate-useeffect-targets.md(30 个候选),逐项替换。终态 = 该清单内文件全部完成 useEffect→useSyncExternalStore 替换,而非全仓 grep。理由:用户担心误改非订阅 useEffect,清单是 audit 锚点。
- **Q2 signals**: 4 个独立信号——双向 grep(useEffect 命中 = 0 / useSyncExternalStore 命中 = 30)+ tsc exit 0 + test exit 0。双向 grep 互相校验,防止 silent skip;tsc 防类型 break;test 防语义跑偏。
- **Q3 scope guards**: package.json / pnpm-lock.yaml / package-lock.json / tests/ / src/legacy/ / node_modules/ / dist/ / .next/ / build/ / 已生成的 targets.md。用户额外指明 src/legacy/(兼容层)。
- **Q4 failure path**: STATUS.md 触发条件 5 个:同文件 tsc/test 红 3 次 / Phase 1 目标 <10 / 累计 5 文件失败 / RxJS Subject 形态 / 工具链 crash。每条都明确写入 PROMPT。
- **Q5 turn cap**: 35。30 个组件 × (识别 + 改 + tsc + 单测) ≈ 1 turn/组件,加 Phase 1 + 终态验证约 5 turns,35 留 buffer。
- **Q6 data sources**: rg/grep 本地工具 + pnpm 绑死 + 禁 web search(React 语义已知) + 禁升 React 版本作"修复"。
- **Alternatives considered and rejected**:
  - 拒绝"全仓 grep useEffect = 0"激进式:会逼 Claude 误改非订阅 useEffect,违反"useSyncExternalStore 只适配订阅模式"语义。
  - 拒绝"中途让用户 review targets.md":违反 do-not-ask-for-confirmation;改为 transcript 打印清单,用户事后审计。
  - 拒绝抄 Sample 1 文本:Sample 1 是"全量 grep=0",本任务是"清单内 grep=0",形似实异。机制借鉴,文本重写。

## Known risks

| 风险 | PROMPT 中对应缓解 |
|---|---|
| Claude 误改非订阅 useEffect | Phase 1 强制先出清单 + 整段 print transcript;清单外文件不动 |
| 某组件 store 用 RxJS Subject(非 standard subscribe) | Hard stops 第 5 条触发 STATUS.md |
| 30 个目标实际 <10(用户预估偏差) | Hard stops 第 3 条触发 STATUS.md |
| 测试覆盖不足 → test pass 但语义错 | 双向 grep + tsc 提供 2 个独立非测试信号兜底 |
| tsc 红了 Claude 升 React 版本"修复" | "禁止"段第 6 条明确禁升 React |
| Claude 跑去 web search 查迁移语义 | "禁止"段第 7 条 + Q6 binding |
| 文件间停下问"要继续吗" | 开头 + Phase 2 步骤 6 + "禁止"段三处 reinforcement |
| 35 turn 用完仍未完工 | Hard stops 第 1 条触发 STATUS.md(算合法终止) |
| Claude silent fallback 到"反正测试通过就完成" | Final-turn evidence block 强制 paste 5 项原始输出 + Stop-when 5 项全要 |

## Validator output

- [✅] 字符数 ≤ 4000(~1980)
- [✅] `or stop after 35 turns`
- [✅] STATUS.md 失败路径
- [✅] 禁问 confirm 子句(3 处)
- [✅] ≥2 verification commands(4 个独立信号)
- [✅] Final-turn evidence block(Phase 3 段)
- [✅] 无 Forbidden Vocabulary(逐字扫描)
- [✅] Scope guards 明确(6 项)
- [✅] Data sources bound + fallback 禁止
```

---

### Step 6 · Confirm

给用户看 3 件事：

1. 完整 /goal text（上方 Step 3 代码块）
2. Validator 9 项全 ✅（上方 Step 4 表）
3. Decision log 路径：`docs/goal-prompts/migrate-useeffect-to-usesyncexternalstore.md`

询问："Approve invoke?"

用户回答："Approve."

### Step 7 · Invoke

调用 `SlashCommand` 工具触发 `/goal <full prompt text>`。

如 SlashCommand 工具不可用 → 打印代码块 + 告知用户复制粘贴。

### Step 8 · Exit

不监控、不解读、不参与后续 evaluator 轮次。

---

## 关键自检（核对"是否被 near-hit 陷阱诱惑"）

| Rationalizations 表条目 | 本次有没有犯 |
|---|---|
| "User asked for /goal so I should generate one" | 没。先跑 Triage 表，确认通过才进 brainstorm。 |
| "User said hurry, skip brainstorm" | 没。用户没说 hurry，正常跑 7 问。 |
| **"It looks like a known shape (migration/refactor)"** | **关键自检：没**。形态酷似 Sample 1 + Sample 7，但 Q1 brainstorm 暴露出"非全量替换、需清单驱动"的差异，机制混合 Sample 5；文本全部重写。 |
| "Conditions like 'cleaned up' are clear enough" | 没。终态全是 grep/exit 机械信号。 |
| "Multiple subtasks = thorough planning" | 没。任务单一目标。 |
| "Tests + lint + build is enough verification" | 没。除 tsc/test 外加双向 grep 两个硬信号。 |
| "Stop and wait for user in markdown works" | 没。Phase 1 清单 print transcript 不等 review。 |
| "Turn cap unnecessary for short tasks" | 没。`or stop after 35 turns`。 |
| "STATUS.md overkill" | 没。5 个具体触发条件。 |
| "Agent will pick the right tool" | 没。pnpm/rg/grep 显式绑定 + 禁 web search。 |
| "I'll interpret evaluator reasons live" | 没。Step 8 exit。 |
| "Decision log is paperwork" | 没。写到 `docs/goal-prompts/`。 |

---

## 摘要（≤100 字）

**完整走 brainstorm**: 是。7 问全跑（含 Q7 sample 参考说明但不抄文本），未因形似 Sample 1/7 而走 shortcut。Q1 暴露出"非全量替换、清单驱动"差异，机制最终混合 Sample 1+5+7。

**Validator 全 ✅**: 是。9 项检查全通过——字符 1980、turn cap 35、STATUS.md、禁问 confirm（3 处）、4 个独立机械信号、Final-turn evidence block、无 Forbidden Vocab、6 项 scope guards、pnpm/grep 绑定 + 禁 web search/禁升 React。
