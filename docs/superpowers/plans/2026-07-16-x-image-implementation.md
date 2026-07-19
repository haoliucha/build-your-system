# X Image Dual-Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Claude-only `/x:cover` pipeline with a dual-host `x-image` system that generates complete covers and article illustrations through exactly one built-in ImageGen call per asset, with no image post-processing.

**Architecture:** Keep routing, size, style, prompt, layout, and QA rules in `x/shared/x-image/`. Claude exposes `/x:image` as a thin bridge to `codex:codex-rescue`; Codex exposes an independent native `x-image` plugin and performs all content analysis, ImageGen calls, file placement, and QA. The Claude and Codex adapters contain no duplicated long-lived generation logic.

**Tech Stack:** Markdown Agent Skills, Claude Code plugin commands, Codex `.codex-plugin` manifests, OpenAI Codex Rescue plugin, built-in ImageGen, Python `unittest`, JSON, zsh, rsync.

**Specification:** `docs/superpowers/specs/2026-07-16-x-image-design.md`

---

## File Responsibility Map

### Shared source of truth

- Create `x/shared/x-image/references/intent-routing.md` — cover/illustration intent, defaults, counts, and source resolution.
- Create `x/shared/x-image/references/size-presets.md` — ratio recommendations and exact-pixel disclaimer.
- Create `x/shared/x-image/references/style-policy.md` — precedence, style locking, and custom-style normalization.
- Create `x/shared/x-image/references/layout-patterns.md` — cover and illustration layout selection.
- Create `x/shared/x-image/references/prompt-contract.md` — final prompt schema and one-call constraints.
- Create `x/shared/x-image/references/qa-checklist.md` — content, style, output, and failure classification.
- Create `x/shared/x-image/styles/terminal-tech.md` — technology cover style.
- Create `x/shared/x-image/styles/editorial-material.md` — general explainer and article illustration style.
- Create `x/shared/x-image/styles/data-editorial.md` — data-led style.

### Claude adapter

- Create `x/commands/image.md` — `/x:image` command and Codex Rescue delegation.
- Create `x/skills/x-image/SKILL.md` — natural-language Claude bridge.
- Delete `x/commands/cover.md`.
- Delete `x/skills/x-cover/`.
- Modify `x/.claude-plugin/plugin.json` — version `2.0.0` and image capability description.
- Modify `.claude-plugin/marketplace.json` — version and description.
- Modify `x/README.md`, `x/CHANGELOG.md`, and root `README.md` — new command, migration, and examples.

### Codex adapter

- Create `targets/codex/x-image/.codex-plugin/plugin.json` — independent Codex plugin.
- Create `targets/codex/x-image/skills/x-image/SKILL.md` — native execution workflow.
- Create repository-relative `references` and `styles` links under the Codex skill.
- Create `targets/codex/x-image/scripts/install-local-plugin.sh` — local marketplace and self-contained cache install.
- Create `targets/codex/x-image/README.md` — install and usage.
- Modify `.agents/plugins/marketplace.json` — register `x-image`.

### Tests and acceptance evidence

- Create `targets/codex/x-image/tests/helpers.py`.
- Create `targets/codex/x-image/tests/test_structure.py`.
- Create `targets/codex/x-image/tests/test_claude_bridge.py`.
- Create `targets/codex/x-image/tests/test_codex_plugin.py`.
- Create `targets/codex/x-image/tests/test_shared_source.py`.
- Create `targets/codex/x-image/tests/test_prompt_contract.py`.
- Create `targets/codex/x-image/tests/test_style_contract.py`.
- Create `targets/codex/x-image/tests/tdd-log.md` — immutable RED/GREEN evidence for each production behavior.
- Create four fixture Markdown files under `targets/codex/x-image/tests/fixtures/`.
- Create seven acceptance record templates under `targets/codex/x-image/tests/acceptance/`.
- Create `targets/codex/x-image/tests/acceptance/output/.gitignore` for untracked live image artifacts.

Do not stage or modify the user's existing untracked root `AGENTS.md`.

## TDD Evidence Convention

Every production behavior in Tasks 2–6, plus every production correction discovered during Tasks 7–10, must be covered by a test created before the production change. Record the following in `targets/codex/x-image/tests/tdd-log.md`:

```text
Behavior:
RED command:
Expected failure:
Observed failure:
GREEN command:
Observed result:
Commit:
```

