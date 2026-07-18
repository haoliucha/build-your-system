import ast
import fcntl
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

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

action_call = sum(
    line == " ".join(args)
    for line in Path(os.environ["CODEX_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines()
)
effect_call = int(
    os.environ.get(f"CODEX_{action.upper()}_EFFECT_CALL", str(action_call))
)
effect = (
    os.environ.get(f"CODEX_{action.upper()}_EFFECT", "")
    if action_call == effect_call
    else ""
)
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
elif effect == "mutate-source-content":
    source_file = Path(os.environ["SOURCE_CONTENT_FILE"])
    source_file.write_text(
        source_file.read_text(encoding="utf-8") + "\\nconcurrent edit\\n",
        encoding="utf-8",
    )
elif effect == "replace-source-content":
    source_file = Path(os.environ["SOURCE_CONTENT_FILE"])
    original_mode = source_file.stat().st_mode & 0o777
    temp_fd, temp_name = tempfile.mkstemp(dir=source_file.parent)
    with os.fdopen(temp_fd, "wb") as temp_file:
        temp_file.write(source_file.read_bytes())
        temp_file.flush()
        os.fsync(temp_file.fileno())
        os.fchmod(temp_file.fileno(), original_mode)
    os.replace(temp_name, source_file)

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
    f"CODEX_{action.upper()}_EXIT_CALL_{action_call}",
    os.environ.get(
        f"CODEX_{action.upper()}_EXIT", os.environ.get("CODEX_EXIT_CODE", "0")
    ),
)
returncode = int(returncode)


def commit_action():
    if action == "add":
        set_installed(True)
    elif action == "remove":
        set_installed(False)


commit_before_exit = (
    os.environ.get(f"CODEX_{action.upper()}_COMMIT_BEFORE_EXIT") == "1"
)
commit_before_block = (
    os.environ.get(f"CODEX_{action.upper()}_COMMIT_BEFORE_BLOCK") == "1"
    or (
        action == "remove"
        and os.environ.get("CODEX_REMOVE_MUTATE_BEFORE_BLOCK") == "1"
    )
)
commit_early = commit_before_exit or commit_before_block
skip_commit = (
    os.environ.get(f"CODEX_{action.upper()}_SKIP_COMMIT") == "1"
    or os.environ.get(
        f"CODEX_{action.upper()}_SKIP_COMMIT_CALL_{action_call}"
    )
    == "1"
)
if not skip_commit and (returncode == 0 or commit_before_exit) and commit_early:
    commit_action()

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
        json.dumps({"pid": os.getpid(), "pgid": os.getpgrp()}),
        encoding="utf-8",
    )
    release_file = Path(os.environ[f"CODEX_{action.upper()}_RELEASE"])
    while not release_file.exists():
        time.sleep(0.01)

