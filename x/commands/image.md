---
description: "Generate a complete X article cover or article illustration through Codex x-image, using one ImageGen call per asset and no post-processing."
argument-hint: "<source> [cover|illustration] [count] [ratio/style/destination notes]"
allowed-tools: Agent
---

# /x:image

Delegate the complete request to Codex. Claude is only the transport layer.

## Invocation

Invoke the `codex:codex-rescue` subagent through the Agent tool exactly once with:

- `subagent_type: "codex:codex-rescue"`
- foreground execution
- this prompt:

```text
--fresh --wait

Work from the current working directory: <insert the current working directory>.
Use the native `x-image` skill to complete this request:

$ARGUMENTS

Codex owns the complete workflow: source analysis, asset planning, prompt compilation, one built-in ImageGen call per asset, collision-safe file placement, read-only inspection, and QA. Save the requested file before reporting. Follow the x-image no-retry and no-post-processing contracts.

Return the complete native x-image report.
```

Forward `$ARGUMENTS` without rewriting the user's intent. Include the actual current working directory in the prompt.

## Response contract

Return the Codex output verbatim. Do not summarize, inspect files, add commentary, call an image tool, retry, or perform follow-up work in Claude.

If `codex:codex-rescue` is unavailable or Codex is unauthenticated, stop and tell the user to run `/codex:setup`.

Do not call another slash command recursively.
