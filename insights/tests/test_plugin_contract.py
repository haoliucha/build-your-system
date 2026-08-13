import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginContractTests(unittest.TestCase):
    def test_codex_only_manifest_and_skill(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "insights")
        self.assertEqual(manifest["version"], "0.3.0")
        self.assertFalse((ROOT / ".claude-plugin").exists())
        skill = (ROOT / "skills" / "insights" / "SKILL.md").read_text(encoding="utf-8")
        for term in (
            "确定性会话统计",
            "native-facet-v1",
            "project_areas",
            "interaction_style",
            "suggestions",
            "At-a-Glance",
            "report.html",
            "$insights",
            "codex exec",
            "SQLite",
            "6–12",
            "--max-new-sessions 200",
            "脱敏分析材料快照",
        ):
            self.assertIn(term, skill)
        for incorrect_native_claim in ("→ Repeat", "五项质检", "facet_v2", "privacy-first"):
            self.assertNotIn(incorrect_native_claim, skill)
        agent = (ROOT / "skills" / "insights" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", agent)
        self.assertNotIn("隐私优先", agent)
        for obsolete in ("next_jobs", "read_job", "submit_jobs", "stty -echo", "RUN_TTL_SECONDS"):
            self.assertNotIn(obsolete, skill)
        for script in ("insights.py", "runner.py", "native_meta.py", "native_analysis.py", "native_report.py"):
            self.assertTrue((ROOT / "skills" / "insights" / "scripts" / script).is_file())
        protocol = (ROOT / "skills" / "insights" / "references" / "protocol-contract.md").read_text(encoding="utf-8")
        self.assertIn("恢复直接读取该快照", protocol)
        self.assertNotIn("恢复必须重新扫描并核对", protocol)


if __name__ == "__main__":
    unittest.main()
