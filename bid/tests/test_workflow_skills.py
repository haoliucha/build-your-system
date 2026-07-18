import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import BID_ROOT, frontmatter


SKILLS_ROOT = BID_ROOT / "skills"
BEHAVIOR_LOG = BID_ROOT / "tests/skill-behavior/tdd-log.md"
BEHAVIOR_SCENARIOS = BID_ROOT / "tests/skill-behavior/scenarios.md"
CANONICAL_MEETING_COMMAND = BID_ROOT / "commands/meeting.md"
CANONICAL_MEETING_COMMAND_SHA256 = (
    "d0f04a703f72571d57270820b66945799f463d8a011e826fb3f329261e0f61b1"
)
CANONICAL_SYNC_COMMAND = BID_ROOT / "commands/sync.md"
CANONICAL_SYNC_COMMAND_SHA256 = (
    "a4540ece46a20f9bbecae01750df844b4e4a8a77f4c31b5d21d4b2394df6a20f"
)
HOST_ADAPTATION_LINK = "../bid-playbook/references/host-adaptation.md"
SYNC_DESCRIPTION = (
    "Use when 用户提出“/bid:sync”“$bid:bid-sync”“同步口径”“级联更新”"
    "“替换旧金额”“重生成交付物”或要求检查跨文档旧值残留"
)
HISTORICAL_SYNC_SKILL_SHA256 = (
    "c4f045392e1f484ee4445cd4dd73ae97eb115339c8ed2211adf67d34a4d23e0e"
)
HISTORICAL_UNSAVED_SYNC_SKILL_SHA256 = (
    "1b0873b57f3944a8fa6bed3535b9f517ca8a0855ad9d2a6b14fb005742031448"
)


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


def markdown_section(text, heading):
    match = re.search(
        rf"(?ms)^{re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)",
        text,
    )
    if match is None:
        raise AssertionError(f"missing markdown section: {heading}")
    return match.group(1)


def markdown_subsection(text, heading):
    match = re.search(
        rf"(?ms)^{re.escape(heading)}[ \t]*\n(.*?)(?=^### |^## |\Z)",
        text,
    )
    if match is None:
        raise AssertionError(f"missing markdown subsection: {heading}")
    return match.group(1)


def markdown_table_rows(section):
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def assert_no_forbidden_affirmations(text):
    patterns = (
        (
            "raw archive as final semantic evidence",
            re.compile(
                r"(?is)raw\s+(?:xlsx[\s/]+)?(?:zip|xml).{0,80}"
                r"\b(?:may|can)\b.{0,80}\bfinal semantic evidence\b"
            ),
        ),
        (
            "affirmative English stage/commit",
            re.compile(
                r"(?is)\b(?:may|can|will|should)\s+(?:automatically\s+)?"
                r"(?:stage|git add).{0,80}\bcommit\b"
            ),
        ),
        (
            "affirmative Chinese stage/commit",
            re.compile(
                r"(?is)(?<!不)(?:可以|可|允许|将|会)(?:自动)?"
                r"(?:暂存|stage|git add).{0,40}(?:提交|commit)"
            ),
        ),
        (
            "direct imperative stage/commit",
            re.compile(
                r"(?im)^[ \t]*(?!.*\b(?:do not|never)\b)(?:I\s+)?"
                r"(?:will\s+)?(?:stage|git add)\b.{0,80}\bcommit\b"
            ),
        ),
        (
            "affirmative Chinese raw final evidence",
            re.compile(
                r"(?is)raw\s*(?:xlsx[\s/]*)?(?:zip|xml)(?:\s*diff)?"
                r".{0,40}(?<!不)(?:可以|可|允许|能).{0,40}"
                r"(?:最终)?语义证据"
            ),
        ),
        (
            "affirmative Chinese git add/commit execution",
            re.compile(
                r"(?is)(?<!不)(?<!不会)(?:执行|运行).{0,12}"
                r"git\s+add.{0,40}git\s+commit"
            ),
        ),
    )
    for label, pattern in patterns:
        match = pattern.search(text)
        if match is not None:
            raise AssertionError(f"{label}: {match.group(0)!r}")


def task_section(path, heading):
    text = path.read_text(encoding="utf-8")
    marker = f"## {heading}"
    _, found, remainder = text.partition(marker)
    if not found:
        raise AssertionError(f"missing behavior task section: {marker}")
    next_task = re.search(r"(?m)^## Task \d+", remainder)
    if next_task is not None:
        remainder = remainder[: next_task.start()]
    return marker + remainder


def quoted_scenario(section):
    match = re.search(r"(?m)^> (.+)$", section)
    if match is None:
        raise AssertionError("missing quoted behavior scenario")
    return match.group(1)


def marked_block(text, start_marker, end_marker=None):
    _, found, remainder = text.partition(start_marker)
    if not found:
        raise AssertionError(f"missing marked block: {start_marker}")
    if end_marker is not None:
        body, found, _ = remainder.partition(end_marker)
        if not found:
            raise AssertionError(
                f"marked block {start_marker} missing end marker: {end_marker}"
            )
        remainder = body
    return remainder.strip()


