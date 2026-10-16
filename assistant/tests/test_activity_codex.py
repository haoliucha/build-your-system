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


class RolloutCollectorTests(unittest.TestCase):
    target = date(2026, 9, 8)

    def rollout(self, home, session, messages, archived=False, filename=None):
        directory = 'archived_sessions' if archived else 'sessions/2026/08/01'
        path = home / directory / (filename or f'rollout-{session}.jsonl')
        write_jsonl(path, [{'type': 'session_meta', 'payload': {'id': session, 'cwd': '/tmp/vault'}}] + messages)
        return path

    def prompt(self, text, ts='2026-09-08T01:00:00Z', identity=None):
        payload = {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}
        if identity:
            payload['id'] = identity
        return {'type': 'response_item', 'timestamp': ts, 'payload': payload}

    def event(self, text, ts='2026-09-08T01:00:00.2Z'):
        return {'type': 'event_msg', 'timestamp': ts, 'payload': {'type': 'user_message', 'message': text}}

    def test_rollout_without_history_and_old_session_crosses_midnight(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.rollout(home, 'a', [self.prompt('yesterday', '2026-09-07T15:59:59Z'),
                                     self.prompt('today', '2026-09-07T16:00:00Z'),
                                     self.prompt('tomorrow', '2026-09-08T16:00:00Z')])
            report = collect(self.target, home=home)
            self.assertEqual([e.content for e in report.timeline], ['today'])
            self.assertEqual(report.timeline[0].time, '00:00')
            self.assertEqual(report.source_health['codex']['status'], 'ok')
            self.assertFalse(report.source_health['codex']['sources']['history.jsonl']['available'])

    def test_stale_history_does_not_hide_archived_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.rollout(home, 'a', [self.prompt('archived')], archived=True)
            write_jsonl(home / 'history.jsonl', [{'session_id': 'old', 'ts': 1700000000, 'text': 'old'}])
            report = collect(self.target, home=home)
            self.assertEqual(report.summary['message_count'], 1)
            self.assertTrue(report.source_health['codex']['sources']['history.jsonl']['predates_requested_day'])
            self.assertEqual(report.source_health['codex']['status'], 'ok')

    def test_pairs_representations_and_preserves_repeated_and_independent_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rows = [self.prompt('continue', identity='one'), self.event('continue'),
                    self.prompt('continue', '2026-09-08T01:00:01Z', 'two'),
                    self.event('continue', '2026-09-08T01:00:01.2Z')]
            self.rollout(home, 'a', rows)
            self.rollout(home, 'a', rows, archived=True)
            self.rollout(home, 'b', [self.prompt('continue')])
            epoch = int(datetime(2026, 9, 8, 1, tzinfo=timezone.utc).timestamp())
            write_jsonl(home / 'history.jsonl', [{'session_id': 'a', 'ts': epoch, 'text': 'continue'},
                                                {'session_id': 'a', 'ts': epoch+1, 'text': 'continue'}])
            report = collect(self.target, home=home)
            self.assertEqual(report.summary['message_count'], 3)
            self.assertEqual(report.summary['session_count'], 2)

    def test_filters_injected_documents_but_preserves_skill_invocation_and_following_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            texts = ['<recommended_plugins>host list</recommended_plugins>\n# AGENTS.md instructions for /tmp/vault\npolicy',
                     '<environment_context>cwd</environment_context>', '<skill>full instructions</skill>',
                     '# AGENTS.md instructions for /tmp/vault\npolicy',
                     '[$assistant:a-setup](/installed/skills/a-setup/SKILL.md)',
                     '<recommended_plugins>host list</recommended_plugins>\nkeep my request',
                     'I want to discuss environment_context parsing']
            self.rollout(home, 'a', [self.prompt(t) for t in texts])
            report = collect(self.target, home=home)
            self.assertEqual(report.summary['message_count'], 3)
            self.assertEqual(report.timeline[0].command, 'assistant:a-setup')
            self.assertEqual(report.timeline[1].content, 'keep my request')

    def test_event_only_and_history_only_remain_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.rollout(home, 'a', [self.event('event only')])
            epoch = int(datetime(2026, 9, 8, 3, tzinfo=timezone.utc).timestamp())
            write_jsonl(home / 'history.jsonl', [{'session_id': 'b', 'ts': epoch, 'text': 'history only'}])
            self.assertEqual(collect(self.target, home=home).summary['message_count'], 2)

    def test_missing_empty_and_malformed_sources_have_different_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            report = collect(self.target, home=home)
            self.assertEqual(report.source_health['codex']['status'], 'unavailable')
            (home / 'sessions').mkdir()
            report = collect(self.target, home=home)
            self.assertEqual(report.source_health['codex']['status'], 'no_activity')
            path = self.rollout(home, 'a', [self.prompt('valid')])
            with path.open('a') as handle:
                handle.write('not json\n[]\n')
            report = collect(self.target, home=home)
            self.assertEqual(report.summary['message_count'], 1)
            self.assertEqual(report.source_health['codex']['status'], 'partial')
            self.assertEqual(len(report.source_health['codex']['sources']['sessions']['errors']), 2)

    def test_read_failure_is_reported(self):
        from unittest.mock import patch
        from activity.source_health import JsonlSource, host_health
        with tempfile.TemporaryDirectory() as tmp:
            source = JsonlSource(Path(tmp) / 'history.jsonl')
            with patch.object(Path, 'open', side_effect=PermissionError):
                self.assertEqual(list(source.read(Path(tmp) / 'history.jsonl')), [])
            health = host_health({'history': source}, 0, self.target)
            self.assertEqual(health['status'], 'unavailable')
            self.assertIn('PermissionError', health['sources']['history']['errors'][0])

    def test_merge_sorts_actual_time_across_timezones_and_keeps_both_host_health(self):
        from activity.common import merge_reports, Report, Event, render_text
        def event(origin, ts):
            return Event('09:00', ts, origin, 'same-id', 'name', '', '', 'message')
        claude = Report('2026-09-08', 'claude-local', hosts=['claude'],
                        timeline=[event('claude-local', '2026-09-08T02:00:00Z')],
                        source_health={'claude': {'status': 'ok', 'message_count': 1}})
        codex = Report('2026-09-08', 'codex-local', hosts=['codex'],
                       timeline=[event('codex-local', '2026-09-08T09:00:00+08:00')],
                       source_health={'codex': {'status': 'ok', 'message_count': 1}})
        result = merge_reports([claude, codex])
        self.assertEqual(result.timeline[0].origin, 'codex-local')
        self.assertEqual(result.summary['session_count'], 2)
        self.assertEqual(set(result.source_health), {'claude', 'codex'})
        self.assertIn('[codex-local]', render_text(result))
        unavailable = Report('2026-09-08', 'codex-local', source_health={'codex': {'status': 'unavailable', 'message_count': 0}})
        self.assertIn('不能据此判断', render_text(unavailable))


    def test_repeated_prompts_with_identical_timestamp_survive_archive_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rows = [self.prompt('again'), self.prompt('again')]
            self.rollout(home, 'a', rows)
            self.rollout(home, 'a', rows, archived=True)
            self.assertEqual(collect(self.target, home=home).summary['message_count'], 2)


    def test_stale_history_alone_cannot_establish_no_activity(self):
        from activity.common import render_text
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            write_jsonl(home / 'history.jsonl', [{'session_id': 'old', 'ts': 1700000000, 'text': 'old'}])
            report = collect(self.target, home=home)
            self.assertEqual(report.source_health['codex']['status'], 'stale')
            self.assertIn('不能据此判断', render_text(report))


if __name__ == '__main__':
    unittest.main()
