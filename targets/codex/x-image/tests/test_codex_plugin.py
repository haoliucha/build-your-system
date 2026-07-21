from __future__ import annotations

import os
import unittest

from helpers import (
    CODEX_X_IMAGE,
    REPO,
    SHARED,
    read_json_optional,
    read_optional,
)


class CodexPluginTests(unittest.TestCase):
    def test_manifest_contract(self):
        manifest = read_json_optional(
            CODEX_X_IMAGE / ".codex-plugin" / "plugin.json"
        )
        self.assertEqual(manifest.get("name"), "x-image")
        self.assertRegex(
            manifest.get("version", ""),
            r"^0\.1\.0(?:\+codex\.[A-Za-z0-9.-]+)?$",
        )
        self.assertEqual(manifest.get("skills"), "./skills")
        self.assertEqual(manifest.get("author", {}).get("name"), "J. Liu")
        self.assertIn("Image generation", manifest.get("interface", {}).get("capabilities", []))

    def test_manifest_surfaces_static_style_previews(self):
        manifest = read_json_optional(
            CODEX_X_IMAGE / ".codex-plugin" / "plugin.json"
        )
        interface = manifest.get("interface", {})
        self.assertIn("Style previews", interface.get("capabilities", []))
        self.assertIn("zero generation calls", interface.get("longDescription", ""))
        self.assertTrue(
            any("预览" in prompt for prompt in interface.get("defaultPrompt", []))
        )

    def test_repo_marketplace_registration(self):
        marketplace = read_json_optional(
            REPO / ".agents" / "plugins" / "marketplace.json"
        )
        entry = next(
            (
                plugin
                for plugin in marketplace.get("plugins", [])
                if plugin.get("name") == "x-image"
            ),
            {},
        )
        self.assertEqual(
            entry.get("source"),
            {"source": "local", "path": "./targets/codex/x-image"},
        )
        self.assertEqual(
            entry.get("policy"),
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertEqual(entry.get("category"), "Productivity")

    def test_shared_paths_are_repository_relative_links(self):
        skill_root = CODEX_X_IMAGE / "skills" / "x-image"
        references = skill_root / "references"
        styles = skill_root / "styles"
        previews = skill_root / "previews"
        self.assertTrue(references.is_symlink())
        self.assertTrue(styles.is_symlink())
        self.assertTrue(previews.is_symlink())
        if references.is_symlink():
            self.assertEqual(references.resolve(), (SHARED / "references").resolve())
        if styles.is_symlink():
            self.assertEqual(styles.resolve(), (SHARED / "styles").resolve())
        if previews.is_symlink():
            self.assertEqual(previews.resolve(), (SHARED / "previews").resolve())

    def test_installer_uses_self_contained_cache_contract(self):
        installer = read_optional(
            CODEX_X_IMAGE / "scripts" / "install-local-plugin.sh"
        )
        for phrase in (
            'PLUGIN_NAME="x-image"',
            'MARKETPLACE_NAME="local-build-your-system"',
            'PLUGIN_VERSION="local"',
            "REGISTERED_VERSION=",
            "REGISTERED_CACHE_ROOT=",
            'rsync -aL',
            '"name": "x-image"',
            '"path": "./plugins/x-image"',
            '"${REGISTERED_CACHE_ROOT}/"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, installer)
        self.assertNotIn('rsync -aL "${SOURCE_ROOT}/"', installer)

    def test_installer_excludes_local_test_artifacts(self):
        installer = read_optional(
            CODEX_X_IMAGE / "scripts" / "install-local-plugin.sh"
        )
        for phrase in (
            "--exclude '.DS_Store'",
            "--exclude '__pycache__'",
            "--exclude '*.pyc'",
            "--exclude 'tests/acceptance/output'",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, installer)

    def test_native_skill_owns_generation_without_nesting(self):
        skill = read_optional(
            CODEX_X_IMAGE / "skills" / "x-image" / "SKILL.md"
        )
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
        skill = read_optional(
            CODEX_X_IMAGE / "skills" / "x-image" / "SKILL.md"
        )
        for phrase in (
            "Default to `native Codex`",
            "Invocation origin: Claude through Codex Rescue",
            "Host: native Codex",
            "Host: Claude through Codex Rescue",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_native_skill_has_zero_generation_preview_mode(self):
        skill = read_optional(
            CODEX_X_IMAGE / "skills" / "x-image" / "SKILL.md"
        )
        for phrase in (
            "Style preview mode",
            "previews/manifest.json",
            "Do not call `image_gen`",
            "zero generation calls",
            "style reference, not a pixel-level promise",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_installer_is_executable(self):
        installer = CODEX_X_IMAGE / "scripts" / "install-local-plugin.sh"
        self.assertTrue(installer.is_file())
        if installer.is_file():
            self.assertTrue(os.access(installer, os.X_OK))

    def test_installer_registers_the_plugin_with_codex(self):
        installer = read_optional(
            CODEX_X_IMAGE / "scripts" / "install-local-plugin.sh"
        )
        self.assertIn(
            'codex plugin add "${PLUGIN_NAME}@${MARKETPLACE_NAME}"',
            installer,
        )


if __name__ == "__main__":
    unittest.main()
