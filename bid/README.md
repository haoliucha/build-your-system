# bid — To-B 投标/交付物项目方法论

`bid` 是一套同时支持 Claude Code 与 Codex 的 To-B 投标、售前和交付物工作流。它把方案、报价、排期、图表、PDF 和原型视为同一条可复核的生产线：数字、标签和关键措辞只存放在“数据文件 + `build/` 生成器”这一单一真源中，xlsx/PDF/HTML/图等文件都是可重生成产物。一次口径变更必须从源头级联到所有消费端，再做残留检查与交付前审校，避免手改产物造成多份口径漂移。

方法论来自一个真实 To-B 投标项目的 9 个 AI-coding 全周期会话（318 条经验、16 个经验域）；案例已化名重构，示例数字均为教学虚构值。完整导读和可播放的流水线动画见 [docs/bid-methodology.html](docs/bid-methodology.html)。

## 安装

### Claude Code

在 Claude Code 中打开 `/plugin`，进入 marketplace `build-your-system`，安装 `bid`。安装后可使用六个流程命令：

- `/bid:init`
- `/bid:meeting`
- `/bid:sync`
- `/bid:review`
- `/bid:handoff`
- `/bid:status`

### Codex 首次本地安装

令 `REPO_ROOT` 指向已经集成目标提交的 `build-your-system` checkout，再从仓库中的 `bid` 目录安装：

```bash
REPO_ROOT="/path/to/build-your-system"
cd "$REPO_ROOT/bid"
zsh scripts/install-codex-local.sh
```

安装脚本先完整预检 `~/.agents/plugins/marketplace.json`：文件必须是普通文件、JSON 结构有效、`name` 必须精确等于 `local-build-your-system`，已有 `bid` 条目也必须与本插件定义完全一致。预检通过后才会建立 `~/plugins/bid` 到当前 `"$REPO_ROOT/bid"` 的符号链接、登记 marketplace，并运行 `codex plugin add bid@local-build-your-system`。如果 Codex CLI 安装失败，脚本只回滚本次创建的链接和 marketplace 改动；既有 marketplace 会恢复原始字节和权限，其他条目不受影响。安装完成后请新建一个 Codex 任务，让技能索引从新安装版本加载。

## 六个共享工作流

Claude Code 使用 slash command；Codex 可显式调用对应 skill。两边执行的是同一份业务流程、护栏与停止条件，也都可以直接用自然语言触发。

| 流程 | Claude Code | Codex | 自然语言示例 |
|---|---|---|---|
| 立项 | `/bid:init <项目名>` | `$bid:bid-init <项目名>` | “初始化某项目投标工作区” |
| 会议 | `/bid:meeting [会议日期或纪要文件] [--prep]` | `$bid:bid-meeting [会议日期或纪要文件] [--prep]` | “归档今天的会议纪要并提取口径变化”；“为下周客户会生成会前准备包” |
| 口径同步 | `/bid:sync [口径变更描述]` | `$bid:bid-sync [口径变更描述]` | “把旧金额替换成新金额并同步所有交付物” |
| 交付审校 | `/bid:review` | `$bid:bid-review` | “交付前多透镜审校方案和报价表” |
| 原型交接 | `/bid:handoff [接收工具名] [原型范围]` | `$bid:bid-handoff [接收工具名] [原型范围]` | “给 AI 设计工具准备原型交接包” |
| 状态速查 | `/bid:status` | `$bid:bid-status` | “查一下当前对客口径和红线” |

例如，在 Claude Code 中可输入：

```text
/bid:meeting 2026-07-21 --prep
```

在 Codex 中对应输入：

```text
$bid:bid-meeting 2026-07-21 --prep
```

不记命令也没有关系。“新会话先给我锁定口径和遗留待办”“重生成后检查全库旧口径残留”这类明确请求会触发相应工作流。

## 十个领域 skills

十个领域 skill 是方法论模块，可被六个流程工作流组合调用。Claude Code 和 Codex 都支持自然语言触发；Codex 需要强制指定时可使用表中的显式调用。

