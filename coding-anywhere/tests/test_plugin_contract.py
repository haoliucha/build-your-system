import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "coding-anywhere"


class CodingAnywhereContractTests(unittest.TestCase):
    def test_dual_host_version_and_dropfile(self):
        claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(codex["version"], "1.4.0")
        self.assertTrue((PLUGIN / "scripts" / "dropfile").is_file())
        self.assertTrue((PLUGIN / "scripts" / "install-dropfile.sh").is_file())

    def test_shared_skill_mentions_dropfile_and_host_neutral_root(self):
        skill = (PLUGIN / "skills" / "coding-anywhere" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("dropfile", skill)
        self.assertNotIn("targets/codex", skill)


if __name__ == "__main__":
    unittest.main()
