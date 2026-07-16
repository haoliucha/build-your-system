# AC-08 — Claude Rescue Bridge

Status: FAIL

Claude session: `fb62d830-5641-44ce-aef5-2b6b730e110e`

Exact `/x:image` invocation:

```text
/x:image targets/codex/x-image/tests/fixtures/tech-article.md illustration 3:2 editorial-material；生成且只生成一张文章插图，表现一位独立开发者正在构建开源研究工具，不显示任何文字；将原始图片保存到 targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge.png。每张图片只允许调用一次 ImageGen，不得重试、编辑或后处理。返回完整的 Codex x-image 原生报告。
```

Local Claude plugin: PASS — the source `x` plugin exposed `/x:image` and loaded the bridge instructions.

Expected `codex:codex-rescue` agent call count: 1

Actual `codex:codex-rescue` agent call count: 1

Agent tool-use ID: `toolu_01LPqGFygGSnF9gJgoLKgbZe`

Fresh task: PASS — the delegated prompt begins with `--fresh --wait`, includes the actual worktree path, and tells Codex to use the native `x-image` skill.

Foreground task: FAIL — the Agent call omitted `run_in_background: false`; Claude Code 2.1.207 launched the task asynchronously and returned a task notification later.

Native Codex `x-image` execution: PASS

Codex report returned verbatim: PASS — the task-notification `<result>` and Claude's final assistant message have the same SHA-256, `203db1f0eca763967be58f9868986860ece573997ce0847e501fb42dfadb1965`.

Silent transport: FAIL — Claude emitted a delegation announcement and a progress/status message before returning the final native report.

Claude-side file inspection count: 0

Claude-side ImageGen call count: 0

Claude-side retry count: 0

Claude-side image modification or post-processing count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge.png`

Actual dimensions: `1536 × 1024`, exact `3:2`

Style ID: `editorial-material`

Native generation call count: 1

Native edit call count: 0

Native image modification command count: 0

Output SHA-256: `3c4d389619da4c7adae9d6ff3c11eeac696ebc247b6996d182d0e82843abf67a`

Content QA: PASS — exactly one developer visibly assembles a modular research/archive tool; research fragments converge into one local archive; no readable text, numbers, code, logo, watermark, additional person, or invented data.

Style QA: PASS — warm off-white background, charcoal and neutral tactile materials, IKB-blue accents, soft studio lighting, and one asymmetric focal cluster.

P0 checklist: PASS — one native generation, zero edits, zero modification commands, original file preserved, correct path and hash, no extra Claude-side image work.

P1 checklist: FAIL — the bridge did not force a foreground Agent call and did not remain silent before the verbatim final report.

P2 checklist: The developer's hair sits closer to the upper edge than the requested 8% safe margin, but remains fully visible and does not impair meaning or composition.

## Attempt history

- Attempt 1: `BLOCKED` in Claude session `3c74bf8e-8cb2-4423-9d4c-0659a8521129` because Vertex Application Default Credentials returned `invalid_grant` before the first model response.
- Attempt 2: Native Codex generation and final verbatim report passed, but foreground and silent-transport bridge requirements failed.
- Regression added: `test_forces_foreground_agent_invocation` and `test_forbids_intermediate_user_visible_messages`.
- Contract correction: the bridge now requires `run_in_background: false`, forbids delegation announcements and progress messages, and allows only the native Codex report as the successful user-visible response.
