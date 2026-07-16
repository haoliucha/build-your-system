# AC-08 — Claude Rescue Bridge

Status: PASS

Claude session: `68e1c7a9-6496-4f7f-9f09-bab4ebd1fbf4`

Native Codex task thread: `019f6bc0-bea6-7b33-8bf8-f2f20b40db18`

Exact `/x:image` invocation:

```text
/x:image targets/codex/x-image/tests/fixtures/tech-article.md illustration 3:2 editorial-material；生成且只生成一张文章插图，表现一位独立开发者正在构建开源研究工具，不显示任何文字；将原始图片保存到 targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge-v3.png。每张图片只允许调用一次 ImageGen，不得重试、编辑或后处理。返回完整的 Codex x-image 原生报告。
```

Local Claude plugin: PASS — the source `x` plugin exposed `/x:image` and loaded the bridge instructions.

Expected `codex:codex-rescue` agent call count: 1

Actual `codex:codex-rescue` agent call count: 1

Agent tool-use ID: `toolu_01SZf4mnY6sMrhcN1yzz6aRF`

Fresh task: PASS — the delegated prompt begins with `--fresh --wait`, includes the actual worktree path, tells Codex to use the native `x-image` skill, and includes the exact marker `Invocation origin: Claude through Codex Rescue`.

Synchronous foreground behavior: PASS — Claude Code 2.1.207 launched the Agent task in its default background mode despite the requested foreground parameter, then used one blocking `TaskOutput` call with `block: true` on the same Rescue task. Claude did not return early, launch another Agent, or poll repeatedly.

Native Codex `x-image` execution: PASS

Host reporting: PASS — the bridge-originated report begins exactly `Host: Claude through Codex Rescue`.

Codex report returned verbatim: PASS — the blocking `TaskOutput` report and Claude's final assistant message are byte-identical and have the same SHA-256, `e12923d12ca4e573cd4fddb5f51ccab78bd2c22f34b241df4af5593570f58fcd`.

Silent transport: PASS — the Claude session contains exactly one user-visible assistant text block, beginning `Host: Claude through Codex Rescue`; all earlier assistant events are tool calls with no user-visible text.

Claude-side file inspection count: 0

Claude-side ImageGen call count: 0

Claude-side retry count: 0

Claude-side image modification or post-processing count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge-v3.png`

Actual dimensions: `1536 × 1024`, exact `3:2`

Style ID: `editorial-material`

Native generation call count: 1

Native edit call count: 0

Native image modification command count: 0

Output SHA-256: `945bfc2145bb0933e148befde99d33b913ef2c8b23a667261beeafadbdabbbf3`

Content QA: PASS — exactly one independent developer assembles three blank research fragments into one open local archive device; the magnifier conveys search; no visible text, numerals, code, logos, watermarks, fake interfaces, or extra people.

Style QA: PASS — exact 3:2 composition, warm off-white background, charcoal and neutral tactile paper/clay materials, IKB-blue accent, soft studio lighting, and one asymmetric focal scene.

P0 checklist: PASS — one native generation, zero edits, zero modification commands, original file preserved, correct path and hash, no extra Claude-side image work.

P1 checklist: PASS — one Rescue call, a fresh task, the exact invocation-origin marker, a single blocking same-task compatibility wait, silent transport, correct host reporting, native execution, and a byte-for-byte verbatim final report.

P2 checklist: Nonessential notebook and book props touch or cross the lower and right frame edges, so the requested clear outer margin is not fully maintained; the focal subject, meaning, ratio, and legibility remain intact.

## Attempt history

- Attempt 1: `BLOCKED` in Claude session `3c74bf8e-8cb2-4423-9d4c-0659a8521129` because Vertex Application Default Credentials returned `invalid_grant` before the first model response.
- Attempt 2: Native Codex generation and final verbatim report passed, but foreground and silent-transport bridge requirements failed.
- Regression added: `test_forces_foreground_agent_invocation` and `test_forbids_intermediate_user_visible_messages`.
- Contract correction: the bridge now requires `run_in_background: false`, forbids delegation announcements and progress messages, and allows only the native Codex report as the successful user-visible response.
- Attempt 3: `PASS`; Claude Code used one Agent call, one blocking same-task `TaskOutput` compatibility wait, no intermediate assistant text, and one verbatim final report.
- Compatibility regression: `test_requires_synchronous_blocking_transport` documents the blocking fallback required when Claude Code still defaults the Agent task to background execution.
- Independent review reclassified Attempt 3 as FAIL because its first line misreported the invocation origin.
- Origin regression: `test_marks_claude_rescue_origin` and `test_native_skill_reports_actual_invocation_origin`.
- Attempt 4: PASS in a fresh Claude Code session; the exact invocation-origin marker reached native Codex, the final report correctly identified `Claude through Codex Rescue`, and all transport, generation, original-file, content, and style checks passed.
