import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class PluginArchitectureTests(unittest.TestCase):
    def test_current_roots_and_versions(self):
        expected = {"assistant": "2.0.0", "insights": "0.4.0", "x": "4.0.0", "coding-anywhere": "1.4.0", "bid": "0.1.0", "media": "1.1.0"}
        for name, version in expected.items():
            self.assertEqual(manifest(Path(name) / ".codex-plugin" / "plugin.json")["version"], version)
        self.assertEqual(manifest(Path("media") / ".claude-plugin" / "plugin.json")["version"], "1.1.0")
        self.assertFalse((ROOT / "targets").exists())

    def test_insights_is_codex_only_and_explicit(self):
        self.assertFalse((ROOT / "insights" / ".claude-plugin").exists())
        self.assertFalse((ROOT / "assistant" / "skills" / "insights").exists())
        skill = (ROOT / "insights" / "skills" / "insights" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("$insights", skill)
        self.assertIn("显式", skill)

    def test_x_boundaries_and_single_unfollow_source(self):
        self.assertFalse((ROOT / "x" / "skills" / "x-follow").exists())
        self.assertTrue((ROOT / "x" / "claude-components" / "x-follow" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "x" / "skills" / "x-unfollow" / "SKILL.md").is_file())
        self.assertFalse((ROOT / "assistant" / "skills" / "x-unfollow").exists())
        codex_skills = manifest(Path("x") / ".codex-plugin" / "plugin.json")["skills"]
        self.assertEqual(codex_skills, "./skills/")

    def test_marketplaces_use_top_level_roots(self):
        codex = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(codex["name"], "build-your-system")
        self.assertEqual(codex["interface"]["displayName"], "Build Your System")
        entries = {item["name"]: item["source"]["path"] for item in codex["plugins"]}
        for name in ("assistant", "insights", "x", "coding-anywhere", "bid", "media"):
            self.assertEqual(entries[name], f"./{name}")
        self.assertNotIn("x-image", entries)


if __name__ == "__main__":
    unittest.main()
