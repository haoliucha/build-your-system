import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path


def load_health():
    path = Path(__file__).resolve().parents[1] / "scripts/vault-health.py"
    spec = importlib.util.spec_from_file_location("vault_health", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VaultHealthTests(unittest.TestCase):
    def test_health_counts_capture_mit_review_tasks_and_missing_files(self):
        module = load_health()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            (vault / "00-Inbox").mkdir(parents=True)
            (vault / "50-GTD").mkdir()
            (vault / "00-Inbox/capture.md").write_text(
                "### 05-11 09:00\nold\n\n### 05-12 09:00\nmid\n\n### 05-14 09:00\nnew\n", encoding="utf-8"
            )
            (vault / "50-GTD/active.md").write_text(
                "## 今日重点 (MIT) - 05-14\n\n- [ ] 旧 MIT\n\n---\n\n- [ ] 逾期任务 📅 2026-05-01\n", encoding="utf-8"
            )
            (vault / "00-Inbox/2026-05-11.md").write_text("# 日记\n\n## 复盘\n完成了一些事\n", encoding="utf-8")
            result = module.health(vault, date(2026, 9, 3))
            self.assertEqual(result["inbox"]["undispatched"], 3)
            self.assertEqual(result["inbox"]["oldest"], "2026-05-11")
            self.assertEqual(result["mit"]["header_date"], "2026-05-14")
            self.assertEqual(result["mit"]["open"], 1)
            self.assertEqual(result["review"]["last_date"], "2026-05-11")
            self.assertEqual(result["tasks"]["overdue"], 1)
            self.assertIn("50-GTD/done.md", result["files"]["missing"])
            self.assertTrue(any("MIT" in nudge for nudge in result["nudges"]))


if __name__ == "__main__":
    unittest.main()
