"""Retained high-risk cache and transaction contracts (runner-independent)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "insights" / "scripts" / "insights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_cache_transaction", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_session(path: Path, session_id: str = "cache-session") -> None:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    rows = [
        {"timestamp": start.isoformat(), "type": "session_meta", "payload": {"id": session_id, "cwd": "/work/widget"}},
        {"timestamp": (start + timedelta(seconds=5)).isoformat(), "type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "修复缓存事务。"}]}},
        {"timestamp": (start + timedelta(seconds=40)).isoformat(), "type": "response_item", "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "先复现再修复。"}]}},
        {"timestamp": (start + timedelta(seconds=80)).isoformat(), "type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "很好，回滚也通过。"}]}},
        {"timestamp": (start + timedelta(seconds=110)).isoformat(), "type": "response_item", "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "完成。"}]}},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def facet() -> dict:
    return {
        "underlying_goal": "修复缓存事务", "goal_categories": {"fix_bug": 1},
        "outcome": "fully_achieved", "user_satisfaction_counts": {"satisfied": 1},
        "claude_helpfulness": "very_helpful", "session_type": "single_task",
        "friction_counts": {}, "friction_detail": "", "primary_success": "good_debugging",
        "brief_summary": "缓存事务与回滚验证完成。", "user_instructions_to_codex": ["先复现"],
        "evidence_anchors": ["用户确认回滚通过"],
    }


def lens(lens_id: str) -> dict:
    return {
        "project_areas": {"areas": [{"name": f"领域 {i}", "project_ids": ["project-00"], "description": "缓存事务。"} for i in range(4)]},
        "interaction_style": {"narrative": "先复现再验证。", "key_pattern": "证据闭环"},
        "what_works": {"intro": "失败注入有效。", "impressive_workflows": [{"title": f"流程 {i}", "description": "验证回滚。"} for i in range(3)]},
        "friction_analysis": {"intro": "边界易遗漏。", "categories": [{"title": f"风险模式 {i}", "description": "需复核。", "examples": ["例一", "例二"]} for i in range(3)]},
        "suggestions": {
            "agents_md_additions": [{"addition": f"规则 {i}", "why": "防回归。", "prompt_scaffold": "验证事务。"} for i in range(2)],
            "features_to_try": [{"feature": "Fast", "one_liner": "提速。", "why_for_you": "批量分析。", "example_code": "/fast"} for _ in range(2)],
            "usage_patterns": [{"title": f"模式 {i}", "suggestion": "先复现。", "detail": "再修复。", "copyable_prompt": "先写失败测试。"} for i in range(2)],
        },
        "on_the_horizon": {"intro": "持续质量。", "opportunities": [{"title": f"机会 {i}", "whats_possible": "质量雷达。", "how_to_try": "按月复盘。", "copyable_prompt": "比较本月。"} for i in range(3)]},
        "fun_ending": {"headline": "失败成为材料", "detail": "用失败验证恢复。"},
    }[lens_id]


GLANCE = {
    "whats_working": "失败注入有效。", "whats_hindering": "事务边界易遗漏。",
    "quick_wins": "先写失败测试。", "ambitious_workflows": "建立质量雷达。",
}


class CacheTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def ready(self, home: Path) -> tuple[dict, Path]:
        source = home / "sessions" / "one.jsonl"
        write_session(source)
        run = self.m.prepare_run(home, max_new_sessions=1)
        run.update({"run_id": "cache-run", "job_results": {}, "job_skips": set(), "aggregate": None, "lens_material": None, "preview_html": None})
        facet_jobs = self.m._facet_jobs(run)
        if facet_jobs:
            facet_job = facet_jobs[0]
            run["job_results"][facet_job["job_id"]] = self.m._validated_job_result(run, facet_job, facet())
        self.m._ensure_aggregate(run)
        for job in self.m._lens_jobs(run):
            run["job_results"][job["job_id"]] = self.m._validated_job_result(run, job, lens(job["lens_id"]))
        glance_job = self.m._glance_job(run)
        assert glance_job is not None
        run["job_results"][glance_job["job_id"]] = self.m._validated_job_result(run, glance_job, GLANCE)
        self.assertEqual(self.m._stage(run)["stage"], "ready_to_commit")
        return run, source

    def test_aggregate_counts_all_eligible_meta_but_only_analyzed_facets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            write_session(home / "sessions" / "one.jsonl", "one")
            write_session(home / "sessions" / "two.jsonl", "two")
            run = self.m.prepare_run(home, max_new_sessions=1)
            run.update({"run_id": "r", "job_results": {}, "job_skips": set(), "aggregate": None, "lens_material": None})
            job = self.m._facet_jobs(run)[0]
            run["job_results"][job["job_id"]] = self.m._validated_job_result(run, job, facet())
            self.m._ensure_aggregate(run)
            self.assertEqual((run["aggregate"]["total_sessions"], run["aggregate"]["sessions_with_facets"]), (1, 1))
            self.assertEqual(run["eligible_aggregate"]["total_sessions"], 2)
            self.assertIn("coverage_limited", run["lens_material"])

    def test_legacy_analysis_version_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; output = home / "usage-data" / "insights"
            write_session(home / "sessions" / "one.jsonl"); output.mkdir(parents=True)
            (output / "state.json").write_text(json.dumps({"generation": 9, "analysis_version": "old", "sessions": {}}), encoding="utf-8")
            prepared = self.m.prepare_run(home, output, max_new_sessions=1)
            self.assertTrue(prepared["legacy_cache_detected"]); self.assertEqual(prepared["inventory"]["selected"], 1)

    def test_legacy_cache_is_archived_and_orphan_facets_are_removed_after_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; output = home / "usage-data" / "insights"
            old_facet = output / "facets" / "deadbeefdeadbeef-cafebabecafebabe.json"
            old_facet.parent.mkdir(parents=True)
            old_facet.write_text('{"legacy":true}', encoding="utf-8")
            (output / "state.json").write_text(json.dumps({"generation": 9, "analysis_version": "old", "sessions": {}}), encoding="utf-8")
            (output / "manifest.json").write_text('{"generation":9}', encoding="utf-8")
            run, _ = self.ready(home)
            result = self.m.commit_run(run)
            legacy_dirs = list((output / "legacy").iterdir())
            self.assertEqual(len(legacy_dirs), 1)
            self.assertTrue((legacy_dirs[0] / "state.json").is_file())
            self.assertTrue((legacy_dirs[0] / "manifest.json").is_file())
            self.assertTrue((legacy_dirs[0] / "facets" / old_facet.name).is_file())
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            expected = {entry["facet_file"] for entry in state["sessions"].values()}
            actual = {path.relative_to(output).as_posix() for path in (output / "facets").glob("*.json")}
            self.assertEqual(actual, expected)
            self.assertEqual(result["facet_count"], len(expected))

    def test_source_append_does_not_abort_snapshot_commit_and_invalidates_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; run, source = self.ready(home)
            source.write_text(source.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
            committed = self.m.commit_run(run)
            self.assertTrue(Path(committed["report_path"]).is_file())
            next_run = self.m.prepare_run(home, max_new_sessions=1)
            self.assertEqual(next_run["inventory"]["cached"], 0)
            self.assertEqual(next_run["inventory"]["selected"], 1)

    def test_transaction_rolls_back_then_same_run_can_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; run, _ = self.ready(home)
            with self.assertRaises(RuntimeError): self.m.commit_run(run, failpoint="before_state")
            self.assertFalse((home / "usage-data" / "insights" / "state.json").exists())
            self.assertEqual(self.m.commit_run(run)["generation"], 1)

    def test_manifest_hashes_state_and_every_facet(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; run, _ = self.ready(home); result = self.m.commit_run(run)
            output = home / "usage-data" / "insights"; manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["state_sha256"], hashlib.sha256((output / "state.json").read_bytes()).hexdigest())
            for relative, digest in manifest["files"].items(): self.assertEqual(digest, hashlib.sha256((output / relative).read_bytes()).hexdigest())

    def test_same_generation_state_tamper_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; first, _ = self.ready(home); self.m.commit_run(first)
            second, _ = self.ready(home); state = home / "usage-data" / "insights" / "state.json"
            value = json.loads(state.read_text(encoding="utf-8")); value["tampered"] = True; state.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(self.m.StaleRunError): self.m.commit_run(second)

    def test_commit_rechecks_snapshot_immediately_before_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"; run, _ = self.ready(home)
            with mock.patch.object(self.m, "_verify_run_snapshot", side_effect=[None, self.m.StaleRunError("changed")]) as verify:
                with self.assertRaises(self.m.StaleRunError): self.m.commit_run(run)
            self.assertGreaterEqual(verify.call_count, 2)
            self.assertFalse((home / "usage-data" / "insights" / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
