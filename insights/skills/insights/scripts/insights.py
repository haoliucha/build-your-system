#!/usr/bin/env python3
"""Codex Insights orchestration and durable report cache.

The product meaning follows the observable Claude Code 2.1.229 pipeline:
deterministic session metrics, one semantic facet per session, seven distinct
analysis lenses, a separate At-a-Glance synthesis, and a fixed HTML report.
Redaction, opaque cache keys, schema versioning, and transactional writes are
Codex safety guardrails; they are not presented as analysis stages.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePath
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import native_analysis as _native_analysis
import native_meta as _native_meta
from native_report import compare_report_structure, render_native_report


MAX_NEW_SESSIONS = 200
LANGUAGE = "zh-CN"
ANALYSIS_VERSION = "codex-exec-runner-v2-primary"
META_SCHEMA_VERSION = "native-meta-v2-source-class"
NORMALIZER_VERSION = "claude-2.1.228-shape-v1"
FACET_PROMPT_VERSION = "claude-2.1.229-codex-fixed-enums-v2"
FACET_SCHEMA_VERSION = "native-facet-v2"
LENS_PROMPT_VERSION = "claude-2.1.229-codex-lens-v4"
REPORT_SCHEMA_VERSION = "claude-report-structure-v4"

OUTCOMES = tuple(sorted(_native_analysis.OUTCOMES))
HELPFULNESS = tuple(sorted(_native_analysis.HELPFULNESS_LEVELS))
SESSION_TYPES = tuple(sorted(_native_analysis.SESSION_TYPES))
PRIMARY_SUCCESSES = tuple(sorted(_native_analysis.PRIMARY_SUCCESSES))
LENS_IDS = _native_analysis.LENS_IDS
classify_session_origin = _native_meta.classify_session_origin
CHUNK_TARGET = _native_analysis.CHUNK_SIZE
CHUNK_HARD_LIMIT = _native_analysis.CHUNK_SIZE

_BCP47 = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
_IPV4 = re.compile(r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])")
_IPV6_CANDIDATE = re.compile(r"(?<![\w:])(?=[0-9A-F:]*:)[0-9A-F:]{2,}(?![\w:])", re.I)
_PRIVATE_PATH = re.compile(
    r"(?:~[/\\][^\s<>'\"]+|/(?:Users|home|private|tmp|Volumes)(?:/[^\s<>'\"]+)+|[A-Za-z]:\\[^\s<>'\"]+|\\\\[^\\\s]+\\[^\s<>'\"]+)"
)
_BEARER = re.compile(r"\bBearer\s+[^\s,;]+", re.I)
_COOKIE = re.compile(r"\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n]+", re.I)
_SECRET_ASSIGNMENT = re.compile(r"\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?[^\s,'\";]+", re.I)
_SECRET_TOKEN = re.compile(r"\b(?:sk|pk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b", re.I)
_TOKEN_CANDIDATE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9_])")
_FACET_PATH = re.compile(r"^facets/[0-9a-f]{16}-[0-9a-f]{16}\.json$")
_SESSION_KEY = re.compile(r"^session-[0-9a-f]{16}$")
_PROJECT_KEY = re.compile(r"^project-[0-9a-f]{8}$")
_SESSION_KEY_DOMAIN = "codex-insights-session-native-v1"
_SELF_MARKER = re.compile(r"(?:^|\s)\$insights(?:\s|$)", re.I)


class InsightsError(RuntimeError):
    """Base error returned as a protocol response."""


class FacetValidationError(InsightsError):
    """Structured model output did not match the required schema."""


class PrivacyError(InsightsError):
    """A persistent or model-facing artifact failed privacy scanning."""


class ConcurrentRunError(InsightsError):
    """Another transaction currently owns the output lock."""


class StaleRunError(InsightsError):
    """Source or committed generation changed after prepare."""


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


def redact_text(value: Any) -> str:
    text = str(value)
    for pattern, replacement in (
        (_COOKIE, "[REDACTED_COOKIE]"),
        (_BEARER, "[REDACTED_BEARER]"),
        (_SECRET_ASSIGNMENT, "[REDACTED_SECRET]"),
        (_SECRET_TOKEN, "[REDACTED_SECRET]"),
        (_EMAIL, "[REDACTED_EMAIL]"),
        (_IPV4, "[REDACTED_IP]"),
        (_PRIVATE_PATH, "[REDACTED_PRIVATE_PATH]"),
    ):
        text = pattern.sub(replacement, text)
    text = _IPV6_CANDIDATE.sub(
        lambda match: "[REDACTED_IP]" if _is_ipv6(match.group(0)) else match.group(0),
        text,
    )
    return _TOKEN_CANDIDATE.sub(
        lambda match: "[REDACTED_HIGH_ENTROPY]" if _looks_high_entropy(match.group(0)) else match.group(0),
        text,
    )


def privacy_violations(value: Any) -> list[str]:
    text = str(value)
    found = [
        name
        for name, pattern in (
            ("cookie", _COOKIE),
            ("bearer", _BEARER),
            ("secret-assignment", _SECRET_ASSIGNMENT),
            ("secret-token", _SECRET_TOKEN),
            ("email", _EMAIL),
            ("ipv4", _IPV4),
            ("private-path", _PRIVATE_PATH),
        )
        if pattern.search(text)
    ]
    if any(_is_ipv6(match.group(0)) for match in _IPV6_CANDIDATE.finditer(text)):
        found.append("ipv6")
    if any(_looks_high_entropy(match.group(0)) for match in _TOKEN_CANDIDATE.finditer(text)):
        found.append("high-entropy")
    return found


def _is_ipv6(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


compute_source_fingerprint = _native_meta.compute_source_fingerprint
extract_native_session_meta = _native_meta.extract_native_session_meta
detect_multi_clauding = _native_meta.detect_multi_clauding
normalize_session = _native_analysis.normalize_session
split_analysis_text = _native_analysis.split_analysis_text
build_facet_prompt = _native_analysis.build_facet_prompt
build_lens_jobs = _native_analysis.build_lens_jobs
build_chunk_summary_prompt = _native_analysis.build_chunk_summary_prompt


def validate_native_facet(value: Any) -> dict[str, Any]:
    try:
        return _native_analysis.validate_native_facet(value)
    except _native_analysis.FacetValidationError as exc:
        raise FacetValidationError(str(exc)) from exc


def validate_lens_result(lens_id: str, value: Any) -> dict[str, Any]:
    try:
        return _native_analysis.validate_lens_result(lens_id, value)
    except _native_analysis.FacetValidationError as exc:
        raise FacetValidationError(str(exc)) from exc


def build_at_a_glance_job(
    material: Mapping[str, Any],
    lenses: Mapping[str, Any],
    *,
    language: str = LANGUAGE,
) -> dict[str, Any]:
    try:
        return _native_analysis.build_at_a_glance_job(material, lenses, language=language)
    except _native_analysis.InsightsError as exc:
        raise InsightsError(str(exc)) from exc


def validate_at_a_glance(value: Any) -> dict[str, Any]:
    try:
        return _native_analysis.validate_at_a_glance(value)
    except _native_analysis.FacetValidationError as exc:
        raise FacetValidationError(str(exc)) from exc


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
    if isinstance(content, Mapping):
        for key in ("text", "input_text", "output_text", "message"):
            if isinstance(content.get(key), str):
                return str(content[key])
        return ""
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        return "\n".join(filter(None, (_text_content(item) for item in content)))
    return ""


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


def _analysis_events(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    event_user: list[dict[str, Any]] = []
    event_assistant: list[dict[str, Any]] = []
    response_user: list[dict[str, Any]] = []
    response_assistant: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
        timestamp = str(row.get("timestamp", payload.get("timestamp", "")))
        row_type = row.get("type")
        if row_type == "event_msg":
            raw_event_type = payload.get("type")
            event_type = raw_event_type if isinstance(raw_event_type, str) else ""
            if event_type == "user_message":
                text = _text_content(payload.get("message", payload.get("content", ""))).strip()
                if text:
                    event_user.append({"timestamp": timestamp, "role": "user", "text": text, "_index": index})
            elif event_type in {"assistant_message", "agent_message"}:
                text = _text_content(payload.get("message", payload.get("content", ""))).strip()
                if text:
                    event_assistant.append({"timestamp": timestamp, "role": "assistant", "text": text, "_index": index})
        elif row_type == "response_item":
            raw_payload_type = payload.get("type")
            raw_role = payload.get("role")
            payload_type = raw_payload_type if isinstance(raw_payload_type, str) else ""
            role = raw_role if isinstance(raw_role, str) else ""
            if payload_type == "message" or role in {"user", "assistant"}:
                text = _text_content(payload.get("content", "")).strip()
                target = response_user if role == "user" else response_assistant
                if role in {"user", "assistant"} and text:
                    target.append({"timestamp": timestamp, "role": role, "text": text, "_index": index})
            if payload_type in {"function_call", "custom_tool_call", "local_shell_call"}:
                name = str(payload.get("name") or ("local_shell" if payload_type == "local_shell_call" else "unknown"))
                tools.append({"timestamp": timestamp, "role": "tool", "name": name, "text": "", "_index": index})
    events = (event_user or response_user) + (event_assistant or response_assistant) + tools
    events.sort(key=lambda item: (_parse_timestamp(item.get("timestamp")) or 0, item["_index"]))
    for event in events:
        event.pop("_index", None)
    return events


def _source_record(path: Path, origin: str) -> dict[str, Any] | None:
    rows = _read_jsonl(path)
    if not rows:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    meta = extract_native_session_meta(rows, transcript_mtime=stat.st_mtime, origin=origin)
    if not meta.get("session_id"):
        meta["session_id"] = re.sub(r"^(?:rollout-)?", "", path.stem)
    events = _analysis_events(rows)
    times = [
        stamp
        for row in rows
        if (stamp := _parse_timestamp(row.get("timestamp"))) is not None
    ]
    return {
        "rows": rows,
        "meta": meta,
        "events": events,
        "source_path": path,
        "source_hash": compute_source_fingerprint(rows),
        "updated_at": max(times, default=stat.st_mtime),
        "duration_seconds": max(times) - min(times) if times else 0,
        "origin": origin,
    }


def _project_alias(project_path: str) -> str:
    digest = hashlib.sha256(("codex-insights-project-v2\0" + project_path).encode("utf-8")).hexdigest()
    return "project-" + digest[:8]


def _project_label(project_path: str) -> str:
    label = PurePath(project_path).name if project_path else "unknown-project"
    cleaned = redact_text(label).strip()
    return cleaned[:120] or "unknown-project"


def _session_key(record: Mapping[str, Any]) -> str:
    meta = record["meta"]
    identity = "\0".join(
        (
            _SESSION_KEY_DOMAIN,
            str(meta.get("session_id", "")),
            str(meta.get("project_path", "")),
            str(meta.get("start_time", "")),
        )
    )
    return "session-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def discover_sessions(
    codex_home: str | Path,
    current_thread_id: str | None = None,
    marker: str = "$insights",
    include_stats: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, int]]:
    home = Path(codex_home)
    current = current_thread_id or os.environ.get("CODEX_THREAD_ID")
    source_files: list[Path] = []
    records: list[dict[str, Any]] = []
    for directory, origin in ((home / "sessions", "active"), (home / "archived_sessions", "archived")):
        if not directory.is_dir():
            continue
        if directory.is_symlink():
            continue
        source_root = directory.resolve()
        for path in sorted(directory.rglob("*.jsonl")):
            source_files.append(path)
            if path.is_symlink():
                continue
            try:
                path.resolve().relative_to(source_root)
            except (OSError, ValueError):
                continue
            record = _source_record(path, origin)
            if record is not None:
                records.append(record)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    raw_id_signatures: dict[str, set[tuple[str, str, str]]] = {}
    for record in records:
        meta = record["meta"]
        signature = (
            str(meta.get("session_id", "")),
            str(meta.get("project_path", "")),
            str(meta.get("start_time", "")),
        )
        grouped.setdefault(signature, []).append(record)
        raw_id_signatures.setdefault(signature[0], set()).add(signature)

    excluded = {"current": 0, "insights": 0, "short_messages": 0, "short_duration": 0}
    cohorts = {
        "primary": 0,
        "legacy_primary": 0,
        "subagent": 0,
        "automation": 0,
        "headless": 0,
    }
    eligible: list[dict[str, Any]] = []
    for signature, branches in grouped.items():
        chosen = max(
            branches,
            key=lambda item: (
                int(item["meta"].get("user_message_count", 0)),
                int(item["meta"].get("duration_minutes", 0)),
                float(item["meta"].get("transcript_mtime", 0)),
            ),
        )
        meta = chosen["meta"]
        user_messages = [event["text"] for event in chosen["events"] if event.get("role") == "user"]
        if current and str(meta.get("session_id")) == current:
            excluded["current"] += 1
            continue
        first_five = user_messages[:5]
        if any(
            _SELF_MARKER.search(message)
            or "RESPOND WITH ONLY A VALID JSON OBJECT" in message
            or "record_facets" in message
            for message in first_five
        ):
            excluded["insights"] += 1
            continue
        session_class = classify_session_origin(meta)
        cohorts[session_class] += 1
        if session_class not in {"primary", "legacy_primary"}:
            continue
        if int(meta.get("user_message_count", 0)) < 2:
            excluded["short_messages"] += 1
            continue
        if float(chosen.get("duration_seconds", 0)) < 60:
            excluded["short_duration"] += 1
            continue
        origins = {branch["origin"] for branch in branches}
        chosen = dict(chosen)
        chosen["session_class"] = session_class
        chosen["meta"] = {**meta, "session_class": session_class}
        chosen["session_key"] = _session_key(chosen)
        chosen["project_alias"] = _project_alias(str(meta.get("project_path", "")))
        chosen["project_label"] = _project_label(str(meta.get("project_path", "")))
        chosen["session_origin"] = "mixed" if len(origins) > 1 else next(iter(origins))
        chosen["source_paths"] = [chosen["source_path"]]
        eligible.append(chosen)

    eligible.sort(key=lambda item: (item["updated_at"], item["session_key"]), reverse=True)
    if not include_stats:
        return eligible
    stats = {
        "physical_source_files": len(source_files),
        "parsed_source_files": len(records),
        "parse_failed": len(source_files) - len(records),
        "logical_sessions": len(grouped),
        "duplicate_source_files": sum(max(0, len(branches) - 1) for branches in grouped.values()),
        "logical_id_collisions": sum(1 for signatures in raw_id_signatures.values() if len(signatures) > 1),
        "eligible": len(eligible),
        "excluded": sum(excluded.values()),
        "excluded_current": excluded["current"],
        "excluded_insights": excluded["insights"],
        "excluded_short_messages": excluded["short_messages"],
        "excluded_short_duration": excluded["short_duration"],
        **cohorts,
        "primary_total": cohorts["primary"] + cohorts["legacy_primary"],
        "primary_eligible": len(eligible),
    }
    return eligible, stats


def _state_path(output_dir: Path) -> Path:
    return output_dir / "state.json"


def _fresh_state() -> dict[str, Any]:
    return {
        "generation": 0,
        "analysis_version": ANALYSIS_VERSION,
        "meta_schema_version": META_SCHEMA_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "facet_prompt_version": FACET_PROMPT_VERSION,
        "sessions": {},
    }


def _canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _state_snapshot_hash(output_dir: Path) -> str:
    """Hash the on-disk state canonically, including corrupt/absent states."""

    path = _state_path(output_dir)
    if not path.exists():
        return hashlib.sha256(b"codex-insights-state:absent").hexdigest()
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StaleRunError("state cannot be read") from exc
    try:
        return _canonical_json_hash(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return hashlib.sha256(b"codex-insights-state:invalid\0" + raw).hexdigest()


def _legacy_state(value: Any = None) -> tuple[dict[str, Any], bool]:
    fresh = _fresh_state()
    if isinstance(value, dict) and isinstance(value.get("generation"), int):
        fresh["generation"] = int(value["generation"])
    return fresh, True


def _valid_state_entry(state_key: str, entry: Any) -> bool:
    return bool(
        _SESSION_KEY.fullmatch(state_key)
        and isinstance(entry, dict)
        and set(entry) == {"source_hash", "facet_file", "analysis_version"}
        and re.fullmatch(r"[a-f0-9]{64}", str(entry.get("source_hash", "")))
        and isinstance(entry.get("facet_file"), str)
        and _FACET_PATH.fullmatch(str(entry.get("facet_file")))
        and entry.get("analysis_version") == ANALYSIS_VERSION
    )


def _manifest_file_path(output_dir: Path, relative: str) -> Path | None:
    if not relative or relative.startswith("/") or "\\" in relative:
        return None
    root = output_dir.resolve()
    path = (output_dir / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _cache_integrity_valid(output_dir: Path, state: Mapping[str, Any], state_bytes: bytes) -> bool:
    manifest_path = output_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, dict) or manifest.get("generation") != state.get("generation"):
        return False
    expected_state_digest = hashlib.sha256(state_bytes).hexdigest()
    if manifest.get("state_sha256") != expected_state_digest:
        return False
    files = manifest.get("files")
    if not isinstance(files, dict) or files.get("state.json") != expected_state_digest:
        return False
    analysis = manifest.get("analysis")
    if not isinstance(analysis, dict) or any(
        analysis.get(key) != expected
        for key, expected in (
            ("analysis_version", ANALYSIS_VERSION),
            ("meta_schema", META_SCHEMA_VERSION),
            ("normalizer", NORMALIZER_VERSION),
            ("facet_prompt", FACET_PROMPT_VERSION),
            ("facet_schema", FACET_SCHEMA_VERSION),
        )
    ):
        return False
    sessions = state.get("sessions", {})
    referenced_facets = {
        entry["facet_file"] for entry in sessions.values() if isinstance(entry, Mapping)
    }
    if not referenced_facets.issubset(files):
        return False
    for relative, expected_digest in files.items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected_digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_digest)
        ):
            return False
        path = _manifest_file_path(output_dir, relative)
        try:
            data = path.read_bytes() if path is not None else None
        except OSError:
            return False
        if data is None or hashlib.sha256(data).hexdigest() != expected_digest:
            return False
    for state_key, entry in sessions.items():
        if not _valid_state_entry(state_key, entry):
            return False
        facet_path = _manifest_file_path(output_dir, entry["facet_file"])
        if facet_path is None:
            return False
        try:
            facet = _validate_persisted_facet(
                json.loads(facet_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, InsightsError):
            return False
        if (
            facet["session_key"] != state_key
            or facet["source_hash"] != entry["source_hash"]
            or _facet_filename(facet) != entry["facet_file"]
        ):
            return False
    return True


def _read_state(output_dir: Path) -> tuple[dict[str, Any], bool]:
    path = _state_path(output_dir)
    if not path.is_file():
        return _fresh_state(), False
    try:
        state_bytes = path.read_bytes()
        value = json.loads(state_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _legacy_state()
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("generation"), int)
        or not isinstance(value.get("sessions"), dict)
        or value.get("analysis_version") != ANALYSIS_VERSION
        or value.get("meta_schema_version") != META_SCHEMA_VERSION
        or value.get("normalizer_version") != NORMALIZER_VERSION
        or value.get("facet_prompt_version") != FACET_PROMPT_VERSION
        or any(not _valid_state_entry(key, entry) for key, entry in value.get("sessions", {}).items())
    ):
        return _legacy_state(value)
    if not _cache_integrity_valid(output_dir, value, state_bytes):
        return _legacy_state(value)
    return value, False


def _facet_filename(facet: Mapping[str, Any]) -> str:
    key_hash = hashlib.sha256(str(facet["session_key"]).encode("utf-8")).hexdigest()[:16]
    return f"facets/{key_hash}-{str(facet['source_hash'])[:16]}.json"


def _validate_persisted_facet(value: Any, expected: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FacetValidationError("persisted facet must be an object")
    helper_fields = {
        "schema_version",
        "analysis_version",
        "meta_schema_version",
        "normalizer_version",
        "facet_prompt_version",
        "analysis_origin",
        "session_key",
        "source_hash",
        "date",
        "project_alias",
        "project_label",
        "session_origin",
        "session_class",
        "session_meta",
        "privacy_redactions",
    }
    model = {key: item for key, item in value.items() if key not in helper_fields}
    validate_native_facet(model)
    if value.get("schema_version") != FACET_SCHEMA_VERSION:
        raise FacetValidationError("wrong facet schema version")
    for key, expected_value in (
        ("analysis_version", ANALYSIS_VERSION),
        ("meta_schema_version", META_SCHEMA_VERSION),
        ("normalizer_version", NORMALIZER_VERSION),
        ("facet_prompt_version", FACET_PROMPT_VERSION),
        ("analysis_origin", "model"),
    ):
        if value.get(key) != expected_value:
            raise FacetValidationError(f"invalid {key}")
    if not _SESSION_KEY.fullmatch(str(value.get("session_key", ""))):
        raise FacetValidationError("invalid opaque session key")
    if not re.fullmatch(r"[a-f0-9]{64}", str(value.get("source_hash", ""))):
        raise FacetValidationError("invalid source hash")
    if not _PROJECT_KEY.fullmatch(str(value.get("project_alias", ""))):
        raise FacetValidationError("invalid project alias")
    session_origin = value.get("session_origin")
    if not isinstance(session_origin, str) or session_origin not in {
        "active",
        "archived",
        "mixed",
    }:
        raise FacetValidationError("invalid session origin")
    if not isinstance(value.get("session_meta"), dict):
        raise FacetValidationError("missing deterministic session meta")
    if expected:
        for key in (
            "schema_version",
            "analysis_version",
            "meta_schema_version",
            "normalizer_version",
            "facet_prompt_version",
            "session_key",
            "source_hash",
            "date",
            "project_alias",
            "project_label",
            "session_origin",
            "session_meta",
            "privacy_redactions",
        ):
            if value.get(key) != expected.get(key):
                raise FacetValidationError(f"helper field mismatch: {key}")
    if privacy_violations(json.dumps(value, ensure_ascii=False, sort_keys=True)):
        raise PrivacyError("persisted facet contains a private value")
    return value


def validate_facet(value: Any, expected: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Backward-compatible public name for the persisted native facet validator."""

    return _validate_persisted_facet(value, expected)


