"""Render the Codex adaptation of Claude Code's native Insights report.

The renderer is deliberately boring: it accepts already-validated structured
analysis and places it in a fixed, static template.  Model output is never
treated as markup.  Keeping rendering separate from analysis also makes the
HTML contract straightforward to test and audit.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

_TEXT = {
    "zh": {
        "title": "Codex 会话洞察",
        "subtitle": "基于本机近期 Codex 会话生成的工作方式复盘",
        "range": "覆盖日期",
        "glance": "一目了然",
        "working": "做得好的地方",
        "hindering": "阻碍你的地方",
        "quick": "快速改进",
        "ambitious": "值得挑战的工作流",
        "messages": "用户消息",
        "lines": "代码行",
        "files": "文件",
        "days": "活跃天数",
        "per_day": "日均消息",
        "nav": "报告导航",
        "work": "项目领域",
        "usage": "协作方式",
        "wins": "有效做法",
        "friction": "摩擦与根因",
        "features": "功能建议",
        "patterns": "工作流建议",
        "horizon": "未来机会",
        "goals_chart": "你想完成什么",
        "tools_chart": "最常用工具",
        "languages_chart": "编程语言",
        "sessions_chart": "会话类型",
        "response_chart": "用户响应时间分布",
        "multi_chart": "多任务并行",
        "hours_chart": "用户消息时段",
        "errors_chart": "遇到的工具错误",
        "success_chart": "最有效的帮助",
        "outcomes_chart": "结果",
        "friction_chart": "主要摩擦类型",
        "satisfaction_chart": "推断满意度",
        "key_pattern": "关键模式",
        "sessions": "个会话",
        "agents": "AGENTS.md 建议",
        "addition": "建议加入",
        "why": "为什么",
        "prompt": "可直接使用",
        "features_try": "值得尝试的功能",
        "why_you": "为什么适合你",
        "example": "示例",
        "usage_patterns": "可优化的使用模式",
        "suggestion": "建议",
        "details": "怎么做",
        "opportunities": "下一阶段的机会",
        "possible": "可以做到什么",
        "try": "如何开始",
        "memorable": "难忘时刻",
        "method": "方法与覆盖量",
        "eligible": "合格会话",
        "cached": "沿用缓存",
        "selected": "本轮分析",
        "remaining": "尚待处理",
        "snapshot_at": "分析快照时间",
        "no_data": "暂无数据",
        "median": "中位数",
        "average": "平均",
        "seconds": "秒",
        "multi_note": "并行期间消息：{during} / {total}（{percent}%）。检测条件：同一任务两条消息之间穿插另一任务消息。",
        "chart_total": "{total} 次",
        "chart_context": "条形表示本图内占比",
        "friction_chart_context": "统计已识别的摩擦事件；同一事件不重复计数",
        "satisfaction_chart_context": "只统计用户明确表达的反馈信号",
        "coverage_limit": "仍有 {remaining} 个合格会话尚未完成语义分析。确定性统计覆盖 {eligible} 个；叙事洞察覆盖 {analyzed} 个。",
        "primary_total": "主会话总数",
        "analyzed": "已分析主会话",
        "skipped": "跳过",
        "subagent": "子代理",
        "automation": "自动化",
        "headless": "无头执行",
    },
    "en": {
        "title": "Codex Session Insights",
        "subtitle": "A review of how you work, based on recent local Codex sessions",
        "range": "Date range",
        "glance": "At a Glance",
        "working": "What's Working",
        "hindering": "What's Hindering You",
        "quick": "Quick Wins",
        "ambitious": "Ambitious Workflows",
        "messages": "User Messages",
        "lines": "Lines",
        "files": "Files",
        "days": "Active Days",
        "per_day": "Messages / Day",
        "nav": "Report navigation",
        "work": "Project Areas",
        "usage": "Interaction Style",
        "wins": "What Works",
        "friction": "Friction and Root Causes",
        "features": "Feature Suggestions",
        "patterns": "Workflow Suggestions",
        "horizon": "On the Horizon",
        "goals_chart": "What You Wanted",
        "tools_chart": "Top Tools Used",
        "languages_chart": "Languages",
        "sessions_chart": "Session Types",
        "response_chart": "User Response Time Distribution",
        "multi_chart": "Multi-Clauding",
        "hours_chart": "User Messages by Time of Day",
        "errors_chart": "Tool Errors Encountered",
        "success_chart": "What Helped Most",
        "outcomes_chart": "Outcomes",
        "friction_chart": "Primary Friction Types",
        "satisfaction_chart": "Inferred Satisfaction",
        "key_pattern": "Key pattern",
        "sessions": "sessions",
        "agents": "AGENTS.md Suggestions",
        "addition": "Addition",
        "why": "Why",
        "prompt": "Copyable prompt",
        "features_try": "Features to Try",
        "why_you": "Why it fits you",
        "example": "Example",
        "usage_patterns": "Usage Patterns",
        "suggestion": "Suggestion",
        "details": "Detail",
        "opportunities": "Opportunities",
        "possible": "What's possible",
        "try": "How to try it",
        "memorable": "A Memorable Moment",
        "method": "Method and Coverage",
        "eligible": "Eligible",
        "cached": "Cached",
        "selected": "Analyzed now",
        "remaining": "Remaining",
        "snapshot_at": "Analysis snapshot",
        "no_data": "No data",
        "median": "Median",
        "average": "Average",
        "seconds": "seconds",
        "multi_note": "Messages during overlap: {during} / {total} ({percent}%). Detection requires another task between two messages from the same task.",
        "chart_total": "{total} events",
        "chart_context": "Bars show the share within this chart",
        "friction_chart_context": "Observed friction events; one event is counted once",
        "satisfaction_chart_context": "Only explicit user feedback signals are counted",
        "coverage_limit": "{remaining} eligible sessions have not completed semantic analysis. Deterministic stats cover {eligible}; narrative insights cover {analyzed}.",
        "primary_total": "Primary sessions",
        "analyzed": "Analyzed primary sessions",
        "skipped": "Skipped",
        "subagent": "Subagents",
        "automation": "Automations",
        "headless": "Headless runs",
    },
}

_LABELS_ZH = {
    "debug_investigate": "调试与排查",
    "implement_feature": "实现功能",
    "fix_bug": "修复缺陷",
    "write_script_tool": "编写脚本或工具",
    "refactor_code": "重构代码",
    "configure_system": "配置系统",
    "create_pr_commit": "提交与合并请求",
    "analyze_data": "分析数据",
    "understand_codebase": "理解代码库",
    "write_tests": "编写测试",
    "write_docs": "编写文档",
    "deploy_infra": "部署与基础设施",
    "warmup_minimal": "简短热身",
    "single_task": "单一任务",
    "multi_task": "多任务",
    "iterative_refinement": "迭代完善",
    "exploration": "探索",
    "quick_question": "快速提问",
    "fully_achieved": "完全达成",
    "mostly_achieved": "基本达成",
    "partially_achieved": "部分达成",
    "not_achieved": "未达成",
    "unclear_from_transcript": "无法判断",
    "unhelpful": "没有帮助",
    "slightly_helpful": "略有帮助",
    "moderately_helpful": "中等帮助",
    "very_helpful": "很有帮助",
    "essential": "不可或缺",
    "fast_accurate_search": "快速准确检索",
    "correct_code_edits": "正确代码修改",
    "good_explanations": "清晰解释",
    "proactive_help": "主动协助",
    "multi_file_changes": "多文件修改",
    "good_debugging": "出色调试",
    "misunderstood_request": "误解请求",
    "wrong_approach": "方案错误",
    "buggy_code": "代码有误",
    "user_rejected_action": "用户否决操作",
    "claude_got_blocked": "Codex 受阻",
    "codex_got_blocked": "Codex 受阻",
    "user_stopped_early": "用户提前停止",
    "wrong_file_or_location": "文件或位置错误",
    "excessive_changes": "改动过度",
    "slow_or_verbose": "缓慢或冗长",
    "tool_failed": "工具失败",
    "user_unclear": "用户意图不清",
    "external_issue": "外部问题",
    "repeated_instruction": "重复指令",
    "frustrated": "沮丧",
    "dissatisfied": "不满意",
    "likely_satisfied": "可能满意",
    "satisfied": "满意",
    "happy": "高兴",
    "positive": "正向",
    "negative": "负向",
    "correction": "纠正",
    "Command Failed": "命令失败",
    "command_failed": "命令失败",
    "File Not Found": "文件未找到",
    "file_not_found": "文件未找到",
    "Edit Failed": "编辑失败",
    "User Rejected": "用户拒绝",
    "user_rejected": "用户拒绝",
    "overlap_events": "重叠事件",
    "overlapping_sessions": "重叠事件",
    "sessions_involved": "涉及会话",
    "max_concurrent": "最高并发",
    "user_messages_during": "并发期间用户消息",
    "2_to_10_seconds": "2–10 秒",
    "10_to_30_seconds": "10–30 秒",
    "30_seconds_to_1_minute": "30 秒–1 分钟",
    "1_to_2_minutes": "1–2 分钟",
    "2_to_5_minutes": "2–5 分钟",
    "5_to_15_minutes": "5–15 分钟",
    "over_15_minutes": "超过 15 分钟",
    "morning": "上午（6–12）",
    "afternoon": "下午（12–18）",
    "evening": "晚上（18–24）",
    "night": "深夜（0–6）",
}

_LABELS_EN = {
    "2_to_10_seconds": "2–10s",
    "10_to_30_seconds": "10–30s",
    "30_seconds_to_1_minute": "30s–1m",
    "1_to_2_minutes": "1–2m",
    "2_to_5_minutes": "2–5m",
    "5_to_15_minutes": "5–15m",
    "over_15_minutes": ">15m",
    "morning": "Morning (6–12)",
    "afternoon": "Afternoon (12–18)",
    "evening": "Evening (18–24)",
    "night": "Night (0–6)",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _number(value: Any, default: Any = 0) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(default)
        return str(value)
    return _escape(value if value not in (None, "") else default)


def _count(value: Any) -> int:
    return max(0, int(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _safe_language(language: Any) -> str:
    candidate = str(language or "zh-CN")
    return candidate if _LANGUAGE_RE.fullmatch(candidate) else "zh-CN"


def _rich_inline(value: Any) -> str:
    escaped = _escape(value)
    return re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", escaped)


def _paragraph(value: Any, class_name: str = "") -> str:
    class_attr = f' class="{class_name}"' if class_name else ""
    return f"<p{class_attr}>{_rich_inline(value)}</p>"


def _paragraphs(value: Any, class_name: str = "") -> str:
    parts = [part.strip() for part in re.split(r"\n\s*\n", str(value or "")) if part.strip()]
    if not parts:
        return _paragraph("", class_name)
    return "".join(_paragraph(part, class_name if index == 0 else "") for index, part in enumerate(parts))


def _code(value: Any) -> str:
    return f"<pre><code>{_escape(value)}</code></pre>"


def _chart(
    chart_id: str,
    title: str,
    values: Any,
    no_data: str,
    *,
    labels: Mapping[str, str],
    preserve_order: bool = False,
    note: str = "",
    context: str = "",
    total_template: str = "{total}",
) -> str:
    rows = _mapping(values)
    numeric = [float(value) for value in rows.values() if isinstance(value, (int, float)) and not isinstance(value, bool)]
    maximum = max(numeric, default=0.0)
    total = sum(max(0.0, value) for value in numeric)
    body: list[str] = []
    entries = list(rows.items())
    if not preserve_order:
        entries.sort(
            key=lambda item: (
                -(float(item[1]) if isinstance(item[1], (int, float)) and not isinstance(item[1], bool) else 0),
                str(item[0]),
            )
        )
        entries = entries[:8]
    for label, raw_value in entries:
        numeric_value = float(raw_value) if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool) else 0.0
        share = 0.0 if total <= 0 else max(0.0, min(100.0, numeric_value / total * 100))
        percent = 0 if share <= 0 else max(2, min(100, round(share)))
        body.append(
            '<div class="chart-row">'
            '<div class="chart-row-head">'
            f'<span class="chart-label">{_escape(labels.get(str(label), label))}</span>'
            '<span class="chart-metric">'
            f'<strong class="chart-value">{_number(raw_value)}</strong>'
            f'<span class="chart-share">{share:.1f}%</span>'
            '</span></div>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{percent}%"></span></span>'
            "</div>"
        )
    if not body:
        body.append(f'<p class="empty">{_escape(no_data)}</p>')
    return (
        f'<section class="chart-card chart-{_escape(chart_id)}" data-chart="{_escape(chart_id)}">'
        '<div class="chart-heading">'
        f'<h3>{_escape(title)}</h3><span class="chart-total">'
        f'{_escape(total_template.format(total=_number(int(total) if total.is_integer() else total)))}</span></div>'
        f'<p class="chart-context">{_escape(context)}</p>{"".join(body)}'
        f'{f"<p class=\"chart-note\">{_escape(note)}</p>" if note else ""}</section>'
    )


def _time_periods(values: Any) -> dict[str, int]:
    result = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
    for raw_hour, raw_count in _mapping(values).items():
        try:
            hour = int(raw_hour) % 24
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        bucket = "morning" if 6 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening" if 18 <= hour < 24 else "night"
        result[bucket] += max(0, count)
    return result


def _glance_item(title: str, body: Any, target: str) -> str:
    return (
        '<p class="glance-item">'
        f'<a href="#{_escape(target)}"><strong>{_escape(title)}</strong></a> '
        f'{_rich_inline(body)}</p>'
    )


def _project_areas(lens: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    for area in _items(lens.get("areas")):
        count = area.get("session_count", 0)
        cards.append(
            '<article class="item-card">'
            f'<div class="item-heading"><h3>{_escape(area.get("name"))}</h3>'
            f'<span class="pill">{_number(count)} {_escape(t["sessions"])}</span></div>'
            f'{_paragraph(area.get("description"))}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def _workflows(lens: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    for item in _items(lens.get("impressive_workflows")):
        cards.append(
            '<article class="item-card success-card">'
            f'<h3>{_escape(item.get("title"))}</h3>{_paragraph(item.get("description"))}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def _friction_categories(lens: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    for item in _items(lens.get("categories")):
        examples = item.get("examples")
        example_items = []
        if isinstance(examples, Sequence) and not isinstance(examples, (str, bytes, bytearray)):
            example_items = [f"<li>{_escape(example)}</li>" for example in examples]
        examples_html = f"<ul>{''.join(example_items)}</ul>" if example_items else ""
        cards.append(
            '<article class="item-card friction-card">'
            f'<h3>{_escape(item.get("title"))}</h3>{_paragraph(item.get("description"))}{examples_html}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def _agents_additions(suggestions: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    additions = suggestions.get("agents_md_additions", suggestions.get("claude_md_additions", []))
    for item in _items(additions):
        cards.append(
            '<article class="action-card">'
            f'<h4>{_escape(t["addition"])}：{_escape(item.get("addition"))}</h4>'
            f'<p><strong>{_escape(t["why"])}：</strong>{_escape(item.get("why"))}</p>'
            f'<p class="code-label">{_escape(t["prompt"])}</p>{_code(item.get("prompt_scaffold"))}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def _features(suggestions: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    for item in _items(suggestions.get("features_to_try")):
        cards.append(
            '<article class="action-card">'
            f'<h4>{_escape(item.get("feature"))}</h4>{_paragraph(item.get("one_liner"))}'
            f'<p><strong>{_escape(t["why_you"])}：</strong>{_escape(item.get("why_for_you"))}</p>'
            f'<p class="code-label">{_escape(t["example"])}</p>{_code(item.get("example_code"))}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def _usage_patterns(suggestions: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    for item in _items(suggestions.get("usage_patterns")):
        cards.append(
            '<article class="action-card">'
            f'<h3>{_escape(item.get("title"))}</h3>'
            f'<p><strong>{_escape(t["suggestion"])}：</strong>{_escape(item.get("suggestion"))}</p>'
            f'<p><strong>{_escape(t["details"])}：</strong>{_escape(item.get("detail"))}</p>'
            f'<p class="code-label">{_escape(t["prompt"])}</p>{_code(item.get("copyable_prompt"))}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def _opportunities(lens: Mapping[str, Any], t: Mapping[str, str]) -> str:
    cards: list[str] = []
    for item in _items(lens.get("opportunities")):
        cards.append(
            '<article class="action-card future-card">'
            f'<h3>{_escape(item.get("title"))}</h3>'
            f'<p><strong>{_escape(t["possible"])}：</strong>{_escape(item.get("whats_possible"))}</p>'
            f'<p><strong>{_escape(t["try"])}：</strong>{_escape(item.get("how_to_try"))}</p>'
            f'<p class="code-label">{_escape(t["prompt"])}</p>{_code(item.get("copyable_prompt"))}</article>'
        )
    return "".join(cards) or f'<p class="empty">{_escape(t["no_data"])}</p>'


def render_native_report(
    aggregate: Mapping[str, Any],
    lenses: Mapping[str, Any],
    at_a_glance: Mapping[str, Any],
    language: str = "zh-CN",
    coverage: Mapping[str, Any] | None = None,
) -> str:
    """Return a self-contained, escaped, zero-JavaScript Insights report."""

    safe_language = _safe_language(language)
    t = _TEXT["zh" if safe_language.lower().startswith("zh") else "en"]
    labels = _LABELS_ZH if safe_language.lower().startswith("zh") else _LABELS_EN
    aggregate = _mapping(aggregate)
    lenses = _mapping(lenses)
    at_a_glance = _mapping(at_a_glance)
    coverage = _mapping(coverage)

    date_range = _mapping(aggregate.get("date_range"))
    range_text = f'{_escape(date_range.get("start", "—"))} – {_escape(date_range.get("end", "—"))}'
    line_stat = f'+{_number(aggregate.get("lines_added"))} / -{_number(aggregate.get("lines_removed"))}'

    nav_items = (
        ("section-work", t["work"]),
        ("section-usage", t["usage"]),
        ("section-wins", t["wins"]),
        ("section-friction", t["friction"]),
        ("section-features", t["features"]),
        ("section-patterns", t["patterns"]),
        ("section-horizon", t["horizon"]),
    )
    nav_html = "".join(
        f'<a href="#{section_id}">{_escape(label)}</a>' for section_id, label in nav_items
    )

    response_note = (
        f'{t["median"]}：{_number(aggregate.get("response_time_median_seconds", aggregate.get("median_response_time", 0)))} {t["seconds"]} · '
        f'{t["average"]}：{_number(aggregate.get("response_time_average_seconds", aggregate.get("avg_response_time", 0)))} {t["seconds"]}'
    )
    multi_values = _mapping(aggregate.get("multi_clauding"))
    messages_during = _count(multi_values.get("user_messages_during"))
    total_messages = _count(aggregate.get("total_messages"))
    multi_percent = round(messages_during / total_messages * 100, 1) if total_messages else 0
    multi_note = t["multi_note"].format(
        during=messages_during,
        total=total_messages,
        percent=multi_percent,
    )
    chart_specs = (
        ("goals", t["goals_chart"], aggregate.get("goal_categories"), False, ""),
        ("tools", t["tools_chart"], aggregate.get("tool_counts"), False, ""),
        ("languages", t["languages_chart"], aggregate.get("languages"), False, ""),
        ("session-types", t["sessions_chart"], aggregate.get("session_types"), False, ""),
        ("response-time", t["response_chart"], aggregate.get("response_time_distribution"), True, response_note),
        ("multi-clauding", t["multi_chart"], multi_values, True, multi_note),
        ("message-hours", t["hours_chart"], _time_periods(aggregate.get("message_hours")), True, ""),
        ("tool-errors", t["errors_chart"], aggregate.get("tool_error_categories"), False, ""),
        ("successes", t["success_chart"], aggregate.get("success"), False, ""),
        ("outcomes", t["outcomes_chart"], aggregate.get("outcomes"), False, ""),
        ("friction", t["friction_chart"], aggregate.get("friction"), False, ""),
        ("satisfaction", t["satisfaction_chart"], aggregate.get("satisfaction"), False, ""),
    )
    charts = {
        chart_id: _chart(
            chart_id,
            title,
            values,
            t["no_data"],
            labels=labels,
            preserve_order=preserve_order,
            note=note,
            context=(
                t["friction_chart_context"] if chart_id == "friction"
                else t["satisfaction_chart_context"] if chart_id == "satisfaction"
                else t["chart_context"]
            ),
            total_template=t["chart_total"],
        )
        for chart_id, title, values, preserve_order, note in chart_specs
    }

    project_areas = _mapping(lenses.get("project_areas"))
    interaction = _mapping(lenses.get("interaction_style"))
    what_works = _mapping(lenses.get("what_works"))
    friction_lens = _mapping(lenses.get("friction_analysis"))
    suggestions = _mapping(lenses.get("suggestions"))
    horizon = _mapping(lenses.get("on_the_horizon"))
    fun_ending = _mapping(lenses.get("fun_ending"))

    analyzed = _count(coverage.get("analyzed")) or _count(aggregate.get("sessions_with_facets"))
    primary_total = (
        _count(coverage.get("primary_total"))
        or _count(coverage.get("eligible"))
        or _count(aggregate.get("total_sessions"))
    )
    if safe_language.lower().startswith("zh"):
        report_meta = (
            f'{_number(aggregate.get("total_messages"))} 条消息，来自 {analyzed} 个会话'
            f'（共 {primary_total} 个）｜{_escape(date_range.get("start", "—"))} 至 '
            f'{_escape(date_range.get("end", "—"))}'
        )
    else:
        report_meta = (
            f'{_number(aggregate.get("total_messages"))} messages across {analyzed} sessions '
            f'({primary_total} total) | {_escape(date_range.get("start", "—"))} to '
            f'{_escape(date_range.get("end", "—"))}'
        )
    method_keys = (
        "primary_total", "analyzed", "skipped", "remaining",
        "subagent", "automation", "headless",
    )
    coverage_html = "".join(
        f'<span><strong>{_escape(t[key])}</strong> {_number(coverage.get(key))}</span>'
        for key in method_keys
        if key in coverage
    )
    snapshot_html = ""
    if coverage.get("snapshot_at"):
        snapshot_html = (
            f'<p><strong>{_escape(t["snapshot_at"])}：</strong>'
            f'{_escape(coverage.get("snapshot_at"))}</p>'
        )
    css = """
    :root{color-scheme:light;--canvas:#f7f7f8;--ink:#202123;--muted:#6b7280;--line:#e3e3e3;--blue:#2563eb;--green:#2f855a;--red:#c53030;--purple:#6b46c1;--yellow:#fff8df}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}.page{max-width:800px;margin:0 auto;padding:42px 24px 72px}a{color:inherit}a:focus-visible{outline:3px solid #84adff;outline-offset:3px}.hero h1{font-size:32px;line-height:1.2;letter-spacing:-.025em;margin:0 0 4px}.report-meta{margin:0;color:var(--muted);font-size:14px;white-space:nowrap}.glance{background:var(--yellow);border:1px solid #ead799;border-radius:10px;padding:18px 22px;margin:26px 0 18px}.glance h2{font-size:20px;margin:0 0 10px}.glance-item{margin:9px 0}.glance-item a{text-decoration:none;color:#8a5b00}.top-nav{display:flex;flex-wrap:wrap;gap:8px 18px;border-bottom:1px solid var(--line);padding:4px 0 14px;margin-bottom:18px}.top-nav a{font-size:13px;text-decoration:none;color:#4b5563}.top-nav a:hover{text-decoration:underline}.stats{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--line);padding:0 0 18px;margin:0 0 32px}.stat{text-align:center;border-right:1px solid var(--line);padding:4px 8px}.stat:last-child{border-right:0}.stat span{display:block;color:var(--muted);font-size:12px}.stat strong{display:block;font-size:17px;margin-top:2px}.report-section{scroll-margin-top:18px;border-top:1px solid var(--line);padding:30px 0 4px;margin:0}.report-section>h2{margin:0 0 14px;font-size:24px}.lead{font-size:16px;color:#34373d}.key-pattern{background:#eef4ff;border-left:3px solid var(--blue);padding:10px 12px}.item-card,.action-card{border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:10px 0;background:#fff}.item-card h3,.action-card h3,.action-card h4{margin:0 0 7px}.item-card p,.action-card p{margin:6px 0}.item-heading{display:flex;gap:12px;justify-content:space-between;align-items:start}.pill{white-space:nowrap;background:#eef4ff;color:#1d4ed8;border-radius:999px;padding:2px 8px;font-size:12px}.success-card{border-left:4px solid var(--green)}.friction-card{border-left:4px solid var(--red)}.future-card{border-left:4px solid var(--purple)}.subsection-title{font-size:18px;margin:22px 0 8px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:24px 0}.chart-card{min-width:0;background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:15px 16px 14px}.chart-heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.chart-card h3{font-size:15px;line-height:1.35;margin:0}.chart-total{flex:none;color:#475569;background:#f1f5f9;border-radius:999px;padding:1px 8px;font-size:11px;font-variant-numeric:tabular-nums}.chart-context{min-height:34px;color:var(--muted);font-size:11px;line-height:1.45;margin:4px 0 12px}.chart-row{border-top:1px solid #eef0f3;padding:9px 0 8px}.chart-row-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:5px}.chart-label{min-width:0;overflow-wrap:anywhere;font-size:12px}.chart-metric{display:flex;align-items:baseline;gap:6px;white-space:nowrap;font-variant-numeric:tabular-nums}.chart-value{font-size:12px}.chart-share{color:var(--muted);font-size:10px;min-width:36px;text-align:right}.bar-track{display:block;height:5px;background:#edf0f4;border-radius:99px;overflow:hidden}.bar-fill{display:block;height:100%;background:var(--blue);border-radius:99px}.chart-successes .bar-fill,.chart-outcomes .bar-fill{background:var(--green)}.chart-friction{border-top:3px solid #dc6b6b}.chart-friction .bar-fill,.chart-tool-errors .bar-fill{background:var(--red)}.chart-satisfaction{border-top:3px solid #d6a532}.chart-satisfaction .bar-fill{background:#d6a532}.chart-multi-clauding .bar-fill{background:var(--purple)}.chart-note{border-top:1px solid #eef0f3;color:var(--muted);font-size:11px;margin:9px 0 0;padding-top:8px}.code-label{font-size:12px;color:var(--muted);margin-top:10px!important}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:5px 0 0;background:#f3f4f6;color:#25272b;border:1px solid #e1e4e8;border-radius:6px;padding:10px 12px;font-size:13px;line-height:1.5}code{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}.fun-ending{background:var(--yellow);border:1px solid #ead799;border-radius:10px;padding:18px 20px;margin:30px 0}.fun-ending h2,.fun-ending h3{margin:0 0 6px}.method{color:var(--muted);font-size:13px;border-top:1px solid var(--line);margin-top:34px;padding-top:20px}.method h2{font-size:18px;color:var(--ink)}.coverage{display:flex;flex-wrap:wrap;gap:7px 18px}.empty{color:var(--muted);font-style:italic}
    @media(max-width:640px){.page{padding:24px 14px 48px}.report-meta{white-space:normal}.top-nav{overflow-x:auto;flex-wrap:nowrap;white-space:nowrap}.stats{grid-template-columns:repeat(2,1fr);gap:10px}.stat{border-right:0;border-bottom:1px solid var(--line);padding:8px}.stats .stat:last-child{grid-column:1/-1}.charts{grid-template-columns:1fr}.chart-context{min-height:0}.hero h1{font-size:28px}}
    @media print{body{background:#fff}.page{max-width:none;padding:0}.top-nav{display:none}.report-section,.glance,.item-card,.action-card,.chart-card{break-inside:avoid}.charts{display:block}.chart-card{margin:12px 0}pre{color:#000;background:#f3f4f6}}
    """

    return f'''<!doctype html>
<html lang="{_escape(safe_language)}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; img-src 'none'; font-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{_escape(t["title"])}</title>
<style>{css}</style>
</head>
<body>
<div class="page">
<main>
<header class="hero"><h1>{_escape(t["title"])}</h1><p class="report-meta">{report_meta}</p></header>
<section class="glance" aria-labelledby="glance-title"><h2 id="glance-title">{_escape(t["glance"])}</h2>
{_glance_item(t["working"], at_a_glance.get("whats_working"), "section-wins")}
{_glance_item(t["hindering"], at_a_glance.get("whats_hindering"), "section-friction")}
{_glance_item(t["quick"], at_a_glance.get("quick_wins"), "section-features")}
{_glance_item(t["ambitious"], at_a_glance.get("ambitious_workflows"), "section-horizon")}
</section>
<nav class="top-nav" aria-label="{_escape(t["nav"])}">{nav_html}</nav>
<section class="stats" aria-label="headline statistics">
<div class="stat"><span>{_escape(t["messages"])}</span><strong>{_number(aggregate.get("total_messages"))}</strong></div>
<div class="stat"><span>{_escape(t["lines"])}</span><strong>{line_stat}</strong></div>
<div class="stat"><span>{_escape(t["files"])}</span><strong>{_number(aggregate.get("files_modified"))}</strong></div>
<div class="stat"><span>{_escape(t["days"])}</span><strong>{_number(aggregate.get("days_active"))}</strong></div>
<div class="stat"><span>{_escape(t["per_day"])}</span><strong>{_number(aggregate.get("messages_per_day"))}</strong></div>
</section>

<section class="report-section" id="section-work"><h2>{_escape(t["work"])}</h2>
{_project_areas(project_areas, t)}
<div class="charts">{charts["goals"]}{charts["tools"]}{charts["languages"]}{charts["session-types"]}</div></section>

<section class="report-section" id="section-usage"><h2>{_escape(t["usage"])}</h2>
{_paragraphs(interaction.get("narrative"), "lead")}
<p class="key-pattern"><strong>{_escape(t["key_pattern"])}：</strong>{_escape(interaction.get("key_pattern"))}</p>
<div class="charts">{charts["response-time"]}{charts["multi-clauding"]}{charts["message-hours"]}{charts["tool-errors"]}</div></section>

<section class="report-section section-wins" id="section-wins"><h2>{_escape(t["wins"])}</h2>
{_paragraph(what_works.get("intro"), "lead")}{_workflows(what_works, t)}
<div class="charts">{charts["successes"]}{charts["outcomes"]}</div></section>

<section class="report-section section-friction" id="section-friction"><h2>{_escape(t["friction"])}</h2>
{_paragraph(friction_lens.get("intro"), "lead")}{_friction_categories(friction_lens, t)}
<div class="charts">{charts["friction"]}{charts["satisfaction"]}</div></section>

<section class="report-section section-features" id="section-features"><h2>{_escape(t["features"])}</h2>
<h3 class="subsection-title">{_escape(t["agents"])}</h3>{_agents_additions(suggestions, t)}
<h3 class="subsection-title">{_escape(t["features_try"])}</h3>{_features(suggestions, t)}</section>

<section class="report-section" id="section-patterns"><h2>{_escape(t["patterns"])}</h2>
<h3 class="subsection-title">{_escape(t["usage_patterns"])}</h3>{_usage_patterns(suggestions, t)}</section>

<section class="report-section section-horizon" id="section-horizon"><h2>{_escape(t["horizon"])}</h2>
{_paragraphs(horizon.get("intro"), "lead")}<h3 class="subsection-title">{_escape(t["opportunities"])}</h3>{_opportunities(horizon, t)}</section>

<section class="fun-ending" id="section-memorable"><h2>{_escape(t["memorable"])}</h2><h3>{_escape(fun_ending.get("headline"))}</h3>{_paragraphs(fun_ending.get("detail"))}</section>

<footer class="method"><h2>{_escape(t["method"])}</h2><div class="coverage">{coverage_html}</div>{snapshot_html}</footer>
</main>
</div>
</body>
</html>'''


def _report_metrics(source: str) -> dict[str, Any]:
    source_without_method = re.sub(
        r'<footer class="method"[^>]*>.*?</footer>',
        "",
        source,
        flags=re.S | re.I,
    )
    narrative_blocks = [
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip().casefold()
        for value in re.findall(r"<(?:p|div)[^>]*>(.*?)</(?:p|div)>", source_without_method, re.S | re.I)
    ]
    coverage_disclaimers = sum(
        1
        for value in narrative_blocks
        if any(marker in value for marker in ("已分析", "analyzed facet", "analyzed subset"))
        and any(marker in value for marker in ("未分析", "未纳入", "尚未分析", "remaining session"))
    )
    section_ids = re.findall(r'<h2[^>]+id="(section-[^"]+)"', source)
    if not section_ids:
        section_ids = re.findall(r'<section[^>]+id="(section-(?:work|usage|wins|friction|features|patterns|horizon))"', source)
    max_widths = [int(value) for value in re.findall(r"max-width\s*:\s*(\d+)px", source)]
    h1_sizes = [int(value) for value in re.findall(r"h1\s*\{[^}]*font-size\s*:\s*(\d+)px", source)]
    radii = [int(value) for value in re.findall(r"border-radius\s*:\s*(\d+)px", source) if int(value) <= 24]
    headings = [
        html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for value in re.findall(r"<h[234][^>]*>(.*?)</h[234]>", source, re.S | re.I)
    ]
    chart_labels = [
        html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for value in re.findall(r'<span class="chart-label">(.*?)</span>', source, re.S | re.I)
    ]
    article_depth = 0
    max_article_depth = 0
    for token in re.findall(r"</?article\b[^>]*>", source, re.I):
        if token.startswith("</"):
            article_depth = max(0, article_depth - 1)
        else:
            article_depth += 1
            max_article_depth = max(max_article_depth, article_depth)
    report_meta_match = re.search(r'<p class="report-meta">(.*?)</p>', source, re.S | re.I)
    report_meta = html.unescape(re.sub(r"<[^>]+>", "", report_meta_match.group(1))).strip() if report_meta_match else ""
    nav_match = re.search(r'<nav class="top-nav"[^>]*>(.*?)</nav>', source, re.S | re.I)
    nav_hrefs = re.findall(r'href="#(section-[^"]+)"', nav_match.group(1)) if nav_match else []
    glance_items = [
        html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()
        for value in re.findall(r'<(?:p|div) class="glance-item">(.*?)</(?:p|div)>', source, re.S | re.I)
    ]
    section_text: dict[str, str] = {}
    section_pre_blocks: dict[str, int] = {}
    for section_id in section_ids:
        match = re.search(
            rf'<section[^>]+id="{re.escape(section_id)}"[^>]*>(.*?)</section>',
            source,
            re.S | re.I,
        )
        body = match.group(1) if match else ""
        section_text[section_id] = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
        section_pre_blocks[section_id] = len(re.findall(r"<pre\b", body, re.I))
    charts = re.findall(r'<section[^>]+data-chart="([^"]+)"', source)
    if not charts:
        reference_chart_titles = [
            html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()
            for value in re.findall(
                r'<div[^>]+class="[^"]*chart-title[^"]*"[^>]*>(.*?)</div>',
                source,
                re.S | re.I,
            )
        ]
        title_markers = (
            ("What You Wanted", "goals"),
            ("Top Tools Used", "tools"),
            ("Languages", "languages"),
            ("Session Types", "session-types"),
            ("User Response Time Distribution", "response-time"),
            ("Multi-Clauding", "multi-clauding"),
            ("Time of Day", "message-hours"),
            ("Tool Errors Encountered", "tool-errors"),
            ("What Helped Most", "successes"),
            ("Outcomes", "outcomes"),
            ("Primary Friction Types", "friction"),
            ("Inferred Satisfaction", "satisfaction"),
        )
        charts = [
            chart_id
            for title in reference_chart_titles
            for marker, chart_id in title_markers
            if marker.lower() in re.sub(r"\s+", " ", title).lower()
        ]
    return {
        "section_ids": section_ids,
        "max_width": max_widths[0] if max_widths else 0,
        "h1_size": h1_sizes[0] if h1_sizes else 0,
        "radius_median": sorted(radii)[len(radii) // 2] if radii else 0,
        "shadow_declarations": len(re.findall(r"box-shadow\s*:", source)),
        "max_article_depth": max_article_depth,
        "paragraphs": len(re.findall(r"<p\b", source, re.I)),
        "pre_blocks": len(re.findall(r"<pre\b", source, re.I)),
        "report_meta": report_meta,
        "glance_items": glance_items,
        "stat_count": len(re.findall(r'<div class="stat">', source)),
        "nav_hrefs": nav_hrefs,
        "section_text": section_text,
        "section_pre_blocks": section_pre_blocks,
        "charts": charts,
        "chart_contexts": len(re.findall(r'class="chart-context"', source)),
        "chart_shares": len(re.findall(r'class="chart-share"', source)),
        "chart_rows": len(re.findall(r'class="chart-row"', source)),
        "machine_headings": [
            heading
            for heading in headings
            if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", heading)
        ],
        "machine_chart_labels": [
            label for label in chart_labels
            if label in _LABELS_ZH
            and re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", label)
        ],
        "coverage_disclaimers": coverage_disclaimers,
    }


def compare_report_structure(candidate_html: str, reference_html: str) -> dict[str, Any]:
    """Compare a candidate with a read-only Claude report without copying content."""

    candidate = _report_metrics(candidate_html)
    reference = _report_metrics(reference_html)
    expected_sections = [
        "section-work", "section-usage", "section-wins", "section-friction",
        "section-features", "section-patterns", "section-horizon",
    ]
    chart_order = [
        "goals", "tools", "languages", "session-types", "response-time",
        "multi-clauding", "message-hours", "tool-errors", "successes",
        "outcomes", "friction", "satisfaction",
    ]
    glance_at = candidate_html.find('class="glance"')
    nav_at = candidate_html.find('<nav class="top-nav"')
    stats_at = candidate_html.find('class="stats"')

    checks = [
        ("reference-readable", len(reference_html) > 1_000),
        ("single-line-header", bool(re.fullmatch(
            r"(?:[\d,]+ 条消息，来自 \d+ 个会话（共 \d+ 个）｜\d{4}-\d{2}-\d{2} 至 \d{4}-\d{2}-\d{2}|[\d,]+ messages across \d+ sessions \(\d+ total\) \| \d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2})",
            candidate["report_meta"],
        ))),
        ("four-distinct-glance-items", len(candidate["glance_items"]) == 4 and len(set(candidate["glance_items"])) == 4 and all(len(item) >= 12 for item in candidate["glance_items"])),
        ("five-headline-stats", candidate["stat_count"] == 5),
        ("linear-overview-nav-stats", -1 < glance_at < nav_at < stats_at),
        ("seven-section-order", candidate["section_ids"][:7] == expected_sections),
        ("reference-seven-section-order", reference["section_ids"][:7] == expected_sections),
        ("navigation-targets", candidate["nav_hrefs"] == expected_sections),
        ("twelve-chart-order", candidate["charts"] == chart_order),
        ("reference-twelve-chart-order", reference["charts"] == chart_order),
        ("container-width", candidate["max_width"] == reference["max_width"] == 800),
        ("title-scale", abs(candidate["h1_size"] - reference["h1_size"]) <= 2),
        ("card-nesting", candidate["max_article_depth"] <= max(1, reference["max_article_depth"] + 1)),
        ("shadow-density", candidate["shadow_declarations"] <= reference["shadow_declarations"] + 1),
        ("radius-scale", abs(candidate["radius_median"] - reference["radius_median"]) <= 4),
        ("narrative-depth", candidate["paragraphs"] >= 20),
        ("action-blocks", candidate["pre_blocks"] >= 4),
        ("section-content-depth", all(len(candidate["section_text"].get(section, "")) >= 80 for section in expected_sections)),
        ("action-block-placement", candidate["section_pre_blocks"].get("section-features", 0) >= 4 and candidate["section_pre_blocks"].get("section-patterns", 0) >= 2 and candidate["section_pre_blocks"].get("section-horizon", 0) >= 3),
        ("localized-headings", not candidate["machine_headings"]),
        ("localized-chart-labels", not candidate["machine_chart_labels"]),
        ("chart-information-depth", candidate["chart_contexts"] == len(candidate["charts"]) and candidate["chart_shares"] == candidate["chart_rows"]),
        ("coverage-disclaimer-centralized", candidate["coverage_disclaimers"] == 0),
        ("no-sidebar", 'class="sidebar"' not in candidate_html),
    ]
    serialized = [
        {"name": name, "passed": passed}
        for name, passed in checks
    ]
    return {
        "passed": all(item["passed"] for item in serialized),
        "score": sum(item["passed"] for item in serialized),
        "total": len(serialized),
        "checks": serialized,
        "candidate": candidate,
        "reference": reference,
    }


__all__ = ["compare_report_structure", "render_native_report"]
