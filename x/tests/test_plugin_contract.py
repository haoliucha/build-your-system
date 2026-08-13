import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
X = ROOT / "x"


class XPluginContractTests(unittest.TestCase):
    def test_dual_host_manifests_and_boundaries(self):
        claude = json.loads((X / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((X / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(codex["skills"], "./skills/")
        self.assertFalse((X / "skills" / "x-follow").exists())
        self.assertTrue((X / "claude-components" / "x-follow" / "SKILL.md").is_file())

    def test_shared_image_contract_is_self_contained(self):
        skill = (X / "skills" / "x-image" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("exactly one call per planned asset", "built-in `image_gen`", "exclusive atomic claim", "Invocation origin"):
            self.assertIn(phrase, skill)
        for name in ("intent-routing.md", "size-presets.md", "style-policy.md", "layout-patterns.md", "prompt-contract.md", "qa-checklist.md"):
            self.assertTrue((X / "skills" / "x-image" / "references" / name).is_file())
        self.assertTrue((X / "scripts" / "place-original.py").is_file())

    def test_unfollow_has_one_business_source(self):
        self.assertTrue((X / "skills" / "x-unfollow" / "SKILL.md").is_file())
        self.assertFalse((ROOT / "assistant" / "skills" / "x-unfollow").exists())
        self.assertFalse((ROOT / "targets").exists())


if __name__ == "__main__":
    unittest.main()
