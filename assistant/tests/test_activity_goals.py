import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from activity.claude_collector import collect
from activity.codex_collector import collect as collect_codex
from activity.common import merge_reports
from activity.common import Event, detect_domain, load_project_map, parse_mit, parse_mit_details
from activity.goals import attach_goals, estimate_minutes, explicit_goal, is_routine

TARGET = date(2026, 10, 16)
DONE_MD = """# 已完成任务归档

## 2026-10

- [x] **奇镜 1.1.0 发布** #indie ⏫ ✅ 2026-10-16
  - 10-16 MIT。GitHub Release v1.1.0 发布于 15:56，线上安装脚本真实装通过。

- [x] **定奇镜首售功能范围** #indie ⏫ ✅ 2026-10-16
  - 10-16 MIT。已定本机图片/视频、文本 AI、TTS；远程抓取不在首售。

- [x] **Paddle 前置外部确认** #indie ✅ 2026-10-16
  - 10-16 MIT。法定名更正请求已发出；ZA 用途暂不问客服（路线图 A13）。

- [x] **收 CP575 并核对** #indie #compliance ✅ 2026-10-16
  - 扫描件已存档。

- [x] **向美司通发出全部询问** #indie ✅ 2026-10-12
  - 10-12 MIT。
"""


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def user(session_id, cwd, utc, text, **extra):
    return {"type": "user", "sessionId": session_id, "cwd": cwd, "timestamp": utc, "uuid": f"{session_id}-{utc}",
            "entrypoint": "claude-desktop", "message": {"content": text}, **extra}


def write_vault(vault: Path, active: str = "# 任务中心\n", done: str = DONE_MD):
    (vault / "50-GTD").mkdir(parents=True, exist_ok=True)
    (vault / "50-GTD/active.md").write_text(active, encoding="utf-8")
    (vault / "50-GTD/done.md").write_text(done, encoding="utf-8")


def build_home(home: Path, vault: Path):
    """2026-10-16（GMT+8）的缩影：两条 MIT 会话、发布后转去做的计划外工作、自动审查子会话。"""
    app = "/Users/u/Projects/montagist-app"
    release = "release-1"
    write_jsonl(home / "projects/app/release.jsonl", [
        {"type": "custom-title", "customTitle": "版本 1.1.0 发布"},
        user(release, app, "2026-10-15T16:15:00Z", "目标：发布新版本 1.1.0 验收条件： * 包含最近的所有改动"),
        user(release, app, "2026-10-15T16:37:00Z", "这 7 个缺陷不进 1.1.0，留到下一个补丁版本。"),
        user(release, app, "2026-10-16T06:20:00Z", "接受建议，不再等审查完全干净"),
        user(release, app, "2026-10-16T08:27:00Z", "Do this task here: “Two-layer env config for worktrees (Montagist + xStudio)”"),
        user(release, app, "2026-10-16T09:19:00Z", "1. 补充 .env.example 2. 解释清楚"),
        user(release, app, "2026-10-16T09:55:00Z", "## 目标：针对这个环境变量问题，制作一期视频 ## 要求： * 不配音"),
        user(release, app, "2026-10-16T12:59:00Z", "合并 xStudio #12 和 vault #4，并清理 release/1.1.0 的分支和 worktree。"),
    ])
    pay = "pay-1"
    write_jsonl(home / "projects/vault/pay.jsonl", [
        {"type": "custom-title", "customTitle": "支付申请与首售交付"},
        user(pay, str(vault), "2026-10-15T16:16:00Z", "* Paddle更名，这个只能等 * 但，sandbox建号你在等什么？"),
        {"type": "assistant", "sessionId": pay, "timestamp": "2026-10-15T16:17:00Z", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": f"{vault}/50-GTD/waiting.md"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/Users/u/notes/only-read.md"}},
        ]}},
        user(pay, str(vault), "2026-10-15T17:42:00Z", "A13你好好说说"),
    ])
    review = "Review this change for security vulnerabilities."
    write_jsonl(home / "projects/wt/aux-1.jsonl", [
        user("aux-1", f"{app}/.claude/worktrees/env-two-layer", "2026-10-16T08:37:00Z", review, entrypoint="sdk-py", turnOrigin="sdk"),
    ])
    write_jsonl(home / "projects/wt/aux-2.jsonl", [
        user("aux-2", "/Users/u/Projects/biz/x/.claude/worktrees/env-two-layer", "2026-10-16T08:51:00Z", review, entrypoint="sdk-py"),
    ])
    write_jsonl(home / "projects/wt/aux-3.jsonl", [
        user("aux-3", "/private/tmp", "2026-10-16T14:18:00Z", "只回复两个字：收到", turnOrigin="sdk"),
    ])


