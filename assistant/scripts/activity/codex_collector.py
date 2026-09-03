"""Collect activity from Codex's local history and rollout files."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from .common import Event, Report, clean_excerpt, detect_domain, iter_jsonl, make_summary, match_mit, parse_mit, to_local


def _session_names(home: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in iter_jsonl(home / "session_index.jsonl") or ():
        session_id = row.get("id")
        name = row.get("thread_name")
        if session_id and name:
            names[session_id] = name
    return names


def _rollout_metadata(home: Path, session_ids: set[str]) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    paths = list((home / "sessions").glob("**/rollout-*.jsonl"))
    paths.extend((home / "archived_sessions").glob("**/rollout-*.jsonl"))
    for path in paths:
        if session_ids and not any(session_id in path.name for session_id in session_ids):
            continue
        for row in iter_jsonl(path) or ():
            if row.get("type") != "session_meta":
                continue
            payload = row.get("payload") or {}
            session_id = payload.get("id")
            if session_id in session_ids:
                metadata[session_id] = {
                    "cwd": payload.get("cwd", ""),
                    "started_at": payload.get("timestamp", ""),
                }
            break
    return metadata


def _session_rows(events: list[Event]) -> list[dict]:
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_session[event.session_id].append(event)
    result = []
    for session_id, rows in sorted(by_session.items(), key=lambda pair: pair[1][0].time):
        rows.sort(key=lambda event: event.time)
        result.append({
            "id": session_id,
            "name": rows[0].session_name,
            "project": rows[0].project,
            "cwd": rows[0].cwd,
            "origin": "codex-local",
            "time_range": f"{rows[0].time}-{rows[-1].time}",
            "messages": len(rows),
            "files": [],
        })
    return result


def collect(target_date: date, *, home: Path, vault: Path | None = None) -> Report:
    names = _session_names(home)
    raw: list[tuple[str, object, str]] = []
    for row in iter_jsonl(home / "history.jsonl") or ():
        session_id = row.get("session_id")
        local = to_local(row.get("ts"))
        text = row.get("text", "")
        if session_id and local and local.date() == target_date and text:
            raw.append((session_id, local, clean_excerpt(text)))

    metadata = _rollout_metadata(home, {session_id for session_id, _, _ in raw})
    timeline: list[Event] = []
    for session_id, local, text in sorted(raw, key=lambda item: item[1]):
        cwd = metadata.get(session_id, {}).get("cwd", "")
        name = names.get(session_id, session_id[:12])
        timeline.append(Event(
            time=local.strftime("%H:%M"),
            ts=local.isoformat(),
            origin="codex-local",
            session_id=session_id,
            session_name=name,
            project=Path(cwd).name if cwd else "",
            cwd=cwd,
            content=text,
            domain=detect_domain(text, cwd),
        ))

    mit_items = parse_mit(vault, target_date) if vault else []
    report = Report(
        date=target_date.isoformat(),
        origin="codex-local",
        hosts=["codex"],
        timeline=timeline,
        sessions=_session_rows(timeline),
    )
    report.summary = make_summary(timeline)
    report.mit = {"date": target_date.isoformat() if mit_items else None, "items": mit_items, "matched": match_mit(timeline, mit_items)}
    return report
