#!/usr/bin/env python3
"""Meaning-parity analysis primitives for Codex ``$insights``.

The functions in this module deliberately mirror the user-visible analysis
pipeline of Claude Code 2.1.228:

``normalized session -> native facet -> seven lenses -> At-a-Glance``.

They are pure and model-free.  The caller is responsible for redacting source
material before calling :func:`normalize_session`, and for sending the prompts
to a model.  Cache safety, transactions, and report rendering live outside
this module; they are implementation guardrails rather than analysis stages.
"""

from __future__ import annotations

import json
from pathlib import PurePath
from typing import Any, Iterable, Mapping, Sequence


USER_TEXT_LIMIT = 500
ASSISTANT_TEXT_LIMIT = 300
LONG_SESSION_THRESHOLD = 30_000
CHUNK_SIZE = 25_000

OUTCOMES = frozenset(
    {
        "fully_achieved",
        "mostly_achieved",
        "partially_achieved",
        "not_achieved",
        "unclear_from_transcript",
    }
)
HELPFULNESS_LEVELS = frozenset(
    {
        "unhelpful",
        "slightly_helpful",
        "moderately_helpful",
        "very_helpful",
        "essential",
    }
)
SESSION_TYPES = frozenset(
    {
        "single_task",
        "multi_task",
        "iterative_refinement",
        "exploration",
        "quick_question",
    }
)
PRIMARY_SUCCESSES = frozenset(
    {
        "none",
        "fast_accurate_search",
        "correct_code_edits",
        "good_explanations",
        "proactive_help",
        "multi_file_changes",
        "good_debugging",
    }
)

NATIVE_FACET_FIELDS = (
    "underlying_goal",
    "goal_categories",
    "outcome",
    "user_satisfaction_counts",
    "claude_helpfulness",
    "session_type",
    "friction_counts",
    "friction_detail",
    "primary_success",
    "brief_summary",
)
FACET_EXTENSION_FIELDS = frozenset(
    {
        # Claude's downstream suggestions prompt accepts user instructions but
        # its 2.1.228 facet prompt does not populate them.  The Codex adapter
        # may populate this explicitly so AGENTS.md suggestions have evidence.
        "user_instructions_to_codex",
        "evidence_anchors",
    }
)

LENS_IDS = (
    "project_areas",
    "interaction_style",
    "what_works",
    "friction_analysis",
    "suggestions",
    "on_the_horizon",
    "fun_ending",
)


class InsightsError(ValueError):
    """Raised when the semantic analysis pipeline is used out of order."""


class FacetValidationError(InsightsError):
    """Raised when model output does not match a native analysis schema."""


def _language_instruction(language: str) -> str:
    if not isinstance(language, str) or not language.strip():
        raise InsightsError("language must be a non-empty BCP 47 tag")
    return (
        f"OUTPUT LANGUAGE: {language}. Write every human-readable free-text value "
        "in that language. Keep JSON field names and canonical enum/category keys in English."
    )


def _text(value: Any) -> str:
    """Return user-visible text from common Codex event representations."""

    if isinstance(value, str):
        return value
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Mapping):
            candidate = item.get("text")
            if not isinstance(candidate, str):
                candidate = item.get("input_text") or item.get("output_text")
            if isinstance(candidate, str):
                parts.append(candidate)
    return "\n".join(parts)


def _project_label(session: Mapping[str, Any]) -> str:
    """Choose a useful project label without copying an absolute path."""

    explicit = session.get("project_label") or session.get("project_alias")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    cwd = session.get("cwd") or session.get("project_path")
    if isinstance(cwd, str) and cwd.strip():
        name = PurePath(cwd).name
        return name or "unknown"
    return "unknown"


