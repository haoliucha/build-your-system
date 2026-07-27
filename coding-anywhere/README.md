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
- **终端里能"贴图"和传文件** — 截图/选文件 → 按一个快捷键 → 远端路径出现在 Claude Code 输入框（见下方 `dropfile`）

---

## 终端远程传图/传文件（dropfile）

远程写代码时最膈应的一件事：**想给 Claude Code 看一张截图或一份文件，
但终端里 `⌘V` 贴不了。**

这**不是 mosh 的锅**。PTY 是字符设备，终端收到 `⌘V` 时只取剪贴板的纯文本类型，
图片和文件引用都没有通道——普通 `ssh -t` 一样贴不了。

解法是让内容走 SSH **带外通道**落到远端 `~/Drops/`，终端里只流转一个路径字符串：

```
截图（⌘⇧⌃4） → 按 Ctrl+Opt+V → 路径出现在输入框 → 接着打字说明 → 回车
```

### 一键在线安装

**不需要先装插件，也不用填任何地址**——在你正连着远端的那台 Mac 上跑：

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/install-dropfile.sh | bash -s
```

目标主机**从你当前的 SSH 会话自动识别**：你的 `ssh user@host -t "tmux ..."`
命令行里就写着 `user@host`，安装器直接读它，并在开头打印出来确认。

认不出来（当前没开 ssh），或者要装到别的机器时，显式指定：

```bash
curl -fsSL <同上> | bash -s -- jliu@192.168.1.10
```

安装器会：取脚本（本地优先，否则按 `raw → jsDelivr → ghfast` 回退下载）→
检查依赖 → 验证免密 SSH → 装远端脚本与清理任务 → 装本地命令与配置 →
写 Karabiner 快捷键 → **推一个测试文件自检**。

> **访问不了 raw.githubusercontent.com**（没有代理）时，换 jsDelivr 镜像：
> `https://cdn.jsdelivr.net/gh/haoliucha/build-your-system@main/coding-anywhere/scripts/install-dropfile.sh`
>
> 只有最外层这条 curl 是单源的；安装器**内部**下载 `dropfile` / `drop-file.sh`
> 时本来就是 `raw → jsDelivr → ghfast` 三源回退，不受影响。

| 选项 | 说明 |
|------|------|
| `--key cmd+shift+i` | 换快捷键（默认 `ctrl+opt+v`） |
| `--iterm2` | 用 iTerm2 Coprocess（**装了 iTerm2 就是默认**） |
| `--karabiner` | 改用 Karabiner 全局快捷键 |
| `--no-hotkey` | 不配快捷键，只装 `dropfile` 命令 |
| `--no-cleanup` | 不装远端定期清理 |
| `--max-mb 50` | 改大小上限（默认 15MB） |
| `--dry-run` | 只打印将要做什么 |

### 快捷键怎么触发：默认走 iTerm2，不装 Karabiner

装了 iTerm2 的话，安装器默认用 **iTerm2 Coprocess**：不用装任何应用、
不用授予系统权限，而且**不模拟按键** —— 那一整类「按了没反应 / 要按两次」的
时序竞态从物理上就不存在。安装器会打印一段 GUI 配置步骤（约 30 秒，立即生效）。

需要在 iTerm2 之外也能按（比如从 Finder 复制文件后直接按）就加 `--karabiner`，
代价是装 Karabiner-Elements 并授予输入监控 + 辅助功能权限。

### 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/uninstall-dropfile.sh | bash -s
```

清掉本地命令、配置、Karabiner 规则和远端脚本。**远端 `~/Drops` 里的文件默认保留**
——那是你传过去的数据，要一并删得显式加 `--purge-drops`。
`--dry-run` 可先看会删什么，`--keep-remote` 只卸本地。

iTerm2 的 Coprocess 绑定是你在 GUI 里手动加的，脚本只检测并提示，不代删。

### 按了快捷键没反应？

在**你面前那台**（按键盘的、跑 iTerm2 的）机器上跑：

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/diagnose-dropfile.sh | bash
```

只读检查，会逐项告诉你卡在哪一环。最常见的三种：在远端机器上按的快捷键
（Karabiner 跑在本地）、本地没装 Karabiner-Elements、规则写进了未选中的 profile。

### 用法

```bash
dropfile                      # 剪贴板内容（Finder 复制的文件 或 截图）
dropfile report.pdf           # 指定文件
dropfile a.png b.zip c.md     # 多个文件，返回多行路径
DROPFILE_MAX_MB=50 dropfile big.zip    # 临时放宽上限
DROP_HOST=user@other dropfile foo.pdf  # 临时换目标机
```

从 Finder 复制文件时会**保留原文件名**；截图这种没有文件名的来源，
远端按 mime 类型生成后缀。图片和普通文件走同一条路，不需要单独的命令。

> 客户端需 macOS（依赖 `NSPasteboard` / `osascript`；`pngpaste` 只有截图这条来源需要），
> 远端 macOS 与 Linux 都支持。默认上限 15MB，客户端与远端两侧都会检查。
> 原理、六条设计取舍、四个 shell 坑与排查表见
> [`references/file-drop-blueprint.md`](skills/coding-anywhere/references/file-drop-blueprint.md)。

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
│       ├── file-drop-blueprint.md        # 终端远程传文件原理 + 设计取舍 + 排查
│       └── troubleshooting.md            # 10 类常见故障的排查清单
└── scripts/
    ├── install-dropfile.sh               # 在线一键安装器（推荐，含自检）
    ├── uninstall-dropfile.sh             # 卸载器（含旧版残留清理）
    ├── diagnose-dropfile.sh              # 自检：命令/配置/快捷键/远端连通性
    ├── dropfile                          # 客户端：取文件/剪贴板 → 推送 → 回填路径
    ├── drop-file.sh                      # 远端：解码 → 校验大小 → 落盘 → 回显路径
    └── ecs-forcecommand-forwarder.py     # 中继 ECS 的 ForceCommand 分流器（方案 A 用）
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
