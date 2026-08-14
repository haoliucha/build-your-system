#!/usr/bin/env python3
"""Persistent, deterministic ``codex exec`` runner for Codex Insights.

The runner owns scheduling, checkpoints, validation and commit.  Models only
receive one schema-bound analysis job at a time; they never orchestrate the run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import native_analysis


def _load_core():
    path = SCRIPT_DIR / "insights.py"
    spec = importlib.util.spec_from_file_location("codex_insights_core", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Insights core: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def _validate_release_receipt(path: str | Path, *, codex_home: str | Path) -> bool:
    """Validate the user-confirmed 0.4 preview receipt for a development run."""

    home = Path(codex_home).expanduser().resolve()
    preview = home / "usage-data" / "insights" / "previews" / "0.4.0"
    receipt_path = Path(path).expanduser().resolve()
    try:
        receipt_path.relative_to(preview.resolve())
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
        report = preview / "report.html"
        comparison = preview / "comparison.json"
        comparison_value = json.loads(comparison.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError):
        return False
    digest = lambda item: hashlib.sha256(item.read_bytes()).hexdigest()
    return bool(
        value.get("user_confirmed") is True
        and comparison_value.get("passed") is True
        and value.get("preview_report_sha256") == digest(report)
        and value.get("comparison_sha256") == digest(comparison)
    )


def _development_receipt_required(max_new_sessions: int) -> bool:
    manifest_path = SCRIPT_DIR.parents[2] / ".codex-plugin" / "plugin.json"
    try:
        version = str(json.loads(manifest_path.read_text(encoding="utf-8")).get("version", ""))
    except (OSError, json.JSONDecodeError):
        version = ""
    return max_new_sessions > 3 and version != "0.4.0"


MODEL_BY_KIND = {
    "chunk_summary": ("gpt-5.6-luna", "low"),
    "session_facet": ("gpt-5.6-terra", "medium"),
    "lens": ("gpt-5.6-sol", "high"),
    "at_a_glance": ("gpt-5.6-sol", "high"),
}
JOB_STATES = ("queued", "running", "succeeded", "skipped")
STAGES = (
    "inventory",
    "chunk_summary",
    "session_facet",
    "lens",
    "at_a_glance",
    "render",
    "commit",
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ModelJob:
    def __init__(
        self,
        job_id: str,
        kind: str,
        prompt: str,
        schema: Mapping[str, Any],
        model: str,
        effort: str,
        wave: int = 0,
        *,
        session_key: str | None = None,
        lens_id: str | None = None,
        raw: Mapping[str, Any] | None = None,
    ) -> None:
        self.job_id = job_id
        self.kind = kind
        self.prompt = prompt
        self.schema = dict(schema)
        self.model = model
        self.effort = effort
        self.wave = int(wave)
        self.session_key = session_key
        self.lens_id = lens_id
        self.raw = dict(raw or {})

    def public(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "prompt": self.prompt,
            "schema": self.schema,
            "model": self.model,
            "effort": self.effort,
            "wave": self.wave,
            "session_key": self.session_key,
            "lens_id": self.lens_id,
        }


class ExecResult:
    def __init__(
        self,
        value: Mapping[str, Any] | None = None,
        *,
        error: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        rate_limited: bool = False,
        retry_after: float = 0.0,
    ) -> None:
        self.value = dict(value) if isinstance(value, Mapping) else None
        self.error = error
        self.input_tokens = int(input_tokens)
        self.output_tokens = int(output_tokens)
        self.rate_limited = bool(rate_limited)
        self.retry_after = float(retry_after)


def _schema_path(run_dir: Path, job: ModelJob) -> Path:
    return run_dir / "exec" / f"{job.job_id}.schema.json"


def _partial_path(run_dir: Path, job: ModelJob) -> Path:
    return run_dir / "exec" / f"{job.job_id}.partial"


def build_exec_command(
    job: ModelJob, run_dir: Path, executable: Sequence[str] | None = None
) -> tuple[list[str], dict[str, str]]:
    run_dir = Path(run_dir).resolve()
    schema = _schema_path(run_dir, job)
    partial = _partial_path(run_dir, job)
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(json.dumps(job.schema, ensure_ascii=False), encoding="utf-8")
    command = list(executable or ["codex"]) + [
        "exec",
        "--ephemeral",
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(partial),
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--model",
        job.model,
        "-c",
        f'model_reasoning_effort="{job.effort}"',
        "-c",
        'service_tier="fast"',
        "-c",
        'web_search="disabled"',
        "-c",
        "mcp_servers={}",
    ]
    for feature in (
        "shell_tool",
        "unified_exec",
        "multi_agent",
        "browser_use",
        "computer_use",
        "apps",
        "image_generation",
    ):
        command.extend(["--disable", feature])
    command.extend(["-C", str(run_dir)])
    exec_home = run_dir / "exec-home"
    exec_home.mkdir(parents=True, exist_ok=True)
    (exec_home / "home").mkdir(parents=True, exist_ok=True)
    source_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    source_auth = source_home / "auth.json"
    target_auth = exec_home / "auth.json"
    if source_auth.is_file() and not target_auth.exists():
        shutil.copy2(source_auth, target_auth)
        target_auth.chmod(0o600)
    env = dict(os.environ)
    env["CODEX_HOME"] = str(exec_home)
    env["HOME"] = str(exec_home / "home")
    env["PYTHONUNBUFFERED"] = "1"
    return command, env


class CodexExecExecutor:
    def __init__(
        self,
        executable: Sequence[str] | None = None,
        *,
        event_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.executable = list(executable or ["codex"])
        self.event_callback = event_callback
        self.processes: set[asyncio.subprocess.Process] = set()

    async def execute(self, job: ModelJob, run_dir: Path) -> ExecResult:
        command, env = build_exec_command(job, run_dir, self.executable)
        partial = _partial_path(Path(run_dir), job)
        partial.unlink(missing_ok=True)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self.processes.add(process)
        usage = {"input_tokens": 0, "output_tokens": 0}
        stderr_lines: list[str] = []

        async def drain_stdout() -> None:
            assert process.stdout is not None
            async for raw in process.stdout:
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if isinstance(event, Mapping):
                    details = event.get("usage")
                    if isinstance(details, Mapping):
                        usage["input_tokens"] = int(details.get("input_tokens", usage["input_tokens"]) or 0)
                        usage["output_tokens"] = int(details.get("output_tokens", usage["output_tokens"]) or 0)
                    if self.event_callback:
                        self.event_callback(job.job_id, event)

        async def drain_stderr() -> None:
            assert process.stderr is not None
            async for raw in process.stderr:
                stderr_lines.append(raw.decode("utf-8", "replace").rstrip())
                if len(stderr_lines) > 100:
                    del stderr_lines[:50]

        stdout_task = asyncio.create_task(drain_stdout())
        stderr_task = asyncio.create_task(drain_stderr())
        try:
            assert process.stdin is not None
            process.stdin.write(job.prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task)
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise
        finally:
            self.processes.discard(process)
        error_text = "\n".join(stderr_lines[-20:])
        if process.returncode != 0:
            lower = error_text.lower()
            limited = "rate limit" in lower or "429" in lower or "too many requests" in lower
            retry_after = 0.0
            match = re.search(r"retry[- ]after[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)", lower)
            if match:
                retry_after = float(match.group(1))
            partial.unlink(missing_ok=True)
            return ExecResult(
                error=error_text or f"codex exec exited {process.returncode}",
                rate_limited=limited,
                retry_after=(retry_after or 5.0) if limited else 0.0,
            )
        try:
            value = json.loads(partial.read_text(encoding="utf-8"))
        except Exception as exc:
            partial.unlink(missing_ok=True)
            return ExecResult(error=f"invalid schema output: {exc}")
        partial.unlink(missing_ok=True)
        if not isinstance(value, Mapping):
            return ExecResult(error="schema output is not a JSON object")
        return ExecResult(value, input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"])

    async def terminate_all(self) -> None:
        processes = list(self.processes)
        for process in processes:
            if process.returncode is None:
                process.terminate()
        if processes:
            await asyncio.gather(*(process.wait() for process in processes), return_exceptions=True)


class RunnerStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs(
              run_id TEXT PRIMARY KEY, status TEXT NOT NULL, metadata TEXT NOT NULL,
              snapshot TEXT, created REAL NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs(
              job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL,
              wave INTEGER NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, result TEXT, error TEXT,
              input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0,
              started REAL, finished REAL
            );
            CREATE INDEX IF NOT EXISTS jobs_run_status ON jobs(run_id,status,wave);
            """
        )
        columns = {str(row[1]) for row in self.connection.execute("PRAGMA table_info(runs)")}
        if "snapshot" not in columns:
            self.connection.execute("ALTER TABLE runs ADD COLUMN snapshot TEXT")
        self.connection.commit()
        os.chmod(self.path, 0o600)
        self.connection.execute("UPDATE jobs SET status='queued', started=NULL WHERE status='running'")
        self.connection.commit()

    def create_run(
        self,
        run_id: str,
        metadata: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        now = time.time()
        self.connection.execute(
            "INSERT INTO runs(run_id,status,metadata,snapshot,created,updated) VALUES(?,?,?,?,?,?)",
            (
                run_id,
                "running",
                json.dumps(metadata, ensure_ascii=False),
                json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None,
                now,
                now,
            ),
        )
        self.connection.commit()

    def metadata(self, run_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT metadata FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"unknown run: {run_id}")
        return json.loads(row[0])

    def snapshot(self, run_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT snapshot FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None or row[0] is None:
            raise RuntimeError(f"run has no persistent snapshot: {run_id}")
        value = json.loads(row[0])
        if not isinstance(value, dict):
            raise RuntimeError("run snapshot is invalid")
        return value

    def clear_snapshot(self, run_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE runs SET snapshot=NULL,updated=? WHERE run_id=?", (time.time(), run_id))

    def enqueue(self, jobs: Sequence[ModelJob]) -> None:
        with self.connection:
            for job in jobs:
                self.connection.execute(
                    "INSERT OR IGNORE INTO jobs(job_id,run_id,kind,wave,payload,status) VALUES(?,?,?,?,?,'queued')",
                    (job.job_id, self._only_run_id(), job.kind, job.wave, json.dumps(job.public(), ensure_ascii=False)),
                )

    def _only_run_id(self) -> str:
        row = self.connection.execute("SELECT run_id FROM runs ORDER BY created DESC LIMIT 1").fetchone()
        if row is None:
            raise RuntimeError("store has no run")
        return str(row[0])

    def runnable(self, run_id: str, limit: int) -> list[ModelJob]:
        wave = self.connection.execute(
            "SELECT MIN(wave) FROM jobs WHERE run_id=? AND status IN ('queued','running')", (run_id,)
        ).fetchone()[0]
        if wave is None:
            return []
        rows = self.connection.execute(
            "SELECT payload FROM jobs WHERE run_id=? AND status='queued' AND wave=? ORDER BY rowid LIMIT ?",
            (run_id, wave, limit),
        ).fetchall()
        return [self._decode_job(json.loads(row[0])) for row in rows]

    @staticmethod
    def _decode_job(value: Mapping[str, Any]) -> ModelJob:
        return ModelJob(
            value["job_id"], value["kind"], value["prompt"], value["schema"],
            value["model"], value["effort"], value.get("wave", 0),
            session_key=value.get("session_key"), lens_id=value.get("lens_id"), raw=value,
        )

    def mark_running(self, job_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, started=? WHERE job_id=? AND status='queued'",
                (time.time(), job_id),
            )

    def succeed(self, job_id: str, result: Mapping[str, Any], *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET status='succeeded',result=?,error=NULL,input_tokens=?,output_tokens=?,finished=? WHERE job_id=?",
                (json.dumps(result, ensure_ascii=False), input_tokens, output_tokens, time.time(), job_id),
            )

    def skip(self, job_id: str, error: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET status='skipped',error=?,finished=? WHERE job_id=?",
                (error, time.time(), job_id),
            )

    def requeue(self, job_id: str, error: str, *, refund_attempt: bool = False) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET status='queued',error=?,started=NULL,attempts=MAX(0,attempts-?) WHERE job_id=?",
                (error, 1 if refund_attempt else 0, job_id),
            )

    def attempts(self, job_id: str) -> int:
        row = self.connection.execute("SELECT attempts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return int(row[0]) if row else 0

    def results(self, run_id: str) -> dict[str, dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT job_id,result FROM jobs WHERE run_id=? AND status='succeeded'", (run_id,)
        ).fetchall()
        return {str(row[0]): json.loads(row[1]) for row in rows}

    def skipped(self, run_id: str) -> set[str]:
        return {str(row[0]) for row in self.connection.execute("SELECT job_id FROM jobs WHERE run_id=? AND status='skipped'", (run_id,))}

    def state(self, job_id: str) -> str:
        row = self.connection.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return str(row[0])

    def run_status(self, run_id: str) -> str:
        row = self.connection.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return str(row[0])

    def pause(self, run_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE jobs SET status='queued',started=NULL WHERE run_id=? AND status='running'", (run_id,))
            self.connection.execute("UPDATE runs SET status='paused',updated=? WHERE run_id=?", (time.time(), run_id))

    def finish(self, run_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE runs SET status='completed',updated=? WHERE run_id=?", (time.time(), run_id))

    def fail(self, run_id: str, reason: str) -> bool:
        with self.connection:
            row = self.connection.execute(
                "SELECT metadata FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                return False
            metadata = json.loads(row[0])
            metadata["failure"] = reason
            self.connection.execute(
                "UPDATE runs SET status='failed',metadata=?,updated=? WHERE run_id=?",
                (json.dumps(metadata, ensure_ascii=False), time.time(), run_id),
            )
        return True

    def resume(self, run_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE jobs SET status='queued',started=NULL WHERE run_id=? AND status='running'", (run_id,))
            self.connection.execute("UPDATE runs SET status='running',updated=? WHERE run_id=?", (time.time(), run_id))

    def completed_counts(self, run_id: str) -> dict[str, int]:
        return {
            str(row[0]): int(row[1])
            for row in self.connection.execute(
                "SELECT kind,COUNT(*) FROM jobs WHERE run_id=? AND status IN ('succeeded','skipped') GROUP BY kind",
                (run_id,),
            )
        }

    def terminal_counts(self, run_id: str) -> dict[tuple[str, str], int]:
        return {
            (str(row[0]), str(row[1])): int(row[2])
            for row in self.connection.execute(
                "SELECT kind,status,COUNT(*) FROM jobs WHERE run_id=? AND status IN ('succeeded','skipped') GROUP BY kind,status",
                (run_id,),
            )
        }

    def checkpoint(self, run_id: str) -> dict[str, Any]:
        rows = self.connection.execute(
            "SELECT wave,status,COUNT(*) count FROM jobs WHERE run_id=? GROUP BY wave,status", (run_id,)
        ).fetchall()
        by_wave: dict[int, dict[str, int]] = {}
        for row in rows:
            by_wave.setdefault(int(row[0]), {})[str(row[1])] = int(row[2])
        complete = sum(1 for counts in by_wave.values() if counts.get("queued", 0) == 0 and counts.get("running", 0) == 0)
        return {"completed_waves": complete, "waves": by_wave}

    def close(self) -> None:
        self.connection.close()


class AdaptivePool:
    def __init__(self, *, initial: int = 6, maximum: int = 12) -> None:
        self.initial = initial
        self.maximum = maximum
        self.limit = initial
        self.streak = 0
        self.retries = 0
        self.retry_after = 0.0

    def success(self) -> None:
        self.streak += 1
        if self.streak >= 20 and self.limit < self.maximum:
            self.limit += 1
            self.streak = 0
        self.retry_after = 0.0

    def failed(self) -> None:
        self.retries += 1
        self.streak = 0

    def rate_limited(self, retry_after: float) -> None:
        self.limit = self.initial
        self.streak = 0
        self.retry_after = max(0.0, float(retry_after))


class ProgressPlan:
    def __init__(self, *, chunks: int, facets: int) -> None:
        self.units = {
            "inventory": 5,
            "chunk_summary": max(0, chunks) * 2,
            "session_facet": max(0, facets) * 5,
            "lens": 7 * 8,
            "at_a_glance": 5,
            "render": 2,
            "commit": 1,
        }
        self.total = sum(self.units.values()) or 1
        self._last = 0.0

    def snapshot(self, counts: Mapping[str, int]) -> dict[str, Any]:
        completed = 0.0
        stages: dict[str, dict[str, Any]] = {}
        totals = {"inventory": 1, "chunk_summary": self.units["chunk_summary"] // 2, "session_facet": self.units["session_facet"] // 5, "lens": 7, "at_a_glance": 1, "render": 1, "commit": 1}
        weights = {"inventory": 5, "chunk_summary": 2, "session_facet": 5, "lens": 8, "at_a_glance": 5, "render": 2, "commit": 1}
        for stage in STAGES:
            done = min(max(0, int(counts.get(stage, 0))), totals[stage])
            completed += done * weights[stage]
            stages[stage] = {"done": done, "total": totals[stage]}
        percent = min(100.0, 100.0 * completed / self.total)
        self._last = max(self._last, percent)
        return {"percent": round(self._last, 2), "stages": stages}


class RunnerConfig:
    def __init__(
        self,
        *,
        codex_home: str | Path,
        max_new_sessions: int = 200,
        language: str = "zh-CN",
        heartbeat_seconds: float = 60,
        dashboard_seconds: float = 300,
        resume_run_id: str | None = None,
    ) -> None:
        self.codex_home = Path(codex_home).expanduser().resolve()
        self.max_new_sessions = int(max_new_sessions)
        self.language = language
        self.heartbeat_seconds = float(heartbeat_seconds)
        self.dashboard_seconds = float(dashboard_seconds)
        self.resume_run_id = resume_run_id


def _persistent_snapshot(run: Mapping[str, Any]) -> dict[str, Any]:
    """Return the redacted, immutable analysis input needed for resume."""

    value = {
        "snapshot_version": 1,
        "snapshot_at": run["inventory"]["snapshot_at"],
        "generation": run["generation"],
        "state_hash": run["state_hash"],
        "language": run["language"],
        "work_items": run["work_items"],
        "selected_session_keys": sorted(run["selected_sessions"]),
        "source_snapshots": run["source_snapshots"],
        "eligible_metas": run["eligible_metas"],
        "cached_facets": run["cached_facets"],
        "inventory": run["inventory"],
        "legacy_cache_detected": run["legacy_cache_detected"],
    }
    violations: set[str] = set()

    def inspect(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key == "source_path":
                    violations.add("source-path-field")
                if isinstance(key, str):
                    violations.update(core.privacy_violations(key))
                inspect(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                inspect(child)
        elif isinstance(item, str):
            violations.update(core.privacy_violations(item))

    inspect(value)
    if violations:
        raise core.PrivacyError(
            "run snapshot contains a private value: " + ", ".join(sorted(violations))
        )
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    value["snapshot_sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return value


def _restore_snapshot(snapshot: Mapping[str, Any], output: Path) -> dict[str, Any]:
    if snapshot.get("snapshot_version") != 1:
        raise RuntimeError("incompatible run snapshot")
    expected = snapshot.get("snapshot_sha256")
    unsigned = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    actual = hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if expected != actual:
        raise RuntimeError("run snapshot hash mismatch")
    if core._state_snapshot_hash(output) != snapshot.get("state_hash"):
        raise core.StaleRunError("Insights state changed after the run snapshot")
    keys = snapshot.get("selected_session_keys")
    if not isinstance(keys, list):
        raise RuntimeError("run snapshot selection is invalid")
    return {
        "protocol_version": 5,
        "generation": snapshot["generation"],
        "state_hash": snapshot["state_hash"],
        "language": snapshot["language"],
        "output_dir": str(output),
        "work_items": list(snapshot["work_items"]),
        "selected_sessions": {str(key): True for key in keys},
        "source_snapshots": dict(snapshot["source_snapshots"]),
        "eligible_metas": list(snapshot["eligible_metas"]),
        "cached_facets": list(snapshot["cached_facets"]),
        "inventory": dict(snapshot["inventory"]),
        "legacy_cache_detected": bool(snapshot["legacy_cache_detected"]),
        "job_results": {},
        "job_skips": set(),
    }


def _facet_json_schema() -> dict[str, Any]:
    goal_keys = tuple(sorted(native_analysis.GOAL_CATEGORIES))
    satisfaction_keys = tuple(sorted(native_analysis.SATISFACTION_SIGNALS))
    friction_keys = tuple(sorted(native_analysis.FRICTION_TYPES))

    def strict_counter(keys: Sequence[str]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {key: {"type": "integer", "minimum": 0} for key in keys},
            "required": list(keys),
            "additionalProperties": False,
        }

    strings = {key: {"type": "string"} for key in ("underlying_goal", "friction_detail", "brief_summary")}
    properties: dict[str, Any] = {
        **strings,
        "goal_categories": strict_counter(goal_keys),
        "outcome": {"type": "string", "enum": sorted(native_analysis.OUTCOMES)},
        "user_satisfaction_counts": strict_counter(satisfaction_keys),
        "claude_helpfulness": {"type": "string", "enum": sorted(native_analysis.HELPFULNESS_LEVELS)},
        "session_type": {"type": "string", "enum": sorted(native_analysis.SESSION_TYPES)},
        "friction_counts": strict_counter(friction_keys),
        "primary_success": {"type": "string", "enum": sorted(native_analysis.PRIMARY_SUCCESSES)},
        "user_instructions_to_codex": {"type": "array", "items": {"type": "string"}},
        "evidence_anchors": {"type": "array", "items": {"type": "string"}},
    }
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _model_job(raw: Mapping[str, Any], wave: int) -> ModelJob:
    kind = str(raw["kind"])
    model, effort = MODEL_BY_KIND[kind]
    schema = raw.get("schema")
    if kind == "session_facet":
        schema = _facet_json_schema()
        raw = dict(raw)
        raw["prompt"] = str(raw["prompt"]) + "\nFor schema compatibility, return every counter key declared in the output schema and use 0 when absent. Never invent an `other` goal category."
    elif kind == "chunk_summary":
        schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False}
    return ModelJob(
        str(raw["job_id"]), kind, str(raw["prompt"]), schema or {}, model, effort, wave,
        session_key=raw.get("session_key"), lens_id=raw.get("lens_id"), raw=raw,
    )


class InsightsRunner:
    def __init__(self, config: RunnerConfig, *, executor: Any | None = None) -> None:
        self.config = config
        self.output = config.codex_home / "usage-data" / "insights"
        self.run_id = config.resume_run_id or uuid.uuid4().hex
        self.run_dir = self.output / "runs" / self.run_id
        self.executor = executor or CodexExecExecutor(event_callback=self._event)
        self.pool = AdaptivePool()
        self.store: RunnerStore | None = None
        self.run_state: dict[str, Any] | None = None
        self.progress: ProgressPlan | None = None
        self.counts = {stage: 0 for stage in STAGES}
        self.started = time.monotonic()
        self.last_event = self.started
        self.durations: list[float] = []
        self.completed_jobs = 0
        self.rate_limit_wait = 0.0
        self.succeeded_facets = 0
        self.skipped_facets = 0
        self._paused = False

    def _event(self, _job_id: str, _event: Mapping[str, Any]) -> None:
        self.last_event = time.monotonic()

    async def _heartbeat_loop(self) -> None:
        if self.config.heartbeat_seconds <= 0:
            return
        last_dashboard = time.monotonic()
        while True:
            await asyncio.sleep(self.config.heartbeat_seconds)
            now = time.monotonic()
            full = self.config.dashboard_seconds > 0 and now - last_dashboard >= self.config.dashboard_seconds
            self._print_progress(full=full)
            if full:
                last_dashboard = now
            if now - self.last_event >= 600:
                print("[告警] 在途模型 Job 已 10 分钟没有新事件；Runner 不会主动中断它。", flush=True)

    def _print_progress(self, *, full: bool = False) -> None:
        if not self.progress:
            return
        snap = self.progress.snapshot(self.counts)
        stage_text = " | ".join(f"{key} {value['done']}/{value['total']}" for key, value in snap["stages"].items())
        elapsed = max(0.001, time.monotonic() - self.started)
        throughput = self.completed_jobs / elapsed * 60
        ordered = sorted(self.durations)
        p50 = ordered[len(ordered) // 2] if ordered else 0.0
        p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))] if ordered else 0.0
        remaining = max(0.0, 100.0 - snap["percent"])
        eta = (elapsed * remaining / snap["percent"]) if snap["percent"] > 0 else 0.0
        prefix = "仪表盘" if full else "进度"
        print(
            f"[{prefix}] 总体 {snap['percent']:.2f}% | 语义覆盖 成功 {self.succeeded_facets} / 跳过 {self.skipped_facets} / 选中 {self.progress.units['session_facet'] // 5} "
            f"| 并发 {self.pool.limit} | 吞吐 {throughput:.2f} job/min | P50/P90 {p50:.1f}/{p90:.1f}s | ETA {eta/60:.1f}min | {stage_text}",
            flush=True,
        )

    async def _execute_jobs(self, jobs: Sequence[ModelJob]) -> None:
        assert self.store is not None and self.run_state is not None
        self.store.enqueue(jobs)
        raw_by_id = {job.job_id: job.raw for job in jobs}
        pending_ids = {job.job_id for job in jobs}
        while pending_ids:
            runnable = [job for job in self.store.runnable(self.run_id, self.pool.limit) if job.job_id in pending_ids]
            if not runnable:
                pending_ids -= set(self.store.results(self.run_id))
                pending_ids -= self.store.skipped(self.run_id)
                if not pending_ids:
                    break
                await asyncio.sleep(0.05)
                continue
            for job in runnable:
                self.store.mark_running(job.job_id)
            batch_started = time.monotonic()
            results = await asyncio.gather(*(self.executor.execute(job, self.run_dir) for job in runnable))
            per_job_duration = (time.monotonic() - batch_started)
            for job, result in zip(runnable, results):
                if self._paused:
                    raise asyncio.CancelledError()
                if result.error is None and result.value is not None:
                    try:
                        accepted = core._validated_job_result(self.run_state, raw_by_id[job.job_id], result.value)
                    except Exception as exc:
                        result = ExecResult(error=f"schema validation failed: {exc}")
                    else:
                        self.store.succeed(job.job_id, accepted, input_tokens=result.input_tokens, output_tokens=result.output_tokens)
                        self.run_state["job_results"][job.job_id] = accepted
                        self.pool.success()
                        pending_ids.discard(job.job_id)
                        self.counts[job.kind] += 1
                        if job.kind == "session_facet":
                            self.succeeded_facets += 1
                        self.completed_jobs += 1
                        self.durations.append(per_job_duration)
                        continue
                if result.rate_limited:
                    self.store.requeue(job.job_id, result.error or "rate limited", refund_attempt=True)
                    self.pool.rate_limited(result.retry_after)
                    if self.pool.retry_after:
                        self.rate_limit_wait += self.pool.retry_after
                        await asyncio.sleep(self.pool.retry_after)
                    continue
                self.pool.failed()
                if self.store.attempts(job.job_id) < 3:
                    self.store.requeue(job.job_id, result.error or "model job failed")
                    continue
                if job.kind == "chunk_summary":
                    item = next(value for value in self.run_state["work_items"] if value["session_key"] == job.session_key)
                    chunk = item["chunks"][int(raw_by_id[job.job_id]["chunk_index"])]
                    accepted = {"summary": chunk[:2000]}
                    self.store.succeed(job.job_id, accepted)
                    self.run_state["job_results"][job.job_id] = accepted
                    self.counts[job.kind] += 1
                    self.completed_jobs += 1
                    self.durations.append(per_job_duration)
                else:
                    self.store.skip(job.job_id, result.error or "model job failed")
                    self.run_state.setdefault("job_skips", set()).add(job.job_id)
                    self.counts[job.kind] += 1
                    if job.kind == "session_facet":
                        self.skipped_facets += 1
                        print(f"[跳过] Facet {job.job_id}：{result.error}", flush=True)
                    self.completed_jobs += 1
                    self.durations.append(per_job_duration)
                pending_ids.discard(job.job_id)
            self._print_progress()

    async def run(self) -> dict[str, Any]:
        resuming = self.config.resume_run_id is not None
        self.run_dir.mkdir(parents=True, exist_ok=resuming)
        self.store = RunnerStore(self.run_dir / "run.sqlite3")
        if resuming:
            snapshot = self.store.snapshot(self.run_id)
            if snapshot.get("language") != self.config.language:
                raise core.StaleRunError("resume language changed")
            self.run_state = _restore_snapshot(snapshot, self.output)
            self.run_state["job_results"].update(self.store.results(self.run_id))
            self.run_state["job_skips"].update(self.store.skipped(self.run_id))
            self.store.resume(self.run_id)
            completed = self.store.completed_counts(self.run_id)
            terminal = self.store.terminal_counts(self.run_id)
            for kind in ("chunk_summary", "session_facet", "lens", "at_a_glance"):
                self.counts[kind] = completed.get(kind, 0)
            self.succeeded_facets = terminal.get(("session_facet", "succeeded"), 0)
            self.skipped_facets = terminal.get(("session_facet", "skipped"), 0)
        else:
            self.run_state = core.prepare_run(
                self.config.codex_home,
                self.output,
                max_new_sessions=self.config.max_new_sessions,
                language=self.config.language,
            )
            snapshot = _persistent_snapshot(self.run_state)
            self.store.create_run(
                self.run_id,
                {
                    "selected": len(self.run_state["work_items"]),
                    "language": self.config.language,
                    "analysis_version": core.ANALYSIS_VERSION,
                    "snapshot_sha256": snapshot["snapshot_sha256"],
                },
                snapshot=snapshot,
            )
        self.run_state.update(
            {
                "run_id": self.run_id,
                "job_results": self.run_state.get("job_results", {}),
                "job_skips": self.run_state.get("job_skips", set()),
                "aggregate": None,
                "lens_material": None,
                "preview_html": None,
            }
        )
        chunks = sum(len(item.get("chunks", [])) for item in self.run_state["work_items"])
        self.progress = ProgressPlan(chunks=chunks, facets=len(self.run_state["work_items"]))
        self.counts["inventory"] = 1
        self._print_progress(full=True)
        heartbeat = asyncio.create_task(self._heartbeat_loop())
        try:
            wave_count = (len(self.run_state["work_items"]) + 49) // 50
            for wave in range(wave_count):
                items = self.run_state["work_items"][wave * 50 : (wave + 1) * 50]
                scoped = {**self.run_state, "work_items": items}
                chunk_jobs = [_model_job(job, wave) for job in core._chunk_jobs(scoped)]
                if chunk_jobs:
                    await self._execute_jobs(chunk_jobs)
                facet_jobs = [_model_job(job, wave) for job in core._facet_jobs(scoped)]
                if facet_jobs:
                    await self._execute_jobs(facet_jobs)
                print(f"[检查点] 波次 {wave + 1}/{wave_count} 已持久化", flush=True)
            core._ensure_aggregate(self.run_state)
            lens_jobs = [_model_job(job, wave_count) for job in core._lens_jobs(self.run_state)]
            await self._execute_jobs(lens_jobs)
            glance = core._glance_job(self.run_state)
            if glance is not None:
                await self._execute_jobs([_model_job(glance, wave_count + 1)])
            self.counts["render"] = 1
            selected = len(self.run_state["work_items"])
            succeeded = sum(1 for item in self.run_state["work_items"] if core._job_id(self.run_id, "facet", item["session_key"]) in self.run_state["job_results"])
            skipped = selected - succeeded
            analyzed = int(self.run_state["inventory"].get("cached", 0)) + succeeded
            eligible = int(self.run_state["inventory"]["eligible"])
            self.run_state["inventory"].update(
                {"analyzed": analyzed, "succeeded": succeeded, "skipped": skipped, "remaining": eligible - analyzed - skipped}
            )
            result = core.commit_run(self.run_state)
            self.counts["commit"] = 1
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        coverage = dict(self.run_state["inventory"])
        result["coverage"] = coverage
        elapsed = time.monotonic() - self.started
        active = max(0.0, elapsed - self.rate_limit_wait)
        result["performance"] = {
            "active_compute_seconds": round(active, 3),
            "end_to_end_seconds": round(elapsed, 3),
            "rate_limit_wait_seconds": round(self.rate_limit_wait, 3),
            "active_within_90_minutes": active <= 90 * 60,
            "end_to_end_within_120_minutes": elapsed <= 120 * 60,
        }
        self.store.finish(self.run_id)
        self.store.clear_snapshot(self.run_id)
        self._print_progress(full=True)
        self._remove_legacy_orphans(result)
        return result

    def _remove_legacy_orphans(self, result: Mapping[str, Any]) -> None:
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        keep = set(manifest.get("files", {}))
        facets = self.output / "facets"
        if facets.exists():
            for path in facets.glob("*.json"):
                if path.relative_to(self.output).as_posix() not in keep:
                    path.unlink()

    async def pause(self) -> None:
        self._paused = True
        await self.executor.terminate_all()
        for partial in self.run_dir.glob("exec/*.partial"):
            partial.unlink(missing_ok=True)
        if self.store:
            self.store.pause(self.run_id)


async def _run_cli(args: argparse.Namespace) -> int:
    output = Path(args.codex_home).expanduser().resolve() / "usage-data" / "insights"
    if args.probe:
        probe_dir = output / "runs" / f"probe-{uuid.uuid4().hex}"
        schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}, "layer": {"type": "string"}},
            "required": ["status", "layer"],
            "additionalProperties": False,
        }
        jobs = [
            ModelJob("probe-chunk", "chunk_summary", 'Return exactly {"status":"ok","layer":"chunk"}.', schema, "gpt-5.6-luna", "low"),
            ModelJob("probe-facet", "session_facet", 'Return exactly {"status":"ok","layer":"facet"}.', schema, "gpt-5.6-terra", "medium"),
            ModelJob("probe-lens", "lens", 'Return exactly {"status":"ok","layer":"lens"}.', schema, "gpt-5.6-sol", "high", lens_id="project_areas"),
        ]
        executor = CodexExecExecutor()
        try:
            results = await asyncio.gather(*(executor.execute(job, probe_dir) for job in jobs))
            payload = [
                {"job": job.job_id, "model": job.model, "effort": job.effort, "value": result.value, "error": result.error}
                for job, result in zip(jobs, results)
            ]
            ok = all(result.error is None and result.value and result.value.get("status") == "ok" for result in results)
            print(json.dumps({"ok": ok, "jobs": payload}, ensure_ascii=False), flush=True)
            return 0 if ok else 1
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)
    if _development_receipt_required(args.max_new_sessions) and not (
        args.release_receipt
        and _validate_release_receipt(args.release_receipt, codex_home=args.codex_home)
    ):
        print(json.dumps({
            "status": "preview_confirmation_required",
            "message": "0.4 开发态正式运行需要通过报告门禁并由用户确认预览。",
        }, ensure_ascii=False), flush=True)
        return 2
    unfinished: list[str] = []
    for database in sorted((output / "runs").glob("*/run.sqlite3")):
        try:
            connection = sqlite3.connect(database)
            row = connection.execute("SELECT run_id,status FROM runs ORDER BY created DESC LIMIT 1").fetchone()
            connection.close()
        except sqlite3.Error:
            continue
        if row and row[1] in {"running", "paused"}:
            unfinished.append(str(row[0]))
    if unfinished and not args.resume and not args.new:
        print(
            json.dumps(
                {
                    "status": "resume_choice_required",
                    "unfinished_runs": unfinished,
                    "message": "发现未完成的兼容运行；请让用户选择 --resume <run-id> 或 --new。",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 2
    config = RunnerConfig(
        codex_home=args.codex_home,
        max_new_sessions=args.max_new_sessions,
        language=args.language,
        resume_run_id=args.resume,
    )
    runner = InsightsRunner(config)
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, lambda: asyncio.create_task(runner.pause()))
        except NotImplementedError:
            pass
    try:
        result = await runner.run()
    except asyncio.CancelledError:
        return 130
    except Exception as exc:
        if runner.store is not None:
            recorded = runner.store.fail(runner.run_id, f"{type(exc).__name__}: {exc}")
            if not recorded:
                runner.store.close()
                runner.store = None
                shutil.rmtree(runner.run_dir, ignore_errors=True)
        completed_stage = "inventory"
        for stage in STAGES:
            if runner.counts.get(stage, 0):
                completed_stage = stage
        print(
            json.dumps(
                {
                    "status": "failed",
                    "run_id": runner.run_id,
                    "last_confirmed_stage": completed_stage,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "report_committed": False,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex Insights 0.4 candidate persistent exec runner")
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--max-new-sessions", type=int, default=200)
    parser.add_argument("--language", default="zh-CN")
    parser.add_argument("--resume", metavar="RUN_ID")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--probe", action="store_true", help="run exactly three real codex exec contract jobs")
    parser.add_argument("--release-receipt", help="user-confirmed pre-200 preview receipt (development candidate only)")
    args = parser.parse_args(argv)
    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
