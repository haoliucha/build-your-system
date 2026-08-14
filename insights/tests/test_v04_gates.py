"""Release gates for the 0.4 primary-session and report-semantic redesign."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "insights" / "scripts"


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_session(
    path: Path,
    session_id: str,
    *,
    source="vscode",
    originator: str = "Codex Desktop",
    forked_from_id: str | None = None,
    minute: int = 0,
) -> None:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    payload = {
        "id": session_id,
        "timestamp": start.isoformat(),
        "cwd": f"/work/{session_id}",
        "source": source,
        "originator": originator,
    }
    if forked_from_id:
        payload["forked_from_id"] = forked_from_id
    rows = [
        {"timestamp": start.isoformat(), "type": "session_meta", "payload": payload},
        {
            "timestamp": (start + timedelta(seconds=5)).isoformat(),
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "请完成任务"}]},
        },
        {
            "timestamp": (start + timedelta(seconds=40)).isoformat(),
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "正在处理"}]},
        },
        {
            "timestamp": (start + timedelta(seconds=75)).isoformat(),
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "结果正确"}]},
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def facet(index: int, project: str, *, friction: bool = False, instruction: str = "") -> dict:
    date = f"2026-08-{(index % 28) + 1:02d}"
    return {
        "session_key": f"session-{index:016x}",
        "date": date,
        "project_alias": project,
        "project_label": project,
        "underlying_goal": f"目标 {index}",
        "goal_categories": {"implement_feature": 1},
        "outcome": "fully_achieved",
        "user_satisfaction_counts": {"satisfied": 1},
        "claude_helpfulness": "very_helpful",
        "session_type": "single_task",
        "friction_counts": {"wrong_approach": 1} if friction else {},
        "friction_detail": f"摩擦 {index}" if friction else "",
        "primary_success": "correct_code_edits",
        "brief_summary": f"{project} 摘要 {index}",
        "user_instructions_to_codex": [instruction] if instruction else [],
        "evidence_anchors": [f"锚点 {index}"],
    }


class V04ReleaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_module("insights.py", "insights_v04_core")
        cls.analysis = load_module("native_analysis.py", "insights_v04_analysis")
        cls.report_module = load_module("native_report.py", "insights_v04_report_labels")

    def test_inventory_selects_only_primary_and_legacy_primary_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            write_session(home / "sessions" / "primary.jsonl", "primary", minute=1)
            short = home / "sessions" / "short-primary.jsonl"
            write_session(short, "short-primary", minute=0)
            rows = short.read_text(encoding="utf-8").splitlines()
            short.write_text("\n".join(rows[:2]) + "\n", encoding="utf-8")
            write_session(
                home / "sessions" / "subagent.jsonl",
                "subagent",
                source={"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}},
                forked_from_id="parent",
                minute=2,
            )
            write_session(
                home / "sessions" / "headless.jsonl",
                "headless",
                source="exec",
                originator="codex_exec",
                minute=3,
            )
            write_session(
                home / "sessions" / "codex-exec.jsonl",
                "codex-exec",
                source="codex_exec",
                originator="Codex CLI",
                minute=4,
            )
            write_session(
                home / "sessions" / "automation.jsonl",
                "automation",
                source="automation",
                originator="Codex Scheduled",
                minute=5,
            )

            found, stats = self.core.discover_sessions(home, include_stats=True)

            self.assertEqual([item["meta"]["session_id"] for item in found], ["primary"])
            self.assertEqual(stats.get("primary"), 0)
            self.assertEqual(stats.get("legacy_primary"), 2)
            self.assertEqual(stats.get("subagent"), 1)
            self.assertEqual(stats.get("headless"), 2)
            self.assertEqual(stats.get("automation"), 1)
            self.assertEqual(stats["eligible"], 1)
            self.assertEqual(stats["primary_total"], 2)
            self.assertEqual(stats["primary_eligible"], 1)

    def test_facet_and_friction_lens_use_closed_machine_enums_but_localized_titles(self):
        valid = facet(1, "project-a")
        valid = {
            key: value
            for key, value in valid.items()
            if key in self.analysis.NATIVE_FACET_FIELDS
            or key in self.analysis.FACET_EXTENSION_FIELDS
        }
        self.analysis.validate_native_facet(valid)
        invalid = {**valid, "goal_categories": {"coding": 1}}
        with self.assertRaises(self.analysis.FacetValidationError):
            self.analysis.validate_native_facet(invalid)

        friction_schema = self.analysis.LENS_SCHEMAS["friction_analysis"]
        item_required = friction_schema["properties"]["categories"]["items"]["required"]
        self.assertIn("title", item_required)
        self.assertNotIn("category", item_required)

    def test_every_closed_enum_has_a_chinese_report_label(self):
        enums = (
            set(self.analysis.GOAL_CATEGORIES)
            | set(self.analysis.SATISFACTION_SIGNALS)
            | set(self.analysis.FRICTION_TYPES)
        )
        self.assertFalse(enums - set(self.report_module._LABELS_ZH))

    def test_lens_evidence_is_stratified_and_records_projects_and_repeated_instructions(self):
        facets = [facet(index, "project-a", friction=index % 9 == 0, instruction="先给证据") for index in range(50)]
        facets.extend(facet(index, "project-b", friction=True, instruction="先给证据") for index in range(50, 60))
        aggregate = {
            "total_sessions": 60,
            "sessions_with_facets": 60,
            "projects": {"project-a": 50, "project-b": 10},
            "date_range": {"start": "2026-08-01", "end": "2026-08-28"},
        }

        self.assertTrue(hasattr(self.core, "build_lens_evidence"))
        evidence = self.core.build_lens_evidence(aggregate, facets, coverage={"remaining": 0})

        self.assertEqual(evidence["project_distribution"], {"project-a": 50, "project-b": 10})
        summaries = evidence["representative_summaries"]
        self.assertEqual(len(summaries), 50)
        self.assertTrue(any(item["project_id"] == "project-b" for item in summaries))
        repeated = evidence["repeated_instructions"]
        self.assertEqual(repeated[0]["text"], "先给证据")
        self.assertEqual(repeated[0]["count"], 60)
        self.assertGreaterEqual(len(repeated[0]["dates"]), 1)

    def test_project_counts_are_helper_computed_and_uncovered_projects_roll_up(self):
        raw = {
            "areas": [
                {"name": "插件系统", "project_ids": ["project-a"], "description": "插件工作。"},
                {"name": "内容系统", "project_ids": ["project-b"], "description": "内容工作。"},
            ]
        }
        self.assertTrue(hasattr(self.analysis, "finalize_project_areas"))
        finalized = self.analysis.finalize_project_areas(
            raw,
            {"project-a": 7, "project-b": 3, "project-c": 2},
            language="zh-CN",
        )
        self.assertEqual(finalized["areas"][0]["session_count"], 7)
        self.assertEqual(finalized["areas"][1]["session_count"], 3)
        self.assertEqual(finalized["areas"][2], {"name": "其他项目", "session_count": 2, "description": "未归入上述领域的主会话。"})

    def test_report_is_flat_claude_style_with_one_line_header_and_no_machine_titles(self):
        aggregate = {
            "total_sessions": 12,
            "sessions_with_facets": 10,
            "date_range": {"start": "2026-08-01", "end": "2026-08-12"},
            "total_messages": 42,
            "lines_added": 320,
            "lines_removed": 75,
            "files_modified": 18,
            "days_active": 6,
            "messages_per_day": 7.0,
            "goal_categories": {"implement_feature": 8},
            "tool_counts": {"exec": 12},
            "languages": {"Python": 8},
            "session_types": {"single_task": 10},
            "response_time_distribution": {"2_to_10_seconds": 5},
            "multi_clauding": {"overlap_events": 1, "sessions_involved": 2, "user_messages_during": 3},
            "message_hours": {"9": 7},
            "tool_error_categories": {},
            "success": {"correct_code_edits": 8},
            "outcomes": {"fully_achieved": 8},
            "friction": {"wrong_approach": 2},
            "satisfaction": {"satisfied": 7},
        }
        lenses = {
            "project_areas": {"areas": [{"name": "插件系统", "session_count": 10, "description": "统一插件。"}]},
            "interaction_style": {"narrative": "第一段。\n\n第二段包含 **证据闭环**。", "key_pattern": "先验收"},
            "what_works": {"intro": "有效。", "impressive_workflows": [{"title": "工作流", "description": "闭环。"}]},
            "friction_analysis": {"intro": "仍有摩擦。", "categories": [{"title": "过早宣称完成", "description": "尚未验证。", "examples": ["例一", "例二"]}]},
            "suggestions": {"agents_md_additions": [], "features_to_try": [], "usage_patterns": []},
            "on_the_horizon": {"intro": "未来。", "opportunities": []},
            "fun_ending": {"headline": "难忘", "detail": "重视证据。"},
        }
        glance = {
            "whats_working": "有效做法。",
            "whats_hindering": "主要阻碍。",
            "quick_wins": "快速改进。",
            "ambitious_workflows": "挑战工作流。",
        }
        report = self.core.render_report(
            [],
            aggregate=aggregate,
            lenses=lenses,
            at_a_glance=glance,
            coverage={"primary_total": 12, "analyzed": 10, "remaining": 2},
        )

        self.assertNotIn('class="sidebar"', report)
        self.assertIn('class="report-meta"', report)
        self.assertIn("42 条消息，来自 10 个会话（共 12 个）｜2026-08-01 至 2026-08-12", report)
        self.assertIn("max-width:800px", report.replace(" ", ""))
        self.assertLess(report.index('class="glance"'), report.index('<nav'))
        self.assertLess(report.index('<nav'), report.index('class="stats"'))
        self.assertIn('class="lead">第一段。</p><p>第二段包含 <strong>证据闭环</strong>。</p>', report)
        self.assertNotIn("codex_failures", report)
        self.assertNotIn("coverage-warning", report)

    def test_report_comparator_api_exists_for_pre_200_release_gate(self):
        self.assertTrue(
            hasattr(self.core, "compare_report_structure"),
            "Gate 1/3 need a read-only Claude report comparator before a 200-session run",
        )

    def test_report_comparator_extracts_claude_chart_titles_in_native_order(self):
        sections = ("section-work", "section-usage", "section-wins", "section-friction", "section-features", "section-patterns", "section-horizon")
        pre_counts = {"section-features": 4, "section-patterns": 2, "section-horizon": 3}
        candidate = """<style>.report{max-width:800px}h1{font-size:32px}.x{border-radius:8px}</style>
        <h1>报告</h1><p class="report-meta">42 条消息，来自 10 个会话（共 12 个）｜2026-08-01 至 2026-08-12</p>
        <div class="glance"><div class="glance-item">有效做法足够具体</div><div class="glance-item">主要阻碍可以行动</div><div class="glance-item">快速改进包含步骤</div><div class="glance-item">挑战工作流包含证据</div></div>
        """ + '<nav class="top-nav">' + "".join(f'<a href="#{section}">{section}</a>' for section in sections) + '</nav>'
        candidate += '<div class="stats">' + '<div class="stat">1</div>' * 5 + '</div>'
        candidate += "".join(
            f'<section id="{section}"><h2>{section}</h2><p>{"具体证据与行动建议" * 12}</p>{"<pre>行动</pre>" * pre_counts.get(section, 0)}</section>'
            for section in sections
        ) + "".join(
            f'<section data-chart="{chart}"></section>'
            for chart in ("goals", "tools", "languages", "session-types", "response-time", "multi-clauding", "message-hours", "tool-errors", "successes", "outcomes", "friction", "satisfaction")
        ) + "<p>叙事</p>" * 20
        reference_titles = (
            "What You Wanted", "Top Tools Used", "Languages", "Session Types",
            "User Response Time Distribution", "Multi-Clauding (Parallel Sessions)",
            "Time of Day", "Tool Errors Encountered",
            "What Helped Most (Claude's Capabilities)", "Outcomes",
            "Primary Friction Types", "Inferred Satisfaction (model-estimated)",
        )
        reference = """<style>.report{max-width:800px}h1{font-size:32px}.x{border-radius:8px}</style><h1>Claude</h1>"""
        reference += "".join(
            f'<h2 id="{section}">{section}</h2>'
            for section in ("section-work", "section-usage", "section-wins", "section-friction", "section-features", "section-patterns", "section-horizon")
        )
        reference += "".join(f'<div class="chart-title">{title}</div>' for title in reference_titles)
        reference += "x" * 1200
        comparison = self.core.compare_report_structure(candidate, reference)
        self.assertEqual(comparison["reference"]["charts"], [
            "goals", "tools", "languages", "session-types", "response-time",
            "multi-clauding", "message-hours", "tool-errors", "successes",
            "outcomes", "friction", "satisfaction",
        ])
        self.assertTrue(next(item for item in comparison["checks"] if item["name"] == "reference-twelve-chart-order")["passed"])

    def test_report_metrics_allow_real_tool_names_but_flag_untranslated_semantic_enums(self):
        allowed = self.report_module._report_metrics(
            '<span class="chart-label">exec_command</span>'
        )
        blocked = self.report_module._report_metrics(
            '<span class="chart-label">wrong_approach</span>'
        )
        self.assertEqual(allowed["machine_chart_labels"], [])
        self.assertEqual(blocked["machine_chart_labels"], ["wrong_approach"])

    def test_report_metrics_flag_repeated_coverage_disclaimers_outside_method_footer(self):
        metrics = self.report_module._report_metrics(
            '<section><p>语义结论仅覆盖已分析的 171 个会话，仍有 29 个会话未分析。</p></section>'
            '<footer class="method"><p>尚待处理 29</p></footer>'
        )
        self.assertEqual(metrics["coverage_disclaimers"], 1)

    def test_report_metrics_require_context_and_share_for_every_chart(self):
        rich = self.report_module._report_metrics(
            "".join(
                f'<section data-chart="chart-{index}"><p class="chart-context">口径</p>'
                f'<span class="chart-share">50%</span></section>'
                for index in range(12)
            )
        )
        rough = self.report_module._report_metrics(
            '<section data-chart="friction"><span class="chart-label">方案错误</span></section>'
        )
        self.assertEqual(rich["chart_contexts"], 12)
        self.assertEqual(rich["chart_shares"], 12)
        self.assertEqual(rough["chart_contexts"], 0)
        self.assertEqual(rough["chart_shares"], 0)

    def test_preview_gate_writes_only_below_versioned_preview_directory(self):
        gate_path = SCRIPTS / "gates.py"
        self.assertTrue(gate_path.exists(), "Gate runner must exist before the real preview")
        gates = load_module("gates.py", "insights_v04_gates")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            output = home / "usage-data" / "insights"
            output.mkdir(parents=True)
            official = {
                "report.html": b"old-report",
                "state.json": b"old-state",
                "manifest.json": b"old-manifest",
            }
            for name, content in official.items():
                (output / name).write_bytes(content)

            result = gates.write_preview_bundle(
                home,
                version="0.4.0",
                report_html="<html lang=\"zh-CN\">preview</html>",
                lenses={"project_areas": {"areas": []}},
                at_a_glance={"whats_working": "ok"},
                comparison={"passed": True},
            )

            self.assertEqual(Path(result["report_path"]).resolve(), (output / "previews" / "0.4.0" / "report.html").resolve())
            for name, content in official.items():
                self.assertEqual((output / name).read_bytes(), content)

    def test_lens_preview_cache_is_frozen_across_renderer_only_iterations(self):
        gates = load_module("gates.py", "insights_v04_cache_policy")
        cached = {
            "lens_prompt_version": self.core.LENS_PROMPT_VERSION,
            "evidence_sha256": "frozen-evidence",
            "aggregate": {"total_messages": 42},
            "coverage": {"analyzed": 10, "primary_total": 12},
            "facets": [],
            "lenses": {"project_areas": {"areas": []}},
            "at_a_glance": {"whats_working": "ok"},
        }
        self.assertTrue(gates._valid_preview_cache(cached, lens_prompt_version=self.core.LENS_PROMPT_VERSION))
        self.assertFalse(gates._valid_preview_cache(
            {**cached, "lens_prompt_version": "changed"},
            lens_prompt_version=self.core.LENS_PROMPT_VERSION,
        ))

    def test_facet_probe_uses_deterministic_user_turns_after_long_session_summarization(self):
        gates = load_module("gates.py", "insights_v04_probe_semantics")
        model_facet = facet(1, "project-a")
        model_facet["goal_categories"] = {
            "configure_system": 8,
            "debug_investigate": 8,
        }
        model_facet["user_satisfaction_counts"] = {}
        self.assertEqual(
            gates._facet_probe_checks(
                "[Long session - 10 parts summarized]\n\n摘要不再包含 User: 标签。",
                model_facet,
                user_turns=12,
            ),
            [],
        )

    def test_released_runner_drops_development_receipt_but_validator_stays_hash_bound(self):
        runner = load_module("runner.py", "insights_v04_receipt")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            preview = home / "usage-data" / "insights" / "previews" / "0.4.0"
            preview.mkdir(parents=True)
            report = preview / "report.html"; report.write_text("preview", encoding="utf-8")
            comparison = preview / "comparison.json"; comparison.write_text('{"passed":true}', encoding="utf-8")
            receipt = preview / "release-receipt.json"
            receipt.write_text(json.dumps({
                "user_confirmed": True,
                "preview_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                "comparison_sha256": hashlib.sha256(comparison.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            self.assertFalse(runner._development_receipt_required(200))
            self.assertTrue(runner._validate_release_receipt(receipt, codex_home=home))
            report.write_text("changed", encoding="utf-8")
            self.assertFalse(runner._validate_release_receipt(receipt, codex_home=home))


if __name__ == "__main__":
    unittest.main()
