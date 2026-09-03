# 贡献指南

感谢你对 Personal Assistant Plugin 的关注！

## 开发环境

### 前置要求

- Claude Code CLI 或 Codex CLI（用于对应宿主的本地插件验证）
- Obsidian (可选，用于测试)
- Python 3.8+ (用于活动分析脚本)

### 本地开发：Claude Code

1. Clone 仓库
   ```bash
   git clone https://github.com/haoliucha/build-your-system.git
   cd build-your-system
   ```

2. 链接到 Claude 的本地插件目录
   ```bash
   ln -s "$(pwd)/assistant" "$HOME/plugins/assistant"
   ```

3. 在 Obsidian Vault 中测试
   ```bash
   cd /path/to/your/vault
   # Claude：/assistant:a-setup
   ```

### 本地开发：Codex

在仓库根目录运行安装脚本。脚本会把 `assistant/` 链接到 `~/plugins/assistant`，按 manifest 读取版本，刷新本地 marketplace 和 Codex cache。

```bash
cd /path/to/build-your-system
./assistant/scripts/install-local-plugin.sh
```

进入 Vault 后用自然语言触发同名 skill，例如“运行 a-setup”或“做一次 o-review”。

## 项目结构

```
assistant/
├── commands/          # 用户命令 (*.md)
├── skills/            # 知识库
├── hooks/             # 自动触发
├── scripts/           # Python/Bash 脚本
└── CONTRIBUTING.md    # 本文件
```

## 命令开发规范

### 文件命名

遵循 CODE+ 前缀：
- `c-*.md` — Capture 捕获
- `o-*.md` — Organize 组织
- `d-*.md` — Distill 提炼
- `e-*.md` — Express 输出
- `a-*.md` — Admin 管理

### 设计原则

1. **精简优先** — 命令只做宿主入口和参数透传
2. **明确交互点** — 需要用户确认的步骤由共享 skill 标出
3. **引用 Skill** — 详细规则放在 skills/ 中，命令中引用

## Skill 开发规范

### 文件结构

```
skills/
└── skill-name/
    ├── SKILL.md           # 主文件
    └── references/        # 参考资料
        └── *.md
```

### SKILL.md 格式

```markdown
---
name: Skill Name
description: 触发条件描述
---

# 技能内容
...
```

## Hook 开发规范

### 支持的事件

- `SessionStart` — 会话启动时
- `PreToolUse` — 工具调用前
- `PostToolUse` — 工具调用后

### 脚本规范

- 使用 Bash 或 Python
- 输出到 stdout 会成为 Claude 的上下文
- exit 0 表示成功，非 0 表示失败

## 提交规范

### Commit Message 格式

```
<type>(<scope>): <subject>

<body>
```

### Type

- `feat` — 新功能
- `fix` — Bug 修复
- `refactor` — 重构
- `docs` — 文档
- `chore` — 杂项

### 示例

```
feat(o-review): add activity timeline display

- 整合 cc-activity 数据到回顾视图
- 添加 MIT vs 实际投入对比
```

## Pull Request 流程

1. 确保本地测试通过
2. 更新相关文档
3. 创建 PR，描述改动内容
4. 等待 Review

## 问题反馈

- 使用 GitHub Issues 报告 Bug
- 提供复现步骤和错误信息
- 标注 Claude Code 版本

---

## 测试

```bash
python3 -m unittest discover -s assistant/tests -v
```

再次感谢你的贡献！
