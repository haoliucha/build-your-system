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
WORKFLOW_SKILLS = {"bid-init"}

SKILLS_ROOT = BID_ROOT / "skills"
HOST_ADAPTATION = SKILLS_ROOT / "bid-playbook/references/host-adaptation.md"
HOST_ADAPTATION_LINK = "../bid-playbook/references/host-adaptation.md"
HOST_ORCHESTRATED_SKILLS = {"adversarial-review", "bid-research"}
SCRIPT_PATH_RULE = (
    "路径约定：先定位本 SKILL.md 所在目录，再从该目录解析 `scripts/...`；"
    "不要相对于进程 CWD 解析。"
)
EXPECTED_SKILL_SCRIPTS = {
    "adversarial-review": {"check-residuals.sh"},
    "bid-costing": {"discount-check.cjs"},
    "bid-research": {"extract-frames.sh"},
    "bid-scheduling": {"level.cjs"},
    "deai-writing": {"aiflavor-scan.cjs"},
    "diagram-pdf-pipeline": {"add-outline.cjs"},
    "prototype-handoff": {"extract-frames.sh"},
    "single-source-sync": {"xlsx-dump.cjs"},
}
SCRIPT_PATH_COMPONENT = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?"
CONCRETE_SCRIPT_REFERENCE = re.compile(
    rf"(?<![\w/.-])scripts/((?!\.\.\.){SCRIPT_PATH_COMPONENT}"
    rf"(?:/{SCRIPT_PATH_COMPONENT})*)"
)
FORBIDDEN_HOST_PATTERNS = (
    (
        "plugin root variable",
        re.compile(r"\b(?:CLAUDE|CODEX)_PLUGIN_ROOT\b"),
        "CLAUDE_PLUGIN_ROOT",
        True,
    ),
    ("Read tool", re.compile(r"\bRead\b"), "Read", False),
    ("Write tool", re.compile(r"\bWrite\b"), "Write", False),
    ("Edit tool", re.compile(r"\bEdit\b"), "Edit", False),
    ("Glob tool", re.compile(r"\bGlob\b"), "Glob", False),
    ("Bash tool", re.compile(r"\bBash\b"), "Bash", False),
    ("Task tool", re.compile(r"\bTask\s+tool\b"), "Task tool", False),
    ("Agent tool", re.compile(r"\bAgent\s+tool\b"), "Agent tool", False),
    ("Skill tool", re.compile(r"\bSkill\s+tool\b"), "Skill tool", False),
    ("TaskOutput tool", re.compile(r"\bTaskOutput\b"), "TaskOutput", False),
    (
        "AskUserQuestion tool",
        re.compile(r"\bAskUserQuestion\b"),
        "AskUserQuestion",
        False,
    ),
    ("SendMessage tool", re.compile(r"\bSendMessage\b"), "SendMessage", False),
    (
        "Claude Code orchestrator assumption",
        re.compile(r"Claude Code 编排者"),
        "Claude Code 编排者",
        False,
    ),
)
PLUGIN_ROOT_EXPANSION_FIXTURES = (
    "${CLAUDE_PLUGIN_ROOT:-fallback}",
    "${CODEX_PLUGIN_ROOT:+value}",
    "${CLAUDE_PLUGIN_ROOT-fallback}",
)
PLUGIN_ROOT_NON_MATCH_FIXTURES = (
    "MY_CLAUDE_PLUGIN_ROOT",
    "CODEX_PLUGIN_ROOT_BACKUP",
)


class SharedSkillPortabilityTests(unittest.TestCase):
    def skill_markdown(self):
        return sorted(SKILLS_ROOT.glob("**/*.md"))

    def test_skill_inventory_is_exact(self):
        actual = {path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")}
        self.assertEqual(actual, DOMAIN_SKILLS | WORKFLOW_SKILLS)

    def test_skill_frontmatter_is_host_neutral(self):
        for skill in DOMAIN_SKILLS:
            path = SKILLS_ROOT / skill / "SKILL.md"
            with self.subTest(skill=skill):
                data, _ = frontmatter(path)
                self.assertEqual(set(data), {"name", "description"})
                self.assertEqual(data["name"], skill)
                self.assertTrue(data["description"].startswith("Use when"))

    def test_forbidden_host_pattern_fixtures_are_effective(self):
        for label, pattern, fixture, _ in FORBIDDEN_HOST_PATTERNS:
            with self.subTest(label=label):
                self.assertIsNotNone(pattern.search(fixture))
        plugin_root_patterns = tuple(
            pattern
            for label, pattern, _, _ in FORBIDDEN_HOST_PATTERNS
            if "plugin root" in label
        )
        for fixture in PLUGIN_ROOT_EXPANSION_FIXTURES:
            with self.subTest(plugin_root_expansion=fixture):
                self.assertTrue(
                    any(pattern.search(fixture) for pattern in plugin_root_patterns)
                )
        for fixture in PLUGIN_ROOT_NON_MATCH_FIXTURES:
            with self.subTest(plugin_root_non_match=fixture):
                self.assertFalse(
                    any(pattern.search(fixture) for pattern in plugin_root_patterns)
                )

    def test_shared_markdown_has_no_forbidden_host_tokens(self):
        for path in self.skill_markdown():
            text = path.read_text(encoding="utf-8")
            for label, pattern, _, forbidden_in_host_adaptation in FORBIDDEN_HOST_PATTERNS:
                if path == HOST_ADAPTATION and not forbidden_in_host_adaptation:
                    continue
                with self.subTest(path=path.relative_to(BID_ROOT), token=label):
                    match = pattern.search(text)
                    self.assertIsNone(
                        match,
                        f"host-specific token {match.group(0)!r}" if match else None,
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

    def test_host_orchestrated_skills_link_the_central_adaptation(self):
        actual = set()
        for skill in DOMAIN_SKILLS:
            path = SKILLS_ROOT / skill / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            if HOST_ADAPTATION_LINK in text:
                actual.add(skill)
        self.assertEqual(actual, HOST_ORCHESTRATED_SKILLS)
        for skill in HOST_ORCHESTRATED_SKILLS:
            path = SKILLS_ROOT / skill / "SKILL.md"
            target = path.parent / HOST_ADAPTATION_LINK
            with self.subTest(skill=skill):
                self.assertTrue(target.is_file())

    def test_script_inventory_and_owner_path_rules_are_exact(self):
        actual = {}
        for path in SKILLS_ROOT.glob("*/scripts/*"):
            if path.is_file():
                actual.setdefault(path.parents[1].name, set()).add(path.name)
        self.assertEqual(actual, EXPECTED_SKILL_SCRIPTS)
        for skill, scripts in EXPECTED_SKILL_SCRIPTS.items():
            path = SKILLS_ROOT / skill / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            with self.subTest(skill=skill, rule="path resolution"):
                self.assertIn(SCRIPT_PATH_RULE, text)
            for script in scripts:
                with self.subTest(skill=skill, script=script):
                    self.assertIn(f"scripts/{script}", text)

    def test_concrete_markdown_script_references_exist_under_their_owner(self):
        for path in self.skill_markdown():
            owner = path.relative_to(SKILLS_ROOT).parts[0]
            text = path.read_text(encoding="utf-8")
            for match in CONCRETE_SCRIPT_REFERENCE.finditer(text):
                reference = f"scripts/{match.group(1)}"
                target = SKILLS_ROOT / owner / reference
                with self.subTest(path=path.relative_to(BID_ROOT), reference=reference):
                    self.assertTrue(target.is_file(), f"missing owned script: {target}")


if __name__ == "__main__":
    unittest.main()
