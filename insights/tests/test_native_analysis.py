"""Claude Code 2.1.228 meaning-parity tests for the analysis pipeline.

These tests intentionally describe the observable analysis contract rather
than Claude's private implementation details.  The Codex adaptation may keep
stronger cache and privacy guarantees, but its semantic pipeline must remain:
native-like session facets -> seven distinct lenses -> At-a-Glance -> report.
"""

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
    spec = importlib.util.spec_from_file_location("insights_native_analysis", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_long_jsonl(path: Path) -> None:
    """Write a qualifying session whose normalized transcript exceeds 30k."""

    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": start.isoformat().replace("+00:00", "Z"),
            "type": "session_meta",
            "payload": {
                "id": "long-native-analysis",
                "timestamp": start.isoformat().replace("+00:00", "Z"),
                "cwd": "/work/native-analysis",
            },
        }
    ]
    # 50 user + 50 assistant records normalize to about 40k characters after
    # Claude's 500/300 per-message caps, while still spanning over a minute.
    for index in range(100):
        role = "user" if index % 2 == 0 else "assistant"
        marker = f"event-{index:03d}-"
        text = marker + (("U" if role == "user" else "A") * 700)
        rows.append(
            {
                "timestamp": (start + timedelta(seconds=3 * (index + 1))).isoformat().replace("+00:00", "Z"),
                "type": "response_item",
                "payload": {"role": role, "content": [{"type": "input_text", "text": text}]},
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def native_facet() -> dict:
    return {
        "underlying_goal": "修复失败的缓存事务并验证回滚",
        "goal_categories": {"debugging": 1, "testing": 1},
        "outcome": "fully_achieved",
        "user_satisfaction_counts": {"likely_satisfied": 1, "dissatisfied": 1},
        "claude_helpfulness": "very_helpful",
        "session_type": "iterative_refinement",
        "friction_counts": {"buggy_code": 1, "tool_failed": 1},
        "friction_detail": "一次测试失败暴露了事务回滚缺口，随后修复并复测。",
        "primary_success": "good_debugging",
        "brief_summary": "定位缓存事务缺口，补上回滚并用失败注入验证。",
    }


def native_lens_results() -> dict[str, dict]:
    return {
        "project_areas": {
            "areas": [
                {"name": f"领域 {index}", "session_count": index + 1, "description": "具体项目工作。"}
                for index in range(4)
            ]
        },
        "interaction_style": {
            "narrative": "用户偏好先对齐目标，再用测试闭环验证。",
            "key_pattern": "明确验收条件后持续迭代。",
        },
        "what_works": {
            "intro": "带评分器和失败注入的任务效果最好。",
            "impressive_workflows": [
                {"title": f"工作流 {index}", "description": "先验证，再修订，最后复评。"}
                for index in range(3)
            ],
        },
        "friction_analysis": {
            "intro": "主要摩擦来自目标误读、工具失败和过度改动。",
            "categories": [
                {
                    "category": f"摩擦 {index}",
                    "description": "可从会话证据中定位的根因。",
                    "examples": ["例子一", "例子二"],
                }
                for index in range(3)
            ],
        },
        "suggestions": {
            "agents_md_additions": [
                {"addition": f"固定验收命令 {index}", "why": "减少口径漂移", "prompt_scaffold": "先运行验收命令。"}
                for index in range(2)
            ],
            "features_to_try": [
                {"feature": f"子代理 {index}", "one_liner": "并行独立分析", "why_for_you": "提高吞吐", "example_code": "$skill"}
                for index in range(2)
            ],
            "usage_patterns": [
                {"title": f"评分循环 {index}", "suggestion": "每轮只改最弱项", "detail": "避免盲目重写", "copyable_prompt": "评分后修订最弱项。"}
                for index in range(2)
            ],
        },
        "on_the_horizon": {
            "intro": "未来三到六个月可把复盘变成长期反馈系统。",
            "opportunities": [
                {"title": f"机会 {index}", "whats_possible": "形成复利资产", "how_to_try": "从小批量开始", "copyable_prompt": "分析并验证。"}
                for index in range(3)
            ],
        },
        "fun_ending": {"headline": "你把 Codex 当作可验证的搭档", "detail": "最鲜明的特点是反复要求证据闭环。"},
    }


class NativeAnalysisParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_normalization_caps_messages_and_keeps_tool_names(self):
        session = {
            "session_key": "session-1111111111111111",
            "start": "2026-08-12T00:00:00Z",
            "cwd": "/private/project",
            "events": [
                {"timestamp": "1", "role": "user", "text": "U" * 550},
                {"timestamp": "2", "role": "assistant", "text": "A" * 350},
                {"timestamp": "3", "role": "tool", "name": "Read", "text": "private tool output"},
            ],
        }

        normalized = self.m.normalize_session(session)

        self.assertIn("U" * 500, normalized)
        self.assertNotIn("U" * 501, normalized)
        self.assertIn("A" * 300, normalized)
        self.assertNotIn("A" * 301, normalized)
        self.assertIn("[Tool: Read]", normalized)
        self.assertNotIn("private tool output", normalized)

    def test_over_30k_text_is_split_at_25k_without_losing_an_oversized_event(self):
        text = "".join(f"<{index:05d}>" for index in range(8_000))
        self.assertGreater(len(text), 30_000)

        chunks = self.m.split_analysis_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= 25_000 for chunk in chunks))
        self.assertEqual("".join(chunks), text)
        self.assertTrue(chunks[-1].endswith("<07999>"))

    def test_chunk_jobs_gate_facet_and_reduce_summaries_in_source_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "codex-home"
            write_long_jsonl(home / "sessions" / "long.jsonl")
            pending: dict[str, dict] = {}
            prepared = self.m.handle_request(
                {"op": "prepare", "codex_home": str(home), "max_new_sessions": 1}, pending
            )["result"]
            run_id = prepared["run_id"]
            self.assertEqual(prepared["next"]["op"], "next_jobs")

            first = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]
            chunk_jobs = first["jobs"]
            self.assertGreater(len(chunk_jobs), 1)
            self.assertTrue(all(job["kind"] == "chunk_summary" for job in chunk_jobs))

            # A partial, out-of-order submission is accepted, but may not make
            # a facet job visible until every source chunk has a summary.
            last_job = chunk_jobs[-1]
            self.m.handle_request(
                {
                    "op": "submit_jobs",
                    "run_id": run_id,
                    "results": [{"job_id": last_job["job_id"], "result": {"summary": "summary-last"}}],
                },
                pending,
            )
            blocked = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]
            self.assertTrue(blocked["jobs"])
            self.assertTrue(all(job["kind"] == "chunk_summary" for job in blocked["jobs"]))

            remaining = [job for job in chunk_jobs if job["job_id"] != last_job["job_id"]]
            results = [
                {"job_id": job["job_id"], "result": {"summary": f"summary-{job['chunk_index']}"}}
                for job in reversed(remaining)
            ]
            self.m.handle_request({"op": "submit_jobs", "run_id": run_id, "results": results}, pending)
            reduced = self.m.handle_request({"op": "next_jobs", "run_id": run_id}, pending)["result"]
            self.assertEqual(len(reduced["jobs"]), 1)
            facet_job = reduced["jobs"][0]
            self.assertEqual(facet_job["kind"], "session_facet")
            material = facet_job["material"]
            expected = [f"summary-{job['chunk_index']}" for job in chunk_jobs[:-1]] + ["summary-last"]
            positions = [material.index(summary) for summary in expected]
            self.assertEqual(positions, sorted(positions))

    def test_native_facet_uses_count_maps_and_native_model_field_names(self):
        facet = native_facet()
        self.assertEqual(self.m.validate_native_facet(facet), facet)

        wrong_categories = {**facet, "goal_categories": ["debugging", "testing"]}
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_native_facet(wrong_categories)
        wrong_helpfulness = dict(facet)
        wrong_helpfulness["helpfulness"] = wrong_helpfulness.pop("claude_helpfulness")
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_native_facet(wrong_helpfulness)
        wrong_success = {**facet, "primary_success": "made_everything_better"}
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_native_facet(wrong_success)
        for field in ("outcome", "claude_helpfulness", "session_type", "primary_success"):
            with self.subTest(field=field), self.assertRaises(self.m.FacetValidationError):
                self.m.validate_native_facet({**facet, field: {"unexpected": "object"}})
        copied_transcript = {**facet, "brief_summary": "原始正文" * 1_000}
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_native_facet(copied_transcript)
        too_many_anchors = {**facet, "evidence_anchors": [f"anchor-{index}" for index in range(21)]}
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_native_facet(too_many_anchors)

    def test_facet_prompt_counts_only_explicit_user_goals_and_signals(self):
        prompt = self.m.build_facet_prompt("a redacted, normalized session", language="zh-CN")
        lowered = prompt.casefold()
        for phrase in (
            "explicit user goals",
            "autonomous exploration",
            "explicit satisfaction",
            "warmup_minimal",
        ):
            self.assertIn(phrase, lowered)

        for category in (
            "happy",
            "satisfied",
            "likely_satisfied",
            "dissatisfied",
            "frustrated",
            "misunderstood_request",
            "wrong_approach",
            "buggy_code",
            "user_rejected_action",
            "excessive_changes",
        ):
            self.assertIn(category, prompt)
        self.assertIn("OUTPUT LANGUAGE: zh-CN", prompt)
        self.assertIn("human-readable", prompt)

        warmup = {**native_facet(), "goal_categories": {"warmup_minimal": 1}, "session_type": "quick_question"}
        self.assertEqual(self.m.validate_native_facet(warmup), warmup)
        wrong_warmup = {**warmup, "session_type": "warmup_minimal"}
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_native_facet(wrong_warmup)
        self.assertNotIn("warmup_minimal", self.m.SESSION_TYPES)

    def test_all_model_prompts_receive_the_requested_output_language(self):
        chunk = self.m.build_chunk_summary_prompt("chunk", language="en-US")
        facet = self.m.build_facet_prompt("session", language="en-US")
        lenses = self.m.build_lens_jobs({"aggregate": "material"}, language="en-US")
        glance = self.m.build_at_a_glance_job(
            {"aggregate": "material"}, native_lens_results(), language="en-US"
        )

        for prompt in [chunk, facet, *(job["prompt"] for job in lenses), glance["prompt"]]:
            self.assertIn("OUTPUT LANGUAGE: en-US", prompt)
            self.assertIn("human-readable", prompt)
        for prompt in [*(job["prompt"] for job in lenses), glance["prompt"]]:
            self.assertIn("coverage", prompt.casefold())

    def test_seven_lenses_are_distinct_single_jobs_with_native_like_schemas(self):
        expected_required = {
            "project_areas": {"areas"},
            "interaction_style": {"narrative", "key_pattern"},
            "what_works": {"intro", "impressive_workflows"},
            "friction_analysis": {"intro", "categories"},
            "suggestions": {"agents_md_additions", "features_to_try", "usage_patterns"},
            "on_the_horizon": {"intro", "opportunities"},
            "fun_ending": {"headline", "detail"},
        }
        jobs = self.m.build_lens_jobs({"aggregate": "compressed session material"}, language="zh-CN")

        self.assertEqual(len(jobs), 7)
        self.assertEqual({job["lens_id"] for job in jobs}, set(expected_required))
        self.assertEqual(len({job["lens_id"] for job in jobs}), len(jobs))
        self.assertEqual(len({job["prompt"] for job in jobs}), len(jobs))
        for job in jobs:
            self.assertEqual(set(job["schema"]["required"]), expected_required[job["lens_id"]])
            self.assertIn("OUTPUT LANGUAGE: zh-CN", job["prompt"])
        suggestions_job = next(job for job in jobs if job["lens_id"] == "suggestions")
        self.assertIn("2-3", suggestions_job["prompt"])
        self.assertIn("Codex capability reference", suggestions_job["prompt"])
        suggestions = native_lens_results()["suggestions"]
        self.assertEqual(self.m.validate_lens_result("suggestions", suggestions), suggestions)
        for field in ("agents_md_additions", "features_to_try", "usage_patterns"):
            too_few = {**suggestions, field: suggestions[field][:1]}
            with self.assertRaises(self.m.FacetValidationError):
                self.m.validate_lens_result("suggestions", too_few)
        forbidden = " ".join(job["lens_id"] for job in jobs).casefold()
        for legacy_stage in ("repeat", "contradiction", "evolution", "quality"):
            self.assertNotIn(legacy_stage, forbidden)

    def test_at_a_glance_waits_for_all_lenses_and_has_four_native_fields(self):
        completed = native_lens_results()
        incomplete = dict(completed)
        incomplete.pop("fun_ending")
        with self.assertRaises(self.m.InsightsError):
            self.m.build_at_a_glance_job({"aggregate": "material"}, incomplete)

        job = self.m.build_at_a_glance_job({"aggregate": "material"}, completed)
        self.assertEqual(job["kind"], "at_a_glance")
        self.assertEqual(
            set(job["schema"]["required"]),
            {"whats_working", "whats_hindering", "quick_wins", "ambitious_workflows"},
        )
        value = {
            "whats_working": "验证闭环稳定有效。",
            "whats_hindering": "工具失败与目标误读造成返工。",
            "quick_wins": "把验收命令写入 AGENTS.md。",
            "ambitious_workflows": "把跨会话复盘变成长期反馈系统。",
        }
        self.assertEqual(self.m.validate_at_a_glance(value), value)
        value.pop("quick_wins")
        with self.assertRaises(self.m.FacetValidationError):
            self.m.validate_at_a_glance(value)


if __name__ == "__main__":
    unittest.main()
