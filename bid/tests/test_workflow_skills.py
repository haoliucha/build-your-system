import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import BID_ROOT, frontmatter


SKILLS_ROOT = BID_ROOT / "skills"
BEHAVIOR_LOG = BID_ROOT / "tests/skill-behavior/tdd-log.md"
HOST_ADAPTATION_LINK = "../bid-playbook/references/host-adaptation.md"


def assert_workflow(name, required, forbidden):
    path = SKILLS_ROOT / name / "SKILL.md"
    if not path.is_file():
        raise AssertionError(f"missing shared workflow skill: {path}")

    data, _ = frontmatter(path)
    if set(data) != {"name", "description"}:
        raise AssertionError(f"invalid frontmatter keys for {name}: {data}")
    if data.get("name") != name:
        raise AssertionError(f"invalid workflow name for {name}: {data}")
    description = data.get("description")
    if not isinstance(description, str) or not description.startswith("Use when "):
        raise AssertionError(f"invalid workflow description for {name}: {data}")

    text = path.read_text(encoding="utf-8")
    host_sections = list(
        re.finditer(r"(?ms)^## 宿主入口[ \t]*\n(.*?)(?=^## |\Z)", text)
    )
    if len(host_sections) != 1:
        raise AssertionError(f"{name} must contain exactly one real 宿主入口 section")
    host_body = host_sections[0].group(1)

    command = name.removeprefix("bid-")
    host_entries = (
        ("Claude", f"/bid:{command}"),
        ("Codex", f"$bid:{name}"),
    )
    for host, invocation in host_entries:
        pattern = rf"(?m)^- {host}：`{re.escape(invocation)}(?: [^`\n]+)?`[ \t]*$"
        if re.search(pattern, host_body) is None:
            raise AssertionError(
                f"{name} 宿主入口 missing correct {host} entry: {invocation}"
            )

    if text.count(HOST_ADAPTATION_LINK) != 1:
        raise AssertionError(
            f"{name} must contain one central host-adaptation reference"
        )
    if HOST_ADAPTATION_LINK not in host_body:
        raise AssertionError(f"{name} host-adaptation reference must be in 宿主入口")
    if not (path.parent / HOST_ADAPTATION_LINK).is_file():
        raise AssertionError(f"{name} host-adaptation reference does not resolve")

    for term in required:
        if term not in text:
            raise AssertionError(f"{name} missing required term: {term}")
    for term in forbidden:
        if term in text:
            raise AssertionError(f"{name} contains forbidden term: {term}")


class WorkflowSkillContractTests(unittest.TestCase):
    def test_bid_init_contract(self):
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
                HOST_ADAPTATION_LINK,
                "仅适用于全新成单项目或经确认转正/重组后的正式项目",
                "新线索分支不初始化 `.claude/memory/`",
                "memory 索引位置（仅正式项目）",
            ),
            forbidden=("$ARGUMENTS", "${CLAUDE_PLUGIN_ROOT}"),
        )

    def test_bid_init_downstream_routes_are_dual_host(self):
        text = (SKILLS_ROOT / "bid-init/SKILL.md").read_text(encoding="utf-8")
        for claude_route, codex_route in (
            ("/bid:meeting", "$bid:bid-meeting"),
            ("/bid:sync", "$bid:bid-sync"),
        ):
            with self.subTest(route=claude_route):
                route_lines = [
                    line
                    for line in text.splitlines()
                    if claude_route in line or codex_route in line
                ]
                self.assertTrue(route_lines)
                for line in route_lines:
                    self.assertIn(claude_route, line)
                    self.assertIn(codex_route, line)

    def test_bid_init_behavior_log_is_independently_reproducible(self):
        text = BEHAVIOR_LOG.read_text(encoding="utf-8")
        for term in (
            "2026-07-18",
            "/root/task4_bid_init/bid_init_baseline_eval",
            "/root/task4_bid_init/bid_init_skill_eval",
            'fork_turns: "none"',
            "Concrete model build: inherited and not exposed",
            "Apply these skill instructions exactly:",
            "Skill snapshot SHA-256:",
            "complete skill snapshot appended verbatim",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)


class WorkflowAssertionMutationTests(unittest.TestCase):
    def write_fixture(self, root, body, frontmatter_text=None):
        skills_root = root / "skills"
        skill_dir = skills_root / "bid-init"
        skill_dir.mkdir(parents=True)
        adaptation = skills_root / "bid-playbook/references/host-adaptation.md"
        adaptation.parent.mkdir(parents=True)
        adaptation.write_text("# host adaptation\n", encoding="utf-8")
        if frontmatter_text is None:
            frontmatter_text = (
                "---\n"
                "name: bid-init\n"
                "description: Use when testing bid initialization\n"
                "---\n"
            )
        (skill_dir / "SKILL.md").write_text(
            frontmatter_text + "\n" + body,
            encoding="utf-8",
        )
        return skills_root

    def valid_host_section(self):
        return (
            "# fixture\n\n"
            "## 宿主入口\n\n"
            "- Claude：`/bid:init`\n"
            "- Codex：`$bid:bid-init`\n"
            "- 自然语言：初始化投标项目\n"
            f"- [host-adaptation]({HOST_ADAPTATION_LINK})\n"
        )

    def test_well_formed_fixture_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(Path(tmp), self.valid_host_section())
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                assert_workflow("bid-init", required=(), forbidden=())

    def test_host_entries_outside_real_section_are_rejected(self):
        body = self.valid_host_section().replace("## 宿主入口", "## 其他章节")
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(Path(tmp), body)
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                with self.assertRaises(AssertionError):
                    assert_workflow("bid-init", required=(), forbidden=())

    def test_wrong_codex_host_entry_is_rejected(self):
        body = self.valid_host_section().replace("$bid:bid-init", "$bid:init")
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(Path(tmp), body)
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                with self.assertRaises(AssertionError):
                    assert_workflow("bid-init", required=(), forbidden=())

    def test_duplicate_host_adaptation_reference_is_rejected(self):
        body = self.valid_host_section() + f"\n再次见 {HOST_ADAPTATION_LINK}\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(Path(tmp), body)
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                with self.assertRaises(AssertionError):
                    assert_workflow("bid-init", required=(), forbidden=())

    def test_extra_frontmatter_key_is_rejected(self):
        frontmatter_text = (
            "---\n"
            "name: bid-init\n"
            "description: Use when testing bid initialization\n"
            "extra: forbidden\n"
            "---\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(
                Path(tmp),
                self.valid_host_section(),
                frontmatter_text,
            )
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                with self.assertRaises(AssertionError):
                    assert_workflow("bid-init", required=(), forbidden=())

    def test_missing_required_term_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(Path(tmp), self.valid_host_section())
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                with self.assertRaises(AssertionError):
                    assert_workflow(
                        "bid-init",
                        required=("missing contract term",),
                        forbidden=(),
                    )

    def test_forbidden_term_is_rejected(self):
        body = self.valid_host_section() + "\nforbidden-token\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_fixture(Path(tmp), body)
            with mock.patch(__name__ + ".SKILLS_ROOT", root):
                with self.assertRaises(AssertionError):
                    assert_workflow(
                        "bid-init",
                        required=(),
                        forbidden=("forbidden-token",),
                    )


if __name__ == "__main__":
    unittest.main()
