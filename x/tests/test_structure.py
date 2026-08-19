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
        self.assertEqual(claude.get("version"), "4.1.0")
        self.assertEqual(codex.get("version"), "4.1.0")

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
        self.assertEqual(claude_entry.get("version"), "4.1.0")

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

    def test_follow_docs_state_shared_runtime_and_comment_consent_contract(self):
        readme = (X / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "$x:x-follow",
            "X_FOLLOW_DATA_DIR",
            "network-run.lock",
            "ALLOW_COMMENT_AFTER_FOLLOW=1",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_follow_skill_examples_keep_safe_filter_and_profile_defaults(self):
        skill = (X / "skills" / "x-follow" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "filter_crypto: 0",
            "bio_blacklist: []",
            "FILTER_CRYPTO=1 才用 crypto 列表",
            "profile_dir: ~/.config/playwright-chrome-profile-campaign",
            "JOB_DIR=/tmp FILTER_CRYPTO=0 node",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)
        self.assertNotIn("JOB_DIR=/tmp NOCRYPTO=1 node", skill)

    def test_follow_docs_name_the_shared_source_profile_and_runtime_gate(self):
        for path in (
            X / "README.md",
            X / "skills" / "x-follow" / "SKILL.md",
            X / "skills" / "x-follow" / "README.md",
            X / "skills" / "x-follow" / "references" / "pacing-anti-detection.md",
            X / "skills" / "x-follow" / "references" / "troubleshooting.md",
            X / "skills" / "x-follow" / "references" / "candidate-sources.md",
        ):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("SOURCE_PROFILE_DIR", text)
                self.assertIn("X_FOLLOW_SOURCE_PROFILE_DIR", text)
                self.assertIn("运行时强制", text)

    def test_follow_docs_do_not_recommend_recursive_profile_deletion(self):
        docs = [X / "README.md", *(X / "skills" / "x-follow").rglob("*.md")]
        for path in docs:
            with self.subTest(document=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("rm -rf", text)
                self.assertNotRegex(text, r"rm\s+-f[^\n]*Singleton")
                self.assertNotRegex(text, r"Fix:.*rm.*Singleton")
                if "cp -R" in text:
                    self.assertIn("export SOURCE_PROFILE_DIR PROFILE_DIR", text)

    def test_troubleshooting_manual_profile_entry_keeps_source_context(self):
        text = (X / "skills" / "x-follow" / "references" / "troubleshooting.md").read_text(encoding="utf-8")
        self.assertIn(
            "SOURCE_PROFILE_DIR=\"$SOURCE_PROFILE_DIR\" PROFILE_DIR=\"$PROFILE_DIR\" \\",
            text,
        )

    def test_follow_reference_docs_share_safe_profile_lock_and_pacing_contracts(self):
        refs = X / "skills" / "x-follow" / "references"
        pacing = (refs / "pacing-anti-detection.md").read_text(encoding="utf-8")
        troubleshooting = (refs / "troubleshooting.md").read_text(encoding="utf-8")
        candidates = (refs / "candidate-sources.md").read_text(encoding="utf-8")
        run_sh = (X / "skills" / "x-follow" / "run.sh").read_text(encoding="utf-8")
        for phrase in (
            "SOURCE_PROFILE_DIR",
            "PROFILE_DIR",
            "post_click_settle_ms: 6000",
            "不自动清理 profile",
        ):
            with self.subTest(document="pacing", phrase=phrase):
                self.assertIn(phrase, pacing)
        for phrase in (
            "SOURCE_PROFILE_DIR",
            "PROFILE_DIR",
            "X_FOLLOW_DATA_DIR",
            "network-run.lock",
            "post_click_settle_ms: 6000",
        ):
            with self.subTest(document="troubleshooting", phrase=phrase):
                self.assertIn(phrase, troubleshooting)
        self.assertIn("campaign 使用独立 `PROFILE_DIR`", candidates)
        self.assertIn("network-run.lock", candidates)
        self.assertIn("不并发", candidates)
        self.assertNotIn("MCP 浏览器", candidates)
        self.assertIn("FILTER_CRYPTO=0 (default; 1 filters crypto)", run_sh)
        self.assertNotIn("NOCRYPTO=1               CAND_MULT", run_sh)

    def test_x_image_assets_are_real_top_level_files_not_target_links(self):
        for directory in ("references", "styles", "previews"):
            path = X_IMAGE / directory
            with self.subTest(directory=directory):
                self.assertTrue(path.is_dir())
                self.assertFalse(path.is_symlink())


if __name__ == "__main__":
    unittest.main()
