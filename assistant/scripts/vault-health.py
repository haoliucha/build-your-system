#!/usr/bin/env python3
"""Emit a non-blocking JSON health snapshot for a Vault."""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent))

from activity.common import GMT8
from activity.vault_paths import (
    ACTIVE_FILE,
    CAPTURE_FILE,
    DIGEST_FILE,
    DONE_FILE,
    NOW_FILE,
    PREFERENCES_FILE,
    PROFILE_FILE,
    REQUIRED_DIRS,
    STANDARD_FILES,
    WEEKLY_DIR,
    daily_note_candidates,
    resolve_short_date,
    MIT_HEADER_RE,
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _age(day: date | None, today: date) -> int | None:
    return (today - day).days if day else None


def _date_from_label(label: str, today: date) -> date | None:
    try:
        return resolve_short_date(label, today)
    except (ValueError, TypeError):
        return None


def _capture(vault: Path, today: date) -> tuple[int, date | None, date | None]:
    text = _read(vault / CAPTURE_FILE)
    dates = []
    for match in re.finditer(r"^### (\d{2}-\d{2}) (\d{2}:\d{2})\s*$", text, re.MULTILINE):
        parsed = _date_from_label(match.group(1), today)
        if parsed:
            dates.append(parsed)
    return len(dates), (min(dates) if dates else None), (max(dates) if dates else None)


def _mit(vault: Path, today: date) -> dict:
    text = _read(vault / ACTIVE_FILE)
    match = MIT_HEADER_RE.search(text)
    if not match:
        return {"header_date": None, "age_days": None, "open": 0, "done": 0, "has_suggestion": "## 明日重点（建议）" in text}
    parsed = _date_from_label(match.group("date"), today)
    tail = text[match.end():]
    boundary = re.search(r"\n(?:---\s*\n|## )", tail)
    block = tail[:boundary.start()] if boundary else tail
    return {
        "header_date": parsed.isoformat() if parsed else None,
        "age_days": _age(parsed, today),
        "open": len(re.findall(r"^- \[ \]", block, re.MULTILINE)),
        "done": len(re.findall(r"^- \[[xX]\]", block, re.MULTILINE)),
        "has_suggestion": "## 明日重点（建议）" in text,
    }


def _daily_notes(vault: Path, today: date) -> list[tuple[date, Path, str]]:
    inbox = vault / "00-Inbox"
    paths = {vault / candidate for candidate in daily_note_candidates(today)}
    if inbox.is_dir():
        paths.update(path for path in inbox.rglob("*.md") if re.search(r"(?:^|/)\d{4}-\d{2}-\d{2}\.md$", str(path)))
    found = []
    for path in paths:
        match = re.search(r"(\d{4}-\d{2}-\d{2})\.md$", str(path))
        if not match:
            continue
        try:
            parsed = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if parsed <= today:
            found.append((parsed, path, _read(path)))
    return sorted(found, key=lambda item: item[0])


def _review(vault: Path, today: date) -> dict:
    notes = [(day, path, text) for day, path, text in _daily_notes(vault, today) if "## 复盘" in text]
    last = notes[-1][0] if notes else None
    today_text = next((text for day, _, text in _daily_notes(vault, today) if day == today), "")
    return {"last_date": last.isoformat() if last else None, "age_days": _age(last, today), "auto_draft_today": "## 复盘（自动草稿" in today_text}


def _memory(vault: Path, today: date) -> dict:
    profile = _read(vault / PROFILE_FILE)
    now = _read(vault / NOW_FILE)
    updated = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})\s*$", now, re.MULTILINE)
    now_date = None
    if updated:
        try:
            now_date = date.fromisoformat(updated.group(1))
        except ValueError:
            pass
    digest = _read(vault / DIGEST_FILE)
    active = len(re.findall(r"^status:\s*active\s*$", digest, re.MULTILINE))
    ablation = None
    weekly = vault / WEEKLY_DIR
    weekly_files = sorted((path for path in weekly.glob("*") if path.is_file()), key=lambda path: path.name)
    if weekly_files:
        latest = weekly_files[-1]
        if "## 记忆消融记录" in _read(latest):
            match = re.search(r"(\d{4})-W(\d{2})", latest.stem)
            if match:
                ablation = date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1).isoformat()
            else:
                ablation = latest.stem
    profile_path = vault / PROFILE_FILE
    return {"profile_lines": len(profile.splitlines()) if profile_path.is_file() else None, "now_age_days": _age(now_date, today), "digest_active": active, "last_ablation": ablation}


