# coding-anywhere

> 让你的 Mac 24/7 留在家里。你在哪里都能从手机/平板/任意笔记本回到它的 shell，回到上一秒离开的 tmux 会话。

一个 Claude Code 插件，把"自建 mosh + tmux + SSH 中继 + DDNS 直连"这套远程开发栈做成了**一段提示词**。复制 → 粘贴 → 让 Claude 引导你完成搭建。

---

## 这套方案能做到什么

- **网络切换不掉线** — 蜂窝 ↔ WiFi、地铁过隧道、高铁，连接一直在
- **App 关掉/电脑重启 session 还在** — tmux 会话持久化
- **不依赖 Tailscale/ZeroTier 的可用性** — 全部自建，路径短、延迟低
- **覆盖任何客户端** — iPhone Blink / iPad Termius / 桌面 mosh CLI / 朋友的 Linux 笔记本
- **两套架构按需切换** — ECS Relay（稳定，需公网 ECS）或 DDNS + IPv6 直连（最快，需家里有公网 IPv6）
- **终端里能"贴图"** — 截图 → 按一个快捷键 → 远端路径出现在 Claude Code 输入框（见下方 `dropimg`）

---

## 终端远程贴图（dropimg）

远程写代码时最膈应的一件事：**想给 Claude Code 看一张截图，但终端里 `⌘V` 贴不了图。**

这**不是 mosh 的锅**。PTY 是字符设备，终端收到 `⌘V` 时只取剪贴板的纯文本类型，
图片二进制根本没有通道——普通 `ssh -t` 一样贴不了。

解法是让图片走 SSH **带外通道**落到远端 `~/Drops/`，终端里只流转一个路径字符串：

```
截图（⌘⇧⌃4） → 按 Ctrl+Opt+V → 路径出现在输入框 → 接着打字说明 → 回车
```

**一键安装**（先装好插件）：

```bash
bash ~/.claude/plugins/marketplaces/build-your-system/coding-anywhere/scripts/install-dropimg.sh user@your-host
```

安装器会检查/安装 `pngpaste`、验证免密 SSH、装远端落盘脚本与清理任务、
装本地命令与配置、写 Karabiner 快捷键，最后**推一张测试图自检**。

| 选项 | 说明 |
|------|------|
| `--key cmd+shift+i` | 换快捷键（默认 `ctrl+opt+v`） |
| `--no-karabiner` | 不配快捷键，只装 `dropimg` 命令 |
| `--no-cleanup` | 不装远端定期清理 |
| `--dry-run` | 只打印将要做什么 |

装完也可以纯命令行用：`dropimg` 推送并把路径复制到剪贴板。

> 客户端需 macOS（依赖 `pngpaste` / `NSPasteboard`），远端 macOS 与 Linux 都支持。
> 原理、五条设计取舍与排查表见
> [`references/image-paste-blueprint.md`](skills/coding-anywhere/references/image-paste-blueprint.md)。

---

## 安装

### 方式 1：通过 Claude Code marketplace 安装

```
/plugin install coding-anywhere
```

（marketplace: `build-your-system`）

### 方式 2：手动安装

```bash
git clone https://github.com/haoliucha/build-your-system.git ~/.claude/plugins/marketplaces/build-your-system
# Claude Code 启动时会自动加载
```

---

## 一键复刻提示词（核心用法）

安装好插件后，把下面这段**整段复制**粘贴到 Claude Code 对话框里。Claude 会读取 `coding-anywhere` skill，自动引导你完成所有配置。

```
我想搭建一套"随时随地远程开发"的方案。

我的目标：从手机/平板/任意笔记本随时连回家里的 Mac，体验要和坐在电脑前一样：
- 网络切换不掉线
- App 关掉后会话还在
- 不依赖第三方 SaaS

请按照 coding-anywhere skill 的引导：
1. 先帮我评估环境（家里有没有公网 IPv6 / 是否有 ECS / 主用什么客户端）
2. 决定走 ECS Relay 还是 DDNS 直连方案
3. 一步一步带我完成配置（生成所有需要的脚本、配置文件、客户端配置）
4. 给我一份验收清单，让我能逐项验证

我的占位偏好：所有脚本和配置请用占位符（<your-xxx>），不要让我把真实 IP/域名贴进对话。
```

---

## 这个插件的内容

```
coding-anywhere/
├── skills/coding-anywhere/
│   ├── SKILL.md                          # 主方法论 + 决策树 + 引导式提问
│   └── references/
│       ├── ecs-relay-blueprint.md        # ECS 中继方案完整模板
│       ├── ddns-direct-blueprint.md      # DDNS + IPv6 直连完整模板
│       ├── client-config.md              # Blink / Termius / La Terminal / mosh CLI
│       ├── tmux-session-recipes.md       # tmux 持久会话配置
│       ├── image-paste-blueprint.md      # 终端远程贴图原理 + 设计取舍 + 排查
│       └── troubleshooting.md            # 9 类常见故障的排查清单
└── scripts/
    ├── install-dropimg.sh                # 贴图能力一键安装器（含自检）
    ├── dropimg                           # 客户端：取剪贴板图 → 推送 → 回填路径
    └── drop-image.sh                     # 远端：解码落盘 → 回显绝对路径
```

---

## 适合谁

- 经常出差/移动办公，又不想背 16 寸 MacBook 的开发者
- 想把家里 Mac mini 改造成"永远在线的开发服务器"的人
- Tailscale 等方案在国内偶发不稳，想要一套自建可控方案的人
- 钓鱼/爬山/咖啡馆是你的"灵感工位"的人

---

## 安全提醒

- 这套方案会在公网暴露 SSH 入口，请务必：
  - 关闭密码登录（只用 ssh key）
  - 给每个客户端单独生成 key
  - 给 ECS 装 fail2ban
  - **不要在公开帖子里暴露你真实的 ECS IP / 域名**

---

## 支持的运行环境

- **Claude Code**（macOS / Linux / Windows）
- **Codex**（适配版本见 `targets/codex/coding-anywhere/`）

---

## License

MIT