def normalize_session(session: Mapping[str, Any]) -> str:
    """Normalize a redacted session using Claude's 500/300/tool-label shape.

    User text is capped at 500 characters, assistant text at 300 characters,
    and tool output is intentionally replaced by ``[Tool: <name>]``.  This is
    the material used for direct facet extraction or long-session chunking.
    """

    session_key = str(session.get("session_key") or session.get("session_id") or "unknown")
    start = str(session.get("start") or session.get("start_time") or session.get("date") or "unknown")
    duration = session.get("duration_minutes")
    if duration is None:
        seconds = session.get("duration_seconds")
        duration = round(float(seconds) / 60) if isinstance(seconds, (int, float)) else "unknown"

    lines = [
        f"Session: {session_key}",
        f"Date: {start}",
        f"Project: {_project_label(session)}",
        f"Duration: {duration} minutes",
        "",
    ]
    events = session.get("events", ())
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        events = ()
    for event in events:
        if not isinstance(event, Mapping):
            continue
        role = str(event.get("role") or event.get("type") or "").casefold()
        if role in {"user", "user_message"}:
            body = _text(event.get("text") if "text" in event else event.get("content"))
            lines.append(f"User: {body[:USER_TEXT_LIMIT]}")
        elif role in {"assistant", "agent", "assistant_message"}:
            body = _text(event.get("text") if "text" in event else event.get("content"))
            lines.append(f"Assistant: {body[:ASSISTANT_TEXT_LIMIT]}")
        elif role in {"tool", "tool_use", "function_call", "custom_tool_call"}:
            name = event.get("name") or event.get("tool_name") or event.get("tool") or "unknown"
            lines.append(f"[Tool: {name}]")
    return "\n".join(lines)


def split_analysis_text(text: str) -> list[str]:
    """Split only long sessions into contiguous 25k-character chunks.

    Claude 2.1.228 uses a 30k threshold and fixed 25k character slices.  Fixed
    slicing is intentional: every character, including a single oversized
    event, is retained and the final chunk always covers the end of a session.
    """

    if not isinstance(text, str):
        raise TypeError("analysis text must be a string")
    if not text:
        return []
    if len(text) <= LONG_SESSION_THRESHOLD:
        return [text]
    return [text[offset : offset + CHUNK_SIZE] for offset in range(0, len(text), CHUNK_SIZE)]


def build_chunk_summary_prompt(
    chunk: str, *, index: int = 0, total: int = 1, language: str = "zh-CN"
) -> str:
    """Build the native-like map prompt used for one long-session chunk."""

    return f"""You are summarizing chunk {index + 1} of {total} from one Codex session.
{_language_instruction(language)}
Summarize: (1) what the user requested, (2) what Codex did, including tools and
files, (3) friction or corrections, and (4) the outcome. Preserve filenames,
error messages, explicit user feedback, and the final result. Write 3-5 dense
sentences. Do not invent context from another chunk.

SESSION CHUNK
{chunk}
"""


def build_facet_prompt(session_material: str, *, language: str = "zh-CN") -> str:
    """Build the native session-facet extraction prompt."""

    return f"""Analyze this single Codex session and respond with ONLY one valid JSON object.
{_language_instruction(language)}

Count only explicit user goals. Do not count Codex's autonomous exploration,
intermediate plans, or self-created subtasks as user goals. Infer satisfaction
only from the following explicit satisfaction signals observed in Claude Code 2.1.228:
- "Yay!", "great!", or "perfect!" -> happy
- "thanks", "looks good", or "that works" -> satisfied
- "ok, now let's..." and continuing without complaint -> likely_satisfied
- "that's not right" or "try again" -> dissatisfied
- "this is broken" or "I give up" -> frustrated

For friction_counts, use these canonical categories when applicable:
- misunderstood_request: Codex interpreted the request incorrectly
- wrong_approach: the goal was right but the solution method was wrong
- buggy_code: generated or edited code did not work correctly
- user_rejected_action: the user explicitly rejected or stopped an action
- excessive_changes: Codex over-engineered or changed too much

If the session is only a short setup, greeting, or warm-up, put
warmup_minimal in goal_categories. It is not a session_type. Describe specific
friction without double-counting the same event. Judge whether Codex helped the
user reach the underlying goal, not merely whether tools ran.

Required JSON fields:
- underlying_goal: string
- goal_categories: object mapping category names to integer counts
- outcome: fully_achieved | mostly_achieved | partially_achieved |
  not_achieved | unclear_from_transcript
- user_satisfaction_counts: object mapping explicit signal names to integer counts
- claude_helpfulness: unhelpful | slightly_helpful | moderately_helpful |
  very_helpful | essential
- session_type: single_task | multi_task | iterative_refinement | exploration |
  quick_question
- friction_counts: object mapping friction categories to integer counts
- friction_detail: concise string grounded in observed events
- primary_success: none | fast_accurate_search | correct_code_edits |
  good_explanations | proactive_help | multi_file_changes | good_debugging
- brief_summary: concise session summary

The Codex adaptation may additionally return user_instructions_to_codex as a
list of explicit reusable instructions and evidence_anchors as a short list of
event references. Never emit HTML.

SESSION MATERIAL
{session_material}
"""


