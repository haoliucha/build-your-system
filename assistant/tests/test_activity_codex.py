import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from activity.codex_collector import collect


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class CodexCollectorTests(unittest.TestCase):
    def test_collect_filters_date_and_enriches_session_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = date(2026, 4, 8)
            same = int(datetime(2026, 4, 8, 1, 5, tzinfo=timezone.utc).timestamp())
            write_jsonl(home / "history.jsonl", [
                {"session_id": "sess-1", "ts": same, "text": "整理今天选题 #media"},
                {"session_id": "sess-1", "ts": same + 1800, "text": "继续梳理发布时间线"},
                {"session_id": "sess-2", "ts": same - 3600 * 10, "text": "昨天不应统计"},
            ])
            write_jsonl(home / "session_index.jsonl", [{"id": "sess-1", "thread_name": "热点追踪工作流"}])
            write_jsonl(home / "sessions/2026/04/08/rollout-sess-1.jsonl", [{
                "type": "session_meta", "payload": {"id": "sess-1", "cwd": "/Users/jliu/Projects/vault"}
            }])
            report = collect(target, home=home, vault=home)
            self.assertEqual(report.origin, "codex-local")
            self.assertEqual(report.summary["message_count"], 2)
            self.assertEqual(report.summary["start_time"], "09:05")
            self.assertEqual(report.summary["end_time"], "09:35")
            self.assertEqual(report.timeline[0].session_name, "热点追踪工作流")
            self.assertEqual(report.timeline[0].domain, "#media")


if __name__ == "__main__":
    unittest.main()