| skill | 解决什么问题 | 触发示例 | Codex 显式调用 |
|---|---|---|---|
| `bid-playbook` | 目录、编号、执行节奏、合规红线与全流程路由 | “投标项目怎么推进？” | `$bid:bid-playbook` |
| `single-source-sync` | 单一真源、手改回捕、七步口径级联与提交纪律 | “我手改了表格，回捕生成器并同步所有交付物” | `$bid:single-source-sync` |
| `bid-costing` | 价格阶梯、依据分层、成本区间与可辩护测算 | “这个成本数字怎么来的？” | `$bid:bid-costing` |
| `bid-scheduling` | PERT、资源平衡、依赖倒挂与利用率口径 | “做投标排期并检查依赖倒挂” | `$bid:bid-scheduling` |
| `adversarial-review` | 独立多透镜审校、检查器反向验证与统一裁决 | “红队一下这份方案” | `$bid:adversarial-review` |
| `deai-writing` | 18 类硬指标扫描、语义净口径与零信息损失改写 | “扫一下这份方案的 AI 味” | `$bid:deai-writing` |
| `diagram-pdf-pipeline` | 图表生成、中文 PDF、书签与逐页验收 | “导出中文 PDF 并加书签大纲” | `$bid:diagram-pdf-pipeline` |
| `prototype-handoff` | 接收工具输入模型、视觉取样与 P0/P1/P2 分批交接 | “给设计工具准备原型交接包” | `$bid:prototype-handoff` |
| `bid-research` | 竞品实证、录屏拆解、license 审查与证据链 | “做竞品调研和开源 license 审查” | `$bid:bid-research` |
| `presales-tactics` | 体量摸底、三档锚定、砍价预案与谈判红线 | “做三档报价和砍价预案” | `$bid:presales-tactics` |

## 推荐生命周期

一条典型项目链路如下：

1. `init`：判定新线索、成单或重组状态，建立客户向/内部双层目录、生成器骨架、P0 问题清单和正式项目 memory。
2. `meeting`：会前用 `--prep` 生成内部准备包；会后归档候选纪要并把定案口径追加到 memory。
3. `sync`：口径变化时按“写句柄检查 → 手改回捕 → 重生成 → 内容抽验 → 残留检查 → memory → 提交预览”固定顺序级联。
4. `review`：冻结本轮交付物，分别执行文档、财务和视觉透镜，再统一裁决与复验。
5. `handoff`：先确认接收工具的输入模型，再按 P0/P1/P2 批次组装和放行原型交接包。

`status` 不属于单向阶段，任何时点都可调用；特别适合改数前、回复客户前、交付前和新任务接手时做只读口径、红线、遗留待办与漂移速查。

## 双宿主共享 memory

项目状态统一保存在项目内 `.claude/memory/`，不会因为换宿主再建一套目录。Claude Code 沿用既有 memory 机制；Codex 必须在相关工作流中显式读取和写入 `.claude/memory/`。因此同一个项目可在两个宿主之间接续，且锁定口径、废弃口径、会议决策和未决事项仍有同一份可审计记录。

新线索阶段默认不初始化正式 memory；成单、转正或确认重组后才建立。已有主题文件和索引不得静默覆盖，只能预览新增内容或追加更正记录。

## 附带的八个脚本

bundled 脚本一律相对于拥有它的 `SKILL.md` 解析，不依赖当前工作目录，也不要假设某个 Claude/Codex 专用插件根变量。

| 脚本（相对 `skills/`） | 用途 | 依赖与可选行为 |
|---|---|---|
| `adversarial-review/scripts/check-residuals.sh` | 残留词/敏感词扫描和已知脏词 selftest | Bash、`grep`、`sed`、`mktemp`；兼容 macOS BSD 工具 |
| `bid-costing/scripts/discount-check.cjs` | 反算折扣标签的隐含列表价并互证 | Node.js；无第三方模块 |
| `bid-research/scripts/extract-frames.sh` | 固定节奏抽帧并生成编号 contact sheet | `ffmpeg`、ImageMagick 7 的 `magick`；macOS 自动探测系统字体，也可传 `FONT=/path/to/font` |
| `bid-scheduling/scripts/level.cjs` | PERT + 依赖拓扑资源平衡与机器校验 | Node.js；无第三方模块；支持 `--selftest` |
| `deai-writing/scripts/aiflavor-scan.cjs` | 扫描 18 类中文 AI 写作痕迹并可输出 JSON | Node.js；无第三方模块 |
| `diagram-pdf-pipeline/scripts/add-outline.cjs` | 用系统 Chrome 把 HTML 导出为 tagged、带 outline 的 PDF | Node.js 18+、`playwright-core`、本机 Chrome；缺依赖时只有该能力不可用 |
| `prototype-handoff/scripts/extract-frames.sh` | 抽帧、contact sheet 和像素 hex 取样 | `ffmpeg`、ImageMagick 7 的 `magick`/`montage`；macOS 自动探测系统字体，也可传 `FONT` |
| `single-source-sync/scripts/xlsx-dump.cjs` | 把 xlsx 逐格导出为稳定逻辑值，供手改 diff | `exceljs`；可就地安装或用 `NODE_PATH` 指向已有 `node_modules` |

macOS 可用 Homebrew 安装媒体依赖：

```bash
brew install ffmpeg imagemagick
```

