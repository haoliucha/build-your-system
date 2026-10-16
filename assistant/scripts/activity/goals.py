"""Goal segmentation, MIT linking and time estimates over a collected report.

会话先按「显式目标切换」切段（会话标题 → `目标：…` / `Do this task here: “…”` /
assistant 命令），每段是一条活动流水；自动化子会话（SDK 入口的安全审查等）不单独占行，
按工作目录归并到父会话当时所在的段。时长只按消息间隔估算，不代表产出。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .claude_collector import COMMAND_GOALS
from .common import Event, Report, clean_excerpt, repo_root, to_local, worktree_name

IDLE_GAP_MIN = 30
TAIL_MIN = 5
MATCH_THRESHOLD = 3.0
ROUTINE_GOALS = set(COMMAND_GOALS.values())
ROUTINE_COMMANDS = {command.rsplit(":", 1)[-1] for command in COMMAND_GOALS}
AUX_GOAL = "自动化辅助会话"
DURATION_METHOD = (
    f"估算：同一目标的相邻消息间隔 ≤{IDLE_GAP_MIN} 分钟连成一段，每段末尾加 {TAIL_MIN} 分钟；"
    "自动化子会话不计时；并行会话的时长可能重叠。消息数与时长都不等于产出。"
)

GOAL_SWITCH_PATTERNS = [
    re.compile(r"Do this task here[:：]\s*[“\"「](?P<goal>[^”\"」]{2,80})[”\"」]"),
    re.compile(r"(?:^|#+\s*)目标\s*[:：]\s*(?P<goal>.+?)(?=\s*(?:#|验收|要求|\*|[。；;]|$))"),
    re.compile(r"^(?:开始|聚焦)\s*[「“\"]?(?P<goal>[^「“\"」”\s]{2,40})"),
]
LATIN_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "you", "are", "not", "was", "have",
    "into", "your", "about", "will", "can", "all", "any", "other", "only", "these", "then",
    "than", "http", "https", "www", "com",
}
CJK_STOPWORDS = {
    "完成", "已完", "已经", "现在", "可以", "需要", "没有", "这个", "那个", "我们", "你们", "什么",
    "怎么", "如果", "然后", "进行", "继续", "问题", "一个", "一下", "是否", "是不", "不是", "所以",
    "因为", "但是", "还是", "的话", "以后", "之后", "之前", "时候", "一起", "所有", "相关", "本人",
}


def _local(event: Event) -> datetime | None:
    return to_local(event.ts)


def _sort_key(event: Event) -> tuple[str, str]:
    local = _local(event)
    return (local.isoformat() if local else "", event.time)


def _tokens(text: str) -> dict[str, float]:
    """Latin words / version numbers weigh 2, CJK bigrams weigh 1."""
    lower = str(text or "").lower()
    tokens: dict[str, float] = {}
    for word in re.findall(r"\d+(?:\.\d+)+|[a-z][a-z0-9_+-]{2,}", lower):
        if word not in LATIN_STOPWORDS:
            tokens[word] = 2.0
    for run in re.findall(r"[一-鿿]{2,}", lower):
        for index in range(len(run) - 1):
            bigram = run[index:index + 2]
            if bigram not in CJK_STOPWORDS:
                tokens.setdefault(bigram, 1.0)
    return tokens


def mit_score(mit: dict[str, Any], label: str, content: str = "") -> float:
    """Title tokens hit in the goal label count triple; notes only count half."""
    title_tokens = _tokens(mit.get("title", ""))
    note_tokens = _tokens(f"{mit.get('item', '')} {mit.get('notes', '')}")
    label_tokens = _tokens(label)
    content_tokens = _tokens(content)
    score = 0.0
    for token, weight in title_tokens.items():
        if token in label_tokens:
            score += 3 * weight
        elif token in content_tokens:
            score += weight
    for token, weight in note_tokens.items():
        if token not in title_tokens and (token in label_tokens or token in content_tokens):
            score += 0.5 * weight
    return score


def explicit_goal(event: Event) -> str | None:
    """Return the goal a message explicitly switches to, if any."""
    if event.command:
        if event.command in COMMAND_GOALS:
            return COMMAND_GOALS[event.command]
        if event.command.rsplit(":", 1)[-1] == "goal" and not event.content.startswith("/"):
            return clean_excerpt(event.content, 40)
        return None
    for pattern in GOAL_SWITCH_PATTERNS:
        match = pattern.search(event.content)
        if match:
            goal = match.group("goal").strip(" ：:，,")
            if len(goal) >= 2:
                return clean_excerpt(goal, 40)
    return None


def is_routine(goal: str) -> bool:
    """assistant 自身的日常命令（回顾、任务概览等）不算 MIT，也不算计划外。"""
    lower = re.sub(r"[\s_]+", "-", goal.lower())
    return goal in ROUTINE_GOALS or goal == AUX_GOAL or any(command in lower for command in ROUTINE_COMMANDS)


def estimate_minutes(events: list[Event]) -> int:
    times = sorted(local for local in (_local(event) for event in events) if local)
    if not times:
        return 0
    total = 0.0
    start = previous = times[0]
    for current in times[1:]:
        if (current - previous).total_seconds() / 60 > IDLE_GAP_MIN:
            total += (previous - start).total_seconds() / 60 + TAIL_MIN
            start = current
        previous = current
    total += (previous - start).total_seconds() / 60 + TAIL_MIN
    return int(round(total))


def _time_range(events: list[Event]) -> str:
    ordered = sorted(events, key=_sort_key)
    return f"{ordered[0].time}-{ordered[-1].time}" if ordered else ""


def _segments(session: dict[str, Any], events: list[Event]) -> list[dict[str, Any]]:
    """Split one human session into consecutive goal segments."""
    segments: list[dict[str, Any]] = []
    for event in sorted(events, key=_sort_key):
        switch = explicit_goal(event)
        if not segments:
            if session.get("titled"):
                goal = session["name"]
            else:
                goal = switch or clean_excerpt(event.content, 30)
            segments.append({"goal": goal, "explicit": False, "hint": switch or "", "events": [event]})
            continue
        if switch and switch != segments[-1]["goal"]:
            segments.append({"goal": switch, "explicit": True, "hint": switch, "events": [event]})
        else:
            segments[-1]["events"].append(event)
    return segments


def _parent_event(aux_events: list[Event], human_events: list[Event]) -> Event | None:
    """Nearest human message sharing the aux session's cwd, worktree, or repository."""
    if not aux_events or not human_events:
        return None
    anchor = aux_events[0]
    anchor_time = _local(anchor)
    keys = [
        lambda event: event.cwd == anchor.cwd,
        lambda event: worktree_name(anchor.cwd) is not None and worktree_name(event.cwd) == worktree_name(anchor.cwd),
        lambda event: repo_root(event.cwd) == repo_root(anchor.cwd),
    ]
    for key in keys:
        candidates = [event for event in human_events if anchor.cwd and key(event)]
        if candidates:
            if anchor_time is None:
                return candidates[0]
            return min(
                candidates,
                key=lambda event: abs(((_local(event) or anchor_time) - anchor_time).total_seconds()),
            )
    return None


