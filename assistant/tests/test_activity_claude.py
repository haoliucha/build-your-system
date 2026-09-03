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

    def test_filters_injected_records_deduplicates_and_counts_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "claude"
            first = home / "projects/project-a/session-1.jsonl"
            second = home / "projects/project-b/session-2.jsonl"
            common = {"sessionId": "session-1", "cwd": "/tmp/vault"}
            write_jsonl(first, [
                {"type": "custom-title", "title": "标题会话"},
                {**common, "type": "user", "uuid": "prompt-1", "timestamp": "2026-04-08T07:00:00Z", "message": {"content": "真实用户输入 #tasks"}},
                {**common, "type": "user", "uuid": "task-1", "timestamp": "2026-04-08T07:01:00Z", "message": {"content": "<task-notification><task-id>1</task-id></task-notification>"}},
                {**common, "type": "user", "uuid": "compact-1", "isCompactSummary": True, "timestamp": "2026-04-08T07:02:00Z", "message": {"content": "压缩摘要"}},
                {**common, "type": "user", "uuid": "continued-1", "timestamp": "2026-04-08T07:03:00Z", "message": {"content": "This session is being continued from a previous conversation\n摘要内容"}},
                {**common, "type": "user", "uuid": "reminder-1", "timestamp": "2026-04-08T07:03:30Z", "message": {"content": "<system-reminder>提示</system-reminder>"}},
                {**common, "type": "user", "uuid": "stdout-1", "timestamp": "2026-04-08T07:03:40Z", "message": {"content": "<local-command-stdout>输出</local-command-stdout>"}},
                {**common, "type": "user", "uuid": "caveat-1", "timestamp": "2026-04-08T07:03:50Z", "message": {"content": "<local-command-caveat>说明</local-command-caveat>"}},
                {**common, "type": "user", "uuid": "message-only-1", "timestamp": "2026-04-08T07:03:55Z", "message": {"content": "<command-message>仅消息</command-message>"}},
                {**common, "type": "user", "uuid": "command-1", "timestamp": "2026-04-08T07:04:00Z", "message": {"content": "<command-name>/assistant:a-setup</command-name><command-message>a-setup</command-message><command-args>x</command-args>"}},
                {**common, "type": "user", "uuid": "side-unique", "isSidechain": True, "timestamp": "2026-04-08T07:05:00Z", "message": {"content": "旁支独有消息"}},
                {**common, "type": "user", "timestamp": "2026-04-08T07:06:00Z", "message": {"content": "无 uuid 的消息"}},
            ])
            write_jsonl(second, [
                {**common, "type": "user", "uuid": "prompt-1", "timestamp": "2026-04-08T07:00:00Z", "isSidechain": True, "message": {"content": "真实用户输入 #tasks"}},
                {**common, "type": "user", "uuid": "side-duplicate", "timestamp": "2026-04-08T07:00:00Z", "isSidechain": True, "message": {"content": "真实用户输入 #tasks"}},
                {**common, "type": "user", "uuid": "command-1", "timestamp": "2026-04-08T07:04:00Z", "message": {"content": "<command-name>/assistant:a-setup</command-name><command-message>a-setup</command-message><command-args>x</command-args>"}},
                {**common, "type": "user", "timestamp": "2026-04-08T07:06:00Z", "isSidechain": True, "message": {"content": "无 uuid 的消息"}},
            ])

            report = collect(date(2026, 4, 8), home=home, vault=home)

            self.assertEqual(report.summary["message_count"], 4)
            self.assertEqual(report.summary["commands"], {"assistant:a-setup": 1})
            self.assertEqual([event.command for event in report.timeline if event.kind == "command"], ["assistant:a-setup"])
            self.assertEqual(next(event.content for event in report.timeline if event.kind == "command"), "x")
            self.assertEqual(report.sessions[0]["name"], "标题会话")
            self.assertFalse(any("task-notification" in event.content for event in report.timeline))
            self.assertFalse(any(event.content == "真实用户输入 #tasks" and event.sidechain for event in report.timeline))


if __name__ == "__main__":
    unittest.main()