def _load_cached_facet(output_dir: Path, state_key: str, entry: Mapping[str, Any]) -> dict[str, Any] | None:
    relative = entry.get("facet_file")
    if not isinstance(relative, str) or not _FACET_PATH.fullmatch(relative):
        return None
    facets_root = (output_dir / "facets").resolve()
    path = (output_dir / relative).resolve()
    try:
        path.relative_to(facets_root)
        value = json.loads(path.read_text(encoding="utf-8"))
        facet = _validate_persisted_facet(value)
    except (OSError, ValueError, json.JSONDecodeError, InsightsError):
        return None
    if (
        facet["session_key"] != state_key
        or facet["source_hash"] != entry.get("source_hash")
        or relative != _facet_filename(facet)
    ):
        return None
    return facet


def _public_session_meta(meta: Mapping[str, Any], project_alias: str, project_label: str) -> dict[str, Any]:
    tool_counts: dict[str, int] = {}
    for raw_name, raw_count in dict(meta.get("tool_counts", {})).items():
        safe_name = redact_text(raw_name)
        tool_counts[safe_name] = tool_counts.get(safe_name, 0) + int(raw_count)
    return {
        "start_time": str(meta.get("start_time", "")),
        "duration_minutes": int(meta.get("duration_minutes", 0)),
        "user_message_count": int(meta.get("user_message_count", 0)),
        "assistant_message_count": int(meta.get("assistant_message_count", 0)),
        "tool_counts": tool_counts,
        "languages": dict(meta.get("languages", {})),
        "git_commits": int(meta.get("git_commits", 0)),
        "git_pushes": int(meta.get("git_pushes", 0)),
        "input_tokens": int(meta.get("input_tokens", 0)),
        "output_tokens": int(meta.get("output_tokens", 0)),
        "user_interruptions": int(meta.get("user_interruptions", 0)),
        "user_response_times": list(meta.get("user_response_times", [])),
        "tool_errors": int(meta.get("tool_errors", 0)),
        "tool_error_categories": dict(meta.get("tool_error_categories", {})),
        "uses_task_agent": bool(meta.get("uses_task_agent")),
        "uses_mcp": bool(meta.get("uses_mcp")),
        "uses_web_search": bool(meta.get("uses_web_search")),
        "uses_web_fetch": bool(meta.get("uses_web_fetch")),
        "lines_added": int(meta.get("lines_added", 0)),
        "lines_removed": int(meta.get("lines_removed", 0)),
        "files_modified": int(meta.get("files_modified", 0)),
        "message_hours": dict(meta.get("message_hours", {})),
        "user_message_timestamps": list(meta.get("user_message_timestamps", [])),
        "project_alias": project_alias,
        "project_label": project_label,
        "session_class": str(meta.get("session_class", "legacy_primary")),
    }