def attach_goals(report: Report, mit: dict[str, Any] | None = None) -> Report:
    """Fill goals / flow / unplanned / goal_meta and extend mit and sessions in place."""
    mit = mit or {"details": [], "source": [], "completed": []}
    details = mit.get("details", [])
    by_session: dict[tuple[str, str], list[Event]] = {}
    for event in report.timeline:
        by_session.setdefault((event.origin, event.session_id), []).append(event)
    sessions = {(session.get("origin", ""), session["id"]): session for session in report.sessions}

    human_keys = [key for key in by_session if not sessions.get(key, {}).get("automated")]
    aux_keys = [key for key in by_session if sessions.get(key, {}).get("automated")]

    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    event_row: dict[int, dict[str, Any]] = {}
    for key in human_keys:
        session = sessions.get(key) or {"name": by_session[key][0].session_name, "titled": False}
        for index, segment in enumerate(_segments(session, by_session[key])):
            row_key = (key[0], session["name"], segment["goal"])
            row = rows.setdefault(row_key, {
                "origin": key[0],
                "session": session["name"],
                "goal": segment["goal"],
                "explicit": True,
                "label_parts": [],
                "events": [],
                "aux_events": [],
                "aux_sessions": set(),
                "session_ids": set(),
            })
            row["explicit"] = row["explicit"] and segment["explicit"]
            row["label_parts"].extend(part for part in (segment["goal"], segment["hint"]) if part)
            if index == 0:
                row["label_parts"].append(session["name"])
            row["events"].extend(segment["events"])
            row["session_ids"].add(key[1])
            for event in segment["events"]:
                event_row[id(event)] = row
                event.goal = segment["goal"]

    # 先到的自动化会话也可作为后到者的锚点：同一 worktree 名的审查跨仓库时归到同一段。
    anchors = [event for key in human_keys for event in by_session[key]]
    orphan: dict[str, Any] | None = None
    for key in sorted(aux_keys, key=lambda item: _sort_key(min(by_session[item], key=_sort_key))):
        aux_events = by_session[key]
        parent = _parent_event(aux_events, anchors)
        row = event_row.get(id(parent)) if parent else None
        if row is None:
            if orphan is None:
                orphan = rows.setdefault(("", AUX_GOAL, AUX_GOAL), {
                    "origin": key[0], "session": AUX_GOAL, "goal": AUX_GOAL, "explicit": True,
                    "label_parts": [], "events": [], "aux_events": [], "aux_sessions": set(),
                    "session_ids": set(),
                })
            row = orphan
        row["aux_events"].extend(aux_events)
        row["aux_sessions"].add(key[1])
        for event in aux_events:
            event.goal = row["goal"]
            event_row[id(event)] = row
        anchors.extend(aux_events)
        if key in sessions:
            sessions[key]["merged_into"] = {"session": row["session"], "goal": row["goal"]}

    for row in rows.values():
        label = " ".join(dict.fromkeys(row["label_parts"]))
        # 显式切换的段只按目标语句匹配，避免收尾消息里顺带提到的版本号把计划外工作算进 MIT。
        content = "" if row["explicit"] else " ".join(event.content for event in row["events"])
        routine = is_routine(row["goal"])
        row["mit_match"] = [] if routine else [
            detail["title"] for detail in details if mit_score(detail, label, content) >= MATCH_THRESHOLD
        ]
        row["category"] = "routine" if routine else ("mit" if row["mit_match"] else "unplanned")
        all_events = row["events"] + row["aux_events"]
        domains: dict[str, int] = {}
        for event in all_events:
            domains[event.domain] = domains.get(event.domain, 0) + 1
        row["domain"] = max(sorted(domains), key=domains.get) if domains else "#other"
        row["duration_min"] = estimate_minutes(row["events"])

    ordered_rows = sorted(rows.values(), key=lambda row: _sort_key(min(row["events"] or row["aux_events"], key=_sort_key)))
    report.flow = []
    for row in ordered_rows:
        events = sorted(row["events"], key=_sort_key)
        base = events or sorted(row["aux_events"], key=_sort_key)
        report.flow.append({
            "time": base[0].time,
            "time_range": _time_range(base),
            "session": row["session"],
            "origin": row["origin"],
            "messages": len(row["events"]),
            "duration_min": row["duration_min"],
            "summary": base[0].content if base else "",
            "samples": list(dict.fromkeys(event.content for event in events))[:3],
            "goal": row["goal"],
            "mit_match": row["mit_match"],
            "category": row["category"],
            "domain": row["domain"],
            "aux_sessions": len(row["aux_sessions"]),
            "aux_messages": len(row["aux_events"]),
        })

    goals: dict[str, dict[str, Any]] = {}
    for row in ordered_rows:
        goal = goals.setdefault(row["goal"], {
            "goal": row["goal"], "events": [], "aux": 0, "aux_messages": 0, "sessions": [],
            "mit_match": [], "categories": set(), "domains": {},
        })
        goal["events"].extend(row["events"])
        goal["aux"] += len(row["aux_sessions"])
        goal["aux_messages"] += len(row["aux_events"])
        if row["session"] not in goal["sessions"]:
            goal["sessions"].append(row["session"])
        goal["mit_match"].extend(item for item in row["mit_match"] if item not in goal["mit_match"])
        goal["categories"].add(row["category"])
        goal["domains"][row["domain"]] = goal["domains"].get(row["domain"], 0) + len(row["events"]) + len(row["aux_events"])
    report.goals = []
    for goal in goals.values():
        category = "mit" if goal["mit_match"] else ("routine" if goal["categories"] == {"routine"} else "unplanned")
        report.goals.append({
            "goal": goal["goal"],
            "category": category,
            "mit_match": goal["mit_match"],
            "duration_min": estimate_minutes(goal["events"]),
            "messages": len(goal["events"]),
            "time_range": _time_range(goal["events"]),
            "sessions": goal["sessions"],
            "domain": max(sorted(goal["domains"]), key=goal["domains"].get) if goal["domains"] else "#other",
            "aux_sessions": goal["aux"],
            "aux_messages": goal["aux_messages"],
        })
    report.goals.sort(key=lambda goal: -goal["duration_min"])
    report.unplanned = [
        {key: goal[key] for key in ("goal", "time_range", "duration_min", "messages", "sessions", "domain")}
        for goal in report.goals if goal["category"] == "unplanned"
    ]

    progress = []
    for detail in details:
        matched = [row for row in ordered_rows if detail["title"] in row["mit_match"]]
        events = [event for row in matched for event in row["events"]]
        progress.append({
            "item": detail["title"],
            "status": detail["status"],
            "goals": list(dict.fromkeys(row["goal"] for row in matched)),
            "sessions": list(dict.fromkeys(row["session"] for row in matched)),
            "duration_min": estimate_minutes(events),
            "messages": len(events),
            # 同一段同时对上多项 MIT 时，时长在这些 MIT 之间重复计算。
            "shared_with": list(dict.fromkeys(
                other for row in matched for other in row["mit_match"] if other != detail["title"]
            )),
        })
    done = sum(1 for detail in details if detail["status"] == "done")
    report.mit.update({
        "date": report.mit.get("date") or (report.date if details else None),
        "items": report.mit.get("items") or [detail["item"] for detail in details],
        "matched": [entry["item"] for entry in progress if entry["goals"]],
        "source": mit.get("source", []),
        "details": details,
        "completed": mit.get("completed", []),
        "progress": progress,
        "completion": {"done": done, "total": len(details), "rate": f"{done}/{len(details)}" if details else None},
    })

    for key, session in sessions.items():
        if session.get("automated"):
            session.update({"aux": True, "goal": session.get("merged_into", {}).get("goal", ""), "mit_match": [], "duration_min": 0})
            continue
        session_rows = [row for row in ordered_rows if key[1] in row["session_ids"] and row["origin"] == key[0]]
        session_events = by_session.get(key, [])
        own = {id(event) for event in session_events}
        session.update({
            "aux": False,
            "goal": session_rows[0]["goal"] if session_rows else "",
            "mit_match": list(dict.fromkeys(item for row in session_rows for item in row["mit_match"])),
            "duration_min": estimate_minutes(session_events),
            "segments": [
                {"goal": row["goal"], "time_range": _time_range([event for event in row["events"] if id(event) in own]),
                 "mit_match": row["mit_match"], "category": row["category"]}
                for row in session_rows
            ],
        })

    report.goal_meta = {
        "duration_method": DURATION_METHOD,
        "idle_gap_min": IDLE_GAP_MIN,
        "tail_min": TAIL_MIN,
        "aux_sessions_merged": len(aux_keys),
        "aux_messages_merged": sum(len(by_session[key]) for key in aux_keys),
    }
    return report
