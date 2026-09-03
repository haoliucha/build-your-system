"""Shared data model, date handling, MIT matching, and rendering."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .vault_paths import ACTIVE_FILE, DOMAIN_PATTERNS, MIT_HEADER_RE, resolve_short_date

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


@dataclass
class Report:
    date: str
    origin: str
    hosts: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[Event] = field(default_factory=list)
    mit: dict[str, Any] = field(default_factory=lambda: {"date": None, "items": [], "matched": []})


def clean_excerpt(text: str, limit: int = 100) -> str:
    line = " ".join(str(text).strip().split())
    return line if len(line) <= limit else f"{line[:limit - 1]}…"


def detect_domain(text: str, cwd_or_paths: str | Iterable[str] | None) -> str:
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
    haystack = "\n".join(values).replace("\\", "/").lower()
    for pattern, domain in DOMAIN_PATTERNS:
        if pattern.lower() in haystack:
            return domain
    return "#other"


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


def parse_mit(vault: Path, target: date) -> list[str]:
    """Return unchecked and checked MIT item text for the requested date."""
    _, block = _mit_block(vault, target)
    items: list[str] = []
    for line in block.splitlines():
        if re.match(r"^- \[[ xX]\]\s*", line.strip()):
            item = re.sub(r"^- \[[ xX]\]\s*", "", line.strip())
            item = re.sub(r"\s+#[\w\u4e00-\u9fff/-]+", " ", item).strip()
            if item:
                items.append(item)
    return items


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
    ordered = sorted(timeline, key=lambda event: (event.ts if isinstance(event.ts, str) else "", event.time))
    domains: dict[str, int] = {}
    commands: dict[str, int] = {}
    for event in ordered:
        domains[event.domain] = domains.get(event.domain, 0) + 1
        if event.command:
            commands[event.command] = commands.get(event.command, 0) + 1
    return {
        "message_count": len(ordered),
        "session_count": len({event.session_id for event in ordered}),
        "start_time": ordered[0].time if ordered else None,
        "end_time": ordered[-1].time if ordered else None,
        "domains": dict(sorted(domains.items())),
        "commands": dict(sorted(commands.items())),
    }


def merge_reports(reports: Iterable[Report]) -> Report:
    reports = list(reports)
    if not reports:
        return Report(date="", origin="mixed")
    timeline = sorted((event for report in reports for event in report.timeline), key=lambda event: (event.ts if isinstance(event.ts, str) else "", event.time))
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
        summary=make_summary(timeline),
        sessions=sessions,
        timeline=timeline,
        mit={"date": mit_date, "items": mit_items, "matched": mit_matched},
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
    if not summary.get("message_count"):
        lines.append("当天没有检测到活动。")
        return "\n".join(lines)
    lines.extend([
        f"活动时段：{summary.get('start_time')} - {summary.get('end_time')}",
        f"消息总数：{summary.get('message_count', 0)}",
        f"活跃会话：{summary.get('session_count', 0)}",
        "",
        "时间线：",
    ])
    for event in report.timeline:
        sidechain = " [sidechain]" if event.sidechain else ""
        command = f" | {event.command}" if event.command else ""
        lines.append(f"{event.time} | {event.session_name} | {event.domain}{command}{sidechain} | {event.content}")
    if summary.get("domains"):
        lines.extend(["", "领域分布："])
        lines.extend(f"- {domain}: {count}" for domain, count in summary["domains"].items())
    return "\n".join(lines)
