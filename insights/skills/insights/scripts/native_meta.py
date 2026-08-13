"""Deterministic usage metrics for Codex JSONL transcripts.

The public functions in this module mirror the non-model portion of Claude
Code's ``/insights`` pipeline while adapting it to the row shapes written by
Codex.  They deliberately accept already-decoded rows so inventory, tests and
the long-running helper all share one pure implementation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import PurePath
from typing import Any, Iterable, Mapping, Sequence


_LANGUAGES = {
    ".bash": "Shell",
    ".c": "C",
    ".cc": "C++",
    ".cjs": "JavaScript",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".cpp": "C++",
    ".cs": "C#",
    ".css": "CSS",
    ".cxx": "C++",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".fish": "Shell",
    ".fs": "F#",
    ".go": "Go",
    ".h": "C",
    ".hh": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".hs": "Haskell",
    ".htm": "HTML",
    ".html": "HTML",
    ".ipp": "C++",
    ".java": "Java",
    ".js": "JavaScript",
    ".json": "JSON",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".less": "CSS",
    ".lua": "Lua",
    ".md": "Markdown",
    ".mjs": "JavaScript",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".php": "PHP",
    ".ps1": "PowerShell",
    ".py": "Python",
    ".r": "R",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".sass": "CSS",
    ".scala": "Scala",
    ".scss": "CSS",
    ".sh": "Shell",
    ".sql": "SQL",
    ".svelte": "Svelte",
    ".swift": "Swift",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".zsh": "Shell",
}

_PATCH_PATH = re.compile(
    r"^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(.+?)\s*$", re.MULTILINE
)
_PATCH_MOVE_PATH = re.compile(r"^\*\*\*\s+Move to:\s*(.+?)\s*$", re.MULTILINE)
_UNIFIED_PATH = re.compile(r"^(?:\+\+\+|---)\s+(?:[ab]/)?(.+?)\s*$", re.MULTILINE)
_GIT_COMMIT = re.compile(r"\bgit\b[^\n;&|]*\bcommit\b", re.IGNORECASE)
_GIT_PUSH = re.compile(r"\bgit\b[^\n;&|]*\bpush\b", re.IGNORECASE)
_WRAPPED_TOOL = re.compile(r"\btools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("payload")
    return value if isinstance(value, Mapping) else {}


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_timestamp(row: Mapping[str, Any]) -> str:
    payload = _payload(row)
    value = row.get("timestamp", payload.get("timestamp", ""))
    return value if isinstance(value, str) else ""


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Mapping):
        for key in ("text", "input_text", "output_text", "message"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return ""
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        return "\n".join(part for part in (_content_text(item) for item in content) if part)
    return ""


def _message_rows(rows: Sequence[Mapping[str, Any]], role: str) -> list[dict[str, str]]:
    """Return one canonical stream per role, avoiding Codex's mirrored rows.

    Current Codex transcripts mirror user and assistant display messages into
    ``event_msg`` rows while also retaining request/response items.  The latter
    can contain injected app context under the user role, so event rows are the
    authoritative stream when present.  Older transcripts and synthetic input
    still fall back to response items.
    """

    event_types = {"user": {"user_message"}, "assistant": {"agent_message", "assistant_message"}}[role]
    event_messages: list[dict[str, str]] = []
    response_messages: list[dict[str, str]] = []

    for row in rows:
        payload = _payload(row)
        row_type = row.get("type")
        timestamp = _row_timestamp(row)
        if row_type == "event_msg" and _enum_text(payload.get("type")) in event_types:
            text = _content_text(payload.get("message", payload.get("content", ""))).strip()
            if text:
                event_messages.append({"timestamp": timestamp, "text": text})
        elif (
            row_type == "response_item"
            and payload.get("type", "message") == "message"
            and payload.get("role") == role
        ):
            text = _content_text(payload.get("content", "")).strip()
            if text:
                response_messages.append({"timestamp": timestamp, "text": text})

    return event_messages if event_messages else response_messages


def _json_text(value: Any) -> str:
    """Flatten a tool argument/output without depending on its serialization."""

    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in "[{\"" and stripped[-1:] in "]}\"":
            try:
                decoded = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                return value
            return _json_text(decoded)
        return value
    if isinstance(value, Mapping):
        return "\n".join(f"{key}: {_json_text(item)}" for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "\n".join(_json_text(item) for item in value)
    return "" if value is None else str(value)


def _tool_calls(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") != "response_item":
            continue
        payload = _payload(row)
        payload_type = _enum_text(payload.get("type"))
        if payload_type not in {"function_call", "custom_tool_call", "local_shell_call"}:
            continue
        name = payload.get("name")
        if not isinstance(name, str) or not name:
            # Some early local-shell rows omit a name but are still one call.
            name = "local_shell" if payload_type == "local_shell_call" else "unknown"
        raw_arguments = payload.get("arguments", payload.get("input", payload.get("action", "")))
        call_id = str(payload.get("call_id", payload.get("id", "")))
        argument_text = _json_text(raw_arguments)
        wrapped = list(dict.fromkeys(_WRAPPED_TOOL.findall(argument_text))) if name == "exec" else []
        if wrapped:
            for index, nested_name in enumerate(wrapped):
                calls.append(
                    {
                        "call_id": f"{call_id}:nested:{index}",
                        "parent_call_id": call_id,
                        "name": nested_name,
                        "arguments": raw_arguments,
                        "argument_text": argument_text,
                    }
                )
        else:
            calls.append(
                {
                    "call_id": call_id,
                    "name": name,
                    "arguments": raw_arguments,
                    "argument_text": argument_text,
                }
            )
    return calls


def _decoded_output(payload: Mapping[str, Any]) -> Any:
    value = payload.get("output", payload.get("result", payload.get("content", "")))
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _enum_text(value: Any) -> str:
    """Return a safe enum-like value; real Codex rows may use objects here."""

    return value.casefold() if isinstance(value, str) else ""


def _nonzero_exit(value: Any) -> bool:
    if isinstance(value, Mapping):
        exit_code = value.get("exit_code", value.get("exitCode"))
        if isinstance(exit_code, (int, float)) and exit_code != 0:
            return True
        return any(_nonzero_exit(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_nonzero_exit(item) for item in value)
    return False


def _error_category(text: str, tool_name: str) -> str:
    lowered = text.lower()
    if "rejected" in lowered or "doesn't want" in lowered or "user denied" in lowered:
        return "User Rejected"
    if "file changed" in lowered or "modified since" in lowered:
        return "File Changed"
    if "file too large" in lowered or "maximum file size" in lowered or "exceeds maximum" in lowered:
        return "File Too Large"
    if (
        "edit failed" in lowered
        or "patch failed" in lowered
        or "failed to apply" in lowered
        or "could not apply patch" in lowered
        or "string to replace not found" in lowered
        or "no changes" in lowered
    ):
        return "Edit Failed"
    if (
        "file not found" in lowered
        or "no such file" in lowered
        or "notfounderror" in lowered
        or "does not exist" in lowered
    ):
        return "File Not Found"
    if (
        "command failed" in lowered
        or "exit code" in lowered
        or tool_name in {"exec", "exec_command", "local_shell", "shell"}
    ):
        return "Command Failed"
    return "Other"


def _tool_errors(
    rows: Sequence[Mapping[str, Any]], calls: Sequence[Mapping[str, Any]]
) -> tuple[int, dict[str, int]]:
    names_by_id = {str(call.get("call_id", "")): str(call.get("name", "")) for call in calls}
    categories: dict[str, int] = {}
    count = 0

    for row in rows:
        payload = _payload(row)
        row_type = row.get("type")
        payload_type = _enum_text(payload.get("type"))
        is_output = row_type == "response_item" and payload_type in {
            "function_call_output",
            "custom_tool_call_output",
            "local_shell_call_output",
        }
        is_failed_event = (
            row_type == "event_msg"
            and isinstance(payload_type, str)
            and payload_type.endswith("_end")
            and (
                payload.get("success") is False
                or _enum_text(payload.get("status")) in {"failed", "error"}
            )
        )
        if not (is_output or is_failed_event):
            continue

        decoded = _decoded_output(payload)
        failed = bool(payload.get("is_error")) or payload.get("success") is False
        failed = (
            failed
            or _enum_text(payload.get("status")) in {"failed", "error"}
            or _nonzero_exit(decoded)
        )
        if not failed:
            continue

        call_id = str(payload.get("call_id", payload.get("id", "")))
        tool_name = names_by_id.get(call_id, str(payload.get("name", "")))
        text = _json_text(decoded)
        category = _error_category(text, tool_name)
        categories[category] = categories.get(category, 0) + 1
        count += 1

    return count, dict(sorted(categories.items()))


def _patch_stats(patch: str) -> tuple[int, int]:
    added = removed = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _patch_paths(patch: str) -> set[str]:
    paths = set(_PATCH_PATH.findall(patch)) | set(_PATCH_MOVE_PATH.findall(patch))
    for path in _UNIFIED_PATH.findall(patch):
        if path != "/dev/null":
            paths.add(path)
    return {path.strip() for path in paths if path.strip()}


def _file_metrics(
    rows: Sequence[Mapping[str, Any]], calls: Sequence[Mapping[str, Any]]
) -> tuple[int, int, int, dict[str, int]]:
    paths: set[str] = set()
    lines_added = lines_removed = 0
    patch_call_ids: set[str] = set()

    for call in calls:
        name = str(call.get("name", "")).lower()
        argument_text = str(call.get("argument_text", ""))
        if "apply_patch" in name or "*** begin patch" in argument_text.lower():
            call_id = str(call.get("call_id", ""))
            if call_id:
                patch_call_ids.add(call_id)
            added, removed = _patch_stats(argument_text)
            lines_added += added
            lines_removed += removed
            paths.update(_patch_paths(argument_text))

    # Completion events are authoritative for the affected path set.  Their
    # content is only a line-count fallback for transcript generations that did
    # not retain the original apply_patch call.
    fallback_added = fallback_removed = 0
    for row in rows:
        payload = _payload(row)
        if row.get("type") != "event_msg" or payload.get("type") != "patch_apply_end":
            continue
        changes = payload.get("changes")
        if not isinstance(changes, Mapping):
            continue
        has_retained_patch = str(payload.get("call_id", "")) in patch_call_ids
        for raw_path, change in changes.items():
            paths.add(str(raw_path))
            if has_retained_patch or not isinstance(change, Mapping):
                continue
            content = change.get("content")
            line_count = len(str(content).splitlines()) if isinstance(content, str) else 0
            change_type = str(change.get("type", "")).lower()
            if change_type == "add":
                fallback_added += line_count
            elif change_type == "delete":
                fallback_removed += line_count

    lines_added += fallback_added
    lines_removed += fallback_removed

    language_counts: dict[str, int] = {}
    for path in paths:
        language = _LANGUAGES.get(PurePath(path).suffix.lower())
        if language:
            language_counts[language] = language_counts.get(language, 0) + 1

    return lines_added, lines_removed, len(paths), dict(sorted(language_counts.items()))


def _latest_tokens(rows: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    input_tokens = output_tokens = 0
    for row in rows:
        payload = _payload(row)
        if row.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        usage = info.get("total_token_usage") if isinstance(info, Mapping) else None
        if not isinstance(usage, Mapping):
            continue
        raw_input = usage.get("input_tokens")
        raw_output = usage.get("output_tokens")
        input_tokens = int(raw_input) if isinstance(raw_input, (int, float)) else 0
        output_tokens = int(raw_output) if isinstance(raw_output, (int, float)) else 0
    return input_tokens, output_tokens


def _response_times(
    users: Sequence[Mapping[str, str]], assistants: Sequence[Mapping[str, str]]
) -> list[float]:
    assistant_times = sorted(
        timestamp for item in assistants if (timestamp := _timestamp(item.get("timestamp"))) is not None
    )
    result: list[float] = []
    for user in users:
        user_time = _timestamp(user.get("timestamp"))
        if user_time is None:
            continue
        previous = [stamp for stamp in assistant_times if stamp < user_time]
        if not previous:
            continue
        delay = (user_time - previous[-1]).total_seconds()
        if 2 < delay < 3600:
            result.append(float(delay))
    return result


def extract_native_session_meta(
    rows: Iterable[Mapping[str, Any]], *, transcript_mtime: float, origin: str
) -> dict[str, Any]:
    """Extract Claude-compatible deterministic metrics from Codex rows."""

    canonical_rows = list(rows)
    session_payload: Mapping[str, Any] = {}
    session_row: Mapping[str, Any] | None = None
    for row in canonical_rows:
        if row.get("type") == "session_meta":
            session_row = row
            session_payload = _payload(row)
            break

    users = _message_rows(canonical_rows, "user")
    assistants = _message_rows(canonical_rows, "assistant")
    calls = _tool_calls(canonical_rows)

    start_time = ""
    if session_row is not None:
        candidate = session_payload.get("timestamp", _row_timestamp(session_row))
        start_time = candidate if isinstance(candidate, str) else ""
    if not start_time and canonical_rows:
        start_time = _row_timestamp(canonical_rows[0])

    parsed_timestamps = [
        parsed
        for row in canonical_rows
        if (parsed := _timestamp(_row_timestamp(row))) is not None
    ]
    parsed_start = _timestamp(start_time)
    if parsed_start is None and parsed_timestamps:
        parsed_start = min(parsed_timestamps)
    end_time = max(parsed_timestamps) if parsed_timestamps else parsed_start
    duration_seconds = (
        max(0.0, (end_time - parsed_start).total_seconds())
        if parsed_start is not None and end_time is not None
        else 0.0
    )
    duration_minutes = int(math.floor(duration_seconds / 60.0 + 0.5))

    tool_counts: dict[str, int] = {}
    for call in calls:
        name = str(call["name"])
        tool_counts[name] = tool_counts.get(name, 0) + 1

    git_commits = sum(bool(_GIT_COMMIT.search(str(call["argument_text"]))) for call in calls)
    git_pushes = sum(bool(_GIT_PUSH.search(str(call["argument_text"]))) for call in calls)
    lines_added, lines_removed, files_modified, languages = _file_metrics(canonical_rows, calls)
    tool_errors, tool_error_categories = _tool_errors(canonical_rows, calls)
    input_tokens, output_tokens = _latest_tokens(canonical_rows)

    user_message_timestamps = [item["timestamp"] for item in users if item.get("timestamp")]
    message_hours: dict[int, int] = {}
    for timestamp in user_message_timestamps:
        parsed = _timestamp(timestamp)
        if parsed is not None:
            local_hour = parsed.astimezone().hour
            message_hours[local_hour] = message_hours.get(local_hour, 0) + 1

    user_interruptions = sum(
        1
        for row in canonical_rows
        if row.get("type") == "event_msg"
        and _enum_text(_payload(row).get("type")) in {"turn_aborted", "user_interruption"}
    )
    tool_names = {str(call["name"]).lower() for call in calls}
    tool_arguments = "\n".join(str(call.get("argument_text", "")) for call in calls).lower()
    event_types = {
        str(_payload(row).get("type", "")).lower()
        for row in canonical_rows
        if row.get("type") == "event_msg"
    }

    session_id = session_payload.get("id", session_payload.get("session_id", ""))
    project_path = session_payload.get("cwd", session_payload.get("project_path", ""))
    summary = session_payload.get("summary", "")

    return {
        "session_id": str(session_id),
        "transcript_mtime": float(transcript_mtime),
        "project_path": str(project_path),
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "user_message_count": len(users),
        "assistant_message_count": len(assistants),
        "tool_counts": dict(sorted(tool_counts.items())),
        "languages": languages,
        "git_commits": int(git_commits),
        "git_pushes": int(git_pushes),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "first_prompt": users[0]["text"] if users else "",
        "summary": str(summary),
        "user_interruptions": user_interruptions,
        "user_response_times": _response_times(users, assistants),
        "tool_errors": tool_errors,
        "tool_error_categories": tool_error_categories,
        "uses_task_agent": bool(
            tool_names & {"task", "spawn_agent", "create_agent", "create_thread", "send_message_to_agent"}
            or "sub_agent_activity" in event_types
        ),
        "uses_mcp": any(name.startswith("mcp__") for name in tool_names)
        or "mcp_tool_call_end" in event_types,
        "uses_web_search": bool(
            tool_names & {"websearch", "web_search", "search_query"}
            or ("web__run" in tool_names and "search_query" in tool_arguments)
            or "web_search_end" in event_types
        ),
        "uses_web_fetch": bool(
            tool_names & {"webfetch", "web_fetch", "open"}
            or ("web__run" in tool_names and any(marker in tool_arguments for marker in ('open:', '"open"', "click:", '"click"')))
            or "web_fetch_end" in event_types
        ),
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "files_modified": files_modified,
        "message_hours": dict(sorted(message_hours.items())),
        "user_message_timestamps": user_message_timestamps,
        "origin": str(origin),
    }


def compute_source_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    """Hash every decoded transcript row using a key-order-independent form."""

    encoded = json.dumps(
        list(rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def detect_multi_clauding(
    metas: Iterable[Mapping[str, Any]], *, window_minutes: float = 30
) -> dict[str, Any]:
    """Detect Claude's ``A ... B ... A`` multi-session overlap pattern.

    A second session must appear between two messages from the same session;
    mere proximity is not enough.  The 30-minute boundary is inclusive.
    """

    window_seconds = max(0.0, float(window_minutes) * 60.0)
    events: list[tuple[datetime, str]] = []
    for index, meta in enumerate(metas):
        raw_key = meta.get("session_key", meta.get("session_id", f"session-{index}"))
        session_key = str(raw_key)
        timestamps = meta.get("user_message_timestamps", [])
        if not isinstance(timestamps, Sequence) or isinstance(timestamps, (str, bytes, bytearray)):
            continue
        for value in timestamps:
            parsed = _timestamp(value)
            if parsed is not None:
                events.append((parsed, session_key))

    events.sort(key=lambda item: item[0])
    pairs: set[tuple[str, str]] = set()
    overlap_messages: set[tuple[datetime, str]] = set()
    last_index: dict[str, int] = {}
    left = 0
    for current_index, (current_time, current_session) in enumerate(events):
        while (
            left < current_index
            and (current_time - events[left][0]).total_seconds() > window_seconds
        ):
            old_session = events[left][1]
            if last_index.get(old_session) == left:
                last_index.pop(old_session, None)
            left += 1

        previous_index = last_index.get(current_session)
        if previous_index is not None:
            for middle_index in range(previous_index + 1, current_index):
                middle_time, middle_session = events[middle_index]
                if middle_session == current_session:
                    continue
                pairs.add(tuple(sorted((current_session, middle_session))))
                overlap_messages.update(
                    {
                        events[previous_index],
                        (middle_time, middle_session),
                        (current_time, current_session),
                    }
                )
                break
        last_index[current_session] = current_index

    ordered_pairs = [list(pair) for pair in sorted(pairs)]
    participating = {session for pair in pairs for session in pair}
    return {
        "detected": bool(ordered_pairs),
        "event_pair_count": len(pairs),
        "session_count": len(participating),
        "session_pairs": ordered_pairs,
        "user_messages_during": len(overlap_messages),
    }


__all__ = [
    "compute_source_fingerprint",
    "detect_multi_clauding",
    "extract_native_session_meta",
]
