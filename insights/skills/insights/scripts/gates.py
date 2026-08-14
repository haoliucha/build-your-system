#!/usr/bin/env python3
"""Low-cost release gates that must pass before a 200-session Insights run."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import insights as core
import native_analysis
import runner


VERSION = "0.4.0"
PREVIEW_DATA_VERSION = "primary-analyzed-only-v2"
DEFAULT_REFERENCE = Path.home() / ".claude" / "usage-data" / "report-2026-08-13-223345.html"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _official_snapshot(output: Path) -> dict[str, str]:
    candidates = [output / "report.html", output / "state.json", output / "manifest.json"]
    candidates.extend(sorted((output / "facets").glob("*.json")) if (output / "facets").exists() else [])
    return {
        path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in candidates
        if path.is_file()
    }


def write_preview_bundle(
    codex_home: str | Path,
    *,
    version: str,
    report_html: str,
    lenses: Mapping[str, Any],
    at_a_glance: Mapping[str, Any],
    comparison: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Atomically write preview-only artifacts below a versioned directory."""

    home = Path(codex_home).expanduser().resolve()
    output = home / "usage-data" / "insights"
    preview = output / "previews" / version
    before = _official_snapshot(output)
    payloads = {
        "report.html": report_html.encode("utf-8"),
        "lenses.json": _json_bytes(dict(lenses)),
        "at-a-glance.json": _json_bytes(dict(at_a_glance)),
        "comparison.json": _json_bytes(dict(comparison)),
        "metadata.json": _json_bytes(dict(metadata or {})),
    }
    for name, data in payloads.items():
        _atomic_write(preview / name, data)
    if _official_snapshot(output) != before:
        raise RuntimeError("preview gate changed an official Insights artifact")
    return {
        "report_path": str(preview / "report.html"),
        "comparison_path": str(preview / "comparison.json"),
        "lenses_path": str(preview / "lenses.json"),
    }


