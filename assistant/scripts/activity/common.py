"""Shared data model, date handling, MIT matching, and rendering."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .vault_paths import (
    ACTIVE_FILE,
    DOMAIN_PATTERNS,
    DONE_FILE,
    MIT_HEADER_RE,
    PROJECT_DOMAINS,
    PROJECT_PATHS_RE,
    TAG_MAPPING_FILE,
    WORKTREE_RE,
    resolve_short_date,
)

GMT8 = timezone(timedelta(hours=8))


def parse_date_arg(value: str | None) -> date:
    if not value:
        return datetime.now(tz=GMT8).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式错误: {value}，应为 YYYY-MM-DD") from exc


def iter_jsonl(path: Path):
    if not path.is_file():
        return
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue


def to_local(ts: Any) -> datetime | None:
    """Convert epoch seconds/milliseconds or an ISO timestamp to GMT+8."""
    try:
        if isinstance(ts, (int, float)):
            number = float(ts)
            if abs(number) > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc).astimezone(GMT8)
        if isinstance(ts, str):
            raw = ts.strip()
            if not raw:
                return None
            if re.fullmatch(r"\d+(?:\.\d+)?", raw):
                return to_local(float(raw))
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(GMT8)
    except (ValueError, OSError, OverflowError):
        return None
    return None


def local_day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, datetime.min.time(), tzinfo=GMT8)
    return start, start + timedelta(days=1)


@dataclass
class Event:
    time: str
    ts: Any
    origin: str
    session_id: str
    session_name: str
    project: str
    cwd: str
    content: str
    kind: str = "prompt"
    command: str | None = None
    domain: str = "#other"
    sidechain: bool = False
    goal: str = ""


@dataclass
class Report:
    date: str
    origin: str
    hosts: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[Event] = field(default_factory=list)
    mit: dict[str, Any] = field(default_factory=lambda: {"date": None, "items": [], "matched": []})
    source_health: dict[str, Any] = field(default_factory=dict)
    goals: list[dict[str, Any]] = field(default_factory=list)
    flow: list[dict[str, Any]] = field(default_factory=list)
    unplanned: list[dict[str, Any]] = field(default_factory=list)
    goal_meta: dict[str, Any] = field(default_factory=dict)


def clean_excerpt(text: str, limit: int = 100) -> str:
    line = " ".join(str(text).strip().split())
    return line if len(line) <= limit else f"{line[:limit - 1]}…"


def detect_domain(
    text: str,
    cwd_or_paths: str | Iterable[str] | None,
    project_map: list[tuple[str, str, str]] | None = None,
) -> str:
    text = text or ""
    tags = re.findall(r"#[\w\u4e00-\u9fff/-]+", text)
    for tag in tags:
        if tag == "#outsourcing" or tag.startswith("#outsourcing/"):
            return "#outsourcing"
        if tag.startswith("#media"):
            return "#media"
        if tag.startswith("#indie"):
            return "#indie"
        if tag.startswith("#tasks"):
            return "#tasks"
        if tag.startswith("#reflection"):
            return "#reflection"
        if tag in {"#life", "#learning"}:
            return tag

    if isinstance(cwd_or_paths, str):
        values = [cwd_or_paths]
    else:
        values = list(cwd_or_paths or [])
    values = [value for value in values if value]
    # 顺序：工作目录所属项目 → Vault 目录（工作目录或改过的文件）→ 改过的文件所属项目。
    if values:
        mapped = project_for_path(values[0], project_map)
        if mapped:
            return mapped[0]
    haystack = "\n".join(values).replace("\\", "/").lower()
    for pattern, domain in DOMAIN_PATTERNS:
        if pattern.lower() in haystack:
            return domain
    for value in values[1:]:
        mapped = project_for_path(value, project_map)
        if mapped:
            return mapped[0]
    return "#other"


def repo_root(path: str) -> str:
    """Strip a Claude worktree suffix so worktrees group with their repository."""
    normalized = str(path or "").replace("\\", "/").rstrip("/")
    match = WORKTREE_RE.search(normalized)
    return normalized[:match.start()] if match else normalized


def worktree_name(path: str) -> str | None:
    match = WORKTREE_RE.search(str(path or "").replace("\\", "/"))
    return match.group("name") if match else None


def project_for_path(path: str, project_map: list[tuple[str, str, str]] | None = None) -> tuple[str, str] | None:
    """Return (domain, project label) when the path's repository matches a mapping fragment."""
    root = f"{repo_root(path).lower()}/"
    for fragment, domain, label in project_map if project_map is not None else PROJECT_DOMAINS:
        if f"/{fragment.strip('/').lower()}/" in root:
            return domain, label
    return None


