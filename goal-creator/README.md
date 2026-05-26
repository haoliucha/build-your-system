# goal-creator

`/goal` 命令的提示词工程辅助 skill。通过引导式 brainstorm 把"模糊想法"转成"evaluator 能机械验证的 /goal 命令",并在当前 session 直接触发。

## 心智模型

`/goal` 在 Claude Code v2.1.139+ 是 session-scoped Stop hook。每 turn 后,一个独立的 evaluator 模型(默认 Haiku)读 transcript 判停。

关键约束:**evaluator 不能跑工具,只读 Claude 印出来的文字**。

所以好的 `/goal` 命令必须:
1. 用 grep / ls / count / exit code 等机械证据,而非主观判断
2. 强制 Claude 在最后一 turn 把验证命令的输出印到 transcript
3. 含 turn 上限、STATUS.md 失败路径、"do not ask for confirmation" 子句

`goal-creator` 是这套纪律的强制器。

## 用法

```
/goal-creator <一句话需求>
```

skill 会:
1. **Triage** — 判这个任务是否适合 /goal(主观判定 / 复合目标 / 缺关键信息 → 拒绝)
2. **Brainstorm** — 5-7 个问题(终态形态 / 验证信号 / scope 守卫 / 失败路径 / turn 上限 / 数据源 / 参考样本)
3. **Generate** — 生成符合 9 条规则的 /goal 文本
4. **Validate** — 9 项自检(turn cap / STATUS.md / 禁 confirm / 多信号 / 无主观词 / scope guard / 数据绑定 / final evidence block / ≤4000 字符)
5. **Decision log** — 写到 `docs/goal-prompts/<slug>.md`
6. **Confirm** — 给用户看终稿
7. **Invoke** — 用 SlashCommand 工具在当前 session 触发 /goal
8. **Exit** — 立即退场,不监控不干预

## 文件

```
goal-creator/
├── .claude-plugin/plugin.json    # 插件 manifest
├── skills/goal-creator/SKILL.md  # 主 skill 内容
├── samples.md                    # 7 个 published /goal 样本(含 source URL)
├── README.md                     # 本文件
└── tests/                        # 三 tier 测试
    ├── prompts/                  # 6 个 RED pressure 场景
    ├── baseline-results/         # RED 阶段证据(skill 不加载)
    ├── with-skill-results/       # GREEN 阶段证据(skill 加载)
    ├── baseline-summary.md       # 20 个 rationalization 归纳
    ├── green-summary.md          # 6/6 GREEN 验证报告
    ├── test-helpers.sh           # bash 断言函数
    └── run-content-tests.sh      # Tier 1 内容契约测试 (50 项)
```

## 测试

### Tier 1 · 内容契约(秒级)

```bash
bash goal-creator/tests/run-content-tests.sh
```

50 项 bash + grep 断言,验证 SKILL.md 和 samples.md 结构完整(章节、关键词、Forbidden Vocab、Rationalizations 表、source URL 数量等)。

### Tier 2/3 · 行为契约(手动,subagent)

`tests/prompts/` 下的 6 个 pressure 场景,用 subagent 加载/不加载 skill 分别跑,对比 `baseline-results/` 与 `with-skill-results/`。

详细方法见 `tests/README.md`。

## 开发方法论

本 skill 按 `superpowers:writing-skills` 的 TDD 流程开发:

- **RED**:6 个 pressure 场景跑 subagent baseline(skill 不加载),记录 20 个 rationalization
- **GREEN**:写 SKILL.md 显式 counter 这 20 个,再跑 6 个 with-skill,验证 6/6 PASS
- **REFACTOR**:无新 rationalization,无需改动
- **Tier 1**:50 项内容契约自动化测试

完整证据见 `tests/baseline-summary.md` 和 `tests/green-summary.md`。

## 前置要求

- Claude Code v2.1.139+ (`/goal` 命令引入)
- `SlashCommand:/goal:*` permission(若要自动触发,否则降级为人工 paste)
- workspace 已 trusted

## 限制

- 单 session 同时只能有 1 个 active `/goal`。skill 在 invoke 前会检查并提示 `/goal clear` 如有冲突
- evaluator 用 Haiku(small fast model),token 消耗忽略不计,但不擅长复杂语义判断
- 不适合主观质量任务(看起来好 / 高级感)、复合目标、需要运行才能判的任务 — skill 会主动拒绝并提议替代

## 版本

v0.1.0 — initial release, 测试覆盖率高但未经过大量真实 dogfood。
