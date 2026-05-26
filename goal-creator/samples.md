# /goal Published Sample Library

7 verbatim published `/goal` commands from public sources. **Reference only — NOT decision trees.** Each sample demonstrates a distinct verification mechanism.

When brainstorming with the user, scan this list to inspire Q1 answers. Do not blindly copy a sample because the user request "looks like" one of them — that overfits familiar shapes and underfits unfamiliar ones. Use samples as inspiration for the **mechanism**, then write from principles.

---

## Sample 1 · API/包全量替换 (grep-clean pattern)

```text
/goal migrate all usages of legacy_api.* to new_api.* in src/, run npm test until exit 0, do not modify tests/legacy/, or stop after 30 turns
```

**Mechanism**: `grep -r 'legacy_api' src/` count = 0 (evaluator sees grep output in transcript) + npm test exit code + file allowlist guard.
**Source**: [Apiyi.com — Claude Code goal mode guide](https://help.apiyi.com/en/claude-code-goal-mode-keep-working-until-done-guide-en.html)

---

## Sample 2 · GitHub Issue 队列清零 (external state)

```text
/goal close all GitHub issues labeled "needs-triage" by either resolving or relabeling, run gh issue list --label needs-triage and verify the output is empty, or stop after 25 turns
```

**Mechanism**: `gh issue list ...` output empty (fully mechanical). "By either resolving or relabeling" explicitly allows two legal terminal actions.
**Source**: [Apiyi.com](https://help.apiyi.com/en/claude-code-goal-mode-keep-working-until-done-guide-en.html)

---

## Sample 3 · 规约逐条对应 (reference proof)

```text
/goal implement every acceptance criterion in docs/design.md, prove each by referencing the exact section, do not edit docs/design.md itself, or stop after 40 turns
```

**Mechanism**: "prove each by referencing the exact section" forces Claude to name `§3.2.1`-style refs in transcript; evaluator counts ref coverage. Plus source-file guard.
**Source**: [Apiyi.com](https://help.apiyi.com/en/claude-code-goal-mode-keep-working-until-done-guide-en.html)

---

## Sample 4 · 文件尺寸预算 (mechanical metric)

```text
/goal split src/megafile.ts into modules under src/parts/ where each file is < 300 lines, run npm run typecheck until exit 0, or stop after 20 turns
```

**Mechanism**: `wc -l src/parts/*` each number < 300 + typecheck exit 0. Two independent mechanical signals.
**Source**: [Apiyi.com](https://help.apiyi.com/en/claude-code-goal-mode-keep-working-until-done-guide-en.html)

---

## Sample 5 · 外部清单 → 文档映射 (manifest mapping)

```text
claude -p "/goal CHANGELOG.md has an entry for every PR merged this week"
```

**Mechanism**: Claude must list this-week PRs via `gh pr list --state merged ...` in transcript, then grep CHANGELOG line-by-line. Evaluator compares two lists. **Best for "I want X written completely with no omission".**
**Source**: [Anthropic 官方文档](https://code.claude.com/docs/en/goal)

---

## Sample 6 · 状态矩阵清零 (multi-terminal-state)

```text
/goal every issue labeled 'triage-needs-repro' in the current repo has either a confirmed reproduction step in its body or has been closed with a comment explaining why.
```

**Mechanism**: Each item lands in one of two legal terminal states {has-repro-step, closed-with-explanation}. The "OR" prevents the agent from paralyzing on cases with no single answer.
**Source**: [developertoolkit.ai](https://developertoolkit.ai/en/claude-code/advanced-techniques/goal-workflows/)

---

## Sample 7 · 多工具交叉验证 (independent signals)

```text
/goal every import of '@old-pkg/auth' is replaced with '@new-pkg/auth', the project compiles via `tsc --noEmit`, and `npm test` exits 0. Do not edit package.json or lockfiles.
```

**Mechanism**: Three **independent** signals — grep count = 0 / tsc passes / test passes. Any one being faked is caught by the other two. Plus lockfile guard.
**Source**: [developertoolkit.ai](https://developertoolkit.ai/en/claude-code/advanced-techniques/goal-workflows/)

---

## Pattern → User-need cheat sheet

| User says... | Closest sample mechanism |
|---|---|
| "Replace all X with Y" | #1 (grep-clean) |
| "Clear out my [queue/backlog/inbox]" | #2 (external state) |
| "Implement this spec" | #3 (reference proof) |
| "Refactor for size/complexity" | #4 (mechanical metric) |
| "Write [doc/manifest] that covers every X" | #5 (manifest mapping) |
| "Triage [items] into [N] buckets" | #6 (multi-terminal-state) |
| "I'm worried about silent regressions" | #7 (independent signals) |

**Critical**: Match on **mechanism**, not surface shape. A content-research task can use Sample 5's mechanism even though no published sample exists for content work.

## What no published sample covers (the principle-driven gap)

Non-code domains have no published samples. Examples:
- Content research (gather → rank → publish)
- Data cleaning (CSV in → cleaned CSV out)
- Account/financial workflows
- Communication tasks (email triage, message routing)

For these, the user's brainstorm answers drive the /goal. Apply the mechanisms above (grep / count / state-matrix / manifest-map / multi-signal) to the user's specific deliverables. **Never refuse to generate just because no sample matches** — that's overfitting to the published set.
