import re
import unittest

from helpers import BID_ROOT


COMMAND_TO_SKILL = {
    "init": "bid-init",
    "meeting": "bid-meeting",
    "sync": "bid-sync",
    "handoff": "bid-handoff",
    "review": "bid-review",
    "status": "bid-status",
}

EXPECTED_FRONTMATTER = {
    "init": """---
description: "一键投标项目立项脚手架:判定线索状态(新线索/成单/重组)→ 客户向·内部双层目录 + build 生成器骨架 + meeting 编年 → P0 问题清单(数据授权第 0 步)→ memory 索引初始化;重组既有目录前先审计脚本路径耦合。详见 skill bid-playbook"
argument-hint: "[项目名]"
---""",
    "meeting": """---
description: "一键会议流程:会后归档纪要打标+提取口径变更落 memory(默认);--prep 会前生成准备包五件套(讲解脚本/数字速查卡/模拟Q&A/『别说』红线/口径桥)。详见 skill bid-playbook 与 presales-tactics"
argument-hint: "[会议日期或纪要文件] [--prep 会前模式]"
---""",
    "sync": """---
description: "一键口径级联同步:lsof 写句柄检查 → 手改回捕 → 跑生成器 → 内容抽验 → 全库 grep 残留 → memory 核对 → 分组提交预览。详见 skill single-source-sync"
argument-hint: "[口径变更描述]"
---""",
    "handoff": """---
description: "一键按接收工具定制原型交接包:先吃透工具输入模型定包形态(prompt+知识库 vs 令牌+组件)→ 组装逐字合规文案 + 全量真实 copy + 实测取样视觉参考 + 宿主双层令牌 → P0/P1/P2 分批放行说明 → 交付前审校与最劣环境核验;写盘/commit 一律只预览。详见 skill prototype-handoff"
argument-hint: "[接收工具名] [原型范围]"
---""",
    "review": """---
description: "一键多透镜收口审校:按交付物类型装配透镜(文档=一致性/脱敏/去AI味/溯源,财务表=算术配平,视觉=逐页目检)并行扇出 → 汇总裁决 → 修复复验,commit 只预览。详见 skill adversarial-review"
argument-hint: "[交付物路径...]"
---""",
    "status": """---
description: "一键口径与红线速查:读 memory+生成器源,出锁定口径表(对客/内部分层)+『勿口播』红线清单+遗留待办三清单(待实测/待确认/待核)+关键数字漂移抽查,全程只读。详见 skill bid-playbook"
argument-hint: ""
---""",
}


class ClaudeCommandWrapperTests(unittest.TestCase):
    def command_parts(self, command):
        path = BID_ROOT / "commands" / f"{command}.md"
        text = path.read_text(encoding="utf-8")
        match = re.fullmatch(r"(?s)(---\n.*?\n---)\n\n(.*)", text)
        self.assertIsNotNone(match, f"invalid command document structure: {path}")
        return match.group(1), match.group(2)

    def test_frontmatter_is_preserved_byte_for_byte(self):
        for command in COMMAND_TO_SKILL:
            with self.subTest(command=command):
                actual, _ = self.command_parts(command)
                self.assertEqual(actual, EXPECTED_FRONTMATTER[command])

    def test_each_command_is_the_exact_thin_adapter(self):
        for command, skill in COMMAND_TO_SKILL.items():
            expected = (
                f"# /bid:{command}\n\n"
                "参数：`$ARGUMENTS`\n\n"
                f"加载本插件的 `{skill}` skill，把 `$ARGUMENTS` 作为本次输入透传，"
                "并完整执行该 skill。命令文件只负责 Claude Code 入口；流程、护栏和停止条件"
                "以 skill 为唯一真源。\n"
            )
            with self.subTest(command=command):
                _, body = self.command_parts(command)
                self.assertEqual(body, expected)

    def test_each_command_passes_arguments_through_and_executes_its_skill_fully(self):
        for command, skill in COMMAND_TO_SKILL.items():
            with self.subTest(command=command):
                _, body = self.command_parts(command)
                self.assertIn("$ARGUMENTS", body)
                self.assertIn(f"`{skill}` skill", body)
                self.assertIn("作为本次输入透传", body)
                self.assertIn("完整执行该 skill", body)

    def test_command_bodies_do_not_duplicate_workflow_sections(self):
        forbidden_headings = ("## 执行流程", "## 固定执行序", "## 硬护栏")
        for command in COMMAND_TO_SKILL:
            with self.subTest(command=command):
                _, body = self.command_parts(command)
                for heading in forbidden_headings:
                    self.assertNotIn(heading, body)
                nonblank_lines = [line for line in body.splitlines() if line.strip()]
                self.assertLess(len(nonblank_lines), 20)


class SharedWorkflowRouteTests(unittest.TestCase):
    def test_first_route_in_each_shared_document_is_dual_host(self):
        markdown_files = sorted((BID_ROOT / "skills").glob("**/*.md"))
        for path in markdown_files:
            lines = path.read_text(encoding="utf-8").splitlines()
            for command, skill in COMMAND_TO_SKILL.items():
                claude_route = f"/bid:{command}"
                codex_route = f"$bid:{skill}"
                first_route_line = next(
                    (line for line in lines if claude_route in line), None
                )
                if first_route_line is None:
                    continue
                with self.subTest(
                    path=path.relative_to(BID_ROOT), command=command
                ):
                    self.assertIn(codex_route, first_route_line)

    def test_codex_is_never_sent_to_a_claude_slash_command(self):
        codex_slash_route = re.compile(r"Codex\s*[：:]?\s*`?/bid:")
        for path in sorted((BID_ROOT / "skills").glob("**/*.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(BID_ROOT)):
                self.assertIsNone(codex_slash_route.search(text))


if __name__ == "__main__":
    unittest.main()