def _synthetic_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    aggregate = {
        "total_sessions": 83,
        "sessions_with_facets": 83,
        "date_range": {"start": "2026-05-29", "end": "2026-08-13"},
        "total_messages": 494,
        "lines_added": 18_420,
        "lines_removed": 5_210,
        "files_modified": 186,
        "days_active": 48,
        "messages_per_day": 10.3,
        "goal_categories": {"implement_feature": 51, "fix_bug": 34, "understand_codebase": 22},
        "tool_counts": {"exec_command": 241, "apply_patch": 132, "web__run": 28},
        "languages": {"Python": 96, "TypeScript": 74, "Markdown": 62},
        "session_types": {"iterative_refinement": 42, "single_task": 31, "exploration": 10},
        "response_time_distribution": {"2_to_10_seconds": 114, "10_to_30_seconds": 61, "1_to_2_minutes": 24},
        "median_response_time": 18,
        "avg_response_time": 37,
        "multi_clauding": {"overlap_events": 7, "sessions_involved": 11, "user_messages_during": 46},
        "message_hours": {"9": 78, "14": 61, "21": 83},
        "tool_error_categories": {"Command Failed": 17, "Edit Failed": 9},
        "success": {"correct_code_edits": 39, "good_debugging": 22, "good_explanations": 12},
        "outcomes": {"fully_achieved": 55, "mostly_achieved": 17, "partially_achieved": 8},
        "friction": {"wrong_approach": 18, "tool_failed": 11},
        "satisfaction": {"satisfied": 48, "likely_satisfied": 21, "dissatisfied": 9},
    }
    lenses = {
        "project_areas": {"areas": [
            {"name": "插件与代理系统", "session_count": 31, "description": "围绕插件真源、Skill 契约和多宿主一致性建立可验证的工程系统。"},
            {"name": "产品与内容实验", "session_count": 22, "description": "把产品假设、用户证据和内容分发串成可复用的验证流程。"},
            {"name": "数据与自动化", "session_count": 18, "description": "用确定性脚本处理数据，把模型判断留给真正需要语义的环节。"},
            {"name": "研究与技术评估", "session_count": 12, "description": "对上游实现、技术边界和真实运行结果做证据驱动的拆解。"},
        ]},
        "interaction_style": {
            "narrative": "你通常先追问 **meaning 是否对齐**，再决定实现路径。你不会把测试通过等同于产品正确，而是要求回到真实命令、真实报告和真实使用情境。\n\n你偏好把复杂任务拆成可判定的阶段门禁：先验证数据语义，再验证模型输出，最后才运行昂贵的全量任务。这让返工更早暴露，也让每次模型调用都有明确职责。\n\n当结果与预期有差距时，你会给出非常具体的界面或措辞反馈，并要求把这些反馈沉淀到系统，而不是只修当前截图。",
            "key_pattern": "先验证 meaning，再验证实现，最后才扩大样本。",
        },
        "what_works": {"intro": "最有效的协作来自真实证据、明确验收和分阶段放大。", "impressive_workflows": [
            {"title": "上游实现蒸馏", "description": "先核查真实二进制、报告和官方边界，再把可观察语义转成 Codex 适配。"},
            {"title": "低成本门禁", "description": "先用合成报告和小型语义探针发现结构问题，避免把 200 会话运行当作 UI 测试。"},
            {"title": "事务化长任务", "description": "把模型任务、缓存与最终报告拆开提交，使失败不会覆盖旧的可用产物。"},
        ]},
        "friction_analysis": {"intro": "主要摩擦不是任务太复杂，而是验证发生得太晚或证据链不完整。", "categories": [
            {"title": "过早宣称完成", "description": "实现只覆盖了协议或测试外壳，却被描述成完整洞察能力。", "examples": ["报告能生成但语义内容是占位", "自动化全绿却没有真实模型分析"]},
            {"title": "缺少直接证据的诊断", "description": "没有先核查真实运行与上游实现，导致修复方向偏离根因。", "examples": ["把提交无响应误判为 helper 计算慢", "把隐私护栏当成命令核心 meaning"]},
            {"title": "昂贵验收前置不足", "description": "在全量运行前没有先比较结构和内容深度，放大了返工成本。", "examples": ["200 会话后才发现报告排版差异", "Lens 输入仍取固定前 50 条"]},
        ]},
        "suggestions": {
            "agents_md_additions": [
                {"addition": "昂贵真实运行前必须通过合成报告和缓存预览。", "why": "把结构与内容问题提前到秒级和分钟级门禁。", "prompt_scaffold": "先生成不提交的候选报告，与参考报告逐项对比；未通过时禁止运行全量任务。"},
                {"addition": "上游复刻任务必须标注观察事实与本地增强。", "why": "避免把安全工程或自主设计误写成原生 meaning。", "prompt_scaffold": "分别列出官方事实、本机观察和 Codex 适配，再决定实现。"},
            ],
            "features_to_try": [
                {"feature": "隔离的 codex exec", "one_liner": "让模型只负责结构化语义 Job。", "why_for_you": "可恢复且不会让主 Agent 变成调度器。", "example_code": "codex exec --ephemeral --json --output-schema schema.json -"},
                {"feature": "持久化进度", "one_liner": "每个 Facet 成功后立即落盘。", "why_for_you": "长任务被暂停后仍能从已完成结果继续。", "example_code": "$insights --resume <run-id>"},
            ],
            "usage_patterns": [
                {"title": "先小后大", "suggestion": "先验证语义和报告，再扩大样本。", "detail": "3 会话只验证 Facet；缓存预览验证 Lens 与 UI；200 会话只做最终统计。", "copyable_prompt": "先跑低成本门禁并给我预览路径；我确认后再启动 200 会话。"},
                {"title": "最新纠正优先", "suggestion": "冲突指令按时间排序。", "detail": "把最新明确纠正作为当前偏好，旧要求只保留为演进证据。", "copyable_prompt": "找出相互冲突的要求，按日期列出，并以最新明确纠正为准。"},
            ],
        },
        "on_the_horizon": {"intro": "下一阶段可以把一次性复盘变成持续的协作质量系统。", "opportunities": [
            {"title": "月度协作基线", "whats_possible": "比较成功率、摩擦和工作流随时间的变化。", "how_to_try": "先保存本月固定 200 主会话基线。", "copyable_prompt": "比较本月与上月 Insights，只报告有双期证据的变化。"},
            {"title": "跨项目验收矩阵", "whats_possible": "发现哪些验收方式能跨仓库复用。", "how_to_try": "从三个活跃项目提取完成条件。", "copyable_prompt": "按项目列出验收命令、真实证据和最常见失败点。"},
            {"title": "规则有效性回测", "whats_possible": "判断写入 AGENTS.md 的规则是否真的减少返工。", "how_to_try": "为每条新规则记录生效日期并比较前后会话。", "copyable_prompt": "回测这条规则生效前后的摩擦变化，避免只做主观评价。"},
        ]},
        "fun_ending": {"headline": "你不是在追求更多自动化，而是在追求更早的真相。", "detail": "最有辨识度的习惯，是在系统看似完成时继续追问：它真的复刻了用户看到的 meaning 吗？"},
    }
    glance = {
        "whats_working": "真实证据、明确验收与分阶段放大，让复杂重构逐渐形成可复用方法。",
        "whats_hindering": "问题往往不是能力不足，而是结构、语义和真实运行的验收顺序太晚。",
        "quick_wins": "把合成报告、3 会话 Facet 探针和缓存 Lens 预览固定为全量运行前门禁。",
        "ambitious_workflows": "建立按月比较的协作质量基线，让规则、工具和工作流都能被回测。",
    }
    coverage = {"primary_total": 83, "analyzed": 83, "skipped": 0, "remaining": 0, "subagent": 41, "automation": 7, "headless": 12}
    return aggregate, lenses, glance, coverage


