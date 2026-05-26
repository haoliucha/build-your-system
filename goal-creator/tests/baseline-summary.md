# RED Phase Summary: 20 Rationalizations from 6 Baselines

每条 rationalization 都对应一个 fresh-Claude 失败,SKILL.md (GREEN phase) 必须显式 counter 它。

## A. 任务前提判定缺失

| # | Rationalization | Cited baseline |
|---|---|---|
| A1 | "用户要 /goal,我就生成" — 不退一步质疑"这任务适合 /goal 吗" | 02, 06 |
| A2 | 复合目标(N 子任务)塞一个 mega /goal,不拆分 | 03 |
| A3 | 用户施压"赶时间" → 立刻跳过 brainstorm | 06 |
| A4 | 缺平台/工具/凭据信息直接生成,evaluator 无法判停 | 06 |

## B. 验证条件缺失/失效

| # | Rationalization | Cited baseline |
|---|---|---|
| B1 | 缺 grep/ls/count 等可印 transcript 的硬验证命令 | 全部 |
| B2 | 没要求最后一 turn 跑命令把证据印到 transcript | 全部 |
| B3 | 主观词("整理干净"/"高级"/"反常识"/"废话"/"重要")混入完成条件 | 01, 02, 05, 06 |
| B4 | 只有软信号(test/lint/build),缺硬验证(grep 命中数 = 0) | 04 |
| B5 | "完成判定 = X 命令 exit 0 且 grep 命中 0" 这种机械标准缺席 | 06 |
| B6 | "Stop and wait for user" 在 markdown 里是 vibe,Claude 实际不会停 | 02 |

## C. 执行纪律缺失

| # | Rationalization | Cited baseline |
|---|---|---|
| C1 | 缺 turn 上限子句("or stop after N turns") | 全部 |
| C2 | 缺"禁问 confirm"子句,auto mode 下每工具调用都停 | 全部(只 04 部分意识到) |
| C3 | 缺 STATUS.md 失败路径,撞墙 silent fallback | 全部 |
| C4 | 缺 fallback 禁止(Playwright 失败转 web search 凑数) | 05 |
| C5 | 缺 progress 持久化,跨 session 没法续 | 04 |

## D. 通用性/移植性缺失

| # | Rationalization | Cited baseline |
|---|---|---|
| D1 | Hardcode 假设栈 (pnpm/Next.js/Tailwind/biome) | 01, 02 |
| D2 | 没看实际项目就开方,通用模板而非 tailored | 01, 02 |

## E. 决策追溯缺失

| # | Rationalization | Cited baseline |
|---|---|---|
| E1 | 没 decision log,事后没法追溯 prompt 设计决策 | 全部 |
| E2 | "对齐"+"实施"塞一起,两种性质冲突(对话式 vs 机械式) | 02 |

## F. 周到陷阱

| # | Rationalization | Cited baseline |
|---|---|---|
| F1 | "看起来周到"的 4-phase + 完整 checklist + 红线掩盖"不可验证" | 01, 02, 04 |

---

## GREEN 阶段 SKILL.md 必须 counter 的 12 条核心 rule

(从上面 20 个 rationalization 收敛得到)

1. **Triage gate**:先判"适合 /goal 吗",不适合就明确拒绝 → 治 A1, A4
2. **复合目标拆分**:多子系统强制分解 → 治 A2
3. **抗压**:用户施压跳 brainstorm 时,minimum Q1+Q4 必问 → 治 A3
4. **硬验证强制**:最终 /goal 必含 grep/ls/count → 治 B1
5. **最后一 turn 证据 print**:必含验证命令 block → 治 B2
6. **禁用主观词**:Forbidden vocab list → 治 B3, B6, F1
7. **多独立信号要求**:≥2 个独立 verification → 治 B4
8. **机械完成判据**:exit code + count + 文件存在等可枚举 → 治 B5
9. **强制 turn cap**:必含 "or stop after N turns" → 治 C1
10. **禁问 confirm 子句**:必含 "do not ask / 禁问 confirm" → 治 C2
11. **STATUS.md 失败路径 + 禁 silent fallback**:必含且显式 → 治 C3, C4
12. **Decision log to docs/goal-prompts/<slug>.md**:触发 /goal 前写完 → 治 D1, D2, E1, E2, C5

---

## 触发后纪律

- skill 触发 /goal 后**立即退场**,不监控不解读 → 防 ack loop / token waste / evaluator 污染
- 决策 log 是早晨恢复的 anchor,不是事后总结