class MitParsingTests(unittest.TestCase):
    def test_reads_archived_mit_from_done_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            write_vault(vault)
            parsed = parse_mit_details(vault, TARGET)
            self.assertEqual([item["title"] for item in parsed["details"]],
                             ["奇镜 1.1.0 发布", "定奇镜首售功能范围", "Paddle 前置外部确认"])
            self.assertTrue(all(item["status"] == "done" for item in parsed["details"]))
            self.assertEqual(parsed["source"], ["done"])
            self.assertIn("收 CP575 并核对", parsed["completed"])
            self.assertNotIn("向美司通发出全部询问", parsed["completed"])
            self.assertEqual(parse_mit(vault, TARGET)[0], "**奇镜 1.1.0 发布**")

    def test_merges_active_block_with_archived_items(self):
        active = """# 任务中心

## 今日重点 (MIT) - 2026-10-16

- [ ] **奇镜 1.1.0 发布准备**：整理未发布 PR #indie 🔼
- [x] **Paddle 前置外部确认** #indie
  - 法定名更正请求已发出

---
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            write_vault(vault, active=active)
            parsed = parse_mit_details(vault, TARGET)
            titles = [item["title"] for item in parsed["details"]]
            self.assertEqual(titles.count("Paddle 前置外部确认"), 1)
            paddle = next(item for item in parsed["details"] if item["title"] == "Paddle 前置外部确认")
            self.assertEqual(paddle["source"], "active+done")
            self.assertEqual(paddle["notes"], "法定名更正请求已发出")
            draft = next(item for item in parsed["details"] if item["title"] == "奇镜 1.1.0 发布准备")
            self.assertEqual(draft["status"], "open")
            self.assertEqual(parsed["source"], ["active", "done"])


class DomainMappingTests(unittest.TestCase):
    def test_cwd_project_mapping_includes_worktrees(self):
        self.assertEqual(detect_domain("", "/Users/u/Projects/montagist-app/.claude/worktrees/env"), "#indie")
        self.assertEqual(detect_domain("", "/Users/u/Projects/biz/x"), "#indie")
        self.assertEqual(detect_domain("", "/Users/u/Projects/biz/haoliucha/drafts"), "#media")
        self.assertEqual(detect_domain("", "/Users/u/Projects/biz/xyz"), "#other")
        self.assertEqual(detect_domain("", ["/Users/u/vault", "/Users/u/vault/50-GTD/active.md"]), "#tasks")
        self.assertEqual(detect_domain("讨论 #media 选题", "/Users/u/Projects/montagist-app"), "#media")

    def test_tag_mapping_project_paths_extend_and_override_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            (vault / "60-Memory").mkdir()
            (vault / "60-Memory/tag-mapping.md").write_text(
                "## #media 自媒体\n关键词：视频\n项目路径：env-video=讲解视频、montagist=奇镜视频\n", encoding="utf-8")
            mapping = load_project_map(vault)
            self.assertEqual(detect_domain("", "/Users/u/Projects/env-video", mapping), "#media")
            self.assertEqual(detect_domain("", "/Users/u/Projects/montagist", mapping), "#media")
            self.assertEqual(detect_domain("", "/Users/u/Projects/montagist-app", mapping), "#indie")


class GoalAnalysisTests(unittest.TestCase):
    def test_estimate_minutes_splits_on_idle_gaps(self):
        def at(utc):
            return Event(time="", ts=utc, origin="x", session_id="s", session_name="s", project="", cwd="", content="")
        events = [at("2026-10-16T02:00:00Z"), at("2026-10-16T02:20:00Z"), at("2026-10-16T03:30:00Z")]
        self.assertEqual(estimate_minutes(events), 30)

    def test_explicit_goal_patterns(self):
        def event(content, command=None):
            return Event(time="", ts="", origin="x", session_id="s", session_name="s", project="", cwd="",
                         content=content, command=command)
        self.assertEqual(explicit_goal(event("目标：发布新版本 1.1.0 验收条件： * 包含")), "发布新版本 1.1.0")
        self.assertEqual(explicit_goal(event("Do this task here: “Two-layer env”")), "Two-layer env")
        self.assertEqual(explicit_goal(event("/assistant:o-review", "assistant:o-review")), "每日回顾")
        self.assertIsNone(explicit_goal(event("这个目标不错")))

    def test_assistant_routines_are_neither_mit_nor_unplanned(self):
        self.assertTrue(is_routine("每日回顾"))
        self.assertTrue(is_routine("今晚 o-review（含记忆消融）"))
        self.assertTrue(is_routine("Assistant O weekly"))
        self.assertFalse(is_routine("版本 1.1.0 发布"))

    def test_links_mits_marks_unplanned_and_merges_aux_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "claude"
            vault = Path(tmpdir) / "vault"
            write_vault(vault)
            build_home(home, vault)
            report = collect(TARGET, home=home, vault=vault)
            attach_goals(report, parse_mit_details(vault, TARGET))

            progress = {entry["item"]: entry for entry in report.mit["progress"]}
            self.assertEqual(progress["奇镜 1.1.0 发布"]["goals"], ["版本 1.1.0 发布"])
            self.assertEqual(progress["定奇镜首售功能范围"]["sessions"], ["支付申请与首售交付"])
            self.assertEqual(progress["Paddle 前置外部确认"]["sessions"], ["支付申请与首售交付"])
            self.assertIn("定奇镜首售功能范围", progress["Paddle 前置外部确认"]["shared_with"])
            self.assertEqual(report.mit["completion"], {"done": 3, "total": 3, "rate": "3/3"})
            self.assertEqual(report.mit["date"], "2026-10-16")

            flow = {row["goal"]: row for row in report.flow}
            env = flow["Two-layer env config for worktrees (Mon…"]
            self.assertEqual(env["category"], "unplanned")
            self.assertEqual(env["aux_sessions"], 2)  # 同仓库 worktree + 跨仓库同名 worktree
            self.assertEqual(flow["针对这个环境变量问题，制作一期视频"]["category"], "unplanned")
            self.assertEqual(flow["版本 1.1.0 发布"]["messages"], 3)
            self.assertNotIn("aux-1", {row["session"] for row in report.flow})
            self.assertEqual(flow["自动化辅助会话"]["category"], "routine")

            unplanned = {goal["goal"] for goal in report.unplanned}
            self.assertIn("针对这个环境变量问题，制作一期视频", unplanned)
            self.assertNotIn("版本 1.1.0 发布", unplanned)

            sessions = {session["id"]: session for session in report.sessions}
            self.assertTrue(sessions["aux-1"]["aux"])
            self.assertEqual(sessions["aux-1"]["merged_into"]["goal"], env["goal"])
            self.assertEqual(sessions["aux-3"]["merged_into"]["goal"], "自动化辅助会话")
            self.assertEqual(sessions["release-1"]["mit_match"], ["奇镜 1.1.0 发布"])
            self.assertEqual(len(sessions["release-1"]["segments"]), 3)
            self.assertGreater(sessions["release-1"]["duration_min"], 0)
            self.assertEqual(sessions["pay-1"]["files"], [f"{vault}/50-GTD/waiting.md"])

            domains = {event.content[:6]: event.domain for event in report.timeline}
            self.assertEqual(domains["* Padd"], "#tasks")
            self.assertEqual(domains["目标：发布新"], "#indie")

    def test_codex_exec_and_subagent_sessions_fold_into_claude_goal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "claude"
            codex = Path(tmpdir) / "codex"
            vault = Path(tmpdir) / "vault"
            write_vault(vault)
            build_home(home, vault)

            def rollout(session_id, cwd, utc, text, **meta):
                write_jsonl(codex / f"sessions/2026/10/16/rollout-2026-10-16T00-00-00-{session_id}.jsonl", [
                    {"type": "session_meta", "payload": {"id": session_id, "cwd": cwd, **meta}},
                    {"type": "response_item", "timestamp": utc, "payload": {
                        "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
                ])

            rollout("desk-1", str(vault), "2026-10-16T05:20:00Z", "开始申请 Mercury，按办理总览推进",
                    originator="Codex Desktop", thread_source="user")
            rollout("exec-1", "/Users/u/Projects/montagist-app/.claude/worktrees/env-two-layer",
                    "2026-10-16T08:40:00Z", "Review the code changes again", originator="codex_exec")
            rollout("sub-1", "/Users/u/Projects/montagist-app/.claude/worktrees/env-two-layer",
                    "2026-10-16T08:41:00Z", "<user_action> review", thread_source="subagent", parent_thread_id="exec-1")
            write_jsonl(codex / "session_index.jsonl", [{"id": "desk-1", "thread_name": "开始申请 Mercury"}])

            report = merge_reports([collect(TARGET, home=home, vault=vault), collect_codex(TARGET, home=codex, vault=vault)])
            attach_goals(report, parse_mit_details(vault, TARGET))

            sessions = {session["id"]: session for session in report.sessions}
            self.assertTrue(sessions["exec-1"]["aux"])
            self.assertTrue(sessions["sub-1"]["aux"])
            self.assertEqual(sessions["exec-1"]["merged_into"]["goal"], "Two-layer env config for worktrees (Mon…")
            self.assertFalse(sessions["desk-1"]["aux"])
            mercury = next(goal for goal in report.goals if goal["goal"] == "开始申请 Mercury")
            self.assertEqual(mercury["category"], "unplanned")
            self.assertNotIn("Review the code changes again", {row["goal"] for row in report.flow})

    def test_cli_json_keeps_old_fields_and_adds_goal_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "claude"
            vault = Path(tmpdir) / "vault"
            write_vault(vault)
            build_home(home, vault)
            output = subprocess.run(
                [sys.executable, str(SCRIPTS / "analyze-activity.py"), "2026-10-16", "--host", "claude",
                 "--json-only", "--claude-home", str(home), "--vault", str(vault)],
                check=True, capture_output=True, text=True,
            ).stdout
            data = json.loads(output)
            for key in ("date", "origin", "hosts", "summary", "sessions", "timeline", "mit", "goals", "flow", "unplanned", "goal_meta"):
                self.assertIn(key, data)
            for key in ("date", "items", "matched", "progress", "completion", "details"):
                self.assertIn(key, data["mit"])
            session = next(item for item in data["sessions"] if item["id"] == "release-1")
            for key in ("id", "name", "project", "cwd", "origin", "time_range", "messages", "files", "goal", "mit_match", "duration_min"):
                self.assertIn(key, session)
            self.assertIn("估算", data["goal_meta"]["duration_method"])
            text = subprocess.run(
                [sys.executable, str(SCRIPTS / "analyze-activity.py"), "2026-10-16", "--host", "claude",
                 "--claude-home", str(home), "--vault", str(vault)],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertIn("MIT vs 实际（完成率 3/3", text)
            self.assertIn("计划外：", text)
            self.assertNotIn("Review this change", text.split("=== ACTIVITY_DATA ===")[0])


if __name__ == "__main__":
    unittest.main()
