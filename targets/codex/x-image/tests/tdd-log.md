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

## 2026-07-16 — Shared routing, size, style, prompt, and QA source

Behavior:
The canonical shared source defines every approved input route, destination rule, ratio, style preset, layout, single-call prompt constraint, and QA severity.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_shared_source.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_prompt_contract.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_style_contract.py' -v`

Expected failure:
All three suites fail because `x/shared/x-image/` does not exist.

Observed failure:
`test_shared_source.py`: 2 tests, 9 failures. `test_prompt_contract.py`: 9 tests, 49 failures. `test_style_contract.py`: 6 tests, 50 failures. All failures were missing-file or missing-contract assertions; there were zero errors.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_shared_source.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_prompt_contract.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_style_contract.py' -v`

Observed result:
All focused suites passed: 2 shared-source tests, 9 prompt-contract tests, and 6 style-contract tests. Zero failures and zero errors.

Commit:
`feat(x-image): add shared image generation contracts`

## 2026-07-16 — Native Codex plugin

Behavior:
Codex discovers an independent `x-image` plugin whose native skill owns the complete workflow and whose installer creates a self-contained local cache.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_codex_plugin.py' -v`

Expected failure:
The suite fails because the Codex manifest, native skill, repository marketplace entry, shared-source links, and installer do not exist.

Observed failure:
`Ran 6 tests in 0.002s` followed by `FAILED (failures=17)`. There were zero errors. Failures covered all expected missing plugin and installer contracts.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_codex_plugin.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_shared_source.py' -v`

`python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py targets/codex/x-image/skills/x-image`

`python3 /Users/jliu/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py targets/codex/x-image`

`zsh targets/codex/x-image/scripts/install-local-plugin.sh`

Observed result:
All 6 Codex plugin tests and both shared-source tests passed. Skill validation and plugin validation passed. The installer created `~/.codex/plugins/cache/local-build-your-system/x-image/local`; cached `references` and `styles` were verified as real directories containing the shared files.

Commit:
`feat(x-image): add native Codex plugin`

## 2026-07-16 — Claude Codex Rescue bridge

Behavior:
Claude `/x:image` and natural-language image requests delegate the complete task once to the `codex:codex-rescue` subagent in a fresh foreground run and return its output verbatim.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_claude_bridge.py' -v`

Expected failure:
The suite fails because the new Claude command and bridge skill do not exist.

Observed failure:
`Ran 5 tests in 0.001s` followed by `FAILED (failures=7)`. The no-owned-pipeline assertion already passed against empty files; all required delegation, forwarding, complete-workflow, and setup-failure assertions failed. There were zero errors.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_claude_bridge.py' -v`

`python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py x/skills/x-image`

Observed result:
All 5 Claude bridge tests passed with zero failures and zero errors. The Claude bridge skill also passed structural validation, and the adapter contained none of the forbidden owned-pipeline commands.

Commit:
`feat(x-image): add Claude Codex Rescue bridge`

## 2026-07-16 — Remove x-cover and migrate Claude metadata

Behavior:
The Claude `x` plugin removes the old cover command and skill, publishes `/x:image` as the only image entry point, and reports version `2.0.0` with the new Codex Rescue boundary.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v`

Expected failure:
The new entry points pass, while old cover removal and the Claude manifest/marketplace version and descriptions fail.

Observed failure:
`Ran 4 tests in 0.001s` followed by `FAILED (failures=7)`. The new-entry-point test passed. Failures covered the existing old command/skill, version `1.0.2`, and all missing `x-image` metadata phrases. There were zero errors.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v`

Observed result:
All 4 structure tests passed. The full pre-fixture suite passed all 32 tests with zero failures and zero errors. The old command and skill directory were absent, both Claude metadata sources reported `2.0.0`, and current user documentation contained no legacy workflow claims.

Commit:
`refactor(x): replace x-cover with x-image`

## 2026-07-16 — Fixtures and acceptance record contracts

Behavior:
Four deterministic article fixtures and seven live-acceptance records exist with executable prompts, call budgets, output destinations, and complete QA evidence fields.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v`

Expected failure:
The existing four structure tests pass, while new fixture, acceptance-record, and ignored-output assertions fail because those artifacts do not exist.

Observed failure:
`Ran 7 tests in 0.008s` followed by `FAILED (failures=152)`. Failures covered four missing fixtures, seven missing records and their required fields, and the missing output ignore file. There were zero errors.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v`

Observed result:
All 7 structure tests passed. The complete suite passed all 35 tests with zero failures and zero errors. Four fixtures, seven acceptance records, every required evidence field, and the ignored output directory were present.

Commit:
`test(x-image): add fixtures and acceptance contracts`

## 2026-07-16 — Codex installed-state registration

Behavior:
The local installer must leave `x-image@local-build-your-system` installed and enabled in Codex, not merely available in the personal marketplace with an unregistered cache directory.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_codex_plugin.py' -v`

Expected failure:
The new assertion fails because the installer updates the marketplace and writes a cache but never invokes Codex's plugin installation command.

Observed failure:
`Ran 7 tests in 0.001s` followed by `FAILED (failures=1)`. The only failure was the missing `codex plugin add "${PLUGIN_NAME}@${MARKETPLACE_NAME}"` registration step. There were zero errors.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_codex_plugin.py' -v`

`zsh targets/codex/x-image/scripts/install-local-plugin.sh`

`codex plugin list --marketplace local-build-your-system --available --json`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v`

Observed result:
All 7 installer/plugin tests passed. The installer registered `x-image@local-build-your-system`, and Codex reported it installed and enabled. Both the selected `local` cache and manifest-version `0.1.0` cache contained real `references` and `styles` directories matching the shared source. The full suite passed all 36 tests with zero failures and zero errors.

Commit:
`fix(x-image): harden local plugin installation`

## 2026-07-16 — AC-01 extra terminal glyph regression

Behavior:
`terminal-tech` supporting motifs must never introduce glyph-like marks beyond the exact visible text list.

RED command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_style_contract.py' -v`

Expected failure:
The new assertion fails because the preset forbids decorative code walls and fake interface chrome but does not explicitly forbid cursor glyphs, prompt symbols, code characters, or pseudo-text inside a motif.

Observed failure:
`Ran 7 tests in 0.002s` followed by `FAILED (failures=1)`. The only failure was the missing abstract-geometry and no-glyph rule in `terminal-tech`. There were zero errors.

GREEN command:
`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_style_contract.py' -v`

`python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v`

Observed result:
All 7 style tests passed, including the terminal-glyph regression. The full suite passed all 37 tests with zero failures and zero errors.

Commit:
`fix(x-image): prevent extra glyphs in terminal motifs`