def load_project_map(vault: Path | None) -> list[tuple[str, str, str]]:
    """Defaults plus `项目路径：片段=显示名、…` lines under `## #tag` blocks in tag-mapping.md."""
    custom: list[tuple[str, str, str]] = []
    try:
        content = (vault / TAG_MAPPING_FILE).read_text(encoding="utf-8") if vault else ""
    except (OSError, UnicodeError):
        content = ""
    for block in re.split(r"^## ", content, flags=re.MULTILINE)[1:]:
        tag = block.split(None, 1)[0] if block.strip() else ""
        if not tag.startswith("#"):
            continue
        for match in PROJECT_PATHS_RE.finditer(block):
            for item in re.split(r"[、,，;；]", match.group("items")):
                fragment, _, label = item.strip().partition("=")
                if fragment.strip():
                    custom.append((fragment.strip(), tag, label.strip() or fragment.strip()))
    overridden = {fragment.lower() for fragment, _, _ in custom}
    return custom + [entry for entry in PROJECT_DOMAINS if entry[0].lower() not in overridden]


def _mit_block(vault: Path, target: date) -> tuple[str | None, str]:
    path = vault / ACTIVE_FILE
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, ""
    for match in MIT_HEADER_RE.finditer(content):
        try:
            resolved = resolve_short_date(match.group("date"), target)
        except ValueError:
            continue
        if resolved != target:
            continue
        start = match.end()
        next_heading = re.search(r"\n(?:---\s*\n|## )", content[start:])
        end = start + next_heading.start() if next_heading else len(content)
        return resolved.isoformat(), content[start:end]
    return None, ""


TASK_LINE_RE = re.compile(r"^- \[(?P<mark>[ xX])\]\s*(?P<text>.*)$")
DONE_DATE_RE = re.compile(r"✅\s*(?P<date>\d{4}-\d{2}-\d{2})")
TASK_DECORATION_RE = re.compile(r"\s*(?:[✅📅⏳🛫]\s*\d{4}-\d{2}-\d{2}|[⏫🔼🔽⏬🔺])")


def _clean_task(text: str) -> str:
    text = re.sub(r"\s+#[\w\u4e00-\u9fff/-]+", " ", f" {text}")
    return " ".join(TASK_DECORATION_RE.sub(" ", text).split())


def _task_title(text: str) -> str:
    bold = re.search(r"\*\*(.+?)\*\*", text)
    title = bold.group(1) if bold else re.split(r"[:：]", text, maxsplit=1)[0]
    return " ".join(title.split())


def _task_blocks(lines: list[str]):
    """Yield (mark, line text, indented note lines) for top-level checkbox tasks."""
    current: list | None = None
    for line in lines:
        match = TASK_LINE_RE.match(line)
        if match:
            if current:
                yield current
            current = [match.group("mark"), match.group("text"), []]
        elif current and line.startswith((" ", "\t")) and line.strip():
            current[2].append(line.strip().lstrip("-* ").strip())
        elif current and line.strip():
            yield current
            current = None
    if current:
        yield current


def _mit_marker(target: date) -> re.Pattern:
    return re.compile(rf"(?:{target:%m-%d}|{target.isoformat()})\s*MIT")


