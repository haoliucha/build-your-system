"""Read local sources without confusing missing/corrupt data with an empty day."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .common import to_local


class JsonlSource:
    def __init__(self, path: Path):
        self.data = {"path": str(path), "available": False, "files_read": 0,
                     "latest_record_at": None, "errors": []}

    def error(self, path: Path, detail: str):
        # Bound diagnostics; never include private message bodies.
        if len(self.data["errors"]) < 20:
            self.data["errors"].append(f"{path}: {detail}")

    def discover(self, root: Path, pattern: str) -> list[Path]:
        if not root.is_dir():
            return []
        result = []
        def failed(exc):
            self.error(root, str(exc))
        for directory, _, names in os.walk(root, onerror=failed):
            self.data["available"] = True
            result.extend(Path(directory) / name for name in names if Path(name).match(pattern))
        return sorted(result)

    def read(self, path: Path):
        try:
            with path.open(encoding="utf-8") as handle:
                self.data["available"] = True
                self.data["files_read"] += 1
                for number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("expected JSON object")
                    except (ValueError, TypeError):
                        self.error(path, f"invalid JSON object at line {number}")
                        continue
                    stamp = to_local(row.get("timestamp", row.get("ts")))
                    if stamp:
                        previous = to_local(self.data["latest_record_at"])
                        if previous is None or stamp > previous:
                            self.data["latest_record_at"] = stamp.isoformat()
                    yield row
        except FileNotFoundError:
            # A discovered file disappearing during the scan is incomplete data.
            if self.data["available"]:
                self.error(path, "FileNotFoundError during scan")
            return
        except (OSError, UnicodeError) as exc:
            self.error(path, type(exc).__name__)


def host_health(sources: dict[str, JsonlSource], count: int, target: date) -> dict:
    values = {key: source.data.copy() for key, source in sources.items()}
    available = any(value["available"] for value in values.values())
    errors = any(value["errors"] for value in values.values())
    status = "partial" if errors and available else "unavailable" if not available else "ok" if count else "no_activity"
    for value in values.values():
        latest = to_local(value["latest_record_at"])
        value["predates_requested_day"] = latest.date() < target if latest else None
    return {"status": status, "message_count": count, "sources": values}
