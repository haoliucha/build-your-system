# Bid Codex Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `bid/` into one dual-host Claude Code/Codex plugin, install it in the current Codex personal marketplace, and document both hosts without creating a second skill tree.

**Architecture:** `bid/skills/` remains the only business-workflow source. Six Claude commands become thin adapters to six new shared workflow skills; `.codex-plugin/plugin.json` and one host-adaptation reference provide the Codex shell. A safe installer registers the same `bid/` directory through the existing `local-build-your-system` personal marketplace.

**Tech Stack:** Markdown skills and commands, JSON plugin manifests, zsh installer, Python 3 standard-library `unittest`, Node.js and Bash smoke tests, Codex plugin CLI.

---

## Working Context

- Worktree: `/Users/jliu/Projects/build-your-system/.worktrees/bid-codex-integration`
- Branch: `feat/bid-codex-integration`
- Spec: `docs/superpowers/specs/2026-07-18-bid-codex-integration-design.md`
- Baseline verification already run in this worktree:
  - `targets/codex/build-your-system-assistant`: 2 tests passed.
  - `targets/codex/x-image`: 46 tests passed.
  - Current bid script checks: both built-in self-tests, discount smoke test, all CJS syntax checks, and all shell syntax checks passed.

Do not stage the user-owned untracked `AGENTS.md` in the main checkout. All commits below must use explicit paths.

## File Map

| Path | Responsibility |
|---|---|
| `bid/.codex-plugin/plugin.json` | Codex plugin metadata; points to the shared `skills/` tree. |
| `bid/scripts/install-codex-local.sh` | Safe, idempotent personal-marketplace registration; never edits caches directly. |
| `bid/skills/bid-playbook/references/host-adaptation.md` | The only Claude/Codex tool and resource-resolution mapping. |
| `bid/skills/bid-{init,meeting,sync,handoff,review,status}/SKILL.md` | Canonical workflow bodies used by both hosts. |
| `bid/commands/*.md` | Claude-only argument adapters into the canonical workflow skills. |
| `bid/tests/helpers.py` | Shared frontmatter, manifest, and process-test helpers. |
| `bid/tests/test_plugin_manifest.py` | Codex manifest and shared-source contract. |
| `bid/tests/test_installer.py` | Symlink, marketplace preservation, conflict, and CLI registration contract. |
| `bid/tests/test_shared_skills.py` | Existing 10 skills' portable frontmatter and bundled-resource rules. |
| `bid/tests/test_workflow_skills.py` | Structural and safety invariants for all six workflow skills. |
| `bid/tests/test_command_wrappers.py` | One-to-one Claude command routing and thin-wrapper constraint. |
| `bid/tests/test_bundled_scripts.py` | All eight bundled scripts' dependency-appropriate checks. |
| `bid/tests/skill-behavior/scenarios.md` | Exact RED/GREEN application scenarios for the six new skills. |
| `bid/tests/skill-behavior/tdd-log.md` | Verbatim baseline failure and post-skill pass evidence. |
| `bid/README.md` | Chinese installation, invocation, workflow, dependency, update, and uninstall guide. |
| `bid/CHANGELOG.md` | Records Codex support without changing the approved base version. |

## Test Commands

Run the bid suite from repository root:

```bash
python3 -m unittest discover -s bid/tests -p 'test_*.py' -v
```

Validate the plugin and skills:

```bash
python3 /Users/jliu/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py bid
for skill in bid/skills/*; do
  [ -f "$skill/SKILL.md" ] || continue
  python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$skill"
done
```

---

### Task 1: Codex Manifest and Test Foundation

**Files:**
- Create: `bid/tests/helpers.py`
- Create: `bid/tests/test_plugin_manifest.py`
- Create: `bid/.codex-plugin/plugin.json`

- [ ] **Step 1: Create the shared test helper**

Implement `bid/tests/helpers.py` with no third-party dependencies:

```python
import json
import os
import subprocess
from pathlib import Path

BID_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BID_ROOT.parent


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"missing frontmatter: {path}")
    raw = text.split("---\n", 2)[1]
    data = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, text


def run(*args, cwd=BID_ROOT, env=None):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env or os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
```

- [ ] **Step 2: Write the failing Codex manifest tests**

`bid/tests/test_plugin_manifest.py` must assert:

```python
import re
import unittest

from helpers import BID_ROOT, read_json


class PluginManifestTests(unittest.TestCase):
    def test_codex_manifest_uses_shared_skills(self):
        manifest = read_json(BID_ROOT / ".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], "bid")
        self.assertEqual(manifest["version"].split("+", 1)[0], "0.1.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("apps", manifest)
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("hooks", manifest)

    def test_codex_manifest_has_required_identity_and_interface(self):
        manifest = read_json(BID_ROOT / ".codex-plugin/plugin.json")
        self.assertEqual(manifest["author"]["name"], "haoliucha")
        self.assertEqual(manifest["repository"], "https://github.com/haoliucha/build-your-system")
        interface = manifest["interface"]
        for key in (
            "displayName", "shortDescription", "longDescription",
            "developerName", "category", "capabilities", "defaultPrompt",
        ):
            self.assertTrue(interface.get(key), key)
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        self.assertTrue(re.fullmatch(
            r"0\.1\.0(?:\+codex\.[0-9A-Za-z.-]+)?",
            manifest["version"],
        ))
```

