"""Release-gate tests for the persistent codex exec Insights runner."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "insights" / "scripts"
RUNNER_PATH = SCRIPTS / "runner.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("insights_exec_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS))
    return module


def write_session(path: Path, session_id: str, minute: int, *, tool_name: str | None = None) -> None:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    rows = [
        {"timestamp": start.isoformat(), "type": "session_meta", "payload": {"id": session_id, "cwd": f"/work/{session_id}"}},
        {"timestamp": (start + timedelta(seconds=5)).isoformat(), "type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": f"完成任务 {session_id}"}]}},
        {"timestamp": (start + timedelta(seconds=40)).isoformat(), "type": "response_item", "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "先分析再执行。"}]}},
        {"timestamp": (start + timedelta(seconds=80)).isoformat(), "type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "很好，结果正确。"}]}},
        {"timestamp": (start + timedelta(seconds=110)).isoformat(), "type": "response_item", "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "任务完成。"}]}},
    ]
    if tool_name:
        rows.insert(
            3,
            {
                "timestamp": (start + timedelta(seconds=60)).isoformat(),
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": tool_name,
                    "call_id": "call-private-tool",
                    "arguments": "{}",
                },
            },
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def facet_result() -> dict:
    return {
        "underlying_goal": "完成用户明确任务",
        "goal_categories": {"implement_feature": 1},
        "outcome": "fully_achieved",
        "user_satisfaction_counts": {"satisfied": 1},
        "claude_helpfulness": "very_helpful",
        "session_type": "single_task",
        "friction_counts": {},
        "friction_detail": "",
        "primary_success": "correct_code_edits",
        "brief_summary": "用户目标已完成并得到明确认可。",
        "user_instructions_to_codex": ["先分析再执行"],
        "evidence_anchors": ["用户明确确认结果正确"],
    }


def lens_result(lens_id: str) -> dict:
    values = {
        "project_areas": {"areas": [{"name": f"领域 {i}", "project_ids": [f"project-{i:02d}"], "description": "持续完成项目任务。"} for i in range(4)]},
        "interaction_style": {"narrative": "你倾向先明确目标，再验证结果。", "key_pattern": "证据闭环"},
        "what_works": {"intro": "结构化执行最有效。", "impressive_workflows": [{"title": f"工作流 {i}", "description": "从目标到验证形成闭环。"} for i in range(3)]},
        "friction_analysis": {"intro": "主要摩擦来自执行偏差。", "categories": [{"title": f"摩擦模式 {i}", "description": "需要更早验证。", "examples": ["例一", "例二"]} for i in range(3)]},
        "suggestions": {
            "agents_md_additions": [{"addition": f"规则 {i}", "why": "减少偏差。", "prompt_scaffold": "先验证目标。"} for i in range(2)],
            "features_to_try": [{"feature": "Fast mode", "one_liner": "提高吞吐。", "why_for_you": "适合批量分析。", "example_code": "/fast on"} for _ in range(2)],
            "usage_patterns": [{"title": f"模式 {i}", "suggestion": "先定义验收。", "detail": "用明确结果约束执行。", "copyable_prompt": "先列验收标准。"} for i in range(2)],
        },
        "on_the_horizon": {"intro": "可建立持续洞察。", "opportunities": [{"title": f"机会 {i}", "whats_possible": "持续改进协作。", "how_to_try": "先跑一个月。", "copyable_prompt": "比较本月与上月。"} for i in range(3)]},
        "fun_ending": {"headline": "你把验证变成习惯", "detail": "明确结果是协作中最稳定的线索。"},
    }
    return values[lens_id]


def glance_result() -> dict:
    return {
        "whats_working": "结构化目标和结果验证持续有效。",
        "whats_hindering": "执行偏差仍会造成返工。",
        "quick_wins": "把验收标准放到每次任务开头。",
        "ambitious_workflows": "建立按月比较的协作改进循环。",
    }


class FakeExecutor:
    def __init__(self, module, *, fail_once: set[str] | None = None):
        self.module = module
        self.fail_once = set(fail_once or ())
        self.calls: list[tuple[str, str]] = []

    async def execute(self, job, run_dir):
        self.calls.append((job.kind, job.model))
        if job.job_id in self.fail_once:
            self.fail_once.remove(job.job_id)
            return self.module.ExecResult(error="temporary network error")
        if job.kind == "chunk_summary":
            value = {"summary": "完整分块摘要"}
        elif job.kind == "session_facet":
            value = facet_result()
        elif job.kind == "lens":
            value = lens_result(job.lens_id)
        else:
            value = glance_result()
        return self.module.ExecResult(value=value, input_tokens=100, output_tokens=20)


class RunnerReleaseGateTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_runner()

    def test_exec_command_is_ephemeral_schema_bound_fast_and_tool_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.m.ModelJob("j1", "session_facet", "prompt", {"type": "object"}, "gpt-5.6-terra", "medium")
            command, env = self.m.build_exec_command(job, Path(tmp), ["codex"])
            joined = " ".join(command)
            for flag in ("--ephemeral", "--json", "--output-schema", "--output-last-message", "--ignore-user-config", "--ignore-rules"):
                self.assertIn(flag, command)
            self.assertIn("service_tier=\"fast\"", joined)
            self.assertIn("web_search=\"disabled\"", joined)
            for feature in ("shell_tool", "unified_exec", "multi_agent", "browser_use", "computer_use", "apps", "image_generation"):
                self.assertIn(feature, joined)
            self.assertEqual(Path(env["CODEX_HOME"]).resolve(), (Path(tmp) / "exec-home").resolve())

    async def test_large_prompt_drains_stdout_and_stderr_without_pty_backpressure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "fake_codex.py"
            fake.write_text(
                "import json, pathlib, sys\n"
                "args=sys.argv[1:]; prompt=sys.stdin.read()\n"
                "flag='-o' if '-o' in args else '--output-last-message'\n"
                "out=pathlib.Path(args[args.index(flag)+1])\n"
                "for i in range(2500):\n print(json.dumps({'type':'item.completed','i':i,'text':'x'*40}), flush=True); print('e'*80, file=sys.stderr, flush=True)\n"
                "out.write_text(json.dumps({'summary':'ok-'+prompt[-13:]}), encoding='utf-8')\n"
                "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':9,'output_tokens':3}}), flush=True)\n",
                encoding="utf-8",
            )
            executor = self.m.CodexExecExecutor([sys.executable, str(fake)])
            job = self.m.ModelJob("large", "chunk_summary", "中" * 100_000 + "TAIL-COMPLETE", {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False}, "gpt-5.6-luna", "low")
            result = await executor.execute(job, root)
            self.assertIsNone(result.error)
            self.assertEqual(result.value["summary"], "ok-TAIL-COMPLETE")
            self.assertEqual((result.input_tokens, result.output_tokens), (9, 3))

    def test_sqlite_queue_exposes_four_persistent_waves_of_fifty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.m.RunnerStore(Path(tmp) / "run.sqlite3")
            store.create_run("run", {"selected": 200})
            store.enqueue([self.m.ModelJob(f"f{i}", "session_facet", "p", {}, "gpt-5.6-terra", "medium", wave=i // 50) for i in range(200)])
            self.assertEqual({job.wave for job in store.runnable("run", 200)}, {0})
            for job in store.runnable("run", 200):
                store.succeed(job.job_id, {})
            self.assertEqual({job.wave for job in store.runnable("run", 200)}, {1})
            self.assertEqual(store.checkpoint("run")["completed_waves"], 1)
            store.close()

    async def test_pause_immediately_requeues_inflight_and_resume_keeps_successes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            private_tool = "mcp__A1_b2_C3_d4_E5_f6_G7_h8_I9_j0_K1_l2"
            write_session(
                home / "sessions" / "one.jsonl",
                "session-one",
                0,
                tool_name=private_tool,
            )
            prepared = self.m.core.prepare_run(home, max_new_sessions=1)
            prepared["work_items"][0]["material"] += "\nnote:\nnext line"
            serialized_prepared = json.dumps(prepared, ensure_ascii=False, sort_keys=True)
            self.assertNotIn(private_tool, serialized_prepared)
            self.assertIn("[REDACTED_HIGH_ENTROPY]", serialized_prepared)
            snapshot = self.m._persistent_snapshot(prepared)
            store = self.m.RunnerStore(Path(tmp) / "run.sqlite3")
            store.create_run("run", {"selected": 2}, snapshot=snapshot)
            jobs = [self.m.ModelJob(f"j{i}", "session_facet", "p", {}, "gpt-5.6-terra", "medium") for i in range(2)]
            store.enqueue(jobs)
            store.mark_running("j0")
            store.succeed("j0", facet_result())
            store.mark_running("j1")
            store.pause("run")
            reopened = self.m.RunnerStore(Path(tmp) / "run.sqlite3")
            self.assertEqual(reopened.state("j0"), "succeeded")
            self.assertEqual(reopened.state("j1"), "queued")
            self.assertEqual(reopened.run_status("run"), "paused")
            self.assertEqual(
                reopened.snapshot("run")["snapshot_sha256"], snapshot["snapshot_sha256"]
            )
            restored = self.m._restore_snapshot(
                reopened.snapshot("run"), home / "usage-data" / "insights"
            )
            self.assertEqual(restored["job_results"], {})
            self.assertEqual(restored["job_skips"], set())
            self.assertNotIn("source_path", (Path(tmp) / "run.sqlite3").read_bytes().decode("utf-8", "ignore"))
            empty = self.m.RunnerStore(Path(tmp) / "empty.sqlite3")
            self.assertFalse(empty.fail("missing-run", "prepare failed"))
            store.close(); reopened.close()
            empty.close()

    def test_adaptive_pool_grows_to_twelve_and_rate_limit_resets_without_retry_cost(self):
        pool = self.m.AdaptivePool(initial=6, maximum=12)
        for _ in range(120):
            pool.success()
        self.assertEqual(pool.limit, 12)
        retries = pool.retries
        pool.rate_limited(2.5)
        self.assertEqual(pool.limit, 6)
        self.assertEqual(pool.retries, retries)
        self.assertEqual(pool.retry_after, 2.5)
        self.assertFalse(hasattr(pool, "timeout"))

    def test_overall_progress_is_monotonic_and_keeps_future_stages_visible(self):
        frozen = self.m.ProgressPlan(chunks=4, facets=200)
        first = frozen.snapshot({"inventory": 1, "chunk_summary": 2, "session_facet": 10})
        second = frozen.snapshot({"inventory": 1, "chunk_summary": 4, "session_facet": 10})
        self.assertLess(first["percent"], second["percent"])
        self.assertEqual(list(second["stages"]), ["inventory", "chunk_summary", "session_facet", "lens", "at_a_glance", "render", "commit"])
        self.assertLess(second["percent"], 100)
        self.assertFalse(hasattr(frozen, "timeout"))

    async def test_fake_exec_completes_two_hundred_sessions_and_commits_consistent_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            for index in range(200):
                write_session(home / "sessions" / f"{index:03d}.jsonl", f"session-{index:03d}", index)
            config = self.m.RunnerConfig(codex_home=home, max_new_sessions=200, heartbeat_seconds=0, dashboard_seconds=0)
            class AppendingExecutor(FakeExecutor):
                appended = False

                async def execute(inner_self, job, run_dir):
                    if job.kind == "session_facet" and not inner_self.appended:
                        inner_self.appended = True
                        changing = home / "sessions" / "000.jsonl"
                        changing.write_text(changing.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
                    return await super(AppendingExecutor, inner_self).execute(job, run_dir)

            executor = AppendingExecutor(self.m)
            runner = self.m.InsightsRunner(config, executor=executor)
            try:
                result = await runner.run()
                self.assertEqual(result["coverage"]["selected"], 200)
                self.assertEqual(result["coverage"]["analyzed"], 200)
                self.assertTrue(Path(result["report_path"]).exists())
                state = json.loads((home / "usage-data" / "insights" / "state.json").read_text(encoding="utf-8"))
                manifest = json.loads((home / "usage-data" / "insights" / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(len(state["sessions"]), 200)
                self.assertEqual(manifest["state_sha256"], self.m.sha256_file(home / "usage-data" / "insights" / "state.json"))
                self.assertEqual(result["coverage"]["eligible"], result["coverage"]["analyzed"] + result["coverage"]["skipped"] + result["coverage"]["remaining"])
                self.assertEqual(len([call for call in executor.calls if call[0] == "session_facet"]), 200)
                next_run = self.m.core.prepare_run(home, max_new_sessions=1)
                self.assertEqual(next_run["inventory"]["selected"], 1)
            finally:
                runner.store.close()


if __name__ == "__main__":
    unittest.main()
