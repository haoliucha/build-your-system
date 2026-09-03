import re
import sys
import unittest
from pathlib import Path


ASSISTANT = Path(__file__).resolve().parents[1]
SKILLS = ASSISTANT / "skills"
COMMANDS = ASSISTANT / "commands"
SCRIPTS = ASSISTANT / "scripts"
sys.path.insert(0, str(SCRIPTS))

WORKFLOW_SKILLS = {
    "a-setup",
    "c-capture",
    "c-dump",
    "c-pause",
    "cc-activity",
    "d-mine",
    "e-export",
    "o-review",
    "o-schedule",
    "o-tasks",
    "o-weekly",
}
EXCLUDED_SKILLS = {"assistant-router", "capture-rules", "vault-structure"}
SCRIPT_COMMANDS = {"a-setup", "cc-activity", "o-review", "o-tasks", "o-weekly", "o-schedule"}


def lines_with_matches(path: Path, pattern):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if pattern.search(line):
            yield f"{path.relative_to(ASSISTANT)}:{number}: {line.strip()}"


class AssistantSkillLintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_files = sorted(SKILLS.rglob("*.md"))
        cls.command_files = sorted(COMMANDS.glob("*.md"))
        cls.content_files = cls.skill_files + cls.command_files

    def assert_no_matches(self, paths, pattern, label):
        failures = [item for path in paths for item in lines_with_matches(path, pattern)]
        self.assertFalse(failures, f"{label}:\n" + "\n".join(failures))

    def test_no_legacy_numbered_paths(self):
        self.assert_no_matches(
            self.content_files,
            re.compile(r"\b0[1-7]-(Inbox|Tasks|Areas|Projects|Resources|Memory|Archives)"),
            "发现旧编号路径",
        )

    def test_no_unnamespaced_retired_commands(self):
        self.assert_no_matches(
            self.content_files,
            re.compile(r"(^|[^:\w])/(a|m|c|o|d|e)-[a-z]+"),
            "发现未加命名空间的退役斜杠命令",
        )

    def test_skill_script_references_exist(self):
        failures = []
        pattern = re.compile(r"scripts/[\w./-]+")
        for path in self.skill_files:
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                relative = Path(match.group(0)).relative_to("scripts")
                target = SCRIPTS / relative
                if not target.is_file():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(
                        f"{path.relative_to(ASSISTANT)}:{line}: {match.group(0)} -> {target.relative_to(ASSISTANT)}"
                    )
        self.assertFalse(failures, "不存在的脚本引用:\n" + "\n".join(failures))

    def test_commands_match_workflow_skills(self):
        command_names = {path.stem for path in self.command_files}
        skill_names = {
            path.parent.name
            for path in self.skill_files
            if path.name == "SKILL.md" and path.parent.name not in EXCLUDED_SKILLS
        }
        failures = []
        for name in sorted(command_names - skill_names):
            failures.append(f"{(COMMANDS / (name + '.md')).relative_to(ASSISTANT)}:1: command 没有对应 skill")
        for name in sorted(skill_names - command_names):
            failures.append(f"{(SKILLS / name / 'SKILL.md').relative_to(ASSISTANT)}:1: skill 没有对应 command")
        for name in sorted(command_names ^ WORKFLOW_SKILLS):
            failures.append(f"{(COMMANDS / (name + '.md')).relative_to(ASSISTANT)}:1: 不在 11 个工作流清单中")
        self.assertFalse(failures, "command/skill 一一对应失败:\n" + "\n".join(failures))

    def test_router_lists_all_workflow_skills(self):
        path = SKILLS / "assistant-router" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        missing = sorted(name for name in WORKFLOW_SKILLS if name not in text)
        self.assertFalse(missing, f"{path.relative_to(ASSISTANT)}:1: 缺少工作流 skill: {', '.join(missing)}")

    def test_no_codex_adaptation_heading(self):
        self.assert_no_matches(self.content_files, re.compile(r"Codex 适配说明"), "发现已退役标题")

    def test_claude_plugin_root_only_in_allowed_reference_and_script_commands(self):
        failures = []
        allowed = Path("vault-structure/references/host-adaptation.md")
        for path in self.skill_files:
            if path.relative_to(SKILLS) == allowed:
                continue
            failures.extend(lines_with_matches(path, re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}")))
        for name in sorted(SCRIPT_COMMANDS):
            path = COMMANDS / f"{name}.md"
            if not re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}", path.read_text(encoding="utf-8")):
                failures.append(f"{path.relative_to(ASSISTANT)}:1: 缺少 ${{CLAUDE_PLUGIN_ROOT}}")
        self.assertFalse(failures, "宿主根目录变量契约失败:\n" + "\n".join(failures))

    def test_emotion_words_only_in_capture_rules(self):
        allowed = Path("capture-rules/SKILL.md")
        pattern = re.compile(r"顺利|不错|搞定")
        failures = []
        for path in self.content_files:
            if path == SKILLS / allowed:
                continue
            failures.extend(lines_with_matches(path, pattern))
        self.assertFalse(failures, "情绪关键词出现在非 capture-rules 文件:\n" + "\n".join(failures))

    def test_memory_writers_reference_memory_model(self):
        for name in ("o-review", "o-weekly", "c-dump"):
            path = SKILLS / name / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            self.assertIn("memory-model", text, f"{path.relative_to(ASSISTANT)}:1: 缺少 memory-model")

    def test_standard_files_are_documented(self):
        from activity.vault_paths import STANDARD_FILES

        path = SKILLS / "vault-structure" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        missing = [relative for relative in STANDARD_FILES if relative not in text]
        self.assertFalse(missing, f"{path.relative_to(ASSISTANT)}:1: 缺少标准路径: {', '.join(missing)}")


if __name__ == "__main__":
    unittest.main()
