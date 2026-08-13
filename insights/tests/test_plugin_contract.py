import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginContractTests(unittest.TestCase):
    def test_codex_only_manifest_and_skill(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "insights")
        self.assertEqual(manifest["version"], "0.2.1")
        self.assertFalse((ROOT / ".claude-plugin").exists())
        skill = (ROOT / "skills" / "insights" / "SKILL.md").read_text(encoding="utf-8")
        for term in (
            "确定性会话统计",
            "native-facet-v1",
            "project_areas",
            "interaction_style",
            "suggestions",
            "At-a-Glance",
            "report.html",
            "$insights",
            "next_jobs",
            "read_job",
            "submit_jobs",
            "stty -echo -icanon min 1 time 0",
            '"max_new_sessions":200',
        ):
            self.assertIn(term, skill)
        for incorrect_native_claim in ("→ Repeat", "五项质检", "facet_v2", "privacy-first"):
            self.assertNotIn(incorrect_native_claim, skill)
        agent = (ROOT / "skills" / "insights" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", agent)
        self.assertNotIn("隐私优先", agent)
        for script in ("insights.py", "native_meta.py", "native_analysis.py", "native_report.py"):
            self.assertTrue((ROOT / "skills" / "insights" / "scripts" / script).is_file())


if __name__ == "__main__":
    unittest.main()
