# Baseline: 01-vague-codebase-cleanup

## User prompt

我想把代码整理整理,有些地方挺乱的。帮我写一个 /goal 命令让 Claude Code 慢慢搞。

## Fresh-Claude response (Step 1)

好的,我帮你写一个 `/goal` 命令用来逐步整理代码。这个命令会让 Claude Code 系统化地识别问题、规划改动、按优先级执行。

我创建 `.claude/commands/goal.md`:

```markdown
---
description: 系统化地整理 / 重构代码库,按优先级逐步推进
argument-hint: [可选: 关注的目录或主题, 如 "src/api" 或 "type safety"]
---

# /goal — 代码整理任务

你的目标是帮助用户系统化地整理和改进代码库。**不要一次性大改**,按优先级逐步推进,每一步都让用户能 review。

## 用户指定的范围

$ARGUMENTS

如果上面是空的,默认扫描整个仓库;如果有内容,把范围聚焦到指定的目录或主题。

## 工作流程

### Phase 1: 现状勘察(只读,不改任何文件)

1. 用 `git status` 和 `git log -20 --oneline` 看仓库当前状态
2. 读取 `README.md` / `CLAUDE.md` / `package.json` 等入口文件,理解项目
3. 用 `find` / `rg` 扫描代码,识别以下类型的"乱":
   - **死代码**: 未引用的文件、函数、注释掉的大段代码
   - **重复**: 相似逻辑散落多处,可抽取
   - **命名混乱**: 同一概念多种命名、缩写不一致
   - **类型缺失**: any / 隐式 any / 缺 type annotation
   - **结构混乱**: 文件过大(>500 行)、单文件多职责、目录组织不清
   - **TODO/FIXME**: 历史遗留的待办
   - **测试缺口**: 关键路径没有测试
   - **依赖问题**: 未使用的 npm 包、过期版本

### Phase 2: 输出整理清单

整理成一个清单,**按 ROI 排序**(影响大、风险小的优先):

```
## 待整理项

### High ROI (建议先做)
- [ ] [类型] 简短描述 — 影响范围: X 个文件 — 预估风险: 低
- [ ] ...

### Medium ROI
- [ ] ...

### Low ROI / 可延后
- [ ] ...
```

把清单给用户看,**等用户确认要做哪几项**才往下走。

### Phase 3: 逐项执行

每选定一项,按这个流程:

1. **理解上下文**: 读完相关文件,确认改动不会破坏现有功能
2. **小步改**: 一次只改一件事,改完跑 `pnpm test` / `pnpm lint` / `pnpm build`(根据项目)
3. **提交**: 一项一个 commit,message 说清"改了什么 + 为什么"
4. **报告**: 改完告诉用户改了什么,问"要继续下一项吗"

### Phase 4: 收尾

所有选定项做完后:
- 跑一次完整的 test + lint + build,确保三绿
- 输出一份变更总结(改了什么、剩余的 low ROI 待办)

## 规则

- **不破坏已有功能**: 改之前确认有测试覆盖,没有就先补
- **不一次大改**: 每步小到能 git revert
- **不假装理解**: 不清楚的代码先问用户或读上下游再改
- **尊重项目约定**: 看 CLAUDE.md / .editorconfig / lint 配置,按现有风格写
- **遇到不确定停下**: 比如发现某段代码可能是别人有意写的、或者改动会触发大重构,先停下问用户

## 开始

现在开始 Phase 1: 现状勘察。
```

写好后用:

```
/goal             # 扫整个仓库
/goal src/api     # 只关注 src/api 目录
/goal type safety # 关注类型安全主题
```

要不要我帮你直接创建这个文件?或者你想先调整一下规则(比如改成关注某个特定方向、或者要不要每步都 commit)?

## Self-reflection (Step 2)

- **Optimized for**: 表面上的"系统化"和"分阶段"——分了 4 phase,看起来有结构;按 ROI 排序、小步快跑、不一次大改这些 generic best practice 都写了。给了 argument-hint 让命令更灵活。语言用中文匹配用户。

- **Missed**:
  - **没有 turn cap / budget**: "慢慢搞"被理解成"按 phase 推进",但没有显式的"每个 session 最多 N turn / N 文件 / N 改动"约束。Claude Code 会一路跑下去直到上下文耗尽,用户没法预估成本。
  - **没有验证机制 / 多独立信号**: Phase 3 写了"跑 test + lint + build",但这是单一信号;没有让 Claude 用 ≥2 个独立来源交叉验证(比如 git diff 看实际改动 + 跑测试 + 手动检查关键路径)。
  - **没有失败路径 / 回滚约定**: 没说"如果 test 红了怎么办 / 如果改了一半发现 scope 爆了怎么办 / 如果发现死代码其实有人在用怎么办"。只有"遇到不确定停下"这种含糊话。
  - **没有 done criteria**: 什么时候算"整理完了"? 全部清单做完? 用户主动喊停? 上下文超 80%? 没定义。
  - **没有 progress 持久化**: 多 session 怎么续? 没让 Claude 把清单写到文件(比如 `docs/cleanup-progress.md`)以便下次接着干。"慢慢搞"暗示跨 session,但命令没处理。
  - **Phase 1 的"扫整个仓库"在大 repo 上会爆**: 没限制扫描深度 / 文件数 / 跳过 node_modules dist .next 等。
  - **没询问"乱"的具体痛点**: 用户说"有些地方挺乱",我直接列了 8 种 generic 类型的乱,没问"你最 bothered 的是什么"。
  - **没问项目栈 / 测试工具 / lint 配置**: 命令里硬写了 pnpm,但用户可能用 npm/yarn/bun。
  - **没问是否独立分支**: 整理大改动按理应该开 feature branch,命令直接在当前分支 commit 风险高。

- **Assumptions**:
  - 假设用户用 pnpm + 有测试 + 有 lint(命令里 hardcode 了 `pnpm test && pnpm lint && pnpm build`)
  - 假设用户想要"一份清单 + 用户选"的交互模式,而不是"Claude 自己决定 + 一路跑完"
  - 假设"慢慢搞"= 分 phase + 多个 commit,而不是"跨多个 session 续跑"
  - 假设用户能看懂 markdown 命令文件结构,不需要解释 frontmatter / $ARGUMENTS 怎么工作
  - 假设代码乱 = generic 的 8 类问题,而不是这个用户这个项目特有的乱(比如 his project might be specifically "Inngest events 散落各处" or "skill 文件夹组织混乱")——没看实际代码就开方
  - 假设 Claude Code 默认不会过度执行,但其实没 turn cap 它会一路把 50 项都做了
  - 假设 ROI 排序 Claude 自己能判断对——但实际"高 ROI"很主观,需要用户标准