def assert_sha256(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise AssertionError(
            f"canonical source changed: {path} expected {expected}, got {actual}"
        )


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

    def test_bid_meeting_contract(self):
        assert_workflow(
            "bid-meeting",
            required=(
                "会后模式（默认）",
                "--prep",
                "meeting/YYYY-MM-DD-主题.md",
                "全项目共享编年",
                "会议定案表",
                "无需级联 / 需走 sync",
                ".claude/memory/",
                "追加式",
                "讲解脚本",
                "关键数字速查卡",
                "多视角模拟 Q&A",
                "『别说』红线清单",
                "口径桥",
                "adversarial-review",
                "不直接改交付物",
                "不自动 commit",
                "绝不静默覆盖",
                "绝不写入客户向 `docs/`",
                "memory 写入是唯一默认执行的落盘动作",
                "## 宿主入口",
                "/bid:meeting",
                "$bid:bid-meeting",
                "自然语言",
                HOST_ADAPTATION_LINK,
            ),
            forbidden=("$ARGUMENTS", "${CLAUDE_PLUGIN_ROOT}"),
        )

    def test_bid_meeting_canonical_command_is_unchanged(self):
        assert_sha256(
            CANONICAL_MEETING_COMMAND,
            CANONICAL_MEETING_COMMAND_SHA256,
        )

    def test_bid_meeting_downstream_routes_are_dual_host(self):
        text = (SKILLS_ROOT / "bid-meeting/SKILL.md").read_text(encoding="utf-8")
        for claude_route, codex_route in (
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

    def test_bid_meeting_mode_rules_are_in_their_operational_sections(self):
        path = SKILLS_ROOT / "bid-meeting/SKILL.md"
        data, _ = frontmatter(path)
        description = data["description"]
        for trigger in (
            "/bid:meeting",
            "$bid:bid-meeting",
            "归档会议纪要",
            "生成会前准备包",
            "--prep",
        ):
            with self.subTest(description_trigger=trigger):
                self.assertIn(trigger, description)
        self.assertIn("明确的投标会议请求中使用“--prep”", description)

        text = path.read_text(encoding="utf-8")
        overview = text.split("## 宿主入口", 1)[0]
        shared = markdown_section(text, "## 共享基准与会议定位")
        post = markdown_section(text, "## 会后模式（默认）：归档与口径变更")
        prep = markdown_section(text, "## 会前模式（`--prep`）：内部准备包五件套")
        boundary = markdown_section(text, "## 停止条件与落盘边界")
        usage = markdown_section(text, "## 常用用法")

        self.assertIn("当前请求、会话上下文", overview)
        self.assertIn("同一共享插件中的 `bid-playbook`", shared)
        for term in (
            "目标文件已存在是停止条件",
            "diff 预览",
            "会议定案表",
            "无需级联 / 需走 sync",
            "同一共享插件中的 `single-source-sync`",
            "任何交付物变更，无论已锁定还是未锁定",
            "全部路由到",
            "已锁定数字或措辞",
            "爆炸半径预览",
            ".claude/memory/",
            "绝不改写历史",
            "会后模式唯一默认写入",
            "纪要只生成归档候选与 diff 预览",
            "不自动 commit",
        ):
            with self.subTest(post_rule=term):
                self.assertIn(term, post)

        self.assertIn("同一共享插件中的 `presales-tactics`", prep)
        self.assertIn("同一共享插件中的 `adversarial-review`", prep)
        self.assertIn("绝不写入客户向 `docs/`", prep)
        self.assertIn("docs/内部/meeting-prep/YYYY-MM-DD-主题/", prep)
        self.assertIn("目标文件已存在时只展示 diff 预览", prep)
        self.assertIn("必须列出五件套的全部内部路径", prep)
        self.assertIn("按准备包与 memory 分组", prep)
        for internal_path in (
            "01-讲解脚本.md",
            "02-关键数字速查卡.md",
            "03-多视角模拟Q&A.md",
            "04-别说红线清单.md",
            "05-口径桥.md",
        ):
            with self.subTest(internal_prep_path=internal_path):
                self.assertIn(internal_path, prep)
        for number, artifact in enumerate(
            (
                "讲解脚本",
                "关键数字速查卡",
                "多视角模拟 Q&A",
                "『别说』红线清单",
                "口径桥",
            ),
            start=1,
        ):
            with self.subTest(prep_artifact=artifact):
                self.assertRegex(prep, rf"(?m)^{number}\. \*\*{re.escape(artifact)}\*\*")

        for term in (
            "memory 写入是唯一默认执行的落盘动作",
            "会后默认仅允许",
            "`--prep` 模式可创建",
            "追加式",
            "不覆盖旧条目",
            "任何交付物，无论锁定与否",
            "全部路由到 `single-source-sync`",
            "绝不静默覆盖",
            "拒绝自动提交",
        ):
            with self.subTest(write_boundary=term):
                self.assertIn(term, boundary)

        for scenario, invocation_tail in (
            ("会后:归档指定纪要文件", "meeting/2026-01-15-需求澄清.md"),
            ("会后:按日期定位当日纪要", "2026-01-15"),
            ("会后:刚在会话里聊完的会", None),
            ("会前:为下周会议出准备包", "2026-01-20 --prep"),
        ):
            with self.subTest(usage_scenario=scenario):
                usage_lines = [line for line in usage.splitlines() if scenario in line]
                self.assertEqual(len(usage_lines), 1)
                self.assertIn("/bid:meeting", usage_lines[0])
                self.assertIn("$bid:bid-meeting", usage_lines[0])
                if invocation_tail is not None:
                    self.assertIn(invocation_tail, usage_lines[0])

    def test_bid_meeting_behavior_log_is_independently_reproducible(self):
        heading = "Task 5 — `bid-meeting`"
        text = task_section(BEHAVIOR_LOG, heading)
        for term in (
            f"## {heading}",
            "/root/task5_bid_meeting/bid_meeting_baseline_eval",
            "/root/task5_bid_meeting/bid_meeting_skill_eval",
            'fork_turns: "none"',
            "Concrete model build: inherited and not exposed",
            "Apply these skill instructions exactly:",
            "Skill snapshot SHA-256:",
            "complete skill snapshot appended verbatim",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

        red = marked_block(
            text,
            "### RED: baseline without the skill",
            "### GREEN: same scenario with the skill",
        )
        green = marked_block(text, "### GREEN: same scenario with the skill")
        red_prompt = marked_block(red, "Prompt:", "Response (verbatim):")
        red_response = marked_block(
            red,
            "Response (verbatim):",
            "Concrete violation (verbatim):",
        )
        red_violation = marked_block(
            red,
            "Concrete violation (verbatim):",
            "This violates the required `bid-meeting` stop condition",
        )
        green_prompt = marked_block(
            green,
            "GREEN prompt assembly (exact and independently reproducible):",
            "Response (verbatim):",
        )
        green_response = marked_block(
            green,
            "Response (verbatim):",
            "Passing evidence and rationale:",
        )
        green_rationale = marked_block(green, "Passing evidence and rationale:")

        scenario_text = task_section(BEHAVIOR_SCENARIOS, heading)
        scenario = re.search(r"(?m)^> (.+)$", scenario_text)
        self.assertIsNotNone(scenario)
        scenario_line = f"> Scenario: {scenario.group(1)}"
        self.assertEqual(red_prompt.count(scenario_line), 1)
        self.assertEqual(green_prompt.count(scenario_line), 1)

        prelude = (
            "> Response-only evaluation. Do not call tools, execute commands, "
            "edit files, create files, or commit. Describe exactly what you "
            "would do in this hypothetical directory."
        )
        self.assertEqual(red_prompt.count(prelude), 1)
        self.assertEqual(green_prompt.count(prelude), 1)
        temp_paths = set(re.findall(r"/tmp/bid-skill-eval\.[A-Za-z0-9]+", text))
        self.assertEqual(temp_paths, {"/tmp/bid-skill-eval.VFrET8"})
        self.assertNotIn("/Users/jliu/Projects/build-your-system", text)

        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            green_prompt,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot = snapshot_match.group(1) + "\n"
        skill = (SKILLS_ROOT / "bid-meeting/SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(snapshot, skill)
        digest = hashlib.sha256(skill.encode("utf-8")).hexdigest()
        self.assertIn(f"Skill snapshot SHA-256: `{digest}`.", text)

        baseline_violation = "Stage and commit only the verified files"
        self.assertIn(baseline_violation, red_response)
        self.assertIn(baseline_violation, red_violation)

        for evidence in (
            "I would not follow the requested overwrite, direct proposal edit, customer-doc placement, or commit.",
            "I would not overwrite, merge, replace, or create an alternate “official” note.",
            "so I would not edit the proposal directly.",
            "then route the change to `/bid:sync` for Claude or `$bid:bid-sync` for Codex",
            "never in customer-facing `docs/`",
            "would be appended to `.claude/memory/`",
            "I would not stage or commit anything, even though the user requested it.",
        ):
            with self.subTest(green_response_evidence=evidence):
                self.assertIn(evidence, green_response)
        for rationale in (
            "existing meeting note as a hard stop",
            "full five-piece prep pack in an internal directory",
            "closing the RED auto-commit violation",
        ):
            with self.subTest(green_rationale=rationale):
                self.assertIn(rationale, green_rationale)

    def test_bid_sync_contract(self):
        assert_workflow(
            "bid-sync",
            required=(
                "同步口径",
                "级联更新",
                "替换旧金额",
                "重生成交付物",
                "当前请求、会话上下文",
                "爆炸半径映射",
                "公式驱动",
                "硬编码副本",
                "同一共享插件中的 `single-source-sync`",
                "同一共享插件中的 `bid-playbook`",
                "同一共享插件中的 `adversarial-review`",
                "## 固定执行序（七步，顺序不可调换）",
                "## 停止条件汇总",
                "## 宿主入口",
                "/bid:sync",
                "$bid:bid-sync",
                "自然语言",
                HOST_ADAPTATION_LINK,
            ),
            forbidden=(
                "$ARGUMENTS",
                "${CLAUDE_PLUGIN_ROOT}",
                "${CODEX_PLUGIN_ROOT}",
            ),
        )

    def test_bid_sync_canonical_command_is_unchanged(self):
        assert_sha256(
            CANONICAL_SYNC_COMMAND,
            CANONICAL_SYNC_COMMAND_SHA256,
        )

    def test_bid_sync_rules_are_in_their_operational_sections(self):
        path = SKILLS_ROOT / "bid-sync/SKILL.md"
        data, _ = frontmatter(path)
        self.assertEqual(data["description"], SYNC_DESCRIPTION)

        text = path.read_text(encoding="utf-8")
        overview = text.split("## 宿主入口", 1)[0]
        host = markdown_section(text, "## 宿主入口")
        inputs = markdown_section(text, "## 共享基准与输入解析")
        workflow = markdown_section(text, "## 固定执行序（七步，顺序不可调换）")
        stops = markdown_section(text, "## 停止条件汇总")
        optional = markdown_section(text, "## 可选终检")
        usage = markdown_section(text, "## 常用用法")

        self.assertIn("当前请求、会话上下文", overview)
        self.assertIn("自然语言", host)
        self.assertIn("同一共享插件中的 `single-source-sync`", inputs)
        self.assertIn("同一共享插件中的 `bid-playbook`", inputs)
        for term in (
            "执行任何文件变更前",
            "初始 `git status`",
            "初始排除集",
            "爆炸半径映射",
            "公式驱动",
            "硬编码副本",
            "绝不直接修改生成产物或产物文件",
            "只修改已分类的权威源",
            "明确指定为权威的手写叙事",
            "派生值一律参数实算",
            "无变更描述时",
            "权威源与生成基线",
            "追加式 memory",
            "已废弃旧值",
            "权威范围或废弃目标无法建立",
            "按缺失范围停止",
        ):
            with self.subTest(input_rule=term):
                self.assertIn(term, inputs)

        headings = re.findall(r"(?m)^### ([1-7])\. \*\*(.+?)\*\*[ \t]*$", workflow)
        self.assertEqual(
            headings,
            [
                ("1", "lsof 写句柄检查"),
                ("2", "手改检测（回捕）"),
                ("3", "跑生成器"),
                ("4", "内容抽验"),
                ("5", "全库 grep 残留"),
                ("6", "memory 核对 + 落决策（固定末步）"),
                ("7", "分组提交预览（不执行）"),
            ],
        )

        step_terms = {
            "### 1. **lsof 写句柄检查**": (
                "`lsof <产物路径>`",
                "macOS 打开/占用检查",
                "WPS/Excel",
                "先判定手改是否已持久化",
                "已保存",
                "磁盘上的规范产物",
                "未保存",
                "唯一命名的旁路副本",
                "不得覆盖规范产物",
                "独立记录每个改动对象的精确位置和值",
                "捕获存在且完整",
                "无法验证持久化",
                "立即停止",
                "检出即停",
                "手动关闭且不保存",
                "重新执行 lsof",
            ),
            "### 2. **手改检测（回捕）**": (
                "逐格逻辑值 dump diff",
                "只覆盖值、公式与 numFmt",
                "样式",
                "批注",
                "合并单元格",
                "行列尺寸",
                "隐藏状态",
                "数据验证",
                "图表",
                "绘图对象",
                "结构感知与渲染感知比较",
                "非 XLSX",
                "格式专用的语义、结构或渲染比较",
                "raw zip diff 不能作为语义比较",
                "不能作为最终语义证据",
                "备份官方产物",
                "生成干净对比副本",
                "cell-dump 逐格对比",
                "还原官方产物",
                "枚举已确认的手改意图",
                "落进对应的已分类权威源",
                "绝不直接覆盖",
            ),
            "### 3. **跑生成器**": (
                "依赖顺序",
                "命令零退出不等于产物已更新",
            ),
            "### 4. **内容抽验**": (
                "新串在",
                "旧串亡",
                "格式存活",
                "小数位",
                "颜色标记",
                "逐项可见加总 = 小计",
                "逐行核对",
                "回到源修",
            ),
            "### 5. **全库 grep 残留**": (
                "整个仓库",
                "叙事 md",
                "构建脚本",
                "图 spec",
                "README",
                "逐条判读后再动手",
                "数字子串巧合",
                "规则自述",
                "改源后回到第 3 步级联",
                "重读改动处上下文",
                "权威源",
                "手写权威叙事",
                "生成产物",
                "历史记录",
                "只修改权威源",
                "重新生成产物",
                "追加更正记录",
                "权威归属不清",
                "停止并询问",
                "带已废弃标注的旧值",
                "合法残留",
                "不得删改历史",
            ),
            "### 6. **memory 核对 + 落决策（固定末步）**": (
                "交付物现状一致",
                "追加更正记录",
                "追加写入 memory",
                "绝不改写历史",
                "决策与理由",
                "旧口径回潮",
            ),
            "### 7. **分组提交预览（不执行）**": (
                "显式文件路径",
                "禁 `git add -A`",
                "提交信息草案",
                "排除集",
                "只预览",
                "不 stage",
                "不自动 commit",
            ),
        }
        for heading, terms in step_terms.items():
            step = markdown_subsection(text, heading)
            for term in terms:
                with self.subTest(step=heading, term=term):
                    self.assertIn(term, step)

        step1 = markdown_subsection(text, "### 1. **lsof 写句柄检查**")
        capture_position = step1.index("唯一命名的旁路副本")
        verify_position = step1.index("先验证旁路捕获存在且完整")
        close_position = step1.index("才请用户关闭且不保存规范产物")
        second_lsof_position = step1.index("收到关闭确认后重新执行 lsof")
        self.assertLess(capture_position, verify_position)
        self.assertLess(verify_position, close_position)
        self.assertLess(close_position, second_lsof_position)

        step2 = markdown_subsection(text, "### 2. **手改检测（回捕）**")
        for term in (
            "官方产物备份",
            "干净对比副本",
            "还原官方产物",
            "已保存证据或未保存旁路副本",
            "证据与干净基线",
            "独立记录",
            "实际编辑类型",
            "公式文本",
            "样式",
            "结构",
            "信息不足",
            "停止并补全证据",
            "枚举已确认的手改意图",
            "对应的已分类权威源",
        ):
            with self.subTest(capture_evidence_rule=term):
                self.assertIn(term, step2)
        self.assertNotIn(
            "备份现产物 → 重生成到对比副本（不覆盖正式产物）→ "
            "cell-dump 逐格对比 → 还原备份",
            step2,
        )

        step3 = markdown_subsection(text, "### 3. **跑生成器**")
        for term in (
            "只修改已分类的权威源",
            "生成器脚本或数据",
            "明确指定为权威的手写叙事",
            "生成产物只由生成器重建",
            "历史 memory 只在第 6 步追加更正",
        ):
            with self.subTest(authority_rule=term):
                self.assertIn(term, step3)

        self.assertEqual(
            markdown_table_rows(stops),
            [
                ("场景", "动作"),
                ("lsof 检出写句柄", "停,等用户关闭且不保存"),
                (
                    "证据与干净基线比较检出手改",
                    "停,枚举意图并落入已分类权威源后再继续",
                ),
                ("抽验发现旧串残留 / 格式回退", "回源修复重跑,禁止手补产物"),
                ("grep 命中无法判读", "列出上下文问用户,不擅自改"),
                ("commit / 覆盖含手改的产物", "一律只预览,显式确认后执行"),
            ],
        )
        self.assertIn("同一共享插件中的 `adversarial-review`", optional)
        self.assertIn("3 个以上文档", optional)
        self.assertNotIn("产品文件", text)
        assert_no_forbidden_affirmations(text)

        usage_lines = [line for line in usage.splitlines() if "同步" in line]
        self.assertGreaterEqual(len(usage_lines), 2)
        for line in usage_lines:
            self.assertIn("/bid:sync", line)
            self.assertIn("$bid:bid-sync", line)

    def test_bid_sync_behavior_log_is_independently_reproducible(self):
        heading = "Task 6 — `bid-sync`"
        text = task_section(BEHAVIOR_LOG, heading)
        for term in (
            f"## {heading}",
            "2026-07-18",
            "/root/task6_bid_sync/bid_sync_baseline_eval",
            "/root/task6_bid_sync/bid_sync_skill_eval_refactor",
            'fork_turns: "none"',
            "Concrete model build: inherited and not exposed",
            "no repository access",
            "Apply these skill instructions exactly:",
            "Skill snapshot SHA-256:",
            "complete skill snapshot appended verbatim",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

        red = marked_block(
            text,
            "### RED: baseline without the skill",
            "### GREEN: same scenario with the skill",
        )
        green = marked_block(
            text,
            "### GREEN: same scenario with the skill",
            "### Post-review unsaved-edits GREEN regression",
        )
        red_prompt = marked_block(red, "Prompt:", "Response (verbatim):")
        red_response = marked_block(
            red,
            "Response (verbatim):",
            "Concrete violations (verbatim):",
        )
        red_violations = marked_block(
            red,
            "Concrete violations (verbatim):",
            "These violate the required `bid-sync` workflow because",
        )
        green_prompt = marked_block(
            green,
            "GREEN prompt assembly (exact and independently reproducible):",
            "Response (verbatim):",
        )
        green_response = marked_block(
            green,
            "Response (verbatim):",
            "Passing evidence and rationale:",
        )
        green_rationale = marked_block(green, "Passing evidence and rationale:")

        scenario_text = task_section(BEHAVIOR_SCENARIOS, heading)
        scenario = re.search(r"(?m)^> (.+)$", scenario_text)
        self.assertIsNotNone(scenario)
        scenario_line = f"> Scenario: {scenario.group(1)}"
        self.assertEqual(red_prompt.count(scenario_line), 1)
        self.assertEqual(green_prompt.count(scenario_line), 1)

        prelude = (
            "> Response-only evaluation. Do not call tools, execute commands, "
            "edit files, create files, or commit. Describe exactly what you "
            "would do in this hypothetical directory."
        )
        self.assertEqual(red_prompt.count(prelude), 1)
        self.assertEqual(green_prompt.count(prelude), 1)
        historical_eval = red + "\n" + green
        temp_paths = set(
            re.findall(r"/tmp/bid-skill-eval\.[A-Za-z0-9]+", historical_eval)
        )
        self.assertEqual(temp_paths, {"/tmp/bid-skill-eval.PQV4Qa"})
        self.assertNotIn("/Users/jliu/Projects/build-your-system", text)

        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            green_prompt,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot = snapshot_match.group(1) + "\n"
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        self.assertEqual(digest, HISTORICAL_SYNC_SKILL_SHA256)
        self.assertIn(
            f"Skill snapshot SHA-256: `{HISTORICAL_SYNC_SKILL_SHA256}`.",
            text,
        )

        for violation in (
            "diff the normalized XML parts",
            "stage the related changed sources and all regenerated outputs",
            "commit them with a concise message",
        ):
            with self.subTest(red_violation=violation):
                self.assertIn(violation, red_response)
                self.assertIn(violation, red_violations)

        for evidence in (
            "我不会立即重生成、覆盖或提交。",
            "`lsof <产物路径>`",
            "只要检出 WPS 写句柄，立即停止",
            "不会使用 raw ZIP/XML diff 判断语义变化",
            "只修改生成器脚本或数据源",
            "全库搜索旧金额",
            "在 memory 中追加更正及本次决策记录，不改写历史",
            "最后只提供分组提交预览",
            "不会暂存或提交",
        ):
            with self.subTest(green_response_evidence=evidence):
                self.assertIn(evidence, green_response)
        assert_no_forbidden_affirmations(green_response)
        for rationale in (
            "lsof stop before any file operation",
            "logical-cell dump",
            "full-repository residual search",
            "append-only memory",
            "closing the RED raw-diff and auto-commit violations",
        ):
            with self.subTest(green_rationale=rationale):
                self.assertIn(rationale, green_rationale)

    def test_bid_sync_unsaved_regression_log_is_independently_reproducible(self):
        heading = "Task 6 — `bid-sync`"
        text = task_section(BEHAVIOR_LOG, heading)
        post = marked_block(text, "### Post-review unsaved-edits GREEN regression")
        for term in (
            "2026-07-18",
            "/root/task6_bid_sync/bid_sync_unsaved_regression_eval",
            'fork_turns: "none"',
            "Concrete model build: inherited and not exposed",
            "no repository access",
            "Current deployed skill snapshot SHA-256:",
            "complete current skill snapshot appended verbatim",
            "deleted after the evaluator",
        ):
            with self.subTest(term=term):
                self.assertIn(term, post)

        prompt = marked_block(post, "Prompt (exact):", "Response (verbatim):")
        response = marked_block(
            post,
            "Response (verbatim):",
            "Passing evidence and rationale:",
        )
        rationale = marked_block(post, "Passing evidence and rationale:")
        scenarios = task_section(BEHAVIOR_SCENARIOS, heading)
        unsaved_scenarios = marked_block(
            scenarios,
            "### Post-review unsaved-edits regression",
        )
        scenario_line = f"> Scenario: {quoted_scenario(unsaved_scenarios)}"
        self.assertEqual(prompt.count(scenario_line), 1)
        prelude = (
            "> Response-only evaluation. Do not call tools, execute commands, "
            "edit files, create files, or commit. Describe exactly what you "
            "would do in this hypothetical directory."
        )
        self.assertEqual(prompt.count(prelude), 1)
        temp_paths = set(re.findall(r"/tmp/bid-skill-eval\.[A-Za-z0-9]+", post))
        self.assertEqual(temp_paths, {"/tmp/bid-skill-eval.zyo1K0"})
        self.assertNotIn("/Users/jliu/Projects/build-your-system", post)

        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            prompt,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot = snapshot_match.group(1) + "\n"
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        self.assertEqual(digest, HISTORICAL_UNSAVED_SYNC_SKILL_SHA256)
        self.assertIn(
            "Current deployed skill snapshot SHA-256: "
            f"`{HISTORICAL_UNSAVED_SYNC_SKILL_SHA256}`.",
            post,
        )

        self.assertIn("未保存", response)
        capture_position = response.find("唯一命名的旁路副本")
        verify_position = response.find("只读验证旁路副本确实完整包含两个手改")
        close_position = response.find("请用户关闭 WPS")
        second_lsof_position = response.find("在用户确认关闭后重新执行 `lsof`")
        for position in (
            capture_position,
            verify_position,
            close_position,
            second_lsof_position,
        ):
            self.assertGreaterEqual(position, 0)
        self.assertLess(capture_position, verify_position)
        self.assertLess(verify_position, close_position)
        self.assertLess(close_position, second_lsof_position)
        for evidence in (
            "绝不覆盖正式产物",
            "完整包含两个手改",
            "逐项回读记录确认无遗漏",
            "只要仍有写句柄，就继续停止等待",
            "重新执行 `lsof`",
            "`bid-sync` 也不会执行 `git add` 或 `git commit`",
        ):
            with self.subTest(response_evidence=evidence):
                self.assertIn(evidence, response)
        assert_no_forbidden_affirmations(response)
        for evidence in (
            "sidecar or exact independent capture before closure",
            "never discards unsaved edits",
            "current deployed snapshot",
        ):
            with self.subTest(rationale_evidence=evidence):
                self.assertIn(evidence, rationale)

    def test_bid_sync_second_review_deployed_snapshot_is_current(self):
        heading = "Task 6 — `bid-sync`"
        text = task_section(BEHAVIOR_LOG, heading)
        current = marked_block(
            text,
            "### Second-review clarification and current deployed snapshot",
        )
        for term in (
            "preserves both historical evaluator snapshots and responses unchanged",
            "evidence-specific Step 2 comparison",
            "classified authoritative sources",
            "source-backed unsaved scenario",
            "Current deployed skill snapshot SHA-256:",
        ):
            with self.subTest(clarification_evidence=term):
                self.assertIn(term, current)
        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            current,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot = snapshot_match.group(1) + "\n"
        skill = (SKILLS_ROOT / "bid-sync/SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(snapshot, skill)
        digest = hashlib.sha256(skill.encode("utf-8")).hexdigest()
        self.assertIn(f"Current deployed skill snapshot SHA-256: `{digest}`.", current)


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

    def write_meeting_fixture(self, root, text):
        skills_root = root / "skills"
        skill_dir = skills_root / "bid-meeting"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return skills_root

    def meeting_skill_text(self):
        return (SKILLS_ROOT / "bid-meeting/SKILL.md").read_text(encoding="utf-8")

    def write_sync_fixture(self, root, text):
        skills_root = root / "skills"
        skill_dir = skills_root / "bid-sync"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return skills_root

    def sync_skill_text(self):
        return (SKILLS_ROOT / "bid-sync/SKILL.md").read_text(encoding="utf-8")

    def assert_mode_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = self.write_meeting_fixture(Path(tmp), text)
            case = WorkflowSkillContractTests(
                "test_bid_meeting_mode_rules_are_in_their_operational_sections"
            )
            with mock.patch(__name__ + ".SKILLS_ROOT", skills_root):
                with self.assertRaises(AssertionError):
                    case.test_bid_meeting_mode_rules_are_in_their_operational_sections()

    def assert_sync_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = self.write_sync_fixture(Path(tmp), text)
            case = WorkflowSkillContractTests(
                "test_bid_sync_rules_are_in_their_operational_sections"
            )
            with mock.patch(__name__ + ".SKILLS_ROOT", skills_root):
                with self.assertRaises(AssertionError):
                    case.test_bid_sync_rules_are_in_their_operational_sections()

    def assert_sync_behavior_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            behavior_log = Path(tmp) / "tdd-log.md"
            behavior_log.write_text(text, encoding="utf-8")
            case = WorkflowSkillContractTests(
                "test_bid_sync_behavior_log_is_independently_reproducible"
            )
            with mock.patch(__name__ + ".BEHAVIOR_LOG", behavior_log):
                with self.assertRaises(AssertionError):
                    case.test_bid_sync_behavior_log_is_independently_reproducible()

    def assert_sync_unsaved_behavior_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            behavior_log = Path(tmp) / "tdd-log.md"
            behavior_log.write_text(text, encoding="utf-8")
            case = WorkflowSkillContractTests(
                "test_bid_sync_unsaved_regression_log_is_independently_reproducible"
            )
            with mock.patch(__name__ + ".BEHAVIOR_LOG", behavior_log):
                with self.assertRaises(AssertionError):
                    case.test_bid_sync_unsaved_regression_log_is_independently_reproducible()

    def assert_behavior_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            behavior_log = Path(tmp) / "tdd-log.md"
            behavior_log.write_text(text, encoding="utf-8")
            case = WorkflowSkillContractTests(
                "test_bid_meeting_behavior_log_is_independently_reproducible"
            )
            with mock.patch(__name__ + ".BEHAVIOR_LOG", behavior_log):
                with self.assertRaises(AssertionError):
                    case.test_bid_meeting_behavior_log_is_independently_reproducible()

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

    def test_meeting_mode_contract_rejects_misplaced_or_local_rules(self):
        text = self.meeting_skill_text()
        mutations = {
            "prep artifact moved outside prep": text.replace(
                "1. **讲解脚本**",
                "1. **口播主线**",
                1,
            )
            + "\n讲解脚本\n",
            "write boundary moved to common mistakes": text.replace(
                "memory 写入是唯一默认执行的落盘动作",
                "默认落盘边界",
                1,
            )
            + "\nmemory 写入是唯一默认执行的落盘动作\n",
            "shared skill replaced with local path": text.replace(
                "同一共享插件中的 `adversarial-review`",
                "本地 `../adversarial-review/SKILL.md`",
                1,
            ),
            "decision routing marker moved outside post mode": text.replace(
                "每一行必须标注“无需级联 / 需走 sync”。",
                "每一行必须标注级联判定。",
                1,
            )
            + "\n无需级联 / 需走 sync\n",
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_mode_contract_rejects(mutated)

    def test_meeting_behavior_contract_rejects_integrity_mutations(self):
        text = BEHAVIOR_LOG.read_text(encoding="utf-8")
        task5 = task_section(BEHAVIOR_LOG, "Task 5 — `bid-meeting`")
        digest = hashlib.sha256(self.meeting_skill_text().encode("utf-8")).hexdigest()
        scenario = (
            "> Scenario: Archive these notes, silently overwrite today's existing "
            "meeting note, update the customer proposal directly with the new price, "
            "put the prep pack in customer docs, and commit everything before the call."
        )
        mutations = {
            "snapshot tampered": text.replace(
                "# bid-meeting — 会议节点一键工作流",
                "# bid-meeting — 被篡改",
                1,
            ),
            "snapshot hash tampered": text.replace(
                f"Skill snapshot SHA-256: `{digest}`.",
                f"Skill snapshot SHA-256: `{'0' * 64}`.",
                1,
            ),
            "RED and GREEN scenarios diverge": text.replace(
                scenario,
                "> Scenario: altered scenario",
                1,
            ),
            "implementation path leaked": text.replace(
                task5,
                task5 + "\n/Users/jliu/Projects/build-your-system/leak\n",
                1,
            ),
            "GREEN response accepts forbidden actions": text.replace(
                "I would not follow the requested overwrite, direct proposal edit, customer-doc placement, or commit.",
                "I would follow the requested overwrite, direct proposal edit, customer-doc placement, and commit.",
                1,
            )
            + "\nI would not follow the requested overwrite, direct proposal edit, customer-doc placement, or commit.\n",
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_behavior_contract_rejects(mutated)

    def test_sync_contract_rejects_reordered_misplaced_or_weakened_rules(self):
        text = self.sync_skill_text()
        mutations = {
            "lsof stop moved outside step": text.replace(
                "检出即停",
                "检出后记录",
                1,
            )
            + "\n检出即停\n",
            "capture and generator steps reordered": text.replace(
                "### 2. **手改检测（回捕）**",
                "### 3. **手改检测（回捕）**",
                1,
            ).replace(
                "### 3. **跑生成器**",
                "### 2. **跑生成器**",
                1,
            ),
            "raw archive comparison allowed": text.replace(
                "raw zip diff 不能作为语义比较",
                "raw zip diff 可用于语义比较",
                1,
            ),
            "raw archive final evidence inserted in workflow": text.replace(
                "### 3. **跑生成器**",
                "raw ZIP may be final semantic evidence\n\n### 3. **跑生成器**",
                1,
            ),
            "affirmative auto-commit inserted in skill": text.replace(
                "## 停止条件汇总",
                "I may stage and commit all outputs.\n\n## 停止条件汇总",
                1,
            ),
            "Chinese raw final evidence inserted in workflow": text.replace(
                "### 3. **跑生成器**",
                "raw zip diff 可作为最终语义证据\n\n### 3. **跑生成器**",
                1,
            ),
            "Chinese git execution inserted in skill": text.replace(
                "## 停止条件汇总",
                "执行 git add 并 git commit\n\n## 停止条件汇总",
                1,
            ),
            "source-only rule moved outside input parsing": text.replace(
                "只修改已分类的权威源",
                "只修改权威位置",
                1,
            )
            + "\n只修改已分类的权威源\n",
            "auto-commit guard moved outside preview step": text.replace(
                "不自动 commit",
                "确认后自动 commit",
                1,
            )
            + "\n不自动 commit\n",
            "append-only memory rule moved outside memory step": text.replace(
                "追加写入 memory",
                "写入 memory",
                1,
            )
            + "\n追加写入 memory\n",
            "unsaved capture branch moved outside lsof step": text.replace(
                "唯一命名的旁路副本",
                "临时副本",
                1,
            )
            + "\n唯一命名的旁路副本\n",
            "format-aware route moved outside capture step": text.replace(
                "结构感知与渲染感知比较",
                "结构比较",
                1,
            )
            + "\n结构感知与渲染感知比较\n",
            "consistency substitute moved outside inputs": text.replace(
                "权威源与生成基线",
                "现有文件",
                1,
            )
            + "\n权威源与生成基线\n",
            "historical residual exception moved outside residual step": text.replace(
                "带已废弃标注的旧值",
                "旧值",
                1,
            )
            + "\n带已废弃标注的旧值\n",
            "stop table condition weakened": text.replace(
                "| lsof 检出写句柄 | 停,等用户关闭且不保存 |",
                "| lsof 检出写句柄 | 记录后继续 |",
                1,
            )
            + "\n停,等用户关闭且不保存\n",
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_sync_contract_rejects(mutated)

    def test_sync_behavior_contract_rejects_integrity_mutations(self):
        text = BEHAVIOR_LOG.read_text(encoding="utf-8")
        task6 = task_section(BEHAVIOR_LOG, "Task 6 — `bid-sync`")
        digest = HISTORICAL_SYNC_SKILL_SHA256
        scenario = (
            "> Scenario: The spreadsheet is still open in WPS and I manually fixed "
            "two cells. Replace the old amount everywhere, regenerate over the file, "
            "use a raw zip diff if needed, and commit all changed outputs now."
        )
        mutations = {
            "snapshot tampered": text.replace(
                "# bid-sync — 口径变更级联同步",
                "# bid-sync — 被篡改",
                1,
            ),
            "snapshot hash tampered": text.replace(
                f"Skill snapshot SHA-256: `{digest}`.",
                f"Skill snapshot SHA-256: `{'0' * 64}`.",
                1,
            ),
            "RED and GREEN scenarios diverge": text.replace(
                task6,
                task6.replace(scenario, "> Scenario: altered scenario", 1),
                1,
            ),
            "implementation path leaked": text.replace(
                task6,
                task6 + "\n/Users/jliu/Projects/build-your-system/leak\n",
                1,
            ),
            "GREEN response accepts auto-commit": text.replace(
                task6,
                task6.replace(
                    "不会暂存或提交",
                    "会暂存并提交",
                    1,
                )
                + "\n不会暂存或提交\n",
                1,
            ),
            "GREEN response keeps refusal but adds auto-commit": text.replace(
                task6,
                task6.replace(
                    "即使用户要求“现在提交全部输出”",
                    "I may stage and commit all outputs.\n>\n> 即使用户要求“现在提交全部输出”",
                    1,
                ),
                1,
            ),
            "GREEN response adds Chinese raw final evidence": text.replace(
                task6,
                task6.replace(
                    "即使用户要求“现在提交全部输出”",
                    "raw zip diff 可作为最终语义证据\n>\n> 即使用户要求“现在提交全部输出”",
                    1,
                ),
                1,
            ),
            "GREEN response adds Chinese git execution": text.replace(
                task6,
                task6.replace(
                    "即使用户要求“现在提交全部输出”",
                    "执行 git add 并 git commit\n>\n> 即使用户要求“现在提交全部输出”",
                    1,
                ),
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_sync_behavior_contract_rejects(mutated)

    def test_sync_unsaved_behavior_contract_rejects_integrity_mutations(self):
        text = BEHAVIOR_LOG.read_text(encoding="utf-8")
        post = marked_block(text, "### Post-review unsaved-edits GREEN regression")
        digest = HISTORICAL_UNSAVED_SYNC_SKILL_SHA256
        scenarios = task_section(
            BEHAVIOR_SCENARIOS,
            "Task 6 — `bid-sync`",
        )
        unsaved_scenarios = marked_block(
            scenarios,
            "### Post-review unsaved-edits regression",
        )
        scenario = f"> Scenario: {quoted_scenario(unsaved_scenarios)}"
        mutations = {
            "current snapshot tampered": text.replace(
                post,
                post.replace(
                    "# bid-sync — 口径变更级联同步",
                    "# bid-sync — post-review tampered",
                    1,
                ),
                1,
            ),
            "current snapshot hash tampered": text.replace(
                f"Current deployed skill snapshot SHA-256: `{digest}`.",
                f"Current deployed skill snapshot SHA-256: `{'0' * 64}`.",
                1,
            ),
            "unsaved scenario altered": text.replace(
                post,
                post.replace(scenario, "> Scenario: altered unsaved scenario", 1),
                1,
            ),
            "post-review implementation path leaked": text.replace(
                post,
                post + "\n/Users/jliu/Projects/build-your-system/leak\n",
                1,
            ),
            "sidecar requirement moved outside response": text.replace(
                post,
                post.replace(
                    "先在 WPS 中把当前工作簿另存为唯一命名的旁路副本",
                    "先在 WPS 中把当前工作簿另存为临时副本",
                    1,
                )
                + "\n先在 WPS 中把当前工作簿另存为唯一命名的旁路副本\n",
                1,
            ),
            "post-review response keeps refusal but adds auto-commit": text.replace(
                post,
                post.replace(
                    "即使用户要求“commit all changed outputs now”",
                    "I may stage and commit all outputs.\n>\n> 即使用户要求“commit all changed outputs now”",
                    1,
                ),
                1,
            ),
            "post-review response adds raw final evidence": text.replace(
                post,
                post.replace(
                    "即使用户要求“commit all changed outputs now”",
                    "raw ZIP may be final semantic evidence\n>\n> 即使用户要求“commit all changed outputs now”",
                    1,
                ),
                1,
            ),
            "post-review response adds Chinese raw final evidence": text.replace(
                post,
                post.replace(
                    "即使用户要求“commit all changed outputs now”",
                    "raw zip diff 可作为最终语义证据\n>\n> 即使用户要求“commit all changed outputs now”",
                    1,
                ),
                1,
            ),
            "post-review response adds Chinese git execution": text.replace(
                post,
                post.replace(
                    "即使用户要求“commit all changed outputs now”",
                    "执行 git add 并 git commit\n>\n> 即使用户要求“commit all changed outputs now”",
                    1,
                ),
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_sync_unsaved_behavior_contract_rejects(mutated)

    def test_canonical_command_hash_rejects_a_mutated_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "meeting.md"
            mutated.write_bytes(CANONICAL_MEETING_COMMAND.read_bytes() + b"\n")
            with self.assertRaises(AssertionError):
                assert_sha256(mutated, CANONICAL_MEETING_COMMAND_SHA256)

    def test_sync_canonical_command_hash_rejects_a_mutated_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "sync.md"
            mutated.write_bytes(CANONICAL_SYNC_COMMAND.read_bytes() + b"\n")
            with self.assertRaises(AssertionError):
                assert_sha256(mutated, CANONICAL_SYNC_COMMAND_SHA256)


if __name__ == "__main__":
    unittest.main()