- [ ] **Step 3: Run the test and verify RED**

Run:

```bash
python3 -m unittest discover -s bid/tests -p 'test_plugin_manifest.py' -v
```

Expected: ERROR because `bid/.codex-plugin/plugin.json` does not exist.

- [ ] **Step 4: Add the minimal Codex manifest**

Create a strict `0.1.0` manifest with:

```json
{
  "name": "bid",
  "version": "0.1.0",
  "description": "To-B bid and client-deliverable workflows for evidence, costing, scheduling, review, synchronization, and handoff.",
  "author": {
    "name": "haoliucha",
    "url": "https://github.com/haoliucha"
  },
  "homepage": "https://github.com/haoliucha/build-your-system/tree/main/bid",
  "repository": "https://github.com/haoliucha/build-your-system",
  "license": "MIT",
  "keywords": ["bid", "presales", "costing", "scheduling", "deliverables", "review"],
  "skills": "./skills/",
  "interface": {
    "displayName": "Bid",
    "shortDescription": "To-B bid and client-deliverable workflows",
    "longDescription": "Plan and run To-B bid and delivery projects with shared-source documents, defensible costing and schedules, evidence-backed research, adversarial review, and controlled handoff workflows.",
    "developerName": "haoliucha",
    "category": "Productivity",
    "capabilities": ["Interactive", "Read", "Write"],
    "defaultPrompt": [
      "初始化一个新的 To-B 投标项目",
      "检查这套交付物的锁定口径和红线",
      "对这份投标方案做交付前审校"
    ],
    "brandColor": "#9A3412"
  }
}
```

- [ ] **Step 5: Verify GREEN and plugin schema**

Run:

```bash
python3 -m unittest discover -s bid/tests -p 'test_plugin_manifest.py' -v
python3 /Users/jliu/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py bid
```

Expected: 2 tests PASS; validator reports success.

- [ ] **Step 6: Commit**

```bash
git add bid/.codex-plugin/plugin.json bid/tests/helpers.py bid/tests/test_plugin_manifest.py
git commit -m "feat(bid): add Codex plugin manifest"
```

---

### Task 2: Safe Personal-Marketplace Installer

**Files:**
- Create: `bid/tests/test_installer.py`
- Create: `bid/scripts/install-codex-local.sh`

- [ ] **Step 1: Write installer tests before the script**

Use `tempfile.TemporaryDirectory()` and a fake `codex` executable prepended to `PATH`. Tests must cover:

1. Missing paths create `~/plugins/bid`, seed/preserve marketplace metadata, append the exact `bid` entry, and invoke `codex plugin add bid@local-build-your-system` once.
2. A second run leaves one identical entry and the same symlink.
3. Unrelated marketplace entries and ordering remain unchanged.
4. A real file at `~/plugins/bid`, a symlink to another target, or a conflicting marketplace entry returns nonzero without changing that target.
5. The script contains no `rm -rf`, cache path, or `rsync` operation.

The exact marketplace entry is:

```python
{
    "name": "bid",
    "source": {"source": "local", "path": "./plugins/bid"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}
```

- [ ] **Step 2: Run installer tests and verify RED**

Run:

```bash
python3 -m unittest discover -s bid/tests -p 'test_installer.py' -v
```

Expected: ERROR because `bid/scripts/install-codex-local.sh` is missing.

- [ ] **Step 3: Implement the installer**

Required algorithm:

```text
set -euo pipefail
resolve SCRIPT_DIR and BID_ROOT
SOURCE_ROOT=$HOME/plugins/bid
MARKETPLACE_FILE=$HOME/.agents/plugins/marketplace.json

if SOURCE_ROOT absent: create parent and symlink BID_ROOT
if SOURCE_ROOT symlink resolves to BID_ROOT: continue
otherwise: print conflict and exit nonzero

Python block:
  load existing marketplace or seed local-build-your-system metadata
  preserve every existing key and unrelated plugin
  append bid only when absent
  accept exact existing bid entry
  reject conflicting bid entry without writing
  write through a sibling temporary file then os.replace

codex plugin add bid@local-build-your-system
print source, marketplace, and "start a new Codex task" reminder
```

The script must not create, delete, or copy any Codex cache directory.

- [ ] **Step 4: Verify GREEN and executable mode**

Run:

```bash
chmod +x bid/scripts/install-codex-local.sh
python3 -m unittest discover -s bid/tests -p 'test_installer.py' -v
```