def parse_mit_details(vault: Path, target: date) -> dict[str, Any]:
    """Read the day's MIT from active.md and, after archiving, from done.md.

    o-review / --auto move finished MIT into done.md; those entries carry a
    `MM-DD MIT` note (or the marker on the task line), which is how they are found.
    """
    details: list[dict[str, Any]] = []
    sources: list[str] = []
    completed: list[str] = []

    def add(mark: str, text: str, notes: list[str], source: str) -> None:
        title = _task_title(_clean_task(text))
        if not title:
            return
        status = "done" if mark.lower() == "x" else "open"
        for existing in details:
            if existing["title"] == title:
                existing["status"] = "done" if "done" in {existing["status"], status} else "open"
                existing["notes"] = existing["notes"] or " ".join(notes)
                if source not in existing["source"]:
                    existing["source"] += f"+{source}"
                return
        details.append({
            "title": title,
            "item": _clean_task(text),
            "status": status,
            "source": source,
            "notes": " ".join(notes),
        })
        if source not in sources:
            sources.append(source)

    _, block = _mit_block(vault, target)
    for mark, text, notes in _task_blocks(block.splitlines()):
        add(mark, text, notes, "active")

    marker = _mit_marker(target)
    try:
        done_lines = (vault / DONE_FILE).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        done_lines = []
    for mark, text, notes in _task_blocks(done_lines):
        done_date = DONE_DATE_RE.search(text)
        if mark.lower() != "x" or not done_date or done_date.group("date") != target.isoformat():
            continue
        completed.append(_task_title(_clean_task(text)))
        if marker.search(text) or any(marker.search(note) for note in notes):
            add(mark, text, notes, "done")
    return {"details": details, "source": sources, "completed": completed}


def parse_mit(vault: Path, target: date) -> list[str]:
    """Return the day's MIT item text, checked or not, including items archived to done.md."""
    return [detail["item"] for detail in parse_mit_details(vault, target)["details"]]


