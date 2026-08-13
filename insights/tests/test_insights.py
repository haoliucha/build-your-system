import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "insights"
MODULE_PATH = SKILL_ROOT / "scripts" / "insights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_kernel", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, session_id: str, start: datetime, messages=None, cwd="/work/project"):
    messages = messages or ["first request", "assistant response", "second request"]
    rows = [{"timestamp": start.isoformat().replace("+00:00", "Z"), "type": "session_meta", "payload": {"id": session_id, "timestamp": start.isoformat().replace("+00:00", "Z"), "cwd": cwd}}]
    for index, text in enumerate(messages):
        stamp = (start + timedelta(seconds=70 * (index + 1))).isoformat().replace("+00:00", "Z")
        rows.append({"timestamp": stamp, "type": "response_item", "payload": {"role": "user" if index % 2 == 0 else "assistant", "content": [{"type": "input_text", "text": text}]}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def facet_for(item, module, goal="完成一个可验证任务"):
    stats = item["deterministic_stats"]
    return {
        "schema_version": module.FACET_SCHEMA_VERSION,
        "session_key": item["session_key"], "source_hash": item["source_hash"], "date": item["date"],
        "project_alias": item["project_alias"], "session_origin": item["session_origin"],
        "deterministic_stats": stats, "privacy_redactions": item["privacy_redactions"],
        "underlying_goal": goal, "goal_categories": ["engineering"], "outcome": "mostly_achieved",
        "user_satisfaction_counts": {"positive": 1, "negative": 0, "correction": 0}, "helpfulness": "very_helpful",
        "session_type": "single_task", "friction_counts": {name: 0 for name in module.FRICTION_TYPES},
        "friction_detail": [], "primary_success": "完成并验证结果", "brief_summary": "一条经过脱敏的会话摘要。",
        "evidence_anchors": ["用户目标", "最终验证"],
    }


class KernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_filters_current_marker_short_and_assigns_opaque_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            base = home / "sessions"
            start = datetime(2026, 8, 12, tzinfo=timezone.utc)
            write_jsonl(base / "valid.jsonl", "valid", start)
            write_jsonl(base / "current.jsonl", "current", start)
            write_jsonl(base / "marker.jsonl", "marker", start, ["$insights", "ignored"])
            short = base / "short.jsonl"
            short.parent.mkdir(parents=True, exist_ok=True)
            short.write_text("\n".join([
                json.dumps({"timestamp": "2026-08-12T10:00:00Z", "type": "session_meta", "payload": {"id": "short"}}),
                json.dumps({"timestamp": "2026-08-12T10:00:10Z", "type": "event_msg", "payload": {"type": "user_message", "message": "one"}}),
                json.dumps({"timestamp": "2026-08-12T10:00:40Z", "type": "event_msg", "payload": {"type": "user_message", "message": "two"}}),
            ]) + "\n", encoding="utf-8")
            found = self.m.discover_sessions(home, current_thread_id="current")
            self.assertEqual(len(found), 1)
            self.assertRegex(found[0]["session_key"], r"^session-[0-9a-f]{16}$")
            self.assertNotIn("valid", found[0]["session_key"])
            self.assertEqual(found[0]["origin"], "active")

    def test_cap_coverage_and_long_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, output = Path(tmp) / "home", Path(tmp) / "out"
            start = datetime(2026, 8, 1, tzinfo=timezone.utc)
            for index in range(205):
                write_jsonl(home / "sessions" / f"{index}.jsonl", str(index), start + timedelta(minutes=index * 4))
            prepared = self.m.prepare_run(home, output)
            self.assertEqual(len(prepared["work_items"]), 200)
            stats = prepared["inventory"]
            self.assertEqual((stats["eligible"], stats["cached"], stats["selected"], stats["remaining"]), (205, 0, 200, 5))
            self.assertEqual(stats["eligible"], stats["cached"] + stats["selected"] + stats["remaining"])

    def test_long_chunks_keep_every_event_and_tail(self):
        events = [{"timestamp": str(i), "role": "user", "text": chr(65 + i) * 9000} for i in range(5)]
        chunks = self.m.chunk_events(events)
        flattened = [event["text"] for chunk in chunks for event in chunk["events"]]
        self.assertEqual(flattened, [item["text"] for item in events])
        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[-1]["events"][-1]["text"].endswith("E" * 100))

    def test_redaction_and_v2_facet(self):
        raw = "api_key=sk-live-ABCDEFGHIJKLMNOP Cookie: sid=secret a@example.com /Users/alice/x 192.168.1.2"
        self.assertEqual(self.m.privacy_violations(self.m.redact_text(raw)), [])
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            write_jsonl(home / "sessions" / "one.jsonl", "one", datetime(2026, 8, 12, tzinfo=timezone.utc))
            item = self.m.prepare_run(home, Path(tmp) / "out")["work_items"][0]
            facet = facet_for(item, self.m)
            self.assertEqual(self.m.validate_facet(facet), facet)
            self.assertEqual(facet["schema_version"], "facet_v2")

    def test_html_escapes_model_text(self):
        facet = {"schema_version": self.m.FACET_SCHEMA_VERSION, "session_key": "session-0000000000000001", "source_hash": "a" * 64, "date": "2026-08-12", "project_alias": "project-00000000", "session_origin": "active", "deterministic_stats": {key: 0 for key in self.m.STATS_KEYS}, "privacy_redactions": {"policy": "pre-model-redaction-v1"}, "underlying_goal": "<script>alert(1)</script>", "goal_categories": [], "outcome": "unclear_from_transcript", "user_satisfaction_counts": {"positive": 0, "negative": 0, "correction": 0}, "helpfulness": "moderately_helpful", "session_type": "exploration", "friction_counts": {name: 0 for name in self.m.FRICTION_TYPES}, "friction_detail": [], "primary_success": "", "brief_summary": "", "evidence_anchors": []}
        patterns = {"schema_version": self.m.AGGREGATION_SCHEMA_VERSION, "groups": {group: ([{"kind": "repeat", "claim": "<script>alert(1)</script>", "evidence": [facet["session_key"]], "confidence": 0.2}] if group == "goals" else []) for group in self.m.PATTERN_GROUPS}}
        rendered = self.m.render_report([facet], patterns=patterns)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)

    def test_patterns_lenses_and_quality_require_evidence_and_hard_gates(self):
        keys = {"session-0000000000000001", "session-0000000000000002"}
        pattern_item = {"kind": "repeat", "claim": "反复目标", "evidence": sorted(keys), "confidence": 0.8}
        patterns = {"schema_version": self.m.AGGREGATION_SCHEMA_VERSION, "groups": {group: [pattern_item] if group == "goals" else [] for group in self.m.PATTERN_GROUPS}}
        self.assertEqual(self.m.validate_patterns(patterns, keys), patterns)
        lens_item = {"claim": "反复协作方式", "evidence": sorted(keys), "action": "保留检查点", "success_criteria": "返工减少", "confidence": 0.8}
        lenses = {"schema_version": self.m.AGGREGATION_SCHEMA_VERSION, "lenses": {lens: [lens_item] for lens in self.m.LENS_IDS}}
        self.assertEqual(self.m.validate_lenses(lenses, keys), lenses)
        quality = {"schema_version": self.m.QUALITY_SCHEMA_VERSION, "scores": {"coverage": 4, "evidence": 4, "privacy": 5, "actionability": 4, "incremental": 4}, "revision_count": 0, "concerns": []}
        self.assertEqual(self.m.validate_quality(quality), quality)
        quality["scores"]["privacy"] = 3
        with self.assertRaises(self.m.PrivacyError):
            self.m.validate_quality(quality)

    def test_html_contract_has_navigation_and_no_active_content(self):
        facet = {"schema_version": self.m.FACET_SCHEMA_VERSION, "session_key": "session-0000000000000001", "source_hash": "a" * 64, "date": "2026-08-12", "project_alias": "project-00000000", "session_origin": "active", "deterministic_stats": {key: 0 for key in self.m.STATS_KEYS}, "privacy_redactions": {"policy": "pre-model-redaction-v1"}, "underlying_goal": "<script>", "goal_categories": [], "outcome": "unclear_from_transcript", "user_satisfaction_counts": {"positive": 0, "negative": 0, "correction": 0}, "helpfulness": "moderately_helpful", "session_type": "exploration", "friction_counts": {name: 0 for name in self.m.FRICTION_TYPES}, "friction_detail": [], "primary_success": "", "brief_summary": "", "evidence_anchors": []}
        html = self.m.render_report([facet], coverage={"eligible": 1, "cached": 0, "selected": 1, "remaining": 0})
        self.assertIn('<html lang="zh-CN">', html)
        self.assertEqual(html.count("<style>"), 1)
        self.assertNotIn("<script", html.lower())
        for directive in ("default-src 'none'", "script-src 'none'", "connect-src 'none'", "frame-src 'none'", "object-src 'none'", "base-uri 'none'", "form-action 'none'"):
            self.assertIn(directive, html)
        for section in self.m.SECTION_IDS:
            self.assertIn(f'id="{section}"', html)
            self.assertIn(f'href="#{section}"', html)
        self.assertNotIn("<script>", html)

    def test_protocol_stages_alias_next_and_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            output = home / "usage-data" / "insights"
            write_jsonl(home / "sessions" / "one.jsonl", "one", datetime(2026, 8, 12, tzinfo=timezone.utc))
            pending = {}
            prepared = self.m.handle_request({"action": "prepare", "codex_home": str(home)}, pending)["result"]
            run_id = prepared["run_id"]
            full = self.m.prepare_run(home, output)
            facet = facet_for(full["work_items"][0], self.m)
            aggregate = self.m.handle_request({"op": "aggregate", "run_id": run_id, "facets": [facet]}, pending)
            self.assertEqual(aggregate["result"]["next"]["op"], "validate_patterns")
            patterns = self.m._fallback_patterns([facet])
            self.m.handle_request({"op": "validate_patterns", "run_id": run_id, "patterns": patterns}, pending)
            lenses = self.m._fallback_lenses([facet])
            self.m.handle_request({"op": "validate_lenses", "run_id": run_id, "lenses": lenses}, pending)
            quality = {"schema_version": self.m.QUALITY_SCHEMA_VERSION, "scores": {"coverage": 4, "evidence": 4, "privacy": 5, "actionability": 3, "incremental": 4}, "revision_count": 0, "concerns": []}
            self.m.handle_request({"op": "validate_quality", "run_id": run_id, "quality": quality}, pending)
            result = self.m.handle_request({"op": "commit", "run_id": run_id, "facets": [facet], "patterns": patterns, "lenses": lenses, "quality": quality}, pending)
            self.assertTrue(Path(result["result"]["report_path"]).is_file())
            self.assertTrue(Path(result["result"]["timestamp_report_path"]).name.startswith("report-202"))
            self.assertFalse((output / ".insights.lock").exists())
            with self.assertRaises(self.m.InsightsError):
                self.m.handle_request({"op": "commit", "run_id": run_id, "facets": [facet]}, pending)

    def test_protocol_fixes_output_root_and_cache_is_language_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            output = home / "usage-data" / "insights"
            write_jsonl(home / "sessions" / "one.jsonl", "one", datetime(2026, 8, 12, tzinfo=timezone.utc))
            with self.assertRaises(self.m.InsightsError):
                self.m.handle_request({"op": "prepare", "codex_home": str(home), "output_dir": str(Path(tmp) / "elsewhere")}, {})
            prepared = self.m.prepare_run(home, output, language="zh-CN")
            facet = facet_for(prepared["work_items"][0], self.m)
            self.m.commit_run(output, prepared, [facet], patterns=self.m._fallback_patterns([facet]), lenses=self.m._fallback_lenses([facet]), quality={"schema_version": self.m.QUALITY_SCHEMA_VERSION, "scores": {"coverage": 4, "evidence": 4, "privacy": 5, "actionability": 3, "incremental": 4}, "revision_count": 0, "concerns": ["单元测试"]})
            cached = self.m.prepare_run(home, output, language="en-US")
            self.assertEqual(cached["inventory"]["cached"], 1)
            self.assertEqual(cached["inventory"]["selected"], 0)

    def test_cached_facet_path_traversal_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, output = Path(tmp) / "home", Path(tmp) / "out"
            write_jsonl(home / "sessions" / "one.jsonl", "one", datetime(2026, 8, 12, tzinfo=timezone.utc))
            output.mkdir(parents=True)
            (output / "state.json").write_text(json.dumps({"generation": 1, "sessions": {"session-0000000000000001": {"facet_file": "../outside.json", "source_hash": "a" * 64}}}), encoding="utf-8")
            (output.parent / "outside.json").write_text("{}", encoding="utf-8")
            prepared = self.m.prepare_run(home, output)
            self.assertEqual(prepared["inventory"]["cached"], 0)
            self.assertEqual(prepared["inventory"]["selected"], 1)


if __name__ == "__main__":
    unittest.main()