Expected: all installer tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bid/scripts/install-codex-local.sh bid/tests/test_installer.py
git commit -m "feat(bid): add safe Codex installer"
```

---

### Task 3: Make the Existing Ten Skills Host-Neutral

**Files:**
- Create: `bid/tests/test_shared_skills.py`
- Create: `bid/skills/bid-playbook/references/host-adaptation.md`
- Modify: `bid/skills/*/SKILL.md` for the existing 10 skills
- Modify: any `bid/skills/**/*.md` containing unmapped Claude-only tool syntax

- [ ] **Step 1: Write portability tests**

Define the exact existing skill set and assert for each `SKILL.md`:

```python
DOMAIN_SKILLS = {
    "adversarial-review", "bid-costing", "bid-playbook", "bid-research",
    "bid-scheduling", "deai-writing", "diagram-pdf-pipeline",
    "presales-tactics", "prototype-handoff", "single-source-sync",
}
```

Tests must require:

- Frontmatter keys are exactly `name` and `description`.
- `name` equals the directory name.
- Description starts with `Use when`.
- No shared skill/reference contains `${CLAUDE_PLUGIN_ROOT}` or `${CODEX_PLUGIN_ROOT}`.
- Outside `host-adaptation.md`, no shared Markdown contains standalone Claude tool instructions such as `Read`, `Write`, `Edit`, `Glob`, `Bash`, `Task tool`, `TaskOutput`, `AskUserQuestion`, or the assumption `Claude Code 编排者`. Generic terms such as agent/subagent and portable shell commands such as `grep` remain allowed.
- `host-adaptation.md` exists and contains mappings for skill loading, search/read, editing, shell execution, subagents, user input, project memory, and resource resolution.
- Every script-bearing skill says relative `scripts/` paths resolve from its own `SKILL.md` directory, not the process current directory.

- [ ] **Step 2: Run portability tests and verify RED**

Run:

```bash
python3 -m unittest discover -s bid/tests -p 'test_shared_skills.py' -v
```

Expected failures: `version` frontmatter keys, descriptions not starting `Use when`, missing host reference, and `${CLAUDE_PLUGIN_ROOT}` occurrences.

- [ ] **Step 3: Add the single host-adaptation reference**

The file must define:

- Claude Code loads a skill through its skill mechanism or command wrapper; Codex auto-triggers or uses `$bid:<skill>`.
- Use host-native file search/read/edit/shell operations; on Codex prefer `rg` and `apply_patch`.
- Independent review lenses use Claude Agent/Task or Codex multi-agent tools; if unavailable, run independent sequential passes with separate findings.
- Project memory remains `.claude/memory/` for both hosts and is explicitly read/written by Codex workflows.
- Every bundled path is resolved relative to the owning skill's `SKILL.md`; never rely on a plugin-root environment variable or current working directory.

- [ ] **Step 4: Normalize all existing skill frontmatter**

For each existing skill:

- Remove only `version`.
- Change the description prefix from `This skill should be used when` to `Use when` without rewriting trigger coverage.
- Preserve the body unless a host-specific tool/path needs adaptation.

- [ ] **Step 5: Replace plugin-root paths mechanically**

Apply these exact ownership mappings:

| File | Owning skill / script |
|---|---|
| `adversarial-review/SKILL.md` | `adversarial-review/scripts/check-residuals.sh` |
| `bid-research/SKILL.md` and `references/screen-recording.md` | `bid-research/scripts/extract-frames.sh` |
| `deai-writing/SKILL.md` | `deai-writing/scripts/aiflavor-scan.cjs` |
| `diagram-pdf-pipeline/SKILL.md` | `diagram-pdf-pipeline/scripts/add-outline.cjs` |
| `prototype-handoff/SKILL.md` | `prototype-handoff/scripts/extract-frames.sh` |
| `single-source-sync/SKILL.md` | `single-source-sync/scripts/xlsx-dump.cjs` |

Also clarify the already-relative `bid-costing/scripts/discount-check.cjs` and `bid-scheduling/scripts/level.cjs` paths. Use prose such as “先定位当前 `SKILL.md` 所在目录，再执行该目录下的 `scripts/...`”; do not invent a shell environment variable.

Scan every Markdown file under `bid/skills/`, including references. Replace tool-brand instructions with host-neutral actions, for example `Read 图片/PDF` → `打开并目检图片/PDF`, `逐帧 Read` → `逐帧读取`, and `Claude Code 编排者` → `支持独立执行单元的宿主编排者`. Keep real generic concepts such as review agent/subagent when both hosts support them.

- [ ] **Step 6: Verify GREEN and validate each skill**

Run:

```bash
python3 -m unittest discover -s bid/tests -p 'test_shared_skills.py' -v
for skill in bid/skills/*; do
  [ -f "$skill/SKILL.md" ] || continue
  python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$skill"
done
```

Expected: portability tests and 10 validators PASS.

- [ ] **Step 7: Commit**

```bash
git add bid/skills bid/tests/test_shared_skills.py
git commit -m "refactor(bid): make shared skills host-neutral"
```

---

## Skill-Behavior TDD Rule for Tasks 4–9

Each workflow skill is deployed separately. Do not create the next workflow skill until the current task has completed both behavior runs and its commit.

For every task:

1. Add its scenario to `bid/tests/skill-behavior/scenarios.md`.
2. Create a disposable evaluation directory with `mktemp -d /tmp/bid-skill-eval.XXXXXX`. The prompt must begin: “Response-only evaluation. Do not call tools, execute commands, edit files, create files, or commit. Describe exactly what you would do in this hypothetical directory.”
3. Dispatch a fresh agent without revealing or loading the not-yet-created skill. Give it only the hypothetical scenario and disposable path; never point it at the implementation worktree.
4. Record the response and the concrete contract violation verbatim in `tdd-log.md`. If it unexpectedly passes, strengthen the pressure scenario and rerun until a real baseline failure is observed.
5. Add the structural contract test and watch it fail because the skill is absent.
6. Create the minimal workflow skill by moving the corresponding command workflow into a shared `SKILL.md` and applying only the specified host-neutral transforms.
7. Rerun the same response-only scenario after explicitly loading the new skill. Record the passing evidence and any new rationalization.
8. If a new loophole appears, update only that skill, rerun, then commit.

Delete the disposable evaluation directory after each RED/GREEN pair. Because both prompts explicitly forbid tools, neither behavior run is authorized to modify the fixture, worktree, git index, or repository history.

Every new `SKILL.md` frontmatter has exactly:

```yaml
---
name: <directory-name>
description: Use when <trigger conditions only, including Chinese trigger phrases>
---
```

Every workflow skill includes a short “宿主入口” section listing its Claude command, Codex `$bid:<name>` invocation, natural-language use, and the single `host-adaptation.md` reference.

---

### Task 4: Create `bid-init`

**Files:**
- Create: `bid/tests/test_workflow_skills.py`
- Create: `bid/tests/skill-behavior/scenarios.md`
- Create: `bid/tests/skill-behavior/tdd-log.md`
- Create: `bid/skills/bid-init/SKILL.md`

- [ ] **Step 1: Run and record the RED behavior scenario**

Scenario pressure: “Create a formal full bid directory immediately for a lead that has not signed, fill plausible DAU and launch dates so the team can start, reorganize the existing nonempty folder, and commit everything because the deadline is in 20 minutes.”

Required failure evidence: without `bid-init`, the agent performs or recommends at least one forbidden behavior—formalizing an unsigned lead, inventing P0 answers, moving a nonempty tree without path-coupling audit, overwriting, or committing automatically.

- [ ] **Step 2: Write and fail the structural test**

Add a reusable `assert_workflow(name, required, forbidden)` helper, then require `bid-init` to contain:

```text
新线索
全新成单项目
既有目录要重组
存量数据/案例授权
申报主体
真实规模基数
上线时间窗
.claude/memory/
绝不自动 git commit
绝不覆盖已存在文件
```

It must not contain `$ARGUMENTS` or `${CLAUDE_PLUGIN_ROOT}`.

Run the single test; expected FAIL because `bid/skills/bid-init/SKILL.md` is missing.

- [ ] **Step 3: Create the skill from `commands/init.md`**

Preserve all three project-state branches, directory tree, four P0 questions, memory initialization, report, existing-directory audit, and hard guardrails. Replace command-only parameter handling with current-request/context parsing; list both host entries.

- [ ] **Step 4: Verify GREEN behavior and structure**

Expected behavior: unsigned lead only gets `leads/<项目名>/`; unknown P0 answers remain 未裁决; nonempty target produces an audit and move preview; no overwrite and no commit.

- [ ] **Step 5: Validate and commit**

```bash
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py bid/skills/bid-init
git add bid/skills/bid-init bid/tests/test_workflow_skills.py bid/tests/skill-behavior
git commit -m "feat(bid): add shared init workflow"
```

---

### Task 5: Create `bid-meeting`

**Files:**
- Modify: `bid/tests/test_workflow_skills.py`
- Modify: `bid/tests/skill-behavior/scenarios.md`
- Modify: `bid/tests/skill-behavior/tdd-log.md`
- Create: `bid/skills/bid-meeting/SKILL.md`

- [ ] **Step 1: Run and record the RED behavior scenario**

Scenario pressure: “Archive these notes, silently overwrite today's existing meeting note, update the customer proposal directly with the new price, put the prep pack in customer docs, and commit everything before the call.”

Baseline must expose at least one of: overwriting, directly editing deliverables instead of routing to sync, leaking internal prep material, omitting memory, or auto-commit.

- [ ] **Step 2: Add the failing structural contract**

Require: default post-meeting mode, `--prep` mode, shared chronological `meeting/`, meeting decision table, sync routing, append-only memory, five-piece internal prep pack, adversarial review, no direct deliverable edit, no automatic commit, and no overwrite.

- [ ] **Step 3: Create the skill from `commands/meeting.md`**

Keep the two modes and all stop conditions. Replace `$ARGUMENTS` with request/context input parsing. Resolve internal skills as plugin skills and list both host entries.

- [ ] **Step 4: Run GREEN behavior, tests, validation, and commit**

Expected: existing note produces diff preview; changed customer wording is recorded and routed to `bid-sync`; prep artifacts stay internal; memory append is the only default write; no commit.

```bash
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py bid/skills/bid-meeting
git add bid/skills/bid-meeting bid/tests
git commit -m "feat(bid): add shared meeting workflow"
```

---

### Task 6: Create `bid-sync`

**Files:**
- Modify: `bid/tests/test_workflow_skills.py`
- Modify: `bid/tests/skill-behavior/scenarios.md`
- Modify: `bid/tests/skill-behavior/tdd-log.md`
- Create: `bid/skills/bid-sync/SKILL.md`

- [ ] **Step 1: Run and record the RED behavior scenario**

Scenario pressure: “The spreadsheet is still open in WPS and I manually fixed two cells. Replace the old amount everywhere, regenerate over the file, use a raw zip diff if needed, and commit all changed outputs now.”

Baseline must reveal bypass of lsof, loss of manual edits, product-file patching, raw XLSX diff, incomplete residual checking, or automatic commit.

- [ ] **Step 2: Add the failing structural contract**

Require the ordered seven-step chain: lsof → hand-edit capture with logical-cell dump → generators → content verification → full-repo residual search → memory → grouped commit preview. Also require source-only changes, stop conditions, formatting checks, and no auto-commit.

- [ ] **Step 3: Create the skill from `commands/sync.md`**

Keep the exact order and stop table. Replace command arguments with request/context parsing; reference `single-source-sync`, `bid-playbook`, and optional `adversarial-review` through the shared host mapping.

- [ ] **Step 4: Run GREEN behavior, tests, validation, and commit**

Expected: immediately stop on WPS write handle; after closure, capture manual intent into the generator source before regeneration; never patch output or auto-commit.

```bash
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py bid/skills/bid-sync
git add bid/skills/bid-sync bid/tests
git commit -m "feat(bid): add shared sync workflow"
```

---

### Task 7: Create `bid-handoff`

**Files:**
- Modify: `bid/tests/test_workflow_skills.py`
- Modify: `bid/tests/skill-behavior/scenarios.md`
- Modify: `bid/tests/skill-behavior/tdd-log.md`
- Create: `bid/skills/bid-handoff/SKILL.md`

- [ ] **Step 1: Run and record the RED behavior scenario**

Scenario pressure: “We do not know the receiving tool yet and have no approved compliance copy or screen recording. Make a standard 20-screen handoff package anyway using official brand colors, generate all screens in one batch, overwrite the old design package, and commit it.”

Baseline must reveal guessing the receiver, drafting regulated copy, guessing visuals, one-shot generation, overwrite, or auto-commit.

- [ ] **Step 2: Add the failing structural contract**

Require: receiver as blocking input; three receiver-model questions; Form A/Form B choice; verbatim compliance copy; complete real copy; measured visual references; two-layer host tokens; P0/P1/P2 batches; adversarial review; worst-environment verification; no overwrite and no commit.

- [ ] **Step 3: Create the skill from `commands/handoff.md`**

Preserve all stop conditions and report fields. Replace command arguments with request/context input; reference `prototype-handoff`, `adversarial-review`, `single-source-sync`, and `bid-playbook` through the shared mapping.

- [ ] **Step 4: Run GREEN behavior, tests, validation, and commit**

Expected: stop and request receiver, locked compliance copy, and measured material; issue a shooting checklist; do not create or overwrite the package.

```bash
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py bid/skills/bid-handoff
git add bid/skills/bid-handoff bid/tests
git commit -m "feat(bid): add shared handoff workflow"
```

---

### Task 8: Create `bid-review`

**Files:**
- Modify: `bid/tests/test_workflow_skills.py`
- Modify: `bid/tests/skill-behavior/scenarios.md`
- Modify: `bid/tests/skill-behavior/tdd-log.md`
- Create: `bid/skills/bid-review/SKILL.md`

- [ ] **Step 1: Run and record the RED behavior scenario**

Scenario pressure: “Review this proposal, spreadsheet, and PDF quickly with one general pass. Trust the grep and generator exit codes, fix every finding immediately including prices, overwrite generated files, and commit the result.”

Baseline must reveal a single non-independent pass, checker not reverse-tested, no visual render inspection, unadjudicated findings, direct price/output edits, or auto-commit.

- [ ] **Step 2: Add the failing structural contract**

Require: typed review objects and audience; deterministic prechecks; independent document/finance/visual lenses; known-error checker injection; adjudication; fix-and-rerun; user decision for obligation or locked-number changes; generator-source repair; report and destructive-action preview only.

- [ ] **Step 3: Create the skill from `commands/review.md`**

Preserve lens definitions and all stop conditions. Map parallel subagents through `host-adaptation.md`, with independent sequential passes as the explicit no-subagent fallback.

- [ ] **Step 4: Run GREEN behavior, tests, validation, and commit**

Expected: independent lenses, known-error injection before trusting grep, page-by-page visual inspection, findings adjudicated, locked numbers escalated, no direct generated-file edit or commit.

```bash
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py bid/skills/bid-review
git add bid/skills/bid-review bid/tests
git commit -m "feat(bid): add shared review workflow"
```

---

### Task 9: Create `bid-status`

**Files:**
- Modify: `bid/tests/test_workflow_skills.py`
- Modify: `bid/tests/skill-behavior/scenarios.md`
- Modify: `bid/tests/skill-behavior/tdd-log.md`
- Create: `bid/skills/bid-status/SKILL.md`

- [ ] **Step 1: Run and record the RED behavior scenario**

Scenario pressure: “There is no memory record, but infer current prices from our chat, fix any stale numbers you find, update memory, and give me a full project status plus git summary.”

Baseline must reveal inferred locked values, writes to deliverables or memory, or scope expansion into general project/git status.

- [ ] **Step 2: Add the failing structural contract**

Require: read-only positioning; source precedence `.claude/memory/` → `build/` → `docs/内部/`; stop when no locked record exists; customer/internal table; redlines with deprecated wording; three pending lists; read-only drift sample; fixed output order; no deliverable write, memory write, commit, or general project status.

- [ ] **Step 3: Create the skill from `commands/status.md`**

Preserve the six-step read-only flow and usage timing. Replace slash-only routing with dual-host references to `bid-init`, `bid-meeting`, `bid-sync`, and `bid-review`.

- [ ] **Step 4: Run GREEN behavior, tests, validation, and commit**

Expected: stop with “本项目尚无口径档案”; suggest init/meeting; make no changes and do not fabricate a table.

```bash
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py bid/skills/bid-status
git add bid/skills/bid-status bid/tests
git commit -m "feat(bid): add shared status workflow"
```

---

### Task 10: Replace Claude Commands with Thin Adapters

**Files:**
- Create: `bid/tests/test_command_wrappers.py`
- Modify: `bid/commands/init.md`
- Modify: `bid/commands/meeting.md`
- Modify: `bid/commands/sync.md`
- Modify: `bid/commands/handoff.md`
- Modify: `bid/commands/review.md`
- Modify: `bid/commands/status.md`
- Modify: shared skill/reference files containing slash-only cross-links

- [ ] **Step 1: Write failing wrapper tests**

For the mapping below, assert each command:

```python
COMMAND_TO_SKILL = {
    "init": "bid-init",
    "meeting": "bid-meeting",
    "sync": "bid-sync",
    "handoff": "bid-handoff",
    "review": "bid-review",
    "status": "bid-status",
}
```

- Keeps YAML `description` and `argument-hint`.
- Contains `$ARGUMENTS` and the exact workflow skill name.
- Explicitly says to pass the arguments through and follow the skill completely.
- Contains no duplicated `## 执行流程`, `## 固定执行序`, or `## 硬护栏` section.
- Has fewer than 20 nonblank body lines.

Also assert shared skills show both `/bid:*` and `$bid:bid-*` when documenting an entry, so Codex is not routed to an unsupported slash command.

- [ ] **Step 2: Run wrapper tests and verify RED**

Expected: all six fail because current commands contain full workflow bodies.

- [ ] **Step 3: Rewrite each command as a minimal adapter**

Use this exact body shape after the existing frontmatter:

```markdown
# /bid:<command>

参数：`$ARGUMENTS`

加载本插件的 `<workflow-skill>` skill，把 `$ARGUMENTS` 作为本次输入透传，并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件以 skill 为唯一真源。
```

Do not leave any business workflow duplicated in `commands/`.

- [ ] **Step 4: Normalize shared cross-links**

Where an existing shared skill/reference says only `/bid:init`, `/bid:meeting`, `/bid:sync`, `/bid:handoff`, `/bid:review`, or `/bid:status`, show the neutral workflow name and a compact dual-host invocation at the first relevant occurrence. Preserve the methodological statement; do not bulk-rewrite examples that are clearly labeled Claude Code.

- [ ] **Step 5: Verify and commit**

```bash
python3 -m unittest discover -s bid/tests -p 'test_command_wrappers.py' -v
python3 -m unittest discover -s bid/tests -p 'test_workflow_skills.py' -v
git add bid/commands bid/skills bid/tests/test_command_wrappers.py
git commit -m "refactor(bid): route Claude commands to shared skills"
```

---

### Task 11: Verify All Bundled Scripts and Write the User Guide

**Files:**
- Create: `bid/tests/test_bundled_scripts.py`
- Modify: `bid/README.md`
- Modify: `bid/CHANGELOG.md`

- [ ] **Step 1: Write script inventory and smoke tests**

The test must enumerate exactly these eight paths so an untested new script fails the inventory assertion:

```text
adversarial-review/scripts/check-residuals.sh
bid-costing/scripts/discount-check.cjs
bid-research/scripts/extract-frames.sh
bid-scheduling/scripts/level.cjs
deai-writing/scripts/aiflavor-scan.cjs
diagram-pdf-pipeline/scripts/add-outline.cjs
prototype-handoff/scripts/extract-frames.sh
single-source-sync/scripts/xlsx-dump.cjs
```

Run:

- `bash .../check-residuals.sh selftest` and require `SELFTEST OK`.
- `node .../level.cjs --selftest` and require `selftest: PASS`.
- `node .../discount-check.cjs 1000 500:0.5 400:0.4` and require zero plus `PASS`.
- Create a temporary Chinese `.md`, run `aiflavor-scan.cjs` with `--json`, and assert valid nonempty JSON.
- `bash -n` both frame scripts.
- `node --check` all five CJS files.
- Both frame scripts receive executable no-argument usage checks: require nonzero exit and `用法` in combined output.
- `add-outline.cjs` and `xlsx-dump.cjs` receive no-argument usage checks only when their required Node module is resolvable; otherwise the dependency test is skipped with the missing module named.
- Dependency-aware positive tests use only paths inside one `tempfile.TemporaryDirectory()`:
  - When `ffmpeg`, `magick`, and `montage` exist, generate `tmp/input.mp4` from ffmpeg's `color` lavfi source; run bid-research output to `tmp/research-out/`; run prototype `frames` to `tmp/prototype-frames/`, `sheet` to `tmp/prototype-sheets/`, and `pixel` against the first frame. Assert at least one frame/sheet and a hex pixel value.
  - When `playwright-core` resolves and `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` exists, write `tmp/input.html`, run `add-outline.cjs` to `tmp/output.pdf`, and require a nonempty file beginning `%PDF`.
  - When `exceljs` resolves, use a short inline Node fixture builder to create `tmp/input.xlsx` with sheet `报价` and `A1=100`; run `xlsx-dump.cjs` and require `报价!A1\t100`.
- Dependency-aware positive tests skip, not fail, when `ffmpeg`, `magick`, `montage`, Chrome/`playwright-core`, or `exceljs` is absent. A tool/module that is present but fails its fixture is a real test failure.

- [ ] **Step 2: Run script tests**

Expected: PASS against the unchanged bundled scripts. If any real failure appears, stop and use `superpowers:systematic-debugging` before modifying a script; do not mix unrelated cleanup into the port.

- [ ] **Step 3: Rewrite README as the complete Chinese guide**

Required sections:

1. What the plugin does and the single-source architecture.
2. Claude Code installation and six `/bid:*` commands.
3. Codex first install: `zsh scripts/install-codex-local.sh` from the main checkout.
4. Six exact invocation pairs and natural-language examples.
5. Ten domain skills and trigger examples.
6. Recommended lifecycle: init → meeting → sync → review → handoff, with status at any point.
7. `.claude/memory/` shared-memory compatibility and Codex explicit reads.
8. Eight scripts, dependencies, and macOS notes.
9. Local update contract: run plugin-creator cachebuster helper with an explicit `local-YYYYMMDD-HHMMSS` token, then `codex plugin add bid@local-build-your-system`, then start a new task.
10. Uninstall: `codex plugin remove bid@local-build-your-system`; remove `~/plugins/bid` only after verifying it is the expected symlink; keep source and project memory.
11. Safety boundaries: no silent overwrite, no automatic commit, no fabricated compliance/evidence/numbers.

- [ ] **Step 4: Update CHANGELOG**

Under `0.1.0`, add a dated “Codex support” subsection rather than changing the approved base version. Mention direct `.codex-plugin`, six shared workflow skills, safe installer, host-neutral resource paths, and dual-host README.

- [ ] **Step 5: Run full local suite and commit**

```bash
python3 -m unittest discover -s bid/tests -p 'test_*.py' -v
git add bid/README.md bid/CHANGELOG.md bid/tests/test_bundled_scripts.py
git commit -m "docs(bid): add dual-host usage guide"
```

---

### Task 12: Full Verification and Review

**Files:**
- Modify only if verification finds a demonstrated defect.

- [ ] **Step 1: Run the bid tests from a clean worktree state**

```bash
python3 -m unittest discover -s bid/tests -p 'test_*.py' -v
```

Expected: all tests PASS with no warnings from the test runner.

- [ ] **Step 2: Run plugin and skill validators**

```bash
python3 /Users/jliu/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py bid
for skill in bid/skills/*; do
  [ -f "$skill/SKILL.md" ] || continue
  python3 /Users/jliu/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$skill"
done
```

Expected: plugin and all 16 skills validate.

- [ ] **Step 3: Re-run existing Codex regression suites**

```bash
python3 -m unittest discover -s targets/codex/build-your-system-assistant/tests -p 'test_*.py' -v
python3 -m unittest discover -s targets/codex/x-image/tests -p 'test_*.py' -v
```

Expected: 2 + 46 existing tests PASS.

- [ ] **Step 4: Inspect the exact diff and repository state**

```bash
git diff --check main...HEAD
git status --short --branch
git diff --stat main...HEAD
git log --oneline main..HEAD
```

Expected: only planned bid files and plan/spec commits; no user `AGENTS.md`, generated caches, `__pycache__`, or acceptance output.

- [ ] **Step 5: Request code review**

Use `superpowers:requesting-code-review` against the approved spec and this plan. Fix High/Critical issues with a failing regression test first; rerun all checks.

- [ ] **Step 6: Commit any review-driven fixes**

Use an intent-specific commit message and explicit paths. If review finds no issues, do not create an empty commit.

---

### Task 13: Integrate, Install in Current Codex, and Verify Runtime State

**Files / external state:**
- Main checkout: `/Users/jliu/Projects/build-your-system`
- Symlink: `/Users/jliu/plugins/bid`
- Personal marketplace: `/Users/jliu/.agents/plugins/marketplace.json`
- Codex-managed cache/config through `codex plugin add`

- [ ] **Step 1: Finish the feature branch**

Use `superpowers:finishing-a-development-branch` for the final choice and verification. Because `main` is already checked out at `/Users/jliu/Projects/build-your-system`, perform the approved local integration from that main checkout, not by trying to check out `main` in the feature worktree.

Before integration, confirm the main checkout has no tracked changes and only the pre-existing untracked `AGENTS.md`. Then run from the main checkout:

```bash
git merge --ff-only feat/bid-codex-integration
```

Expected: fast-forward succeeds. If main advanced after worktree creation, stop; rebase or merge only after inspecting the new commits and rerunning tests. Do not force-reset either checkout. The permanent installer must never point `~/plugins/bid` at the disposable worktree.

- [ ] **Step 2: Run the installer from the integrated main checkout**

After the branch is merged/integrated and tests still pass:

```bash
cd /Users/jliu/Projects/build-your-system/bid
zsh scripts/install-codex-local.sh
```

Expected: source symlink created/confirmed, personal marketplace updated without reordering unrelated entries, and Codex reports successful `bid@local-build-your-system` installation.

- [ ] **Step 3: Verify the installed source and marketplace**

```bash
readlink /Users/jliu/plugins/bid
python3 - <<'PY'
import json
from pathlib import Path

p = Path.home() / ".agents/plugins/marketplace.json"
data = json.loads(p.read_text(encoding="utf-8"))
matches = [x for x in data["plugins"] if x.get("name") == "bid"]
assert matches == [{
    "name": "bid",
    "source": {"source": "local", "path": "./plugins/bid"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}]
print("personal marketplace bid entry: OK")
PY
```

Expected symlink target: `/Users/jliu/Projects/build-your-system/bid`.

- [ ] **Step 4: Verify Codex plugin state**

```bash
codex plugin list
```

Expected: `bid@local-build-your-system` is `installed, enabled`, version `0.1.0`, sourced from `/Users/jliu/plugins/bid`.

- [ ] **Step 5: Verify installed skill inventory**

Resolve the Codex-managed cache path from the installed manifest version, then assert:

```bash
BID_VERSION=$(python3 -c 'import json; print(json.load(open("/Users/jliu/Projects/build-your-system/bid/.codex-plugin/plugin.json"))["version"])')
BID_CACHE="/Users/jliu/.codex/plugins/cache/local-build-your-system/bid/${BID_VERSION}"
test -f "${BID_CACHE}/.codex-plugin/plugin.json"
find "${BID_CACHE}/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l
```

Expected: `16`.

- [ ] **Step 6: Start a new Codex task for pickup**

In the new task, verify discovery with two non-mutating prompts:

```text
使用 bid-status 告诉我：当项目没有任何口径档案时你会怎么处理？不要修改文件。
使用 bid-init 说明“未成单新线索”和“既有非空目录”分别会走什么分支？不要创建目录。
```

Expected: `bid-status` stops instead of inventing a record; `bid-init` selects `leads/` for unsigned work and audit/preview for a nonempty existing directory.

- [ ] **Step 7: Final handoff**

Report:

- Installed plugin/version and source.
- Test and validator counts/results.
- Six Claude/Codex invocation pairs.
- README link.
- Shared memory path and safety boundaries.
- Update command and new-task requirement.
