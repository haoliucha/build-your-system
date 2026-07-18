import re
import unittest

from helpers import BID_ROOT, read_json


class PluginManifestTests(unittest.TestCase):
    def test_codex_manifest_uses_shared_skills(self):
        manifest = read_json(BID_ROOT / ".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], "bid")
        self.assertEqual(manifest["version"].split("+", 1)[0], "0.1.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("apps", manifest)
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("hooks", manifest)

    def test_codex_manifest_has_required_identity_and_interface(self):
        manifest = read_json(BID_ROOT / ".codex-plugin/plugin.json")
        self.assertEqual(manifest["author"]["name"], "haoliucha")
        self.assertEqual(manifest["repository"], "https://github.com/haoliucha/build-your-system")
        interface = manifest["interface"]
        for key in (
            "displayName", "shortDescription", "longDescription",
            "developerName", "category", "capabilities", "defaultPrompt",
        ):
            self.assertTrue(interface.get(key), key)
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        self.assertTrue(re.fullmatch(
            r"0\.1\.0(?:\+codex\.[0-9A-Za-z.-]+)?",
            manifest["version"],
        ))