需要 PDF 或 xlsx 辅助能力时，再按需安装 `playwright-core` 或 `exceljs`。缺少这些可选依赖不会阻止其他 skills 和零依赖脚本工作。`add-outline.cjs` 使用系统 Chrome；macOS 正向测试要求 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` 和可解析的 `playwright-core` 同时存在。中文 PDF 要使用 CJK-first 字体栈，导出后必须实际打开检查书签、字体和关键页，不能只看命令零退出。建议在具备这两项依赖的可选 macOS CI job 中覆盖 PDF 正向路径；依赖缺失时测试会明确跳过，跳过结果不能作为 outline 语义已经验证的发布证据。

## Codex 本地更新

本集成批准的基础版本是 `0.1.0`，不为本地重装另行提升语义版本。开发期更新由 plugin-creator cachebuster 在 `0.1.0` 后增加 Codex build metadata，例如 `0.1.0+codex.local-20260719-103000`。

本地源码改动后，Codex 已安装缓存不会自动刷新。请在有意用于本次更新的分支或 worktree 中操作，不要在不准备提交的 checkout 上执行 helper，也不要手改 marketplace 或 Codex 配置。先设置仓库与 plugin-creator 根目录，再更新唯一 cachebuster：

```bash
REPO_ROOT="/path/to/build-your-system"
PLUGIN_CREATOR_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator"

python3 "$PLUGIN_CREATOR_ROOT/scripts/update_plugin_cachebuster.py" \
  "$REPO_ROOT/bid" \
  --cachebuster local-YYYYMMDD-HHMMSS
```

把 `YYYYMMDD-HHMMSS` 换成这次更新的时间令牌。helper 会直接重写受 Git 跟踪的 `bid/.codex-plugin/plugin.json`：保留 `+` 前的 `0.1.0` 基础版本，并把旧 suffix 替换成单个 `+codex.<cachebuster>`，不会不断叠加 suffix。随后检查实际 diff 和暂存范围：

```bash
git -C "$REPO_ROOT" diff -- bid/.codex-plugin/plugin.json
git -C "$REPO_ROOT" status --short
```

确认 cachebuster manifest 改动与本次发布文件属于同一更新后，把它们一起显式暂存、评审并提交。提交完成后再重装：

```bash
codex plugin add bid@local-build-your-system
```

最后必须新建一个 Codex 任务；现有任务不会重新加载新的 skill 索引。不要用删除缓存、重写 marketplace 或清理整个插件目录来代替这份更新合同。

## 卸载 Codex 本地安装

卸载必须从同一个源码 checkout 调用受测试的事务模式：

```bash
REPO_ROOT="/path/to/build-your-system"
cd "$REPO_ROOT/bid"
zsh scripts/install-codex-local.sh --uninstall
```

脚本会先验证 marketplace 名称、精确 `bid` 条目和 `~/plugins/bid` 的实际目标，再调用底层 `codex plugin remove bid@local-build-your-system`。这条 Codex 命令会删除 Codex 自己管理的已安装配置与缓存；这是卸载的预期行为。它不会删除源码 checkout、Claude 状态、项目内 `.claude/memory/`，也不会改动无关的 marketplace 条目。

如果 Codex CLI 移除失败，marketplace 与链接保持原样；成功后脚本才原子移除单个 `bid` 条目并 unlink 这个精确链接，保留其他 marketplace key、插件及顺序。若后续 marketplace 写入或 unlink 失败，脚本会尽力恢复本地字节、权限和链接，并执行 `codex plugin add bid@local-build-your-system` 恢复 Codex 已安装状态；该次卸载仍以非零状态退出。若补偿安装也失败，错误信息会给出精确恢复命令以及 marketplace、源码链接和源码 checkout 路径，不会宣称卸载成功。若本地条目和链接都已不存在，脚本给出明确的 already absent 消息并幂等退出；遇到残缺状态、并发修改或错误目标则停止，不做猜测性清理或覆盖。

## 安全边界

- **不静默覆盖**：已有目录、文件、符号链接或 marketplace 条目冲突时停止，先展示差异和目标；生成产物覆盖前也要确认真源与写句柄状态。
- **不自动提交**：工作流只给出分组提交预览或建议命令，不替用户静默执行 `git add` / `git commit`；需要提交时只列本任务的显式路径。
- **不伪造合规结论**：数据授权是第 0 步；未知授权、法定角色或客户事实保持“待确认”，不能用看似完整的合规措辞代替证据。
- **不伪造证据**：链接打不开、自动化受阻或 license 继承链不清时明确标注限制，转人工取证或安全降级，不生成不存在的截图、测试结果或出处。
- **不伪造数字**：报价、成本、排期和容量必须有真源、算式与依据层级；缺官方价就标估算与置信度，不能为了目标数反调能力参数或编造精确值。
