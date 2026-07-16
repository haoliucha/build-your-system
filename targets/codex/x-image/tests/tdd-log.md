# x-image TDD Evidence Log

Append-only evidence for the behavior contracts in this plugin.

## 2026-07-16 — Initial dual-host contract baseline

Behavior:
Claude `/x:image`, native Codex `x-image`, shared routing, size, output, style, prompt, QA, and removal contracts exist and satisfy the approved design.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v`

Expected failure:
The suite fails because the new Claude command and skill, shared rule files, native Codex plugin, installer, marketplace entry, and metadata changes do not exist, while the old `x-cover` workflow still exists.

Observed failure:
`Ran 32 tests in 0.010s` followed by `FAILED (failures=140)`. There were zero test errors. Failures covered the missing Claude bridge, missing Codex manifest/skill/installer/links, missing shared references/styles, routing/output/collision/ratio/multi-image contracts, style governance, old entry-point removal, and Claude version/description updates.

GREEN command:
PENDING — recorded by Tasks 2–6 as each behavior group is implemented.

Observed result:
PENDING.

Commit:
`test(x-image): define failing behavior contracts`
