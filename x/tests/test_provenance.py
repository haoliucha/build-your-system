from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import X


PROVENANCE = X / "scripts" / "plugin-provenance.cjs"
MIGRATE = X / "scripts" / "migrate-legacy-skill.sh"


def make_plugin(root: Path, version: str = "4.1.2") -> None:
    for host in (".claude-plugin", ".codex-plugin"):
        directory = root / host
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "plugin.json").write_text(
            json.dumps({"name": "x", "version": version}) + "\n",
            encoding="utf-8",
        )
    for skill in ("x-follow", "x-unfollow"):
        directory = root / "skills" / skill
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: fixture\n---\n",
            encoding="utf-8",
        )


class ProvenanceTests(unittest.TestCase):
    def run_provenance(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(PROVENANCE), *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_runtime_identifies_the_canonical_source_skill(self):
        version = json.loads((X / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        result = self.run_provenance(
            "runtime",
            "--skill=x-unfollow",
            f"--skill-dir={X / 'skills' / 'x-unfollow'}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plugin=x", result.stdout)
        self.assertIn(f"version={version}", result.stdout)
        self.assertIn("host=source", result.stdout)
        self.assertRegex(result.stdout, r"fingerprint=[0-9a-f]{16}")

    def test_runtime_rejects_a_bare_standalone_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "x-unfollow"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: x-unfollow\n---\n", encoding="utf-8")
            result = self.run_provenance(
                "runtime",
                "--skill=x-unfollow",
                f"--skill-dir={skill}",
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("LEGACY_STANDALONE_INSTALL", result.stderr)
        self.assertIn("$x:x-unfollow", result.stderr)

    def test_copied_run_sh_rejects_before_creating_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            standalone = base / "skills" / "x-unfollow"
            standalone.mkdir(parents=True)
            shutil.copy2(X / "skills" / "x-unfollow" / "run.sh", standalone / "run.sh")
            data = base / "data"
            result = subprocess.run(
                ["bash", str(standalone / "run.sh")],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "MY_HANDLE": "fixture", "XU_DATA_DIR": str(data)},
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("LEGACY_STANDALONE_INSTALL", result.stderr)
        self.assertFalse(data.exists())

    def test_account_run_scripts_check_provenance_first(self):
        unfollow = (X / "skills" / "x-unfollow" / "run.sh").read_text(encoding="utf-8")
        follow = (X / "skills" / "x-follow" / "run.sh").read_text(encoding="utf-8")
        self.assertLess(unfollow.index("plugin-provenance.cjs"), unfollow.index("configure-account.cjs"))
        self.assertLess(follow.index("plugin-provenance.cjs"), follow.index("node-runtime.cjs"))
        self.assertIn("LEGACY_STANDALONE_INSTALL", unfollow)
        self.assertIn("LEGACY_STANDALONE_INSTALL", follow)

    def test_doctor_accepts_one_matching_plugin_per_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source" / "x"
            home = base / "home"
            make_plugin(source)

            codex_cache = home / ".codex" / "plugins" / "cache" / "local-build-your-system" / "x" / "4.1.2"
            claude_cache = home / ".claude" / "plugins" / "cache" / "build-your-system" / "x" / "4.1.2"
            historical_codex = home / ".codex" / "plugins" / "cache" / "old-marketplace" / "x" / "4.1.1"
            shutil.copytree(source, codex_cache)
            shutil.copytree(source, claude_cache)
            make_plugin(historical_codex, "4.1.1")

            codex_list = base / "codex.json"
            codex_list.write_text(json.dumps({"installed": [{
                "pluginId": "x@local-build-your-system",
                "name": "x",
                "marketplaceName": "local-build-your-system",
                "version": "4.1.2",
                "installed": True,
                "enabled": True,
            }, {
                "pluginId": "x@old-marketplace", "name": "x", "marketplaceName": "old-marketplace",
                "version": "4.1.1", "installed": False, "enabled": False,
            }]}), encoding="utf-8")
            claude_list = base / "claude.json"
            claude_list.write_text(json.dumps([{
                "id": "x@build-your-system",
                "scope": "user",
                "version": "4.1.2",
                "installPath": str(claude_cache),
                "enabled": True,
            }, {
                "id": "x@old-marketplace",
                "scope": "project",
                "version": "4.0.0",
                "installPath": str(base / "historical-claude-cache"),
                "enabled": False,
            }]), encoding="utf-8")

            result = self.run_provenance(
                "doctor",
                "--json",
                f"--plugin-root={source}",
                f"--home={home}",
                f"--codex-list={codex_list}",
                f"--claude-list={claude_list}",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertTrue(all(check["ok"] for check in report["checks"]))

    def test_doctor_rejects_same_version_content_drift_in_both_host_caches(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source" / "x"
            home = base / "home"
            make_plugin(source)
            codex_cache = home / ".codex" / "plugins" / "cache" / "local-build-your-system" / "x" / "4.1.2"
            claude_cache = base / "claude-cache"
            shutil.copytree(source, codex_cache)
            shutil.copytree(source, claude_cache)
            (codex_cache / "skills" / "x-unfollow" / "SKILL.md").write_text("codex drift\n", encoding="utf-8")
            (claude_cache / "skills" / "x-follow" / "SKILL.md").write_text("claude drift\n", encoding="utf-8")
            codex_list = base / "codex.json"
            codex_list.write_text(json.dumps({"installed": [{
                "name": "x", "marketplaceName": "local-build-your-system", "version": "4.1.2",
                "installed": True, "enabled": True,
            }]}), encoding="utf-8")
            claude_list = base / "claude.json"
            claude_list.write_text(json.dumps([{
                "id": "x@build-your-system", "scope": "user", "enabled": True,
                "version": "4.1.2", "installPath": str(claude_cache),
            }]), encoding="utf-8")
            result = self.run_provenance(
                "doctor", "--json", f"--plugin-root={source}", f"--home={home}",
                f"--codex-list={codex_list}", f"--claude-list={claude_list}",
            )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        failures = {check["name"] for check in report["checks"] if not check["ok"]}
        self.assertIn("codex-fingerprint", failures)
        self.assertIn("claude-fingerprint", failures)

    def test_doctor_rejects_legacy_and_version_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source" / "x"
            home = base / "home"
            make_plugin(source)
            legacy = home / ".agents" / "skills" / "x-unfollow"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text("---\nname: x-unfollow\n---\n", encoding="utf-8")
            codex_list = base / "codex.json"
            codex_list.write_text(json.dumps({"installed": [{
                "name": "x", "marketplaceName": "local-build-your-system",
                "version": "4.1.1", "installed": True, "enabled": True,
            }]}), encoding="utf-8")
            claude_list = base / "claude.json"
            claude_list.write_text(json.dumps([{
                "id": "x@build-your-system", "scope": "user", "enabled": True,
                "version": "4.1.0", "installPath": str(base / "missing"),
            }]), encoding="utf-8")
            result = self.run_provenance(
                "doctor",
                "--json",
                f"--plugin-root={source}",
                f"--home={home}",
                f"--codex-list={codex_list}",
                f"--claude-list={claude_list}",
            )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        failures = {check["name"] for check in report["checks"] if not check["ok"]}
        self.assertIn("legacy-standalone", failures)
        self.assertIn("codex-version", failures)
        self.assertIn("claude-version", failures)

    def test_doctor_rejects_multiple_enabled_claude_x_entries_across_scopes_and_marketplaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source" / "x"
            home = base / "home"
            make_plugin(source)
            codex_cache = home / ".codex" / "plugins" / "cache" / "local-build-your-system" / "x" / "4.1.2"
            claude_cache = base / "claude-cache"
            shutil.copytree(source, codex_cache)
            shutil.copytree(source, claude_cache)
            codex_list = base / "codex.json"
            codex_list.write_text(json.dumps({"installed": [{
                "name": "x", "marketplaceName": "local-build-your-system", "version": "4.1.2",
                "installed": True, "enabled": True,
            }]}), encoding="utf-8")
            claude_list = base / "claude.json"
            claude_list.write_text(json.dumps([{
                "id": "x@build-your-system", "scope": "user", "enabled": True,
                "version": "4.1.2", "installPath": str(claude_cache),
            }, {
                "id": "x@other-marketplace", "scope": "project", "enabled": True,
                "projectPath": "/fixture/project", "version": "4.1.2", "installPath": str(claude_cache),
            }]), encoding="utf-8")
            result = self.run_provenance(
                "doctor", "--json", f"--plugin-root={source}", f"--home={home}",
                f"--codex-list={codex_list}", f"--claude-list={claude_list}",
            )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        check = next(item for item in report["checks"] if item["name"] == "claude-single-active")
        self.assertFalse(check["ok"])
        self.assertIn("active=2", check["detail"])

    def test_every_direct_x_facing_child_rejects_a_standalone_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            follow = base / "follow" / "x-follow"
            unfollow = base / "unfollow" / "x-unfollow"
            shutil.copytree(X / "skills" / "x-follow", follow)
            shutil.copytree(X / "skills" / "x-unfollow", unfollow)
            base_env = {**os.environ, "HOME": str(base / "home")}

            follow_cases = {
                "campaign.cjs": [],
                "harvest.cjs": ["search", "fixture"],
                "smoke-test.cjs": [],
                "snapshot-following.cjs": ["fixture"],
                "verify-follows.cjs": ["fixture"],
            }
            for script, args in follow_cases.items():
                with self.subTest(skill="x-follow", script=script):
                    result = subprocess.run(
                        ["node", str(follow / "scripts" / script), *args],
                        check=False, capture_output=True, text=True, env=base_env,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("LEGACY_STANDALONE_INSTALL", result.stderr + result.stdout)

            data = base / "unfollow-data"
            claim = subprocess.run(
                ["node", str(unfollow / "scripts" / "run-lock.cjs"), "claim"],
                check=False, capture_output=True, text=True,
                env={**base_env, "XU_DATA_DIR": str(data), "XU_RUN_OWNER_PID": str(os.getpid())},
            )
            self.assertEqual(claim.returncode, 0, claim.stderr)
            token = claim.stdout.strip()
            unfollow_env = {
                **base_env, "XU_DATA_DIR": str(data), "XU_RUN_TOKEN": token,
                "MY_HANDLE": "fixture", "ALERT_PATH": str(data / "ALERT.txt"),
            }
            unfollow_cases = {
                "list-snapshot.cjs": ["--list=following", f"--run-id={token}"],
                "profile-counts.cjs": ["fixture"],
                "unfollow.cjs": ["--handles=fixture"],
            }
            for script, args in unfollow_cases.items():
                with self.subTest(skill="x-unfollow", script=script):
                    result = subprocess.run(
                        ["node", str(unfollow / "scripts" / script), *args],
                        check=False, capture_output=True, text=True, env=unfollow_env,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("LEGACY_STANDALONE_INSTALL", result.stderr + result.stdout)

    def test_legacy_migration_is_dry_runnable_and_recoverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            legacy = base / ".agents" / "skills" / "x-unfollow"
            backup = base / ".agents" / "skills-disabled"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text(
                "---\nname: x-unfollow\ndescription: legacy fixture\n---\n",
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "HOME": str(base),
                "X_PLUGIN_MIGRATION_STAMP": "fixture",
            }
            dry = subprocess.run(["bash", str(MIGRATE), "--dry-run"], env=env, capture_output=True, text=True)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertTrue(legacy.is_dir())
            moved = subprocess.run(["bash", str(MIGRATE)], env=env, capture_output=True, text=True)
            self.assertEqual(moved.returncode, 0, moved.stderr)
            target = backup / "x-unfollow-legacy-fixture"
            self.assertFalse(legacy.exists())
            self.assertTrue((target / "SKILL.md").is_file())

    def test_legacy_migration_rejects_custom_and_overlapping_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "custom" / "x-unfollow"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("---\nname: x-unfollow\n---\n", encoding="utf-8")
            custom = {
                **os.environ,
                "HOME": str(base / "home"),
                "X_PLUGIN_LEGACY_SKILL_DIR": str(source),
                "X_PLUGIN_LEGACY_BACKUP_ROOT": str(base / "backup"),
                "X_PLUGIN_MIGRATION_STAMP": "fixture",
            }
            refused = subprocess.run(["bash", str(MIGRATE)], env=custom, capture_output=True, text=True)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("production migration only accepts", refused.stderr)
            self.assertTrue(source.is_dir())

            overlap = {
                **custom,
                "X_PLUGIN_MIGRATION_TEST_MODE": "1",
                "X_PLUGIN_LEGACY_BACKUP_ROOT": str(source / "backup"),
            }
            refused = subprocess.run(["bash", str(MIGRATE)], env=overlap, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("overlap", refused.stderr)
            self.assertFalse((source / "backup").exists())


if __name__ == "__main__":
    unittest.main()
