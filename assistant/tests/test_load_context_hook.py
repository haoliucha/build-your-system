import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks/scripts/load-context.sh"


def run_hook(project_dir: Path) -> str:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    result = subprocess.run(
        ["bash", str(HOOK)], cwd=project_dir, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class LoadContextHookScopeTests(unittest.TestCase):
    def test_silent_in_project_without_assistant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".claude").mkdir()
            (project / ".claude/settings.json").write_text(
                '{"enabledPlugins": {"x@build-your-system": true}}', encoding="utf-8")
            self.assertEqual(run_hook(project), "")

    def test_setup_prompt_when_project_enables_assistant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".claude").mkdir()
            (project / ".claude/settings.local.json").write_text(
                '{"enabledPlugins": {"assistant@build-your-system": true}}', encoding="utf-8")
            self.assertIn("未初始化", run_hook(project))

    def test_para_layout_without_install_is_not_a_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            for name in ("50-GTD", "60-Memory"):
                (project / name).mkdir()
            self.assertEqual(run_hook(project), "")

    def test_codex_project_config_counts_as_install(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".codex").mkdir()
            (project / ".codex/config.toml").write_text(
                '[plugins."assistant@build-your-system"]\nenabled = true\n', encoding="utf-8")
            self.assertIn("未初始化", run_hook(project))

    def test_codex_project_config_disabled_is_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".codex").mkdir()
            (project / ".codex/config.toml").write_text(
                '[plugins."assistant@build-your-system"]\nenabled = false\n', encoding="utf-8")
            self.assertEqual(run_hook(project), "")


if __name__ == "__main__":
    unittest.main()
