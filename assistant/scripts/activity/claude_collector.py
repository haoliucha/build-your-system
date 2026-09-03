"""Collect user activity from Claude Code's local JSONL sessions."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .common import Event, Report, clean_excerpt, detect_domain, iter_jsonl, local_day_bounds, make_summary, match_mit, parse_mit, to_local

COMMAND_GOALS = {
    "assistant:a-setup": "初始化配置",
    "assistant:c-capture": "快速捕获",
    "assistant:c-pause": "间隙记录",
    "assistant:c-dump": "脑暴倾倒",
    "assistant:cc-activity": "活动分析",
    "assistant:d-mine": "选题挖矿",
    "assistant:e-export": "导出对话",
    "assistant:o-review": "每日回顾",
    "assistant:o-schedule": "作息状态",
    "assistant:o-tasks": "任务概览",
    "assistant:o-weekly": "每周整合",
}
IGNORED_COMMANDS = {"clear", "help", "exit", "quit", "rename", "compact", "model", "mcp"}
COMMAND_RE = re.compile(r"<command-name>/(?:(?P<plugin>[\w-]+):)?(?P<cmd>[\w-]+)</command-name>")
COMMAND_ARGS_RE = re.compile(r"<command-args>(?P<args>.*?)</command-args>", re.DOTALL)
SYSTEM_PREFIXES = (
    "<task-notification>",
    "<system-reminder>",
    "<local-command-stdout>",
    "<local-command-caveat>",
)
CONTINUED_SUMMARY = "This session is being continued from a previous conversation"


def _content(record: dict) -> str:
    message = record.get("message")
    raw = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "\n".join(item.get("text", "") for item in raw if isinstance(item, dict) and item.get("type") == "text")
    return ""


def _file_paths(value) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        path = value.get("filePath")
        if isinstance(path, str) and path:
            paths.add(path)
        for item in value.values():
            paths.update(_file_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.update(_file_paths(item))
    return paths


def _session_name(custom_title: str | None, slug: str | None, session_id: str) -> str:
    return (custom_title or slug or session_id[:12]).strip()


def _command(text: str) -> tuple[str | None, str | None]:
    """Return the normalized command and the useful command content."""
    match = COMMAND_RE.search(text)
    if not match:
        return None, None
    plugin = match.group("plugin")
    command = f"{plugin}:{match.group('cmd')}" if plugin else match.group("cmd")
    args_match = COMMAND_ARGS_RE.search(text)
    args = args_match.group("args").strip() if args_match else ""
    return command, args or f"/{command}"


def _is_system_record(record: dict, text: str, command: str | None) -> bool:
    """Exclude Claude's injected/continuation records, but keep real commands."""
    if record.get("isCompactSummary"):
        return True
    stripped = text.lstrip()
    if stripped.startswith(SYSTEM_PREFIXES) or CONTINUED_SUMMARY in text:
        return True
    if command is None and (
        "<command-message>" in text or "<local-command-stdout>" in text
    ):
        return True
    return "[Request interrupted" in text


