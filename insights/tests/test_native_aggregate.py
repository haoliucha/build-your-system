"""RED tests for Claude ``/insights``-compatible aggregate material.

The native Claude Code 2.1.228 pipeline keeps deterministic usage aggregation
separate from the compact material sent to its seven semantic lenses.  These
tests preserve that boundary for the Codex adaptation:

``aggregate_usage``
    Combines deterministic session metadata with native-shaped facets.

``build_lens_material``
    Compresses the aggregate and facets to the native 50/20/15 evidence caps.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "insights" / "scripts" / "insights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_native_aggregate", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def meta(
    session_id: str,
    *,
    start_time: str,
    duration_minutes: int,
    user_message_count: int,
    assistant_message_count: int,
    project_path: str,
    first_prompt: str,
    summary: str = "",
    tool_counts: dict[str, int] | None = None,
    languages: dict[str, int] | None = None,
    git_commits: int = 0,
    git_pushes: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    user_interruptions: int = 0,
    user_response_times: list[float] | None = None,
    tool_errors: int = 0,
    tool_error_categories: dict[str, int] | None = None,
    uses_task_agent: bool = False,
    uses_mcp: bool = False,
    uses_web_search: bool = False,
    uses_web_fetch: bool = False,
    lines_added: int = 0,
    lines_removed: int = 0,
    files_modified: int = 0,
    message_hours: list[int] | None = None,
    user_message_timestamps: list[str] | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "transcript_mtime": 1_723_456_789.0,
        "project_path": project_path,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "user_message_count": user_message_count,
        "assistant_message_count": assistant_message_count,
        "tool_counts": tool_counts or {},
        "languages": languages or {},
        "git_commits": git_commits,
        "git_pushes": git_pushes,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "first_prompt": first_prompt,
        "summary": summary,
        "user_interruptions": user_interruptions,
        "user_response_times": user_response_times or [],
        "tool_errors": tool_errors,
        "tool_error_categories": tool_error_categories or {},
        "uses_task_agent": uses_task_agent,
        "uses_mcp": uses_mcp,
        "uses_web_search": uses_web_search,
        "uses_web_fetch": uses_web_fetch,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "files_modified": files_modified,
        "message_hours": message_hours or [],
        "user_message_timestamps": user_message_timestamps or [],
    }


def facet(
    *,
    goal: str,
    goal_categories: dict[str, int],
    outcome: str,
    satisfaction: dict[str, int],
    helpfulness: str,
    session_type: str,
    friction: dict[str, int],
    friction_detail: str,
    primary_success: str,
    brief_summary: str,
    instructions: list[str] | None = None,
) -> dict:
    return {
        "underlying_goal": goal,
        "goal_categories": goal_categories,
        "outcome": outcome,
        "user_satisfaction_counts": satisfaction,
        "claude_helpfulness": helpfulness,
        "session_type": session_type,
        "friction_counts": friction,
        "friction_detail": friction_detail,
        "primary_success": primary_success,
        "brief_summary": brief_summary,
        # This is the one deliberate Codex extension.  Claude 2.1.228 reads
        # ``user_instructions_to_claude`` here but does not populate it in its
        # facet prompt, which makes the native suggestions input ineffective.
        "user_instructions_to_codex": instructions or [],
    }


class NativeAggregateParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_aggregate_usage_matches_native_metrics_and_facet_counts(self):
        metas = [
            meta(
                "aaaaaaaa11111111",
                start_time="2026-08-10T10:00:00Z",
                duration_minutes=90,
                user_message_count=3,
                assistant_message_count=4,
                project_path="project-alpha",
                first_prompt="Repair alpha",
                summary="Deterministic alpha summary",
                tool_counts={"exec_command": 2, "apply_patch": 1},
                languages={"Python": 2},
                git_commits=1,
                input_tokens=100,
                output_tokens=20,
                user_interruptions=1,
                user_response_times=[4.0, 20.0],
                tool_errors=2,
                tool_error_categories={"Command Failed": 1, "File Not Found": 1},
                uses_task_agent=True,
                uses_web_search=True,
                lines_added=10,
                lines_removed=3,
                files_modified=2,
                message_hours=[10, 10, 11],
                user_message_timestamps=["2026-08-10T10:00:00Z", "2026-08-10T10:10:00Z"],
            ),
            meta(
                "bbbbbbbb22222222",
                start_time="2026-08-10T10:05:00Z",
                duration_minutes=30,
                user_message_count=2,
                assistant_message_count=2,
                project_path="project-alpha",
                first_prompt="Implement beta safely",
                tool_counts={"exec_command": 1, "web_search": 1},
                languages={"Python": 1, "TypeScript": 3},
                git_pushes=1,
                input_tokens=200,
                output_tokens=40,
                user_response_times=[8.0],
                tool_errors=1,
                tool_error_categories={"Command Failed": 1},
                uses_mcp=True,
                uses_web_search=True,
                uses_web_fetch=True,
                lines_added=5,
                lines_removed=1,
                files_modified=1,
                message_hours=[10, 21],
                user_message_timestamps=["2026-08-10T10:05:00Z", "2026-08-10T10:07:00Z"],
            ),
            meta(
                "cccccccc33333333",
                start_time="2026-08-12T21:00:00Z",
                duration_minutes=60,
                user_message_count=5,
                assistant_message_count=6,
                project_path="project-beta",
                first_prompt="Research gamma",
                tool_counts={"apply_patch": 2},
                languages={"Rust": 4},
                git_commits=2,
                git_pushes=1,
                input_tokens=300,
                output_tokens=60,
                user_interruptions=2,
                user_response_times=[60.0],
                lines_added=20,
                lines_removed=4,
                files_modified=3,
                message_hours=[21, 21, 21, 21, 21],
                user_message_timestamps=["2026-08-12T21:00:00Z"],
            ),
        ]
        facets = {
            "aaaaaaaa11111111": facet(
                goal="修复 Alpha 的调试缺口",
                goal_categories={"fix_bug": 2, "debug_investigate": 1},
                outcome="fully_achieved",
                satisfaction={"satisfied": 1, "dissatisfied": 1},
                helpfulness="very_helpful",
                session_type="iterative_refinement",
                friction={"tool_failed": 1},
                friction_detail="Alpha 工具失败一次。",
                primary_success="good_debugging",
                brief_summary="Alpha facet summary",
                instructions=["先复现再修复"],
            ),
            "bbbbbbbb22222222": facet(
                goal="实现 Beta 并验证",
                goal_categories={"implement_feature": 1, "write_tests": 1},
                outcome="partially_achieved",
                satisfaction={"dissatisfied": 1},
                helpfulness="moderately_helpful",
                session_type="single_task",
                friction={"tool_failed": 2},
                friction_detail="",
                primary_success="correct_code_edits",
                brief_summary="Beta facet summary",
                instructions=["保留旧接口"],
            ),
            "cccccccc33333333": facet(
                goal="调研 Gamma 方案",
                goal_categories={"understand_codebase": 1},
                outcome="fully_achieved",
                satisfaction={"satisfied": 2},
                helpfulness="very_helpful",
                session_type="exploration",
                friction={"external_issue": 1},
                friction_detail="外部文档不完整。",
                primary_success="none",
                brief_summary="Gamma facet summary",
                instructions=["结论必须带证据"],
            ),
        }

        aggregate = self.m.aggregate_usage(metas, facets)

        self.assertEqual(aggregate["total_sessions"], 3)
        self.assertEqual(aggregate["sessions_with_facets"], 3)
        self.assertEqual(aggregate["date_range"], {"start": "2026-08-10", "end": "2026-08-12"})
        # Native ``total_messages`` means user messages, not both roles.
        self.assertEqual(aggregate["total_messages"], 10)
        self.assertEqual(aggregate["total_duration_hours"], 3.0)
        self.assertEqual(aggregate["total_input_tokens"], 600)
        self.assertEqual(aggregate["total_output_tokens"], 120)
        self.assertEqual(
            aggregate["tool_counts"],
            {"exec_command": 3, "apply_patch": 3, "web_search": 1},
        )
        self.assertEqual(aggregate["languages"], {"Python": 3, "TypeScript": 3, "Rust": 4})
        self.assertEqual(aggregate["git_commits"], 3)
        self.assertEqual(aggregate["git_pushes"], 2)
        self.assertEqual(aggregate["projects"], {"project-alpha": 2, "project-beta": 1})

        self.assertEqual(
            aggregate["goal_categories"],
            {"fix_bug": 2, "debug_investigate": 1, "implement_feature": 1, "write_tests": 1, "understand_codebase": 1},
        )
        self.assertEqual(aggregate["outcomes"], {"fully_achieved": 2, "partially_achieved": 1})
        self.assertEqual(aggregate["satisfaction"], {"satisfied": 3, "dissatisfied": 2})
        self.assertEqual(aggregate["helpfulness"], {"very_helpful": 2, "moderately_helpful": 1})
        self.assertEqual(
            aggregate["session_types"],
            {"iterative_refinement": 1, "single_task": 1, "exploration": 1},
        )
        self.assertEqual(aggregate["friction"], {"tool_failed": 3, "external_issue": 1})
        self.assertEqual(aggregate["success"], {"good_debugging": 1, "correct_code_edits": 1})

        self.assertEqual(
            aggregate["session_summaries"],
            [
                {
                    "id": "aaaaaaaa",
                    "date": "2026-08-10",
                    "summary": "Deterministic alpha summary",
                    "goal": "修复 Alpha 的调试缺口",
                },
                {
                    "id": "bbbbbbbb",
                    "date": "2026-08-10",
                    "summary": "Implement beta safely",
                    "goal": "实现 Beta 并验证",
                },
                {
                    "id": "cccccccc",
                    "date": "2026-08-12",
                    "summary": "Research gamma",
                    "goal": "调研 Gamma 方案",
                },
            ],
        )

        self.assertEqual(aggregate["total_interruptions"], 3)
        self.assertEqual(aggregate["total_tool_errors"], 3)
        self.assertEqual(
            aggregate["tool_error_categories"],
            {"Command Failed": 2, "File Not Found": 1},
        )
        self.assertEqual(aggregate["user_response_times"], [4.0, 20.0, 8.0, 60.0])
        # Claude uses the upper middle element for an even-sized list.
        self.assertEqual(aggregate["median_response_time"], 20.0)
        self.assertEqual(aggregate["avg_response_time"], 23.0)
        self.assertEqual(
            aggregate["response_time_distribution"],
            {
                "2_to_10_seconds": 2,
                "10_to_30_seconds": 1,
                "30_seconds_to_1_minute": 0,
                "1_to_2_minutes": 1,
                "2_to_5_minutes": 0,
                "5_to_15_minutes": 0,
                "over_15_minutes": 0,
            },
        )
        self.assertEqual(aggregate["sessions_using_task_agent"], 1)
        self.assertEqual(aggregate["sessions_using_mcp"], 1)
        self.assertEqual(aggregate["sessions_using_web_search"], 2)
        self.assertEqual(aggregate["sessions_using_web_fetch"], 1)
        self.assertEqual(aggregate["total_lines_added"], 35)
        self.assertEqual(aggregate["total_lines_removed"], 8)
        self.assertEqual(aggregate["total_files_modified"], 6)
        self.assertEqual(aggregate["days_active"], 2)
        self.assertEqual(aggregate["messages_per_day"], 5.0)
        self.assertEqual(aggregate["message_hours"], [10, 10, 11, 10, 21, 21, 21, 21, 21, 21])
        self.assertEqual(
            aggregate["multi_clauding"],
            {"overlap_events": 1, "sessions_involved": 2, "user_messages_during": 3},
        )

    def test_native_summary_and_lens_material_caps_keep_source_order(self):
        metas = []
        facets = {}
        for index in range(55):
            session_id = f"session-{index:08d}"
            metas.append(
                meta(
                    session_id,
                    start_time=f"2026-08-{(index % 20) + 1:02d}T10:00:00Z",
                    duration_minutes=1,
                    user_message_count=2,
                    assistant_message_count=1,
                    project_path="project-cap",
                    first_prompt=f"deterministic-summary-{index:02d}",
                )
            )
            facets[session_id] = facet(
                goal=f"goal-{index:02d}",
                goal_categories={"write_tests": 1},
                outcome="fully_achieved",
                satisfaction={"satisfied": 1},
                helpfulness="very_helpful",
                session_type="single_task",
                friction={"tool_failed": 1},
                friction_detail=f"friction-{index:02d}",
                primary_success="good_debugging",
                brief_summary=f"facet-summary-{index:02d}",
                instructions=[f"instruction-{index:02d}"],
            )

        aggregate = self.m.aggregate_usage(metas, facets)
        self.assertEqual(len(aggregate["session_summaries"]), 50)
        self.assertEqual(aggregate["session_summaries"][0]["summary"], "deterministic-summary-00")
        self.assertEqual(aggregate["session_summaries"][-1]["summary"], "deterministic-summary-49")

        material = self.m.build_lens_material(aggregate, facets)
        self.assertIsInstance(material, str)
        self.assertIn('"summary":"facet-summary-00"', material)
        self.assertIn('"summary":"facet-summary-49"', material)
        self.assertNotIn("facet-summary-50", material)
        self.assertIn("friction-19", material)
        self.assertNotIn("friction-20", material)
        self.assertIn("instruction-14", material)
        self.assertNotIn("instruction-15", material)
        self.assertLess(material.index("facet-summary-00"), material.index("facet-summary-49"))
        self.assertLess(material.index("friction-00"), material.index("friction-19"))
        self.assertLess(material.index("instruction-00"), material.index("instruction-14"))
        self.assertIn('"repeated_instructions"', material)

    def test_warmup_facet_removes_its_matching_meta_and_runtime_keys_keep_summaries(self):
        warmup_meta = meta(
            "warmup-key",
            start_time="2026-08-10T10:00:00Z",
            duration_minutes=2,
            user_message_count=9,
            assistant_message_count=9,
            project_path="project-warmup",
            first_prompt="hello",
            tool_counts={"exec_command": 99},
        )
        useful_meta = meta(
            "useful-key",
            start_time="2026-08-11T10:00:00Z",
            duration_minutes=10,
            user_message_count=3,
            assistant_message_count=4,
            project_path="project-useful",
            first_prompt="repair the cache",
            tool_counts={"apply_patch": 2},
        )
        warmup = facet(
            goal="初始化",
            goal_categories={"warmup_minimal": 1},
            outcome="unclear_from_transcript",
            satisfaction={},
            helpfulness="slightly_helpful",
            session_type="quick_question",
            friction={},
            friction_detail="",
            primary_success="none",
            brief_summary="仅初始化。",
        )
        useful = facet(
            goal="修复缓存",
            goal_categories={"debug_investigate": 1},
            outcome="fully_achieved",
            satisfaction={"satisfied": 1},
            helpfulness="very_helpful",
            session_type="single_task",
            friction={},
            friction_detail="",
            primary_success="good_debugging",
            brief_summary="修复缓存并完成验证。",
        )

        aggregate = self.m.aggregate_usage(
            [warmup_meta, useful_meta],
            {"warmup-key": warmup, "useful-key": useful},
        )

        self.assertEqual(aggregate["total_sessions"], 1)
        self.assertEqual(aggregate["total_messages"], 3)
        self.assertEqual(aggregate["tool_counts"], {"apply_patch": 2})
        self.assertEqual(aggregate["session_summaries"][0]["id"], "useful-k")
        self.assertEqual(aggregate["session_summaries"][0]["goal"], "修复缓存")

        runtime_facet = {**useful, "session_key": "session-1234567890abcdef"}
        runtime_meta = {**useful_meta, "session_id": "", "session_key": "session-1234567890abcdef"}
        runtime = self.m.aggregate_usage([runtime_meta], [runtime_facet])
        self.assertEqual(runtime["session_summaries"][0]["id"], "session-")
        self.assertEqual(runtime["session_summaries"][0]["goal"], "修复缓存")
        self.assertTrue(runtime["session_summaries"][0]["summary"])

        persisted_shape = {
            **runtime_facet,
            "session_meta": {key: value for key, value in runtime_meta.items() if key != "session_key"},
        }
        combined_meta = self.m._combined_metas({}, [persisted_shape])
        self.assertEqual(combined_meta[0]["session_key"], "session-1234567890abcdef")


if __name__ == "__main__":
    unittest.main()
