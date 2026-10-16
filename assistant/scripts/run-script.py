#!/usr/bin/env python3
"""Run an Assistant helper with a validated root in the same process environment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPTS = ("analyze-activity.py", "vault-health.py", "session-context.py", "setup-entrypoints.py")


def valid_root(root: Path, script: str) -> bool:
    try:
        manifest = json.loads((root / ".codex-plugin/plugin.json").read_text())
        return manifest.get("name") == "assistant" and (root / "scripts" / script).is_file()
    except (OSError, ValueError, AttributeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", help="Explicit Assistant installation root")
    parser.add_argument("script", choices=SCRIPTS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    explicit = args.plugin_root or os.environ.get("ASSISTANT_PLUGIN_ROOT", "").strip()
    candidates = [Path(explicit).expanduser()] if explicit else [
        Path(__file__).resolve().parents[1], Path.home() / "plugins/assistant"]
    root = next((p.resolve() for p in candidates if valid_root(p, args.script)), None)
    if root is None:
        parser.error("Assistant 根目录无效或脚本缺失；已检查：" + ", ".join(map(str, candidates)))
    environment = dict(os.environ, ASSISTANT_PLUGIN_ROOT=str(root))
    os.execve(sys.executable, [sys.executable, str(root / "scripts" / args.script), *args.arguments], environment)


if __name__ == "__main__":
    main()
