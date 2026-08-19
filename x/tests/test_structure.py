from __future__ import annotations

import unittest

from helpers import REPO, X, X_IMAGE, read_json_optional


class StructureTests(unittest.TestCase):
    def test_dual_host_entry_points_share_one_top_level_plugin(self):
        self.assertTrue((X / "commands" / "image.md").is_file())
        self.assertTrue((X_IMAGE / "SKILL.md").is_file())
        self.assertTrue((X / ".claude-plugin" / "plugin.json").is_file())
        self.assertTrue((X / ".codex-plugin" / "plugin.json").is_file())

    def test_old_cover_and_target_entry_points_are_removed(self):
        self.assertFalse((X / "commands" / "cover.md").exists())
        self.assertFalse((X / "skills" / "x-cover").exists())
        self.assertFalse((REPO / "targets" / "codex" / "x-image").exists())

    def test_both_host_manifests_use_x_version_4(self):
        claude = read_json_optional(X / ".claude-plugin" / "plugin.json")
        codex = read_json_optional(X / ".codex-plugin" / "plugin.json")
        self.assertEqual(claude.get("name"), "x")
        self.assertEqual(codex.get("name"), "x")
        self.assertEqual(claude.get("version"), "4.0.1")
        self.assertEqual(codex.get("version"), "4.0.1")

    def test_both_marketplaces_register_the_same_top_level_source(self):
        claude_marketplace = read_json_optional(
            REPO / ".claude-plugin" / "marketplace.json"
        )
        codex_marketplace = read_json_optional(
            REPO / ".agents" / "plugins" / "marketplace.json"
        )
        claude_entry = next(
            (
                plugin
                for plugin in claude_marketplace.get("plugins", [])
                if plugin.get("name") == "x"
            ),
            {},
        )
        codex_entry = next(
            (
                plugin
                for plugin in codex_marketplace.get("plugins", [])
                if plugin.get("name") == "x"
            ),
            {},
        )
        self.assertEqual(claude_entry.get("source"), "./x")
        self.assertEqual(codex_entry.get("source"), {"source": "local", "path": "./x"})
        self.assertEqual(claude_entry.get("version"), "4.0.1")

    def test_claude_metadata_describes_the_rescue_boundary(self):
        manifest = read_json_optional(X / ".claude-plugin" / "plugin.json")
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

    def test_codex_and_claude_expose_the_same_shared_follow_skill(self):
        codex = read_json_optional(X / ".codex-plugin" / "plugin.json")
        claude = read_json_optional(X / ".claude-plugin" / "plugin.json")
        self.assertEqual(codex.get("skills"), "./skills/")
        self.assertEqual(claude.get("skills"), ["./skills/"])
        self.assertTrue((X / "skills" / "x-follow" / "SKILL.md").is_file())
        self.assertFalse((X / "claude-components" / "x-follow").exists())

    def test_x_image_assets_are_real_top_level_files_not_target_links(self):
        for directory in ("references", "styles", "previews"):
            path = X_IMAGE / directory
            with self.subTest(directory=directory):
                self.assertTrue(path.is_dir())
                self.assertFalse(path.is_symlink())


if __name__ == "__main__":
    unittest.main()
