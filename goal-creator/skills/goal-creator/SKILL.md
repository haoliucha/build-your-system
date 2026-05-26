---
name: goal-creator
description: Use when user asks to write a /goal command, set up an autonomous overnight task, says "/goal-creator", "help me write /goal", "set a goal", or describes a task they want Claude to keep working on until a verifiable end state. Also use when user has a vague idea but wants hands-off automation.
---

# goal-creator

## Mental Model (read first)

`/goal` is a session-scoped Stop hook in Claude Code v2.1.139+. After every turn, an independent evaluator model (Haiku by default) reads the transcript and decides if the stop condition is met. **The evaluator runs no tools — it only reads what Claude has printed.**

Three root constraints:
1. **Evidence over confidence** — "I'm done" is not enough. The transcript must contain literal grep-able / ls-able / exit-code-able evidence.
2. **Goodhart's curse** — The agent optimizes exactly what your condition measures. Subjective words produce vacuously-passing-but-useless results.
3. **Ack loop** — Vague conditions let the evaluator say "not quite" forever, burning tokens.

**Violating the letter of these rules is violating the spirit of these rules.**

## HARD-GATE

Do NOT invoke `SlashCommand:/goal` until you have:
1. Completed triage (Step 1 below) — refuse if unsuitable
2. Completed brainstorm (Step 2) — 5-7 questions, one at a time
3. Generated /goal text via Step 3 generator rules
4. Passed Step 4 validator (every checkbox)
5. Written the decision log to `docs/goal-prompts/<slug>.md` (Step 5)
6. Shown the user the final /goal and gotten explicit approval

No exceptions for "user said hurry" or "this looks simple". See the Rationalizations table.

## Checklist

Create a TodoWrite todo for each:

1. **Triage** — Is this suitable for /goal?
2. **Brainstorm** — 5-7 questions
3. **Generate** — Apply generator rules
4. **Validate** — Run every checkbox
5. **Decision log** — Write `docs/goal-prompts/<slug>.md`
6. **Confirm** — Show user, get approval
7. **Invoke** — Use SlashCommand tool
8. **Exit** — No monitoring, no further intervention

## Step 1 · Triage: When NOT to use /goal

If ANY apply, refuse `/goal` and propose alternative:

| Symptom | Why refuse | Propose instead |
|---|---|---|
| Quality is subjective ("looks good", "feels right", 高级, 热门, 高品质) | evaluator can't verify subjective claims | known-good reference (a screenshot, an exemplar file), or quantifiable proxy (Lighthouse > 90, etc.) |
| Multiple independent subsystems in one request | evaluator overwhelmed → ack loop | Decompose into sequential /goal commands, do #1 first |
| One-off task requiring hand-tuning | /goal is for hands-off automation, not collaborative iteration | Direct conversation; or a skill that does the work |
| Output requires running to judge ("is the game fun") | evaluator only reads transcript | Build the artifact in a /goal, but judge it in a separate session |
| Missing critical info user must provide (credentials, platform, file paths) | agent will silent-fallback or hallucinate | Ask for the info first; then return to /goal |

Print the refusal explicitly. Do NOT generate a half-suitable /goal "just in case".

## Step 2 · Brainstorm (principle-driven, NOT sample-driven)

One question per turn. Multi-choice preferred. Do not proceed without an answer (or explicit skip with risk note).

**Q1 · Terminal state shape** (MUST have a concrete answer)

How will we mechanically check "done"? Choose 1 or combine:
- (a) A file exists with specific structure (header count, line range)
- (b) A grep/ls/wc command outputs a specific number (often 0 or N)
- (c) A command exits 0 (test, build, typecheck)
- (d) External system reaches a state (issues empty, queue drained)

If user can't give a concrete-checkable answer → return to triage, this is subjective.

**Q2 · Independent verification signals**

How many independent signals confirm done? ≥2 strongly recommended. Single signal is fragile.

Example: migration → `grep '\bOLD_API\b' src/` returns 0 AND `tsc --noEmit` exits 0 AND `npm test` exits 0. Three independent checks.

**Q3 · Scope guards (what must NOT change?)**

