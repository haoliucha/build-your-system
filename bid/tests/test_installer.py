import ast
import fcntl
import json
import os
import signal
import stat
import subprocess
import tempfile
import time
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
REAL_CODEX_ORPHAN_LIST_FIXTURE = '{"installed": [], "available": []}'


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
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path


args = sys.argv[1:]
with Path(os.environ["CODEX_LOG"]).open("a", encoding="utf-8") as log:
    log.write(" ".join(args) + "\\n")

action = args[1] if len(args) > 1 else ""


def set_installed(installed):
    Path(os.environ["CODEX_INSTALLED_STATE"]).write_text(
        "1" if installed else "0", encoding="utf-8"
    )


def is_installed():
    return Path(os.environ["CODEX_INSTALLED_STATE"]).read_text(
        encoding="utf-8"
    ).strip() == "1"


def exit_130(_signum, _frame):
    signal_file = os.environ.get("CODEX_CHILD_SIGNAL_FILE")
    if signal_file:
        Path(signal_file).write_text("signaled", encoding="utf-8")
    raise SystemExit(130)


def exit_on_term(_signum, _frame):
    term_file = os.environ.get("CODEX_CHILD_TERM_FILE")
    if term_file:
        Path(term_file).write_text("terminated", encoding="utf-8")
    term_installed = os.environ.get("CODEX_CHILD_TERM_INSTALLED")
    if term_installed is not None:
        set_installed(term_installed == "1")
    if os.environ.get("CODEX_CHILD_IGNORE_TERM") == "1":
        return
    raise SystemExit(int(os.environ.get("CODEX_CHILD_TERM_EXIT", "143")))


if action == "list":
    returncode = int(os.environ.get("CODEX_LIST_EXIT", "0"))
    if returncode == 0:
        if "CODEX_LIST_JSON" in os.environ:
            output = os.environ["CODEX_LIST_JSON"]
        else:
            installed = []
            marketplace_has_bid = True
            if os.environ.get("CODEX_LIST_REQUIRE_BID_ENTRY") == "1":
                try:
                    marketplace = json.loads(
                        Path(os.environ["MARKETPLACE_FILE"]).read_text(
                            encoding="utf-8"
                        )
                    )
                    marketplace_has_bid = any(
                        isinstance(plugin, dict) and plugin.get("name") == "bid"
                        for plugin in marketplace.get("plugins", [])
                    )
                except (FileNotFoundError, json.JSONDecodeError, AttributeError):
                    marketplace_has_bid = False
            if is_installed() and marketplace_has_bid:
                installed.append(
                    {
                        "pluginId": "bid@local-build-your-system",
                        "name": "bid",
                        "marketplaceName": "local-build-your-system",
                        "version": "0.1.0",
                        "installed": True,
                        "enabled": True,
                        "source": {
                            "source": "local",
                            "path": os.environ["SOURCE_ROOT"],
                        },
                    }
                )
            output = json.dumps({"installed": installed, "available": []})
        list_call = sum(
            line == "plugin list --json"
            for line in Path(os.environ["CODEX_LOG"]).read_text(
                encoding="utf-8"
            ).splitlines()
        )
        effect_call = int(os.environ.get("CODEX_LIST_EFFECT_CALL", str(list_call)))
        if list_call == effect_call:
            list_effect = os.environ.get("CODEX_LIST_EFFECT", "")
            if list_effect == "mutate-marketplace":
                Path(os.environ["MARKETPLACE_FILE"]).write_bytes(
                    Path(os.environ["CONCURRENT_MARKETPLACE_FILE"]).read_bytes()
                )
            elif list_effect == "swap-source":
                source = Path(os.environ["SOURCE_ROOT"])
                source.unlink()
                source.symlink_to(Path(os.environ["OTHER_SOURCE"]))
        print(output)
    raise SystemExit(returncode)

effect = os.environ.get(f"CODEX_{action.upper()}_EFFECT", "")
if effect == "mutate-marketplace":
    Path(os.environ["MARKETPLACE_FILE"]).write_bytes(
        Path(os.environ["CONCURRENT_MARKETPLACE_FILE"]).read_bytes()
    )
