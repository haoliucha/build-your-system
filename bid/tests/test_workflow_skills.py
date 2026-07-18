import unittest

from helpers import BID_ROOT, frontmatter


SKILLS_ROOT = BID_ROOT / "skills"


def assert_workflow(name, required, forbidden):
    path = SKILLS_ROOT / name / "SKILL.md"
    assert path.is_file(), f"missing shared workflow skill: {path}"

    data, _ = frontmatter(path)
    assert set(data) == {"name", "description"}, data
    assert data["name"] == name, data
    assert data["description"].startswith("Use when "), data

    text = path.read_text(encoding="utf-8")
    for term in required:
        assert term in text, f"{name} missing required term: {term}"
    for term in forbidden:
        assert term not in text, f"{name} contains forbidden term: {term}"


class WorkflowSkillContractTests(unittest.TestCase):
    def test_bid_init_contract(self):
        host_adaptation_link = "../bid-playbook/references/host-adaptation.md"
        assert_workflow(
            "bid-init",
            required=(
                "新线索",
                "全新成单项目",
                "既有目录要重组",
                "存量数据/案例授权",
                "申报主体",
                "真实规模基数",
                "上线时间窗",
                ".claude/memory/",
                "绝不自动 git commit",
                "绝不覆盖已存在文件",
                "## 宿主入口",
                "/bid:init",
                "$bid:bid-init",
                "自然语言",
                host_adaptation_link,
            ),
            forbidden=("$ARGUMENTS", "${CLAUDE_PLUGIN_ROOT}"),
        )
        skill_path = SKILLS_ROOT / "bid-init" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        self.assertEqual(text.count(host_adaptation_link), 1)
        self.assertTrue((skill_path.parent / host_adaptation_link).is_file())


if __name__ == "__main__":
    unittest.main()