if returncode == 0 and not commit_early and not skip_commit:
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

    def load_lifecycle_module(self):
        module_name = f"bid_lifecycle_test_{id(self)}_{time.monotonic_ns()}"
        spec = importlib.util.spec_from_file_location(module_name, LIFECYCLE)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        lifecycle_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = lifecycle_module
        self.addCleanup(sys.modules.pop, module_name, None)
        lifecycle_source = LIFECYCLE.read_text(encoding="utf-8")
        definitions = lifecycle_source.rsplit(
            "\ntry:\n    raise SystemExit(main())", 1
        )[0]
        exec(compile(definitions, LIFECYCLE, "exec"), lifecycle_module.__dict__)
        return lifecycle_module

    def new_lifecycle(self, bid_root=BID_ROOT):
        lifecycle_module = self.load_lifecycle_module()
        with mock.patch.object(lifecycle_module.Path, "home", return_value=self.home):
            lifecycle = lifecycle_module.LocalLifecycle(bid_root)
        return lifecycle_module, lifecycle

    def make_source_tree(self):
        source = self.home / "source-checkout/bid"
        (source / ".codex-plugin").mkdir(parents=True)
        (source / "skills/example").mkdir(parents=True)
        (source / "scripts").mkdir()
        (source / "docs").mkdir()
        (source / ".codex-plugin/plugin.json").write_text(
            '{"name":"bid","version":"0.1.0"}\n', encoding="utf-8"
        )
        (source / "skills/example/SKILL.md").write_text(
            "---\nname: example\n---\n", encoding="utf-8"
        )
        (source / "scripts/example.py").write_text(
            "print('stable')\n", encoding="utf-8"
        )
        (source / "docs/contract.md").write_text("stable\n", encoding="utf-8")
        return source

    def terminate_test_child_group(self, child_pid):
        try:
            child_pgid = os.getpgid(child_pid)
        except ProcessLookupError:
            return
        command = subprocess.run(
            ["ps", "-p", str(child_pid), "-o", "command="],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
        if child_pgid != child_pid or "fake-bin/codex plugin" not in command:
            self.fail(
                f"refusing to kill unexpected test child pid={child_pid} "
                f"pgid={child_pgid} command={command!r}"
            )
        os.killpg(child_pgid, signal.SIGKILL)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
        self.fail(f"test child process group {child_pid} was not reaped")

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
        child_pid = None
        deadline = time.monotonic() + 5
        try:
            while child_pid is None:
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.fail(
                        f"installer exited before {action} was ready: "
                        f"{process.returncode}\nstdout={stdout}\nstderr={stderr}"
                    )
                if time.monotonic() >= deadline:
                    self.fail(f"timed out waiting for blocked codex {action}")
                if ready_file.exists():
                    try:
                        child_pid = json.loads(
                            ready_file.read_text(encoding="utf-8")
                        )["pid"]
                    except (json.JSONDecodeError, KeyError):
                        pass
                time.sleep(0.01)
            os.killpg(process.pid, signal.SIGINT)
            stdout, stderr = process.communicate(timeout=8)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            if child_pid is not None:
                self.terminate_test_child_group(child_pid)
        return subprocess.CompletedProcess(
            process.args, process.returncode, stdout, stderr
        )

    def run_installer_and_parent_sigterm(self, action, *args):
        ready_file = self.home / f"codex-{action}-parent-term-ready"
        self.env[f"CODEX_{action.upper()}_BLOCK"] = "1"
        self.env[f"CODEX_{action.upper()}_BLOCK_CALL"] = "1"
        self.env[f"CODEX_{action.upper()}_READY"] = str(ready_file)
        self.env[f"CODEX_{action.upper()}_RELEASE"] = str(
            self.home / f"codex-{action}-parent-term-release"
        )
        self.env["CODEX_CHILD_SIGNAL_FILE"] = str(
            self.home / f"codex-{action}-parent-term-child-signaled"
        )
        self.env["CODEX_CHILD_TERM_FILE"] = str(
            self.home / f"codex-{action}-parent-term-child-terminated"
        )
        process = subprocess.Popen(
            ["zsh", str(INSTALLER), *args],
            cwd=BID_ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        child_pid = None
        child_alive_after_parent = False
        deadline = time.monotonic() + 8
        try:
            while child_pid is None:
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.fail(
                        f"installer exited before {action} was ready: "
                        f"{process.returncode}\nstdout={stdout}\nstderr={stderr}"
                    )
                if time.monotonic() >= deadline:
                    self.fail(f"timed out waiting for blocked codex {action}")
                if ready_file.exists():
                    try:
                        child_pid = json.loads(
                            ready_file.read_text(encoding="utf-8")
                        )["pid"]
                    except (json.JSONDecodeError, KeyError):
                        pass
                time.sleep(0.01)
            os.kill(process.pid, signal.SIGTERM)
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    self.fail("timed out waiting for parent SIGTERM handling")
                time.sleep(0.01)
            try:
                os.kill(child_pid, 0)
                child_alive_after_parent = True
            except ProcessLookupError:
                pass
            if child_alive_after_parent:
                self.terminate_test_child_group(child_pid)
            stdout, stderr = process.communicate(timeout=2)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            if child_pid is not None:
                self.terminate_test_child_group(child_pid)
        self.last_parent_sigterm_child_pid = child_pid
        self.last_parent_sigterm_child_alive = child_alive_after_parent
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

    def test_sigint_after_source_creation_rolls_back_owned_local_state(self):
        lifecycle_module, lifecycle = self.new_lifecycle()
        original_symlink_to = lifecycle_module.Path.symlink_to

        def interrupt_after_symlink(path, target, *args, **kwargs):
            result = original_symlink_to(path, target, *args, **kwargs)
            if path == lifecycle.source_root:
                os.kill(os.getpid(), signal.SIGINT)
            return result

        previous_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)
        try:
            with mock.patch.object(
                lifecycle_module.Path,
                "symlink_to",
                interrupt_after_symlink,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    lifecycle.install()
        finally:
            signal.signal(signal.SIGINT, previous_sigint)

        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertFalse(self.marketplace_file.exists())
        self.assertEqual(self.codex_calls(), [])

    def test_sigterm_after_first_marketplace_write_rolls_back_local_state(self):
        lifecycle_module, lifecycle = self.new_lifecycle()
        original_write_marketplace = lifecycle.write_marketplace

        def terminate_after_write(*args, **kwargs):
            snapshot = original_write_marketplace(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return snapshot

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.object(
                lifecycle,
                "write_marketplace",
                side_effect=terminate_after_write,
            ):
                with self.assertRaises(lifecycle_module.ParentTermination):
                    lifecycle.install()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.source_root.is_symlink())
        self.assertEqual(self.codex_calls(), [])

    def test_sigint_during_popen_construction_reaps_the_created_child(self):
        lifecycle_module = self.load_lifecycle_module()
        original_popen = lifecycle_module.subprocess.Popen
        spawned = []

        def signal_after_child_creation(*_args, **kwargs):
            child = original_popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                start_new_session=True,
                preexec_fn=kwargs.get("preexec_fn"),
            )
            spawned.append(child)
            os.kill(os.getpid(), signal.SIGINT)
            return child

        escaped = False
        result = None
        previous_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)
        try:
            with mock.patch.object(
                lifecycle_module.subprocess,
                "Popen",
                side_effect=signal_after_child_creation,
            ):
                try:
                    result = lifecycle_module.LocalLifecycle.run_codex("add")
                except KeyboardInterrupt:
                    escaped = True
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            for child in spawned:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)

        self.assertFalse(escaped, "SIGINT escaped before child ownership")
        self.assertIsNotNone(result)
        self.assertTrue(result.interrupted)
        self.assertTrue(spawned)
        self.assertIsNotNone(spawned[0].poll())

    def test_sigterm_after_add_child_return_reconciles_complete_transaction(self):
        lifecycle_module, lifecycle = self.new_lifecycle()
        self.set_codex_installed(False)
        original_run_codex = lifecycle.run_codex
        add_calls = 0

        def terminate_after_add(action):
            nonlocal add_calls
            result = original_run_codex(action)
            if action == "add":
                add_calls += 1
                if add_calls == 1:
                    os.kill(os.getpid(), signal.SIGTERM)
            return result

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle, "run_codex", side_effect=terminate_after_add
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.install()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())

    def test_sigterm_after_remove_child_return_reconciles_complete_transaction(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        lifecycle_module, lifecycle = self.new_lifecycle()
        original_run_codex = lifecycle.run_codex
        remove_calls = 0

        def terminate_after_remove(action):
            nonlocal remove_calls
            result = original_run_codex(action)
            if action == "remove":
                remove_calls += 1
                if remove_calls == 1:
                    os.kill(os.getpid(), signal.SIGTERM)
            return result

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle, "run_codex", side_effect=terminate_after_remove
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.uninstall()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertTrue(self.source_root.is_symlink())

    def test_sigterm_during_actual_add_result_dispatch_reconciles_transaction(self):
        lifecycle_module, lifecycle = self.new_lifecycle()
        self.set_codex_installed(False)
        original_run_codex = lifecycle.run_codex
        first_add = True

        class TerminatingResult:
            returncode = 0
            interruption_exit_code = None

            @property
            def interrupted(self):
                os.kill(os.getpid(), signal.SIGTERM)
                return False

        def committed_add(action):
            nonlocal first_add
            if action == "add" and first_add:
                first_add = False
                self.set_codex_installed(True)
                return TerminatingResult()
            return original_run_codex(action)

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle, "run_codex", side_effect=committed_add
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.install()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())

    def test_sigterm_during_actual_remove_result_dispatch_reconciles_transaction(
        self,
    ):
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
        self.set_codex_installed(True)
        lifecycle_module, lifecycle = self.new_lifecycle()
        original_run_codex = lifecycle.run_codex
        first_remove = True

        class TerminatingResult:
            returncode = 0
            interruption_exit_code = None

            @property
            def interrupted(self):
                os.kill(os.getpid(), signal.SIGTERM)
                return False

        def committed_remove(action):
            nonlocal first_remove
            if action == "remove" and first_remove:
                first_remove = False
                self.set_codex_installed(False)
                return TerminatingResult()
            return original_run_codex(action)

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle, "run_codex", side_effect=committed_remove
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.uninstall()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

    def test_add_commit_then_nonzero_restores_preoperation_installed_state(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_EXIT"] = "23"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"

        result = self.run_installer()

        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin add bid@local-build-your-system",
                "plugin remove bid@local-build-your-system",
            ],
        )

    def test_sigterm_during_nonzero_add_compensation_returns_143(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_EXIT"] = "23"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "0"

        result = self.run_installer_and_parent_sigterm("remove")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())
        self.assertFalse(self.last_parent_sigterm_child_alive)

    def test_failed_nested_sigterm_compensation_still_returns_143(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_EXIT"] = "23"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "1"
        self.env["CODEX_REMOVE_EXIT_CALL_2"] = "31"
        self.env["CODEX_REMOVE_SKIP_COMMIT_CALL_2"] = "1"

        result = self.run_installer_and_parent_sigterm("remove")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertTrue(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())
        self.assertFalse(self.last_parent_sigterm_child_alive)

    def test_nested_sigterm_code_survives_local_rollback_failure(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_EXIT"] = "23"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"
        self.env["CODEX_ADD_EFFECT"] = "lock-source-parent"
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "0"
        self.addCleanup(self.source_root.parent.chmod, 0o700)

        result = self.run_installer_and_parent_sigterm("remove")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())
        self.assertFalse(self.last_parent_sigterm_child_alive)

    def test_add_nonzero_failed_compensation_preserves_trusted_local_contract(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_EXIT"] = "23"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"
        self.env["CODEX_REMOVE_EXIT"] = "31"

        result = self.run_installer()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("partial", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        marketplace = json.loads(self.marketplace_file.read_text(encoding="utf-8"))
        self.assertEqual(marketplace["plugins"], [BID_ENTRY])
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin add bid@local-build-your-system",
                "plugin remove bid@local-build-your-system",
            ],
        )

    def test_add_zero_without_installed_poststate_does_not_report_success(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_SKIP_COMMIT"] = "1"

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())
        self.assertNotIn("Reminder:", result.stdout)

    def test_source_content_edit_during_add_blocks_success(self):
        source = self.make_source_tree()
        content_file = source / "skills/example/SKILL.md"
        lifecycle_module, lifecycle = self.new_lifecycle(source)
        self.set_codex_installed(False)
        direct_env = {
            **self.env,
            "CODEX_ADD_EFFECT": "mutate-source-content",
            "SOURCE_CONTENT_FILE": str(content_file),
        }

        with mock.patch.dict(os.environ, direct_env, clear=False):
            result = lifecycle.install()

        self.assertNotEqual(result, 0)
        self.assertTrue(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())

    def test_source_file_replacement_during_compensation_blocks_success_claim(self):
        source = self.make_source_tree()
        content_file = source / "scripts/example.py"
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(source)
        self.set_codex_installed(True)
        lifecycle_module, lifecycle = self.new_lifecycle(source)
        original_unlink = lifecycle_module.Path.unlink

        def fail_source_unlink(path, *args, **kwargs):
            if path == lifecycle.source_root:
                raise OSError("forced source removal failure")
            return original_unlink(path, *args, **kwargs)

        direct_env = {
            **self.env,
            "CODEX_ADD_EFFECT": "replace-source-content",
            "SOURCE_CONTENT_FILE": str(content_file),
        }
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, direct_env, clear=False):
            with mock.patch.object(
                lifecycle_module.Path, "unlink", fail_source_unlink
            ):
                with redirect_stderr(stderr):
                    result = lifecycle.uninstall()

        self.assertEqual(result, 1)
        self.assertTrue(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())
        self.assertNotIn("Compensation succeeded", stderr.getvalue())
        self.assertIn("content", stderr.getvalue().lower())

    def test_source_content_entry_limit_fails_closed_with_diagnostic(self):
        source = self.make_source_tree()
        lifecycle_module, lifecycle = self.new_lifecycle(source)
        lifecycle.SOURCE_TREE_MAX_ENTRIES = 2

        with self.assertRaisesRegex(
            lifecycle_module.ConflictError, "entry limit"
        ):
            lifecycle.capture_source_tree_snapshot()

    def test_source_content_byte_limit_fails_closed_with_diagnostic(self):
        source = self.make_source_tree()
        lifecycle_module, lifecycle = self.new_lifecycle(source)
        lifecycle.SOURCE_TREE_MAX_BYTES = 4

        with self.assertRaisesRegex(lifecycle_module.ConflictError, "byte limit"):
            lifecycle.capture_source_tree_snapshot()

    def test_source_tree_rejects_symlinked_file_without_following_target(self):
        source = self.make_source_tree()
        external = self.home / "external-skill.md"
        external.write_bytes(b"x" * 256)
        skill = source / "skills/example/SKILL.md"
        skill.unlink()
        skill.symlink_to(external)
        lifecycle_module, lifecycle = self.new_lifecycle(source)
        lifecycle.SOURCE_TREE_MAX_BYTES = 128

        with self.assertRaises(lifecycle_module.ConflictError) as raised:
            lifecycle.capture_source_tree_snapshot()

        self.assertIn("symlink", str(raised.exception).lower())
        self.assertIn(str(skill), str(raised.exception))

    def test_source_tree_rejects_symlinked_directory(self):
        source = self.make_source_tree()
        external = self.home / "external-docs"
        external.mkdir()
        (external / "guide.md").write_text("outside\n", encoding="utf-8")
        docs = source / "docs"
        (docs / "contract.md").unlink()
        docs.rmdir()
        docs.symlink_to(external, target_is_directory=True)
        lifecycle_module, lifecycle = self.new_lifecycle(source)

        with self.assertRaises(lifecycle_module.ConflictError) as raised:
            lifecycle.capture_source_tree_snapshot()

        self.assertIn("symlink", str(raised.exception).lower())
        self.assertIn(str(docs), str(raised.exception))

    def test_sigterm_after_child_reap_is_recorded_before_handler_restore(self):
        module_name = "bid_lifecycle_signal_race_test"
        spec = importlib.util.spec_from_file_location(module_name, LIFECYCLE)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        lifecycle = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = lifecycle
        self.addCleanup(sys.modules.pop, module_name, None)
        lifecycle_source = LIFECYCLE.read_text(encoding="utf-8")
        definitions = lifecycle_source.rsplit(
            "\ntry:\n    raise SystemExit(main())", 1
        )[0]
        exec(compile(definitions, LIFECYCLE, "exec"), lifecycle.__dict__)

        installed_handlers = {signal.SIGTERM: signal.SIG_DFL}

        def fake_getsignal(signum):
            return installed_handlers[signum]

        def fake_signal(signum, handler):
            previous = installed_handlers[signum]
            if handler is signal.SIG_DFL and callable(previous):
                previous(signal.SIGTERM, None)
            installed_handlers[signum] = handler
            return previous

        class ReapedProcess:
            pid = 424242

            def __init__(self):
                self.returncode = None

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        original_getsignal = lifecycle.signal.getsignal
        original_signal = lifecycle.signal.signal
        original_popen = lifecycle.subprocess.Popen
        lifecycle.signal.getsignal = fake_getsignal
        lifecycle.signal.signal = fake_signal
        lifecycle.subprocess.Popen = lambda *args, **kwargs: ReapedProcess()
        self.addCleanup(setattr, lifecycle.signal, "getsignal", original_getsignal)
        self.addCleanup(setattr, lifecycle.signal, "signal", original_signal)
        self.addCleanup(setattr, lifecycle.subprocess, "Popen", original_popen)

        escaped = False
        result = None
        try:
            result = lifecycle.LocalLifecycle.run_codex("add")
        except KeyboardInterrupt:
            escaped = True

        self.assertFalse(escaped, "post-reap SIGTERM escaped run_codex")
        self.assertIsNotNone(result)
        self.assertTrue(result.interrupted)
        self.assertEqual(result.returncode, 0)
        self.assertIs(installed_handlers[signal.SIGTERM], signal.SIG_DFL)

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
                "plugin list --json",
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

    def test_remove_commit_then_nonzero_restores_preoperation_installed_state(self):
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
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_EXIT"] = "29"
        self.env["CODEX_REMOVE_COMMIT_BEFORE_EXIT"] = "1"

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin add bid@local-build-your-system",
            ],
        )
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

    def test_remove_zero_without_absent_poststate_preserves_local_contract(self):
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
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_SKIP_COMMIT"] = "1"

        result = self.run_installer("--uninstall")

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

    def test_unverified_zero_remove_preserves_nested_sigterm_exit_code(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        lifecycle_module, lifecycle = self.new_lifecycle()
        source_snapshot = lifecycle.validate_source()
        self.assertIsNotNone(source_snapshot)
        nested_error = lifecycle_module.CodexStateRecoveryError(
            "nested remove did not converge", 143
        )

        with mock.patch.dict(os.environ, self.env, clear=False):
            result = lifecycle.reconcile_unverified_zero_remove(
                True, source_snapshot, nested_error
            )

        self.assertEqual(result, 143)

    def test_sigint_after_source_removal_restores_preoperation_state(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        lifecycle_module, lifecycle = self.new_lifecycle()
        original_unlink = lifecycle_module.Path.unlink

        def interrupt_after_source_unlink(path, *args, **kwargs):
            result = original_unlink(path, *args, **kwargs)
            if path == lifecycle.source_root:
                os.kill(os.getpid(), signal.SIGINT)
            return result

        previous_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle_module.Path,
                    "unlink",
                    interrupt_after_source_unlink,
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        lifecycle.uninstall()
        finally:
            signal.signal(signal.SIGINT, previous_sigint)

        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertTrue(self.source_root.is_symlink())
        self.assertEqual(self.source_root.readlink(), BID_ROOT)

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

    def test_sigterm_during_failed_uninstall_compensation_returns_143(self):
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
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_EFFECT"] = "lock-marketplace-parent"
        self.env["CODEX_ADD_RESTORE_PERMISSIONS"] = "1"
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "1"
        self.addCleanup(self.marketplace_file.parent.chmod, 0o700)

        result = self.run_installer_and_parent_sigterm("add", "--uninstall")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)
        self.assertFalse(self.last_parent_sigterm_child_alive)

    def test_failed_uninstall_accepts_committed_nonzero_add_compensation(self):
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
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_EFFECT"] = "lock-marketplace-parent"
        self.env["CODEX_ADD_RESTORE_PERMISSIONS"] = "1"
        self.env["CODEX_ADD_EXIT"] = "29"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"
        self.addCleanup(self.marketplace_file.parent.chmod, 0o700)

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Compensation succeeded", result.stderr)
        self.assertNotIn("compensation add failed", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

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

    def test_uninstall_local_absent_commit_then_nonzero_retries_to_convergence(self):
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_EXIT_CALL_1"] = "29"
        self.env["CODEX_REMOVE_COMMIT_BEFORE_EXIT"] = "1"

        result = self.run_installer("--uninstall")

        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())
        self.assertEqual(
            self.codex_calls(),
            [
                "plugin remove bid@local-build-your-system",
                "plugin remove bid@local-build-your-system",
            ],
        )

    def test_sigterm_during_local_absent_primary_result_dispatch_converges(self):
        lifecycle_module, lifecycle = self.new_lifecycle()
        self.set_codex_installed(True)
        original_run_codex = lifecycle.run_codex
        remove_calls = 0

        class TerminatingResult:
            returncode = 29
            interruption_exit_code = None

            @property
            def interrupted(self):
                os.kill(os.getpid(), signal.SIGTERM)
                return False

        def first_remove_handoff(action):
            nonlocal remove_calls
            remove_calls += 1
            if remove_calls == 1:
                return TerminatingResult()
            return original_run_codex(action)

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle, "run_codex", side_effect=first_remove_handoff
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.uninstall()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertFalse(self.codex_is_installed())
        self.assertEqual(remove_calls, 2)

    def test_sigterm_during_local_absent_retry_result_dispatch_converges(self):
        lifecycle_module, lifecycle = self.new_lifecycle()
        self.set_codex_installed(True)
        original_run_codex = lifecycle.run_codex
        remove_calls = 0

        class TerminatingResult:
            returncode = 29
            interruption_exit_code = None

            @property
            def interrupted(self):
                os.kill(os.getpid(), signal.SIGTERM)
                return False

        def retry_remove_handoff(action):
            nonlocal remove_calls
            remove_calls += 1
            if remove_calls == 1:
                return lifecycle_module.CodexCommandResult(29, False)
            if remove_calls == 2:
                return TerminatingResult()
            return original_run_codex(action)

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle, "run_codex", side_effect=retry_remove_handoff
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.uninstall()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertFalse(self.codex_is_installed())
        self.assertEqual(remove_calls, 3)

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
                "plugin list --json",
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

    def test_parent_sigterm_during_add_before_commit_reconciles_and_reaps_child(self):
        self.set_codex_installed(False)

        result = self.run_installer_and_parent_sigterm("add")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.last_parent_sigterm_child_alive)
        self.assertTrue(Path(self.env["CODEX_CHILD_TERM_FILE"]).exists())
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())

    def test_parent_sigterm_during_add_after_commit_reconciles_and_reaps_child(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_COMMIT_BEFORE_BLOCK"] = "1"

        result = self.run_installer_and_parent_sigterm("add")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.last_parent_sigterm_child_alive)
        self.assertTrue(Path(self.env["CODEX_CHILD_TERM_FILE"]).exists())
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())

    def test_interrupted_add_does_not_trust_stale_zero_remove_compensation(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_COMMIT_BEFORE_BLOCK"] = "1"
        self.env["CODEX_REMOVE_SKIP_COMMIT"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("partial", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())

    def test_interrupted_add_accepts_committed_nonzero_remove_compensation(self):
        self.set_codex_installed(False)
        self.env["CODEX_ADD_COMMIT_BEFORE_BLOCK"] = "1"
        self.env["CODEX_REMOVE_EXIT"] = "29"
        self.env["CODEX_REMOVE_COMMIT_BEFORE_EXIT"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("rolled back", result.stderr.lower())
        self.assertNotIn("partial", result.stderr.lower())
        self.assertFalse(self.codex_is_installed())
        self.assertFalse(self.marketplace_file.exists())
        self.assertFalse(self.source_root.exists())

    def test_interrupted_add_does_not_trust_stale_zero_add_compensation(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "0"
        self.env["CODEX_ADD_SKIP_COMMIT"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("partial", result.stderr.lower())
        self.assertFalse(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())

    def test_interrupted_add_accepts_committed_nonzero_add_compensation(self):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["CODEX_CHILD_TERM_INSTALLED"] = "0"
        self.env["CODEX_ADD_EXIT_CALL_2"] = "29"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"

        result = self.run_installer_and_interrupt("add")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("restored", result.stderr.lower())
        self.assertNotIn("partial", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertTrue(self.marketplace_file.exists())
        self.assertTrue(self.source_root.is_symlink())

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

    def test_parent_sigterm_during_remove_before_commit_reconciles_and_reaps_child(
        self,
    ):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)

        result = self.run_installer_and_parent_sigterm("remove", "--uninstall")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.last_parent_sigterm_child_alive)
        self.assertTrue(Path(self.env["CODEX_CHILD_TERM_FILE"]).exists())
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertTrue(self.source_root.is_symlink())

    def test_parent_sigterm_during_remove_after_commit_reconciles_and_reaps_child(
        self,
    ):
        existing = {
            "name": "local-build-your-system",
            "interface": {"displayName": "Keep"},
            "plugins": [BID_ENTRY],
        }
        self.write_marketplace(existing)
        original_bytes = self.marketplace_file.read_bytes()
        self.source_root.parent.mkdir(parents=True)
        self.source_root.symlink_to(BID_ROOT)
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_COMMIT_BEFORE_BLOCK"] = "1"

        result = self.run_installer_and_parent_sigterm("remove", "--uninstall")

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.last_parent_sigterm_child_alive)
        self.assertTrue(Path(self.env["CODEX_CHILD_TERM_FILE"]).exists())
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertTrue(self.source_root.is_symlink())

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
                "plugin list --json",
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

    def test_interrupted_remove_accepts_committed_nonzero_add_compensation(self):
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
        self.set_codex_installed(True)
        self.env["CODEX_REMOVE_COMMIT_BEFORE_BLOCK"] = "1"
        self.env["CODEX_ADD_EXIT"] = "29"
        self.env["CODEX_ADD_COMMIT_BEFORE_EXIT"] = "1"

        result = self.run_installer_and_interrupt("remove", "--uninstall")

        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("restored", result.stderr.lower())
        self.assertNotIn("partial", result.stderr.lower())
        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

    def test_sigint_after_remove_commit_refuses_add_if_marketplace_entry_changed(self):
        self.assert_interrupted_remove_compensation_is_blocked([])

    def test_sigterm_after_remove_verification_restores_before_local_cleanup(self):
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
        self.set_codex_installed(True)
        lifecycle_module, lifecycle = self.new_lifecycle()
        original_restore = lifecycle.restore_codex_state_with_contract

        def terminate_after_absent_verification(installed_before, *args):
            result = original_restore(installed_before, *args)
            if installed_before is False:
                os.kill(os.getpid(), signal.SIGTERM)
            return result

        def raise_parent_termination(_signum, _frame):
            raise lifecycle_module.ParentTermination

        previous_sigterm = signal.signal(signal.SIGTERM, raise_parent_termination)
        try:
            with mock.patch.dict(os.environ, self.env, clear=False):
                with mock.patch.object(
                    lifecycle,
                    "restore_codex_state_with_contract",
                    side_effect=terminate_after_absent_verification,
                ):
                    with self.assertRaises(lifecycle_module.ParentTermination):
                        lifecycle.uninstall()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)

        self.assertTrue(self.codex_is_installed())
        self.assertEqual(self.marketplace_file.read_bytes(), original_bytes)
        self.assertEqual(self.source_root.lstat().st_ino, source_inode)

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
        self.assertIn("SIGINT 或 SIGTERM", text)
        self.assertIn("CLI 返回非零也不被当作", text)
        self.assertIn("内容指纹", text)
        self.assertIn("源码树内部的符号链接", text)
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
