from __future__ import annotations

import unittest

from helpers import (
    CLAUDE_X,
    CODEX_X_IMAGE,
    REPO,
    read_json_optional,
    read_optional,
)


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

    def test_acceptance_fixtures_exist(self):
        fixture_dir = CODEX_X_IMAGE / "tests" / "fixtures"
        for name in (
            "tech-article.md",
            "data-article.md",
            "explainer-article.md",
            "humanities-article.md",
        ):
            with self.subTest(name=name):
                self.assertTrue((fixture_dir / name).is_file())

    def test_acceptance_records_have_required_fields(self):
        acceptance_dir = CODEX_X_IMAGE / "tests" / "acceptance"
        required_fields = (
            "Status:",
            "Codex task or thread:",
            "Input fixture:",
            "Exact Codex prompt:",
            "Expected style:",
            "Expected ratio:",
            "Maximum permitted tool calls:",
            "Final prompt:",
            "Style ID:",
            "image_gen call count:",
            "ImageGen edit call count:",
            "Image modification command count:",
            "Saved output path:",
            "Actual dimensions:",
            "Content QA:",
            "Style QA:",
            "P0 checklist:",
            "P1 checklist:",
            "P2 checklist:",
        )
        for name in (
            "cover-2_5x1.md",
            "hero-16x9.md",
            "explainer-3x2.md",
            "vertical-3x4.md",
            "data-editorial.md",
            "custom-style.md",
            "multi-image.md",
        ):
            path = acceptance_dir / name
            text = read_optional(path)
            with self.subTest(name=name, field="exists"):
                self.assertTrue(path.is_file())
            for field in required_fields:
                with self.subTest(name=name, field=field):
                    self.assertIn(field, text)
            with self.subTest(name=name, field="status"):
                self.assertIn("Status: NOT RUN", text)

    def test_acceptance_output_is_ignored(self):
        ignore = read_optional(
            CODEX_X_IMAGE
            / "tests"
            / "acceptance"
            / "output"
            / ".gitignore"
        )
        self.assertEqual(ignore, "*\n!.gitignore\n")


if __name__ == "__main__":
    unittest.main()