def match_mit(events: Iterable[Event], mit_items: list[str]) -> list[str]:
    """Return MIT items matched by event content/commands using old loose matching."""
    event_texts = [f"{event.content} {event.command or ''}".lower() for event in events]
    matched: list[str] = []
    for mit in mit_items:
        lower = mit.lower()
        if any(lower in text or text in lower for text in event_texts):
            matched.append(mit)
            continue
        mit_words = set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", lower))
        if any(mit_words & set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", text)) for text in event_texts):
            matched.append(mit)
    return matched


def make_summary(timeline: list[Event]) -> dict[str, Any]:
    ordered = sorted(timeline, key=lambda event: ((to_local(event.ts).isoformat() if to_local(event.ts) else ""), event.time))
    domains: dict[str, int] = {}
    commands: dict[str, int] = {}
    for event in ordered:
        domains[event.domain] = domains.get(event.domain, 0) + 1
        if event.command:
            commands[event.command] = commands.get(event.command, 0) + 1
    return {
        "message_count": len(ordered),
        "session_count": len({(event.origin, event.session_id) for event in ordered}),
        "start_time": ordered[0].time if ordered else None,
        "end_time": ordered[-1].time if ordered else None,
        "domains": dict(sorted(domains.items())),
        "commands": dict(sorted(commands.items())),
    }


def merge_reports(reports: Iterable[Report]) -> Report:
    reports = list(reports)
    if not reports:
        return Report(date="", origin="mixed")
    timeline = sorted((event for report in reports for event in report.timeline), key=lambda event: ((to_local(event.ts).isoformat() if to_local(event.ts) else ""), event.time))
    sessions = [session for report in reports for session in report.sessions]
    mit_items: list[str] = []
    mit_matched: list[str] = []
    mit_date = None
    for report in reports:
        mit_date = mit_date or report.mit.get("date")
        for item in report.mit.get("items", []):
            if item not in mit_items:
                mit_items.append(item)
        for item in report.mit.get("matched", []):
            if item not in mit_matched:
                mit_matched.append(item)
    hosts: list[str] = []
    for report in reports:
        for host in report.hosts:
            if host not in hosts:
                hosts.append(host)
    return Report(
        date=reports[0].date,
        origin="mixed",
        hosts=hosts,
        source_health={host: value for report in reports for host, value in report.source_health.items()},
        summary=make_summary(timeline),
        sessions=sessions,
        timeline=timeline,
        mit={**next((report.mit for report in reports if report.mit.get("items")), {}), "date": mit_date, "items": mit_items, "matched": mit_matched},
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def render_json(report: Report) -> str:
    return json.dumps(_jsonable(report), ensure_ascii=False, indent=2)


def render_text(report: Report) -> str:
    summary = report.summary
    lines = [f"=== 活动分析 {report.date} ({report.origin}) ==="]
    lines.append(f"宿主：{', '.join(report.hosts) if report.hosts else '无'}")
    for host, health in report.source_health.items():
        lines.append(f"数据源 {host}：{health['status']} | 消息 {health['message_count']}")
    if not summary.get("message_count"):
        incomplete = any(h["status"] in {"partial", "unavailable", "stale"} for h in report.source_health.values())
        lines.append("活动数据不完整，不能据此判断当天没有活动。" if incomplete else "当天没有检测到活动。")
        return "\n".join(lines)
    lines.extend([
        f"活动时段：{summary.get('start_time')} - {summary.get('end_time')}",
        f"消息总数：{summary.get('message_count', 0)}",
        f"活跃会话：{summary.get('session_count', 0)}",
        "",
        "时间线：",
    ])
    aux_ids = {session["id"] for session in report.sessions if session.get("aux")}
    for event in report.timeline:
        if event.session_id in aux_ids:
            continue
        sidechain = " [sidechain]" if event.sidechain else ""
        command = f" | {event.command}" if event.command else ""
        lines.append(f"{event.time} | [{event.origin}] {event.session_name} | {event.domain}{command}{sidechain} | {event.content}")
    if aux_ids:
        lines.append(f"（{len(aux_ids)} 个自动化子会话已归并到对应目标，不单列）")
    if summary.get("domains"):
        lines.extend(["", "领域分布："])
        lines.extend(f"- {domain}: {count}" for domain, count in summary["domains"].items())
    lines.extend(_render_goals(report))
    return "\n".join(lines)


CATEGORY_LABELS = {"mit": "MIT", "unplanned": "计划外", "routine": "日常"}


def _render_goals(report: Report) -> list[str]:
    if not report.goals:
        return []
    lines = ["", f"按目标分组（{report.goal_meta.get('duration_method', '时长为估算')}）："]
    for goal in report.goals:
        aux = f"，含 {goal['aux_sessions']} 个子会话" if goal.get("aux_sessions") else ""
        link = " / ".join(goal["mit_match"]) or CATEGORY_LABELS.get(goal["category"], goal["category"])
        lines.append(f"- {goal['goal']} | ~{goal['duration_min']} 分钟 | {goal['messages']} 条{aux} | {link}")
    lines.extend(["", "活动流水："])
    for row in report.flow:
        link = " / ".join(row["mit_match"]) or f"（{CATEGORY_LABELS.get(row['category'], row['category'])}）"
        lines.append(f"{row['time_range']} | {row['session']} | {row['messages']} 条 | ~{row['duration_min']} 分钟 | {row['goal']} | {link}")
    progress = report.mit.get("progress") or []
    if progress:
        completion = report.mit.get("completion", {})
        lines.extend(["", f"MIT vs 实际（完成率 {completion.get('rate')}，来源 {'+'.join(report.mit.get('source', []))}）："])
        for entry in progress:
            status = "✅" if entry["status"] == "done" else "⏸️"
            invested = f"~{entry['duration_min']} 分钟（{'、'.join(entry['goals'])}）" if entry["goals"] else "未见活动"
            shared = f"，与「{'、'.join(entry['shared_with'])}」共用会话" if entry.get("shared_with") else ""
            lines.append(f"- {status} {entry['item']} → {invested}{shared}")
    if report.unplanned:
        lines.extend(["", "计划外："])
        lines.extend(f"- {goal['goal']} | {goal['time_range']} | ~{goal['duration_min']} 分钟" for goal in report.unplanned)
    return lines
