---
name: x-image
description: Use when the user wants an X article cover, article hero, inline explainer, data visual, vertical illustration, share image, or one or more article illustrations generated from a file, directory, text, data, or image brief.
---

# X Image

## Overview

Generate a complete final raster asset through the installed `imagegen` skill and built-in `image_gen`. Own source analysis, visual planning, prompt compilation, original-file placement, inspection, and QA in the current Codex task.

For each asset, allow exactly one call per planned asset. Use no edit, retry, post-processing, alternate image execution mode, or intermediate image.

## Load the canonical contracts

Before planning an image, read these files completely:

- `references/intent-routing.md`
- `references/size-presets.md`
- `references/style-policy.md`
- `references/layout-patterns.md`
- `references/prompt-contract.md`
- `references/qa-checklist.md`

After choosing a built-in Style ID, read the matching file under `styles/`. For a custom style, read all three built-in presets first so the task-local Style Spec preserves their level of precision.

## Workflow

### 1. Resolve the source

Determine whether the input is a file, directory, direct text, structured data, or brief.

- Read a named file directly.
- For a directory, choose `publish.md`, then `draft.md`, then the only Markdown file.
- If multiple source files remain plausible, ask one concise source-location question before continuing.
- Do not modify the source.

### 2. Resolve the complete asset plan

Before the first image call, determine:

- Intent: cover or illustration.
- Count: default or explicit.
- Destination directory and filename.
- Ratio and prompt target dimensions.
- Style ID and full Style Spec.
- Layout pattern.
- Exact visible text and exact data.

For multiple assets, plan every asset's distinct cognitive job and lock the shared style fields before generation.

Resolve a collision-safe destination before each call. Preserve existing files and choose `-v2`, `-v3`, or the first later unused sibling. Never overwrite.

### 3. Compile the final prompt

Follow `references/prompt-contract.md` exactly. Include all source-derived content, verbatim text, data semantics, ratio, target dimensions, full style, layout, safe margins, constraints, avoid items, and the complete single-call instruction.

Do not call the image tool until the prompt is complete and internally consistent.

### 4. Generate exactly once

Load the installed `imagegen` skill completely and use its default built-in `image_gen` path.

For the current asset:

1. Submit the compiled prompt in one generation call.
2. Do not call an edit operation.
3. Do not retry automatically for any reason.
4. If the call fails or no output file is returned, record the failure and stop remaining assets.

### 5. Place the original file

Use the output path returned by the built-in tool. Create only the resolved final output directory, then copy the original generated file to the collision-safe destination.

Do not transform the file while moving it. Reading file metadata or calculating a checksum is allowed; changing image bytes is not.

### 6. Inspect and decide QA

Always inspect without editing. Check the original asset against `references/qa-checklist.md`, including:

- Required subject, relationships, text, values, units, category order, and axes.
- Ratio composition, safe margins, focal point, Style ID, and avoid list.
- One generation call, zero edit calls, and zero image modification commands.
- Saved path and actual dimensions when available.

If the asset has a P0 or P1 finding, preserve it, mark it failed, and stop remaining assets. Do not repair or regenerate. A P2 observation may pass when meaning and legibility remain intact.

## Final report

For every attempted asset, report:

```text
Host: native Codex
Status: PASS or FAIL
Saved path:
Actual dimensions:
Style ID:
Final prompt:
Generation call count:
Edit call count:
Image modification command count:
Content QA:
Style QA:
P2 observations:
```

For a stopped multi-image request, also list completed, failed, and unattempted assets.

## Hard boundary

Execute directly in the current Codex task. Do not delegate generation to another task or agent. Do not upload, publish, edit the source article, or perform X account actions.
