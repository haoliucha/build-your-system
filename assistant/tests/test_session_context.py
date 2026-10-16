import importlib.util
import os
from datetime import datetime
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path


def load_context():
    path = Path(__file__).resolve().parents[1] / "scripts/session-context.py"
    spec = importlib.util.spec_from_file_location("session_context", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SessionContextTests(unittest.TestCase):
    def test_full_profile_legacy_preferences_and_top_five_digest(self):
        module = load_context()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            (vault / "60-Memory").mkdir(parents=True)
            profile = ["---", "created: 2025-12-06", "updated: 2026-09-03", "---"] + [f"画像行 {i}" for i in range(79)] + ["## AI 助手注意事项"]
            (vault / "60-Memory/profile.md").write_text("\n".join(profile) + "\n", encoding="utf-8")
            (vault / "60-Memory/preferences.md").write_text("# 偏好\n\n- 起床时间: 8:00\n- 结束工作: 20:00 - 22:00\n", encoding="utf-8")
            digest = []
            for i in range(7):
                digest.append(f"### P-{i:03d} 模式 {i}\nstatus: active\nlast_confirmed: 2026-09-{i + 1:02d}\n")
            (vault / "60-Memory/patterns-digest.md").write_text("\n".join(digest), encoding="utf-8")
            rendered = module.render(vault)
            self.assertIn("AI 助手注意事项", rendered)
            self.assertIn("收工: 20:00 - 22:00", rendered)
            self.assertEqual(len([line for line in rendered.splitlines() if line.startswith("### P-")]), 5)
            self.assertLessEqual(len(rendered.splitlines()), 90)


    def test_shared_vault_policy_is_identical_without_host_files_or_private_memory(self):
        module = load_context()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir) / 'vault'
            (vault / '60-Memory').mkdir(parents=True)
            text = '# 偏好\n\n## 工作流边界\n\n- media 已停用，不执行选题或发布动作。\n- 手动入口不依赖 hook。\n\n## 自定义保留章节\n- 原样保留。\n'
            pref = vault / '60-Memory/preferences.md'
            pref.write_text(text)
            # Neither AGENTS/CLAUDE files nor either host's private memory exists.
            outputs = []
            for host in ['claude', 'codex']:
                environment = {'HOME': str(Path(tmpdir) / host), 'ASSISTANT_HOST': host}
                if host == 'claude':
                    environment['CLAUDECODE'] = '1'
                with patch.dict(os.environ, environment, clear=True), patch.object(module, '_nudge', return_value=''), patch.object(module, 'datetime') as clock:
                    clock.now.return_value = datetime(2026, 9, 8, 14, tzinfo=module.GMT8)
                    outputs.append(module.render(vault))
            self.assertEqual(outputs[0], outputs[1])
            self.assertTrue(outputs[0].startswith('## 工作流边界'))
            self.assertIn('media 已停用', outputs[0])
            self.assertIn('手动入口不依赖 hook', outputs[0])
            self.assertNotIn('自定义保留章节', outputs[0])
            self.assertEqual(pref.read_text(), text)
            self.assertFalse((vault / 'AGENTS.override.md').exists())
            self.assertFalse((vault / 'CLAUDE.md').exists())

    def test_missing_shared_policy_does_not_invent_host_configuration(self):
        module = load_context()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            with patch.object(module, '_nudge', return_value=''):
                rendered = module.render(vault)
            self.assertNotIn('工作流边界', rendered)
            self.assertNotIn('media', rendered)
            self.assertEqual(list(vault.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
