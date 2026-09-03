import importlib.util
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


if __name__ == "__main__":
    unittest.main()
