from __future__ import annotations

import unittest

from helpers import X, X_IMAGE, read_json_optional, read_optional


class CodexPluginTests(unittest.TestCase):
    def test_manifest_contract_uses_the_unified_x_identity(self):
        manifest = read_json_optional(X / ".codex-plugin" / "plugin.json")
        self.assertEqual(manifest.get("name"), "x")
        self.assertEqual(manifest.get("version"), "4.0.0")
        self.assertEqual(manifest.get("skills"), "./skills/")
        self.assertEqual(manifest.get("author", {}).get("name"), "haoliucha")
        self.assertIn(
            "Image generation",
            manifest.get("interface", {}).get("capabilities", []),
        )

    def test_native_skill_owns_generation_without_nesting(self):
        skill = read_optional(X_IMAGE / "SKILL.md")
        for phrase in (
            "installed `imagegen` skill",
            "built-in `image_gen`",
            "exactly one call per planned asset",
            "exclusive atomic claim",
            "Place the original",
            "inspect without editing",
            "stop remaining",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)
        for forbidden in ("codex:codex-rescue", "nested Codex", "codex exec"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, skill)

    def test_native_skill_reports_actual_invocation_origin(self):
        skill = read_optional(X_IMAGE / "SKILL.md")
        for phrase in (
            "Default to `native Codex`",
            "Invocation origin: Claude through Codex Rescue",
            "Host: native Codex",
            "Host: Claude through Codex Rescue",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_native_skill_has_zero_generation_preview_mode(self):
        skill = read_optional(X_IMAGE / "SKILL.md")
        for phrase in (
            "Style preview mode",
            "previews/manifest.json",
            "Do not call `image_gen`",
            "zero generation calls",
            "style reference, not a pixel-level promise",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_openai_agent_routes_to_the_shared_x_image_skill(self):
        agent = read_optional(X_IMAGE / "agents" / "openai.yaml")
        self.assertIn('display_name: "X Image"', agent)
        self.assertIn("one built-in ImageGen call", agent)


if __name__ == "__main__":
    unittest.main()
