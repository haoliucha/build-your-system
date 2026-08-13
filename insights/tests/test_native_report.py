import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "insights" / "scripts" / "insights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("insights_native_report", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def aggregate_fixture():
    """A compact instance of Claude Code 2.1.228's report material."""
    return {
        "total_sessions": 12,
        "sessions_with_facets": 10,
        "date_range": {"start": "2026-08-01", "end": "2026-08-12"},
        "total_messages": 42,
        "total_duration_hours": 9.5,
        "total_input_tokens": 120_000,
        "total_output_tokens": 30_000,
        "tool_counts": {"exec": 52, "apply_patch": 11},
        "languages": {"Python": 43, "TypeScript": 7},
        "git_commits": 4,
        "git_pushes": 2,
        "projects": {"build-your-system": 7, "haoliucha": 3},
        "goal_categories": {"coding": 61, "research": 8},
        "outcomes": {"fully_achieved": 41, "partially_achieved": 3},
        "satisfaction": {"positive": 33, "negative": 2, "correction": 4},
        "helpfulness": {"very_helpful": 8, "moderately_helpful": 2},
        "session_types": {"single_task": 34, "iterative_refinement": 6},
        "friction": {"tool_failed": 22, "wrong_approach": 5},
        "success": {"good_debugging": 39, "correct_code_edits": 8},
        "session_summaries": [],
        "interruptions": 3,
        "tool_errors": 18,
        "tool_error_categories": {"command_failed": 18, "user_rejected": 2},
        "response_time_distribution": {
            "2_to_10_seconds": 25,
            "10_to_30_seconds": 6,
            "30_seconds_to_1_minute": 4,
            "1_to_2_minutes": 3,
            "2_to_5_minutes": 2,
            "5_to_15_minutes": 1,
            "over_15_minutes": 1,
        },
        "response_time_median_seconds": 14,
        "response_time_average_seconds": 27,
        "sessions_using_task_agent": 5,
        "sessions_using_mcp": 2,
        "sessions_using_web_search": 3,
        "sessions_using_web_fetch": 1,
        "lines_added": 320,
        "lines_removed": 75,
        "files_modified": 18,
        "days_active": 6,
        "messages_per_day": 7.0,
        "message_hours": {"09": 27, "21": 9},
        "multi_clauding": {"overlap_events": 16, "sessions_involved": 3, "user_messages_during": 20},
    }


def lenses_fixture():
    """The seven independent native lenses, adapted only for Codex terminology."""
    return {
        "project_areas": {
            "areas": [
                {
                    "name": "插件系统",
                    "session_count": 7,
                    "description": "统一 Claude Code 与 Codex 的插件真源。",
                }
            ]
        },
        "interaction_style": {
            "narrative": "你倾向先对齐语义，再进入实现，并要求用真实测试验收。",
            "key_pattern": "先看证据，再改代码",
        },
        "what_works": {
            "intro": "有验收条件的长任务最容易产生复利。",
            "impressive_workflows": [
                {
                    "title": "证据驱动重构",
                    "description": "先反编译事实，再用测试固定行为。",
                }
            ],
        },
        "friction_analysis": {
            "intro": "主要摩擦来自过早抽象，而不是工作量本身。",
            "categories": [
                {
                    "category": "方案偏航",
                    "description": "实现了安全流程，但没有复刻原生命令语义。",
                    "examples": ["把跨会话模式误当作原生主流程", "报告章节偏离原生结构"],
                }
            ],
        },
        "suggestions": {
            "agents_md_additions": [
                {
                    "addition": "复杂复刻任务先建立原生行为矩阵。",
                    "why": "避免把自主设计误写成上游事实。",
                    "prompt_scaffold": "对比命令描述、数据流、模型提示与报告输出。",
                }
            ],
            "features_to_try": [
                {
                    "feature": "Codex 子代理",
                    "one_liner": "把七个互不依赖的 lens 并行分析。",
                    "why_for_you": "能缩短额度冲刺中的墙钟时间。",
                    "example_code": "$insights MAX_NEW_SESSIONS=10",
                }
            ],
            "usage_patterns": [
                {
                    "title": "先定义评分器",
                    "suggestion": "每个长任务先写可判定验收条件。",
                    "detail": "完成一轮后只修订最弱项，避免无终点改写。",
                    "copyable_prompt": "先列出验收条件，再开始实现。",
                }
            ],
        },
        "on_the_horizon": {
            "intro": "接下来可以把复盘转成持续改进系统。",
            "opportunities": [
                {
                    "title": "跨仓库质量雷达",
                    "whats_possible": "自动发现多个项目反复出现的失败模式。",
                    "how_to_try": "先用三个仓库做只读审计并比较回归证据。",
                    "copyable_prompt": "扫描三个仓库，按风险和可验证性排序。",
                }
            ],
        },
        "fun_ending": {
            "headline": "你不是在和 Codex 聊天，而是在训练一套工作系统。",
            "detail": "最难忘的时刻，是你发现“安全”并不等于“复刻正确”。",
        },
    }


