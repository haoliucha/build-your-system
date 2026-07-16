# AC-08 — Claude Rescue Bridge

Status: FAIL

Claude session: `09c1615a-06f1-40aa-9dd8-ad1941dff368`

Exact `/x:image` invocation:

```text
/x:image targets/codex/x-image/tests/fixtures/tech-article.md illustration 3:2 editorial-material；生成且只生成一张文章插图，表现一位独立开发者正在构建开源研究工具，不显示任何文字；将原始图片保存到 targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge-v2.png。每张图片只允许调用一次 ImageGen，不得重试、编辑或后处理。返回完整的 Codex x-image 原生报告。
```

Local Claude plugin: PASS — the source `x` plugin exposed `/x:image` and loaded the bridge instructions.

Expected `codex:codex-rescue` agent call count: 1

Actual `codex:codex-rescue` agent call count: 1

Agent tool-use ID: `toolu_0177hqY6Jng7j1H2divvJsrg`

Fresh task: PASS — the delegated prompt begins with `--fresh --wait`, includes the actual worktree path, and tells Codex to use the native `x-image` skill.

Synchronous foreground behavior: PASS — Claude Code 2.1.207 launched the Agent task in its default background mode despite the requested foreground parameter, then used one blocking `TaskOutput` call with `block: true` on the same Rescue task. Claude did not return early, launch another Agent, or poll repeatedly.

Native Codex `x-image` execution: PASS

Host reporting: FAIL — the bridge-originated report begins `Host: native Codex` instead of `Host: Claude through Codex Rescue`.

Codex report returned verbatim: PASS — the blocking `TaskOutput` report and Claude's final assistant message have the same SHA-256, `774c2c353bf69f547047826504a5fd8e6c9652b642a37b0ee1f52753ba379619`.

Silent transport: PASS — the Claude session contains exactly one user-visible assistant text block, beginning `Host: native Codex`; all earlier assistant events are tool calls with no user-visible text.

Claude-side file inspection count: 0

Claude-side ImageGen call count: 0

Claude-side retry count: 0

Claude-side image modification or post-processing count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge-v2.png`

Actual dimensions: `1536 × 1024`, exact `3:2`

Style ID: `editorial-material`

Native generation call count: 1

Native edit call count: 0

Native image modification command count: 0

Output SHA-256: `358a2b3a7d5c2ad466be89f6b31633a1be0d65658480b6155a398c4ce0135998`

Content QA: PASS — exactly one developer assembles a modular research/archive tool; scattered material fragments flow into an organized archive and search metaphor; no readable text, numbers, logo, watermark, additional person, or invented data.

Style QA: PASS — exact 3:2 composition, warm off-white background, charcoal and neutral tactile materials, IKB-blue accents, soft studio lighting, safe margins, and one asymmetric focal cluster.

P0 checklist: PASS — one native generation, zero edits, zero modification commands, original file preserved, correct path and hash, no extra Claude-side image work.

P1 checklist: FAIL — transport behavior passes, but the final report misidentifies the Claude-through-Rescue origin as native Codex.

P2 checklist: Some abstract marks on the incoming material tiles resemble interface icons, but none form readable or pseudo-readable text and they do not affect the requested concept.

## Attempt history

- Attempt 1: `BLOCKED` in Claude session `3c74bf8e-8cb2-4423-9d4c-0659a8521129` because Vertex Application Default Credentials returned `invalid_grant` before the first model response.
- Attempt 2: Native Codex generation and final verbatim report passed, but foreground and silent-transport bridge requirements failed.
- Regression added: `test_forces_foreground_agent_invocation` and `test_forbids_intermediate_user_visible_messages`.
- Contract correction: the bridge now requires `run_in_background: false`, forbids delegation announcements and progress messages, and allows only the native Codex report as the successful user-visible response.
- Attempt 3: `PASS`; Claude Code used one Agent call, one blocking same-task `TaskOutput` compatibility wait, no intermediate assistant text, and one verbatim final report.
- Compatibility regression: `test_requires_synchronous_blocking_transport` documents the blocking fallback required when Claude Code still defaults the Agent task to background execution.
- Independent review reclassified Attempt 3 as FAIL because its first line misreported the invocation origin.
- Origin regression: `test_marks_claude_rescue_origin` and `test_native_skill_reports_actual_invocation_origin`.
