"""Inventory, privacy, and cache guardrails around the semantic pipeline."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "insights" / "scripts" / "insights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_guardrails", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_session(
    path: Path,
    session_id: str,
    start: datetime,
    *,
    messages: list[tuple[int, str, str]] | None = None,
    cwd: str = "/work/project",
) -> None:
    messages = messages or [
        (5, "user", "first request"),
        (45, "assistant", "working"),
        (75, "user", "second request"),
    ]
    rows = [
        {
            "timestamp": start.isoformat().replace("+00:00", "Z"),
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": start.isoformat().replace("+00:00", "Z"),
                "cwd": cwd,
            },
        }
    ]
    for seconds, role, text in messages:
        rows.append(
            {
                "timestamp": (start + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
                },
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_filters_current_self_analysis_and_under_one_minute_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            start = datetime(2026, 8, 12, tzinfo=timezone.utc)
            write_session(home / "sessions" / "valid.jsonl", "valid", start)
            write_session(home / "sessions" / "current.jsonl", "current", start)
            write_session(
                home / "sessions" / "self.jsonl",
                "self",
                start,
                messages=[(5, "user", "$insights MAX_NEW_SESSIONS=10"), (45, "assistant", "working"), (75, "user", "continue")],
            )
            write_session(
                home / "sessions" / "short.jsonl",
                "short",
                start,
                messages=[(5, "user", "one"), (20, "assistant", "working"), (40, "user", "two")],
            )
            found, stats = self.m.discover_sessions(home, current_thread_id="current", include_stats=True)
            self.assertEqual([record["meta"]["session_id"] for record in found], ["valid"])
            self.assertRegex(found[0]["session_key"], r"^session-[0-9a-f]{16}$")
            self.assertEqual(stats["excluded_current"], 1)
            self.assertEqual(stats["excluded_insights"], 1)
            self.assertEqual(stats["excluded_short_duration"], 1)

    def test_default_cap_is_200_and_coverage_identity_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            start = datetime(2026, 8, 1, tzinfo=timezone.utc)
            for index in range(205):
                write_session(
                    home / "sessions" / f"{index}.jsonl",
                    f"session-{index}",
                    start + timedelta(minutes=index * 3),
                )
            prepared = self.m.prepare_run(home)
            coverage = prepared["inventory"]
            self.assertEqual(len(prepared["work_items"]), 200)
            self.assertEqual(
                coverage["eligible"],
                coverage["cached"] + coverage["selected"] + coverage["remaining"],
            )
            self.assertEqual(coverage["remaining"], 5)

    def test_redaction_and_cached_path_containment_fail_safe(self):
        raw = "api_key=sk-live-ABCDEFGHIJKLMNOP Cookie: sid=secret a@example.com /Users/alice/x 192.168.1.2"
        redacted = self.m.redact_text(raw)
        self.assertEqual(self.m.privacy_violations(redacted), [])
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            output = home / "usage-data" / "insights"
            write_session(
                home / "sessions" / "one.jsonl",
                "one",
                datetime(2026, 8, 12, tzinfo=timezone.utc),
            )
            session = self.m.discover_sessions(home)[0]
            output.mkdir(parents=True)
            state = {
                "generation": 1,
                "analysis_version": self.m.ANALYSIS_VERSION,
                "meta_schema_version": self.m.META_SCHEMA_VERSION,
                "normalizer_version": self.m.NORMALIZER_VERSION,
                "facet_prompt_version": self.m.FACET_PROMPT_VERSION,
                "sessions": {
                    session["session_key"]: {
                        "facet_file": "../outside.json",
                        "source_hash": session["source_hash"],
                    }
                },
            }
            (output / "state.json").write_text(json.dumps(state), encoding="utf-8")
            (output.parent / "outside.json").write_text("{}", encoding="utf-8")
            prepared = self.m.prepare_run(home, output)
            self.assertEqual(prepared["inventory"]["cached"], 0)
            self.assertEqual(prepared["inventory"]["selected"], 1)

    def test_redaction_covers_cross_platform_paths_and_does_not_treat_times_as_ipv6(self):
        private_values = (
            "Bearer ABCDEFGHIJKLMNOP",
            "/private/var/folders/secret.txt",
            "/tmp/secret.txt",
            "/Volumes/Data/secret.txt",
            "~/secret.txt",
            r"D:\Private\secret.txt",
            r"\\server\share\secret.txt",
            "2001:db8::1",
        )
        for value in private_values:
            with self.subTest(value=value):
                redacted = self.m.redact_text(value)
                self.assertNotEqual(redacted, value)
                self.assertEqual(self.m.privacy_violations(redacted), [])
        self.assertEqual(self.m.redact_text("12:34:56"), "12:34:56")
        self.assertNotIn("ipv6", self.m.privacy_violations("12:34:56"))

    def test_symlink_source_and_output_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            outside = root / "outside"
            source = outside / "session.jsonl"
            write_session(source, "outside", datetime(2026, 8, 12, tzinfo=timezone.utc))
            (home / "sessions").mkdir(parents=True)
            (home / "sessions" / "linked.jsonl").symlink_to(source)

            found, stats = self.m.discover_sessions(home, include_stats=True)
            self.assertEqual(found, [])
            self.assertEqual(stats["physical_source_files"], 1)
            self.assertEqual(stats["parse_failed"], 1)

            (home / "usage-data").mkdir(parents=True)
            (home / "usage-data" / "insights").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(self.m.InsightsError):
                self.m.prepare_run(home)

    def test_inventory_ignores_object_shaped_event_enums_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / "sessions" / "object-enums.jsonl"
            write_session(path, "object-enums", datetime(2026, 8, 12, tzinfo=timezone.utc))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": "2026-08-12T00:02:00Z",
                            "type": "response_item",
                            "payload": {
                                "type": {"kind": "message"},
                                "role": {"kind": "assistant"},
                                "status": {"state": "completed"},
                            },
                        }
                    )
                    + "\n"
                )

            found = self.m.discover_sessions(home)

            self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
