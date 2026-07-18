import re
import unittest

from helpers import BID_ROOT, frontmatter


DOMAIN_SKILLS = {
    "adversarial-review",
    "bid-costing",
    "bid-playbook",
    "bid-research",
    "bid-scheduling",
    "deai-writing",
    "diagram-pdf-pipeline",
    "presales-tactics",
    "prototype-handoff",
    "single-source-sync",
}

SKILLS_ROOT = BID_ROOT / "skills"
HOST_ADAPTATION = SKILLS_ROOT / "bid-playbook/references/host-adaptation.md"
SCRIPT_PATH_RULE = (
    "路径约定：先定位本 SKILL.md 所在目录，再从该目录解析 `scripts/...`；"
    "不要相对于进程 CWD 解析。"
)


class SharedSkillPortabilityTests(unittest.TestCase):
    def skill_markdown(self):
        return sorted(SKILLS_ROOT.glob("**/*.md"))

    def test_domain_skill_set_is_exact(self):
        actual = {path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")}
        self.assertEqual(actual, DOMAIN_SKILLS)

    def test_skill_frontmatter_is_host_neutral(self):
        for skill in DOMAIN_SKILLS:
            path = SKILLS_ROOT / skill / "SKILL.md"
            with self.subTest(skill=skill):
                data, _ = frontmatter(path)
                self.assertEqual(set(data), {"name", "description"})
                self.assertEqual(data["name"], skill)
                self.assertTrue(data["description"].startswith("Use when"))

    def test_shared_markdown_has_no_plugin_root_placeholders(self):
        for path in self.skill_markdown():
            with self.subTest(path=path.relative_to(BID_ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", text)
                self.assertNotIn("${CODEX_PLUGIN_ROOT}", text)

    def test_shared_markdown_has_no_standalone_claude_tool_instructions(self):
        branded_instruction = re.compile(
            r"\b(?:Read|Write|Edit|Glob|Bash|TaskOutput|AskUserQuestion)\b"
            r"|\bTask\s+tool\b"
            r"|Claude Code 编排者"
        )
        for path in self.skill_markdown():
            if path == HOST_ADAPTATION:
                continue
            with self.subTest(path=path.relative_to(BID_ROOT)):
                text = path.read_text(encoding="utf-8")
                match = branded_instruction.search(text)
                self.assertIsNone(
                    match,
                    f"host-specific instruction {match.group(0)!r}" if match else None,
                )

    def test_host_adaptation_reference_maps_both_hosts(self):
        self.assertTrue(HOST_ADAPTATION.is_file())
        text = HOST_ADAPTATION.read_text(encoding="utf-8")
        required_terms = (
            "技能加载",
            "$bid:<skill>",
            "文件搜索、读取与编辑",
            "shell",
            "rg",
            "apply_patch",
            "独立透镜",
            "Agent/Task",
            "multi-agent",
            "顺序执行",
            "用户输入",
            ".claude/memory/",
            "SKILL.md",
            "CWD",
        )
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_script_paths_are_resolved_from_the_owning_skill(self):
        for skill in DOMAIN_SKILLS:
            path = SKILLS_ROOT / skill / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            if "scripts/" not in text:
                continue
            with self.subTest(skill=skill):
                self.assertIn(SCRIPT_PATH_RULE, text)


if __name__ == "__main__":
    unittest.main()