elif effect == "lock-marketplace-parent":
    Path(os.environ["MARKETPLACE_FILE"]).parent.chmod(0o500)
elif effect == "lock-source-parent":
    Path(os.environ["SOURCE_ROOT"]).parent.chmod(0o500)
elif effect == "chmod-marketplace":
    Path(os.environ["MARKETPLACE_FILE"]).chmod(0o600)
elif effect == "replace-marketplace-identical":
    marketplace = Path(os.environ["MARKETPLACE_FILE"])
    original_mode = marketplace.stat().st_mode & 0o777
    temp_fd, temp_name = tempfile.mkstemp(dir=marketplace.parent)
    with os.fdopen(temp_fd, "wb") as temp_file:
        temp_file.write(marketplace.read_bytes())
        temp_file.flush()
        os.fsync(temp_file.fileno())
        os.fchmod(temp_file.fileno(), original_mode)
    os.replace(temp_name, marketplace)
elif effect == "swap-source":
    source = Path(os.environ["SOURCE_ROOT"])
    source.unlink()
    source.symlink_to(Path(os.environ["OTHER_SOURCE"]))

effect_state_file = os.environ.get("CODEX_EFFECT_STATE")
if effect_state_file and effect:
    marketplace = Path(os.environ["MARKETPLACE_FILE"])
    source = Path(os.environ["SOURCE_ROOT"])
    marketplace_stat = marketplace.lstat()
    source_stat = source.lstat()
    Path(effect_state_file).write_text(
        json.dumps(
            {
                "marketplace": {
                    "dev": marketplace_stat.st_dev,
                    "ino": marketplace_stat.st_ino,
                    "mode": marketplace_stat.st_mode & 0o777,
                    "bytes_hex": marketplace.read_bytes().hex(),
                },
                "source": {
                    "dev": source_stat.st_dev,
                    "ino": source_stat.st_ino,
                    "target": os.readlink(source),
                },
            }
        ),
        encoding="utf-8",
    )

if action == "add" and os.environ.get("CODEX_ADD_RESTORE_PERMISSIONS") == "1":
    Path(os.environ["MARKETPLACE_FILE"]).parent.chmod(0o700)
    Path(os.environ["SOURCE_ROOT"]).parent.chmod(0o700)

returncode = os.environ.get(
    f"CODEX_{action.upper()}_EXIT", os.environ.get("CODEX_EXIT_CODE", "0")
)
returncode = int(returncode)


def commit_action():
    if action == "add":
        set_installed(True)
    elif action == "remove":
        set_installed(False)


commit_before_block = (
    os.environ.get(f"CODEX_{action.upper()}_COMMIT_BEFORE_BLOCK") == "1"
    or (
        action == "remove"
        and os.environ.get("CODEX_REMOVE_MUTATE_BEFORE_BLOCK") == "1"
    )
)
if returncode == 0 and commit_before_block:
    commit_action()

