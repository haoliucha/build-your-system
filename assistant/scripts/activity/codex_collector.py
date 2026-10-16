"""Collect Codex user messages from rollouts, with legacy history compatibility."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .common import Event, Report, clean_excerpt, detect_domain, iter_jsonl, load_project_map, make_summary, match_mit, parse_mit, to_local
from .source_health import JsonlSource, host_health

# These are host-injected documents, not user requests. Strip complete wrappers so
# a user request following an injected block in the same record remains available.
INJECTION_TAGS = ("recommended_plugins", "environment_context", "skill", "system-reminder",
                  "task-notification", "permissions_instructions", "permissions", "turn_aborted")
SKILL_CALL = re.compile(r"\[\$(?P<name>[\w:-]+)\]\(")


def _user_text(raw) -> str:
    if isinstance(raw, list):
        raw = "\n".join(item.get("text", "") for item in raw
                        if isinstance(item, dict) and isinstance(item.get("text"), str)
                        and item.get("type") in {"input_text", "text"})
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    if text.startswith(("# AGENTS.md instructions for ", "<INSTRUCTIONS>",
                        "This session is being continued from a previous conversation",
                        "[Request interrupted")):
        return ""
    for tag in INJECTION_TAGS:
        text = re.sub(rf"<{tag}(?:\s[^>]*)?>.*?</{tag}>", "", text, flags=re.DOTALL).strip()
    if text.startswith(("# AGENTS.md instructions for ", "<INSTRUCTIONS>",
                        "<skill>", "<environment_context>", "<recommended_plugins>")):
        return ""
    return text


def _session_names(home: Path) -> dict[str, str]:
    return {str(row["id"]): str(row["thread_name"])
            for row in iter_jsonl(home / "session_index.jsonl") or ()
            if isinstance(row, dict) and row.get("id") and row.get("thread_name")}


def _deduplicate(candidates: list[dict]) -> list[dict]:
    """Pair alternative representations one-to-one; don't collapse repeated prompts."""
    selected = []
    groups = defaultdict(list)
    identities = set()
    exact = set()
    occurrences = Counter()
    for candidate in sorted(candidates, key=lambda c: (c["rank"], c["local"], c["path"], c["line"])):
        session = candidate["session"]
        identity = (session, candidate["id"]) if candidate["id"] else None
        base = (session, candidate["local"].isoformat(), candidate["text"], candidate["representation"])
        occurrence_key = (candidate["path"], base)
        occurrences[occurrence_key] += 1
        same = (*base, occurrences[occurrence_key])
        # Archive/live copies preserve message IDs or timestamp/content. A fresh
        # record with a different explicit ID is still a separate user message.
        if identity and identity in identities:
            continue
        if not identity and same in exact:
            continue
        if identity:
            identities.add(identity)
        exact.add(same)
        key = (session, candidate["text"])
        match = None
        for existing in groups[key]:
            if candidate["representation"] in existing["paired"]:
                continue
            distance = abs((candidate["local"] - existing["local"]).total_seconds())
            if distance <= 2:
                match = existing
                break
        if match:
            match["paired"].add(candidate["representation"])
        else:
            candidate["paired"] = {candidate["representation"]}
            groups[key].append(candidate)
            selected.append(candidate)
    return sorted(selected, key=lambda c: c["local"])


def collect(target_date: date, *, home: Path, vault: Path | None = None) -> Report:
    names = _session_names(home)
    sources = {key: JsonlSource(home / key) for key in ("sessions", "archived_sessions", "history.jsonl")}
    metadata = {}
    candidates = []

    def add(session, timestamp, raw, representation, path, line, message_id=""):
        local = to_local(timestamp)
        if not session or not local or local.date() != target_date:
            return
        text = _user_text(raw)
        if text:
            candidates.append({"session": str(session), "local": local, "text": text,
                               "representation": representation,
                               "rank": {"response_item": 0, "event_msg": 1, "history": 2}[representation],
                               "path": str(path), "line": line, "id": message_id})

    for key in ("sessions", "archived_sessions"):
        source = sources[key]
        for path in source.discover(home / key, "rollout-*.jsonl"):
            session = None
            for number, row in enumerate(source.read(path), 1):
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    continue
                if row.get("type") == "session_meta":
                    session = payload.get("id")
                    if session:
                        metadata.setdefault(str(session), {}).update({"cwd": payload.get("cwd", "")})
                elif row.get("type") == "response_item" and payload.get("role") == "user":
                    add(session, row.get("timestamp"), payload.get("content"), "response_item", path, number, payload.get("id", ""))
                elif row.get("type") == "event_msg" and payload.get("type") == "user_message":
                    add(session, row.get("timestamp"), payload.get("message"), "event_msg", path, number)
    history = home / "history.jsonl"
    for number, row in enumerate(sources["history.jsonl"].read(history), 1):
        add(row.get("session_id"), row.get("ts"), row.get("text"), "history", history, number)

    project_map = load_project_map(vault)
    timeline = []
    for candidate in _deduplicate(candidates):
        session = candidate["session"]
        local = candidate["local"]
        text = candidate["text"]
        cwd = metadata.get(session, {}).get("cwd", "")
        command = SKILL_CALL.search(text)
        timeline.append(Event(time=local.strftime("%H:%M"), ts=local.isoformat(),
                              origin="codex-local", session_id=session,
                              session_name=names.get(session, session[:12]),
                              project=Path(cwd).name if cwd else "", cwd=cwd,
                              content=clean_excerpt(text), domain=detect_domain(text, cwd, project_map),
                              kind="command" if command else "prompt",
                              command=command.group("name") if command else None))

    grouped = defaultdict(list)
    for event in timeline:
        grouped[event.session_id].append(event)
    sessions = [{"id": session, "name": rows[0].session_name, "project": rows[0].project,
                 "cwd": rows[0].cwd, "origin": "codex-local",
                 "time_range": f"{rows[0].time}-{rows[-1].time}", "messages": len(rows), "files": [],
                 "titled": session in names, "automated": False}
                for session, rows in grouped.items()]
    mit_items = parse_mit(vault, target_date) if vault else []
    health = host_health(sources, len(timeline), target_date)
    # A stopped legacy history alone cannot establish inactivity in the desktop app.
    if (health["status"] == "no_activity"
            and health["sources"]["history.jsonl"]["predates_requested_day"]
            and not any(sources[key].data["files_read"] for key in ("sessions", "archived_sessions"))):
        health["status"] = "stale"
    return Report(date=target_date.isoformat(), origin="codex-local", hosts=["codex"],
                  timeline=timeline, sessions=sessions, summary=make_summary(timeline),
                  source_health={"codex": health},
                  mit={"date": target_date.isoformat() if mit_items else None,
                       "items": mit_items, "matched": match_mit(timeline, mit_items)})
