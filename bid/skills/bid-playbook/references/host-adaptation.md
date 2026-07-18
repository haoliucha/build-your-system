# Claude Code / Codex 宿主适配

共享 skill 只描述业务方法与可验证结果；宿主负责把下面的动作映射到自身能力。

## 技能加载

- Claude Code 通过 skill 机制或 command wrapper 加载相应 skill。
- Codex 可按描述自动触发，或由用户显式调用 `$bid:<skill>`。

## 文件搜索、读取与编辑及 shell 执行

- 搜索、读取、编辑文件和执行 shell 都使用宿主原生能力，不在共享文档中绑定某一组工具名。
- Codex 搜索优先用 `rg`，文本补丁编辑优先用 `apply_patch`；其他宿主选择等价的原生操作。
- 对图片、PDF 等非纯文本产物，应实际打开并检查渲染结果，不能只凭命令零退出判定完成。

## 独立透镜与执行单元

- 需要独立透镜时，Claude Code 可用 Agent/Task，Codex 可用 multi-agent；每个执行单元保持独立简报、独立证据与独立 findings。
- 宿主不支持并行执行单元时，改为顺序执行相互独立的多轮检查；每轮隔离上一轮结论并分别记录 findings，最后再统一裁定。

## 用户输入

- 需要用户输入时使用宿主原生交互能力。只在会改变交付物形态、数字或业务前提的真实分叉暂停，并给出推荐选项；机械可推导步骤继续推进。

## 项目 memory

- 两个宿主都沿用项目内 `.claude/memory/`，不另建第二套目录。
- Claude Code 按既有机制使用该目录；Codex 必须显式读取和写入 `.claude/memory/`，确保口径决策跨会话延续。

## bundled 资源路径

- 脚本和 references 等 bundled 资源一律相对于拥有它们的 `SKILL.md` 所在目录解析。
- 先定位当前 `SKILL.md`，再拼接 `scripts/...` 或 `references/...`；绝不依赖插件根目录环境变量，也不依赖进程 CWD。
