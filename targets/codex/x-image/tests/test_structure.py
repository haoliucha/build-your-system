from __future__ import annotations

import unittest

from helpers import CLAUDE_X, CODEX_X_IMAGE, REPO, read_json_optional


class StructureTests(unittest.TestCase):
    def test_new_entry_points_exist(self):
        self.assertTrue((CLAUDE_X / "commands" / "image.md").is_file())
        self.assertTrue((CLAUDE_X / "skills" / "x-image" / "SKILL.md").is_file())
        self.assertTrue(
            (CODEX_X_IMAGE / ".codex-plugin" / "plugin.json").is_file()
        )
        self.assertTrue(
            (CODEX_X_IMAGE / "skills" / "x-image" / "SKILL.md").is_file()
        )

    def test_old_cover_entry_points_are_removed(self):
        self.assertFalse((CLAUDE_X / "commands" / "cover.md").exists())
        self.assertFalse((CLAUDE_X / "skills" / "x-cover").exists())

    def test_claude_plugin_and_marketplace_use_version_2(self):
        manifest = read_json_optional(
            CLAUDE_X / ".claude-plugin" / "plugin.json"
        )
        marketplace = read_json_optional(
            REPO / ".claude-plugin" / "marketplace.json"
        )
        entry = next(
            (
                plugin
                for plugin in marketplace.get("plugins", [])
                if plugin.get("name") == "x"
            ),
            {},
        )
        self.assertEqual(manifest.get("version"), "2.0.0")
        self.assertEqual(entry.get("version"), "2.0.0")

    def test_claude_metadata_describes_the_new_boundary(self):
        manifest = read_json_optional(
            CLAUDE_X / ".claude-plugin" / "plugin.json"
        )
        marketplace = read_json_optional(
            REPO / ".claude-plugin" / "marketplace.json"
        )
        entry = next(
            (
                plugin
                for plugin in marketplace.get("plugins", [])
                if plugin.get("name") == "x"
            ),
            {},
        )
        text = f"{manifest.get('description', '')}\n{entry.get('description', '')}"
        for phrase in (
            "x-image",
            "/x:image",
            "article illustrations",
            "Codex Rescue",
            "one-call ImageGen",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()

