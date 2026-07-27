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
- **终端里能"贴图"和传文件** — 截图/选文件 → 按一个快捷键 → 远端路径出现在 Claude Code 输入框（见文末 [dropfile](#附终端里传图传文件dropfile)）

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

## 两套架构

| | ECS Relay（方案 A） | DDNS + IPv6 直连（方案 B） |
|---|---|---|
| 前提 | 一台公网 ECS（约 ¥30/月） | 家里有公网 IPv6 或公网 IP |
| 路径 | Client → ECS → 家庭 Mac | Client → 家庭 Mac |
| 延迟 | 多一跳 | 最低 |
| 适用 | 家里在 NAT 后 / 要"任何网络都能连" | 家宽给了公网地址，且客户端所在网络支持 IPv6 |

两套都由 skill 引导生成完整配置，模板见
[`ecs-relay-blueprint.md`](skills/coding-anywhere/references/ecs-relay-blueprint.md) 和
[`ddns-direct-blueprint.md`](skills/coding-anywhere/references/ddns-direct-blueprint.md)。

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
│       └── troubleshooting.md            # 11 类常见故障的排查清单
└── scripts/
    ├── ecs-forcecommand-forwarder.py     # 中继 ECS 的 ForceCommand 分流器（方案 A 用）
    ├── install-dropfile.sh               # dropfile 在线一键安装器（含自检）
    ├── uninstall-dropfile.sh             # dropfile 卸载器（含旧版残留清理）
    ├── diagnose-dropfile.sh              # dropfile 自检：命令/配置/快捷键/远端连通性
    ├── dropfile                          # 客户端：取文件/剪贴板 → 推送 → 回填路径
    └── drop-file.sh                      # 远端：解码 → 校验大小 → 落盘 → 回显路径
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

## 附：终端里传图/传文件（dropfile）

> 这是上面那套远程开发栈的配套小工具，可以单独装、单独用。

远程写代码时想给 Claude Code 看一张截图或一份文件，终端里 `⌘V` 贴不了。
**这不是 mosh 的锅**：PTY 是字符设备，终端收到 `⌘V` 只取剪贴板的纯文本类型，
图片和文件引用都没有通道——普通 `ssh -t` 一样贴不了。

`dropfile` 让内容走 SSH **带外通道**落到远端 `~/Drops/`，终端里只流转一个路径字符串：

```
截图（⌘⇧⌃4） → 按 Ctrl+Opt+V → 路径出现在输入框 → 接着打字说明 → 回车
```

**不用先装插件，也不用填任何地址**——在你正连着远端的那台 Mac 上跑，
目标主机从当前 SSH 会话自动识别（安装器会打印出来让你确认）：

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/install-dropfile.sh | bash -s
```

```bash
dropfile                      # 剪贴板内容（Finder 复制的文件 或 截图）
dropfile report.pdf           # 指定文件
dropfile a.png b.zip c.md     # 多个文件，返回多行路径
```

从 Finder 复制文件时**保留原文件名**；截图这种没有文件名的来源，远端按 mime 生成后缀。
图片和普通文件走同一条命令。装了 iTerm2 就默认用 **Coprocess** 触发——不装应用、
不给系统权限、不模拟按键，那一整类"按了没反应/要按两次"的时序竞态从物理上不存在。

**按了没反应**——在你面前那台（按键盘的）机器上跑只读自检：

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/diagnose-dropfile.sh | bash
```

**卸载**（远端 `~/Drops` 里的文件默认保留，要一并删加 `--purge-drops`）：

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/uninstall-dropfile.sh | bash -s
```

- **访问不了 `raw.githubusercontent.com`** → 换 jsDelivr：
  `https://cdn.jsdelivr.net/gh/haoliucha/build-your-system@main/coding-anywhere/scripts/install-dropfile.sh`
  （只有最外层这条 curl 是单源的，安装器内部下载本来就是三源回退）

> 客户端需 macOS（依赖 `NSPasteboard` / `osascript`；`pngpaste` 只有截图这条来源需要），
> 远端 macOS 与 Linux 都支持。默认上限 15MB，客户端与远端两侧都会检查。
> 完整安装选项、两种触发方式对比、原理、六条设计取舍、四个 shell 坑与排查表见
> [`references/file-drop-blueprint.md`](skills/coding-anywhere/references/file-drop-blueprint.md)。

---

## 支持的运行环境

- **Claude Code**（macOS / Linux / Windows）
- **Codex**（适配版本见 `targets/codex/coding-anywhere/`）

---

## License

MIT
