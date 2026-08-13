"""End-to-end RED tests for the helper-owned Insights job protocol."""

from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "insights" / "scripts" / "insights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_native_protocol", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_session(path: Path, session_id: str = "semantic-smoke") -> None:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": start.isoformat().replace("+00:00", "Z"),
            "type": "session_meta",
            "payload": {"id": session_id, "timestamp": start.isoformat().replace("+00:00", "Z"), "cwd": "/work/widget"},
        },
        {
            "timestamp": (start + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {"role": "user", "content": [{"type": "input_text", "text": "修复缓存事务并跑回归测试。"}]},
        },
        {
            "timestamp": (start + timedelta(seconds=35)).isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "我会先复现再修复。"}]},
        },
        {
            "timestamp": (start + timedelta(seconds=80)).isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {"role": "user", "content": [{"type": "input_text", "text": "很好，确认回滚也覆盖了。"}]},
        },
        {
            "timestamp": (start + timedelta(seconds=110)).isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "回归测试和失败注入均通过。"}]},
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def facet_result() -> dict:
    return {
        "underlying_goal": "修复缓存事务并验证回滚",
        "goal_categories": {"debugging": 1, "testing": 1},
        "outcome": "fully_achieved",
        "user_satisfaction_counts": {"satisfied": 1},
        "claude_helpfulness": "very_helpful",
        "session_type": "single_task",
        "friction_counts": {},
        "friction_detail": "",
        "primary_success": "good_debugging",
        "brief_summary": "修复缓存事务，并通过回归测试与失败注入。",
        "user_instructions_to_codex": ["先复现再修复"],
        "evidence_anchors": ["用户要求修复缓存事务", "回归与失败注入通过"],
    }


def result_for_lens(lens_id: str) -> dict:
    return {
        "project_areas": {"areas": [{"name": f"缓存领域 {index}", "session_count": 1, "description": "修复事务和回滚。"} for index in range(4)]},
        "interaction_style": {"narrative": "你要求先复现，再用测试闭环。", "key_pattern": "证据优先"},
        "what_works": {"intro": "测试闭环有效。", "impressive_workflows": [{"title": f"失败注入 {index}", "description": "用失败场景验证回滚。"} for index in range(3)]},
        "friction_analysis": {"intro": "本轮摩擦较少。", "categories": [{"category": f"缓存风险 {index}", "description": "提交边界需要验证。", "examples": ["失败注入", "回滚复核"]} for index in range(3)]},
        "suggestions": {
            "agents_md_additions": [{"addition": f"事务规则 {index}", "why": "避免回滚缺口。", "prompt_scaffold": "验证规则"} for index in range(2)],
            "features_to_try": [{"feature": f"Codex 子代理 {index}", "one_liner": "并行审计。", "why_for_you": "缩短复核时间。", "example_code": "$insights MAX_NEW_SESSIONS=10"} for index in range(2)],
            "usage_patterns": [{"title": f"先复现 {index}", "suggestion": "先建立失败测试。", "detail": "只在失败可重复后修复。", "copyable_prompt": "先复现问题，再提出最小修复。"} for index in range(2)],
        },
        "on_the_horizon": {"intro": "可以扩展为持续质量雷达。", "opportunities": [{"title": f"质量雷达 {index}", "whats_possible": "跨仓库发现风险。", "how_to_try": "先从三个仓库开始。", "copyable_prompt": "比较三个仓库的失败模式。"} for index in range(3)]},
        "fun_ending": {"headline": "你把失败当作测试材料", "detail": "失败注入成为验收的一部分。"},
    }[lens_id]


class NativeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def _ready_run(self, home: Path, pending: dict[str, dict]) -> tuple[str, Path]:
        source = home / "sessions" / "one.jsonl"
        write_session(source)
        prepared = self.m.handle_request(
            {"op": "prepare", "codex_home": str(home), "max_new_sessions": 1},
            pending,
        )["result"]
        run_id = prepared["run_id"]
        facet_job = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]["jobs"][0]
        self.m.handle_request(
            {"op": "submit_jobs", "run_id": run_id, "results": [{"job_id": facet_job["job_id"], "result": facet_result()}]},
            pending,
        )
        lens_jobs = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]["jobs"]
        self.m.handle_request(
            {
                "op": "submit_jobs",
                "run_id": run_id,
                "results": [{"job_id": job["job_id"], "result": result_for_lens(job["lens_id"])} for job in lens_jobs],
            },
            pending,
        )
        glance_job = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]["jobs"][0]
        glance = {
            "whats_working": "失败注入让验证更可靠。",
            "whats_hindering": "需要减少事务边界遗漏。",
            "quick_wins": "把失败注入写入 AGENTS.md。",
            "ambitious_workflows": "建立跨仓库质量雷达。",
        }
        self.m.handle_request(
            {"op": "submit_jobs", "run_id": run_id, "results": [{"job_id": glance_job["job_id"], "result": glance}]},
            pending,
        )
        return run_id, source

    def test_helper_owns_artifacts_and_enforces_facet_lens_glance_commit_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            write_session(home / "sessions" / "one.jsonl")
            pending: dict[str, dict] = {}

            prepared = self.m.handle_request({"op": "prepare", "codex_home": str(home), "max_new_sessions": 1}, pending)["result"]
            run_id = prepared["run_id"]
            with self.assertRaises(self.m.InsightsError):
                self.m.handle_request({"op": "commit", "run_id": run_id}, pending)

            jobs = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]["jobs"]
            self.assertEqual([job["kind"] for job in jobs], ["session_facet"])
            self.m.handle_request(
                {"op": "submit_jobs", "run_id": run_id, "results": [{"job_id": jobs[0]["job_id"], "result": facet_result()}]},
                pending,
            )

            lens_jobs = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]["jobs"]
            self.assertEqual(len(lens_jobs), 7)
            self.assertEqual({job["kind"] for job in lens_jobs}, {"lens"})
            self.m.handle_request(
                {
                    "op": "submit_jobs",
                    "run_id": run_id,
                    "results": [{"job_id": job["job_id"], "result": result_for_lens(job["lens_id"])} for job in lens_jobs],
                },
                pending,
            )

            glance_jobs = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]["jobs"]
            self.assertEqual([job["kind"] for job in glance_jobs], ["at_a_glance"])
            glance = {
                "whats_working": "失败注入让验证更可靠。",
                "whats_hindering": "需要减少事务边界遗漏。",
                "quick_wins": "把失败注入写入 AGENTS.md。",
                "ambitious_workflows": "建立跨仓库质量雷达。",
            }
            self.m.handle_request(
                {"op": "submit_jobs", "run_id": run_id, "results": [{"job_id": glance_jobs[0]["job_id"], "result": glance}]},
                pending,
            )
            ready = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]
            self.assertEqual(ready["stage"], "ready_to_commit")
            self.assertIn("<!doctype html>", ready["preview_html"].lower())

            with self.assertRaises(self.m.InsightsError):
                self.m.handle_request({"op": "commit", "run_id": run_id, "facets": []}, pending)
            committed = self.m.handle_request({"op": "commit", "run_id": run_id}, pending)["result"]
            output = home / "usage-data" / "insights"
            self.assertEqual(committed["facet_count"], 1)
            self.assertTrue((output / "report.html").is_file())
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(state["analysis_version"], self.m.ANALYSIS_VERSION)
            self.assertEqual(manifest["analysis"]["facet_schema"], self.m.FACET_SCHEMA_VERSION)
            self.assertEqual(state["coverage"]["eligible"], state["coverage"]["cached"] + state["coverage"]["selected"] + state["coverage"]["remaining"])

    def test_aggregate_counts_all_eligible_meta_but_only_analyzed_facets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            write_session(home / "sessions" / "one.jsonl", "semantic-one")
            write_session(home / "sessions" / "two.jsonl", "semantic-two")
            pending: dict[str, dict] = {}

            prepared = self.m.handle_request(
                {"op": "prepare", "codex_home": str(home), "max_new_sessions": 1}, pending
            )["result"]
            run_id = prepared["run_id"]
            facet_job = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"][0]
            self.m.handle_request(
                {
                    "op": "submit_jobs",
                    "run_id": run_id,
                    "results": [{"job_id": facet_job["job_id"], "result": facet_result()}],
                },
                pending,
            )

            run = pending[run_id]
            self.m._ensure_aggregate(run)
            self.assertEqual(run["inventory"]["eligible"], 2)
            self.assertEqual(run["inventory"]["remaining"], 1)
            self.assertEqual(run["aggregate"]["total_sessions"], 2)
            self.assertEqual(run["aggregate"]["sessions_with_facets"], 1)
            self.assertIn("coverage_limited", run["lens_material"])

            remaining_key = next(
                key for key in run["source_snapshots"] if key not in run["selected_sessions"]
            )
            remaining_source = Path(run["source_snapshots"][remaining_key]["source_path"])
            with remaining_source.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "event_msg", "payload": {"type": "notice"}}) + "\n")
            with self.assertRaises(self.m.StaleRunError):
                self.m._verify_run_snapshot(run)

    def test_legacy_or_wrong_analysis_version_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            output = home / "usage-data" / "insights"
            write_session(home / "sessions" / "one.jsonl")
            output.mkdir(parents=True)
            (output / "state.json").write_text(
                json.dumps({"generation": 9, "analysis_version": "placeholder-v0", "sessions": {}}),
                encoding="utf-8",
            )

            prepared = self.m.prepare_run(home, output, max_new_sessions=1)
            self.assertTrue(prepared["legacy_cache_detected"])
            self.assertEqual(prepared["inventory"]["cached"], 0)
            self.assertEqual(prepared["inventory"]["selected"], 1)

    def test_source_change_before_commit_fails_without_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            run_id, source = self._ready_run(home, pending)
            with source.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"timestamp": "2026-08-12T01:00:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"output_tokens": 1}}}}) + "\n")
            with self.assertRaises(self.m.StaleRunError):
                self.m.handle_request({"op": "commit", "run_id": run_id}, pending)
            output = home / "usage-data" / "insights"
            self.assertFalse((output / "state.json").exists())
            self.assertFalse((output / "report.html").exists())
            self.assertFalse((output / ".insights.lock").exists())

    def test_transaction_rolls_back_before_state_and_same_run_can_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            run_id, _source = self._ready_run(home, pending)
            with self.assertRaises(RuntimeError):
                self.m.commit_run(pending[run_id], failpoint="before_state")
            output = home / "usage-data" / "insights"
            self.assertFalse((output / "state.json").exists())
            self.assertFalse((output / "report.html").exists())
            self.assertFalse((output / ".insights.lock").exists())
            committed = self.m.handle_request({"op": "commit", "run_id": run_id}, pending)["result"]
            self.assertEqual(committed["generation"], 1)
            self.assertTrue((output / "report.html").is_file())

    def test_submit_jobs_batch_is_atomic_when_a_later_result_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            source = home / "sessions" / "one.jsonl"
            write_session(source)
            prepared = self.m.handle_request(
                {"op": "prepare", "codex_home": str(home), "max_new_sessions": 1}, pending
            )["result"]
            run_id = prepared["run_id"]
            facet_job = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"][0]
            self.m.handle_request(
                {
                    "op": "submit_jobs",
                    "run_id": run_id,
                    "results": [{"job_id": facet_job["job_id"], "result": facet_result()}],
                },
                pending,
            )
            lens_jobs = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"]

            with self.assertRaises(self.m.FacetValidationError):
                self.m.handle_request(
                    {
                        "op": "submit_jobs",
                        "run_id": run_id,
                        "results": [
                            {
                                "job_id": lens_jobs[0]["job_id"],
                                "result": result_for_lens(lens_jobs[0]["lens_id"]),
                            },
                            {"job_id": lens_jobs[1]["job_id"], "result": {"invalid": True}},
                        ],
                    },
                    pending,
                )

            retry = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"]
            self.assertEqual(
                {job["job_id"] for job in retry},
                {job["job_id"] for job in lens_jobs},
            )

    def test_submit_jobs_cannot_cross_the_issued_stage_with_a_guessed_job_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            write_session(home / "sessions" / "one.jsonl")
            run_id = self.m.handle_request(
                {"op": "prepare", "codex_home": str(home), "max_new_sessions": 1}, pending
            )["result"]["run_id"]
            facet_job = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"][0]
            guessed_lens_id = self.m._job_id(run_id, "lens", "project_areas")

            with self.assertRaises(self.m.InsightsError):
                self.m.handle_request(
                    {
                        "op": "submit_jobs",
                        "run_id": run_id,
                        "results": [
                            {"job_id": facet_job["job_id"], "result": facet_result()},
                            {
                                "job_id": guessed_lens_id,
                                "result": result_for_lens("project_areas"),
                            },
                        ],
                    },
                    pending,
                )

            retry = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"]
            self.assertEqual([job["job_id"] for job in retry], [facet_job["job_id"]])

    def test_manifest_covers_state_and_every_referenced_facet_and_corruption_is_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            run_id, _source = self._ready_run(home, pending)
            self.m.handle_request({"op": "commit", "run_id": run_id}, pending)
            output = home / "usage-data" / "insights"
            state_bytes = (output / "state.json").read_bytes()
            state = json.loads(state_bytes)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["state_sha256"], hashlib.sha256(state_bytes).hexdigest())
            self.assertEqual(manifest["files"]["state.json"], manifest["state_sha256"])
            for entry in state["sessions"].values():
                self.assertIn(entry["facet_file"], manifest["files"])
                facet_path = output / entry["facet_file"]
                self.assertEqual(
                    manifest["files"][entry["facet_file"]],
                    hashlib.sha256(facet_path.read_bytes()).hexdigest(),
                )

            facet_path = output / next(iter(state["sessions"].values()))["facet_file"]
            facet_path.write_bytes(facet_path.read_bytes() + b"\n")
            prepared = self.m.prepare_run(home, output, max_new_sessions=1)
            self.assertTrue(prepared["legacy_cache_detected"])
            self.assertEqual(prepared["inventory"]["cached"], 0)
            self.assertEqual(prepared["inventory"]["selected"], 1)

    def test_cached_source_and_same_generation_state_changes_both_stale_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            first_run, source = self._ready_run(home, pending)
            self.m.handle_request({"op": "commit", "run_id": first_run}, pending)

            # A second run uses the previously committed facet, so it has no facet job.
            prepared = self.m.handle_request(
                {"op": "prepare", "codex_home": str(home), "max_new_sessions": 1}, pending
            )["result"]
            run_id = prepared["run_id"]
            lens_jobs = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"]
            self.m.handle_request(
                {
                    "op": "submit_jobs",
                    "run_id": run_id,
                    "results": [
                        {"job_id": job["job_id"], "result": result_for_lens(job["lens_id"])}
                        for job in lens_jobs
                    ],
                },
                pending,
            )
            glance_job = self.m.handle_request(
                {"op": "next_jobs", "run_id": run_id}, pending
            )["result"]["jobs"][0]
            self.m.handle_request(
                {
                    "op": "submit_jobs",
                    "run_id": run_id,
                    "results": [
                        {
                            "job_id": glance_job["job_id"],
                            "result": {
                                "whats_working": "失败注入让验证更可靠。",
                                "whats_hindering": "需要减少事务边界遗漏。",
                                "quick_wins": "把失败注入写入 AGENTS.md。",
                                "ambitious_workflows": "建立跨仓库质量雷达。",
                            },
                        }
                    ],
                },
                pending,
            )

            with source.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": "2026-08-12T01:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "token_count"},
                        }
                    )
                    + "\n"
                )
            with self.assertRaises(self.m.StaleRunError):
                self.m.handle_request({"op": "commit", "run_id": run_id}, pending)

            # Restore the source snapshot and change state without changing generation.
            write_session(source)
            state_path = home / "usage-data" / "insights" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["tampered_same_generation"] = True
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(self.m.StaleRunError):
                self.m.handle_request({"op": "commit", "run_id": run_id}, pending)

    def test_commit_rechecks_snapshot_immediately_before_state_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            pending: dict[str, dict] = {}
            run_id, _source = self._ready_run(home, pending)
            run = pending[run_id]
            with mock.patch.object(
                self.m,
                "_verify_run_snapshot",
                side_effect=[None, self.m.StaleRunError("changed before state")],
            ) as verify:
                with self.assertRaises(self.m.StaleRunError):
                    self.m.commit_run(run)
            self.assertGreaterEqual(verify.call_count, 2)
            output = home / "usage-data" / "insights"
            self.assertFalse((output / "state.json").exists())
            self.assertFalse((output / "report.html").exists())

    def test_protocol_binds_process_codex_home_and_supports_abort_and_ttl_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "process-home"
            other = Path(tmp) / "attacker-home"
            write_session(home / "sessions" / "one.jsonl")
            pending: dict[str, dict] = {}
            original = getattr(self.m, "_PROCESS_CODEX_HOME", None)
            self.m._PROCESS_CODEX_HOME = home.resolve()
            try:
                with self.assertRaises(self.m.InsightsError):
                    self.m.handle_request(
                        {"op": "prepare", "codex_home": str(other), "max_new_sessions": 1},
                        pending,
                        bind_process_home=True,
                    )
                prepared = self.m.handle_request(
                    {"op": "prepare", "max_new_sessions": 1},
                    pending,
                    bind_process_home=True,
                )["result"]
                self.assertEqual(prepared["stats"]["selected"], 1)
                run_id = prepared["run_id"]
                aborted = self.m.handle_request(
                    {"op": "abort", "run_id": run_id}, pending
                )["result"]
                self.assertTrue(aborted["aborted"])
                self.assertNotIn(run_id, pending)

                pending["expired"] = {"expires_at": 1.0}
                removed = self.m._cleanup_pending_runs(pending, now=2.0)
                self.assertEqual(removed, ["expired"])
                self.assertNotIn("expired", pending)
            finally:
                if original is None:
                    delattr(self.m, "_PROCESS_CODEX_HOME")
                else:
                    self.m._PROCESS_CODEX_HOME = original

    def test_jsonl_error_response_keeps_recoverable_run_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "process-home"
            write_session(home / "sessions" / "one.jsonl")
            original = getattr(self.m, "_PROCESS_CODEX_HOME", None)
            self.m._PROCESS_CODEX_HOME = home.resolve()
            try:
                request_stream = io.StringIO(
                    json.dumps({"op": "prepare", "max_new_sessions": 1})
                    + "\n"
                    + json.dumps(
                        {
                            "op": "submit_jobs",
                            "run_id": "fixed-run",
                            "results": [{"job_id": "not-a-job", "result": {}}],
                        }
                    )
                    + "\n"
                )
                output_stream = io.StringIO()
                with mock.patch.object(
                    self.m.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed-run")
                ):
                    self.m.serve_json_lines(request_stream, output_stream)
                responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
                self.assertTrue(responses[0]["ok"])
                self.assertFalse(responses[1]["ok"])
                self.assertEqual(
                    responses[1]["error"]["next"],
                    {"op": "next_jobs", "run_id": "fixed-run"},
                )
            finally:
                if original is None:
                    delattr(self.m, "_PROCESS_CODEX_HOME")
                else:
                    self.m._PROCESS_CODEX_HOME = original


if __name__ == "__main__":
    unittest.main()
