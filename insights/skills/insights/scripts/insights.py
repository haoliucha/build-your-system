#!/usr/bin/env python3
"""Local, privacy-first analysis kernel for the Codex ``$insights`` skill.

This program is deliberately model-free.  It inventories local JSONL sessions,
redacts the text that is handed to Codex, validates structured model responses,
and commits a single static HTML report transactionally.  A long-running
JSON-lines process keeps the prepared run in memory so a caller can never pick
an arbitrary output directory or fabricate a prepared state during commit.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MAX_NEW_SESSIONS = 200
LANGUAGE = "zh-CN"
CHUNK_TARGET = 25_000
CHUNK_HARD_LIMIT = 30_000
FACET_SCHEMA_VERSION = "facet_v2"
AGGREGATION_SCHEMA_VERSION = "aggregation_v1"
QUALITY_SCHEMA_VERSION = "quality_v1"

SECTION_IDS = (
    "overview",
    "project_domains",
    "collaboration",
    "what_works",
    "friction",
    "features_workflows",
    "agents_suggestions",
    "new_uses",
    "future_opportunities",
    "memorable_moments",
    "method_coverage",
)
SECTION_TITLES = {
    "zh": (
        "总览", "项目领域", "协作方式", "有效做法", "摩擦与根因",
        "功能与工作流", "AGENTS.md 建议", "新用法", "未来机会", "难忘时刻", "方法与覆盖量",
    ),
    "en": (
        "Overview", "Project Domains", "Collaboration Style", "What Works", "Friction and Root Causes",
        "Features and Workflows", "AGENTS.md Suggestions", "New Ways to Use Codex", "Future Opportunities",
        "Memorable Moments", "Method and Coverage",
    ),
}
SECTION_TONES = {
    "overview": "tone-warm", "project_domains": "tone-neutral", "collaboration": "tone-neutral",
    "what_works": "tone-success", "friction": "tone-friction", "features_workflows": "tone-suggestion",
    "agents_suggestions": "tone-suggestion", "new_uses": "tone-suggestion",
    "future_opportunities": "tone-future", "memorable_moments": "tone-warm", "method_coverage": "tone-neutral",
}
LENS_IDS = (
    "project_areas", "interaction_style", "what_works", "friction_analysis",
    "suggestions", "on_the_horizon", "fun_ending",
)
PATTERN_KINDS = ("repeat", "contradiction", "evolution")
PATTERN_GROUPS = ("goals", "friction", "successes", "tools", "instructions", "concurrency")
OUTCOMES = ("fully_achieved", "mostly_achieved", "partially_achieved", "not_achieved", "unclear_from_transcript")
HELPFULNESS = ("unhelpful", "slightly_helpful", "moderately_helpful", "very_helpful", "essential")
SESSION_TYPES = ("single_task", "multi_task", "iterative_refinement", "exploration", "quick_question")
FRICTION_TYPES = (
    "misunderstood_request", "wrong_approach", "buggy_code", "user_rejected_action",
    "excessive_changes", "tool_failed", "external_issue", "repeated_instruction", "missing_context",
)
STATS_KEYS = (
    "event_count", "user_message_count", "assistant_message_count", "duration_seconds",
    "character_count", "source_file_count", "tool_count", "error_count", "file_change_count", "subagent_count",
)
FACET_KEYS = {
    "schema_version", "session_key", "source_hash", "date", "project_alias", "session_origin",
    "deterministic_stats", "privacy_redactions", "underlying_goal", "goal_categories", "outcome",
    "user_satisfaction_counts", "helpfulness", "session_type", "friction_counts", "friction_detail",
    "primary_success", "brief_summary", "evidence_anchors",
}
_BCP47 = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
_IPV4 = re.compile(r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])(?:[A-F0-9]{1,4}:){2,7}[A-F0-9]{0,4}(?![\w:])", re.I)
_PRIVATE_PATH = re.compile(r"(?:/(?:Users|home)/[^/\s]+(?:/[^\s<>'\"`]+)*|[A-Za-z]:\\Users\\[^\\\s]+(?:\\[^\s<>'\"`]+)*)")
_BEARER = re.compile(r"\bBearer\s+(?=[A-Za-z0-9._~+/=-]*[._~+/=-])[A-Za-z0-9._~+/=-]+", re.I)
_COOKIE = re.compile(r"\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n]+", re.I)
_SECRET_ASSIGNMENT = re.compile(r"\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?[^\s,'\";]+", re.I)
_SECRET_TOKEN = re.compile(r"\b(?:sk|pk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b", re.I)
_TOKEN_CANDIDATE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9_])")
_FACET_PATH = re.compile(r"^facets/[0-9a-f]{16}-[0-9a-f]{16}\.json$")
_SESSION_KEY = re.compile(r"^session-[0-9a-f]{16}$")
_PROJECT_KEY = re.compile(r"^project-[0-9a-f]{8}$")
_SESSION_KEY_DOMAIN = "codex-insights-session-v2"
_PENDING_RUNS: dict[str, dict[str, Any]] = {}


class InsightsError(RuntimeError):
    """Base error returned as a protocol data response."""


class FacetValidationError(InsightsError):
    pass


class PrivacyError(InsightsError):
    pass


class ConcurrentRunError(InsightsError):
    pass


class StaleRunError(InsightsError):
    pass


def validate_language(language: str) -> str:
    if not isinstance(language, str) or not _BCP47.fullmatch(language):
        raise ValueError("language must be a valid BCP 47 tag")
    return language


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_high_entropy(value: str) -> bool:
    core = value.rstrip("=")
    classes = sum(bool(re.search(pattern, core)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[+/_-]"))
    return len(core) >= 32 and classes >= 3 and _entropy(core) >= 3.6


def redact_text(value: str) -> str:
    text = str(value)
    for pattern, replacement in (
        (_COOKIE, "[REDACTED_COOKIE]"), (_BEARER, "[REDACTED_BEARER]"),
        (_SECRET_ASSIGNMENT, "[REDACTED_SECRET]"), (_SECRET_TOKEN, "[REDACTED_SECRET]"),
        (_EMAIL, "[REDACTED_EMAIL]"), (_IPV4, "[REDACTED_IP]"), (_IPV6, "[REDACTED_IP]"),
        (_PRIVATE_PATH, "[REDACTED_PRIVATE_PATH]"),
    ):
        text = pattern.sub(replacement, text)
    return _TOKEN_CANDIDATE.sub(
        lambda match: "[REDACTED_HIGH_ENTROPY]" if _looks_high_entropy(match.group(0)) else match.group(0), text
    )


def privacy_violations(value: str) -> list[str]:
    text = str(value)
    found = [name for name, pattern in (
        ("cookie", _COOKIE), ("bearer", _BEARER), ("secret-assignment", _SECRET_ASSIGNMENT),
        ("secret-token", _SECRET_TOKEN), ("email", _EMAIL), ("ipv4", _IPV4), ("ipv6", _IPV6),
        ("private-path", _PRIVATE_PATH),
    ) if pattern.search(text)]
    if any(_looks_high_entropy(match.group(0)) for match in _TOKEN_CANDIDATE.finditer(text)):
        found.append("high-entropy")
    return found


def _parse_timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "input_text", "message"):
            if isinstance(content.get(key), str):
                return content[key]
        return ""
    if isinstance(content, list):
        return "\n".join(filter(None, (_text_content(item) for item in content)))
    return ""


def _event_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    timestamp = row.get("timestamp", payload.get("timestamp"))
    row_type = row.get("type")
    role = payload.get("role")
    text = ""
    if row_type == "response_item" and role in {"user", "assistant"}:
        text = _text_content(payload.get("content"))
    elif row_type == "event_msg":
        event_type = payload.get("type")
        if event_type == "user_message":
            role, text = "user", _text_content(payload.get("message", payload.get("content")))
        elif event_type in {"assistant_message", "agent_message"}:
            role, text = "assistant", _text_content(payload.get("message", payload.get("content")))
    elif row_type == "message" and role in {"user", "assistant"}:
        text = _text_content(payload.get("content", row.get("content")))
    if role not in {"user", "assistant"} or not text.strip():
        return None
    return {"timestamp": timestamp or "", "role": role, "text": text}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def _source_record(path: Path) -> dict[str, Any] | None:
    rows = _read_jsonl(path)
    if not rows:
        return None
    metas = [row.get("payload", {}) for row in rows if row.get("type") == "session_meta" and isinstance(row.get("payload"), dict)]
    meta = metas[0] if metas else {}
    session_id = meta.get("id") or meta.get("session_id") or meta.get("thread_id")
    if not session_id:
        for row in rows:
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            session_id = payload.get("session_id") or payload.get("thread_id")
            if session_id:
                break
    session_id = str(session_id or re.sub(r"^(?:rollout-)?", "", path.stem))
    start = meta.get("timestamp") or (rows[0].get("timestamp") if rows else "")
    cwd = meta.get("cwd") if isinstance(meta.get("cwd"), str) else ""
    events = [event for row in rows if (event := _event_from_row(row)) is not None]
    row_times = [_parse_timestamp(row.get("timestamp")) for row in rows]
    times = [stamp for stamp in row_times if stamp is not None]
    def count_words(names: tuple[str, ...]) -> int:
        return sum(1 for row in rows if str(row.get("type", "")).lower() in names or str((row.get("payload") or {}).get("type", "")).lower() in names)
    return {
        "session_id": session_id, "cwd": cwd, "start": start or "", "events": events, "times": times,
        "source_path": str(path),
        "tool_count": count_words(("function_call", "tool_call", "tool_result", "command_execution", "mcp_tool_call")),
        "error_count": count_words(("error", "tool_error", "turn_aborted")),
        "file_change_count": count_words(("file_change", "patch", "apply_patch")),
        "subagent_count": count_words(("spawn_agent", "subagent", "agent_spawned")),
    }


def _canonical_hash(session: dict[str, Any]) -> str:
    payload = {"session_id": session["session_id"], "cwd": session["cwd"], "start": session["start"], "events": session["events"]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _project_alias(cwd: str) -> str:
    return "project-" + hashlib.sha256(("codex-insights-project-v1\0" + cwd).encode("utf-8")).hexdigest()[:8]


def discover_sessions(
    codex_home: str | Path,
    current_thread_id: str | None = None,
    marker: str = "$insights",
    include_stats: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, int]]:
    home = Path(codex_home)
    current = current_thread_id or os.environ.get("CODEX_THREAD_ID")
    records: list[dict[str, Any]] = []
    source_files: list[Path] = []
    for directory in (home / "sessions", home / "archived_sessions"):
        if directory.is_dir():
            for path in sorted(directory.rglob("*.jsonl")):
                source_files.append(path)
                record = _source_record(path)
                if record:
                    record["origin"] = "archived" if "archived_sessions" in path.parts else "active"
                    records.append(record)
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        signature = (record["session_id"], record["cwd"], str(record["start"]))
        logical = grouped.setdefault(signature, {
            "session_id": record["session_id"], "cwd": record["cwd"], "start": record["start"],
            "events": [], "times": [], "source_paths": [], "origins": set(),
            "tool_count": 0, "error_count": 0, "file_change_count": 0, "subagent_count": 0,
        })
        logical["events"].extend(record["events"])
        logical["times"].extend(record["times"])
        logical["source_paths"].append(record["source_path"])
        logical["origins"].add(record["origin"])
        for name in ("tool_count", "error_count", "file_change_count", "subagent_count"):
            logical[name] += record[name]
    eligible: list[dict[str, Any]] = []
    excluded = {"current": 0, "insights": 0, "short_messages": 0, "short_duration": 0}
    for signature, logical in grouped.items():
        unique_events: list[dict[str, Any]] = []
        seen_events: set[str] = set()
        for event in sorted(logical["events"], key=lambda item: (_parse_timestamp(item.get("timestamp")) or 0, item.get("role", ""), item.get("text", ""))):
            fingerprint = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if fingerprint not in seen_events:
                seen_events.add(fingerprint)
                unique_events.append(event)
        logical["events"] = unique_events
        users = [event["text"] for event in unique_events if event["role"] == "user"]
        if current and logical["session_id"] == current:
            excluded["current"] += 1
            continue
        if any(marker.casefold() in message.casefold() for message in users):
            excluded["insights"] += 1
            continue
        if len(users) < 2:
            excluded["short_messages"] += 1
            continue
        times = logical["times"] + [stamp for event in unique_events if (stamp := _parse_timestamp(event.get("timestamp"))) is not None]
        if not times or max(times) - min(times) < 60:
            excluded["short_duration"] += 1
            continue
        identity = "\0".join((_SESSION_KEY_DOMAIN, *signature))
        logical["session_key"] = "session-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        logical["user_messages"] = users
        logical["updated_at"] = max(times)
        logical["source_hash"] = _canonical_hash(logical)
        logical["origin"] = "mixed" if len(logical["origins"]) > 1 else next(iter(logical["origins"]), "active")
        eligible.append(logical)
    result = sorted(eligible, key=lambda item: (item["updated_at"], item["session_key"]), reverse=True)
    if not include_stats:
        return result
    raw_id_counts: dict[str, int] = {}
    for session_id, _, _ in grouped:
        raw_id_counts[session_id] = raw_id_counts.get(session_id, 0) + 1
    stats = {
        "physical_source_files": len(source_files), "parsed_source_files": len(records), "parse_failed": len(source_files) - len(records),
        "logical_sessions": len(grouped), "duplicate_source_files": max(0, len(records) - len(grouped)),
        "logical_id_collisions": sum(1 for count in raw_id_counts.values() if count > 1), "eligible": len(result),
        "excluded": sum(excluded.values()), "excluded_current": excluded["current"], "excluded_insights": excluded["insights"],
        "excluded_short_messages": excluded["short_messages"], "excluded_short_duration": excluded["short_duration"],
    }
    return result, stats


def chunk_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for original in events:
        event = {"timestamp": str(original.get("timestamp", "")), "role": str(original.get("role", "")), "text": redact_text(str(original.get("text", "")))}
        size = len(event["text"])
        if current and (current_size + size > CHUNK_TARGET or current_size + size > CHUNK_HARD_LIMIT):
            chunks.append({"index": len(chunks), "char_count": current_size, "events": current})
            current, current_size = [], 0
        current.append(event)
        current_size += size
    if current:
        chunks.append({"index": len(chunks), "char_count": current_size, "events": current})
    for chunk in chunks:
        chunk["total"] = len(chunks)
    return chunks


def _state_path(output_dir: Path) -> Path:
    return output_dir / "state.json"


def _read_state(output_dir: Path) -> dict[str, Any]:
    path = _state_path(output_dir)
    if not path.is_file():
        return {"generation": 0, "sessions": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InsightsError(f"cannot read state: {exc}") from exc
    if not isinstance(state, dict) or not isinstance(state.get("generation"), int) or not isinstance(state.get("sessions"), dict):
        raise InsightsError("invalid state file")
    return state


def _facet_filename(facet: dict[str, Any]) -> str:
    return f"facets/{hashlib.sha256(facet['session_key'].encode('utf-8')).hexdigest()[:16]}-{facet['source_hash'][:16]}.json"


def _load_cached_facet(output_dir: Path, state_key: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    relative = entry.get("facet_file")
    if not isinstance(relative, str) or not _FACET_PATH.fullmatch(relative):
        return None
    facets_root = (output_dir / "facets").resolve()
    path = (output_dir / relative).resolve()
    try:
        path.relative_to(facets_root)
        facet = json.loads(path.read_text(encoding="utf-8"))
        validate_facet(facet)
    except (OSError, ValueError, json.JSONDecodeError, FacetValidationError):
        return None
    if facet.get("session_key") != state_key or facet.get("source_hash") != entry.get("source_hash") or relative != _facet_filename(facet):
        return None
    return facet


def _deterministic_stats(session: dict[str, Any]) -> dict[str, Any]:
    events = session["events"]
    times = session["times"] + [stamp for event in events if (stamp := _parse_timestamp(event.get("timestamp"))) is not None]
    duration = int(max(times) - min(times)) if times else 0
    return {
        "event_count": len(events), "user_message_count": sum(event["role"] == "user" for event in events),
        "assistant_message_count": sum(event["role"] == "assistant" for event in events),
        "duration_seconds": max(0, duration), "character_count": sum(len(event["text"]) for event in events),
        "source_file_count": len(session["source_paths"]), "tool_count": int(session.get("tool_count", 0)),
        "error_count": int(session.get("error_count", 0)), "file_change_count": int(session.get("file_change_count", 0)),
        "subagent_count": int(session.get("subagent_count", 0)),
    }


def _work_item(session: dict[str, Any]) -> dict[str, Any]:
    date = str(session.get("start") or "")[:10] or datetime.fromtimestamp(session["updated_at"], timezone.utc).strftime("%Y-%m-%d")
    helper_fields = {
        "schema_version": FACET_SCHEMA_VERSION, "session_key": session["session_key"], "source_hash": session["source_hash"],
        "date": date, "project_alias": _project_alias(session.get("cwd", "")), "session_origin": session.get("origin", "active"),
        "deterministic_stats": _deterministic_stats(session), "privacy_redactions": {"policy": "pre-model-redaction-v1"},
    }
    return {
        **helper_fields,
        "updated_at": datetime.fromtimestamp(session["updated_at"], timezone.utc).isoformat().replace("+00:00", "Z"),
        "chunks": chunk_events(session["events"]),
        "facet_contract": {
            "schema": FACET_SCHEMA_VERSION, "helper_owned": sorted(helper_fields),
            "model_owned": ["underlying_goal", "goal_categories", "outcome", "user_satisfaction_counts", "helpfulness", "session_type", "friction_counts", "friction_detail", "primary_success", "brief_summary", "evidence_anchors"],
            "evidence": "event anchors are concise labels; never copy raw paths, IDs, credentials, or long transcript text",
        },
    }


def prepare_run(codex_home: str | Path, output_dir: str | Path | None = None, current_thread_id: str | None = None, max_new_sessions: int = MAX_NEW_SESSIONS, language: str = LANGUAGE) -> dict[str, Any]:
    validate_language(language)
    if not isinstance(max_new_sessions, int) or isinstance(max_new_sessions, bool) or max_new_sessions < 0:
        raise ValueError("max_new_sessions must be a non-negative integer")
    home = Path(codex_home)
    output = Path(output_dir) if output_dir is not None else home / "usage-data" / "insights"
    state = _read_state(output)
    sessions, inventory = discover_sessions(home, current_thread_id=current_thread_id, include_stats=True)
    cached_facets: list[dict[str, Any]] = []
    uncached: list[dict[str, Any]] = []
    cached_discovered = 0
    discovered_keys: set[str] = set()
    for session in sessions:
        key = session["session_key"]
        discovered_keys.add(key)
        entry = state["sessions"].get(key)
        facet = _load_cached_facet(output, key, entry) if isinstance(entry, dict) and entry.get("source_hash") == session["source_hash"] else None
        if facet is None:
            uncached.append(session)
        else:
            cached_facets.append(facet)
            cached_discovered += 1
    for key, entry in state["sessions"].items():
        if key not in discovered_keys and isinstance(entry, dict):
            facet = _load_cached_facet(output, key, entry)
            if facet is not None:
                cached_facets.append(facet)
    work_items = [_work_item(session) for session in uncached[:max_new_sessions]]
    inventory.update({
        "cached": cached_discovered, "selected": len(work_items),
        "remaining": max(0, inventory["eligible"] - cached_discovered - len(work_items)),
        "historical_cached": len(cached_facets) - cached_discovered,
    })
    return {"protocol_version": 2, "generation": state["generation"], "language": language, "output_dir": str(output), "work_items": work_items, "cached_facets": cached_facets, "inventory": inventory}


def _check_string(value: Any, name: str, maximum: int = 2_000, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise FacetValidationError(f"invalid {name}")


def validate_facet(facet: Any, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(facet, dict) or set(facet) != FACET_KEYS:
        raise FacetValidationError(f"facet_v2 must contain exactly: {', '.join(sorted(FACET_KEYS))}")
    if facet["schema_version"] != FACET_SCHEMA_VERSION or not _SESSION_KEY.fullmatch(str(facet["session_key"])):
        raise FacetValidationError("invalid facet schema or opaque session_key")
    if not isinstance(facet["source_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", facet["source_hash"]):
        raise FacetValidationError("invalid source_hash")
    _check_string(facet["date"], "date", 32)
    if not _PROJECT_KEY.fullmatch(str(facet["project_alias"])) or facet["session_origin"] not in {"active", "archived", "mixed"}:
        raise FacetValidationError("invalid project_alias or session_origin")
    stats = facet["deterministic_stats"]
    if not isinstance(stats, dict) or set(stats) != set(STATS_KEYS) or any(not isinstance(stats[k], int) or stats[k] < 0 for k in STATS_KEYS):
        raise FacetValidationError("deterministic_stats must contain non-negative integer counters")
    if facet["privacy_redactions"] != {"policy": "pre-model-redaction-v1"}:
        raise FacetValidationError("invalid privacy_redactions marker")
    _check_string(facet["underlying_goal"], "underlying_goal", allow_empty=True)
    if not isinstance(facet["goal_categories"], list) or len(facet["goal_categories"]) > 6 or any(not isinstance(x, str) or not x.strip() or len(x) > 80 for x in facet["goal_categories"]):
        raise FacetValidationError("invalid goal_categories")
    if facet["outcome"] not in OUTCOMES or facet["helpfulness"] not in HELPFULNESS or facet["session_type"] not in SESSION_TYPES:
        raise FacetValidationError("invalid outcome, helpfulness, or session_type")
    satisfaction = facet["user_satisfaction_counts"]
    if not isinstance(satisfaction, dict) or set(satisfaction) != {"positive", "negative", "correction"} or any(not isinstance(v, int) or v < 0 for v in satisfaction.values()):
        raise FacetValidationError("invalid user_satisfaction_counts")
    friction = facet["friction_counts"]
    if not isinstance(friction, dict) or set(friction) != set(FRICTION_TYPES) or any(not isinstance(v, int) or v < 0 for v in friction.values()):
        raise FacetValidationError("invalid friction_counts")
    if not isinstance(facet["friction_detail"], list) or len(facet["friction_detail"]) > 12:
        raise FacetValidationError("invalid friction_detail")
    for detail in facet["friction_detail"]:
        if not isinstance(detail, dict) or set(detail) != {"type", "root_cause", "evidence"} or detail["type"] not in FRICTION_TYPES:
            raise FacetValidationError("invalid friction_detail item")
        _check_string(detail["root_cause"], "friction root cause", 500, allow_empty=True)
        _check_string(detail["evidence"], "friction evidence", 500, allow_empty=True)
    _check_string(facet["primary_success"], "primary_success", allow_empty=True)
    _check_string(facet["brief_summary"], "brief_summary", 3_000, allow_empty=True)
    if not isinstance(facet["evidence_anchors"], list) or len(facet["evidence_anchors"]) > 12 or any(not isinstance(x, str) or len(x) > 500 for x in facet["evidence_anchors"]):
        raise FacetValidationError("invalid evidence_anchors")
    if expected:
        for key in ("schema_version", "session_key", "source_hash", "date", "project_alias", "session_origin", "deterministic_stats", "privacy_redactions"):
            if facet.get(key) != expected.get(key):
                raise FacetValidationError(f"helper-owned facet field mismatch: {key}")
    if privacy_violations(_facet_privacy_text(facet)):
        raise PrivacyError("facet contains a known private value")
    return facet


def _facet_privacy_text(facet: dict[str, Any]) -> str:
    return json.dumps(facet, ensure_ascii=False, sort_keys=True)


def _opaque_evidence(value: Any, session_keys: set[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not _SESSION_KEY.fullmatch(x) or x not in session_keys for x in value):
        raise InsightsError("evidence must be a list of known opaque session keys")
    if len(set(value)) != len(value):
        raise InsightsError("evidence keys must be unique")
    return value


def validate_patterns(patterns: Any, session_keys: Iterable[str] | None = None) -> dict[str, Any]:
    if not isinstance(patterns, dict) or set(patterns) != {"schema_version", "groups"} or patterns["schema_version"] != AGGREGATION_SCHEMA_VERSION:
        raise InsightsError("patterns must use aggregation_v1")
    groups = patterns["groups"]
    if not isinstance(groups, dict) or set(groups) != set(PATTERN_GROUPS):
        raise InsightsError("patterns must contain the six groups")
    known = set(session_keys or [])
    for group, values in groups.items():
        if not isinstance(values, list) or len(values) > 20:
            raise InsightsError(f"pattern group {group} is invalid")
        for item in values:
            if not isinstance(item, dict) or set(item) != {"kind", "claim", "evidence", "confidence"} or item["kind"] not in PATTERN_KINDS:
                raise InsightsError("invalid pattern item")
            _check_string(item["claim"], "pattern claim", 1_000)
            evidence = _opaque_evidence(item["evidence"], known) if known else item["evidence"]
            if len(evidence) < 2 and not re.search(r"单例|singleton", item["claim"], re.I):
                raise InsightsError("cross-session pattern claims need two sessions or an explicit singleton label")
            if not isinstance(item["confidence"], (int, float)) or not 0 <= item["confidence"] <= 1:
                raise InsightsError("pattern confidence must be between 0 and 1")
    return patterns


def validate_lenses(lenses: Any, session_keys: Iterable[str] | None = None) -> dict[str, Any]:
    if not isinstance(lenses, dict) or set(lenses) != {"schema_version", "lenses"} or lenses["schema_version"] != AGGREGATION_SCHEMA_VERSION:
        raise InsightsError("lenses must use aggregation_v1")
    values = lenses["lenses"]
    if not isinstance(values, dict) or set(values) != set(LENS_IDS):
        raise InsightsError("lenses must contain the seven independent views")
    known = set(session_keys or [])
    for lens, entries in values.items():
        if not isinstance(entries, list) or len(entries) > 20:
            raise InsightsError(f"lens {lens} is invalid")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"claim", "evidence", "action", "success_criteria", "confidence"}:
                raise InsightsError("invalid lens item")
            _check_string(entry["claim"], "lens claim", 1_000)
            _check_string(entry["action"], "lens action", 1_000, allow_empty=True)
            _check_string(entry["success_criteria"], "lens success criteria", 1_000, allow_empty=True)
            evidence = _opaque_evidence(entry["evidence"], known) if known else entry["evidence"]
            if len(evidence) < 2 and not re.search(r"单例|singleton", entry["claim"], re.I):
                raise InsightsError("lens claims with one session must be marked singleton")
            if not isinstance(entry["confidence"], (int, float)) or not 0 <= entry["confidence"] <= 1:
                raise InsightsError("lens confidence must be between 0 and 1")
    return lenses


def validate_quality(quality: Any) -> dict[str, Any]:
    if not isinstance(quality, dict) or set(quality) != {"schema_version", "scores", "revision_count", "concerns"} or quality["schema_version"] != QUALITY_SCHEMA_VERSION:
        raise InsightsError("quality must use quality_v1")
    scores = quality["scores"]
    required = {"coverage", "evidence", "privacy", "actionability", "incremental"}
    if not isinstance(scores, dict) or set(scores) != required or any(not isinstance(v, int) or not 1 <= v <= 5 for v in scores.values()):
        raise InsightsError("quality scores must be integers from 1 to 5")
    if not isinstance(quality["revision_count"], int) or quality["revision_count"] not in {0, 1} or not isinstance(quality["concerns"], list) or any(not isinstance(x, str) or len(x) > 500 for x in quality["concerns"]):
        raise InsightsError("invalid quality concerns or revision_count")
    if scores["privacy"] < 4 or scores["evidence"] < 4 or scores["incremental"] < 4:
        raise PrivacyError("privacy, evidence, and incremental scores are hard gates (>=4)")
    return quality


def _fallback_patterns(facets: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [facet["session_key"] for facet in facets]
    groups = {group: [] for group in PATTERN_GROUPS}
    if keys:
        groups["goals"] = [{"kind": "repeat", "claim": "单例：本轮会话目标各不相同，暂无跨会话重复目标", "evidence": [keys[0]], "confidence": 0.2}]
    return {"schema_version": AGGREGATION_SCHEMA_VERSION, "groups": groups}


def _fallback_lenses(facets: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [facet["session_key"] for facet in facets]
    def entry(claim: str, action: str = "", success: str = "") -> dict[str, Any]:
        return {"claim": claim, "evidence": keys[:1], "action": action, "success_criteria": success, "confidence": 0.2}
    return {"schema_version": AGGREGATION_SCHEMA_VERSION, "lenses": {lens: ([entry("单例：样本不足以形成跨会话结论")] if keys else []) for lens in LENS_IDS}}


def _material(facets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "batch_size": 50,
        "facet_count": len(facets),
        "facets": [{"session_key": f["session_key"], "date": f["date"], "project_alias": f["project_alias"], "goal": f["underlying_goal"], "outcome": f["outcome"], "helpfulness": f["helpfulness"], "friction": f["friction_counts"], "success": f["primary_success"]} for f in facets],
        "instructions": "Return Repeat, Contradiction, and Evolution patterns; a claim called repeated/common must cite at least two opaque keys.",
    }


def _claim_entries(values: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    return [(str(value.get("claim", "")), list(value.get("evidence", []))) for value in values]


def render_report(facets: Iterable[dict[str, Any]], language: str = LANGUAGE, coverage: dict[str, Any] | None = None, patterns: dict[str, Any] | None = None, lenses: dict[str, Any] | None = None, quality: dict[str, Any] | None = None) -> str:
    language = validate_language(language)
    items = list(facets)
    for facet in items:
        validate_facet(facet)
    patterns = patterns or _fallback_patterns(items)
    lenses = lenses or _fallback_lenses(items)
    locale = "zh" if language.lower().startswith("zh") else "en"
    titles = dict(zip(SECTION_IDS, SECTION_TITLES[locale]))
    report_title = "Codex 使用洞察" if locale == "zh" else "Codex Usage Insights"
    generated_label = "生成时间" if locale == "zh" else "Generated"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    coverage = coverage or {}
    eligible, cached, selected = (int(coverage.get(k, 0)) for k in ("eligible", "cached", "selected"))
    remaining = int(coverage.get("remaining", max(0, eligible - cached - selected)))
    coverage_note = (f"覆盖恒等式：合格会话 {eligible} = 已缓存 {cached} + 本轮新增 {selected} + 尚未处理 {remaining}" if locale == "zh" else f"Coverage: {eligible} = cached {cached} + new {selected} + remaining {remaining}")
    stats_html = "".join(f'<span>{html.escape(label)} <strong>{value}</strong></span>' for label, value in (("合格会话" if locale == "zh" else "Eligible", eligible), ("已缓存" if locale == "zh" else "Cached", cached), ("本轮新增" if locale == "zh" else "New", selected), ("尚未处理" if locale == "zh" else "Remaining", remaining)))
    lens_values = lenses.get("lenses", {})
    pattern_values = patterns.get("groups", {})
    mapping = {
        "overview": _claim_entries(pattern_values.get("goals", [])),
        "project_domains": _claim_entries(lens_values.get("project_areas", [])),
        "collaboration": _claim_entries(lens_values.get("interaction_style", [])),
        "what_works": _claim_entries(lens_values.get("what_works", [])),
        "friction": _claim_entries(lens_values.get("friction_analysis", [])) + _claim_entries(pattern_values.get("friction", [])),
        "features_workflows": _claim_entries(lens_values.get("suggestions", [])),
        "agents_suggestions": _claim_entries(lens_values.get("suggestions", [])),
        "new_uses": _claim_entries(lens_values.get("on_the_horizon", [])),
        "future_opportunities": _claim_entries(lens_values.get("on_the_horizon", [])),
        "memorable_moments": _claim_entries(lens_values.get("fun_ending", [])),
        "method_coverage": [(coverage_note, [])],
    }
    if quality and quality.get("concerns"):
        mapping["method_coverage"].extend((f"Concern: {concern}", []) for concern in quality["concerns"])
    navigation = "".join(f'<a href="#{section}">{html.escape(titles[section])}</a>' for section in SECTION_IDS)
    sections_html: list[str] = []
    for section in SECTION_IDS:
        entries = mapping[section]
        if not entries:
            body = '<p class="empty">暂无可靠洞察</p>' if locale == "zh" else '<p class="empty">No reliable insight yet</p>'
        else:
            rows = []
            for claim, evidence in entries:
                evidence_label = (f"{len(set(evidence))} 个会话" if locale == "zh" else f"{len(set(evidence))} sessions") if evidence else ("方法说明" if locale == "zh" else "Method note")
                rows.append(f'<li><span class="evidence">{html.escape(evidence_label)}</span>{html.escape(claim)}<small>{html.escape(" · ".join(dict.fromkeys(evidence)))}</small></li>')
            body = "<ul>" + "".join(rows) + "</ul>"
        sections_html.append(f'<section id="{section}" class="{SECTION_TONES[section]}"><h2>{html.escape(titles[section])}</h2>{body}</section>')
    style = """:root{color-scheme:light;--ink:#182026;--muted:#66727d;--line:#d9e0e5;--paper:#fff;--wash:#f4f7f8;--accent:#176b87}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.layout{display:grid;grid-template-columns:220px minmax(0,800px);gap:48px;max-width:1120px;margin:0 auto;padding:40px 28px 80px}aside{width:220px;position:sticky;top:24px;align-self:start}aside h1{font-size:21px;line-height:1.25;margin:0 0 8px}aside p{color:var(--muted);font-size:12px;margin:0 0 20px}nav{display:flex;flex-direction:column;gap:2px}nav a{color:var(--ink);text-decoration:none;border-left:3px solid transparent;padding:7px 10px}nav a:hover,nav a:focus{border-color:var(--accent);color:var(--accent);background:var(--paper)}main{max-width:800px;background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:14px 44px 48px;box-shadow:0 12px 40px rgba(24,32,38,.06)}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:20px 0 4px}.stats span{padding:10px;border:1px solid var(--line);border-radius:8px;color:var(--muted);font-size:12px}.stats strong{display:block;color:var(--ink);font-size:20px}.coverage{padding:12px 14px;border-left:4px solid var(--accent);background:#edf6fa}section{padding:26px 0 18px;border-bottom:1px solid var(--line);border-left:4px solid transparent;scroll-margin-top:24px}section:last-child{border-bottom:0}.tone-warm{border-left-color:#d9a317;background:#fffaf0;padding-left:16px}.tone-success{border-left-color:#2f8f55;background:#f3fbf6;padding-left:16px}.tone-friction{border-left-color:#c84b4b;background:#fff6f5;padding-left:16px}.tone-suggestion{border-left-color:#3578c6;background:#f3f8ff;padding-left:16px}.tone-future{border-left-color:#7958b3;background:#f8f5ff;padding-left:16px}h2{font-size:24px;line-height:1.3;margin:0 0 16px}ul{padding-left:22px;margin:0}li{margin:0 0 12px}small{display:block;color:var(--muted);font-size:12px}.empty{color:var(--muted);font-style:italic}.evidence{display:inline-block;margin:0 8px 4px 0;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:650;color:#17613a;background:#e8f6ed}@media(max-width:640px){.layout{display:block;padding:0 14px 40px}aside{position:static;width:auto;padding:20px 4px 14px}nav{flex-direction:row;overflow-x:auto;padding-bottom:8px}nav a{white-space:nowrap;border-left:0;border-bottom:3px solid transparent}main{max-width:800px;padding:4px 22px 32px;border-radius:10px}.stats{grid-template-columns:1fr}h2{font-size:21px}}@media print{body{background:#fff}.layout{display:block;max-width:none;padding:0}aside{position:static;width:auto}nav{display:none}main{max-width:none;border:0;box-shadow:none;padding:0}section{break-inside:avoid}a{color:#000}}""".strip()
    return ("<!doctype html>\n" f'<html lang="{html.escape(language, quote=True)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src \'none\'; script-src \'none\'; connect-src \'none\'; frame-src \'none\'; object-src \'none\'; base-uri \'none\'; form-action \'none\'">' f"<title>{html.escape(report_title)}</title><style>{style}</style></head><body><div class=\"layout\"><aside><h1>{html.escape(report_title)}</h1><p>{html.escape(generated_label)}：{html.escape(generated)}</p><nav aria-label=\"章节导航\">{navigation}</nav></aside><main><div class=\"stats\" aria-label=\"核心统计\">{stats_html}</div>{''.join(sections_html)}</main></div></body></html>\n")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _acquire_lock(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ".insights.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ConcurrentRunError("another insights commit holds the lock") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()}\n")
    return path


def _timestamp_filename() -> str:
    return datetime.now(timezone.utc).strftime("report-%Y%m%dT%H%M%SZ.html")


def _validate_commit_material(facets: list[dict[str, Any]], patterns: dict[str, Any], lenses: dict[str, Any], quality: dict[str, Any]) -> None:
    keys = {facet["session_key"] for facet in facets}
    validate_patterns(patterns, keys)
    validate_lenses(lenses, keys)
    validate_quality(quality)


def commit_run(output_dir: str | Path, prepared: dict[str, Any], facets: Iterable[dict[str, Any]], language: str = LANGUAGE, failpoint: str | None = None, patterns: dict[str, Any] | None = None, lenses: dict[str, Any] | None = None, quality: dict[str, Any] | None = None, strict: bool = False) -> dict[str, Any]:
    language = validate_language(language)
    output = Path(output_dir)
    if str(output) != str(prepared.get("output_dir")):
        raise InsightsError("output_dir does not match prepared run")
    supplied = list(facets)
    expected_items = prepared.get("work_items", [])
    expected = {(item["session_key"], item["source_hash"]) for item in expected_items}
    actual = {(facet.get("session_key"), facet.get("source_hash")) for facet in supplied}
    if expected != actual or len(actual) != len(supplied):
        raise FacetValidationError("facets must cover each prepared work item exactly once")
    for item, facet in zip(sorted(expected_items, key=lambda x: x["session_key"]), sorted(supplied, key=lambda x: x.get("session_key", ""))):
        validate_facet(facet, item)
    cached = list(prepared.get("cached_facets", []))
    for facet in cached:
        validate_facet(facet)
    combined_by_key = {facet["session_key"]: facet for facet in cached}
    combined_by_key.update({facet["session_key"]: facet for facet in supplied})
    combined = sorted(combined_by_key.values(), key=lambda item: item["session_key"])
    patterns = patterns or _fallback_patterns(combined)
    lenses = lenses or _fallback_lenses(combined)
    quality = quality or {"schema_version": QUALITY_SCHEMA_VERSION, "scores": {"coverage": 4, "evidence": 4, "privacy": 5, "actionability": 3, "incremental": 4}, "revision_count": 0, "concerns": ["未提供模型质检材料，使用保守回退"]}
    if strict:
        _validate_commit_material(combined, patterns, lenses, quality)
    else:
        validate_patterns(patterns, {facet["session_key"] for facet in combined})
        validate_lenses(lenses, {facet["session_key"] for facet in combined})
        validate_quality(quality)
    if any(privacy_violations(_facet_privacy_text(facet)) for facet in combined):
        raise PrivacyError("privacy scan rejected facets")
    report = render_report(combined, language=language, coverage=prepared.get("inventory"), patterns=patterns, lenses=lenses, quality=quality)
    if privacy_violations(report):
        raise PrivacyError("privacy scan rejected rendered content")
    lock = _acquire_lock(output)
    staging = output / f".staging-{uuid.uuid4().hex}"
    backup = output / f".backup-{uuid.uuid4().hex}"
    installed: list[Path] = []
    backed_up: list[tuple[Path, Path]] = []
    try:
        current = _read_state(output)
        if current["generation"] != prepared.get("generation"):
            raise StaleRunError("state changed after prepare; prepare again")
        new_generation = current["generation"] + 1
        sessions = dict(current["sessions"])
        for facet in supplied:
            sessions[facet["session_key"]] = {"source_hash": facet["source_hash"], "facet_file": _facet_filename(facet)}
        timestamp_name = _timestamp_filename()
        if (output / timestamp_name).exists():
            raise InsightsError(f"timestamp report already exists: {timestamp_name}")
        state = {"generation": new_generation, "sessions": sessions, "coverage": prepared.get("inventory", {}), "quality": quality, "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        artifacts: dict[str, bytes] = {"report.html": report.encode("utf-8"), timestamp_name: report.encode("utf-8")}
        for facet in supplied:
            artifacts[_facet_filename(facet)] = _json_bytes(facet)
        manifest = {"generation": new_generation, "language": language, "report": "report.html", "timestamp_report": timestamp_name, "facet_count": len(combined), "coverage": prepared.get("inventory", {}), "analysis": {"facet_schema": FACET_SCHEMA_VERSION, "aggregation_schema": AGGREGATION_SCHEMA_VERSION, "quality_schema": QUALITY_SCHEMA_VERSION}, "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(artifacts.items())}}
        artifacts["manifest.json"] = _json_bytes(manifest)
        artifacts["state.json"] = _json_bytes(state)
        for relative, data in artifacts.items():
            _write_bytes(staging / relative, data)
        ordered = [name for name in artifacts if name != "state.json"] + ["state.json"]
        backup.mkdir(parents=True, exist_ok=True)
        for index, relative in enumerate(ordered):
            target, staged, saved = output / relative, staging / relative, backup / relative
            if target.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, saved)
                backed_up.append((saved, target))
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            installed.append(target)
            if relative != "state.json" and failpoint == "before_state" and index == len(ordered) - 2:
                raise RuntimeError("injected failure before state commit")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        return {"generation": new_generation, "report_path": str(output / "report.html"), "timestamp_report_path": str(output / timestamp_name), "manifest_path": str(output / "manifest.json"), "facet_count": len(combined), "quality": quality}
    except Exception:
        for target in reversed(installed):
            try:
                if target.exists():
                    target.unlink()
            except OSError:
                pass
        for saved, target in reversed(backed_up):
            if saved.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(saved, target)
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        raise
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _next_for(op: str, run_id: str | None = None) -> dict[str, Any]:
    if op == "prepare":
        return {"op": "aggregate", "run_id": run_id, "facets": "<one facet_v2 per work_item>"}
    if op == "aggregate":
        return {"op": "validate_patterns", "run_id": run_id, "patterns": "<aggregation_v1>"}
    if op == "validate_patterns":
        return {"op": "validate_lenses", "run_id": run_id, "lenses": "<seven-lens aggregation_v1>"}
    if op == "validate_lenses":
        return {"op": "validate_quality", "run_id": run_id, "quality": "<quality_v1>"}
    if op == "validate_quality":
        return {"op": "commit", "run_id": run_id, "facets": "<same facets>", "patterns": "<validated>", "lenses": "<validated>", "quality": "<validated>"}
    return {"op": "prepare"}


def handle_request(request: dict[str, Any], pending_runs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise InsightsError("request must be an object")
    op = request.get("op")
    action = request.get("action")
    if op is None and isinstance(action, str):
        op = action
    elif op is not None and action is not None and op != action:
        raise InsightsError("op and action aliases disagree")
    if not isinstance(op, str):
        raise InsightsError("request requires op (action is accepted as a legacy alias)")
    pending = _PENDING_RUNS if pending_runs is None else pending_runs
    if op == "prepare":
        codex_home = Path(request.get("codex_home", os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))).expanduser().resolve()
        canonical_output = (codex_home / "usage-data" / "insights").resolve()
        requested_output = request.get("output_dir")
        if requested_output is not None and Path(requested_output).expanduser().resolve() != canonical_output:
            raise InsightsError("output_dir is fixed to $CODEX_HOME/usage-data/insights")
        prepared = prepare_run(codex_home, canonical_output, current_thread_id=request.get("current_thread_id"), max_new_sessions=request.get("max_new_sessions", MAX_NEW_SESSIONS), language=request.get("language", LANGUAGE))
        run_id = uuid.uuid4().hex
        pending[run_id] = {**prepared, "facets": None, "patterns": None, "lenses": None, "quality": None}
        result = {"run_id": run_id, "language": prepared["language"], "work_items": prepared["work_items"], "stats": prepared["inventory"], "next": _next_for(op, run_id)}
    elif op == "validate_facet":
        validate_facet(request.get("facet"))
        result = {"valid": True, "next": _next_for(op)}
    elif op == "aggregate":
        run_id = request.get("run_id")
        run = pending.get(run_id) if isinstance(run_id, str) else None
        if run is None:
            raise InsightsError("unknown run_id")
        facets = list(request.get("facets", []))
        expected = {(item["session_key"], item["source_hash"]) for item in run["work_items"]}
        actual = {(facet.get("session_key"), facet.get("source_hash")) for facet in facets if isinstance(facet, dict)}
        if expected != actual or len(actual) != len(facets):
            raise FacetValidationError("aggregate facets must cover each work item exactly once")
        for item, facet in zip(sorted(run["work_items"], key=lambda x: x["session_key"]), sorted(facets, key=lambda x: x.get("session_key", ""))):
            validate_facet(facet, item)
        combined = list(run["cached_facets"]) + facets
        run["facets"] = facets
        result = {"run_id": run_id, "facet_count": len(combined), "aggregation_material": _material(combined), "next": _next_for(op, run_id)}
    elif op == "validate_patterns":
        run_id = request.get("run_id"); run = pending.get(run_id) if isinstance(run_id, str) else None
        if run is None or run.get("facets") is None:
            raise InsightsError("aggregate must precede validate_patterns")
        patterns = validate_patterns(request.get("patterns"), {facet["session_key"] for facet in run["cached_facets"] + run["facets"]})
        run["patterns"] = patterns
        result = {"run_id": run_id, "valid": True, "next": _next_for(op, run_id)}
    elif op == "validate_lenses":
        run_id = request.get("run_id"); run = pending.get(run_id) if isinstance(run_id, str) else None
        if run is None or run.get("patterns") is None:
            raise InsightsError("validate_patterns must precede validate_lenses")
        lenses = validate_lenses(request.get("lenses"), {facet["session_key"] for facet in run["cached_facets"] + run["facets"]})
        run["lenses"] = lenses
        result = {"run_id": run_id, "valid": True, "next": _next_for(op, run_id)}
    elif op == "validate_quality":
        run_id = request.get("run_id"); run = pending.get(run_id) if isinstance(run_id, str) else None
        if run is None or run.get("lenses") is None:
            raise InsightsError("validate_lenses must precede validate_quality")
        run["quality"] = validate_quality(request.get("quality"))
        result = {"run_id": run_id, "valid": True, "next": _next_for(op, run_id)}
    elif op == "commit":
        allowed = {"op", "action", "run_id", "facets", "patterns", "lenses", "quality", "language"}
        if set(request) - allowed or "output_dir" in request or "prepared" in request:
            raise InsightsError("commit accepts only run_id, facets, patterns, lenses, quality, and optional matching language")
        run_id = request.get("run_id")
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise InsightsError("commit requires a valid run_id")
        run = pending.pop(run_id, None)
        if run is None:
            raise InsightsError("unknown or already consumed run_id")
        language = request.get("language", run["language"])
        if language != run["language"]:
            raise InsightsError("commit language must equal prepare language")
        facets = request.get("facets", run.get("facets") or [])
        patterns = request.get("patterns", run.get("patterns")); lenses = request.get("lenses", run.get("lenses")); quality = request.get("quality", run.get("quality"))
        if patterns is None or lenses is None or quality is None:
            raise InsightsError("commit requires validated patterns, lenses, and quality")
        result = commit_run(run["output_dir"], run, facets, language=language, patterns=patterns, lenses=lenses, quality=quality, strict=True)
    elif op == "render":
        result = {"html": render_report(request.get("facets", []), request.get("language", LANGUAGE), coverage=request.get("coverage"), patterns=request.get("patterns"), lenses=request.get("lenses"), quality=request.get("quality"))}
    else:
        raise InsightsError(f"unsupported op: {op}")
    return {"ok": True, "result": result}


def serve_json_lines(input_stream=sys.stdin, output_stream=sys.stdout) -> int:
    pending_runs: dict[str, dict[str, Any]] = {}
    for line in input_stream:
        if not line.strip():
            continue
        try:
            response = handle_request(json.loads(line), pending_runs=pending_runs)
        except Exception as exc:
            response = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc), "next": {"op": "prepare"}}}
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local deterministic helper for $insights")
    parser.add_argument("--request", help="handle one JSON request and print one JSON response")
    args = parser.parse_args(argv)
    if args.request:
        try:
            response = handle_request(json.loads(args.request))
        except Exception as exc:
            print(json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc), "next": {"op": "prepare"}}}, ensure_ascii=False))
            return 1
        print(json.dumps(response, ensure_ascii=False))
        return 0
    return serve_json_lines()


if __name__ == "__main__":
    raise SystemExit(main())
