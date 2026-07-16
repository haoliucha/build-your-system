---
description: "Generate a complete X article cover or article illustration through Codex x-image, using one ImageGen call per asset and no post-processing."
argument-hint: "<source> [cover|illustration] [count] [ratio/style/destination notes]"
allowed-tools: Agent, TaskOutput
---

# /x:image

Delegate the complete request to Codex. Claude is only the transport layer.

## Invocation

Invoke the `codex:codex-rescue` subagent through the Agent tool exactly once with:

- `subagent_type: "codex:codex-rescue"`
- `run_in_background: false`
- this prompt:

```text
--fresh --wait

Work from the current working directory: <insert the current working directory>.
Use the native `x-image` skill to complete this request:

Invocation origin: Claude through Codex Rescue

$ARGUMENTS

Codex owns the complete workflow: source analysis, asset planning, prompt compilation, one built-in ImageGen call per asset, collision-safe file placement, read-only inspection, and QA. Save the requested file before reporting. Follow the x-image no-retry and no-post-processing contracts.

Return the complete native x-image report. Its first line must be exactly:
Host: Claude through Codex Rescue
```

Forward `$ARGUMENTS` without rewriting the user's intent. Include the actual current working directory in the prompt.

## Blocking compatibility

If the Agent tool still launches the subagent in the background, do not announce that state and do not return early. Call `TaskOutput` for the same Rescue task with:

- `block: true`
- the task ID returned by the Agent call
- a timeout long enough for the image workflow to finish

Use this compatibility wait only once. Do not invoke another Agent, start another Codex task, poll repeatedly, or expose task metadata to the user.

## Response contract

Do not announce delegation before the Agent call.

Do not emit progress or status messages while the Agent call is running.

On success, the only user-visible assistant message must be the complete Codex output verbatim, with no text before or after it. Do not summarize, inspect files, add commentary, call an image tool, retry, or perform follow-up work in Claude.

If `codex:codex-rescue` is unavailable or Codex is unauthenticated, stop and tell the user to run `/codex:setup`.

Do not call another slash command recursively.
