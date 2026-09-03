#!/usr/bin/env python3
"""唯一活动分析入口，支持 Claude Code、Codex 或两者。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from activity.claude_collector import collect as collect_claude
from activity.codex_collector import collect as collect_codex
from activity.common import GMT8, merge_reports, parse_date_arg, render_json, render_text


def _host(explicit: str) -> str:
    if explicit != "auto":
        return explicit
    configured = os.environ.get("ASSISTANT_HOST", "").strip().lower()
    if configured in {"claude", "codex", "all"}:
        return configured
    return "claude" if "CLAUDECODE" in os.environ else "codex"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分析 Claude Code / Codex 本地活动")
    parser.add_argument("target_date", nargs="?", help="日期 YYYY-MM-DD，默认 GMT+8 今天")
    parser.add_argument("--host", choices=("auto", "claude", "codex", "all"), default="auto")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--claude-home", default=str(Path.home() / ".claude"))
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--vault", default=str(Path.cwd()))
    args = parser.parse_args(argv)
    try:
        target = parse_date_arg(args.target_date)
    except ValueError as exc:
        parser.error(str(exc))
    selected = _host(args.host)
    vault = Path(args.vault)
    reports = []
    if selected in {"claude", "all"}:
        reports.append(collect_claude(target, home=Path(args.claude_home), vault=vault))
    if selected in {"codex", "all"}:
        reports.append(collect_codex(target, home=Path(args.codex_home), vault=vault))
    report = merge_reports(reports) if len(reports) > 1 else reports[0]
    if args.json_only:
        print(render_json(report))
    else:
        print(render_text(report))
        print("=== ACTIVITY_DATA ===")
        print(render_json(report))
        print("=== END ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
