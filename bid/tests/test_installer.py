import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import BID_ROOT


INSTALLER = BID_ROOT / "scripts/install-codex-local.sh"
BID_ENTRY = {
    "name": "bid",
    "source": {"source": "local", "path": "./plugins/bid"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.home = Path(self.tempdir.name)
        self.codex_log = self.home / "codex.log"
        fake_bin = self.home / "fake-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CODEX_LOG"\n',
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        self.env = os.environ.copy()
        self.env.update(
            HOME=str(self.home),
            PATH=f"{fake_bin}{os.pathsep}{self.env['PATH']}",
            CODEX_LOG=str(self.codex_log),
        )

    @property
    def source_root(self):
        return self.home / "plugins/bid"

    @property
    def marketplace_file(self):
        return self.home / ".agents/plugins/marketplace.json"

    def run_installer(self):
        return subprocess.run(
            [str(INSTALLER)],
            cwd=BID_ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_marketplace(self, data):
        self.marketplace_file.parent.mkdir(parents=True, exist_ok=True)
        self.marketplace_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def codex_calls(self):
        if not self.codex_log.exists():
            return []
        return self.codex_log.read_text(encoding="utf-8").splitlines()

    def test_missing_paths_seed_marketplace_and_register_plugin_once(self):
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(
            json.loads(self.marketplace_file.read_text(encoding="utf-8")),
            {
                "name": "local-build-your-system",
                "interface": {"displayName": "Local Build Your System"},
                "plugins": [BID_ENTRY],
            },
        )
        self.assertEqual(
            self.codex_calls(),
            ["plugin add bid@local-build-your-system"],
        )

    def test_second_run_keeps_one_entry_and_the_same_symlink(self):
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stderr)
        symlink_inode = self.source_root.lstat().st_ino
        marketplace_text = self.marketplace_file.read_text(encoding="utf-8")

        second = self.run_installer()

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.source_root.lstat().st_ino, symlink_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(
            self.marketplace_file.read_text(encoding="utf-8"), marketplace_text
        )
        plugins = json.loads(marketplace_text)["plugins"]
        self.assertEqual(plugins.count(BID_ENTRY), 1)
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin add bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )

    def test_unrelated_marketplace_keys_entries_and_order_are_preserved(self):
        first_plugin = {
            "name": "first",
            "source": {"source": "local", "path": "./plugins/first"},
        }
        second_plugin = {
            "name": "second",
            "source": {"source": "local", "path": "./plugins/second"},
        }
        existing = {
            "name": "custom-marketplace-name",
            "interface": {"displayName": "Custom Name", "icon": "custom.svg"},
            "custom": {"preserve": True},
            "plugins": [first_plugin, second_plugin],
        }
        self.write_marketplace(existing)

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(self.marketplace_file.read_text(encoding="utf-8"))
        self.assertEqual(list(updated), list(existing))
        self.assertEqual(updated["name"], existing["name"])
        self.assertEqual(updated["interface"], existing["interface"])
        self.assertEqual(updated["custom"], existing["custom"])
        self.assertEqual(updated["plugins"], [first_plugin, second_plugin, BID_ENTRY])

    def test_real_file_source_conflict_is_unchanged(self):
        self.source_root.parent.mkdir(parents=True)
        self.source_root.write_text("keep me", encoding="utf-8")
        source_inode = self.source_root.stat().st_ino

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflict", result.stderr.lower())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.source_root.stat().st_ino, source_inode)
        self.assertEqual(self.source_root.read_text(encoding="utf-8"), "keep me")
        self.assertFalse(self.marketplace_file.exists())
        self.assertEqual(self.codex_calls(), [])

    def test_wrong_symlink_source_conflict_is_unchanged(self):
        other_target = self.home / "other-bid"
        other_target.mkdir()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(other_target)
        source_inode = self.source_root.lstat().st_ino

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflict", result.stderr.lower())
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), other_target)
        self.assertFalse(self.marketplace_file.exists())
        self.assertEqual(self.codex_calls(), [])

    def test_conflicting_bid_entry_does_not_rewrite_marketplace(self):
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        conflicting_entry = {
            **BID_ENTRY,
            "source": {"source": "local", "path": "./plugins/not-bid"},
        }
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Local Build Your System"},
            "plugins": [conflicting_entry],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflict", result.stderr.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(self.codex_calls(), [])

    def test_symlinked_marketplace_is_rejected_before_any_mutation(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Local Build Your System"},
            "plugins": [],
        }
        target = self.home / "external-marketplace.json"
        target.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        target_bytes = target.read_bytes()
        self.marketplace_file.parent.mkdir(parents=True)
        self.marketplace_file.symlink_to(target)
        marketplace_inode = self.marketplace_file.lstat().st_ino

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflict", result.stderr.lower())
        self.assertIn("symlink", result.stderr.lower())
        self.assertTrue(self.marketplace_file.is_symlink())
        self.assertEqual(self.marketplace_file.lstat().st_ino, marketplace_inode)
        self.assertEqual(self.marketplace_file.readlink(), target)
        self.assertEqual(target.read_bytes(), target_bytes)
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), [])

    def test_script_is_executable_and_has_no_cache_or_copy_operations(self):
        mode = INSTALLER.stat().st_mode
        text = INSTALLER.read_text(encoding="utf-8").lower()

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertNotIn("rm -rf", text)
        self.assertNotIn(".codex/plugins/cache", text)
        self.assertNotIn("rsync", text)


if __name__ == "__main__":
    unittest.main()
