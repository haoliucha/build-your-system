"""Canonical paths used by the assistant plugin's script layer."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

INBOX_DIR = "00-Inbox"
CAPTURE_FILE = "00-Inbox/capture.md"
PROJECTS_DIR = "10-Projects"
AREAS_DIR = "20-Areas"
TOPICS_DIR = "20-Areas/media/topics"
IDEAS_DIR = "20-Areas/indie/ideas"
RESOURCES_DIR = "30-Resources"
CONVERSATIONS_DIR = "30-Resources/conversations"
CLIPPINGS_DIR = "Clippings"
ARCHIVES_DIR = "40-Archives"
GTD_DIR = "50-GTD"
ACTIVE_FILE = "50-GTD/active.md"
WAITING_FILE = "50-GTD/waiting.md"
SOMEDAY_FILE = "50-GTD/someday.md"
DONE_FILE = "50-GTD/done.md"
MEMORY_DIR = "60-Memory"
PROFILE_FILE = "60-Memory/profile.md"
NOW_FILE = "60-Memory/now.md"
PREFERENCES_FILE = "60-Memory/preferences.md"
PATTERNS_FILE = "60-Memory/patterns.md"
DIGEST_FILE = "60-Memory/patterns-digest.md"
TAG_MAPPING_FILE = "60-Memory/tag-mapping.md"
WEEKLY_DIR = "60-Memory/weekly-summary"
ARCHIVE_DIR = "60-Memory/archive"

REQUIRED_DIRS = [
    INBOX_DIR,
    PROJECTS_DIR,
    AREAS_DIR,
    RESOURCES_DIR,
    ARCHIVES_DIR,
    GTD_DIR,
    MEMORY_DIR,
]

STANDARD_FILES = [
    PROFILE_FILE,
    NOW_FILE,
    PREFERENCES_FILE,
    PATTERNS_FILE,
    DIGEST_FILE,
    TAG_MAPPING_FILE,
    ACTIVE_FILE,
    WAITING_FILE,
    SOMEDAY_FILE,
    DONE_FILE,
    CAPTURE_FILE,
]

DOMAIN_PATTERNS = [
    ("20-Areas/media/", "#media"),
    ("20-Areas/indie/", "#indie"),
    ("10-Projects/", "#indie"),
    ("50-GTD/", "#tasks"),
    ("60-Memory/", "#reflection"),
    ("outsourcing", "#outsourcing"),
]

MIT_HEADER_RE = re.compile(
    r"^## 今日重点 \(MIT\) - (?P<date>\d{4}-\d{2}-\d{2}|\d{2}-\d{2})\s*$",
    re.MULTILINE,
)


def resolve_short_date(value: str, reference: date) -> date:
    """Resolve an old MM-DD label to the nearest date not after reference."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    month, day = (int(part) for part in value.split("-"))
    candidate = date(reference.year, month, day)
    if candidate > reference:
        candidate = date(reference.year - 1, month, day)
    return candidate


def daily_note_candidates(value: date) -> list[str]:
    day = value.isoformat()
    return [f"{INBOX_DIR}/{day}.md", f"{INBOX_DIR}/{value.year}/{value.year}-{value.month:02d}/{day}.md"]
