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


def collect(target_date: date, *, home: Path, vault: Path | None = None) -> Report:
    start, _ = local_day_bounds(target_date)
    cutoff = start - timedelta(days=1)
    events: list[Event] = []
    session_data: dict[str, dict] = {}
    projects_root = home / "projects"
    paths = sorted(path for path in projects_root.glob("*/*.jsonl") if path.is_file()) if projects_root.is_dir() else []
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
                custom_title = record.get("customTitle") or custom_title
            if record.get("type") == "user":
                session_id = record.get("sessionId") or session_id
                slug = record.get("slug") or slug
                cwd = record.get("cwd") or cwd
        name = _session_name(custom_title, slug, session_id)
        touched: set[str] = set()
        for record in rows:
            if record.get("type") != "user" or record.get("isMeta"):
                continue
            local = to_local(record.get("timestamp"))
            if not local or local.date() != target_date:
                continue
            text = _content(record)
            if not text or any(marker in text for marker in ("<local-command-stdout>", "<command-message>", "[Request interrupted")):
                continue
            touched.update(_file_paths(record.get("toolUseResult")))
            command = None
            command_match = COMMAND_RE.search(text)
            if command_match:
                plugin = command_match.group("plugin")
                command = f"{plugin}:{command_match.group('cmd')}" if plugin else command_match.group("cmd")
                if command in IGNORED_COMMANDS or command.rsplit(":", 1)[-1] in IGNORED_COMMANDS:
                    continue
            event = Event(
                time=local.strftime("%H:%M"),
                ts=record.get("timestamp"),
                origin="claude-local",
                session_id=session_id,
                session_name=name,
                project=Path(cwd).name if cwd else "",
                cwd=cwd,
                content=clean_excerpt(text),
                kind="command" if command else "prompt",
                command=command,
                domain=detect_domain(text, [cwd, *touched]),
                sidechain=bool(record.get("isSidechain")),
            )
            events.append(event)
            session_data.setdefault(session_id, {"events": [], "files": set(), "name": name, "project": event.project, "cwd": cwd})
            session_data[session_id]["events"].append(event)
            session_data[session_id]["files"].update(touched)

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
