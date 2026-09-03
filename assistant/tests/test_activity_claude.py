import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from activity.claude_collector import collect
from activity.common import merge_reports


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class ClaudeCollectorTests(unittest.TestCase):
    def test_collects_namespace_command_sidechain_and_custom_title(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "claude"
            session = home / "projects/-tmp-vault/session-1.jsonl"
            write_jsonl(session, [
                {"type": "custom-title", "customTitle": "命名会话"},
                {"type": "user", "sessionId": "session-1", "slug": "slug-name", "cwd": "/tmp/vault", "timestamp": "2026-04-08T15:30:00Z", "message": {"content": "<command-name>/assistant:o-review</command-name>"}},
                {"type": "user", "sessionId": "session-1", "cwd": "/tmp/vault", "timestamp": "2026-04-08T16:30:00Z", "message": {"content": "次日消息，应排除"}},
                {"type": "user", "sessionId": "session-1", "cwd": "/tmp/vault", "isMeta": True, "timestamp": "2026-04-08T15:40:00Z", "message": {"content": "元消息，应排除"}},
                {"type": "user", "sessionId": "session-1", "cwd": "/tmp/vault", "isSidechain": True, "timestamp": "2026-04-08T15:45:00Z", "message": {"content": [{"type": "text", "text": "旁支仍保留 #indie"}]}},
            ])
            report = collect(date(2026, 4, 8), home=home, vault=home)
            self.assertEqual(report.origin, "claude-local")
            self.assertEqual(report.summary["message_count"], 2)
            self.assertEqual(report.timeline[0].command, "assistant:o-review")
            self.assertEqual(report.timeline[0].kind, "command")
            self.assertEqual(report.timeline[0].project, "vault")
            self.assertTrue(report.timeline[1].sidechain)
            self.assertEqual(report.sessions[0]["name"], "命名会话")
            self.assertEqual(merge_reports([report, report]).origin, "mixed")


if __name__ == "__main__":
    unittest.main()
