import ast
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import BID_ROOT


INSTALLER = BID_ROOT / "scripts/install-codex-local.sh"
LIFECYCLE = BID_ROOT / "scripts/codex-local-lifecycle.py"
README = BID_ROOT / "README.md"
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
            """#!/usr/bin/env python3
import os
import sys
from pathlib import Path


args = sys.argv[1:]
with Path(os.environ["CODEX_LOG"]).open("a", encoding="utf-8") as log:
    log.write(" ".join(args) + "\\n")

action = args[1] if len(args) > 1 else ""
effect = os.environ.get(f"CODEX_{action.upper()}_EFFECT", "")
if effect == "mutate-marketplace":
    Path(os.environ["MARKETPLACE_FILE"]).write_bytes(
        Path(os.environ["CONCURRENT_MARKETPLACE_FILE"]).read_bytes()
    )
elif effect == "lock-marketplace-parent":
    Path(os.environ["MARKETPLACE_FILE"]).parent.chmod(0o500)
elif effect == "lock-source-parent":
    Path(os.environ["SOURCE_ROOT"]).parent.chmod(0o500)

if action == "add" and os.environ.get("CODEX_ADD_RESTORE_PERMISSIONS") == "1":
    Path(os.environ["MARKETPLACE_FILE"]).parent.chmod(0o700)
    Path(os.environ["SOURCE_ROOT"]).parent.chmod(0o700)

returncode = os.environ.get(
    f"CODEX_{action.upper()}_EXIT", os.environ.get("CODEX_EXIT_CODE", "0")
)
raise SystemExit(int(returncode))
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        self.env = os.environ.copy()
        self.env.update(
            HOME=str(self.home),
            PATH=f"{fake_bin}{os.pathsep}{self.env['PATH']}",
            CODEX_LOG=str(self.codex_log),
            CODEX_EXIT_CODE="0",
            MARKETPLACE_FILE=str(self.marketplace_file),
            SOURCE_ROOT=str(self.source_root),
        )

    @property
    def source_root(self):
        return self.home / "plugins/bid"

    @property
    def marketplace_file(self):
        return self.home / ".agents/plugins/marketplace.json"

    def run_installer(self, *args):
        return subprocess.run(
            ["zsh", str(INSTALLER), *args],
            cwd=BID_ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
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

    def set_codex_exit(self, returncode):
        self.env["CODEX_EXIT_CODE"] = str(returncode)

    def set_concurrent_marketplace(self, data):
        concurrent_file = self.home / "concurrent-marketplace.json"
        concurrent_file.write_bytes(data)
        self.env["CONCURRENT_MARKETPLACE_FILE"] = str(concurrent_file)

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
            "name": "local-build-your-system",
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

    def test_wrong_marketplace_name_is_rejected_before_any_local_mutation(self):
        existing = {
            "name": "different-marketplace",
            "interface": {"displayName": "Different"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        original_mode = stat.S_IMODE(self.marketplace_file.stat().st_mode)

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local-build-your-system", result.stderr)
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(
            stat.S_IMODE(self.marketplace_file.stat().st_mode), original_mode
        )
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), [])

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
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), [])

    def test_first_install_codex_failure_rolls_back_new_local_state(self):
        self.set_codex_exit(23)

        result = self.run_installer()

        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.marketplace_file.is_symlink())
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), ["plugin add bid@local-build-your-system"])

    def test_codex_failure_restores_exact_preexisting_marketplace_and_symlink(self):
        first_plugin = {
            "name": "first",
            "source": {"source": "local", "path": "./plugins/first"},
        }
        original_bytes = (
            b'{"name":"local-build-your-system","custom":{"keep":true},'
            b'"plugins":['
            + json.dumps(first_plugin, separators=(",", ":")).encode("utf-8")
            + b']}\n'
        )
        self.marketplace_file.parent.mkdir(parents=True)
        self.marketplace_file.write_bytes(original_bytes)
        self.marketplace_file.chmod(0o640)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.set_codex_exit(19)

        result = self.run_installer()

        self.assertEqual(result.returncode, 19, result.stderr)
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(self.codex_calls(), ["plugin add bid@local-build-your-system"])

    def test_install_failure_does_not_overwrite_concurrent_marketplace_edit(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "custom": {"before": True},
            "plugins": [],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        concurrent_bytes = (
            b'{"name":"local-build-your-system","custom":{"concurrent":true},'
            b'"plugins":[{"name":"other","source":{"source":"local",'
            b'"path":"./plugins/other"}}]}\n'
        )
        self.set_concurrent_marketplace(concurrent_bytes)
        self.env["CODEX_ADD_EFFECT"] = "mutate-marketplace"
        self.env["CODEX_ADD_EXIT"] = "19"

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("concurrent", result.stderr.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), ["plugin add bid@local-build-your-system"])

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

    def test_uninstall_preserves_unrelated_marketplace_state_and_source(self):
        first_plugin = {
            "name": "first",
            "source": {"source": "local", "path": "./plugins/first"},
        }
        second_plugin = {
            "name": "second",
            "source": {"source": "local", "path": "./plugins/second"},
        }
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep", "icon": "keep.svg"},
            "custom": {"preserve": True},
            "plugins": [first_plugin, BID_ENTRY, second_plugin],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(self.marketplace_file.read_text(encoding="utf-8"))
        self.assertEqual(list(updated), list(existing))
        self.assertEqual(updated["interface"], existing["interface"])
        self.assertEqual(updated["custom"], existing["custom"])
        self.assertEqual(updated["plugins"], [first_plugin, second_plugin])
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertTrue(BID_ROOT.is_dir())
        self.assertIn(
            "Removed Codex-owned installed configuration and cache", result.stdout
        )
        self.assertIn("Preserved source repository", result.stdout)
        self.assertIn("Preserved Claude state", result.stdout)
        self.assertIn("project .claude/memory/", result.stdout)
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )

    def test_uninstall_refuses_wrong_source_symlink_without_mutation(self):
        other_target = self.home / "other-bid"
        other_target.mkdir()
        self.write_marketplace(
            {
                "name": "local-build-your-system",
                "interface": {"displayName": "Local Build Your System"},
                "plugins": [BID_ENTRY],
            }
        )
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(other_target)
        source_inode = self.source_root.lstat().st_ino

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflict", result.stderr.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), other_target)
        self.assertEqual(self.codex_calls(), [])

    def test_uninstall_refuses_wrong_marketplace_name_without_mutation(self):
        existing = {
            "name": "different-marketplace",
            "interface": {"displayName": "Different"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local-build-your-system", result.stderr)
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(self.codex_calls(), [])

    def test_uninstall_refuses_conflicting_bid_entry_without_mutation(self):
        conflicting_entry = {
            **BID_ENTRY,
            "source": {"source": "local", "path": "./plugins/not-bid"},
        }
        self.write_marketplace(
            {
                "name": "local-build-your-system",
                "interface": {"displayName": "Local Build Your System"},
                "plugins": [conflicting_entry],
            }
        )
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflict", result.stderr.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(self.codex_calls(), [])

    def test_uninstall_codex_failure_leaves_all_local_state_unchanged(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Local Build Your System"},
            "custom": {"preserve": True},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.set_codex_exit(29)

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )

    def test_uninstall_marketplace_write_failure_compensates_codex_remove(self):
        original_bytes = (
            b'{"name":"local-build-your-system","custom":{"keep":true},'
            b'"plugins":['
            + json.dumps(BID_ENTRY, separators=(",", ":")).encode("utf-8")
            + b']}\n'
        )
        self.marketplace_file.parent.mkdir(parents=True)
        self.marketplace_file.write_bytes(original_bytes)
        self.marketplace_file.chmod(0o640)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_REMOVE_EFFECT"] = "lock-marketplace-parent"
        self.env["CODEX_ADD_RESTORE_PERMISSIONS"] = "1"
        self.addCleanup(self.marketplace_file.parent.chmod, 0o700)

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restored", result.stderr.lower())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_uninstall_unlink_failure_rolls_back_and_compensates_codex_remove(self):
        original_bytes = (
            b'{"name":"local-build-your-system","custom":{"keep":true},'
            b'"plugins":['
            + json.dumps(BID_ENTRY, separators=(",", ":")).encode("utf-8")
            + b']}\n'
        )
        self.marketplace_file.parent.mkdir(parents=True)
        self.marketplace_file.write_bytes(original_bytes)
        self.marketplace_file.chmod(0o640)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_REMOVE_EFFECT"] = "lock-source-parent"
        self.env["CODEX_ADD_RESTORE_PERMISSIONS"] = "1"
        self.addCleanup(self.source_root.parent.chmod, 0o700)

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restored", result.stderr.lower())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_uninstall_concurrent_edit_is_preserved_and_remove_is_compensated(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "custom": {"before": True},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        concurrent_bytes = (
            b'{"name":"local-build-your-system","custom":{"concurrent":true},'
            b'"plugins":['
            + json.dumps(BID_ENTRY, separators=(",", ":")).encode("utf-8")
            + b']}\n'
        )
        self.set_concurrent_marketplace(concurrent_bytes)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_REMOVE_EFFECT"] = "mutate-marketplace"

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("concurrent", result.stderr.lower())
        self.assertIn("restored", result.stderr.lower())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_uninstall_failed_compensation_reports_recovery_command_and_paths(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        concurrent_bytes = (
            b'{"name":"local-build-your-system","custom":{"concurrent":true},'
            b'"plugins":['
            + json.dumps(BID_ENTRY, separators=(",", ":")).encode("utf-8")
            + b']}\n'
        )
        self.set_concurrent_marketplace(concurrent_bytes)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.env["CODEX_REMOVE_EFFECT"] = "mutate-marketplace"
        self.env["CODEX_ADD_EXIT"] = "31"

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("partial", result.stderr.lower())
        self.assertIn(
            "codex plugin add bid@local-build-your-system", result.stderr
        )
        self.assertIn(str(self.marketplace_file), result.stderr)
        self.assertIn(str(self.source_root), result.stderr)
        self.assertNotIn("uninstall complete", result.stdout.lower())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_uninstall_is_idempotent_when_local_state_is_already_absent(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Local Build Your System"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already", result.stdout.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertFalse(self.source_root.exists())
        self.assertEqual(self.codex_calls(), [])

    def test_uninstall_documentation_distinguishes_deleted_and_preserved_state(self):
        text = README.read_text(encoding="utf-8")

        self.assertIn("Codex 自己管理的已安装配置与缓存", text)
        self.assertIn("Claude 状态", text)
        self.assertIn("项目内 `.claude/memory/`", text)
        stale_claim = "Codex/Claude cache 和项目内 `.claude/memory/` 永不删除"
        self.assertNotIn(stale_claim, text)

    def test_scripts_are_valid_and_have_no_recursive_cache_or_copy_operations(self):
        mode = INSTALLER.stat().st_mode
        shell_text = INSTALLER.read_text(encoding="utf-8")
        lifecycle_text = LIFECYCLE.read_text(encoding="utf-8")
        combined_text = f"{shell_text}\n{lifecycle_text}".lower()

        self.assertTrue(mode & stat.S_IXUSR)
        ast.parse(lifecycle_text)
        self.assertNotIn("rm -rf", combined_text)
        self.assertNotIn(".codex/plugins/cache", combined_text)
        self.assertNotIn("rsync", combined_text)


if __name__ == "__main__":
    unittest.main()