def collect(target_date: date, *, home: Path, vault: Path | None = None) -> Report:
    start, _ = local_day_bounds(target_date)
    cutoff = start - timedelta(days=1)
    projects_root = home / "projects"
    paths = sorted(path for path in projects_root.glob("*/*.jsonl") if path.is_file()) if projects_root.is_dir() else []
    file_data: list[tuple[Path, list[dict], str, str | None, str | None, str, str]] = []
    session_meta: dict[str, dict[str, str | None]] = {}

    for path in paths:
        try:
            if to_local(path.stat().st_mtime) is None or to_local(path.stat().st_mtime) < cutoff:
                continue
        except OSError:
            continue
        fallback_id = path.stem
        custom_title = None
        slug = None
        session_id = fallback_id
        cwd = ""
        rows = list(iter_jsonl(path) or ())
        for record in rows:
            if record.get("type") == "custom-title":
                custom_title = record.get("customTitle") or record.get("title") or custom_title
            if record.get("type") == "user":
                session_id = record.get("sessionId") or session_id
                slug = record.get("slug") or slug
                cwd = record.get("cwd") or cwd
        file_data.append((path, rows, fallback_id, custom_title, slug, session_id, cwd))
        metadata = session_meta.setdefault(session_id, {"custom_title": None, "slug": None, "cwd": ""})
        metadata["custom_title"] = metadata["custom_title"] or custom_title
        metadata["slug"] = metadata["slug"] or slug
        metadata["cwd"] = metadata["cwd"] or cwd

    candidates: list[dict] = []
    for path, rows, fallback_id, custom_title, slug, file_session_id, file_cwd in file_data:
        touched: set[str] = set()
        for record in rows:
            if record.get("type") != "user" or record.get("isMeta"):
                continue
            local = to_local(record.get("timestamp"))
            if not local or local.date() != target_date:
                continue
            text = _content(record)
            if not text:
                continue
            command, command_content = _command(text)
            if _is_system_record(record, text, command):
                continue
            if command and (command in IGNORED_COMMANDS or command.rsplit(":", 1)[-1] in IGNORED_COMMANDS):
                continue
            touched.update(_file_paths(record.get("toolUseResult")))
            session_id = str(record.get("sessionId") or file_session_id or fallback_id)
            metadata = session_meta.setdefault(session_id, {"custom_title": None, "slug": None, "cwd": ""})
            cwd = str(record.get("cwd") or metadata["cwd"] or file_cwd or "")
            name = _session_name(
                metadata["custom_title"] or custom_title,
                metadata["slug"] or slug,
                session_id,
            )
            candidates.append({
                "dedup_key": (
                    session_id,
                    "uuid",
                    str(record["uuid"]),
                ) if record.get("uuid") else (
                    session_id,
                    "fallback",
                    record.get("timestamp"),
                    text[:80],
                ),
                "content_key": " ".join(text.split()),
                "time": local.strftime("%H:%M"),
                "ts": record.get("timestamp"),
                "session_id": session_id,
                "session_name": name,
                "project": Path(cwd).name if cwd else "",
                "cwd": cwd,
                "text": command_content if command else text,
                "kind": "command" if command else "prompt",
                "command": command,
                "domain": detect_domain(text, [cwd, *touched]),
                "sidechain": bool(record.get("isSidechain")),
                "files": touched,
            })

    primary_content = {
        (candidate["session_id"], candidate["content_key"])
        for candidate in candidates
        if not candidate["sidechain"]
    }
    deduplicated: dict[tuple, dict] = {}
    for candidate in candidates:
        if candidate["sidechain"] and (candidate["session_id"], candidate["content_key"]) in primary_content:
            continue
        existing = deduplicated.get(candidate["dedup_key"])
        if existing is None or (existing["sidechain"] and not candidate["sidechain"]):
            deduplicated[candidate["dedup_key"]] = candidate

    events: list[Event] = []
    session_data: dict[str, dict] = {}
    for candidate in deduplicated.values():
        event = Event(
            time=candidate["time"],
            ts=candidate["ts"],
            origin="claude-local",
            session_id=candidate["session_id"],
            session_name=candidate["session_name"],
            project=candidate["project"],
            cwd=candidate["cwd"],
            content=clean_excerpt(candidate["text"]),
            kind=candidate["kind"],
            command=candidate["command"],
            domain=candidate["domain"],
            sidechain=candidate["sidechain"],
        )
        events.append(event)
        data = session_data.setdefault(candidate["session_id"], {
            "events": [],
            "files": set(),
            "name": candidate["session_name"],
            "project": candidate["project"],
            "cwd": candidate["cwd"],
        })
        data["events"].append(event)
        data["files"].update(candidate["files"])

    events.sort(key=lambda event: (event.ts or "", event.time))
    sessions = []
    for session_id, data in sorted(session_data.items(), key=lambda item: item[1]["events"][0].time):
        rows = sorted(data["events"], key=lambda event: (event.ts or "", event.time))
        sessions.append({
            "id": session_id,
            "name": data["name"],
            "project": data["project"],
            "cwd": data["cwd"],
            "origin": "claude-local",
            "time_range": f"{rows[0].time}-{rows[-1].time}",
            "messages": len(rows),
            "files": sorted(data["files"])[:10],
        })
    mit_items = parse_mit(vault, target_date) if vault else []
    return Report(
        date=target_date.isoformat(),
        origin="claude-local",
        hosts=["claude"],
        summary=make_summary(events),
        sessions=sessions,
        timeline=events,
        mit={"date": target_date.isoformat() if mit_items else None, "items": mit_items, "matched": match_mit(events, mit_items)},
    )
