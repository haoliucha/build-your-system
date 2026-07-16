---
name: x-image
description: Use when the user wants an X article cover, article illustration, explainer, data visual, article hero, vertical image, share image, or custom-ratio article image in Claude Code.
---

# X Image Claude Bridge

Delegate the entire request to the native Codex `x-image` skill. Claude does not own image-generation logic.

## Required delegation

Invoke `codex:codex-rescue` through the Agent tool exactly once:

- Use a fresh foreground run with `--fresh --wait`.
- Forward the user's request and the actual current working directory.
- Tell Codex to use the native `x-image` skill.
- Require Codex to own source analysis, asset planning, prompt compilation, one built-in ImageGen call per asset, collision-safe file placement, read-only inspection, and QA.
- Require Codex to save the output file and return the complete native report.

Return the Codex output verbatim with no text before or after it.

## Claude boundary

Do not read or analyze the article in Claude. Do not choose the intent, ratio, style, layout, prompt, or destination. Do not inspect output files. Do not call an image tool, retry, repair, or post-process. Do not perform QA in Claude.

If the rescue subagent is unavailable or Codex is unauthenticated, stop and instruct the user to run `/codex:setup`.

Do not invoke another slash command. The bridge calls the subagent directly.
