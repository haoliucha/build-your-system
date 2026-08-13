import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginContractTests(unittest.TestCase):
    def test_codex_only_manifest_and_skill(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "insights")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertFalse((ROOT / ".claude-plugin").exists())
        skill = (ROOT / "skills" / "insights" / "SKILL.md").read_text(encoding="utf-8")
        for term in ("L1", "L2", "L3", "L4", "L5", "质检", "facet_v2", "aggregation_v1", "report.html", "$insights"):
            self.assertIn(term, skill)
        self.assertIn("quality-contract.md", skill)
        self.assertIn("allow_implicit_invocation: false", (ROOT / "skills" / "insights" / "agents" / "openai.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