def _require_object(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FacetValidationError(f"{label} must be a JSON object")
    return value


def _require_string(
    value: Any,
    *,
    field: str,
    allow_empty: bool = False,
    max_length: int = 8_000,
) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise FacetValidationError(f"{field} must be a non-empty string")
    if len(value) > max_length:
        raise FacetValidationError(f"{field} exceeds the {max_length}-character limit")
    return value


def _require_count_map(value: Any, *, field: str) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise FacetValidationError(f"{field} must be an object of integer counts")
    for key, count in value.items():
        if not isinstance(key, str) or not key.strip():
            raise FacetValidationError(f"{field} keys must be non-empty strings")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise FacetValidationError(f"{field}.{key} must be a non-negative integer")
    return value


def _require_enum(value: Any, *, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise FacetValidationError(f"invalid {field}: {value!r}")
    return value


def _require_string_list(
    value: Any,
    *,
    field: str,
    max_items: int = 20,
    max_item_length: int = 1_000,
) -> Sequence[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FacetValidationError(f"{field} must be an array of strings")
    if len(value) > max_items:
        raise FacetValidationError(f"{field} exceeds the {max_items}-item limit")
    for item in value:
        _require_string(item, field=field, max_length=max_item_length)
    return value


def validate_native_facet(value: Any) -> dict[str, Any]:
    """Validate Claude's native facet fields plus two Codex-safe extensions."""

    facet = _require_object(value, label="facet")
    missing = set(NATIVE_FACET_FIELDS) - set(facet)
    if missing:
        raise FacetValidationError(f"facet missing fields: {sorted(missing)}")
    unknown = set(facet) - set(NATIVE_FACET_FIELDS) - FACET_EXTENSION_FIELDS
    if unknown:
        raise FacetValidationError(f"facet has unknown fields: {sorted(unknown)}")

    _require_string(facet["underlying_goal"], field="underlying_goal", max_length=2_000)
    _require_count_map(facet["goal_categories"], field="goal_categories")
    _require_enum(facet["outcome"], field="outcome", allowed=OUTCOMES)
    _require_count_map(facet["user_satisfaction_counts"], field="user_satisfaction_counts")
    _require_enum(
        facet["claude_helpfulness"],
        field="claude_helpfulness",
        allowed=HELPFULNESS_LEVELS,
    )
    _require_enum(facet["session_type"], field="session_type", allowed=SESSION_TYPES)
    _require_count_map(facet["friction_counts"], field="friction_counts")
    _require_string(
        facet["friction_detail"],
        field="friction_detail",
        allow_empty=True,
        max_length=2_000,
    )
    _require_enum(
        facet["primary_success"], field="primary_success", allowed=PRIMARY_SUCCESSES
    )
    _require_string(facet["brief_summary"], field="brief_summary", max_length=2_000)
    if "user_instructions_to_codex" in facet:
        _require_string_list(facet["user_instructions_to_codex"], field="user_instructions_to_codex")
    if "evidence_anchors" in facet:
        _require_string_list(facet["evidence_anchors"], field="evidence_anchors")
    return dict(facet)


def _object_schema(required: Iterable[str], properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(required),
        "additionalProperties": False,
        "properties": dict(properties),
    }


def _array_of_object(
    required: Iterable[str],
    properties: Mapping[str, Any],
    *,
    min_items: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": _object_schema(required, properties)}
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


_STRING = {"type": "string"}

LENS_SCHEMAS: dict[str, dict[str, Any]] = {
    "project_areas": _object_schema(
        ("areas",),
        {
            "areas": _array_of_object(
                ("name", "session_count", "description"),
                {"name": _STRING, "session_count": {"type": "integer", "minimum": 1}, "description": _STRING},
            )
        },
    ),
    "interaction_style": _object_schema(
        ("narrative", "key_pattern"),
        {"narrative": _STRING, "key_pattern": _STRING},
    ),
    "what_works": _object_schema(
        ("intro", "impressive_workflows"),
        {
            "intro": _STRING,
            "impressive_workflows": _array_of_object(
                ("title", "description"), {"title": _STRING, "description": _STRING}
            ),
        },
    ),
    "friction_analysis": _object_schema(
        ("intro", "categories"),
        {
            "intro": _STRING,
            "categories": _array_of_object(
                ("category", "description", "examples"),
                {"category": _STRING, "description": _STRING, "examples": {"type": "array", "items": _STRING}},
            ),
        },
    ),
    "suggestions": _object_schema(
        ("agents_md_additions", "features_to_try", "usage_patterns"),
        {
            "agents_md_additions": _array_of_object(
                ("addition", "why", "prompt_scaffold"),
                {"addition": _STRING, "why": _STRING, "prompt_scaffold": _STRING},
                min_items=2,
                max_items=3,
            ),
            "features_to_try": _array_of_object(
                ("feature", "one_liner", "why_for_you", "example_code"),
                {"feature": _STRING, "one_liner": _STRING, "why_for_you": _STRING, "example_code": _STRING},
                min_items=2,
                max_items=3,
            ),
            "usage_patterns": _array_of_object(
                ("title", "suggestion", "detail", "copyable_prompt"),
                {"title": _STRING, "suggestion": _STRING, "detail": _STRING, "copyable_prompt": _STRING},
                min_items=2,
                max_items=3,
            ),
        },
    ),
    "on_the_horizon": _object_schema(
        ("intro", "opportunities"),
        {
            "intro": _STRING,
            "opportunities": _array_of_object(
                ("title", "whats_possible", "how_to_try", "copyable_prompt"),
                {"title": _STRING, "whats_possible": _STRING, "how_to_try": _STRING, "copyable_prompt": _STRING},
            ),
        },
    ),
    "fun_ending": _object_schema(
        ("headline", "detail"), {"headline": _STRING, "detail": _STRING}
    ),
}


_LENS_INSTRUCTIONS = {
    "project_areas": """Identify 4-5 meaningful project areas. Group related work, give an evidence-based session count and a concrete description. Exclude internal Codex housekeeping or the Insights run itself.""",
    "interaction_style": """Write a 2-3 paragraph second-person narrative about how the user collaborates with Codex. Use concrete examples from the material and end with one concise key pattern.""",
    "what_works": """Explain what works especially well, then select exactly three impressive, repeatable workflows. Each workflow needs a concrete title and description grounded in successful sessions.""",
    "friction_analysis": """Explain the main friction, then produce exactly three distinct root-cause categories with two concrete examples each. Separate Codex failures, user-side constraints, and external/tool constraints when the evidence supports it.""",
    "suggestions": """Return 2-3 actionable recommendations in each of three groups: additions the user can paste into AGENTS.md, relevant Codex features to try, and improved usage patterns. Every item must explain why it fits this user and include a copyable scaffold or example. Codex capability reference: Skills, subagents, MCP, headless `codex exec`, Fast mode, long-running goals, and isolated worktrees. Choose feature recommendations only from this reference and only when the evidence makes them relevant. Do not suggest unsupported Claude-only features.""",
    "on_the_horizon": """Describe what may become possible over the next 3-6 months and give exactly three ambitious but testable opportunities. Each needs a small first experiment and a copyable prompt.""",
    "fun_ending": """End with one warm, memorable qualitative observation about this user's distinctive way of working. Do not turn it into a statistic or generic praise.""",
}


def build_lens_jobs(
    material: Mapping[str, Any], *, language: str = "zh-CN"
) -> list[dict[str, Any]]:
    """Build seven separate jobs, each with Claude's native-like lens schema."""

    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    jobs: list[dict[str, Any]] = []
    for lens_id in LENS_IDS:
        prompt = f"""You are generating the `{lens_id}` section of a Codex Insights report.
{_language_instruction(language)}
{_LENS_INSTRUCTIONS[lens_id]}

Use only the compressed evidence below. Do not invent facts, quotations, or
statistics. Respect its coverage fields: when remaining sessions exist, state
that semantic conclusions cover only the analyzed facet subset. Respond with
ONLY a JSON object matching this schema:
{json.dumps(LENS_SCHEMAS[lens_id], ensure_ascii=False, sort_keys=True)}

COMPRESSED EVIDENCE
{encoded}
"""
        jobs.append(
            {
                "kind": "lens",
                "lens_id": lens_id,
                "prompt": prompt,
                "schema": LENS_SCHEMAS[lens_id],
            }
        )
    return jobs


def _validate_object_array(
    value: Any,
    *,
    field: str,
    fields: Iterable[str],
    count_field: str | None = None,
    string_list_field: str | None = None,
) -> Sequence[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise FacetValidationError(f"{field} must be a non-empty array")
    required = set(fields)
    for index, item in enumerate(value):
        obj = _require_object(item, label=f"{field}[{index}]")
        if set(obj) != required:
            raise FacetValidationError(f"{field}[{index}] must contain exactly {sorted(required)}")
        for key in required:
            if key == count_field:
                count = obj[key]
                if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                    raise FacetValidationError(f"{field}[{index}].{key} must be a positive integer")
            elif key == string_list_field:
                _require_string_list(obj[key], field=f"{field}[{index}].{key}")
            else:
                _require_string(obj[key], field=f"{field}[{index}].{key}")
    return value


def validate_lens_result(lens_id: str, value: Any) -> dict[str, Any]:
    """Validate one of the seven lens results without merging their schemas."""

    if lens_id not in LENS_SCHEMAS:
        raise FacetValidationError(f"unknown lens: {lens_id}")
    result = _require_object(value, label=lens_id)
    required = set(LENS_SCHEMAS[lens_id]["required"])
    if set(result) != required:
        raise FacetValidationError(f"{lens_id} must contain exactly {sorted(required)}")

    if lens_id == "project_areas":
        areas = _validate_object_array(
            result["areas"],
            field="areas",
            fields=("name", "session_count", "description"),
            count_field="session_count",
        )
        if not 4 <= len(areas) <= 5:
            raise FacetValidationError("project_areas.areas must contain 4-5 items")
    elif lens_id == "interaction_style":
        _require_string(result["narrative"], field="narrative")
        _require_string(result["key_pattern"], field="key_pattern")
    elif lens_id == "what_works":
        _require_string(result["intro"], field="intro")
        workflows = _validate_object_array(
            result["impressive_workflows"],
            field="impressive_workflows",
            fields=("title", "description"),
        )
        if len(workflows) != 3:
            raise FacetValidationError("what_works.impressive_workflows must contain 3 items")
    elif lens_id == "friction_analysis":
        _require_string(result["intro"], field="intro")
        categories = _validate_object_array(
            result["categories"],
            field="categories",
            fields=("category", "description", "examples"),
            string_list_field="examples",
        )
        if len(categories) != 3:
            raise FacetValidationError("friction_analysis.categories must contain 3 items")
        if any(len(category["examples"]) != 2 for category in categories):
            raise FacetValidationError("each friction category must contain 2 examples")
    elif lens_id == "suggestions":
        groups = (
            _validate_object_array(
            result["agents_md_additions"],
            field="agents_md_additions",
            fields=("addition", "why", "prompt_scaffold"),
            ),
            _validate_object_array(
            result["features_to_try"],
            field="features_to_try",
            fields=("feature", "one_liner", "why_for_you", "example_code"),
            ),
            _validate_object_array(
            result["usage_patterns"],
            field="usage_patterns",
            fields=("title", "suggestion", "detail", "copyable_prompt"),
            ),
        )
        if any(not 2 <= len(group) <= 3 for group in groups):
            raise FacetValidationError("each suggestions group must contain 2-3 items")
    elif lens_id == "on_the_horizon":
        _require_string(result["intro"], field="intro")
        opportunities = _validate_object_array(
            result["opportunities"],
            field="opportunities",
            fields=("title", "whats_possible", "how_to_try", "copyable_prompt"),
        )
        if len(opportunities) != 3:
            raise FacetValidationError("on_the_horizon.opportunities must contain 3 items")
    elif lens_id == "fun_ending":
        _require_string(result["headline"], field="headline")
        _require_string(result["detail"], field="detail")
    return dict(result)


AT_A_GLANCE_FIELDS = (
    "whats_working",
    "whats_hindering",
    "quick_wins",
    "ambitious_workflows",
)
AT_A_GLANCE_SCHEMA = _object_schema(AT_A_GLANCE_FIELDS, {key: _STRING for key in AT_A_GLANCE_FIELDS})


def build_at_a_glance_job(
    material: Mapping[str, Any],
    completed_lenses: Mapping[str, Any],
    *,
    language: str = "zh-CN",
) -> dict[str, Any]:
    """Build the eighth synthesis call after all seven lenses are complete."""

    if not isinstance(completed_lenses, Mapping):
        raise InsightsError("completed_lenses must be an object")
    missing = set(LENS_IDS) - set(completed_lenses)
    extra = set(completed_lenses) - set(LENS_IDS)
    if missing or extra:
        raise InsightsError(f"all seven lenses are required (missing={sorted(missing)}, extra={sorted(extra)})")
    validated = {lens_id: validate_lens_result(lens_id, completed_lenses[lens_id]) for lens_id in LENS_IDS}
    evidence = json.dumps(
        {"material": material, "lenses": validated},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    prompt = f"""Synthesize an At-a-Glance opening for this Codex Insights report.
{_language_instruction(language)}
Write 2-3 concrete coaching sentences for each field. Use no headline statistics
and no generic praise. `whats_hindering` must distinguish Codex mistakes from
user-side or external friction when the evidence supports that distinction.
`ambitious_workflows` should look 3-6 months ahead. Respect coverage limits and
never generalize an analyzed facet subset to all eligible sessions. Respond with ONLY JSON
matching this schema:
{json.dumps(AT_A_GLANCE_SCHEMA, ensure_ascii=False, sort_keys=True)}

ANALYSIS MATERIAL AND SEVEN COMPLETED LENSES
{evidence}
"""
    return {
        "kind": "at_a_glance",
        "prompt": prompt,
        "schema": AT_A_GLANCE_SCHEMA,
    }


def validate_at_a_glance(value: Any) -> dict[str, Any]:
    """Validate the four-field At-a-Glance synthesis."""

    result = _require_object(value, label="at_a_glance")
    required = set(AT_A_GLANCE_FIELDS)
    if set(result) != required:
        raise FacetValidationError(f"at_a_glance must contain exactly {sorted(required)}")
    for field in AT_A_GLANCE_FIELDS:
        _require_string(result[field], field=field)
    return dict(result)


__all__ = [
    "ASSISTANT_TEXT_LIMIT",
    "AT_A_GLANCE_FIELDS",
    "AT_A_GLANCE_SCHEMA",
    "CHUNK_SIZE",
    "FacetValidationError",
    "InsightsError",
    "LENS_IDS",
    "LENS_SCHEMAS",
    "LONG_SESSION_THRESHOLD",
    "NATIVE_FACET_FIELDS",
    "PRIMARY_SUCCESSES",
    "USER_TEXT_LIMIT",
    "build_at_a_glance_job",
    "build_chunk_summary_prompt",
    "build_facet_prompt",
    "build_lens_jobs",
    "normalize_session",
    "split_analysis_text",
    "validate_at_a_glance",
    "validate_lens_result",
    "validate_native_facet",
]
