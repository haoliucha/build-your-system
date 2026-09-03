#!/usr/bin/env python3
"""Render concise, deterministic context for a new assistant session."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from activity.common import GMT8
from activity.vault_paths import ACTIVE_FILE, DIGEST_FILE, NOW_FILE, PREFERENCES_FILE, PROFILE_FILE


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _without_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4:].lstrip("\n")
    return text


def _preferences(text: str) -> str:
    values: dict[str, str] = {}
    key_map = {
        "wake": "起床",
        "deep_work": "深度工作",
        "end_work": "收工",
        "bedtime": "上床",
        "language": "language",
        "penalty_per_day": "惩罚",
    }
    in_frontmatter = text.startswith("---")
    if in_frontmatter:
        match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        source = match.group(1) if match else ""
        for line in source.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() in key_map:
                values[key.strip()] = value.strip().strip('"\'')
    labels = {"起床时间": "wake", "深度工作": "deep_work", "结束工作": "end_work", "结束时间": "end_work", "上床时间": "bedtime", "language": "language", "语言": "language", "惩罚": "penalty_per_day"}
    for line in text.splitlines():
        match = re.match(r"^\s*-?\s*([^:：]+)[:：]\s*(.+?)\s*$", line)
        if match:
            key = labels.get(match.group(1).strip())
            if key and key not in values:
                values[key] = match.group(2).strip()
    return " | ".join(f"{key_map[key]}: {values[key]}" for key in key_map if key in values)


def _mit_section(text: str) -> list[str]:
    match = re.search(r"^## 今日重点(?: \(MIT\))?.*$", text, re.MULTILINE)
    if not match:
        return []
    tail = text[match.start():]
    boundary = re.search(r"\n(?:## |---\s*$)", tail, re.MULTILINE)
    section = tail[:boundary.start()] if boundary else tail
    return section.splitlines()[:10]


def _digest_titles(text: str) -> list[str]:
    chunks = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    candidates = []
    for chunk in chunks:
        if not re.search(r"^status:\s*active\s*$", chunk, re.MULTILINE):
            continue
        confirmed = re.search(r"^last_confirmed:\s*(\S+)", chunk, re.MULTILINE)
        title = re.search(r"^### .*$", chunk, re.MULTILINE)
        if title:
            candidates.append((confirmed.group(1) if confirmed else "", title.group(0)))
    return [title for _, title in sorted(candidates, key=lambda item: item[0], reverse=True)[:5]]


def _nudge(vault: Path) -> str:
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("vault-health.py")), "--vault", str(vault), "--nudge"], capture_output=True, text=True, check=False)
        return result.stdout.strip()
    except OSError:
        return ""


def render(vault: Path) -> str:
    lines: list[str] = []
    profile = _without_frontmatter(_read(vault / PROFILE_FILE)).strip()
    if profile:
        lines.extend(["## 用户画像", profile])
    now = _without_frontmatter(_read(vault / NOW_FILE)).strip()
    if now:
        lines.extend(["## 当前状态", now])
    preferences = _preferences(_read(vault / PREFERENCES_FILE))
    if preferences:
        lines.extend(["## 偏好", preferences])
    mit = _mit_section(_read(vault / ACTIVE_FILE))
    if mit:
        lines.extend(["## 今日重点", *mit])
    digest = _digest_titles(_read(vault / DIGEST_FILE))
    if digest:
        lines.extend(["## 精华模式", *digest])
    nudge = _nudge(vault)
    current = datetime.now(tz=GMT8).strftime("当前时间: %Y-%m-%d %H:%M 星期%w (GMT+8)")
    current = current.replace("星期0", "星期日").replace("星期1", "星期一").replace("星期2", "星期二").replace("星期3", "星期三").replace("星期4", "星期四").replace("星期5", "星期五").replace("星期6", "星期六")
    lines.append(f"{current} | {nudge}" if nudge else current)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="输出会话启动上下文")
    parser.add_argument("--vault", default=".")
    args = parser.parse_args(argv)
    try:
        print(render(Path(args.vault).resolve()))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