def _helper_fields(session: Mapping[str, Any]) -> dict[str, Any]:
    meta = session["meta"]
    return {
        "schema_version": FACET_SCHEMA_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "meta_schema_version": META_SCHEMA_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "facet_prompt_version": FACET_PROMPT_VERSION,
        "analysis_origin": "model",
        "session_key": session["session_key"],
        "source_hash": session["source_hash"],
        "date": str(meta.get("start_time", ""))[:10],
        "project_alias": session["project_alias"],
        "project_label": session["project_label"],
        "session_origin": session["session_origin"],
        "session_class": session["session_class"],
        "session_meta": _public_session_meta(meta, session["project_alias"], session["project_label"]),
        "privacy_redactions": {"policy": "model-input-guardrail-v2"},
    }


def _model_session(session: Mapping[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for event in session["events"]:
        if event["role"] == "tool":
            events.append({"timestamp": event.get("timestamp", ""), "role": "tool", "name": redact_text(event.get("name", "")), "text": ""})
        else:
            events.append({"timestamp": event.get("timestamp", ""), "role": event["role"], "text": redact_text(event.get("text", ""))})
    return {
        "session_key": session["session_key"],
        "start": session["meta"].get("start_time", ""),
        "project_label": session["project_label"],
        "duration_minutes": session["meta"].get("duration_minutes", 0),
        "events": events,
    }


def _work_item(session: Mapping[str, Any]) -> dict[str, Any]:
    helper = _helper_fields(session)
    material = normalize_session(_model_session(session))
    chunks = split_analysis_text(material)
    return {
        **helper,
        "updated_at": datetime.fromtimestamp(float(session["updated_at"]), timezone.utc).isoformat().replace("+00:00", "Z"),
        "material": material if len(chunks) == 1 else None,
        "chunks": chunks if len(chunks) > 1 else [],
        "facet_schema": {
            "required": list(_native_analysis.NATIVE_FACET_FIELDS),
            "optional": sorted(_native_analysis.FACET_EXTENSION_FIELDS),
        },
    }


def prepare_run(
    codex_home: str | Path,
    output_dir: str | Path | None = None,
    current_thread_id: str | None = None,
    max_new_sessions: int = MAX_NEW_SESSIONS,
    language: str = LANGUAGE,
) -> dict[str, Any]:
    validate_language(language)
    if isinstance(max_new_sessions, bool) or not isinstance(max_new_sessions, int) or not 0 <= max_new_sessions <= MAX_NEW_SESSIONS:
        raise ValueError(f"max_new_sessions must be an integer from 0 to {MAX_NEW_SESSIONS}")
    home = Path(codex_home).expanduser().resolve()
    requested_output = Path(output_dir).expanduser() if output_dir is not None else home / "usage-data" / "insights"
    output = requested_output.resolve()
    try:
        output.relative_to(home)
    except ValueError as exc:
        raise InsightsError("Insights output must remain inside CODEX_HOME") from exc
    state_hash = _state_snapshot_hash(output)
    state, legacy = _read_state(output)
    if state_hash != _state_snapshot_hash(output):
        raise StaleRunError("state changed while preparing the run")
    sessions, inventory = discover_sessions(home, current_thread_id=current_thread_id, include_stats=True)
    cached: list[dict[str, Any]] = []
    uncached: list[dict[str, Any]] = []
    cached_discovered = 0
    selected_sessions: dict[str, bool] = {}
    source_snapshots: dict[str, dict[str, Any]] = {}
    eligible_metas: list[dict[str, Any]] = []
    for session in sessions:
        key = session["session_key"]
        public_meta = _public_session_meta(
            session["meta"], session["project_alias"], session["project_label"]
        )
        public_meta["session_key"] = key
        eligible_metas.append(public_meta)
        source_snapshots[key] = {
            "source_hash": session["source_hash"],
        }
        entry = state["sessions"].get(key)
        facet = (
            _load_cached_facet(output, key, entry)
            if isinstance(entry, Mapping) and entry.get("source_hash") == session["source_hash"]
            else None
        )
        if facet is None:
            uncached.append(session)
        else:
            cached.append(facet)
            cached_discovered += 1
    selected = uncached[:max_new_sessions]
    for session in selected:
        selected_sessions[session["session_key"]] = True
    work_items = [_work_item(session) for session in selected]
    inventory.update(
        {
            "cached": cached_discovered,
            "selected": len(work_items),
            "remaining": max(0, inventory["eligible"] - cached_discovered - len(work_items)),
            "historical_cached": 0,
            "snapshot_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    return {
        "protocol_version": 5,
        "generation": state["generation"],
        "state_hash": state_hash,
        "language": language,
        "output_dir": str(output.resolve()),
        "work_items": work_items,
        "selected_sessions": selected_sessions,
        "source_snapshots": source_snapshots,
        "eligible_metas": eligible_metas,
        "cached_facets": cached,
        "inventory": inventory,
        "legacy_cache_detected": legacy,
    }


def _increment(counter: dict[str, int], values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            counter[str(key)] = counter.get(str(key), 0) + value


def aggregate_usage(metas: Iterable[Mapping[str, Any]], facets: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    metas = list(metas)
    if isinstance(facets, Mapping):
        facet_map = dict(facets)
        facet_list = [
            facet_map.get(str(meta.get("session_key") or meta.get("session_id", "")))
            for meta in metas
        ]
        facets = [facet for facet in facet_list if isinstance(facet, Mapping)]
    else:
        facets = list(facets)
        facet_map = {
            str(facet.get("session_key", index)): facet
            for index, facet in enumerate(facets)
        }

    def facet_for_meta(meta: Mapping[str, Any], index: int) -> Mapping[str, Any] | None:
        key = str(meta.get("session_key") or meta.get("session_id", ""))
        candidate = facet_map.get(key)
        if isinstance(candidate, Mapping):
            return candidate
        if index < len(facets) and isinstance(facets[index], Mapping):
            candidate = facets[index]
            candidate_key = str(candidate.get("session_key", ""))
            if not key or not candidate_key or candidate_key == key:
                return candidate
        return None

    def is_warmup(facet: Mapping[str, Any] | None) -> bool:
        if not isinstance(facet, Mapping):
            return False
        active = {
            str(key)
            for key, value in facet.get("goal_categories", {}).items()
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        }
        return active == {"warmup_minimal"}

    paired = [(meta, facet_for_meta(meta, index)) for index, meta in enumerate(metas)]
    metas = [meta for meta, facet in paired if not is_warmup(facet)]
    facets = [facet for facet in facets if not is_warmup(facet)]
    tool_counts: dict[str, int] = {}
    languages: dict[str, int] = {}
    projects: dict[str, int] = {}
    goal_categories: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    satisfaction: dict[str, int] = {}
    helpfulness: dict[str, int] = {}
    session_types: dict[str, int] = {}
    friction: dict[str, int] = {}
    success: dict[str, int] = {}
    tool_error_categories: dict[str, int] = {}
    message_hours: list[int] = []
    response_times: list[float] = []
    active_dates: set[str] = set()
    total_messages = 0
    total_duration_minutes = 0
    for meta in metas:
        total_messages += int(meta.get("user_message_count", 0))
        total_duration_minutes += int(meta.get("duration_minutes", 0))
        _increment(tool_counts, meta.get("tool_counts", {}))
        _increment(languages, meta.get("languages", {}))
        label = str(
            meta.get("project_alias")
            or meta.get("project_label")
            or meta.get("project_path")
            or "project-unknown"
        )
        projects[label] = projects.get(label, 0) + 1
        _increment(tool_error_categories, meta.get("tool_error_categories", {}))
        raw_hours = meta.get("message_hours", [])
        if isinstance(raw_hours, Mapping):
            for hour, count in raw_hours.items():
                message_hours.extend([int(hour)] * int(count))
        elif isinstance(raw_hours, Sequence) and not isinstance(raw_hours, (str, bytes, bytearray)):
            message_hours.extend(int(hour) for hour in raw_hours)
        response_times.extend(float(value) for value in meta.get("user_response_times", []) if isinstance(value, (int, float)))
        start = str(meta.get("start_time", ""))
        if start[:10]:
            active_dates.add(start[:10])
    for facet in facets:
        _increment(goal_categories, facet.get("goal_categories", {}))
        outcome = str(facet.get("outcome", "unclear_from_transcript"))
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        _increment(satisfaction, facet.get("user_satisfaction_counts", {}))
        help_value = str(facet.get("claude_helpfulness", ""))
        helpfulness[help_value] = helpfulness.get(help_value, 0) + 1
        session_type = str(facet.get("session_type", ""))
        session_types[session_type] = session_types.get(session_type, 0) + 1
        _increment(friction, facet.get("friction_counts", {}))
        primary = str(facet.get("primary_success", "none"))
        if primary != "none":
            success[primary] = success.get(primary, 0) + 1
    starts = sorted(active_dates)
    multi = detect_multi_clauding(metas)
    response_distribution = {
        "2_to_10_seconds": sum(2 < value < 10 for value in response_times),
        "10_to_30_seconds": sum(10 <= value < 30 for value in response_times),
        "30_seconds_to_1_minute": sum(30 <= value < 60 for value in response_times),
        "1_to_2_minutes": sum(60 <= value < 120 for value in response_times),
        "2_to_5_minutes": sum(120 <= value < 300 for value in response_times),
        "5_to_15_minutes": sum(300 <= value < 900 for value in response_times),
        "over_15_minutes": sum(value >= 900 for value in response_times),
    }
    return {
        "total_sessions": len(metas),
        "sessions_with_facets": len(facets),
        "date_range": {"start": starts[0] if starts else "", "end": starts[-1] if starts else ""},
        "total_messages": total_messages,
        "total_duration_hours": round(total_duration_minutes / 60, 1),
        "total_input_tokens": sum(int(meta.get("input_tokens", 0)) for meta in metas),
        "total_output_tokens": sum(int(meta.get("output_tokens", 0)) for meta in metas),
        "tool_counts": tool_counts,
        "languages": languages,
        "git_commits": sum(int(meta.get("git_commits", 0)) for meta in metas),
        "git_pushes": sum(int(meta.get("git_pushes", 0)) for meta in metas),
        "projects": projects,
        "goal_categories": goal_categories,
        "outcomes": outcomes,
        "satisfaction": satisfaction,
        "helpfulness": helpfulness,
        "session_types": session_types,
        "friction": friction,
        "success": success,
        "session_summaries": [
            {
                "id": str(meta.get("session_key") or meta.get("session_id", ""))[:8],
                "date": str(meta.get("start_time", ""))[:10],
                "summary": str(
                    meta.get("summary")
                    or meta.get("first_prompt")
                    or (matched_facet or {}).get("brief_summary", "")
                ),
                "goal": str((matched_facet or {}).get("underlying_goal", "")),
            }
            for index, meta in enumerate(metas[:50])
            for matched_facet in [facet_for_meta(meta, index)]
        ],
        "total_interruptions": sum(int(meta.get("user_interruptions", 0)) for meta in metas),
        "total_tool_errors": sum(int(meta.get("tool_errors", 0)) for meta in metas),
        "tool_error_categories": tool_error_categories,
        "user_response_times": response_times,
        "median_response_time": sorted(response_times)[len(response_times) // 2] if response_times else 0,
        "avg_response_time": round(mean(response_times), 1) if response_times else 0,
        "response_time_distribution": response_distribution,
        "sessions_using_task_agent": sum(bool(meta.get("uses_task_agent")) for meta in metas),
        "sessions_using_mcp": sum(bool(meta.get("uses_mcp")) for meta in metas),
        "sessions_using_web_search": sum(bool(meta.get("uses_web_search")) for meta in metas),
        "sessions_using_web_fetch": sum(bool(meta.get("uses_web_fetch")) for meta in metas),
        "total_lines_added": sum(int(meta.get("lines_added", 0)) for meta in metas),
        "total_lines_removed": sum(int(meta.get("lines_removed", 0)) for meta in metas),
        "total_files_modified": sum(int(meta.get("files_modified", 0)) for meta in metas),
        "lines_added": sum(int(meta.get("lines_added", 0)) for meta in metas),
        "lines_removed": sum(int(meta.get("lines_removed", 0)) for meta in metas),
        "files_modified": sum(int(meta.get("files_modified", 0)) for meta in metas),
        "days_active": len(active_dates),
        "messages_per_day": round(total_messages / len(active_dates), 1) if active_dates else 0,
        "message_hours": message_hours,
        "multi_clauding": {
            "overlap_events": multi["event_pair_count"],
            "sessions_involved": multi["session_count"],
            "user_messages_during": multi["user_messages_during"],
        },
    }


def _facet_tokens(facet: Mapping[str, Any]) -> set[str]:
    tokens = {
        "project:" + str(facet.get("project_alias", "project-unknown")),
        "outcome:" + str(facet.get("outcome", "")),
        "help:" + str(facet.get("claude_helpfulness", "")),
        "success:" + str(facet.get("primary_success", "none")),
        "month:" + str(facet.get("date", ""))[:7],
    }
    tokens.update("friction:" + str(key) for key, count in facet.get("friction_counts", {}).items() if count)
    tokens.update(
        "satisfaction:" + str(key)
        for key, count in facet.get("user_satisfaction_counts", {}).items()
        if count
    )
    return tokens


def _representative_facets(
    facets: Sequence[Mapping[str, Any]], *, limit: int
) -> list[Mapping[str, Any]]:
    """Greedily cover project/time/outcome/friction/feedback strata."""

    remaining = sorted(
        facets,
        key=lambda facet: (
            str(facet.get("date", "")),
            str(facet.get("session_key", "")),
        ),
        reverse=True,
    )
    selected: list[Mapping[str, Any]] = []
    covered: set[str] = set()
    while remaining and len(selected) < limit:
        best_index = max(
            range(len(remaining)),
            key=lambda index: (
                len(_facet_tokens(remaining[index]) - covered),
                str(remaining[index].get("date", "")),
                str(remaining[index].get("session_key", "")),
            ),
        )
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        covered.update(_facet_tokens(chosen))
    return selected


def build_lens_evidence(
    aggregate: Mapping[str, Any],
    facets: Iterable[Mapping[str, Any]],
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    facet_list = list(facets.values()) if isinstance(facets, Mapping) else list(facets)
    representatives = _representative_facets(facet_list, limit=50)
    summary_rows = [
        {
            "session": str(facet.get("session_key", ""))[:24],
            "date": str(facet.get("date", "")),
            "project_id": str(facet.get("project_alias", "project-unknown")),
            "goal": str(facet.get("underlying_goal", "")),
            "summary": str(facet.get("brief_summary", "")),
            "outcome": str(facet.get("outcome", "")),
            "helpfulness": str(facet.get("claude_helpfulness", "")),
            "success": str(facet.get("primary_success", "none")),
            "friction": dict(facet.get("friction_counts", {})),
            "satisfaction": dict(facet.get("user_satisfaction_counts", {})),
            "evidence": list(facet.get("evidence_anchors", []))[:4],
        }
        for facet in representatives
    ]
    friction_candidates = [
        facet
        for facet in facet_list
        if str(facet.get("friction_detail", "")).strip()
    ]
    friction_rows = [
        {
            "date": str(facet.get("date", "")),
            "project_id": str(facet.get("project_alias", "project-unknown")),
            "types": [str(key) for key, count in facet.get("friction_counts", {}).items() if count],
            "detail": str(facet.get("friction_detail", "")),
        }
        for facet in _representative_facets(friction_candidates, limit=20)
    ]
    instruction_groups: dict[str, dict[str, Any]] = {}
    for facet in facet_list:
        date = str(facet.get("date", ""))
        for raw in facet.get("user_instructions_to_codex", []):
            if not isinstance(raw, str) or not raw.strip():
                continue
            text = raw.strip()
            key = re.sub(r"\s+", " ", text).casefold()
            entry = instruction_groups.setdefault(
                key, {"text": text, "count": 0, "dates": set(), "latest_date": ""}
            )
            entry["count"] += 1
            if date:
                entry["dates"].add(date)
                if date >= entry["latest_date"]:
                    entry["latest_date"] = date
                    entry["text"] = text
    repeated_instructions = sorted(
        (
            {
                "text": entry["text"],
                "count": entry["count"],
                "dates": sorted(entry["dates"]),
                "latest_date": entry["latest_date"],
            }
            for entry in instruction_groups.values()
        ),
        key=lambda entry: (-entry["count"], entry["latest_date"], entry["text"]),
    )[:15]
    return {
        "aggregate": dict(aggregate),
        "project_distribution": dict(aggregate.get("projects", {})),
        "representative_summaries": summary_rows,
        "friction_details": friction_rows,
        "repeated_instructions": repeated_instructions,
        "coverage": dict(coverage or {}),
        "coverage_limited": bool((coverage or {}).get("remaining", 0)),
        "instruction_authority": "When instructions conflict, the latest explicit correction is authoritative.",
    }


def build_lens_material(
    aggregate: Mapping[str, Any],
    facets: Iterable[Mapping[str, Any]],
    coverage: Mapping[str, Any] | None = None,
) -> str:
    return json.dumps(
        build_lens_evidence(aggregate, facets, coverage=coverage),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _model_fields(facet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: facet[key]
        for key in (*_native_analysis.NATIVE_FACET_FIELDS, *sorted(_native_analysis.FACET_EXTENSION_FIELDS))
        if key in facet
    }


def _job_id(*parts: Any) -> str:
    return "job-" + hashlib.sha256("\0".join(map(str, parts)).encode("utf-8")).hexdigest()[:20]

def _chunk_jobs(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for item in run["work_items"]:
        for index, chunk in enumerate(item.get("chunks", [])):
            job_id = _job_id(run["run_id"], "chunk", item["session_key"], index)
            if job_id in run["job_results"] or job_id in run.get("job_skips", set()):
                continue
            jobs.append(
                {
                    "job_id": job_id,
                    "kind": "chunk_summary",
                    "session_key": item["session_key"],
                    "chunk_index": index,
                    "chunk_total": len(item["chunks"]),
                    "prompt": _native_analysis.build_chunk_summary_prompt(
                        chunk,
                        index=index,
                        total=len(item["chunks"]),
                        language=run["language"],
                    ),
                    "schema": {"required": ["summary"]},
                }
            )
    return jobs


def _session_material(run: Mapping[str, Any], item: Mapping[str, Any]) -> str | None:
    chunks = item.get("chunks", [])
    if not chunks:
        return str(item.get("material", ""))
    summaries: list[str] = []
    for index in range(len(chunks)):
        job_id = _job_id(run["run_id"], "chunk", item["session_key"], index)
        result = run["job_results"].get(job_id)
        if not isinstance(result, Mapping):
            return None
        summaries.append(str(result["summary"]))
    return (
        f"[Long session - {len(summaries)} parts summarized]\n\n"
        + "\n\n---\n\n".join(summaries)
    )


def _facet_jobs(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for item in run["work_items"]:
        job_id = _job_id(run["run_id"], "facet", item["session_key"])
        if job_id in run["job_results"] or job_id in run.get("job_skips", set()):
            continue
        material = _session_material(run, item)
        if material is None:
            continue
        jobs.append(
            {
                "job_id": job_id,
                "kind": "session_facet",
                "session_key": item["session_key"],
                "material": material,
                "prompt": build_facet_prompt(material, language=run["language"]),
                "schema": item["facet_schema"],
            }
        )
    return jobs


def _combined_facets(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    facets = list(run["cached_facets"])
    for item in run["work_items"]:
        job_id = _job_id(run["run_id"], "facet", item["session_key"])
        value = run["job_results"].get(job_id)
        if isinstance(value, Mapping):
            facets.append(dict(value))
    return facets


def _combined_metas(run: Mapping[str, Any], facets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    metas: list[dict[str, Any]] = []
    for facet in facets:
        meta = dict(facet["session_meta"])
        meta["session_key"] = facet["session_key"]
        metas.append(meta)
    return metas


def _ensure_aggregate(run: dict[str, Any]) -> None:
    if run.get("aggregate") is not None:
        return
    facets = _combined_facets(run)
    analyzed_metas = _combined_metas(run, facets)
    eligible_metas = list(run.get("eligible_metas") or analyzed_metas)
    run["eligible_aggregate"] = aggregate_usage(eligible_metas, facets)
    run["aggregate"] = aggregate_usage(analyzed_metas, facets)
    run["lens_material"] = build_lens_material(
        run["aggregate"], facets, coverage=run["inventory"]
    )


def _lens_jobs(run: dict[str, Any]) -> list[dict[str, Any]]:
    _ensure_aggregate(run)
    generated = build_lens_jobs(
        {"material": run["lens_material"]}, language=run["language"]
    )
    jobs: list[dict[str, Any]] = []
    for value in generated:
        lens_id = value["lens_id"]
        job_id = _job_id(run["run_id"], "lens", lens_id)
        if job_id in run["job_results"] or job_id in run.get("job_skips", set()):
            continue
        jobs.append({**value, "job_id": job_id})
    return jobs


def _lens_results(
    run: Mapping[str, Any], *, finalize_project_counts: bool = True
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for lens_id in LENS_IDS:
        job_id = _job_id(run["run_id"], "lens", lens_id)
        value = run["job_results"].get(job_id)
        if isinstance(value, Mapping):
            if lens_id == "project_areas" and finalize_project_counts:
                results[lens_id] = _native_analysis.finalize_project_areas(
                    value,
                    (run.get("aggregate") or {}).get("projects", {}),
                    language=str(run.get("language", LANGUAGE)),
                )
            else:
                results[lens_id] = dict(value)
    return results


def _glance_job(run: dict[str, Any]) -> dict[str, Any] | None:
    # At-a-Glance consumes the seven validated model schemas. Project counts
    # are helper-owned report data and are finalized only for rendering.
    lenses = _lens_results(run, finalize_project_counts=False)
    terminal = set(lenses) | {
        lens_id
        for lens_id in LENS_IDS
        if _job_id(run["run_id"], "lens", lens_id) in run.get("job_skips", set())
    }
    if terminal != set(LENS_IDS):
        return None
    job_id = _job_id(run["run_id"], "at-a-glance")
    if job_id in run["job_results"] or job_id in run.get("job_skips", set()):
        return None
    if set(lenses) == set(LENS_IDS):
        value = build_at_a_glance_job(
            {"aggregate": run["aggregate"], "lens_material": run["lens_material"]},
            lenses,
            language=run["language"],
        )
    else:
        payload = json.dumps(
            {
                "aggregate": run["aggregate"],
                "lens_material": run["lens_material"],
                "completed_lenses": lenses,
                "missing_lenses": sorted(set(LENS_IDS) - set(lenses)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        value = {
            "kind": "at_a_glance",
            "prompt": (
                f"Generate the four-field Codex Insights overview in {run['language']}. "
                "Use only the completed evidence below; explicitly acknowledge missing sections and do not infer them. "
                f"Return only JSON matching this schema: {json.dumps(_native_analysis.AT_A_GLANCE_SCHEMA, ensure_ascii=False)}\n{payload}"
            ),
            "schema": _native_analysis.AT_A_GLANCE_SCHEMA,
        }
    return {**value, "job_id": job_id}


def _report_aggregate(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(aggregate)
    raw_hours = aggregate.get("message_hours", [])
    if isinstance(raw_hours, Sequence) and not isinstance(raw_hours, (str, bytes, bytearray)):
        hours: dict[str, int] = {}
        for hour in raw_hours:
            key = str(hour).zfill(2)
            hours[key] = hours.get(key, 0) + 1
        value["message_hours"] = hours
    value["lines_added"] = int(aggregate.get("total_lines_added", aggregate.get("lines_added", 0)))
    value["lines_removed"] = int(aggregate.get("total_lines_removed", aggregate.get("lines_removed", 0)))
    value["files_modified"] = int(aggregate.get("total_files_modified", aggregate.get("files_modified", 0)))
    return value


def render_report(
    facets: Iterable[Mapping[str, Any]],
    language: str = LANGUAGE,
    coverage: Mapping[str, Any] | None = None,
    *,
    aggregate: Mapping[str, Any] | None = None,
    lenses: Mapping[str, Any] | None = None,
    at_a_glance: Mapping[str, Any] | None = None,
    **_ignored: Any,
) -> str:
    validate_language(language)
    facet_list = list(facets)
    if aggregate is None:
        aggregate = aggregate_usage(
            [facet["session_meta"] for facet in facet_list if isinstance(facet.get("session_meta"), Mapping)],
            facet_list,
        )
    return render_native_report(
        _report_aggregate(aggregate),
        lenses or {},
        at_a_glance or {},
        language=language,
        coverage=coverage,
    )


def _preview(run: dict[str, Any]) -> str:
    glance = run["job_results"].get(_job_id(run["run_id"], "at-a-glance"))
    if not isinstance(glance, Mapping):
        if _job_id(run["run_id"], "at-a-glance") not in run.get("job_skips", set()):
            raise InsightsError("At-a-Glance must complete before preview")
        concern = "At-a-Glance 模型调用失败；本节已降级，其他成功章节仍保留。"
        glance = {field: concern for field in _native_analysis.AT_A_GLANCE_FIELDS}
    report = render_report(
        _combined_facets(run),
        language=run["language"],
        coverage=run["inventory"],
        aggregate=run["aggregate"],
        lenses=_lens_results(run),
        at_a_glance=glance,
    )
    if privacy_violations(report):
        raise PrivacyError("rendered report contains a private value")
    return report


def _ensure_preview(run: dict[str, Any]) -> str:
    preview = run.get("preview_html")
    if not isinstance(preview, str):
        preview = _preview(run)
        run["preview_html"] = preview
    return preview


def _stage(run: dict[str, Any]) -> dict[str, Any]:
    chunks = _chunk_jobs(run)
    if chunks:
        return {"stage": "chunk_summaries", "jobs": chunks}
    facets = _facet_jobs(run)
    if facets:
        return {"stage": "session_facets", "jobs": facets}
    lenses = _lens_jobs(run)
    if lenses:
        return {"stage": "lenses", "jobs": lenses}
    glance = _glance_job(run)
    if glance is not None:
        return {"stage": "at_a_glance", "jobs": [glance]}
    preview = _ensure_preview(run)
    encoded = preview.encode("utf-8")
    return {
        "stage": "ready_to_commit",
        "jobs": [],
        "preview_bytes": len(encoded),
        "preview_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _validated_job_result(run: Mapping[str, Any], job: Mapping[str, Any], value: Any) -> dict[str, Any]:
    kind = job["kind"]
    if kind == "chunk_summary":
        if not isinstance(value, Mapping) or set(value) != {"summary"} or not isinstance(value["summary"], str) or not value["summary"].strip():
            raise FacetValidationError("chunk result must contain one non-empty summary")
        if len(value["summary"]) > 8_000:
            raise FacetValidationError("chunk summary is too long")
        accepted: dict[str, Any] = {"summary": value["summary"]}
    elif kind == "session_facet":
        model = validate_native_facet(value)
        item = next(item for item in run["work_items"] if item["session_key"] == job["session_key"])
        accepted = {
            key: item[key]
            for key in (
                "schema_version",
                "analysis_version",
                "meta_schema_version",
                "normalizer_version",
                "facet_prompt_version",
                "analysis_origin",
                "session_key",
                "source_hash",
                "date",
                "project_alias",
                "project_label",
                "session_origin",
                "session_class",
                "session_meta",
                "privacy_redactions",
            )
        }
        accepted.update(model)
        _validate_persisted_facet(accepted, item)
    elif kind == "lens":
        accepted = validate_lens_result(job["lens_id"], value)
    elif kind == "at_a_glance":
        accepted = validate_at_a_glance(value)
    else:
        raise InsightsError(f"unsupported job kind: {kind}")
    if privacy_violations(json.dumps(accepted, ensure_ascii=False, sort_keys=True)):
        raise PrivacyError(f"{kind} result contains a private value")
    return accepted


def _accept_job(run: dict[str, Any], job_id: str, value: Any) -> None:
    """Accept one result; batch callers must validate the whole batch first."""

    if job_id in run["job_results"]:
        raise InsightsError(f"job already submitted: {job_id}")
    current = _stage(run)
    expected = {job["job_id"]: job for job in current["jobs"]}
    job = expected.get(job_id)
    if job is None:
        raise InsightsError(f"unknown or currently blocked job: {job_id}")
    accepted = _validated_job_result(run, job, value)
    run["job_results"][job_id] = accepted


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o600)


def _acquire_lock(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ".insights.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ConcurrentRunError("another Insights commit holds the lock") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()}\n")
    return path


def _timestamp_filename() -> str:
    return datetime.now(timezone.utc).strftime("report-%Y%m%dT%H%M%SZ.html")


def _verify_run_snapshot(run: Mapping[str, Any]) -> None:
    """Verify only Insights-owned state.

    Transcript files are append-only live inputs.  The run analyzes the
    immutable, redacted material captured during prepare; later source changes
    intentionally invalidate the next cache lookup, not the current commit.
    """

    output = Path(run["output_dir"])
    if _state_snapshot_hash(output) != run.get("state_hash"):
        raise StaleRunError("state changed after prepare")


def _verify_sources(run: Mapping[str, Any]) -> None:
    """Backward-compatible alias for callers that only need snapshot verification."""

    _verify_run_snapshot(run)


def commit_run(run: dict[str, Any], failpoint: str | None = None) -> dict[str, Any]:
    ready = _stage(run)
    if ready["stage"] != "ready_to_commit":
        raise InsightsError(f"run is incomplete: {ready['stage']}")
    output = Path(run["output_dir"])
    lock = _acquire_lock(output)
    staging = output / f".staging-{uuid.uuid4().hex}"
    backup = output / f".backup-{uuid.uuid4().hex}"
    installed: list[Path] = []
    backed_up: list[tuple[Path, Path]] = []
    try:
        _verify_run_snapshot(run)
        current, legacy = _read_state(output)
        if current["generation"] != run["generation"]:
            raise StaleRunError("state generation changed after prepare")
        if legacy != bool(run["legacy_cache_detected"]):
            raise StaleRunError("cache compatibility changed after prepare")
        supplied = [
            facet
            for facet in _combined_facets(run)
            if facet["session_key"] in run["selected_sessions"]
        ]
        combined = _combined_facets(run)
        timestamp_name = _timestamp_filename()
        if (output / timestamp_name).exists():
            raise InsightsError(f"timestamp report already exists: {timestamp_name}")
        report = _ensure_preview(run).encode("utf-8")
        artifacts: dict[str, bytes] = {
            "report.html": report,
            timestamp_name: report,
        }
        old_facet_paths = sorted((output / "facets").glob("*.json")) if (output / "facets").exists() else []
        if legacy:
            legacy_stamp = timestamp_name.removeprefix("report-").removesuffix(".html")
            legacy_root = f"legacy/{legacy_stamp}"
            for name in ("state.json", "manifest.json"):
                path = output / name
                if path.is_file():
                    artifacts[f"{legacy_root}/{name}"] = path.read_bytes()
            for path in old_facet_paths:
                artifacts[f"{legacy_root}/facets/{path.name}"] = path.read_bytes()
        sessions = {} if legacy else dict(current["sessions"])
        for facet in supplied:
            filename = _facet_filename(facet)
            sessions[facet["session_key"]] = {
                "source_hash": facet["source_hash"],
                "facet_file": filename,
                "analysis_version": ANALYSIS_VERSION,
            }
            artifacts[filename] = _json_bytes(facet)
        generation = current["generation"] + 1
        state = {
            "generation": generation,
            "analysis_version": ANALYSIS_VERSION,
            "meta_schema_version": META_SCHEMA_VERSION,
            "normalizer_version": NORMALIZER_VERSION,
            "facet_prompt_version": FACET_PROMPT_VERSION,
            "lens_prompt_version": LENS_PROMPT_VERSION,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "sessions": sessions,
            "coverage": run["inventory"],
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        state_bytes = _json_bytes(state)
        manifest_files = {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(artifacts.items())
            if not name.startswith("legacy/")
        }
        for entry in sessions.values():
            relative = entry["facet_file"]
            if relative in artifacts:
                data = artifacts[relative]
            else:
                path = _manifest_file_path(output, relative)
                if path is None:
                    raise InsightsError("state references an unsafe facet path")
                try:
                    data = path.read_bytes()
                except OSError as exc:
                    raise InsightsError("state references a missing facet") from exc
            manifest_files[relative] = hashlib.sha256(data).hexdigest()
        state_digest = hashlib.sha256(state_bytes).hexdigest()
        manifest_files["state.json"] = state_digest
        manifest = {
            "generation": generation,
            "language": run["language"],
            "report": "report.html",
            "timestamp_report": timestamp_name,
            "facet_count": len(sessions),
            "coverage": run["inventory"],
            "analysis": {
                "analysis_version": ANALYSIS_VERSION,
                "meta_schema": META_SCHEMA_VERSION,
                "normalizer": NORMALIZER_VERSION,
                "facet_prompt": FACET_PROMPT_VERSION,
                "facet_schema": FACET_SCHEMA_VERSION,
                "lens_prompt": LENS_PROMPT_VERSION,
                "report_schema": REPORT_SCHEMA_VERSION,
            },
            "state_sha256": state_digest,
            "files": dict(sorted(manifest_files.items())),
        }
        artifacts["manifest.json"] = _json_bytes(manifest)
        artifacts["state.json"] = state_bytes
        for relative, data in artifacts.items():
            _write_bytes(staging / relative, data)
        ordered = [name for name in artifacts if name != "state.json"] + ["state.json"]
        backup.mkdir(parents=True, exist_ok=True)
        for index, relative in enumerate(ordered):
            if relative == "state.json":
                _verify_run_snapshot(run)
            target = output / relative
            staged = staging / relative
            saved = backup / relative
            if target.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, saved)
                backed_up.append((saved, target))
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            target.chmod(0o600)
            installed.append(target)
            if failpoint == "before_state" and relative != "state.json" and index == len(ordered) - 2:
                raise RuntimeError("injected failure before state commit")
        referenced = {entry["facet_file"] for entry in sessions.values()}
        for old_path in old_facet_paths:
            relative = old_path.relative_to(output).as_posix()
            if relative in referenced or not old_path.exists():
                continue
            saved = backup / ".orphan-facets" / old_path.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old_path, saved)
            backed_up.append((saved, old_path))
        actual_facets = {
            path.relative_to(output).as_posix()
            for path in (output / "facets").glob("*.json")
        } if (output / "facets").exists() else set()
        if actual_facets != referenced:
            raise InsightsError("facet directory does not match committed state")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        return {
            "generation": generation,
            "report_path": str(output / "report.html"),
            "timestamp_report_path": str(output / timestamp_name),
            "manifest_path": str(output / "manifest.json"),
            "facet_count": len(sessions),
            "coverage": run["inventory"],
        }
    except Exception:
        for target in reversed(installed):
            try:
                target.unlink()
            except FileNotFoundError:
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
