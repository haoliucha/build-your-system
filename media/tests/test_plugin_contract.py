import json
import unittest
from pathlib import Path


MEDIA = Path(__file__).resolve().parents[1]


class MediaPluginContractTests(unittest.TestCase):
    def test_dual_host_manifest_and_version(self):
        codex = json.loads((MEDIA / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        claude = json.loads((MEDIA / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex["name"], "media")
        self.assertEqual(codex["version"], "1.1.1")
        self.assertEqual(claude["name"], "media")
        self.assertEqual(claude["version"], "1.1.1")
        self.assertEqual(codex["skills"], "./skills/")
        self.assertNotIn("commands", codex)
        self.assertEqual(claude["commands"], "./commands")

    def test_all_workflows_have_one_shared_skill_and_thin_claude_entry(self):
        workflows = {"m-hook", "m-hotspot", "m-keywords", "m-publish", "m-script", "m-structure", "m-title", "m-topic"}
        for name in workflows:
            skill = MEDIA / "skills" / name / "SKILL.md"
            command = MEDIA / "commands" / f"{name}.md"
            self.assertTrue(skill.is_file(), name)
            self.assertTrue(command.is_file(), name)
            self.assertIn("当前请求中的用户输入", skill.read_text(encoding="utf-8"), name)
            self.assertLessEqual(len(command.read_text(encoding="utf-8").splitlines()), 14, name)

    def test_existing_methodology_skills_remain_shared(self):
        for name in ("jenny-hoyos-method", "script-writing", "transcript-cleaner", "youtube-transcript"):
            self.assertTrue((MEDIA / "skills" / name / "SKILL.md").is_file(), name)
        shared_text = "\n".join(path.read_text(encoding="utf-8") for path in (MEDIA / "skills").glob("**/*.md"))
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", shared_text)
        self.assertTrue((MEDIA / "references" / "host-adaptation.md").is_file())


if __name__ == "__main__":
    unittest.main()