The initial failing contract suite and its RED evidence must be committed before any `x-image` production file is created. Later tasks append focused RED/GREEN evidence to the same log and include the updated log in the corresponding commit. Never rewrite an earlier evidence entry; append a correction if a command or observation was recorded incorrectly.

---

### Task 1: Establish the RED Contract Test Suite

**Files:**
- Create: `targets/codex/x-image/tests/helpers.py`
- Create: `targets/codex/x-image/tests/test_structure.py`
- Create: `targets/codex/x-image/tests/test_claude_bridge.py`
- Create: `targets/codex/x-image/tests/test_codex_plugin.py`
- Create: `targets/codex/x-image/tests/test_shared_source.py`
- Create: `targets/codex/x-image/tests/test_prompt_contract.py`
- Create: `targets/codex/x-image/tests/test_style_contract.py`
- Create: `targets/codex/x-image/tests/tdd-log.md`

- [ ] **Step 1: Create shared test helpers**

Implement `helpers.py` with repository-relative paths and text readers:

```python
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CLAUDE_X = REPO / "x"
CODEX_X_IMAGE = REPO / "targets" / "codex" / "x-image"
SHARED = CLAUDE_X / "shared" / "x-image"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(read(path))
```

- [ ] **Step 2: Write failing structure and removal tests**

`test_structure.py` must assert:

```python
import unittest

from helpers import CLAUDE_X, CODEX_X_IMAGE


class StructureTests(unittest.TestCase):
    def test_new_entry_points_exist(self):
        self.assertTrue((CLAUDE_X / "commands" / "image.md").is_file())
        self.assertTrue((CLAUDE_X / "skills" / "x-image" / "SKILL.md").is_file())
        self.assertTrue((CODEX_X_IMAGE / ".codex-plugin" / "plugin.json").is_file())
        self.assertTrue((CODEX_X_IMAGE / "skills" / "x-image" / "SKILL.md").is_file())

    def test_old_cover_entry_points_are_removed(self):
        self.assertFalse((CLAUDE_X / "commands" / "cover.md").exists())
        self.assertFalse((CLAUDE_X / "skills" / "x-cover").exists())
```

- [ ] **Step 3: Write failing Claude bridge tests**

`test_claude_bridge.py` must require:

```python
import unittest

from helpers import CLAUDE_X, read


class ClaudeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.command = read(CLAUDE_X / "commands" / "image.md")
        self.skill = read(CLAUDE_X / "skills" / "x-image" / "SKILL.md")
        self.text = self.command + "\n" + self.skill

    def test_delegates_to_codex_rescue_once(self):
        self.assertIn("codex:codex-rescue", self.text)
        self.assertIn("--fresh", self.text)
        self.assertIn("--wait", self.text)
        self.assertIn("verbatim", self.text.lower())

    def test_has_no_owned_codex_or_image_pipeline(self):
        forbidden = ["codex exec", "cover-gen.sh", "magick", "sips", "image_gen("]
        for value in forbidden:
            self.assertNotIn(value, self.text)
```

- [ ] **Step 4: Write failing Codex plugin and shared-source tests**

Split responsibilities so each task can reach GREEN without depending on later tasks:

- `test_shared_source.py`: all six reference files and all three style files exist in `x/shared/x-image/`. Do not assert Codex links or plugin metadata here.
- `test_codex_plugin.py`: Codex manifest name is `x-image`, version is `0.1.0`, skills path is `./skills`; `.agents/plugins/marketplace.json` contains a local `x-image` entry; the Codex `references` and `styles` paths resolve to the shared source; the installer declares the approved marketplace, plugin name, and local version. Do not assert Claude metadata here.
- `test_structure.py`: the new Claude and Codex entry points exist, the old cover entry points are removed, and the Claude plugin plus Claude marketplace versions are `2.0.0`. Do not add fixture or acceptance-record assertions until Task 6.
- `test_claude_bridge.py`: only Claude command/skill delegation behavior.
- `test_prompt_contract.py` and `test_style_contract.py`: only shared routing, output, size, prompt, style, and QA content that Task 2 implements.

- [ ] **Step 5: Write failing prompt and style contract tests**

Require the shared text to contain:

- `exactly once`
- `built-in image_gen`
- `no retry`
- `no edit`
- `no post-processing`
- `actual dimensions`
- `3:1`
- all five recommended ratios
- the three style IDs
- explicit user style precedence
- locked style across a set
- exact visible text and data requirements

Add explicit behavior assertions for:

- A path-only request defaults to exactly one cover.
- Explicit cover or illustration language overrides the path-only default.
- An illustration request without a count defaults to exactly one strongest cognitive anchor.
- File sources save to a sibling `images/` directory.
- Directory sources save to `<source-dir>/images/`.
- Direct text, data, and brief inputs save to `<cwd>/images/`.
- Existing destination filenames are never overwritten; collisions resolve deterministically as `-v2`, then `-v3`, and so on.
- A user ratio overrides the intent preset when it is at most `3:1`.
- Ratios wider than `3:1` are rejected with the nearest valid alternative.
- Multi-image generation stops after the first failed asset while preserving already completed originals.
- Global hard constraints remain active even when the user supplies a custom or explicit style.

Require production Markdown and scripts under the planned x-image paths not to contain:

```python
forbidden = [
    "codex exec",
    "magick",
    "sips",
    "ImageMagick",
    "generate-batch",
    "image_gen.py",
]
```

- [ ] **Step 6: Run the suite and verify RED**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: FAIL because the new Claude command, shared rules, and Codex plugin do not yet exist, while the old cover paths still exist.

Do not change the tests to make them pass.

- [ ] **Step 7: Record and commit the initial RED baseline**

Create `targets/codex/x-image/tests/tdd-log.md` and record the command, expected failure, and actual failing test names from Step 6. Leave the GREEN fields as `PENDING` for behaviors not implemented yet.

Commit the failing tests before creating production files:

```bash
git add targets/codex/x-image/tests
git commit -m "test(x-image): define failing behavior contracts"
```

Verify the committed suite is still RED. A failing test commit is intentional at this checkpoint.

---

### Task 2: Add the Shared Routing, Size, Style, Prompt, and QA Source

**Files:**
- Create: `x/shared/x-image/references/intent-routing.md`
- Create: `x/shared/x-image/references/size-presets.md`
- Create: `x/shared/x-image/references/style-policy.md`
- Create: `x/shared/x-image/references/layout-patterns.md`
- Create: `x/shared/x-image/references/prompt-contract.md`
- Create: `x/shared/x-image/references/qa-checklist.md`
- Create: `x/shared/x-image/styles/terminal-tech.md`
- Create: `x/shared/x-image/styles/editorial-material.md`
- Create: `x/shared/x-image/styles/data-editorial.md`
- Test: `targets/codex/x-image/tests/test_shared_source.py`
- Test: `targets/codex/x-image/tests/test_prompt_contract.py`
- Test: `targets/codex/x-image/tests/test_style_contract.py`

- [ ] **Step 1: Run shared-source tests alone and confirm RED**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_shared_source.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_prompt_contract.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_style_contract.py' -v
```

Expected: FAIL with missing shared reference and style files.

Append this focused RED run and the observed failures to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 2: Implement intent and size rules**

`intent-routing.md` must define:

- File, directory, direct-text, data, and brief inputs.
- Path-only requests default to one cover.
- Explicit cover/illustration words override the default.
- Illustration without count defaults to one strongest cognitive anchor.
- Explicit multi-image count creates one independent asset plan per image.
- A failure stops remaining calls while preserving completed outputs.
- Output location defaults for every source type.
- File input destinations resolve to the source file's sibling `images/`; directory inputs resolve to `<source-dir>/images/`; direct text, data, and briefs resolve to `<cwd>/images/`.
- Before placement, probe the complete destination filename. If it exists, preserve it and append `-v2`; continue with `-v3`, `-v4`, and so on until an unused filename is found.
- Never overwrite an existing asset.

`size-presets.md` must include the five approved presets and state:

```text
The ratio is a composition requirement.
The pixel dimensions are prompt targets, not guaranteed built-in ImageGen output.
Never crop, resize, pad, or re-encode the result to force dimensions.
Reject ratios above 3:1 and recommend the nearest valid alternative.
Always report actual output dimensions when available.
```

- [ ] **Step 3: Implement style policy and presets**

`style-policy.md` must encode the merge precedence:

```text
explicit user request
> asset intent
> content semantics
> default preset
```

After that merge, apply global hard constraints as a non-overridable validation layer. An explicit or custom user style may change the preset fields but may never disable legibility, factual accuracy, one-call generation, no-retry, no-post-processing, ratio safety, or other global hard constraints.

Each style file must contain the fields:

```text
id
use-for
background
palette
accent
medium
lighting
composition
text-rules
avoid
```

Implement the exact three approved styles and their constraints from the spec.

- [ ] **Step 4: Implement layout, prompt, and QA contracts**

`layout-patterns.md` must cover:

- Cover: hero title, hero number, comparison, trend, structure, annotated object.
- Illustration: cycle, pipeline, hub-and-spoke, before/after, layer stack, data scene, scientific mechanism, symbolic scene.
- One primary focal point per asset.

`prompt-contract.md` must contain the approved final prompt schema and explicitly require:

```text
Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Do not edit, retry, crop, resize, overlay, composite, or re-encode the result.
```

`qa-checklist.md` must define P0, P1, and P2 findings and require FAIL without regeneration for P0/P1.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_shared_source.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_prompt_contract.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_style_contract.py' -v
```

