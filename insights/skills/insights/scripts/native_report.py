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
        "no_data": "暂无数据",
        "median": "中位数",
        "average": "平均",
        "seconds": "秒",
        "multi_note": "并行期间消息：{during} / {total}（{percent}%）。检测条件：同一任务两条消息之间穿插另一任务消息。",
        "coverage_limit": "仍有 {remaining} 个合格会话尚未完成语义分析。确定性统计覆盖 {eligible} 个；叙事洞察覆盖 {analyzed} 个。",
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
        "no_data": "No data",
        "median": "Median",
        "average": "Average",
        "seconds": "seconds",
        "multi_note": "Messages during overlap: {during} / {total} ({percent}%). Detection requires another task between two messages from the same task.",
        "coverage_limit": "{remaining} eligible sessions have not completed semantic analysis. Deterministic stats cover {eligible}; narrative insights cover {analyzed}.",
    },
}

_LABELS_ZH = {
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
    "user_stopped_early": "用户提前停止",
    "wrong_file_or_location": "文件或位置错误",
    "excessive_changes": "改动过度",
    "slow_or_verbose": "缓慢或冗长",
    "tool_failed": "工具失败",
    "user_unclear": "用户意图不清",
    "external_issue": "外部问题",
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


def _paragraph(value: Any, class_name: str = "") -> str:
    class_attr = f' class="{class_name}"' if class_name else ""
    return f"<p{class_attr}>{_escape(value)}</p>"


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
) -> str:
    rows = _mapping(values)
    numeric = [float(value) for value in rows.values() if isinstance(value, (int, float)) and not isinstance(value, bool)]
    maximum = max(numeric, default=0.0)
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
        percent = 0 if maximum <= 0 else max(0, min(100, round(numeric_value / maximum * 100)))
        body.append(
            '<div class="chart-row">'
            f'<span class="chart-label">{_escape(labels.get(str(label), label))}</span>'
            f'<progress max="100" value="{percent}">{percent}%</progress>'
            f'<strong>{_number(raw_value)}</strong>'
            "</div>"
        )
    if not body:
        body.append(f'<p class="empty">{_escape(no_data)}</p>')
    return (
        f'<section class="chart-card" data-chart="{_escape(chart_id)}">'
        f"<h3>{_escape(title)}</h3>{''.join(body)}"
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


def _glance_card(title: str, body: Any, tone: str) -> str:
    return f'<article class="glance-card {tone}"><h3>{_escape(title)}</h3>{_paragraph(body)}</article>'


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
            f'<h3>{_escape(item.get("category"))}</h3>{_paragraph(item.get("description"))}{examples_html}</article>'
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

    coverage_html = "".join(
        f'<span><strong>{_escape(t[key])}</strong> {_number(coverage.get(key))}</span>'
        for key in ("eligible", "cached", "selected", "remaining")
    )
    remaining = _count(coverage.get("remaining"))
    coverage_notice = ""
    if remaining:
        coverage_notice = (
            '<p class="coverage-warning">'
            + _escape(
                t["coverage_limit"].format(
                    remaining=remaining,
                    eligible=_count(coverage.get("eligible")),
                    analyzed=_count(aggregate.get("sessions_with_facets")),
                )
            )
            + "</p>"
        )

    css = """
    :root{color-scheme:light;--canvas:#f4f5f7;--ink:#172033;--muted:#667085;--line:#dfe3e8;--card:#fff;--blue:#eaf2ff;--blue-ink:#175cd3;--green:#eaf8ef;--green-ink:#18794e;--red:#fff0f0;--red-ink:#b42318;--purple:#f3efff;--purple-ink:#6938ef;--yellow:#fff7df;--yellow-ink:#8a5b00;--shadow:0 8px 24px rgba(16,24,40,.07)}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}a{color:inherit}a:focus-visible,progress:focus-visible{outline:3px solid #84adff;outline-offset:3px}.page{display:grid;grid-template-columns:220px minmax(0,800px);gap:32px;justify-content:center;align-items:start;padding:32px 24px 72px}.sidebar{position:sticky;top:24px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:var(--shadow)}.sidebar h2{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}.sidebar nav{display:grid;gap:4px}.sidebar a{text-decoration:none;border-radius:9px;padding:8px 10px;font-size:.92rem}.sidebar a:hover{background:var(--blue);color:var(--blue-ink)}main{min-width:0}.hero{margin-bottom:22px}.hero h1{font-size:clamp(2rem,6vw,3.4rem);line-height:1.05;letter-spacing:-.04em;margin:0 0 12px}.hero p{margin:3px 0;color:var(--muted)}.coverage-warning{background:var(--yellow);border:1px solid #f4d77d;border-radius:12px;padding:10px 12px;color:var(--yellow-ink)!important}.glance{background:var(--yellow);border:1px solid #f4d77d;border-radius:20px;padding:22px;margin:20px 0}.glance>h2{margin:0 0 14px}.glance-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.glance-card{background:rgba(255,255,255,.72);border-radius:14px;padding:14px;border:1px solid rgba(138,91,0,.12)}.glance-card h3{font-size:.94rem;margin:0 0 6px;color:var(--yellow-ink)}.glance-card p{margin:0}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin:18px 0 28px}.stat{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:13px 10px;text-align:center}.stat span{display:block;color:var(--muted);font-size:.76rem}.stat strong{display:block;font-size:1.05rem;margin-top:4px}.report-section{scroll-margin-top:24px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:24px;margin:18px 0;box-shadow:var(--shadow)}.report-section>h2{margin:0 0 14px;font-size:1.5rem}.lead{font-size:1.04rem;color:#344054}.key-pattern{background:var(--blue);border-left:4px solid var(--blue-ink);padding:12px 14px;border-radius:0 10px 10px 0}.item-card,.action-card,.chart-card{border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0;background:#fff}.item-card h3,.action-card h3,.action-card h4,.chart-card h3{margin:0 0 8px}.item-card p,.action-card p{margin:6px 0}.item-heading{display:flex;gap:12px;justify-content:space-between;align-items:start}.pill{white-space:nowrap;background:var(--blue);color:var(--blue-ink);border-radius:999px;padding:3px 9px;font-size:.76rem}.success-card{background:var(--green);border-color:#b7e3c8}.friction-card{background:var(--red);border-color:#fac5c2}.future-card{background:var(--purple);border-color:#d9ccff}.section-features{border-top:5px solid var(--blue-ink)}.section-wins{border-top:5px solid var(--green-ink)}.section-friction{border-top:5px solid var(--red-ink)}.section-horizon{border-top:5px solid var(--purple-ink)}.subsection-title{font-size:1.12rem;margin:22px 0 8px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px}.chart-card{margin:0}.chart-row{display:grid;grid-template-columns:minmax(90px,1fr) 2fr auto;align-items:center;gap:10px;margin:9px 0;font-size:.84rem}.chart-label{overflow-wrap:anywhere}progress{width:100%;height:10px;border:0;border-radius:999px;overflow:hidden;background:#e9edf3}progress::-webkit-progress-bar{background:#e9edf3;border-radius:999px}progress::-webkit-progress-value{background:#4c80e8;border-radius:999px}progress::-moz-progress-bar{background:#4c80e8;border-radius:999px}.code-label{font-size:.78rem;color:var(--muted);margin-top:12px!important}.chart-note{color:var(--muted);font-size:.78rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0 0;background:#172033;color:#f8fafc;border-radius:10px;padding:12px;font-size:.84rem;line-height:1.5}code{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}.fun-ending{background:var(--yellow);border:1px solid #f4d77d;border-radius:16px;padding:18px;margin-top:18px}.fun-ending h3{margin:0 0 6px}.fun-ending p{margin:0}.method{color:var(--muted);font-size:.84rem;border-top:1px solid var(--line);margin-top:30px;padding-top:18px}.coverage{display:flex;flex-wrap:wrap;gap:10px 18px}.empty{color:var(--muted);font-style:italic}
    @media(max-width:900px){.page{grid-template-columns:180px minmax(0,1fr)}.stats{grid-template-columns:repeat(3,1fr)}.charts{grid-template-columns:1fr}}
    @media(max-width:640px){.page{display:block;padding:16px 12px 48px}.sidebar{position:static;margin-bottom:18px;padding:10px}.sidebar h2{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}.sidebar nav{display:flex;overflow-x:auto;gap:4px;white-space:nowrap;position:sticky;top:0}.sidebar a{background:#f8fafc}.glance-grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.report-section{padding:18px}.chart-row{grid-template-columns:minmax(80px,1fr) 1.5fr auto}.hero h1{font-size:2.25rem}}
    @media print{body{background:#fff}.page{display:block;padding:0}.sidebar{position:static;box-shadow:none;margin-bottom:16px}.sidebar nav{display:flex;flex-wrap:wrap}.report-section,.glance,.stat{box-shadow:none;break-inside:avoid}.charts{display:block}.chart-card{break-inside:avoid;margin:10px 0}pre{white-space:pre-wrap;color:#000;background:#f3f4f6;border:1px solid #d0d5dd}}
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
<aside class="sidebar"><h2>{_escape(t["nav"])}</h2><nav aria-label="{_escape(t["nav"])}">{nav_html}</nav></aside>
<main>
<header class="hero"><h1>{_escape(t["title"])}</h1><p>{_escape(t["subtitle"])}</p><p>{_escape(t["range"])}：{range_text}</p>{coverage_notice}</header>
<section class="glance" aria-labelledby="glance-title"><h2 id="glance-title">{_escape(t["glance"])}</h2><div class="glance-grid">
{_glance_card(t["working"], at_a_glance.get("whats_working"), "glance-success")}
{_glance_card(t["hindering"], at_a_glance.get("whats_hindering"), "glance-friction")}
{_glance_card(t["quick"], at_a_glance.get("quick_wins"), "glance-quick")}
{_glance_card(t["ambitious"], at_a_glance.get("ambitious_workflows"), "glance-future")}
</div></section>
<section class="stats" aria-label="headline statistics">
<div class="stat"><span>{_escape(t["messages"])}</span><strong>{_number(aggregate.get("total_messages"))}</strong></div>
<div class="stat"><span>{_escape(t["lines"])}</span><strong>{line_stat}</strong></div>
<div class="stat"><span>{_escape(t["files"])}</span><strong>{_number(aggregate.get("files_modified"))}</strong></div>
<div class="stat"><span>{_escape(t["days"])}</span><strong>{_number(aggregate.get("days_active"))}</strong></div>
<div class="stat"><span>{_escape(t["per_day"])}</span><strong>{_number(aggregate.get("messages_per_day"))}</strong></div>
</section>

<section class="report-section" id="section-work"><h2>{_escape(t["work"])}</h2>
{_project_areas(project_areas, t)}
<div class="charts">{charts["goals"]}</div></section>

<section class="report-section" id="section-usage"><h2>{_escape(t["usage"])}</h2>
{_paragraph(interaction.get("narrative"), "lead")}
<p class="key-pattern"><strong>{_escape(t["key_pattern"])}：</strong>{_escape(interaction.get("key_pattern"))}</p>
<div class="charts">{charts["tools"]}{charts["languages"]}{charts["session-types"]}{charts["response-time"]}{charts["multi-clauding"]}{charts["message-hours"]}{charts["tool-errors"]}</div></section>

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
{_paragraph(horizon.get("intro"), "lead")}<h3 class="subsection-title">{_escape(t["opportunities"])}</h3>{_opportunities(horizon, t)}
<aside class="fun-ending"><h3>{_escape(t["memorable"])}：{_escape(fun_ending.get("headline"))}</h3>{_paragraph(fun_ending.get("detail"))}</aside></section>

<footer class="method"><h2>{_escape(t["method"])}</h2><div class="coverage">{coverage_html}</div></footer>
</main>
</div>
</body>
</html>'''


__all__ = ["render_native_report"]