def health(vault: Path, today: date | None = None) -> dict:
    today = today or datetime.now(tz=GMT8).date()
    count, oldest, latest_capture = _capture(vault, today)
    mit = _mit(vault, today)
    review = _review(vault, today)
    memory = _memory(vault, today)
    active_text = _read(vault / ACTIVE_FILE)
    open_tasks = len(re.findall(r"^- \[ \]", active_text, re.MULTILINE))
    overdue = 0
    for line in active_text.splitlines():
        if re.match(r"^- \[ \]", line):
            due = re.search(r"📅\s*(\d{4}-\d{2}-\d{2})", line)
            if due:
                try:
                    overdue += date.fromisoformat(due.group(1)) < today
                except ValueError:
                    pass
    missing = [relative for relative in STANDARD_FILES if not (vault / relative).is_file()]
    capture = {"last_date": latest_capture.isoformat() if latest_capture else None, "age_days": _age(latest_capture, today)}
    result = {
        "generated_at": datetime.now(tz=GMT8).isoformat(),
        "vault": str(vault),
        "inbox": {"undispatched": count, "oldest": oldest.isoformat() if oldest else None, "oldest_age_days": _age(oldest, today)},
        "mit": mit,
        "review": review,
        "capture": capture,
        "tasks": {"active_open": open_tasks, "overdue": overdue},
        "memory": memory,
        "files": {"missing": missing, "checked": len(STANDARD_FILES)},
        "nudges": [],
    }
    nudges = result["nudges"]
    if count >= 5:
        nudges.append(f"inbox {count} 条待分发")
    if _age(oldest, today) is not None and _age(oldest, today) >= 3:
        nudges.append(f"inbox 最老条目已 {result['inbox']['oldest_age_days']} 天")
    if not mit["header_date"] or mit["header_date"] not in {today.isoformat(), (today + timedelta(days=1)).isoformat()}:
        nudges.append(f"MIT 不是今天或明天（{mit['header_date'] or '缺失'}）")
    if review["age_days"] is not None and review["age_days"] >= 2:
        nudges.append(f"复盘已 {review['age_days']} 天未更新")
    if capture["age_days"] is not None and capture["age_days"] >= 3:
        nudges.append(f"capture 已 {capture['age_days']} 天未更新")
    if missing:
        nudges.append("缺少文件: " + ", ".join(missing))
    if memory["profile_lines"] is not None and memory["profile_lines"] > 40:
        nudges.append(f"profile 超过 40 行（{memory['profile_lines']}）")
    if memory["now_age_days"] is not None and memory["now_age_days"] > 14:
        nudges.append(f"now 已 {memory['now_age_days']} 天未更新")
    ablation_age = None
    if memory["last_ablation"]:
        try:
            ablation_age = _age(date.fromisoformat(memory["last_ablation"]), today)
        except ValueError:
            pass
    if (ablation_age is None or ablation_age > 10) and memory["digest_active"]:
        nudges.append("记忆消融记录缺失或已超过 10 天")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 Vault 健康状态")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--nudge", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = health(Path(args.vault).resolve())
        if args.nudge:
            if result["nudges"]:
                print(" | ".join(result["nudges"]))
        else:
            import json
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        # Health is advisory and must never break a host session.
        if not args.nudge:
            import json
            print(json.dumps({"generated_at": datetime.now(tz=GMT8).isoformat(), "vault": str(Path(args.vault).resolve()), "nudges": ["健康检查失败"], "files": {"missing": [], "checked": 0}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