Expected: PASS.

Append the focused GREEN commands and observed passing result to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 6: Commit**

```bash
git add x/shared/x-image targets/codex/x-image/tests/tdd-log.md
git commit -m "feat(x-image): add shared image generation contracts"
```

Ensure root `AGENTS.md` is not staged.

---

### Task 3: Add the Native Codex `x-image` Plugin

**Files:**
- Create: `targets/codex/x-image/.codex-plugin/plugin.json`
- Create: `targets/codex/x-image/skills/x-image/SKILL.md`
- Create: `targets/codex/x-image/skills/x-image/references` (repository-relative link)
- Create: `targets/codex/x-image/skills/x-image/styles` (repository-relative link)
- Create: `targets/codex/x-image/scripts/install-local-plugin.sh`
- Create: `targets/codex/x-image/README.md`
- Modify: `.agents/plugins/marketplace.json`
- Test: `targets/codex/x-image/tests/test_codex_plugin.py`
- Test: `targets/codex/x-image/tests/test_shared_source.py`

- [ ] **Step 1: Run Codex plugin tests and confirm RED**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_codex_plugin.py' -v
```

Expected: FAIL because manifest, skill, marketplace entry, and installer do not exist.

Append the focused RED command and observed failure to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 2: Create the Codex plugin manifest**

Use:

```json
{
  "name": "x-image",
  "version": "0.1.0",
  "description": "Generate complete X article covers and article illustrations with one built-in ImageGen call per asset.",
  "skills": "./skills",
  "interface": {
    "displayName": "X Image",
    "shortDescription": "One-call covers and article illustrations",
    "longDescription": "Generate complete X article covers, article heroes, explainers, data visuals, and vertical illustrations. Codex selects ratio, style, and layout, then calls built-in ImageGen exactly once per asset with no image post-processing.",
    "developerName": "J. Liu",
    "category": "Productivity",
    "capabilities": ["Skills", "Image generation", "Article workflow"],
    "defaultPrompt": [
      "给这篇 X 文章生成一张封面",
      "为这篇文章生成一张正文解释图",
      "Create two consistent article illustrations from this Markdown file"
    ],
    "brandColor": "#1DA1F2"
  }
}
```

- [ ] **Step 3: Create the native Codex skill**

The Codex `SKILL.md` must:

- Use the shared references and style presets.
- Read source material itself.
- Resolve intent, count, destination, size, style, and layout.
- Resolve file/directory/direct-input output directories and collision-safe `-v2`, `-v3`, and later filenames without overwriting.
- Use the installed `imagegen` skill and built-in `image_gen`.
- Make exactly one call per planned asset.
- Copy the selected original result from the Codex generated-images location.
- Inspect without editing.
- Report final prompt, style ID, actual dimensions, output path, host, and QA.
- Stop remaining multi-image calls after failure.
- Never invoke Codex Rescue or a nested Codex task.

- [ ] **Step 4: Link shared references and styles**

From `targets/codex/x-image/skills/x-image/`, create:

```bash
ln -s ../../../../../x/shared/x-image/references references
ln -s ../../../../../x/shared/x-image/styles styles
```

Verify:

```bash
test -f targets/codex/x-image/skills/x-image/references/prompt-contract.md
test -f targets/codex/x-image/skills/x-image/styles/terminal-tech.md
```

Expected: both commands exit 0.

- [ ] **Step 5: Add marketplace registration and installer**

Add this entry to `.agents/plugins/marketplace.json`:

```json
{
  "name": "x-image",
  "source": {
    "source": "local",
    "path": "./targets/codex/x-image"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

Model `install-local-plugin.sh` after the existing Codex target installers, with:

```text
PLUGIN_NAME=x-image
MARKETPLACE_NAME=local-build-your-system
PLUGIN_VERSION=local
```

Important: copy from the real `TARGET_ROOT` with `rsync -aL`, not from the `~/plugins/x-image` symlink, so repository-relative shared links resolve correctly before being dereferenced into cache.

- [ ] **Step 6: Run Codex plugin tests and install smoke test**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_codex_plugin.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_shared_source.py' -v
zsh targets/codex/x-image/scripts/install-local-plugin.sh
```

Expected:

- Tests PASS.
- Cache exists at `~/.codex/plugins/cache/local-build-your-system/x-image/local`.
- Cached `references` and `styles` are real directories/files, not links to the repository.

Append the focused GREEN commands and observed results to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 7: Commit**

```bash
git add .agents/plugins/marketplace.json targets/codex/x-image
git commit -m "feat(x-image): add native Codex plugin"
```

---

### Task 4: Add the Claude `/x:image` Codex Rescue Bridge

**Files:**
- Create: `x/commands/image.md`
- Create: `x/skills/x-image/SKILL.md`
- Test: `targets/codex/x-image/tests/test_claude_bridge.py`

- [ ] **Step 1: Run Claude bridge tests and confirm RED**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_claude_bridge.py' -v
```

Expected: FAIL because the new command and skill do not exist.

Append the focused RED command and observed failure to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 2: Create `/x:image`**

Command frontmatter:

```yaml
---
description: "Generate a complete X article cover or article illustration through Codex x-image, using one ImageGen call per asset and no post-processing."
argument-hint: "<source> [cover|illustration] [count] [ratio/style/destination notes]"
allowed-tools: Agent
---
```

Command behavior:

1. Invoke `codex:codex-rescue` through the Agent tool.
2. Forward `$ARGUMENTS` plus the current working directory.
3. Include `--fresh --wait`.
4. Tell Codex to use the native `x-image` skill.
5. Require the complete workflow, file output, and QA inside Codex.
6. Return Codex stdout verbatim.
7. If the rescue agent is unavailable or unauthenticated, instruct the user to run `/codex:setup`.

Do not call another slash command recursively.

- [ ] **Step 3: Create the Claude natural-language bridge skill**

The Claude `SKILL.md` must be a thin adapter:

```yaml
---
name: x-image
description: Use when the user wants an X article cover, article illustration, explainer, data visual, or custom-ratio article image. In Claude Code, delegate the complete task to the Codex x-image skill through codex:codex-rescue.
---
```

It must repeat the same fresh-foreground delegation contract and forbid Claude-side article analysis, ImageGen calls, file inspection, retries, and post-processing.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_claude_bridge.py' -v
```

Expected: PASS.

Append the focused GREEN command and observed result to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 5: Commit**

```bash
git add x/commands/image.md x/skills/x-image/SKILL.md \
  targets/codex/x-image/tests/tdd-log.md
git commit -m "feat(x-image): add Claude Codex Rescue bridge"
```

---

### Task 5: Remove `x-cover` and Update Claude Plugin Metadata

**Files:**
- Delete: `x/commands/cover.md`
- Delete: `x/skills/x-cover/SKILL.md`
- Delete: `x/skills/x-cover/references/prompt-template.md`
- Delete: `x/skills/x-cover/scripts/cover-gen.sh`
- Modify: `x/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `x/README.md`
- Modify: `x/CHANGELOG.md`
- Modify: `README.md`
- Test: `targets/codex/x-image/tests/test_structure.py`

- [ ] **Step 1: Run removal and metadata tests and confirm RED**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v
```

Expected: FAIL while old cover files remain and plugin versions/descriptions are stale.

Append the focused RED command and observed failure to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 2: Delete the old workflow**

Delete the four old x-cover files/directories listed above. Do not preserve an alias command or compatibility skill.

- [ ] **Step 3: Update versions and descriptions**

Set:

- `x/.claude-plugin/plugin.json` version to `2.0.0`.
- `.claude-plugin/marketplace.json` x entry version to `2.0.0`.
- Descriptions to mention `x-image`, `/x:image`, covers, article illustrations, Codex Rescue, and one-call ImageGen.

Add a `2.0.0` changelog entry with:

- `/x:cover` removed.
- `/x:image` added.
- Covers and article illustrations supported.
- Claude execution delegated through Codex Rescue.
- No image post-processing or automatic retries.

- [ ] **Step 4: Rewrite user documentation**

Update examples:

```text
/x:image articles/example
/x:image article.md 生成一张正文解释图
/x:image article.md 生成 2 张 3:2 插图，统一浅色材质风
/x:image article.md 封面，深色终端风
```

Remove all claims about:

- `cover-gen.sh`
- ImageMagick or `sips`
- thumbnail generation
- crop gates
- `/x:cover`

Document the Codex plugin requirement and `/codex:setup`.

- [ ] **Step 5: Run focused and full tests**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: PASS.

Append the focused and full GREEN commands and observed results to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 6: Commit**

```bash
git add x .claude-plugin/marketplace.json README.md \
  targets/codex/x-image/tests/tdd-log.md
git commit -m "refactor(x): replace x-cover with x-image"
```

Before committing, verify root `AGENTS.md` is absent from `git diff --cached --name-only`.

---

### Task 6: Add Fixtures and Acceptance Record Contracts

**Files:**
- Create: `targets/codex/x-image/tests/fixtures/tech-article.md`
- Create: `targets/codex/x-image/tests/fixtures/data-article.md`
- Create: `targets/codex/x-image/tests/fixtures/explainer-article.md`
- Create: `targets/codex/x-image/tests/fixtures/humanities-article.md`
- Create: `targets/codex/x-image/tests/acceptance/cover-2_5x1.md`
- Create: `targets/codex/x-image/tests/acceptance/hero-16x9.md`
- Create: `targets/codex/x-image/tests/acceptance/explainer-3x2.md`
- Create: `targets/codex/x-image/tests/acceptance/vertical-3x4.md`
- Create: `targets/codex/x-image/tests/acceptance/data-editorial.md`
- Create: `targets/codex/x-image/tests/acceptance/custom-style.md`
- Create: `targets/codex/x-image/tests/acceptance/multi-image.md`
- Create: `targets/codex/x-image/tests/acceptance/output/.gitignore`
- Modify: `targets/codex/x-image/tests/test_structure.py`

- [ ] **Step 1: Add failing fixture and acceptance-record tests**

Require all four fixtures and all seven acceptance records to exist. Require each acceptance record to contain:

```text
Status
Codex task or thread
Input fixture
Final prompt
Style ID
image_gen call count
ImageGen edit call count
Image modification command count
Saved output path
Actual dimensions
Content QA
Style QA
```

Run the focused test and confirm RED.

Append the focused RED command and observed failure to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 2: Create deterministic fixture content**

Fixtures must contain exact facts that can be visually checked:

- `tech-article.md`: a short open-source tool story with one exact Chinese title and one exact star count.
- `data-article.md`: four named categories, exact values, units, and an explicit ordering.
- `explainer-article.md`: a four-step workflow with four exact short Chinese labels.
- `humanities-article.md`: a symbolic concept that requires mood but contains no unverifiable historical claim.

- [ ] **Step 3: Create acceptance record templates**

Each record starts with `Status: NOT RUN` and includes:

- Exact Codex prompt to execute.
- Expected style and ratio.
- Maximum permitted tool calls.
- P0/P1/P2 checklist.
- Placeholders that are allowed only until the live acceptance task runs.

`output/.gitignore`:

```gitignore
*
!.gitignore
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_structure.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: PASS.

Append the focused and full GREEN commands and observed results to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 5: Commit**

```bash
git add targets/codex/x-image/tests
git commit -m "test(x-image): add fixtures and acceptance contracts"
```

---

### Task 7: Verify Installation and Full Static Regression

**Files:**
- Modify if required: `targets/codex/x-image/scripts/install-local-plugin.sh`
- Modify if required: `targets/codex/x-image/tests/test_codex_plugin.py`

- [ ] **Step 1: Run the complete static suite**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: all tests PASS with no warnings or skipped cases.

- [ ] **Step 2: Install the Codex plugin**

Run:

```bash
zsh targets/codex/x-image/scripts/install-local-plugin.sh
```

Expected:

- Personal marketplace entry is updated.
- Cache is recreated under `~/.codex/plugins/cache/local-build-your-system/x-image/local`.
- Shared references and styles exist as real cached files.

- [ ] **Step 3: Compare source and installed contracts**

Run:

```bash
diff -ru x/shared/x-image/references \
  ~/.codex/plugins/cache/local-build-your-system/x-image/local/skills/x-image/references

diff -ru x/shared/x-image/styles \
  ~/.codex/plugins/cache/local-build-your-system/x-image/local/skills/x-image/styles
```

Expected: no differences.

- [ ] **Step 4: Synchronize the Claude plugin cache**

Run:

```bash
mkdir -p "$HOME/.claude/plugins/cache/build-your-system/x/2.0.0"
bash scripts/sync-to-cache.sh
diff -ru x "$HOME/.claude/plugins/cache/build-your-system/x/2.0.0"
```

Expected:

- The repository creates the new local `2.0.0` cache directory before synchronization, so `sync-to-cache.sh` does not skip it.
- The source and `2.0.0` cache copy have no differences. If Claude creates a runtime-only `.in_use` marker, exclude only that marker from the comparison and document the exclusion.
- This cache copy is local verification evidence; it does not change the version selected by Claude's installed marketplace record.

For local development and Task 9 bridge acceptance, launch Claude with the source plugin explicitly:

```bash
claude --plugin-dir "$PWD/x"
```

Persistent activation of `x@build-your-system` version `2.0.0` requires publishing the marketplace update and then running:

```bash
claude plugin update x@build-your-system
```

Publishing or pushing is outside this plan unless the user separately authorizes it.

- [ ] **Step 5: Re-run tests after installation**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: PASS.

- [ ] **Step 6: Commit any required installer corrections**

If Task 7 exposes an installer defect, first add a failing assertion, record RED in `tdd-log.md`, make the minimum correction, run focused and full GREEN, and append the GREEN evidence. Then commit:

```bash
git add targets/codex/x-image/scripts targets/codex/x-image/tests
git commit -m "fix(x-image): harden local plugin installation"
```

If no corrections were required, do not create an empty commit.

---

### Task 8: Run Seven Live Codex + ImageGen Acceptance Cases

**Files:**
- Modify: `targets/codex/x-image/tests/acceptance/cover-2_5x1.md`
- Modify: `targets/codex/x-image/tests/acceptance/hero-16x9.md`
- Modify: `targets/codex/x-image/tests/acceptance/explainer-3x2.md`
- Modify: `targets/codex/x-image/tests/acceptance/vertical-3x4.md`
- Modify: `targets/codex/x-image/tests/acceptance/data-editorial.md`
- Modify: `targets/codex/x-image/tests/acceptance/custom-style.md`
- Modify: `targets/codex/x-image/tests/acceptance/multi-image.md`
- Write untracked outputs: `targets/codex/x-image/tests/acceptance/output/`

- [ ] **Step 1: Confirm live-test preconditions**

Verify:

```text
Codex x-image plugin is installed and discoverable.
Built-in imagegen is available.
Each acceptance task will be fresh.
Generated images will stay under the ignored acceptance output directory.
```

- [ ] **Step 2: Run AC-01 through AC-07 from Codex**

Run each acceptance prompt in a fresh Codex task:

1. 2.5:1 technology cover.
2. 16:9 article hero.
3. 3:2 labeled explainer.
4. 3:4 vertical illustration.
5. Data-led editorial image.
6. Explicit custom style.
7. Two-illustration request.

For each task:

- Use the installed native `x-image` skill.
- Observe the tool trace.
- Confirm exactly one `image_gen` call per asset.
- Confirm zero edit calls.
- Confirm zero image modification commands.
- Inspect the original output.
- Record actual path, dimensions, prompt, style ID, and QA.

- [ ] **Step 3: Handle acceptance failures correctly**

If a case has a P0 or P1 issue:

1. Mark the case `FAIL`.
2. Do not regenerate inside that task.
3. Add a failing static or contract test reproducing the missing rule when possible.
4. Run the new test and confirm RED.
5. Append the RED command and observed failure to `targets/codex/x-image/tests/tdd-log.md`.
6. Update the smallest shared prompt/style/QA rule.
7. Run the focused and full static suites and confirm GREEN.
8. Append the GREEN commands and observed results to `targets/codex/x-image/tests/tdd-log.md`.
9. Commit the test, rule correction, and TDD log together:

   ```bash
   git add x/shared/x-image targets/codex/x-image/tests
   git commit -m "fix(x-image): correct acceptance contract"
   ```

10. Start a new fresh acceptance task for that case.

This development iteration does not change the one-call production contract.

- [ ] **Step 4: Require release-grade results**

Before proceeding:

- AC-01 through AC-07 are `PASS`.
- No record contains a P0 or P1 finding.
- `image_gen` counts equal the number of requested assets.
- All generated files are original ImageGen outputs.

- [ ] **Step 5: Commit acceptance records**

Do not add ignored generated images.

```bash
git add targets/codex/x-image/tests/acceptance/*.md
git commit -m "test(x-image): record live Codex acceptance"
```

---

### Task 9: Validate the Claude Rescue Bridge

**Files:**
- Modify if required: `x/commands/image.md`
- Modify if required: `x/skills/x-image/SKILL.md`
- Modify: `targets/codex/x-image/tests/acceptance/claude-bridge.md`

- [ ] **Step 1: Add a Claude bridge acceptance record**

The record requires:

- `/x:image` invocation.
- One `codex:codex-rescue` agent call.
- Fresh foreground task.
- Native Codex `x-image` execution.
- Codex output returned verbatim.
- No Claude-side file inspection, ImageGen call, retry, or post-processing.

- [ ] **Step 2: Run the bridge smoke test**

Start Claude Code from the repository with the local source plugin:

```bash
claude --plugin-dir "$PWD/x"
```

Then run `/x:image` against `tech-article.md`, targeting the ignored acceptance output directory.

Expected:

- Claude delegates once.
- Codex generates and saves the asset.
- Claude returns the Codex report unchanged.

If the environment cannot run an interactive Claude Code smoke test, mark the record `BLOCKED` with the exact environmental blocker; do not substitute a Codex-native test and call the bridge verified.

- [ ] **Step 3: Fix bridge defects with TDD**

For any bridge defect:

1. Add a failing assertion to `test_claude_bridge.py`.
2. Confirm RED.
3. Append the RED command and observed failure to `targets/codex/x-image/tests/tdd-log.md`.
4. Make the minimum command/skill change.
5. Confirm focused and full GREEN.
6. Append the GREEN commands and observed results to `targets/codex/x-image/tests/tdd-log.md`.
7. Re-run the bridge smoke test.

- [ ] **Step 4: Commit**

```bash
git add x/commands/image.md x/skills/x-image/SKILL.md \
  targets/codex/x-image/tests/test_claude_bridge.py \
  targets/codex/x-image/tests/tdd-log.md \
  targets/codex/x-image/tests/acceptance/claude-bridge.md
git commit -m "test(x-image): verify Claude Rescue bridge"
```

---

### Task 10: Final Regression, Review, and Handoff

**Files:**
- Review all files changed by Tasks 1–9.
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run all automated tests**

Run:

```bash
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: all PASS, zero failures, zero errors.

- [ ] **Step 2: Validate manifests and JSON**

Run:

```bash
python3 -m json.tool x/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool targets/codex/x-image/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
```

Expected: all exit 0.

- [ ] **Step 3: Check forbidden legacy and post-processing paths**

Run:

```bash
test ! -e x/commands/cover.md
test ! -e x/skills/x-cover

rg -n --hidden --glob '!**/.git/**' \
  'cover-gen\\.sh|codex exec|magick|sips|ImageMagick|image_gen\\.py|generate-batch' \
  x/commands/image.md x/skills/x-image x/shared/x-image targets/codex/x-image
```

Expected:

- Both `test` commands exit 0.
- `rg` returns no production-contract violations. Test fixtures may quote forbidden strings only inside explicit assertions.

- [ ] **Step 4: Verify acceptance records**

Run:

```bash
rg -n '^Status: (NOT RUN|FAIL|BLOCKED)$' \
  targets/codex/x-image/tests/acceptance/*.md
```

Expected: no matches before release. If the Claude bridge is genuinely environment-blocked, stop and report the blocker rather than claiming full completion.

- [ ] **Step 5: Review staged scope**

Run:

```bash
git status --short
git diff --check
git diff --stat
```

Verify:

- Root `AGENTS.md` remains untracked and untouched.
- Generated acceptance images remain ignored.
- No unrelated files are staged.

- [ ] **Step 6: Request code review**

Use `superpowers:requesting-code-review` against the full implementation diff. Address only verified, in-scope findings using failing regression tests first. For every production correction, append its RED and GREEN evidence to `targets/codex/x-image/tests/tdd-log.md`.

- [ ] **Step 7: Run final verification after review**

Repeat Steps 1–5 and record the fresh output.

- [ ] **Step 8: Commit final review corrections if any**

If corrections were required:

```bash
git add x/commands/image.md x/skills/x-image x/shared/x-image \
  targets/codex/x-image x/.claude-plugin/plugin.json \
  .claude-plugin/marketplace.json .agents/plugins/marketplace.json \
  x/README.md x/CHANGELOG.md README.md \
  targets/codex/x-image/tests/tdd-log.md
git commit -m "fix(x-image): address final review findings"
```

Do not create an empty commit.

- [ ] **Step 9: Handoff**

Report:

- Claude command and plugin version.
- Codex plugin version and install path.
- Automated test totals.
- AC-01 through AC-07 results.
- Claude bridge result.
- ImageGen call counts.
- Any residual P2 observations.
- Cache synchronization status.
