from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
X = REPO / "x"
X_IMAGE = X / "skills" / "x-image"

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
    "tactile-systems.md",
    "isometric-systems.md",
)
STYLE_IDS = tuple(name.removesuffix(".md") for name in STYLE_NAMES)


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


def reference_text() -> str:
    return "\n".join(
        read_optional(X_IMAGE / "references" / name)
        for name in REFERENCE_NAMES
    )


def style_text() -> str:
    return "\n".join(
        read_optional(X_IMAGE / "styles" / name)
        for name in STYLE_NAMES
    )
