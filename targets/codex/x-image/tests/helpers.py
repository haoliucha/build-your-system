from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CLAUDE_X = REPO / "x"
CODEX_X_IMAGE = REPO / "targets" / "codex" / "x-image"
SHARED = CLAUDE_X / "shared" / "x-image"

REFERENCE_NAMES = (
    "intent-routing.md",
    "size-presets.md",
    "style-policy.md",
    "layout-patterns.md",
    "prompt-contract.md",
    "qa-checklist.md",
)
STYLE_NAMES = (
    "terminal-tech.md",
    "editorial-material.md",
    "data-editorial.md",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_optional(path: Path) -> str:
    if not path.is_file():
        return ""
    return read(path)


def read_json(path: Path) -> dict:
    return json.loads(read(path))


def read_json_optional(path: Path) -> dict:
    if not path.is_file():
        return {}
    return read_json(path)


def shared_reference_text() -> str:
    return "\n".join(
        read_optional(SHARED / "references" / name) for name in REFERENCE_NAMES
    )


def shared_style_text() -> str:
    return "\n".join(
        read_optional(SHARED / "styles" / name) for name in STYLE_NAMES
    )