action_call = sum(
    line == " ".join(args)
    for line in Path(os.environ["CODEX_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines()
)
block_call = int(
    os.environ.get(f"CODEX_{action.upper()}_BLOCK_CALL", str(action_call))
)
if (
    os.environ.get(f"CODEX_{action.upper()}_BLOCK") == "1"
    and action_call == block_call
):
    signal.signal(signal.SIGINT, exit_130)
    signal.signal(signal.SIGTERM, exit_on_term)
    Path(os.environ[f"CODEX_{action.upper()}_READY"]).write_text(
        "ready", encoding="utf-8"
    )
    release_file = Path(os.environ[f"CODEX_{action.upper()}_RELEASE"])
    while not release_file.exists():
        time.sleep(0.01)

if returncode == 0 and not commit_before_block:
    commit_action()
raise SystemExit(returncode)
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
        self.codex_installed_state = self.home / "codex-installed-state"
        self.codex_installed_state.write_text("1", encoding="utf-8")
        self.env["CODEX_INSTALLED_STATE"] = str(self.codex_installed_state)
        self.effect_state = self.home / "codex-effect-state.json"
        self.env["CODEX_EFFECT_STATE"] = str(self.effect_state)

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

    def run_installer_and_interrupt(self, action, *args):
        ready_file = self.home / f"codex-{action}-ready"
        release_file = self.home / f"codex-{action}-release"
        child_signal_file = self.home / f"codex-{action}-child-signaled"
        child_term_file = self.home / f"codex-{action}-child-terminated"
        self.env[f"CODEX_{action.upper()}_BLOCK"] = "1"
        self.env[f"CODEX_{action.upper()}_BLOCK_CALL"] = "1"
        self.env[f"CODEX_{action.upper()}_READY"] = str(ready_file)
        self.env[f"CODEX_{action.upper()}_RELEASE"] = str(release_file)
        self.env["CODEX_CHILD_SIGNAL_FILE"] = str(child_signal_file)
        self.env["CODEX_CHILD_TERM_FILE"] = str(child_term_file)
        process = subprocess.Popen(
            ["zsh", str(INSTALLER), *args],
            cwd=BID_ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        deadline = time.monotonic() + 5
        try:
            while not ready_file.exists():
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.fail(
                        f"installer exited before {action} was ready: "
                        f"{process.returncode}\nstdout={stdout}\nstderr={stderr}"
                    )
                if time.monotonic() >= deadline:
                    self.fail(f"timed out waiting for blocked codex {action}")
                time.sleep(0.01)
            os.killpg(process.pid, signal.SIGINT)
            stdout, stderr = process.communicate(timeout=8)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        return subprocess.CompletedProcess(
            process.args, process.returncode, stdout, stderr
        )

    def child_received_sigint(self, action):
        return (self.home / f"codex-{action}-child-signaled").exists()

    def child_received_sigterm(self, action):
        return (self.home / f"codex-{action}-child-terminated").exists()

    def write_marketplace(self, data):
        self.marketplace_file.parent.mkdir(parents=True, exist_ok=True)
        self.marketplace_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def all_codex_calls(self):
        if not self.codex_log.exists():
            return []
        return self.codex_log.read_text(encoding="utf-8").splitlines()

    def codex_calls(self):
        return [
            call for call in self.all_codex_calls() if call != "plugin list --json"
        ]

    def set_codex_installed(self, installed):
        self.codex_installed_state.write_text(
            "1" if installed else "0", encoding="utf-8"
        )

    def codex_is_installed(self):
        return self.codex_installed_state.read_text(encoding="utf-8") == "1"

    def set_codex_exit(self, returncode):
        self.env["CODEX_EXIT_CODE"] = str(returncode)

    def set_concurrent_marketplace(self, data):
        concurrent_file = self.home / "concurrent-marketplace.json"
        concurrent_file.write_bytes(data)
        self.env["CONCURRENT_MARKETPLACE_FILE"] = str(concurrent_file)

    def assert_unsafe_marketplace_compensation_is_blocked(self, plugins):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        concurrent = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Concurrent"},
            "plugins": plugins,
        }
        concurrent_bytes = (
            json.dumps(concurrent, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.set_concurrent_marketplace(concurrent_bytes)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.env["CODEX_REMOVE_EFFECT"] = "mutate-marketplace"

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("partial", result.stderr.lower())
        self.assertIn("not run", result.stderr.lower())
        self.assertIn("marketplace", result.stderr.lower())
        self.assertFalse(self.codex_is_installed())
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def assert_interrupted_remove_compensation_is_blocked(self, plugins):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        concurrent = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Concurrent"},
            "plugins": plugins,
        }
        concurrent_bytes = (
            json.dumps(concurrent, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.set_concurrent_marketplace(concurrent_bytes)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["CODEX_LIST_REQUIRE_BID_ENTRY"] = "1"
        self.env["CODEX_REMOVE_EFFECT"] = "mutate-marketplace"
        self.env["CODEX_REMOVE_COMMIT_BEFORE_BLOCK"] = "1"

        result = self.run_installer_and_interrupt("remove", "--uninstall")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("partial", result.stderr.lower())
        self.assertIn("marketplace", result.stderr.lower())
        self.assertIn("not run", result.stderr.lower())
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.child_received_sigint("remove"))
        self.assertTrue(self.child_received_sigterm("remove"))
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertTrue(self.source_root.is_symlink())

    def read_effect_state(self):
        return json.loads(self.effect_state.read_text(encoding="utf-8"))

    @property
    def lifecycle_lock_file(self):
        return self.marketplace_file.with_name(f".{self.marketplace_file.name}.lock")

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

    def test_install_prestate_discovery_requires_stable_local_contract(self):
        concurrent = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Concurrent"},
            "plugins": [],
        }
        concurrent_bytes = (
            json.dumps(concurrent, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.set_concurrent_marketplace(concurrent_bytes)
        self.set_codex_installed(False)
        self.env["CODEX_LIST_EFFECT"] = "mutate-marketplace"
        self.env["CODEX_LIST_EFFECT_CALL"] = "1"

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("concurrent", result.stderr.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.codex_is_installed())
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
        self.assertEqual(
            self.all_codex_calls(),
            [
                "plugin list --json",
                "plugin remove bid@local-build-your-system",
            ],
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

    def test_uninstall_compensation_refuses_concurrent_bid_entry_removal(self):
        self.assert_unsafe_marketplace_compensation_is_blocked([])

    def test_uninstall_compensation_refuses_concurrent_bid_entry_replacement(self):
        replacement = {**BID_ENTRY, "category": "Concurrent replacement"}
        self.assert_unsafe_marketplace_compensation_is_blocked([replacement])

    def test_uninstall_compensation_refuses_concurrent_bid_entry_retarget(self):
        retargeted = {
            **BID_ENTRY,
            "source": {"source": "local", "path": "./plugins/not-bid"},
        }
        self.assert_unsafe_marketplace_compensation_is_blocked([retargeted])

    def test_uninstall_same_target_source_replacement_blocks_compensation_add(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "custom": {"preserve": True},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.env["OTHER_SOURCE"] = str(BID_ROOT)
        self.env["CODEX_REMOVE_EFFECT"] = "swap-source"

        result = self.run_installer("--uninstall")

        effect_state = self.read_effect_state()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("partial", result.stderr.lower())
        self.assertIn("source", result.stderr.lower())
        self.assertIn("not run", result.stderr.lower())
        self.assertIn(
            "codex plugin add bid@local-build-your-system", result.stderr
        )
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(
            self.source_root.lstat().st_ino, effect_state["source"]["ino"]
        )

    def test_uninstall_chmod_only_concurrent_edit_is_not_clobbered(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_REMOVE_EFFECT"] = "chmod-marketplace"

        result = self.run_installer("--uninstall")

        effect_state = self.read_effect_state()["marketplace"]
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("concurrent", result.stderr.lower())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o600)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)
        self.assertEqual(self.marketplace_file.stat().st_ino, effect_state["ino"])
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_uninstall_identical_byte_replacement_is_not_clobbered(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_REMOVE_EFFECT"] = "replace-marketplace-identical"

        result = self.run_installer("--uninstall")

        effect_state = self.read_effect_state()["marketplace"]
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("concurrent", result.stderr.lower())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertNotEqual(effect_state["ino"], original_inode)
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.marketplace_file.stat().st_ino, effect_state["ino"])
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_lifecycle_lock_contention_aborts_without_local_mutation(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        lock_fd = os.open(self.lifecycle_lock_file, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = self.run_installer()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lifecycle", result.stderr.lower())
        self.assertIn("lock", result.stderr.lower())
        self.assertIn(str(self.lifecycle_lock_file), result.stderr)
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), [])

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

    def test_uninstall_local_absent_and_codex_absent_is_idempotent(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Local Build Your System"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.set_codex_installed(False)

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("absent", result.stdout.lower())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)
        self.assertFalse(self.source_root.exists())
        self.assertEqual(
            self.all_codex_calls(), ["plugin remove bid@local-build-your-system"]
        )

    def test_uninstall_local_absent_and_list_omits_orphan_still_removes_codex_state(
        self,
    ):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.set_codex_installed(True)
        self.env["CODEX_LIST_JSON"] = REAL_CODEX_ORPHAN_LIST_FIXTURE

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)
        self.assertFalse(self.source_root.exists())

    def test_uninstall_local_present_and_codex_absent_cleans_only_local_state(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "custom": {"preserve": True},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(False)

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(self.marketplace_file.read_text(encoding="utf-8"))
        self.assertEqual(updated["plugins"], [])
        self.assertEqual(updated["custom"], {"preserve": True})
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.codex_is_installed())
        self.assertEqual(
            self.all_codex_calls(),
            [
                "plugin list --json",
                "plugin remove bid@local-build-your-system",
            ],
        )

    def test_uninstall_local_absent_does_not_consult_failing_discovery(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.env["CODEX_LIST_EXIT"] = "17"

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertEqual(
            self.all_codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)

    def test_uninstall_local_absent_does_not_consult_malformed_discovery(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.env["CODEX_LIST_JSON"] = '{"installed": {}}'

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertEqual(
            self.all_codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)

    def test_uninstall_local_present_stops_if_discovery_query_fails(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_LIST_EXIT"] = "17"

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plugin list", result.stderr.lower())
        self.assertIn("17", result.stderr)
        self.assertEqual(self.all_codex_calls(), ["plugin list --json"])
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

    def test_uninstall_local_present_stops_if_discovery_json_is_malformed(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.env["CODEX_LIST_JSON"] = '{"installed": {}}'

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installed", result.stderr.lower())
        self.assertIn("list", result.stderr.lower())
        self.assertEqual(self.all_codex_calls(), ["plugin list --json"])
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

    def test_uninstall_prestate_discovery_requires_stable_source_contract(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        other_source = self.home / "other-source"
        other_source.mkdir()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["OTHER_SOURCE"] = str(other_source)
        self.env["CODEX_LIST_EFFECT"] = "swap-source"
        self.env["CODEX_LIST_EFFECT_CALL"] = "1"

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.all_codex_calls(), ["plugin list --json"])
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.readlink(), other_source)

    def test_sigint_after_add_commits_removes_codex_state_before_local_rollback(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_COMMIT_BEFORE_BLOCK"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("interrupt", result.stderr.lower())
        self.assertIn("rolled back", result.stderr.lower())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.child_received_sigint("add"))
        self.assertTrue(self.child_received_sigterm("add"))
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin add bid@local-build-your-system",
                "plugin remove bid@local-build-your-system",
            ],
        )
        lock_fd = os.open(self.lifecycle_lock_file, os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def test_sigint_after_add_commit_directly_removes_orphan_if_marketplace_changed(
        self,
    ):
        concurrent = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Concurrent"},
            "plugins": [],
        }
        concurrent_bytes = (
            json.dumps(concurrent, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.set_concurrent_marketplace(concurrent_bytes)
        self.set_codex_installed(False)
        self.env["CODEX_ADD_EFFECT"] = "mutate-marketplace"
        self.env["CODEX_ADD_COMMIT_BEFORE_BLOCK"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("partial", result.stderr.lower())
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.child_received_sigint("add"))
        self.assertTrue(self.child_received_sigterm("add"))
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin add bid@local-build-your-system",
                "plugin remove bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertFalse(self.source_root.exists())

    def test_interrupted_install_refuses_add_if_contract_changes_during_requery(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        retargeted = {
            **BID_ENTRY,
            "source": {"source": "local", "path": "./plugins/not-bid"},
        }
        concurrent = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Concurrent"},
            "plugins": [retargeted],
        }
        concurrent_bytes = (
            json.dumps(concurrent, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.set_concurrent_marketplace(concurrent_bytes)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "0"
        self.env["CODEX_LIST_EFFECT"] = "mutate-marketplace"
        self.env["CODEX_LIST_EFFECT_CALL"] = "2"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("partial", result.stderr.lower())
        self.assertFalse(self.codex_is_installed())
        self.assertEqual(self.codex_calls(), ["plugin add bid@local-build-your-system"])
        self.assertEqual(self.marketplace_file.read_bytes(), concurrent_bytes)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_sigint_escalates_to_sigkill_if_isolated_child_ignores_sigterm(self):
        self.set_codex_installed(False)
        self.env["CODEX_CHILD_IGNORE_TERM"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("sigkill", result.stderr.lower())
        self.assertFalse(self.child_received_sigint("add"))
        self.assertTrue(self.child_received_sigterm("add"))
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())

    def test_sigint_before_remove_commits_does_not_run_unneeded_add(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_EXIT"] = "130"

        result = self.run_installer_and_interrupt("remove", "--uninstall")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("interrupt", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertFalse(self.child_received_sigint("remove"))
        self.assertTrue(self.child_received_sigterm("remove"))
        self.assertEqual(
            self.codex_calls(), ["plugin remove bid@local-build-your-system"]
        )
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

    def test_local_absent_interrupted_remove_retries_even_if_child_exits_zero(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [],
        }
        self.write_marketplace(existing)
        self.set_codex_installed(True)
        self.env["CODEX_CHILD_TERM_EXIT"] = "0"

        result = self.run_installer_and_interrupt("remove", "--uninstall")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.child_received_sigint("remove"))
        self.assertTrue(self.child_received_sigterm("remove"))
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin remove bid@local-build-your-system",
            ],
        )

    def test_sigint_after_remove_commits_restores_installed_and_local_state(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.marketplace_file.chmod(0o640)
        original_bytes = self.marketplace_file.read_bytes()
        original_inode = self.marketplace_file.stat().st_ino
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        source_inode = self.source_root.lstat().st_ino
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_COMMIT_BEFORE_BLOCK"] = "1"

        result = self.run_installer_and_interrupt("remove", "--uninstall")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("interrupt", result.stderr.lower())
        self.assertIn("restored", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertFalse(self.child_received_sigint("remove"))
        self.assertTrue(self.child_received_sigterm("remove"))
        self.assertEqual(
            self.all_codex_calls(),
            [
                "plugin list --json",
                "plugin remove bid@local-build-your-system",
                "plugin list --json",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(stat.S_IMODE(self.marketplace_file.stat().st_mode), 0o640)
        self.assertEqual(self.marketplace_file.stat().st_ino, original_inode)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        lock_fd = os.open(self.lifecycle_lock_file, os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def test_sigint_after_remove_commit_refuses_add_if_marketplace_entry_changed(self):
        self.assert_interrupted_remove_compensation_is_blocked([])

    def test_sigint_after_remove_commit_refuses_add_if_marketplace_entry_replaced(
        self,
    ):
        replacement = {**BID_ENTRY, "category": "Concurrent replacement"}
        self.assert_interrupted_remove_compensation_is_blocked([replacement])

    def test_sigint_after_remove_commit_refuses_add_if_marketplace_entry_retargeted(
        self,
    ):
        retargeted = {
            **BID_ENTRY,
            "source": {"source": "local", "path": "./plugins/not-bid"},
        }
        self.assert_interrupted_remove_compensation_is_blocked([retargeted])

    def test_uninstall_documentation_distinguishes_deleted_and_preserved_state(self):
        text = README.read_text(encoding="utf-8")

        self.assertIn("Codex 自己管理的已安装配置与缓存", text)
        self.assertIn("Claude 状态", text)
        self.assertIn("项目内 `.claude/memory/`", text)
        self.assertIn("`.marketplace.json.lock`", text)
        self.assertIn("补偿安装不会执行", text)
        self.assertIn("codex plugin list --json", text)
        self.assertIn("不会把 list 的空结果当作已卸载证据", text)
        self.assertIn("幂等的 `codex plugin remove", text)
        self.assertIn("SIGKILL", text)
        stale_claim = "Codex/Claude cache 和项目内 `.claude/memory/` 永不删除"
        self.assertNotIn(stale_claim, text)

    def test_first_install_requires_stable_main_checkout_source(self):
        text = README.read_text(encoding="utf-8")
        first_install = text.split("### Codex 首次本地安装", 1)[1].split("##", 1)[0]

        self.assertIn("稳定的主 checkout", first_install)
        self.assertIn("`.worktrees/`", first_install)
        self.assertIn("缓存目录", first_install)
        self.assertIn("不得", first_install)

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
