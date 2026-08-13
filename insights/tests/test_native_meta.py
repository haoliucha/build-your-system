"""RED tests for Claude ``/insights``-compatible deterministic Codex metrics.

These tests intentionally describe the next public, pure-function boundary of
the helper.  Transcript rows are synthetic but mirror the JSONL shapes emitted
by Codex (``session_meta``, ``response_item`` and ``event_msg``).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "insights" / "scripts" / "insights.py"
NATIVE_META_PATH = ROOT / "skills" / "insights" / "scripts" / "native_meta.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_native_meta_kernel", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_native_meta():
    spec = importlib.util.spec_from_file_location("insights_native_meta_pure", NATIVE_META_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _row(timestamp: str, row_type: str, payload: dict) -> dict:
    return {"timestamp": timestamp, "type": row_type, "payload": payload}


def realistic_codex_rows() -> list[dict]:
    patch = """*** Begin Patch
*** Update File: src/app.py
@@
-old_value = 1
+new_value = 2
+enabled = True
*** Add File: web/panel.tsx
+export const Panel = () => null;
*** End Patch"""
    return [
        _row(
            "2026-08-12T10:00:00Z",
            "session_meta",
            {
                "id": "raw-session-a",
                "timestamp": "2026-08-12T10:00:00Z",
                "cwd": "/Users/alice/Projects/widget",
                "source": "cli",
            },
        ),
        _row(
            "2026-08-12T10:00:05Z",
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Fix src/app.py and add the panel."}],
            },
        ),
        _row(
            "2026-08-12T10:00:10Z",
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I will inspect and patch it."}],
            },
        ),
        _row(
            "2026-08-12T10:00:11Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-commit",
                "arguments": json.dumps({"cmd": "git commit -am 'fix widget'"}),
            },
        ),
        _row(
            "2026-08-12T10:00:12Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "call-commit",
                "output": json.dumps({"exit_code": 0, "output": "[main abc1234] fix widget"}),
            },
        ),
        _row(
            "2026-08-12T10:00:20Z",
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": "call-patch",
                "input": patch,
            },
        ),
        _row(
            "2026-08-12T10:00:21Z",
            "event_msg",
            {
                "type": "patch_apply_end",
                "call_id": "call-patch",
                "status": "completed",
                "changes": {
                    "src/app.py": {"type": "update"},
                    "web/panel.tsx": {"type": "add"},
                },
            },
        ),
        _row(
            "2026-08-12T10:00:30Z",
            "response_item",
            {
                "type": "function_call",
                "name": "mcp__github__search_code",
                "call_id": "call-mcp",
                "arguments": "{}",
            },
        ),
        _row(
            "2026-08-12T10:00:31Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "call-mcp",
                "is_error": True,
                "output": "File not found while searching repository",
            },
        ),
        _row(
            "2026-08-12T10:00:40Z",
            "response_item",
            {
                "type": "function_call",
                "name": "spawn_agent",
                "call_id": "call-agent",
                "arguments": json.dumps({"task_name": "review"}),
            },
        ),
        _row(
            "2026-08-12T10:00:41Z",
            "response_item",
            {"type": "function_call_output", "call_id": "call-agent", "output": "started"},
        ),
        _row(
            "2026-08-12T10:01:00Z",
            "response_item",
            {
                "type": "function_call",
                "name": "web_search",
                "call_id": "call-search",
                "arguments": json.dumps({"query": "widget API"}),
            },
        ),
        _row(
            "2026-08-12T10:01:01Z",
            "response_item",
            {"type": "function_call_output", "call_id": "call-search", "output": "results"},
        ),
        _row(
            "2026-08-12T10:01:10Z",
            "response_item",
            {
                "type": "function_call",
                "name": "web_fetch",
                "call_id": "call-fetch",
                "arguments": json.dumps({"url": "https://example.invalid/docs"}),
            },
        ),
        _row(
            "2026-08-12T10:01:11Z",
            "response_item",
            {"type": "function_call_output", "call_id": "call-fetch", "output": "page"},
        ),
        _row(
            "2026-08-12T10:01:20Z",
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "The first version is ready."}],
            },
        ),
        _row(
            "2026-08-12T10:02:00Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-failed",
                "arguments": json.dumps({"cmd": "python -m pytest"}),
            },
        ),
        _row(
            "2026-08-12T10:02:01Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "call-failed",
                "is_error": True,
                "output": json.dumps({"exit_code": 1, "output": "Command failed: one test failed"}),
            },
        ),
        _row(
            "2026-08-12T10:03:00Z",
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Actually keep the old API name."}],
            },
        ),
        _row("2026-08-12T10:03:10Z", "event_msg", {"type": "turn_aborted", "reason": "user_interrupt"}),
        _row(
            "2026-08-12T10:04:00Z",
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I restored the old API name."}],
            },
        ),
        _row(
            "2026-08-12T10:05:00Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-push",
                "arguments": json.dumps({"cmd": "git push origin main"}),
            },
        ),
        _row(
            "2026-08-12T10:05:01Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "call-push",
                "output": json.dumps({"exit_code": 0, "output": "main -> main"}),
            },
        ),
        _row(
            "2026-08-12T10:05:30Z",
            "event_msg",
            {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 400,
                        "output_tokens": 200,
                        "reasoning_output_tokens": 50,
                        "total_tokens": 1200,
                    }
                },
            },
        ),
        _row(
            "2026-08-12T10:06:00Z",
            "event_msg",
            {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 1500,
                        "cached_input_tokens": 600,
                        "output_tokens": 350,
                        "reasoning_output_tokens": 80,
                        "total_tokens": 1850,
                    }
                },
            },
        ),
        _row(
            "2026-08-12T10:07:00Z",
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Done and verified."}],
            },
        ),
    ]


class NativeDeterministicMetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.native_meta = load_native_meta()

    def test_extracts_claude_compatible_metrics_from_codex_rows(self):
        meta = self.m.extract_native_session_meta(
            realistic_codex_rows(), transcript_mtime=1_723_456_789.0, origin="active"
        )

        self.assertEqual(meta["session_id"], "raw-session-a")
        self.assertEqual(meta["transcript_mtime"], 1_723_456_789.0)
        self.assertEqual(meta["project_path"], "/Users/alice/Projects/widget")
        self.assertEqual(meta["start_time"], "2026-08-12T10:00:00Z")
        self.assertEqual(meta["duration_minutes"], 7)
        self.assertEqual(meta["user_message_count"], 2)
        self.assertEqual(meta["assistant_message_count"], 4)
        self.assertEqual(meta["first_prompt"], "Fix src/app.py and add the panel.")

        # Count calls by tool name; paired outputs and patch completion events
        # must not be counted as additional calls.
        self.assertEqual(
            meta["tool_counts"],
            {
                "apply_patch": 1,
                "exec_command": 3,
                "mcp__github__search_code": 1,
                "spawn_agent": 1,
                "web_fetch": 1,
                "web_search": 1,
            },
        )
        self.assertEqual(meta["input_tokens"], 1500)
        self.assertEqual(meta["output_tokens"], 350)
        self.assertEqual(meta["languages"], {"Python": 1, "TypeScript": 1})
        self.assertEqual(meta["git_commits"], 1)
        self.assertEqual(meta["git_pushes"], 1)
        self.assertEqual(meta["lines_added"], 3)
        self.assertEqual(meta["lines_removed"], 1)
        self.assertEqual(meta["files_modified"], 2)

        self.assertEqual(meta["user_interruptions"], 1)
        self.assertEqual(meta["user_response_times"], [100.0])
        self.assertEqual(meta["tool_errors"], 2)
        self.assertEqual(meta["tool_error_categories"], {"Command Failed": 1, "File Not Found": 1})
        self.assertTrue(meta["uses_task_agent"])
        self.assertTrue(meta["uses_mcp"])
        self.assertTrue(meta["uses_web_search"])
        self.assertTrue(meta["uses_web_fetch"])
        local_hour = datetime.fromisoformat("2026-08-12T10:00:05+00:00").astimezone().hour
        self.assertEqual(meta["message_hours"], {local_hour: 2})
        self.assertEqual(
            meta["user_message_timestamps"],
            ["2026-08-12T10:00:05Z", "2026-08-12T10:03:00Z"],
        )

    def test_source_fingerprint_changes_for_tool_or_token_only_edits(self):
        baseline = realistic_codex_rows()
        tool_changed = copy.deepcopy(baseline)
        tool_changed[3]["payload"]["arguments"] = json.dumps({"cmd": "git commit -am 'different'"})
        token_changed = copy.deepcopy(baseline)
        token_changed[-2]["payload"]["info"]["total_token_usage"]["output_tokens"] = 351

        baseline_hash = self.m.compute_source_fingerprint(baseline)
        self.assertNotEqual(baseline_hash, self.m.compute_source_fingerprint(tool_changed))
        self.assertNotEqual(baseline_hash, self.m.compute_source_fingerprint(token_changed))

    def test_native_error_phrases_and_cpp_extensions_are_classified(self):
        cases = {
            "process exited with exit code 1": "Command Failed",
            "the user doesn't want to proceed": "User Rejected",
            "string to replace not found": "Edit Failed",
            "no changes were made": "Edit Failed",
            "file modified since read": "File Changed",
            "content exceeds maximum size": "File Too Large",
            "target does not exist": "File Not Found",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(self.native_meta._error_category(message, "unknown"), expected)
        for suffix in (".hh", ".hxx", ".ipp"):
            self.assertEqual(self.native_meta._LANGUAGES[suffix], "C++")

    def test_exec_wrapper_counts_nested_codex_tools_and_usage_flags(self):
        rows = realistic_codex_rows()[:3]
        rows.append(
            _row(
                "2026-08-12T10:00:11Z",
                "response_item",
                {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "wrapped-tools",
                    "input": """const a = await tools.exec_command({cmd: \"rg TODO\"});
const b = await tools.web__run({search_query:[{q:\"Codex docs\"}]});
const c = await tools.mcp__github__search_code({query:\"needle\"});
const d = await tools.spawn_agent({task_name:\"review\"});""",
                },
            )
        )
        rows.extend(realistic_codex_rows()[-2:])

        meta = self.m.extract_native_session_meta(rows, transcript_mtime=1.0, origin="active")

        self.assertEqual(
            meta["tool_counts"],
            {
                "exec_command": 1,
                "mcp__github__search_code": 1,
                "spawn_agent": 1,
                "web__run": 1,
            },
        )
        self.assertTrue(meta["uses_task_agent"])
        self.assertTrue(meta["uses_mcp"])
        self.assertTrue(meta["uses_web_search"])
        self.assertFalse(meta["uses_web_fetch"])

    def test_real_transcript_object_status_fields_do_not_crash_enum_checks(self):
        rows = realistic_codex_rows()
        rows.append(
            _row(
                "2026-08-12T10:08:00Z",
                "event_msg",
                {
                    "type": "task_complete_end",
                    "status": {"state": "completed", "detail": {"ok": True}},
                    "success": True,
                },
            )
        )
        rows.append(
            _row(
                "2026-08-12T10:08:01Z",
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "unknown-shape",
                    "status": {"state": "completed"},
                    "output": {"ok": True},
                },
            )
        )
        rows.append(
            _row(
                "2026-08-12T10:08:02Z",
                "response_item",
                {"type": {"kind": "message"}, "role": {"kind": "assistant"}},
            )
        )
        rows.append(
            _row(
                "2026-08-12T10:08:03Z",
                "event_msg",
                {"type": {"kind": "user_message"}, "message": {"text": "ignored"}},
            )
        )

        meta = self.m.extract_native_session_meta(rows, transcript_mtime=1.0, origin="active")

        self.assertEqual(meta["tool_errors"], 2)

    def test_detects_native_sandwich_overlap_and_includes_thirty_minute_boundary(self):
        metas = [
            {
                "session_key": "session-a",
                "user_message_timestamps": [
                    "2026-08-12T10:00:00Z",
                    "2026-08-12T10:30:00Z",
                    "2026-08-12T11:00:00Z",
                ],
            },
            {
                "session_key": "session-b",
                "user_message_timestamps": [
                    "2026-08-12T10:15:00Z",
                    "2026-08-12T10:45:00Z",
                ],
            },
            {"session_key": "session-c", "user_message_timestamps": ["2026-08-12T11:10:00Z"]},
        ]

        self.assertEqual(
            self.m.detect_multi_clauding(metas, window_minutes=30),
            {
                "detected": True,
                "event_pair_count": 1,
                "session_count": 2,
                "session_pairs": [["session-a", "session-b"]],
                "user_messages_during": 5,
            },
        )

        adjacent_only = [
            {"session_key": "session-a", "user_message_timestamps": ["2026-08-12T10:00:00Z"]},
            {"session_key": "session-b", "user_message_timestamps": ["2026-08-12T10:10:00Z"]},
        ]
        self.assertFalse(self.m.detect_multi_clauding(adjacent_only)["detected"])


if __name__ == "__main__":
    unittest.main()