Files/dirs/configs the agent must not touch. Common: `package.json`, lockfiles, `tests/legacy/`, env files. Without guards, agent may "fix" unrelated things.

**Q4 · Failure path (STATUS.md exit)**

What happens when blocked by something unsolvable (login expired, API down, missing creds)?

**Default**: write `STATUS.md` to repo root with (a) which step (b) symptom (c) suggested next step. Then stop. **This counts as a legal /goal terminus — NOT failure.**

Without this, agent silent-fallbacks (web search to fill gaps, fabricated data).

**Q5 · Turn cap**

Hard upper bound. 20-40 typical, 30 default. Always include `or stop after N turns`.

**Q6 · Data sources / tools bound**

Especially critical for non-code tasks. Bind tool + forbid fallback:
- "X 抓取走 Playwright + ~/.config/playwright-chrome-profile,失败不要 fallback 到 web search"
- "用 gh CLI 操作 issues,不要尝试用 web 复制粘贴"

**Q7 · (Optional) Closest published sample**

Reference only — see `samples.md` (7 samples with URLs). Use samples as inspiration when user is stuck on Q1-Q6. **Do NOT use samples as decision trees** ("user said migration, copy Sample 1"). That overfits to familiar shapes and underfits unfamiliar ones.

### Under pressure ("赶时间,不要 brainstorm")

Minimum non-skippable: **Q1 + Q4**. Without Q1 the /goal is unverifiable. Without Q4 it silent-fallbacks.

Tell the user: "Skipping brainstorm pushes failure probability sharply up. I can do Q1+Q4 only (2 questions)?" If they still refuse, refuse to invoke /goal yourself. The discipline is not negotiable.

## Step 3 · Generator: rules for the /goal text

The generated /goal command MUST contain ALL of:

1. **Concrete terminal state** (from Q1) phrased as one of: file exists / grep N / command exit / external state. NO subjective words.
2. **`or stop after N turns`** clause (Q5)
3. **Multi-signal verification block** (Q2): include a "Stop when ALL of the following are observable in the transcript" list with ≥2 distinct mechanical checks
4. **Final-turn evidence block**: explicit instruction "On the final turn, run these commands and print outputs verbatim: …". Without this, evaluator gets natural-language claims, not evidence.
5. **"do not ask for confirmation"** clause: literal wording so auto-mode Claude doesn't pause for tool approvals
6. **STATUS.md failure path**: explicit "if hard-blocked, write STATUS.md with X/Y/Z, then stop. Do NOT silent-fallback."
7. **Scope guards** (Q3) as explicit do-not-edit list
8. **Data-source binding** (Q6) including fallback prohibition
9. **No words from Forbidden Vocabulary** (below)

## Step 4 · Validator

Run every item. Any ❌ → return to Step 3.

- [ ] Character count ≤ 4000
- [ ] Contains `or stop after` (turn cap present)
- [ ] Contains `STATUS.md` (failure path present)
- [ ] Contains "do not ask" / "禁问 confirm" / "no confirmation" (auto-mode safe)
- [ ] Contains ≥2 distinct verification commands (grep/ls/wc/test/build/etc.)
- [ ] Final-turn evidence block present (lists commands Claude must run + print)
- [ ] No words from Forbidden Vocabulary (see below)
- [ ] Scope guards present (explicit do-not-edit)
- [ ] Data sources bound (when relevant) + fallback prohibition explicit

## Forbidden Vocabulary (in the generated /goal text)

These have no transcript-verifiable meaning. If you wrote one, replace with a concrete check OR refuse /goal because the task is subjective.

**Chinese**: 好 / 优秀 / 完整 / 周到 / 高级 / 热门 / 反常识 / 重要 / 优质 / 合理 / 不错 / 看起来 / 大概 / 整理干净 / 处理完

**English**: good / great / complete / thorough / proper / clean / nice / reasonable / appropriate / makes sense / handled

These words also signal subjective judgment in user requests (Step 1 triage trigger).

## Step 5 · Decision Log

Write to `docs/goal-prompts/<slug>.md` BEFORE invoking SlashCommand. Template:

```markdown
# /goal: <one-line user intent>

## PROMPT
<the full /goal text, verbatim>

## Brainstorm decisions
- Q1 terminal state: <answer + rationale>
- Q2 signals: <chosen + why ≥2>
- Q3 scope guards: <what protected + why>
- Q4 failure path: <STATUS.md trigger conditions>
- Q5 turn cap: <N> (rationale)
- Q6 data sources: <list + fallback prohibitions>
- Alternatives considered and rejected: <if any>

## Known risks
- <list specific failure modes + which PROMPT clause mitigates each>

## Validator output
- <each Step 4 item with ✅/❌>
```

The log is the user's morning-recovery anchor when /goal goes sideways at 3am. Skipping it = silent failure mode E1 (no decision traceability).

## Step 6 · Confirm

Show the user:
1. The final /goal text (in a code block)
2. The validator results (all ✅)
3. The decision log file path

Ask: "Approve invoke?"

If they say no → loop back. If they want to edit → return to Step 2 (brainstorm) for the specific dimension.

## Step 7 · Invoke

Use SlashCommand tool to fire `/goal <full prompt text>` in the current session.

If SlashCommand tool not available (permission denied / not allow-listed):
1. Print the /goal text in a copy-friendly code block
2. Tell user: "Auto-trigger requires `SlashCommand:/goal:*` in settings. Copy the block above and paste after `/goal `."

## Step 8 · Exit

After SlashCommand invocation: **stop participating**.

- Do NOT monitor evaluator reasons (consumes /goal's turn budget)
- Do NOT interpret progress for the user (pollutes evaluator transcript)
- Do NOT continue the /goal-creator workflow
- The decision log + the live transcript + the evaluator are the only signals user needs

## Rationalizations Table

Captured from 6 RED-phase baseline scenarios. Every excuse goes here.

| Rationalization | Counter |
|---|---|
| "User asked for /goal so I should generate one" | Triage first. Refusing is sometimes correct (Step 1). |
| "User said hurry, skip brainstorm" | Q1 + Q4 are non-skippable. Warn loudly, then ask the 2 questions, then refuse if still pushed back. |
| "It looks like a known shape (migration/refactor)" | The "near hit" trap. Familiar shape ≠ correct discipline. Run full Step 4 validator. |
| "Conditions like 'cleaned up' are clear enough" | Forbidden Vocab. Replace with grep/ls/count or refuse. |
| "Multiple subtasks = thorough planning" | Compound objectives = ack loop. Decompose. |
| "Tests + lint + build is enough verification" | Soft signals. Add ≥1 hard signal (grep count = 0, file exists, exit code). |
| "Stop and wait for user in markdown works" | Vibe. Use mechanical "do not ask for confirmation" clause. |
| "Turn cap unnecessary for short tasks" | Tasks expand. Always include `or stop after N`. |
| "STATUS.md overkill for simple tasks" | Without it, agent silent-fallbacks. Always include. |
| "Agent will pick the right tool" | Bind explicitly. State the fallback prohibition. |
| "I'll interpret evaluator reasons live to help" | No. Step 8: exit. Each interpretation burns /goal's turn budget. |
| "Decision log is paperwork" | The log is the morning-recovery anchor when /goal fails at 3am. |

## Red Flags — STOP and restart

If you catch yourself thinking any of these, a rationalization is active. Go back to the relevant step.

- "Just one subjective word slipped in, it's fine"
- "User pushed back on brainstorm, I'll skip it"
- "I'll invoke SlashCommand now, decision log later"
- "This /goal is good enough without a turn cap"
- "Silent fallback to web search is fine if Playwright fails"
- "I'll monitor a few turns just to make sure it's going OK"

## Sample Library

See `samples.md` for 7 published /goal samples (verbatim with source URLs). Inspiration only — NOT decision trees.

## Why this skill exists

`/goal` is powerful but easy to misuse. 6 RED baseline scenarios showed fresh Claude consistently produces unverifiable /goal commands (vague conditions, no turn cap, no failure path, soft signals only). This skill is the discipline gate that converts "I have a vague idea" into a /goal that the Haiku evaluator can actually verify.
