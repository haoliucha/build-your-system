# AC-08 — Claude Rescue Bridge

Status: BLOCKED

Claude session: `3c74bf8e-8cb2-4423-9d4c-0659a8521129`

Claude launch command:

```text
claude --plugin-dir "$PWD/x" --permission-mode bypassPermissions --debug-file /tmp/x-image-claude-bridge-debug.log
```

Exact `/x:image` invocation:

```text
/x:image targets/codex/x-image/tests/fixtures/tech-article.md illustration 3:2 editorial-material; generate exactly one image showing one independent maker building an open-source research tool, with no visible text; save to targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge.png
```

Local Claude plugin: PASS — debug evidence confirms the source plugin loaded from `x/`, exposed three commands, and resolved `x:x-image` from version `2.0.0`.

Expected `codex:codex-rescue` agent call count: 1

Actual `codex:codex-rescue` agent call count: 0

Fresh foreground task: NOT STARTED

Native Codex `x-image` execution: NOT STARTED

Codex output returned verbatim: NOT AVAILABLE

Claude-side file inspection count: 0

Claude-side ImageGen call count: 0

Claude-side retry count: 0

Claude-side image modification or post-processing count: 0

Expected output path: `targets/codex/x-image/tests/acceptance/output/ac-08-claude-bridge.png`

Saved output path: NOT CREATED

Environmental blocker:

```text
API Error: invalid_grant
```

Claude Code was configured for Google Vertex AI and failed before its first model response. The debug log records eleven failed API attempts, all with `invalid_grant`, followed by termination of the turn. No Agent tool call was emitted, so the Rescue bridge and Codex generation stages were never entered.

Credential health evidence:

```text
$ claude auth status
{
  "loggedIn": true,
  "authMethod": "third_party",
  "apiProvider": "vertex"
}

$ gcloud auth application-default print-access-token
ERROR: (gcloud.auth.application-default.print-access-token) There was a problem refreshing your current auth tokens: ('invalid_grant: Bad Request', ...)
Please run:

  $ gcloud auth application-default login

to obtain new credentials.
```

The regular `gcloud auth print-access-token` check succeeds, but Claude's Vertex path uses Application Default Credentials, whose refresh grant is invalid. Re-authenticating ADC changes external credential state and requires user authorization, so the smoke test was not retried.

Release decision: BLOCKED — do not claim the Claude bridge verified and do not substitute a Codex-native acceptance run.