def run_synthetic_gate(codex_home: str | Path, reference: str | Path) -> dict[str, Any]:
    home = Path(codex_home).expanduser().resolve()
    output = home / "usage-data" / "insights"
    before = _official_snapshot(output)
    aggregate, lenses, glance, coverage = _synthetic_inputs()
    report = core.render_report([], aggregate=aggregate, lenses=lenses, at_a_glance=glance, coverage=coverage)
    reference_html = Path(reference).read_text(encoding="utf-8")
    comparison = core.compare_report_structure(report, reference_html)
    preview = output / "previews" / VERSION
    synthetic_path = preview / "synthetic-report.html"
    comparison_path = preview / "synthetic-comparison.json"
    _atomic_write(synthetic_path, report.encode("utf-8"))
    _atomic_write(comparison_path, _json_bytes(comparison))
    if _official_snapshot(output) != before:
        raise RuntimeError("synthetic gate changed an official Insights artifact")
    return {
        "synthetic_report_path": str(synthetic_path),
        "comparison_path": str(comparison_path),
        "comparison": comparison,
    }


def _map_counter(values: Any, mapping: Mapping[str, str], allowed: set[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    if not isinstance(values, Mapping):
        return result
    for raw, count in values.items():
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            continue
        key = mapping.get(str(raw), str(raw))
        if key in allowed:
            result[key] = result.get(key, 0) + count
    return result


def _legacy_model_facet(value: Mapping[str, Any]) -> dict[str, Any] | None:
    goal_map = {
        "coding": "implement_feature", "implementation": "implement_feature",
        "debugging": "debug_investigate", "testing": "write_tests",
        "research": "understand_codebase", "analysis": "analyze_data",
        "data_analysis": "analyze_data", "writing": "write_docs",
        "documentation": "write_docs", "configuration": "configure_system",
        "automation": "write_script_tool", "deployment": "deploy_infra",
        "review": "understand_codebase", "planning": "understand_codebase",
        "design": "implement_feature", "project_management": "configure_system",
    }
    friction_map = {
        "claude_got_blocked": "codex_got_blocked",
        "user_unclear": "misunderstood_request",
    }
    satisfaction_map = {"positive": "satisfied", "negative": "dissatisfied", "correction": "dissatisfied"}
    model = {
        "underlying_goal": str(value.get("underlying_goal", "")),
        "goal_categories": _map_counter(value.get("goal_categories"), goal_map, set(native_analysis.GOAL_CATEGORIES)),
        "outcome": value.get("outcome"),
        "user_satisfaction_counts": _map_counter(value.get("user_satisfaction_counts"), satisfaction_map, set(native_analysis.SATISFACTION_SIGNALS)),
        "claude_helpfulness": value.get("claude_helpfulness"),
        "session_type": value.get("session_type"),
        "friction_counts": _map_counter(value.get("friction_counts"), friction_map, set(native_analysis.FRICTION_TYPES)),
        "friction_detail": str(value.get("friction_detail", "")),
        "primary_success": value.get("primary_success"),
        "brief_summary": str(value.get("brief_summary", "")),
        "user_instructions_to_codex": list(value.get("user_instructions_to_codex", [])) if isinstance(value.get("user_instructions_to_codex"), list) else [],
        "evidence_anchors": list(value.get("evidence_anchors", [])) if isinstance(value.get("evidence_anchors"), list) else [],
    }
    if not model["goal_categories"]:
        return None
    try:
        return core.validate_native_facet(model)
    except core.FacetValidationError:
        return None


def load_primary_preview_material(codex_home: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    home = Path(codex_home).expanduser().resolve()
    records, stats = core.discover_sessions(home, include_stats=True)
    by_key = {record["session_key"]: record for record in records}
    state_path = home / "usage-data" / "insights" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    sessions = state.get("sessions", {}) if isinstance(state, Mapping) else {}
    facets: list[dict[str, Any]] = []
    for session_key, entry in sessions.items():
        record = by_key.get(str(session_key))
        if record is None or not isinstance(entry, Mapping):
            continue
        if str(entry.get("source_hash", "")) != str(record.get("source_hash", "")):
            continue
        relative = str(entry.get("facet_file", ""))
        if not re.fullmatch(r"facets/[0-9a-f]{16}-[0-9a-f]{16}\.json", relative):
            continue
        path = (state_path.parent / relative).resolve()
        try:
            path.relative_to((state_path.parent / "facets").resolve())
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        model = _legacy_model_facet(raw)
        if model is None:
            continue
        facets.append(
            {
                **model,
                "session_key": session_key,
                "date": str(record["meta"].get("start_time", ""))[:10],
                "project_alias": record["project_alias"],
                "project_label": record["project_label"],
                "session_meta": {
                    **core._public_session_meta(record["meta"], record["project_alias"], record["project_label"]),
                    "session_key": session_key,
                },
            }
        )
    facet_keys = {facet["session_key"] for facet in facets}
    metas = []
    for record in records:
        public = core._public_session_meta(record["meta"], record["project_alias"], record["project_label"])
        public["session_key"] = record["session_key"]
        metas.append(public)
    coverage = {
        "primary_total": int(stats.get("primary_total", len(records))),
        "primary_eligible": len(records),
        "eligible": len(records),
        "analyzed": len(facet_keys),
        "cached": len(facet_keys),
        "selected": 0,
        "succeeded": 0,
        "skipped": 0,
        "remaining": max(0, len(records) - len(facet_keys)),
        "subagent": int(stats.get("subagent", 0)),
        "automation": int(stats.get("automation", 0)),
        "headless": int(stats.get("headless", 0)),
        "snapshot_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return metas, facets, coverage


async def run_facet_probe(codex_home: str | Path) -> dict[str, Any]:
    home = Path(codex_home).expanduser().resolve()
    records = list(core.discover_sessions(home))
    materials = [(len(core.normalize_session(core._model_session(record))), record) for record in records]
    if len(materials) < 3:
        raise RuntimeError("fewer than three eligible primary sessions are available")
    ordered = sorted(materials, key=lambda item: item[0])
    selected = [ordered[0][1], ordered[len(ordered) // 2][1], ordered[-1][1]]
    probe_dir = home / "usage-data" / "insights" / "previews" / VERSION / f"facet-probe-{uuid.uuid4().hex}"
    executor = runner.CodexExecExecutor()
    summaries: list[dict[str, Any]] = []
    try:
        for position, record in enumerate(selected):
            material = core.normalize_session(core._model_session(record))
            chunks = core.split_analysis_text(material)
            if len(chunks) > 1:
                jobs = [
                    runner.ModelJob(
                        f"probe-chunk-{position}-{index}", "chunk_summary",
                        core.build_chunk_summary_prompt(chunk, index=index, total=len(chunks), language="zh-CN"),
                        {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False},
                        "gpt-5.6-luna", "low",
                    )
                    for index, chunk in enumerate(chunks)
                ]
                results = await asyncio.gather(*(executor.execute(job, probe_dir) for job in jobs))
                if any(result.error or not result.value for result in results):
                    raise RuntimeError("facet probe chunk summary failed")
                material = "[Long session - %d parts summarized]\n\n%s" % (
                    len(results), "\n\n".join(str(result.value["summary"]) for result in results)
                )
            raw = {
                "job_id": f"probe-facet-{position}", "kind": "session_facet",
                "prompt": core.build_facet_prompt(material, language="zh-CN"),
                "schema": runner._facet_json_schema(),
            }
            job = runner._model_job(raw, 0)
            result = await executor.execute(job, probe_dir)
            if result.error or not result.value:
                raise RuntimeError(f"facet probe failed: {result.error}")
            validated = core.validate_native_facet(result.value)
            user_turns = int(record.get("meta", {}).get("user_message_count", 0))
            semantic_concerns = _facet_probe_checks(
                material,
                validated,
                user_turns=user_turns,
            )
            summaries.append(
                {
                    "size": ("short", "medium", "long")[position],
                    "goal_categories": sorted(key for key, count in validated["goal_categories"].items() if count),
                    "explicit_goal_count": sum(validated["goal_categories"].values()),
                    "user_message_count": user_turns,
                    "satisfaction_signals": sorted(key for key, count in validated["user_satisfaction_counts"].items() if count),
                    "friction_types": sorted(key for key, count in validated["friction_counts"].items() if count),
                    "outcome": validated["outcome"],
                    "semantic_concerns": semantic_concerns,
                }
            )
    finally:
        await executor.terminate_all()
        shutil.rmtree(probe_dir, ignore_errors=True)
    path = home / "usage-data" / "insights" / "previews" / VERSION / "facet-probe.json"
    passed = all(not item["semantic_concerns"] for item in summaries)
    _atomic_write(path, _json_bytes({"passed": passed, "sessions": summaries}))
    return {"passed": passed, "path": str(path), "sessions": summaries}


def _valid_preview_cache(value: Mapping[str, Any], *, lens_prompt_version: str) -> bool:
    """Renderer iterations reuse a frozen semantic preview until prompts change."""

    return (
        value.get("lens_prompt_version") == lens_prompt_version
        and isinstance(value.get("lenses"), Mapping)
        and isinstance(value.get("at_a_glance"), Mapping)
    )


def _facet_probe_checks(
    material: str,
    facet: Mapping[str, Any],
    *,
    user_turns: int | None = None,
) -> list[str]:
    """Return semantic probe concerns; schema validity alone is insufficient."""

    concerns: list[str] = []
    goal_total = sum(int(value) for value in facet.get("goal_categories", {}).values())
    deterministic_user_turns = max(
        1,
        int(user_turns) if user_turns is not None else material.count("User:"),
    )
    if goal_total < 1 or goal_total > deterministic_user_turns * 3:
        concerns.append("explicit_goal_count_out_of_range")
    anchors = [str(value).strip() for value in facet.get("evidence_anchors", []) if str(value).strip()]
    if not anchors:
        concerns.append("missing_evidence_anchors")
    satisfaction = {
        key for key, count in facet.get("user_satisfaction_counts", {}).items() if int(count) > 0
    }
    lower = material.casefold()
    cue_groups = {
        "happy": ("great", "perfect", "太好了", "很好"),
        "satisfied": ("thanks", "looks good", "that works", "谢谢", "可以了"),
        "likely_satisfied": ("ok now", "好，接下来", "可以，接下来"),
        "dissatisfied": ("not right", "try again", "不对", "重来"),
        "frustrated": ("broken", "give up", "崩了", "放弃"),
    }
    for signal in satisfaction:
        if not any(cue.casefold() in lower for cue in cue_groups.get(signal, ())):
            concerns.append(f"unsupported_satisfaction:{signal}")
    if any(int(value) > 0 for value in facet.get("friction_counts", {}).values()):
        if not str(facet.get("friction_detail", "")).strip() or not anchors:
            concerns.append("unsupported_friction")
    return concerns


async def run_lens_preview(codex_home: str | Path, reference: str | Path) -> dict[str, Any]:
    home = Path(codex_home).expanduser().resolve()
    output = home / "usage-data" / "insights"
    before = _official_snapshot(output)
    metas, facets, coverage = load_primary_preview_material(home)
    if not facets:
        raise RuntimeError("no existing cached facets can be mapped to primary sessions")
    facet_map = {facet["session_key"]: facet for facet in facets}
    analyzed_metas = [meta for meta in metas if str(meta.get("session_key")) in facet_map]
    aggregate = core.aggregate_usage(analyzed_metas, facet_map)
    material = core.build_lens_material(aggregate, facets, coverage=coverage)
    evidence_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
    preview = output / "previews" / VERSION
    cache_path = preview / "lens-cache.json"
    cached: dict[str, Any] = {}
    try:
        candidate = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(candidate, Mapping) and _valid_preview_cache(
            candidate, lens_prompt_version=core.LENS_PROMPT_VERSION
        ):
            cached = dict(candidate)
    except (OSError, json.JSONDecodeError):
        pass
    raw_lenses = cached.get("lenses") if isinstance(cached.get("lenses"), Mapping) else None
    glance = cached.get("at_a_glance") if isinstance(cached.get("at_a_glance"), Mapping) else None
    if raw_lenses is None or glance is None:
        run_dir = preview / f"lens-run-{uuid.uuid4().hex}"
        executor = runner.CodexExecExecutor()
        try:
            raw_jobs = core.build_lens_jobs({"material": material}, language="zh-CN")
            jobs = [runner._model_job({**raw, "job_id": f"preview-{raw['lens_id']}"}, 0) for raw in raw_jobs]
            results = await asyncio.gather(*(executor.execute(job, run_dir) for job in jobs))
            if any(result.error or not result.value for result in results):
                errors = [result.error for result in results if result.error]
                raise RuntimeError("lens preview failed: " + "; ".join(errors))
            raw_lenses = {
                job.lens_id: core.validate_lens_result(job.lens_id, result.value)
                for job, result in zip(jobs, results)
            }
            glance_job = core.build_at_a_glance_job(
                {"aggregate": aggregate, "lens_material": material}, raw_lenses, language="zh-CN"
            )
            model_job = runner._model_job({**glance_job, "job_id": "preview-at-a-glance"}, 1)
            glance_result = await executor.execute(model_job, run_dir)
            if glance_result.error or not glance_result.value:
                raise RuntimeError("at-a-glance preview failed: " + str(glance_result.error))
            glance = core.validate_at_a_glance(glance_result.value)
            _atomic_write(
                cache_path,
                _json_bytes(
                    {
                        "evidence_sha256": evidence_hash,
                        "lens_prompt_version": core.LENS_PROMPT_VERSION,
                        "preview_data_version": PREVIEW_DATA_VERSION,
                        "aggregate": aggregate,
                        "coverage": coverage,
                        "lenses": raw_lenses,
                        "at_a_glance": glance,
                    }
                ),
            )
        finally:
            await executor.terminate_all()
            shutil.rmtree(run_dir, ignore_errors=True)
    else:
        # 0.4 previews are semantic snapshots. Active JSONL may keep changing,
        # but renderer/comparator work must not silently spend eight more model
        # calls. Migrate the first 0.4 cache once, then keep its aggregate and
        # coverage frozen until LENS_PROMPT_VERSION changes.
        if (
            cached.get("preview_data_version") != PREVIEW_DATA_VERSION
            or not isinstance(cached.get("aggregate"), Mapping)
            or not isinstance(cached.get("coverage"), Mapping)
        ):
            cached.update({
                "aggregate": aggregate,
                "coverage": coverage,
                "preview_data_version": PREVIEW_DATA_VERSION,
            })
            _atomic_write(cache_path, _json_bytes(cached))
        aggregate = dict(cached["aggregate"])
        coverage = dict(cached["coverage"])
        evidence_hash = str(cached.get("evidence_sha256", evidence_hash))
    render_lenses = dict(raw_lenses)
    render_lenses["project_areas"] = native_analysis.finalize_project_areas(
        raw_lenses["project_areas"], aggregate.get("projects", {}), language="zh-CN"
    )
    report = core.render_report(
        facets, aggregate=aggregate, lenses=render_lenses,
        at_a_glance=glance, coverage=coverage, language="zh-CN",
    )
    if core.privacy_violations(report):
        raise core.PrivacyError("preview report contains a private value")
    comparison = core.compare_report_structure(
        report, Path(reference).read_text(encoding="utf-8")
    )
    bundle = write_preview_bundle(
        home,
        version=VERSION,
        report_html=report,
        lenses=render_lenses,
        at_a_glance=glance,
        comparison=comparison,
        metadata={
            "gate": "lens-only-preview",
            "primary_total": coverage["primary_total"],
            "analyzed": coverage["analyzed"],
            "evidence_sha256": evidence_hash,
            "lens_prompt_version": core.LENS_PROMPT_VERSION,
            "report_schema_version": core.REPORT_SCHEMA_VERSION,
        },
    )
    if _official_snapshot(output) != before:
        raise RuntimeError("lens preview changed an official Insights artifact")
    return {**bundle, "comparison": comparison, "coverage": coverage}


async def _main_async(args: argparse.Namespace) -> int:
    if args.gate == "synthetic":
        result = run_synthetic_gate(args.codex_home, args.reference)
    elif args.gate == "facet-probe":
        result = await run_facet_probe(args.codex_home)
    elif args.gate == "lens-preview":
        result = await run_lens_preview(args.codex_home, args.reference)
    else:
        synthetic = run_synthetic_gate(args.codex_home, args.reference)
        if not synthetic["comparison"]["passed"]:
            print(json.dumps({"status": "blocked", "gate": "synthetic", "result": synthetic}, ensure_ascii=False), flush=True)
            return 1
        probe = await run_facet_probe(args.codex_home)
        preview = await run_lens_preview(args.codex_home, args.reference)
        result = {"synthetic": synthetic, "facet_probe": probe, "lens_preview": preview}
    passed = bool(result.get("passed", result.get("comparison", {}).get("passed", True)))
    if args.gate == "all":
        passed = bool(
            result["synthetic"]["comparison"]["passed"]
            and result["facet_probe"]["passed"]
            and result["lens_preview"]["comparison"]["passed"]
        )
    if not passed:
        print(json.dumps({"status": "blocked", "gate": args.gate, "result": result}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex Insights 0.4 pre-200 release gates")
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--gate", choices=("synthetic", "facet-probe", "lens-preview", "all"), default="all")
    return asyncio.run(_main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
