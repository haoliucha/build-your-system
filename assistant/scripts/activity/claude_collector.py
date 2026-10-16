"""Collect user activity from Claude Code's local JSONL sessions."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .common import Event, Report, clean_excerpt, detect_domain, load_project_map, local_day_bounds, make_summary, match_mit, parse_mit, to_local

from .source_health import JsonlSource, host_health

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


EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _edited_paths(record: dict) -> set[str]:
    """File paths an assistant record writes through edit tools (reads are ignored)."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    paths: set[str] = set()
    for item in content if isinstance(content, list) else ():
        if not isinstance(item, dict) or item.get("type") != "tool_use" or item.get("name") not in EDIT_TOOLS:
            continue
        tool_input = item.get("input") or {}
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if isinstance(path, str) and path:
            paths.add(path)
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
    source = JsonlSource(projects_root)
    paths = [p for p in source.discover(projects_root, "*.jsonl") if p.parent.parent == projects_root]
    file_data: list[tuple[Path, list[dict], str, str | None, str | None, str, str]] = []
    session_meta: dict[str, dict[str, str | None]] = {}

    for path in paths:
        try:
            if to_local(path.stat().st_mtime) is None or to_local(path.stat().st_mtime) < cutoff:
                continue
        except OSError as exc:
            source.error(path, type(exc).__name__)
            continue
        fallback_id = path.stem
        custom_title = None
        slug = None
        session_id = fallback_id
        cwd = ""
        rows = list(source.read(path))
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
        last_candidate: dict | None = None
        for record in rows:
            if record.get("type") == "assistant" and last_candidate is not None:
                # 编辑工具写入的文件归到触发它的那条用户消息上。
                edited_at = to_local(record.get("timestamp"))
                if edited_at and edited_at.date() == target_date:
                    last_candidate["files"].update(_edited_paths(record))
                continue
            if record.get("type") != "user" or record.get("isMeta"):
                continue
            local = to_local(record.get("timestamp"))
            timestamp_key = local.strftime("%Y-%m-%dT%H:%M") if local else str(record.get("timestamp") or "")
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
            session_id = str(record.get("sessionId") or file_session_id or fallback_id)
            metadata = session_meta.setdefault(session_id, {"custom_title": None, "slug": None, "cwd": ""})
            cwd = str(record.get("cwd") or metadata["cwd"] or file_cwd or "")
            name = _session_name(
                metadata["custom_title"] or custom_title,
                metadata["slug"] or slug,
                session_id,
            )
            candidates.append({
                "dedup_key": (session_id, timestamp_key, text[:80]),
                "uuid": str(record.get("uuid") or ""),
                "time": local.strftime("%H:%M"),
                "ts": record.get("timestamp"),
                "session_id": session_id,
                "session_name": name,
                "project": Path(cwd).name if cwd else "",
                "cwd": cwd,
                "text": command_content if command else text,
                "kind": "command" if command else "prompt",
                "command": command,
                "sidechain": bool(record.get("isSidechain")),
                "files": set(),
                "titled": bool(metadata["custom_title"] or custom_title),
                "automated": str(record.get("entrypoint") or "").startswith("sdk-"),
                "turn_origin": record.get("turnOrigin"),
            })
            last_candidate = candidates[-1]

    # 第一层：同 uuid 必是同一条记录（fork 会话会整份复制 transcript 并改写 sessionId）。
    by_uuid: dict[str, dict] = {}
    unique_candidates: list[dict] = []
    for candidate in candidates:
        if not candidate["uuid"]:
            unique_candidates.append(candidate)
            continue
        existing = by_uuid.get(candidate["uuid"])
        if existing is None:
            by_uuid[candidate["uuid"]] = candidate
            unique_candidates.append(candidate)
        elif existing["sidechain"] and not candidate["sidechain"]:
            existing.update(candidate)
    # 第二层：同 session 内同一分钟、同内容前 80 字视为重复（子代理 transcript 的 uuid 不同）。
    deduplicated: dict[tuple, dict] = {}
    for candidate in unique_candidates:
        existing = deduplicated.get(candidate["dedup_key"])
        if existing is None or (existing["sidechain"] and not candidate["sidechain"]):
            deduplicated[candidate["dedup_key"]] = candidate

    project_map = load_project_map(vault)
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
            domain=detect_domain(candidate["text"], [candidate["cwd"], *sorted(candidate["files"])], project_map),
            sidechain=candidate["sidechain"],
        )
        events.append(event)
        data = session_data.setdefault(candidate["session_id"], {
            "events": [],
            "files": set(),
            "name": candidate["session_name"],
            "project": candidate["project"],
            "cwd": candidate["cwd"],
            "titled": False,
            "automated": False,
            "turn_origins": set(),
        })
        data["events"].append(event)
        data["files"].update(candidate["files"])
        data["titled"] = data["titled"] or candidate["titled"]
        data["automated"] = data["automated"] or candidate["automated"]
        data["turn_origins"].add(candidate["turn_origin"])

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
            "titled": data["titled"],
            # SDK 入口（如自动安全审查）或无标题、单条、由程序发起的会话，归并到父会话的目标里。
            "automated": data["automated"] or (
                not data["titled"] and len(rows) == 1 and data["turn_origins"] == {"sdk"}
            ),
        })
    mit_items = parse_mit(vault, target_date) if vault else []
    return Report(
        date=target_date.isoformat(),
        origin="claude-local",
        hosts=["claude"],
        source_health={"claude": host_health({"projects": source}, len(events), target_date)},
        summary=make_summary(events),
        sessions=sessions,
        timeline=events,
        mit={"date": target_date.isoformat() if mit_items else None, "items": mit_items, "matched": match_mit(events, mit_items)},
    )