def at_a_glance_fixture():
    return {
        "whats_working": "先定义验收条件，复杂任务完成率明显更高。",
        "whats_hindering": "工具失败后重复尝试，造成不必要返工。",
        "quick_wins": "把常用约束写入 AGENTS.md。",
        "ambitious_workflows": "建立跨仓库回归审计流水线。",
    }


def render(module, *, aggregate=None, lenses=None, at_a_glance=None, language=None, coverage=None):
    kwargs = {
        "aggregate": aggregate or aggregate_fixture(),
        "lenses": lenses or lenses_fixture(),
        "at_a_glance": at_a_glance or at_a_glance_fixture(),
        "coverage": coverage or {"eligible": 12, "cached": 2, "selected": 10, "remaining": 0},
    }
    if language is not None:
        kwargs["language"] = language
    return module.render_report([], **kwargs)


class NativeReportParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_at_a_glance_and_native_five_headline_stats(self):
        report = render(self.m)

        self.assertIn("一目了然", report)
        for title, value in (
            ("做得好的地方", "先定义验收条件，复杂任务完成率明显更高。"),
            ("阻碍你的地方", "工具失败后重复尝试，造成不必要返工。"),
            ("快速改进", "把常用约束写入 AGENTS.md。"),
            ("值得挑战的工作流", "建立跨仓库回归审计流水线。"),
        ):
            self.assertIn(title, report)
            self.assertIn(value, report)

        # Claude Code's headline row has these five meanings. Tokens and session
        # counts may appear in methods, but must not replace this row.
        for label, value in (
            ("用户消息", "42"),
            ("代码行", "+320 / -75"),
            ("文件", "18"),
            ("活跃天数", "6"),
            ("日均消息", "7.0"),
        ):
            self.assertRegex(report, rf"{re.escape(label)}[\s\S]{{0,160}}{re.escape(value)}")

    def test_all_twelve_native_chart_meanings_render_real_aggregate_data(self):
        report = render(self.m)
        charts = (
            ("goals", "你想完成什么", "coding", 61),
            ("tools", "最常用工具", "exec", 52),
            ("languages", "编程语言", "Python", 43),
            ("session-types", "会话类型", "单一任务", 34),
            ("response-time", "用户响应时间分布", "2–10 秒", 25),
            ("multi-clauding", "多任务并行", "重叠事件", 16),
            ("message-hours", "用户消息时段", "上午（6–12）", 27),
            ("tool-errors", "遇到的工具错误", "命令失败", 18),
            ("successes", "最有效的帮助", "出色调试", 39),
            ("outcomes", "结果", "完全达成", 41),
            ("friction", "主要摩擦类型", "工具失败", 22),
            ("satisfaction", "推断满意度", "正向", 33),
        )

        starts = []
        for chart_id, _title, _label, _value in charts:
            marker = f'data-chart="{chart_id}"'
            self.assertEqual(report.count(marker), 1, marker)
            starts.append(report.index(marker))
        self.assertEqual(starts, sorted(starts), "charts should retain the native report order")

        for index, (chart_id, title, label, value) in enumerate(charts):
            start = report.index(f'data-chart="{chart_id}"')
            end = starts[index + 1] if index + 1 < len(starts) else len(report)
            fragment = report[start:end]
            self.assertIn(title, fragment)
            self.assertIn(label, fragment)
            self.assertIn(str(value), fragment)

        response_start = report.index('data-chart="response-time"')
        response_end = report.index('data-chart="multi-clauding"')
        response_fragment = report[response_start:response_end]
        for label in ("2–10 秒", "10–30 秒", "30 秒–1 分钟", "1–2 分钟", "2–5 分钟", "5–15 分钟", "超过 15 分钟"):
            self.assertIn(label, response_fragment)
        self.assertIn("中位数：14 秒", response_fragment)
        self.assertIn("平均：27 秒", response_fragment)
        multi_start = report.index('data-chart="multi-clauding"')
        multi_end = report.index('data-chart="message-hours"')
        multi_fragment = report[multi_start:multi_end]
        self.assertIn("20 / 42", multi_fragment)
        self.assertIn("47.6%", multi_fragment)
        self.assertIn("同一任务两条消息之间", multi_fragment)
        for raw in ("fully_achieved", "single_task", "good_debugging", "tool_failed"):
            self.assertNotIn(f'>{raw}<', report)

    def test_seven_semantic_sections_and_navigation_preserve_lens_outputs(self):
        report = render(self.m)
        expected_sections = (
            ("section-work", "项目领域"),
            ("section-usage", "协作方式"),
            ("section-wins", "有效做法"),
            ("section-friction", "摩擦与根因"),
            ("section-features", "功能建议"),
            ("section-patterns", "工作流建议"),
            ("section-horizon", "未来机会"),
        )

        links = re.findall(r'href="#(section-[^"]+)"', report)
        self.assertEqual(links, [section_id for section_id, _ in expected_sections])
        self.assertNotIn("section-feedback", report)
        for section_id, title in expected_sections:
            self.assertEqual(report.count(f'id="{section_id}"'), 1)
            self.assertIn(title, report)

        # Project, collaboration, success, and friction are native semantic
        # lenses; suggestions must keep their actionable subfields instead of
        # being flattened into generic claims.
        for value in (
            "统一 Claude Code 与 Codex 的插件真源。",
            "先看证据，再改代码",
            "先反编译事实，再用测试固定行为。",
            "把跨会话模式误当作原生主流程",
            "复杂复刻任务先建立原生行为矩阵。",
            "避免把自主设计误写成上游事实。",
            "对比命令描述、数据流、模型提示与报告输出。",
            "把七个互不依赖的 lens 并行分析。",
            "能缩短额度冲刺中的墙钟时间。",
            "$insights MAX_NEW_SESSIONS=10",
            "每个长任务先写可判定验收条件。",
            "完成一轮后只修订最弱项，避免无终点改写。",
            "先列出验收条件，再开始实现。",
            "自动发现多个项目反复出现的失败模式。",
            "先用三个仓库做只读审计并比较回归证据。",
            "扫描三个仓库，按风险和可验证性排序。",
            "你不是在和 Codex 聊天，而是在训练一套工作系统。",
            "最难忘的时刻，是你发现“安全”并不等于“复刻正确”。",
        ):
            self.assertIn(value, report)

        self.assertGreaterEqual(report.count("<pre><code>"), 4)

    def test_default_chinese_static_responsive_print_contract_and_escaping(self):
        lenses = lenses_fixture()
        lenses["suggestions"]["usage_patterns"][0]["copyable_prompt"] = '</code><img src="https://evil.example/x">'
        glance = at_a_glance_fixture()
        glance["whats_hindering"] = '<script>alert("x")</script> & 继续'
        report = render(self.m, lenses=lenses, at_a_glance=glance)
        compact_css = re.sub(r"\s+", "", report[report.index("<style>") : report.index("</style>")])

        self.assertTrue(report.lower().startswith("<!doctype html>"))
        self.assertIn('<html lang="zh-CN">', report)
        self.assertEqual(report.count("<style>"), 1)
        self.assertEqual(report.count("</style>"), 1)
        self.assertNotIn("<script", report.lower())
        self.assertNotRegex(report, r"(?i)\son[a-z]+\s*=")
        self.assertNotRegex(report, r'(?i)(?:href|src)=["\'](?:https?:|//)')
        self.assertNotRegex(report, r"(?i)<(?:link|iframe|form)\b")
        self.assertIn("<aside", report)
        self.assertIn("<nav", report)
        self.assertRegex(compact_css, r"position:sticky")
        self.assertRegex(compact_css, r"@media\(max-width:640px\)")
        self.assertRegex(compact_css, r"@mediaprint")
        self.assertRegex(compact_css, r":focus(?:-visible)?")
        for directive in (
            "default-src 'none'",
            "script-src 'none'",
            "connect-src 'none'",
            "frame-src 'none'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ):
            self.assertIn(directive, report)

        self.assertIn('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; 继续', report)
        self.assertIn('&lt;/code&gt;&lt;img src=&quot;https://evil.example/x&quot;&gt;', report)
        self.assertNotIn('<img src="https://evil.example/x">', report)

    def test_remaining_sessions_show_semantic_coverage_limit(self):
        report = render(
            self.m,
            coverage={"eligible": 14, "cached": 2, "selected": 10, "remaining": 2},
        )
        self.assertIn("仍有 2 个合格会话尚未完成语义分析", report)
        self.assertIn("确定性统计覆盖 14 个", report)
        self.assertIn("叙事洞察覆盖 10 个", report)


if __name__ == "__main__":
    unittest.main()
