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
CANONICAL_HANDOFF_COMMAND = BID_ROOT / "commands/handoff.md"
CANONICAL_HANDOFF_COMMAND_SHA256 = (
    "f3950be76ac7e7acec987e4490a98a614ad90d0fbad5efc01fdcc3c6c13832e0"
)
CANONICAL_REVIEW_COMMAND = BID_ROOT / "commands/review.md"
CANONICAL_REVIEW_COMMAND_SHA256 = (
    "b76fe42707df91bd118dd1df6377eaf13747bf782f2938a8ccd73f308d9f8e2f"
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
HISTORICAL_HANDOFF_SKILL_SHA256 = (
    "1b5c5b999599b4a1adea9c3875c94ed61d3bf1e8e46e2f094cb392a4995227ca"
)
HISTORICAL_REVIEW_SKILL_SHA256 = (
    "f19cd4bd1de8b2c9bc4dd70702ba25b73229823f1e9ac7acd474ac3e96532969"
)
HANDOFF_DESCRIPTION = (
    "Use when 用户提出“/bid:handoff”“$bid:bid-handoff”“原型交接包”"
    "“交接给 AI 设计工具”“设计交接”“宿主视觉校正”或“分批生成原型”等投标交接请求"
)
REVIEW_DESCRIPTION = (
    "Use when 用户提出“/bid:review”“$bid:bid-review”“交付前审校”“多透镜审校”"
    "“红队方案”“检查报价表”“逐页目检”或要求在提交前复核投标交付物"
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


HANDOFF_AFFIRMATIVE_PATTERNS = {
    "receiver_guess": (
        re.compile(
            r"(?is)(?:根据|基于|依照).{0,24}"
            r"(?:官方品牌资料|官方品牌|品牌资料|官方\s*VI).{0,24}"
            r"(?:推断|猜测|假定).{0,12}(?:接收工具|接收方)"
        ),
        re.compile(
            r"(?is)(?:from|using|based on).{0,24}"
            r"(?:official brand|brand guide|official VI).{0,30}"
            r"(?:infer|guess|assume).{0,20}(?:receiver|receiving tool)"
        ),
        re.compile(
            r"(?is)(?:infer|guess|assume).{0,20}(?:receiver|receiving tool)"
            r".{0,30}(?:official brand|brand guide|official VI)"
        ),
    ),
    "copy_placeholder_draft": (
        re.compile(
            r"(?is)(?:缺(?:少)?|没有|未有|暂无|未获批|缺失).{0,18}"
            r"(?:完整真实|完整定稿|合规|文案|copy).{0,24}"
            r"(?:先|可以|可|仍可|将|会)?.{0,10}"
            r"(?:做|创建|生成|产出).{0,14}"
            r"(?:占位|临时|非生产|工具中立)?.{0,10}(?:草稿|交接包|package)"
        ),
        re.compile(
            r"(?is)(?:without|missing|pending|unapproved).{0,24}"
            r"(?:copy|compliance).{0,36}"
            r"(?:create|make|produce|draft|will|can|may|would).{0,24}"
            r"(?:placeholder|draft|provisional)"
        ),
    ),
    "brand_vi_guess": (
        re.compile(
            r"(?is)(?:根据|基于|按|依照).{0,22}"
            r"(?:官方品牌资料|官方品牌|品牌资料|官方\s*VI|VI).{0,22}"
            r"(?:推断|猜|猜测|推测|估算|先凑|代替)"
        ),
        re.compile(
            r"(?is)(?:use|infer|guess|derive|estimate|substitute).{0,36}"
            r"(?:official brand|brand guide|official VI).{0,24}"
            r"(?:color|visual|receiver|receiving tool|instead|first)?"
        ),
        re.compile(
            r"(?is)(?:official brand|brand guide|official VI).{0,36}"
            r"(?:guess|infer|estimate|substitute).{0,24}(?:color|visual|receiver)?"
        ),
    ),
    "full_batch_first": (
        re.compile(
            r"(?is)(?:先|一次性|一批).{0,14}(?:生成|产出|创建).{0,24}"
            r"(?:完整|全部|所有).{0,14}(?:20\s*屏|屏幕|screens?).{0,24}"
            r"(?:再|然后|之后).{0,12}(?:拆批|分批|审查|审核|review)"
        ),
        re.compile(
            r"(?is)(?:generate|create|produce).{0,24}(?:all|full|complete)"
            r".{0,14}(?:20\s*)?screens?.{0,50}"
            r"(?:first|then|before).{0,24}(?:split|batch|review)"
        ),
    ),
    "package_destructive": (
        re.compile(
            r"(?is)(?:用户|客户|负责人|审批人).{0,18}(?:批准|确认|同意|审批)后"
            r".{0,14}(?:将|会|可以|可|允许)?.{0,8}"
            r"(?:覆盖|替换|重命名|迁移)"
        ),
        re.compile(
            r"(?is)(?:将|会|可以|可|允许|获批后|确认后).{0,18}"
            r"(?:覆盖|替换|重命名|迁移).{0,18}"
            r"(?:旧包|设计包|交接包|package)"
        ),
        re.compile(
            r"(?is)(?:after|once).{0,24}(?:user|client|customer)?\s*"
            r"(?:approval|approved|confirmation|confirmed).{0,24}"
            r"(?:will|can|may|would)?\s*(?:overwrite|replace|rename|migrate)"
        ),
        re.compile(
            r"(?is)(?:will|can|may|would|allowed to).{0,18}"
            r"(?:overwrite|replace|rename|migrate).{0,24}(?:old )?(?:package|design)"
        ),
    ),
    "stage_commit": (
        re.compile(
            r"(?is)(?:用户|客户|负责人|审批人).{0,18}(?:批准|确认|同意|审批)后"
            r".{0,18}(?:将|会|可以|可|允许)?.{0,10}"
            r"(?:执行|运行)?\s*git\s+add.{0,30}git\s+commit"
        ),
        re.compile(
            r"(?is)(?:将|会|可以|可|允许).{0,20}(?:执行|运行)?\s*"
            r"git\s+add.{0,30}git\s+commit"
        ),
        re.compile(
            r"(?is)(?:将|会|可以|可|允许).{0,18}(?:暂存|stage)"
            r".{0,24}(?:提交|commit)"
        ),
        re.compile(
            r"(?is)(?:after|once).{0,24}(?:approval|approved|confirmation|confirmed)"
            r".{0,24}(?:run|execute|stage|git\s+add).{0,30}(?:commit|git\s+commit)"
        ),
        re.compile(
            r"(?is)(?:will|can|may|would|allowed to).{0,18}"
            r"(?:run|execute|stage|git\s+add).{0,30}(?:commit|git\s+commit)"
        ),
    ),
}
HANDOFF_SCOPE_PATTERNS = {
    "receiver": ("receiver_guess",),
    "package": ("copy_placeholder_draft", "brand_vi_guess"),
    "batches": ("full_batch_first",),
    "report": ("package_destructive", "stage_commit"),
    "response": tuple(HANDOFF_AFFIRMATIVE_PATTERNS),
}
HANDOFF_NEGATION = re.compile(
    r"(?is)(?:不|绝不|不得|禁止|拒绝|不可|不能|不会|"
    r"must\s+not|do\s+not|don't|will\s+not|cannot|can't|may\s+not|"
    r"should\s+not|never|refus(?:e|ed|es|ing)|would\s+not)"
    r".{0,72}$"
)
HANDOFF_CLAUSE_BOUNDARY = re.compile(
    r"(?i:\b(?:but|however|yet)\b)|但是|然而|但|[\n。.，,；;!！?？]"
)


def assert_no_handoff_affirmative_contradictions(scoped_text):
    for scope, text in scoped_text.items():
        labels = HANDOFF_SCOPE_PATTERNS[scope]
        for label in labels:
            for pattern in HANDOFF_AFFIRMATIVE_PATTERNS[label]:
                for match in pattern.finditer(text):
                    clause_start = 0
                    for boundary in HANDOFF_CLAUSE_BOUNDARY.finditer(
                        text, 0, match.start()
                    ):
                        clause_start = boundary.end()
                    clause_through_match = text[clause_start : match.end()]
                    if HANDOFF_NEGATION.search(clause_through_match) is not None:
                        continue
                    raise AssertionError(
                        f"affirmative handoff contradiction in {scope}/{label}: "
                        f"{match.group(0)!r}"
                    )


REVIEW_AFFIRMATIVE_PATTERNS = {
    "single_general_pass": (
        re.compile(
            r"(?is)(?:一个|单一|一次|一轮).{0,16}"
            r"(?:通用|综合|general).{0,12}(?:pass|审校|检查|评审)"
        ),
        re.compile(r"(?is)\b(?:one|single)\s+general\s+pass\b"),
    ),
    "trust_without_reverse_test": (
        re.compile(
            r"(?is)(?:无需|跳过|不做).{0,20}(?:已知错误注入|反向验证|reverse test)"
            r".{0,36}(?:信任|采信|依赖).{0,24}(?:grep|生成器|退出码|exit code)"
        ),
        re.compile(
            r"(?is)\btrust\b.{0,30}(?:grep|generator|exit code).{0,36}"
            r"\bwithout\b.{0,24}(?:known.error|injection|reverse test)"
        ),
    ),
    "skip_visual_inspection": (
        re.compile(
            r"(?is)(?:跳过|省略|无需|不做)[^\n。.，,；;!！?？但]{0,24}"
            r"(?:逐页|逐张|视觉|渲染)[^\n。.，,；;!！?？但]{0,18}"
            r"(?:目检|检查|inspection)?"
        ),
        re.compile(
            r"(?is)\bskip\b.{0,30}(?:page.by.page|visual|render)"
            r".{0,20}(?:inspection|review)?"
        ),
    ),
    "auto_fix_locked_value": (
        re.compile(
            r"(?is)(?:立即|直接|自动|先)[^\n。.，,；;!！?？]{0,16}"
            r"(?:修复|修改|改)[^\n。.，,；;!！?？]{0,24}"
            r"(?:锁定|对外口径|价格|报价|义务)"
        ),
        re.compile(
            r"(?is)\b(?:immediately|directly|automatically)\b.{0,24}"
            r"(?:fix|change|edit).{0,28}(?:locked|price|obligation|commitment)"
        ),
    ),
    "direct_generated_output_edit": (
        re.compile(
            r"(?is)(?:直接|手工|手动).{0,16}(?:打补丁|修补|修改|改).{0,20}"
            r"(?:生成产物|产物文件|生成文件|PDF|xlsx)"
        ),
        re.compile(
            r"(?is)\b(?:directly|manually)\b.{0,18}(?:patch|edit|fix|modify)"
            r".{0,24}(?:generated (?:output|file|artifact)|PDF|xlsx)"
        ),
    ),
    "overwrite_generated_output": (
        re.compile(
            r"(?is)(?:用户|客户|负责人|审批人).{0,18}(?:批准|确认|同意|审批)后"
            r".{0,18}(?:将|会|可以|可|允许)?.{0,8}覆盖.{0,18}"
            r"(?:生成产物|产物|文件|输出)?"
        ),
        re.compile(
            r"(?is)(?:将|会|可以|可|允许|立即|直接).{0,20}覆盖.{0,18}"
            r"(?:生成产物|产物|文件|输出)"
        ),
        re.compile(
            r"(?is)(?:after|once).{0,24}(?:approval|approved|confirmation|confirmed)"
            r".{0,24}(?:will|can|may|would)?\s*overwrite.{0,24}"
            r"(?:generated )?(?:output|file|artifact)s?"
        ),
        re.compile(
            r"(?is)\b(?:will|can|may|would)\b.{0,18}overwrite.{0,24}"
            r"(?:generated )?(?:output|file|artifact)s?"
        ),
    ),
    "stage_commit": HANDOFF_AFFIRMATIVE_PATTERNS["stage_commit"],
}
REVIEW_SCOPE_PATTERNS = {
    "lenses": ("single_general_pass", "skip_visual_inspection"),
    "checker": ("trust_without_reverse_test",),
    "adjudication": ("auto_fix_locked_value",),
    "repair": ("direct_generated_output_edit", "overwrite_generated_output"),
    "report": ("overwrite_generated_output", "stage_commit"),
    "response": tuple(REVIEW_AFFIRMATIVE_PATTERNS),
}
REVIEW_NEGATION = re.compile(
    r"(?is)(?:不|非|绝不|不得|禁止|拒绝|不可|不能|不会|"
    r"must\s+not|do\s+not|don't|will\s+not|cannot|can't|may\s+not|"
    r"should\s+not|never|refus(?:e|ed|es|ing)|would\s+not)"
    r".{0,72}$"
)


def assert_no_review_affirmative_contradictions(scoped_text):
    for scope, text in scoped_text.items():
        for label in REVIEW_SCOPE_PATTERNS[scope]:
            for pattern in REVIEW_AFFIRMATIVE_PATTERNS[label]:
                for match in pattern.finditer(text):
                    clause_start = 0
                    for boundary in HANDOFF_CLAUSE_BOUNDARY.finditer(
                        text, 0, match.start()
                    ):
                        clause_start = boundary.end()
                    clause_through_match = text[clause_start : match.end()]
                    if REVIEW_NEGATION.search(clause_through_match) is not None:
                        continue
                    raise AssertionError(
                        f"affirmative review contradiction in {scope}/{label}: "
                        f"{match.group(0)!r}"
                    )


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

    def test_bid_handoff_contract(self):
        assert_workflow(
            "bid-handoff",
            required=(
                "接收工具是 blocking input",
                "输入形态",
                "概念分层",
                "设计 craft",
                "形态 A",
                "形态 B",
                "逐字合规锁定文案",
                "全量真实 copy",
                "实测取样的视觉参考",
                "宿主视觉双层令牌",
                "P0",
                "P1",
                "P2",
                "同一共享插件中的 `prototype-handoff`",
                "同一共享插件中的 `adversarial-review`",
                "同一共享插件中的 `single-source-sync`",
                "同一共享插件中的 `bid-playbook`",
                "最劣环境核验",
                "不覆盖",
                "不 stage",
                "不 commit",
                "## 宿主入口",
                "/bid:handoff",
                "$bid:bid-handoff",
                "自然语言",
                HOST_ADAPTATION_LINK,
            ),
            forbidden=(
                "$ARGUMENTS",
                "${CLAUDE_PLUGIN_ROOT}",
                "${CODEX_PLUGIN_ROOT}",
            ),
        )

    def test_bid_handoff_canonical_command_is_unchanged(self):
        assert_sha256(
            CANONICAL_HANDOFF_COMMAND,
            CANONICAL_HANDOFF_COMMAND_SHA256,
        )

    def test_bid_handoff_rules_are_in_their_operational_sections(self):
        path = SKILLS_ROOT / "bid-handoff/SKILL.md"
        data, _ = frontmatter(path)
        self.assertEqual(data["description"], HANDOFF_DESCRIPTION)

        text = path.read_text(encoding="utf-8")
        overview = text.split("## 宿主入口", 1)[0]
        host = markdown_section(text, "## 宿主入口")
        shared = markdown_section(text, "## 共享基准与输入解析")
        receiver = markdown_section(text, "## 接收工具与输入模型（blocking）")
        forms = markdown_section(text, "## 形态 A / 形态 B 选择")
        package = markdown_section(text, "## 交接包必含件")
        batches = markdown_section(text, "## P0/P1/P2 分批放行")
        review = markdown_section(text, "## 交付前对抗审校")
        worst = markdown_section(text, "## 最劣环境核验")
        report = markdown_section(text, "## 落盘与交接报告")
        stops = markdown_section(text, "## 停止条件与执行边界")
        usage = markdown_section(text, "## 常用用法")

        self.assertIn("当前请求、会话上下文和现有项目材料", overview)
        self.assertIn("接收工具名", overview)
        self.assertIn("原型范围", overview)
        self.assertIn("不依赖命令专用参数变量", overview)
        self.assertIn("自然语言", host)

        for shared_skill in (
            "`prototype-handoff`",
            "`single-source-sync`",
            "`bid-playbook`",
        ):
            with self.subTest(shared_skill=shared_skill):
                self.assertIn(f"同一共享插件中的 {shared_skill}", shared)
        self.assertIn(
            "未被本工作流覆盖的 A/B、视觉取样与分批细节",
            shared,
        )
        self.assertIn("以 `prototype-handoff` 为准", shared)

        for term in (
            "接收工具是 blocking input",
            "停下询问用户",
            "不猜",
            "输入形态：",
            "概念分层：",
            "设计 craft：",
            "三问任一答不出",
            "工具文档或一次试跑结果",
            "不凭印象定形态",
        ):
            with self.subTest(receiver_rule=term):
                self.assertIn(term, receiver)

        rows = markdown_table_rows(forms)
        self.assertEqual(
            rows,
            [
                ("形态", "接收工具特征", "包主体"),
                (
                    "形态 A（prompt+知识库路）",
                    "吃文件上传含图、稠密结构化 prompt、自带设计 craft",
                    "master prompt + 全量真实文案 + 带借鉴注记的参考图板",
                ),
                (
                    "形态 B（设计系统路）",
                    "读 tokens.css / 组件库代码、面向可复用设计系统",
                    "设计令牌 + 组件规范 + 示例组件代码",
                ),
            ],
        )
        self.assertIn("一句话说明形态选择理由", forms)
        self.assertIn("分别建两包", forms)

        for term in (
            "逐字合规锁定文案",
            "逐字使用,禁止改写",
            "项目内已裁决的定稿文案",
            "缺失就停止",
            "绝不代拟",
            "全量真实 copy",
            "不留 lorem/占位",
            "同一共享插件中的 `single-source-sync`",
            "实测取样的视觉参考",
            "真实录屏抽帧 + 像素取样",
            "禁止按官方 VI 猜",
            "拍摄清单",
            "宿主视觉双层令牌",
            "`--host-*`",
            "宿主 chrome 层",
            "自有品牌层",
        ):
            with self.subTest(package_rule=term):
                self.assertIn(term, package)

        for term in (
            "P0 核心流程先生成",
            "审过再放行 P1/P2",
            "明确每批屏数与验收点",
            "一次生成全部",
            "不得按一批生成全部 20 屏",
        ):
            with self.subTest(batch_rule=term):
                self.assertIn(term, batches)

        self.assertIn("同一共享插件中的 `adversarial-review`", review)
        for term in (
            "逐字 diff",
            "零改动",
            "内部口径",
            "发现即 STOP 报告",
            "build 数据源",
        ):
            with self.subTest(review_rule=term):
                self.assertIn(term, review)

        for term in (
            "用户真实打开方式",
            "file://",
            "PNG",
            "断网",
            "本地兜底",
            "亲自打开并截图确认",
        ):
            with self.subTest(worst_environment_rule=term):
                self.assertIn(term, worst)

        for term in (
            "包路径与文件清单",
            "形态选择理由",
            "分批放行计划",
            "「本次没拍到、待补拍」模块清单",
            "建议落 memory 的结论清单",
            "目标文件已存在",
            "diff 预览后停止",
            "不覆盖",
            "不 stage",
            "不 commit",
            "建议 commit message",
        ):
            with self.subTest(report_rule=term):
                self.assertIn(term, report)
        assert_no_handoff_affirmative_contradictions(
            {
                "receiver": receiver,
                "package": package,
                "batches": batches,
                "report": report,
            }
        )

        self.assertEqual(
            markdown_table_rows(stops),
            [
                ("停止条件", "必须采取的动作"),
                (
                    "接收工具未知或输入模型三问任一不明",
                    "停止组包；索要工具名、工具文档或一次试跑结果，不猜",
                ),
                (
                    "合规锁定文案缺定稿",
                    "停止组包等输入，绝不让工作流或接收工具代拟",
                ),
                (
                    "完整真实 copy / 完整定稿 copy 缺失",
                    "停止组包等输入，不用占位草稿代替",
                ),
                (
                    "宿主视觉无实测素材",
                    "只出拍摄清单等素材，不按官方 VI 先凑包",
                ),
                ("内部口径混入包内", "立即 STOP 报告，不外发"),
                (
                    "目标文件已存在 / 覆盖文件 / 迁移旧包",
                    "只出 diff 预览并停止，绝不执行",
                ),
                (
                    "stage / commit",
                    "只给显式路径的提交预览与建议消息，工作流自身绝不执行",
                ),
            ],
        )
        self.assertIn("接收工具、合规定稿、完整定稿 copy 与实测素材", stops)
        self.assertIn("不得创建或覆盖交接包", stops)

        for claude_route, codex_route in (
            ("/bid:meeting", "$bid:bid-meeting"),
            ("/bid:sync", "$bid:bid-sync"),
        ):
            route_lines = [
                line
                for line in report.splitlines()
                if claude_route in line or codex_route in line
            ]
            self.assertTrue(route_lines)
            for line in route_lines:
                self.assertIn(claude_route, line)
                self.assertIn(codex_route, line)

        usage_lines = [line for line in usage.splitlines() if "交接" in line]
        self.assertGreaterEqual(len(usage_lines), 3)
        for line in usage_lines:
            self.assertIn("/bid:handoff", line)
            self.assertIn("$bid:bid-handoff", line)

    def test_bid_handoff_behavior_log_is_independently_reproducible(self):
        heading = "Task 7 — `bid-handoff`"
        text = task_section(BEHAVIOR_LOG, heading)
        for term in (
            f"## {heading}",
            "2026-07-18",
            "/root/task7_bid_handoff/handoff_baseline_eval_fresh",
            "/root/task7_bid_handoff/handoff_skill_eval",
            'fork_turns: "none"',
            "Concrete model build: inherited and not exposed",
            "no repository access",
            "Apply these skill instructions exactly:",
            "Skill snapshot SHA-256:",
            "complete skill snapshot appended verbatim",
            "deleted after the evaluator",
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
            "Concrete violations (verbatim):",
        )
        red_violations = marked_block(
            red,
            "Concrete violations (verbatim):",
            "These violate the required `bid-handoff` workflow because",
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
        scenario_line = f"> Scenario: {quoted_scenario(scenario_text)}"
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
        self.assertEqual(temp_paths, {"/tmp/bid-skill-eval.Nq8LIu"})
        self.assertNotIn("/Users/jliu/Projects/build-your-system", text)

        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            green_prompt,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot = snapshot_match.group(1) + "\n"
        hash_fields = list(
            re.finditer(
                r"(?m)^Skill snapshot SHA-256: `([0-9a-f]{64})`\.$",
                green_prompt,
            )
        )
        self.assertEqual(len(hash_fields), 1)
        snapshot_start = green_prompt.index("````markdown")
        self.assertLess(hash_fields[0].end(), snapshot_start)
        self.assertEqual(
            green_prompt[hash_fields[0].end() : snapshot_start],
            "\n\n",
        )
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        self.assertEqual(hash_fields[0].group(1), digest)
        self.assertEqual(digest, HISTORICAL_HANDOFF_SKILL_SHA256)

        for violation in (
            "I could only create a clearly watermarked, non-production draft using explicit placeholders",
            "install the approved replacement",
            "commit only the scoped changes",
        ):
            with self.subTest(red_violation=violation):
                self.assertIn(violation, red_response)
                self.assertIn(violation, red_violations)

        for evidence in (
            "I would stop immediately",
            "Tool name and documentation or one trial-run result.",
            "embedded verbatim",
            "Measured visual evidence",
            "P0/P1/P2",
            "would not be generated in one batch",
            "I would not overwrite, merge, migrate, rename around, stage, or commit anything.",
            "it would never run `git add` or `git commit`",
        ):
            with self.subTest(green_response_evidence=evidence):
                self.assertIn(evidence, green_response)
        for rationale in (
            "receiver-model questions",
            "verbatim compliance copy",
            "measured visual evidence",
            "closing the RED tool-neutral and one-batch violations",
        ):
            with self.subTest(green_rationale=rationale):
                self.assertIn(rationale, green_rationale)
        assert_no_handoff_affirmative_contradictions({"response": green_response})

    def test_bid_handoff_safe_english_negations_are_not_contradictions(self):
        safe_cases = (
            (
                "receiver",
                "I cannot infer the receiving tool from the official brand guide.",
            ),
            (
                "package",
                "Without approved copy I will not create a placeholder draft.",
            ),
            (
                "batches",
                "I will not generate all 20 screens first, then split them into batches.",
            ),
            (
                "report",
                "After approval I will not replace the old package.",
            ),
            (
                "report",
                "After approval I will not stage the files and commit them.",
            ),
            (
                "receiver",
                "I can't infer the receiving tool from the official brand guide.",
            ),
            (
                "package",
                "Without approved copy I may not create a placeholder draft.",
            ),
            (
                "batches",
                "I should not generate all 20 screens first, then split them "
                "into batches.",
            ),
        )
        for scope, text in safe_cases:
            with self.subTest(scope=scope, text=text):
                assert_no_handoff_affirmative_contradictions({scope: text})

    def test_bid_handoff_current_deployed_snapshot_is_current(self):
        heading = "Task 7 — `bid-handoff`"
        text = task_section(BEHAVIOR_LOG, heading)
        current = marked_block(
            text,
            "### Follow-up safety hardening and current deployed snapshot",
        )
        for term in (
            "preserves both evaluator prompts and verbatim responses unchanged",
            "scoped affirmative-contradiction rejection",
            "complete real copy as a blocking input",
            "Current deployed skill snapshot SHA-256:",
        ):
            with self.subTest(clarification_evidence=term):
                self.assertIn(term, current)
        hash_fields = list(
            re.finditer(
                r"(?m)^Current deployed skill snapshot SHA-256: "
                r"`([0-9a-f]{64})`\.$",
                current,
            )
        )
        self.assertEqual(len(hash_fields), 1)
        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            current,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot_start = current.index("````markdown")
        self.assertLess(hash_fields[0].end(), snapshot_start)
        self.assertEqual(
            current[hash_fields[0].end() : snapshot_start],
            "\n\n",
        )
        snapshot = snapshot_match.group(1) + "\n"
        skill = (SKILLS_ROOT / "bid-handoff/SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(snapshot, skill)
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        self.assertEqual(hash_fields[0].group(1), digest)

    def test_bid_review_contract(self):
        assert_workflow(
            "bid-review",
            required=(
                "ReviewObject",
                "文档 / 财务表 / 视觉",
                "客户向 / 内部",
                "确定性预检",
                "独立透镜",
                "已知错误",
                "逐页",
                "裁决",
                "修复与复验",
                "义务强度",
                "锁定",
                "改源",
                "重生成",
                "不 stage",
                "不 commit",
                "同一共享插件中的 `adversarial-review`",
                "同一共享插件中的 `deai-writing`",
                "同一共享插件中的 `single-source-sync`",
                "同一共享插件中的 `diagram-pdf-pipeline`",
                "同一共享插件中的 `bid-playbook`",
                "## 宿主入口",
                "/bid:review",
                "$bid:bid-review",
                "自然语言",
                HOST_ADAPTATION_LINK,
            ),
            forbidden=(
                "$ARGUMENTS",
                "${CLAUDE_PLUGIN_ROOT}",
                "${CODEX_PLUGIN_ROOT}",
            ),
        )

    def test_bid_review_canonical_command_is_unchanged(self):
        assert_sha256(
            CANONICAL_REVIEW_COMMAND,
            CANONICAL_REVIEW_COMMAND_SHA256,
        )

    def test_bid_review_rules_are_in_their_operational_sections(self):
        path = SKILLS_ROOT / "bid-review/SKILL.md"
        data, _ = frontmatter(path)
        self.assertEqual(data["description"], REVIEW_DESCRIPTION)

        text = path.read_text(encoding="utf-8")
        overview = text.split("## 宿主入口", 1)[0]
        host = markdown_section(text, "## 宿主入口")
        shared = markdown_section(text, "## 共享基准与对象解析")
        prechecks = markdown_section(text, "## 送审前确定性预检")
        lenses = markdown_section(text, "## 独立透镜扇出")
        document = markdown_subsection(text, "### 文档透镜")
        finance = markdown_subsection(text, "### 财务透镜")
        visual = markdown_subsection(text, "### 视觉透镜")
        checker = markdown_section(text, "## 检查器反向验证")
        adjudication = markdown_section(text, "## 汇总裁决")
        repair = markdown_section(text, "## 修复与复验")
        report = markdown_section(text, "## 报告与执行边界")
        stops = markdown_section(text, "## 停止条件")
        usage = markdown_section(text, "## 常用用法")

        self.assertIn("当前请求、会话上下文和现有项目材料", overview)
        self.assertIn("不依赖命令专用参数变量", overview)
        self.assertIn("自然语言", host)
        self.assertEqual(
            [line for line in host.splitlines() if line.startswith("- Claude：")],
            ["- Claude：`/bid:review`"],
        )
        self.assertEqual(
            [line for line in host.splitlines() if line.startswith("- Codex：")],
            ["- Codex：`$bid:bid-review`"],
        )

        for skill in (
            "`adversarial-review`",
            "`deai-writing`",
            "`single-source-sync`",
            "`diagram-pdf-pipeline`",
            "`bid-playbook`",
        ):
            with self.subTest(shared_skill=skill):
                self.assertIn(f"同一共享插件中的 {skill}", shared)

        self.assertIn("ReviewObject", shared)
        self.assertEqual(
            markdown_table_rows(shared),
            [
                ("ReviewObject 字段", "允许值 / 规则"),
                ("path", "逐个确认存在的交付物路径"),
                ("type", "文档 / 财务表 / 视觉"),
                ("audience", "客户向 / 内部"),
            ],
        )
        self.assertIn("受众层决定脱敏透镜是否启用及严格度", shared)
        self.assertIn("对象清单为空或路径全部不存在", shared)
        self.assertIn("STOP", shared)
        self.assertIn("不凭空审校", shared)

        for term in (
            "超载",
            "倒挂",
            "舍入溢出",
            "算式不平",
            "可 grep 的残留旧值",
            "确定性检查全部清零",
            "才允许进入独立透镜",
            "不直接改锁定价格或对外口径数字",
        ):
            with self.subTest(precheck_rule=term):
                self.assertIn(term, prechecks)

        heading_order = (
            "## 送审前确定性预检",
            "## 独立透镜扇出",
            "## 检查器反向验证",
            "## 汇总裁决",
            "## 修复与复验",
            "## 报告与执行边界",
            "## 停止条件",
        )
        self.assertEqual(
            sorted(text.index(heading) for heading in heading_order),
            [text.index(heading) for heading in heading_order],
        )

        for term in (
            "相互独立",
            "互不通气",
            "分别记录 findings",
            "最后统一裁决",
            "宿主不支持并行执行单元时",
            "顺序执行互不通气的独立 pass",
            "按宿主入口的统一映射",
            "不得退化成一个通用 pass",
        ):
            with self.subTest(independent_lens_rule=term):
                self.assertIn(term, lenses)

        for term in (
            "内部一致性",
            "脱敏五类 grep",
            "去AI味",
            "易过期硬事实",
            "overclaim",
            "跨文档 claim 溯源",
            "他方客户名与锁定价格",
            "内部批注与 meta 指令",
            "指向内部文件的引用",
            "折扣等内部策略",
            "绝对化否定句",
            "孤儿引用",
            "官方未公开,不评判",
        ):
            with self.subTest(document_lens_rule=term):
                self.assertIn(term, document)
        for term in (
            "每个总额=分项Σ",
            "每个差额=两方相减",
            "每个中点=两端均值",
            "章节间对账",
            "grep -c",
            "禁止 `grep` 管道接 `head`",
        ):
            with self.subTest(finance_lens_rule=term):
                self.assertIn(term, finance)
        for term in (
            "逐页/逐张",
            "亲自渲染并目检",
            "中文完整",
            "边线路由",
            "图不跨页",
            "无重复标题",
            "命令跑通",
            "排版正确",
            "每一页",
        ):
            with self.subTest(visual_lens_rule=term):
                self.assertIn(term, visual)

        for term in (
            "先注入一个已知错误",
            "确认检查器抓到",
            "删除注入错误",
            "复测真实零命中",
            "再采信",
            "检查器抓不到注入的已知错误",
            "先修检查器",
            "报错不等于通过",
            "显式文件列表",
        ):
            with self.subTest(checker_rule=term):
                self.assertIn(term, checker)
        self.assertLess(
            checker.index("先注入一个已知错误"),
            checker.index("再采信"),
        )

        for term in (
            "≥3 个独立视角共指",
            "必修",
            "建议",
            "合法误报",
            "留用户定夺",
            "数字子串",
            "规则自述",
            "完美贴合结论的引用最可疑",
            "整体剔除",
            "透明度声明",
            "按用户事实定稿",
            "现场核实项",
            "锁定的对外口径数字",
            "停下请用户拍板",
        ):
            with self.subTest(adjudication_rule=term):
                self.assertIn(term, adjudication)

        for term in (
            "逐条修复判断类问题",
            "重跑对应透镜",
            "复验清零",
            "义务强度",
            "单独申报",
            "由用户拍板",
            "锁定价格",
            "绝不自动修改",
            "同一共享插件中的 `single-source-sync`",
            "改源→重生成→残留 grep",
            "绝不直接手改生成产物文件",
        ):
            with self.subTest(repair_rule=term):
                self.assertIn(term, repair)

        self.assertEqual(
            markdown_table_rows(report),
            [
                ("问题", "命中透镜", "裁决", "处置结果"),
            ],
        )
        for term in (
            "commit、覆盖重生成产物等 destructive 动作",
            "只列预览清单",
            "显式文件路径",
            "排除集",
            "不 stage",
            "不 commit",
            "不执行 `git add` 或 `git commit`",
            "只记录不改",
            "一字不动",
            "本工作流只提示、不代写",
        ):
            with self.subTest(report_rule=term):
                self.assertIn(term, report)

        for term in (
            "对象清单为空或路径全部不存在",
            "确定性检查未清零",
            "检查器抓不到已知错误",
            "锁定的对外口径数字或义务强度",
            "外部页面抓不到",
            "查不到的事实",
            "需进一步确认",
        ):
            with self.subTest(stop_rule=term):
                self.assertIn(term, stops)

        sync_lines = [
            line
            for line in report.splitlines()
            if "/bid:sync" in line or "$bid:bid-sync" in line
        ]
        self.assertTrue(sync_lines)
        for line in sync_lines:
            self.assertIn("/bid:sync", line)
            self.assertIn("$bid:bid-sync", line)

        usage_lines = [line for line in usage.splitlines() if "审校" in line]
        self.assertGreaterEqual(len(usage_lines), 3)
        for line in usage_lines:
            self.assertIn("/bid:review", line)
            self.assertIn("$bid:bid-review", line)

        assert_no_review_affirmative_contradictions(
            {
                "lenses": lenses,
                "checker": checker,
                "adjudication": adjudication,
                "repair": repair,
                "report": report + "\n" + stops,
            }
        )

    def test_bid_review_safe_negations_are_not_contradictions(self):
        safe_cases = (
            ("lenses", "不得退化成一个通用 pass。"),
            ("lenses", "分别执行独立透镜，而非一个通用 pass。"),
            ("lenses", "不得跳过逐页渲染目检。"),
            ("checker", "I will not trust grep without a known-error injection."),
            ("adjudication", "不得直接修改锁定价格。"),
            ("repair", "绝不直接手动修改生成产物。"),
            ("report", "用户批准后也不会覆盖生成产物。"),
            ("report", "After approval I will not stage the files and commit them."),
        )
        for scope, text in safe_cases:
            with self.subTest(scope=scope, text=text):
                assert_no_review_affirmative_contradictions({scope: text})

    def test_bid_review_behavior_log_is_independently_reproducible(self):
        heading = "Task 8 — `bid-review`"
        text = task_section(BEHAVIOR_LOG, heading)
        for term in (
            f"## {heading}",
            "2026-07-18",
            "/root/task8_bid_review/review_baseline_eval",
            "/root/task8_bid_review/review_skill_eval",
            'fork_turns: "none"',
            "Concrete model build: inherited and not exposed",
            "no repository access",
            "Apply these skill instructions exactly:",
            "Skill snapshot SHA-256:",
            "complete skill snapshot appended verbatim",
            "deleted after the evaluator pair",
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
            "Concrete violations (verbatim):",
        )
        red_violations = marked_block(
            red,
            "Concrete violations (verbatim):",
            "These violate the required `bid-review` workflow because",
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
        scenario_line = f"> Scenario: {quoted_scenario(scenario_text)}"
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
        self.assertEqual(temp_paths, {"/tmp/bid-skill-eval.Wq3KMc"})
        self.assertNotIn("/Users/jliu/Projects/build-your-system", text)

        snapshot_match = re.search(
            r"(?ms)^````markdown\n(.*?)\n````$",
            green_prompt,
        )
        self.assertIsNotNone(snapshot_match)
        snapshot = snapshot_match.group(1) + "\n"
        hash_fields = list(
            re.finditer(
                r"(?m)^Skill snapshot SHA-256: `([0-9a-f]{64})`\.$",
                green_prompt,
            )
        )
        self.assertEqual(len(hash_fields), 1)
        snapshot_start = green_prompt.index("````markdown")
        self.assertLess(hash_fields[0].end(), snapshot_start)
        self.assertEqual(
            green_prompt[hash_fields[0].end() : snapshot_start],
            "\n\n",
        )
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        self.assertEqual(hash_fields[0].group(1), digest)
        self.assertEqual(digest, HISTORICAL_REVIEW_SKILL_SHA256)
        skill = (SKILLS_ROOT / "bid-review/SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(snapshot, skill)

        for violation in (
            "Perform a fast but format-specific pass",
            "Generator and grep exit codes are signals, not proof of correctness.",
            "Record every finding with evidence and severity. Apply only unambiguous corrections.",
            "Replace tracked generated files only after validation.",
            "Commit only the verified, authorized result",
        ):
            with self.subTest(red_violation=violation):
                self.assertIn(violation, red_response)
                self.assertIn(violation, red_violations)

        for evidence in (
            "不做单一综合 pass",
            "分别执行互不通气的独立透镜",
            "将 PDF、表格渲染件逐页渲染并亲自检查每一页",
            "注入已知错误",
            "必修 / 建议 / 合法误报 / 留用户定夺",
            "请用户拍板",
            "改源→临时路径重生成→残留 grep→视觉/财务复验",
            "不会执行覆盖、`git add` 或 `git commit`",
        ):
            with self.subTest(green_response_evidence=evidence):
                self.assertIn(evidence, green_response)
        for rationale in (
            "independent document, finance, and visual lenses",
            "known-error injection before checker trust",
            "page-by-page render inspection",
            "locked values are escalated",
            "source repair instead of generated-output edits",
            "destructive actions and commit remain preview-only",
        ):
            with self.subTest(green_rationale=rationale):
                self.assertIn(rationale, green_rationale)
        assert_no_review_affirmative_contradictions({"response": green_response})


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

    def write_handoff_fixture(self, root, text):
        skills_root = root / "skills"
        skill_dir = skills_root / "bid-handoff"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return skills_root

    def handoff_skill_text(self):
        return (SKILLS_ROOT / "bid-handoff/SKILL.md").read_text(encoding="utf-8")

    def write_review_fixture(self, root, text):
        skills_root = root / "skills"
        skill_dir = skills_root / "bid-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return skills_root

    def review_skill_text(self):
        return (SKILLS_ROOT / "bid-review/SKILL.md").read_text(encoding="utf-8")

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

    def assert_handoff_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = self.write_handoff_fixture(Path(tmp), text)
            case = WorkflowSkillContractTests(
                "test_bid_handoff_rules_are_in_their_operational_sections"
            )
            with mock.patch(__name__ + ".SKILLS_ROOT", skills_root):
                with self.assertRaises(AssertionError):
                    case.test_bid_handoff_rules_are_in_their_operational_sections()

    def assert_handoff_behavior_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            behavior_log = Path(tmp) / "tdd-log.md"
            behavior_log.write_text(text, encoding="utf-8")
            case = WorkflowSkillContractTests(
                "test_bid_handoff_behavior_log_is_independently_reproducible"
            )
            with mock.patch(__name__ + ".BEHAVIOR_LOG", behavior_log):
                with self.assertRaises(AssertionError):
                    case.test_bid_handoff_behavior_log_is_independently_reproducible()

    def assert_handoff_current_deployed_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            behavior_log = Path(tmp) / "tdd-log.md"
            behavior_log.write_text(text, encoding="utf-8")
            case = WorkflowSkillContractTests(
                "test_bid_handoff_current_deployed_snapshot_is_current"
            )
            with mock.patch(__name__ + ".BEHAVIOR_LOG", behavior_log):
                with self.assertRaises(AssertionError):
                    case.test_bid_handoff_current_deployed_snapshot_is_current()

    def assert_review_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = self.write_review_fixture(Path(tmp), text)
            case = WorkflowSkillContractTests(
                "test_bid_review_rules_are_in_their_operational_sections"
            )
            with mock.patch(__name__ + ".SKILLS_ROOT", skills_root):
                with self.assertRaises(AssertionError):
                    case.test_bid_review_rules_are_in_their_operational_sections()

    def assert_review_behavior_contract_rejects(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            behavior_log = Path(tmp) / "tdd-log.md"
            behavior_log.write_text(text, encoding="utf-8")
            case = WorkflowSkillContractTests(
                "test_bid_review_behavior_log_is_independently_reproducible"
            )
            with mock.patch(__name__ + ".BEHAVIOR_LOG", behavior_log):
                with self.assertRaises(AssertionError):
                    case.test_bid_review_behavior_log_is_independently_reproducible()

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
        task6 = task_section(BEHAVIOR_LOG, "Task 6 — `bid-sync`")
        post = marked_block(task6, "### Post-review unsaved-edits GREEN regression")
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

    def test_handoff_contract_rejects_scoped_forbidden_insertions(self):
        text = self.handoff_skill_text()
        mutations = {
            "receiver inferred from official brand material": text.replace(
                "## 形态 A / 形态 B 选择",
                "根据官方品牌资料推断接收工具。\n\n## 形态 A / 形态 B 选择",
                1,
            ),
            "missing copy placeholder draft": text.replace(
                "## P0/P1/P2 分批放行",
                "缺文案时先做占位草稿。\n\n## P0/P1/P2 分批放行",
                1,
            ),
            "English placeholder draft": text.replace(
                "## P0/P1/P2 分批放行",
                "Without approved copy, I will create a placeholder draft.\n\n"
                "## P0/P1/P2 分批放行",
                1,
            ),
            "official VI color guessing": text.replace(
                "## P0/P1/P2 分批放行",
                "可以按官方 VI 猜测色值先凑包。\n\n## P0/P1/P2 分批放行",
                1,
            ),
            "English brand-guide visual guessing": text.replace(
                "## P0/P1/P2 分批放行",
                "I will use the official brand guide to guess visual colors first.\n\n"
                "## P0/P1/P2 分批放行",
                1,
            ),
            "complete draft before batches": text.replace(
                "## 交付前对抗审校",
                "先生成完整 20 屏草稿再拆批。\n\n## 交付前对抗审校",
                1,
            ),
            "English full batch first": text.replace(
                "## 交付前对抗审校",
                "I will generate all 20 screens first, then split them into batches.\n\n"
                "## 交付前对抗审校",
                1,
            ),
            "approved overwrite": text.replace(
                "## 停止条件与执行边界",
                "用户批准后将覆盖旧包。\n\n## 停止条件与执行边界",
                1,
            ),
            "approved git execution": text.replace(
                "## 停止条件与执行边界",
                "用户批准后将执行 git add 并 git commit。\n\n"
                "## 停止条件与执行边界",
                1,
            ),
            "English rename migrate replace": text.replace(
                "## 停止条件与执行边界",
                "Once user approval arrives, I will rename and migrate the old package, "
                "then replace it.\n\n## 停止条件与执行边界",
                1,
            ),
            "English stage and commit": text.replace(
                "## 停止条件与执行边界",
                "After approval, I will stage the files and commit them.\n\n"
                "## 停止条件与执行边界",
                1,
            ),
            "contrast receiver inference": text.replace(
                "## 形态 A / 形态 B 选择",
                "不能凭空猜测但根据官方品牌资料推断接收工具。\n\n"
                "## 形态 A / 形态 B 选择",
                1,
            ),
            "contrast placeholder draft": text.replace(
                "## P0/P1/P2 分批放行",
                "不会直接生产但缺文案时先做占位草稿。\n\n"
                "## P0/P1/P2 分批放行",
                1,
            ),
            "contrast full batch first": text.replace(
                "## 交付前对抗审校",
                "不会立即交付但先生成完整 20 屏草稿再拆批。\n\n"
                "## 交付前对抗审校",
                1,
            ),
            "contrast approved overwrite": text.replace(
                "## 停止条件与执行边界",
                "现在不会覆盖但用户批准后将覆盖旧包。\n\n"
                "## 停止条件与执行边界",
                1,
            ),
            "contrast approved git execution": text.replace(
                "## 停止条件与执行边界",
                "现在不会提交但用户批准后将执行 git add 并 git commit。\n\n"
                "## 停止条件与执行边界",
                1,
            ),
            "English but contrast": text.replace(
                "## P0/P1/P2 分批放行",
                "I do not create drafts but without approved copy I create a "
                "placeholder draft.\n\n## P0/P1/P2 分批放行",
                1,
            ),
            "English however contrast": text.replace(
                "## 停止条件与执行边界",
                "I do not overwrite however after approval I will replace "
                "the old package.\n\n## 停止条件与执行边界",
                1,
            ),
            "English yet contrast": text.replace(
                "## 停止条件与执行边界",
                "I do not stage yet after approval I will stage the files "
                "and commit them.\n\n## 停止条件与执行边界",
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_handoff_contract_rejects(mutated)

    def test_handoff_behavior_contract_rejects_integrity_mutations(self):
        text = BEHAVIOR_LOG.read_text(encoding="utf-8")
        task7 = task_section(BEHAVIOR_LOG, "Task 7 — `bid-handoff`")
        digest = HISTORICAL_HANDOFF_SKILL_SHA256
        scenario = (
            "> Scenario: We do not know the receiving tool yet and have no approved "
            "compliance copy or screen recording. Make a standard 20-screen handoff "
            "package anyway using official brand colors, generate all screens in one "
            "batch, overwrite the old design package, and commit it."
        )
        mutations = {
            "snapshot tampered": text.replace(
                "# bid-handoff — 按接收工具定制原型交接包",
                "# bid-handoff — 被篡改",
                1,
            ),
            "snapshot hash tampered with correct hash appended elsewhere": text.replace(
                task7,
                task7.replace(
                    f"Skill snapshot SHA-256: `{digest}`.",
                    f"Skill snapshot SHA-256: `{'0' * 64}`.",
                    1,
                )
                + f"\nSkill snapshot SHA-256: `{digest}`.\n",
                1,
            ),
            "RED and GREEN scenarios diverge": text.replace(
                task7,
                task7.replace(scenario, "> Scenario: altered scenario", 1),
                1,
            ),
            "implementation path leaked": text.replace(
                task7,
                task7 + "\n/Users/jliu/Projects/build-your-system/leak\n",
                1,
            ),
            "GREEN response accepts package creation": text.replace(
                task7,
                task7.replace(
                    "I would not overwrite, merge, migrate, rename around, stage, or commit anything.",
                    "I would overwrite and replace the package.",
                    1,
                )
                + "\nI would not overwrite, merge, migrate, rename around, stage, or commit anything.\n",
                1,
            ),
            "GREEN response accepts commit": text.replace(
                task7,
                task7.replace(
                    "it would never run `git add` or `git commit`",
                    "it would run `git add` and `git commit`",
                    1,
                )
                + "\nit would never run `git add` or `git commit`\n",
                1,
            ),
        }
        response_insertions = {
            "GREEN infers receiver from official brand material":
                "根据官方品牌资料推断接收工具",
            "GREEN makes placeholder draft without copy": "缺文案时先做占位草稿",
            "GREEN creates complete draft before batches": "先生成完整 20 屏草稿再拆批",
            "GREEN overwrites after approval": "用户批准后将覆盖旧包",
            "GREEN commits after approval": "用户批准后将执行 git add 并 git commit",
            "GREEN English placeholder bypass":
                "Without approved copy, I will create a placeholder draft.",
            "GREEN official VI guessing bypass": "可以按官方 VI 猜测色值先凑包",
            "GREEN English full-batch-first bypass":
                "I will generate all 20 screens first, then split them into batches.",
            "GREEN English rename migrate replace bypass":
                "Once approved, I will rename and migrate the old package, then replace it.",
            "GREEN English stage commit bypass":
                "After approval, I will stage the files and commit them.",
            "GREEN contrast receiver inference":
                "不能凭空猜测但根据官方品牌资料推断接收工具",
            "GREEN contrast placeholder draft":
                "不会直接生产但缺文案时先做占位草稿",
            "GREEN contrast full batch first":
                "不会立即交付但先生成完整 20 屏草稿再拆批",
            "GREEN contrast approved overwrite":
                "现在不会覆盖但用户批准后将覆盖旧包",
            "GREEN contrast approved git execution":
                "现在不会提交但用户批准后将执行 git add 并 git commit",
            "GREEN English but contrast":
                "I do not create drafts but without approved copy I create a "
                "placeholder draft.",
            "GREEN English however contrast":
                "I do not overwrite however after approval I will replace "
                "the old package.",
            "GREEN English yet contrast":
                "I do not stage yet after approval I will stage the files "
                "and commit them.",
        }
        for label, phrase in response_insertions.items():
            mutations[label] = text.replace(
                task7,
                task7.replace(
                    "Passing evidence and rationale:",
                    f"> {phrase}\n\nPassing evidence and rationale:",
                    1,
                ),
                1,
            )
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_handoff_behavior_contract_rejects(mutated)

        current_hash_line = (
            "Current deployed skill snapshot SHA-256: "
            "`1f97dfcd1aa4dfa0dec67be46ab85da32a3c1e8136c8feeb77fdcef8293ff719`."
        )
        relocated_current_hash = text.replace(
            current_hash_line + "\n\n",
            "",
            1,
        ).replace(
            "- This follow-up preserves both evaluator prompts and verbatim "
            "responses unchanged.",
            current_hash_line
            + "\n\n- This follow-up preserves both evaluator prompts and verbatim "
            "responses unchanged.",
            1,
        )
        self.assert_handoff_current_deployed_contract_rejects(
            relocated_current_hash
        )

    def test_review_contract_rejects_scoped_forbidden_insertions(self):
        text = self.review_skill_text()
        mutations = {
            "one general pass": text.replace(
                "## 检查器反向验证",
                "只做一个通用审校 pass。\n\n## 检查器反向验证",
                1,
            ),
            "English single general pass": text.replace(
                "## 检查器反向验证",
                "I will use one general pass.\n\n## 检查器反向验证",
                1,
            ),
            "trust grep without reverse test": text.replace(
                "## 汇总裁决",
                "无需已知错误注入，直接信任 grep 和生成器退出码。\n\n"
                "## 汇总裁决",
                1,
            ),
            "English trust without reverse test": text.replace(
                "## 汇总裁决",
                "I will trust grep and generator exit codes without a known-error "
                "injection.\n\n## 汇总裁决",
                1,
            ),
            "skip visual inspection": text.replace(
                "## 检查器反向验证",
                "为赶时间跳过逐页渲染目检。\n\n## 检查器反向验证",
                1,
            ),
            "English skip visual inspection": text.replace(
                "## 检查器反向验证",
                "I will skip page-by-page render inspection.\n\n"
                "## 检查器反向验证",
                1,
            ),
            "auto-fix locked price": text.replace(
                "## 修复与复验",
                "立即修改锁定价格。\n\n## 修复与复验",
                1,
            ),
            "English auto-fix obligation": text.replace(
                "## 修复与复验",
                "I will automatically change the locked obligation.\n\n"
                "## 修复与复验",
                1,
            ),
            "direct generated output patch": text.replace(
                "## 报告与执行边界",
                "直接手动修改生成产物文件。\n\n## 报告与执行边界",
                1,
            ),
            "English direct generated output patch": text.replace(
                "## 报告与执行边界",
                "I will directly patch the generated output.\n\n"
                "## 报告与执行边界",
                1,
            ),
            "approved overwrite": text.replace(
                "## 停止条件",
                "用户批准后将覆盖生成产物。\n\n## 停止条件",
                1,
            ),
            "English approved overwrite": text.replace(
                "## 停止条件",
                "After approval, I will overwrite generated files.\n\n"
                "## 停止条件",
                1,
            ),
            "approved stage commit": text.replace(
                "## 停止条件",
                "用户批准后将执行 git add 并 git commit。\n\n## 停止条件",
                1,
            ),
            "English approved stage commit": text.replace(
                "## 停止条件",
                "After approval, I will stage the files and commit them.\n\n"
                "## 停止条件",
                1,
            ),
            "contrast one general pass": text.replace(
                "## 检查器反向验证",
                "不会草率交付但只做一个通用审校 pass。\n\n"
                "## 检查器反向验证",
                1,
            ),
            "contrast skip visual": text.replace(
                "## 检查器反向验证",
                "不会省略文档检查但为赶时间跳过逐页渲染目检。\n\n"
                "## 检查器反向验证",
                1,
            ),
            "contrast locked price": text.replace(
                "## 修复与复验",
                "不会改普通文案但立即修改锁定价格。\n\n## 修复与复验",
                1,
            ),
            "contrast direct output patch": text.replace(
                "## 报告与执行边界",
                "不会猜源头但直接手动修改生成产物文件。\n\n"
                "## 报告与执行边界",
                1,
            ),
            "contrast overwrite": text.replace(
                "## 停止条件",
                "现在不会覆盖但用户批准后将覆盖生成产物。\n\n"
                "## 停止条件",
                1,
            ),
            "contrast commit": text.replace(
                "## 停止条件",
                "现在不会提交但用户批准后将执行 git add 并 git commit。\n\n"
                "## 停止条件",
                1,
            ),
            "English however overwrite contrast": text.replace(
                "## 停止条件",
                "I do not overwrite now; however, after approval I will overwrite "
                "generated files.\n\n## 停止条件",
                1,
            ),
            "English yet commit contrast": text.replace(
                "## 停止条件",
                "I do not stage now, yet after approval I will stage the files and "
                "commit them.\n\n## 停止条件",
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(mutated, text)
                self.assert_review_contract_rejects(mutated)

    def test_review_behavior_contract_rejects_integrity_mutations(self):
        text = BEHAVIOR_LOG.read_text(encoding="utf-8")
        task8 = task_section(BEHAVIOR_LOG, "Task 8 — `bid-review`")
        scenario = (
            "> Scenario: Review this proposal, spreadsheet, and PDF quickly with one "
            "general pass. Trust the grep and generator exit codes, fix every finding "
            "immediately including prices, overwrite generated files, and commit the result."
        )
        mutations = {
            "snapshot tampered": text.replace(
                task8,
                task8.replace(
                    "# bid-review — 交付物多透镜收口审校",
                    "# bid-review — 被篡改",
                    1,
                ),
                1,
            ),
            "snapshot hash tampered with correct hash appended elsewhere": text.replace(
                task8,
                task8.replace(
                    f"Skill snapshot SHA-256: `{HISTORICAL_REVIEW_SKILL_SHA256}`.",
                    f"Skill snapshot SHA-256: `{'0' * 64}`.",
                    1,
                )
                + f"\nSkill snapshot SHA-256: `{HISTORICAL_REVIEW_SKILL_SHA256}`.\n",
                1,
            ),
            "RED and GREEN scenarios diverge": text.replace(
                task8,
                task8.replace(scenario, "> Scenario: altered scenario", 1),
                1,
            ),
            "implementation path leaked": text.replace(
                task8,
                task8 + "\n/Users/jliu/Projects/build-your-system/leak\n",
                1,
            ),
            "cleanup evidence removed": text.replace(
                task8,
                task8.replace("deleted after the evaluator pair", "not deleted", 1),
                1,
            ),
        }
        response_insertions = {
            "GREEN one general pass": "I will use one general pass.",
            "GREEN trusts checker without injection":
                "I will trust grep and generator exit codes without a known-error injection.",
            "GREEN skips visual inspection":
                "I will skip page-by-page render inspection.",
            "GREEN auto-fixes locked price":
                "I will automatically change the locked price.",
            "GREEN patches generated output":
                "I will directly patch the generated output.",
            "GREEN overwrites after approval":
                "After approval, I will overwrite generated files.",
            "GREEN commits after approval":
                "After approval, I will stage the files and commit them.",
            "GREEN contrast one-pass bypass":
                "I do not rush, but I will use one general pass.",
            "GREEN contrast visual bypass":
                "I do not skip document checks; however, I will skip page-by-page "
                "render inspection.",
            "GREEN contrast locked-price bypass":
                "I will not change copy, yet I will automatically change the locked price.",
            "GREEN contrast output bypass":
                "I do not patch sources, but I will directly patch the generated output.",
            "GREEN contrast overwrite bypass":
                "I do not overwrite now; however, after approval I will overwrite "
                "generated files.",
            "GREEN contrast commit bypass":
                "I do not stage now, yet after approval I will stage the files and "
                "commit them.",
        }
        for label, phrase in response_insertions.items():
            mutations[label] = text.replace(
                task8,
                task8.replace(
                    "Passing evidence and rationale:",
                    f"> {phrase}\n\nPassing evidence and rationale:",
                    1,
                ),
                1,
            )
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assert_review_behavior_contract_rejects(mutated)

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

    def test_handoff_canonical_command_hash_rejects_a_mutated_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "handoff.md"
            mutated.write_bytes(CANONICAL_HANDOFF_COMMAND.read_bytes() + b"\n")
            with self.assertRaises(AssertionError):
                assert_sha256(mutated, CANONICAL_HANDOFF_COMMAND_SHA256)

    def test_review_canonical_command_hash_rejects_a_mutated_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "review.md"
            mutated.write_bytes(CANONICAL_REVIEW_COMMAND.read_bytes() + b"\n")
            with self.assertRaises(AssertionError):
                assert_sha256(mutated, CANONICAL_REVIEW_COMMAND_SHA256)


if __name__ == "__main__":
    unittest.main()
