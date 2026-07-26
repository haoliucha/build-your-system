# 终端远程贴图蓝图（dropimg）

> 解决：在终端里 SSH 到远端跑 tmux + Claude Code 时，**⌘V 粘不了图片**。

---

## 1. 根因：这不是 mosh 的问题

很多人以为是 mosh 把图片吃掉了。不是。

**PTY 是字符设备**，只传字节流。终端模拟器收到 `⌘V` 时，只会从系统剪贴板取
`public.utf8-plain-text` 类型；剪贴板里的 `public.png` / TIFF 二进制**根本没有通道可走**。

所以：

- 普通 `ssh -t` 贴不了图
- `mosh` 贴不了图
- 任何终端方案都贴不了图

**唯一解法**：图片走**带外通道**（out-of-band）落到远端文件系统，
终端里只流转一个**路径字符串**，让 Claude Code 按路径 attach。

```
┌──────────────┐                          ┌──────────────┐
│  本地 Mac    │   ①终端通道(PTY,字符)     │   远端主机   │
│              │ ───────────────────────► │              │
│  剪贴板:图片 │                          │  tmux        │
│              │   ②带外通道(SSH,二进制)   │  Claude Code │
│              │ ═══════════════════════► │  ~/Drops/    │
└──────────────┘                          └──────────────┘
        ▲                                        │
        └──────── ③回传绝对路径(文本) ────────────┘
              路径进本地剪贴板 → ⌘V → 走①进输入框
```

---

## 2. 数据流

```text
⌘⇧⌃4 截屏 → 图片进 NSPasteboard
  │
  │ 按全局快捷键（默认 Ctrl+Opt+V）
  ▼
Karabiner shell_command: AUTO_PASTE=1 ~/.local/bin/dropimg
  │
  ├─ pngpaste 取剪贴板图片（回退：AppleScript 解 file URL）
  ├─ base64 编码
  ├─ ssh user@host 'bash ~/bin/drop-image.sh'      ← 带外通道
  │     远端：解码 → file 检测 mime → 落盘 ~/Drops/<ts>.<ext> → 回显绝对路径
  ├─ 路径 pbcopy 回本机剪贴板（**不带尾随换行**）
  ├─ 等修饰键释放 + 等剪贴板就绪                    ← 关键，见第 4 节
  └─ 模拟 ⌘V 粘到前台窗口
  ▼
Claude Code 输入框出现 /home/user/Drops/20260727_000624.png（光标停在末尾）
```

---

## 3. 组件

| 位置 | 文件 | 作用 |
|------|------|------|
| 远端 | `~/bin/drop-image.sh` | stdin 读 base64 → 落盘 → 回显绝对路径 |
| 远端 | `com.dropimg.cleanup`（LaunchAgent / crontab） | 每周清理 7 天前的 Drops 文件 |
| 本地 | `~/.local/bin/dropimg` | 取剪贴板图 → 推送 → 路径回写剪贴板 → 自动 ⌘V |
| 本地 | `~/.config/dropimg/config` | `DROP_HOST` 等配置 |
| 本地 | `~/.config/karabiner/karabiner.json` | 全局快捷键 → 调 dropimg |

---

## 4. 五条关键设计取舍

> 改脚本时不要顺手"简化"掉这几条，每一条都是踩出来的。

### 4.1 所有外部命令写死绝对路径

Karabiner / 快捷键触发的是 **GUI 上下文**，PATH 被消毒成 `/usr/bin:/bin`。
`pngpaste` 装在 `/opt/homebrew/bin`（Apple Silicon）或 `/usr/local/bin`（Intel），
不写绝对路径必然 `command not found`，而且报错发生在 GUI 里，你看不到。

### 4.2 `pbcopy` 用 `printf '%s'` 而不是 `echo`

多一个尾随换行，⌘V 粘进 Claude Code 会**立刻提交**，来不及在路径后面补
"看这个图，帮我…"。去掉换行后光标停在路径末尾等你继续打字。

### 4.3 双路取图

- 截图（⌘⇧⌃4）时剪贴板是 PNG 二进制 → `pngpaste` 直接吃
- 从 Finder 复制**图片文件**时剪贴板是 file URL → `pngpaste` 失败，
  需要 AppleScript `«class furl»` 解出路径再读

### 4.4 远端用 `file --mime-type` 判类型，不信后缀

剪贴板可能给出 HEIC / WebP，盲目命名成 `.png` 会让下游读图失败。

### 4.5 自动粘贴必须**条件化等待**，不能直接发键

这是最容易翻车的一条。

**现象**：直接 `osascript -e 'tell application "System Events" to keystroke "v" using command down'`
经常静默失效，用户得再手动按一次 ⌘V。

**候选根因**（实测中未能 100% 锁定，但都属于"发得太早"这一类竞态）：

| 候选 | 机制 |
|------|------|
| 修饰键残留 | 触发快捷键的 ctrl/opt 还按着，合成的 cmd 与之叠加成 `Cmd+Ctrl+Opt+V`，目标应用没有这个绑定 → 静默丢弃 |
| 剪贴板未就绪 | `pbcopy` 刚写入，目标应用读到的还是旧内容（常常就是那张**图片**），⌘V 到终端等于什么都没发生 |
| 剪贴板管理器 | PasteEasy / Maccy 等介入 pasteboard，引入额外抖动 |

**解法**：不要用固定 `sleep`，而是**轮询到条件真正满足**再发键：

1. 条件一：`shift/ctrl/opt/cmd` 全部释放
2. 条件二：系统剪贴板的文本确实等于我们刚写入的那个路径

两个条件都满足（或超过 1.5s 预算）才发送。这样对上述任一根因都成立。

> [!warning] 海森堡陷阱
> 开发过程中出现过一次典型的观测者效应：把实现从 AppleScript 换成
> JXA + `ObjC.import("AppKit")` 后问题"自己好了"——因为加载 AppKit 让启动
> **慢了 48ms**，恰好躲过竞态窗口。
> **靠偶然延迟工作的代码，换台更快的机器就会复发。**
> 所以必须写成显式条件等待，而不是保留那个"碰巧慢一点"的实现。
>
> 相应地，所有等待逻辑都放在**一次** `osascript` 调用内完成 ——
> 拆成多次调用会各自引入 ~50ms 启动开销，等于又在偷偷加固定延迟。

---

## 5. 安装

```bash
bash <插件目录>/coding-anywhere/scripts/install-dropimg.sh <user@host>
```

安装器会：检查/安装 `pngpaste` → 验证免密 SSH → 装远端落盘脚本 →
装远端清理任务 → 装本地命令与配置 → 写 Karabiner 快捷键 → **推一张测试图自检**。

常用选项：

| 选项 | 说明 |
|------|------|
| `--key cmd+shift+i` | 换快捷键（默认 `ctrl+opt+v`） |
| `--no-karabiner` | 不配快捷键，只装命令 |
| `--no-cleanup` | 不装远端清理任务 |
| `--remote-dir '$HOME/img'` | 换远端落盘目录 |
| `--dry-run` | 只打印将要做什么 |

选快捷键时避开目标终端已占用的组合。iTerm2 里 `Cmd+Shift+V`（Paste Special）
和 `Cmd+Shift+D`（Split）都有用途，`Ctrl+Opt+V` 通常是空的。

---

## 6. 排查

| 现象 | 排查 |
|------|------|
| 按快捷键**完全没反应也没通知** | Karabiner IPC 失联（`invalid shared secret`），看 `/var/log/karabiner/core_service.log`，`launchctl kickstart -k gui/$(id -u)/org.pqrs.karabiner.karabiner_console_user_server` |
| 弹通知"路径已复制，请手动 ⌘V" | 自动粘贴被拦：系统设置 → 隐私与安全性 → **辅助功能**，勾上 Karabiner-Elements。不修也能用，手动 ⌘V 即可 |
| **需要按两次**（快捷键 + 手动 ⌘V） | 条件等待没生效或超时太短。在配置里打开 `DROPIMG_DEBUG_LOG`，看 `waitMods` / `clipOK` 两个字段 |
| `剪贴板里没有图片` | 剪贴板确实没图（常见：上一次 dropimg 已把它换成了路径），重新截图 |
| `SSH 推送失败` | `ssh -o BatchMode=yes user@host hostname` 单独测；远端睡眠 / 换 IP / 免密 key 失效都会命中 |
| Claude Code 不识别路径 | 确认是**绝对路径**；确认远端文件存在 `ssh user@host 'ls -la ~/Drops/'` |
| 路径粘进去**直接被提交了** | `pbcopy` 那行被改成了 `echo`（带尾随换行） |

调试日志：编辑 `~/.config/dropimg/config`，取消 `DROPIMG_DEBUG_LOG` 那行注释，
再看 `/tmp/dropimg-debug.log`：

```
[2026-07-27 00:06:24] rc=0 mods0=786432 waitMods=105ms clipOK=true waitClip=0ms frontmost=iTerm2 err=
```

- `mods0` 非 0 → 触发瞬间修饰键确实按着（`ctrl=262144 opt=524288 cmd=1048576 shift=131072`）
- `waitMods` → 为等修饰键释放实际等了多久
- `clipOK=false` → 剪贴板在预算内始终没变成目标路径，是条线索

---

## 7. 副作用与边界

- **剪贴板会被路径覆盖**：跑完后剪贴板里是路径不再是图片。想把同一张图再推一次
  需重新截图。这是刻意取舍，换来"粘完即用"。
- **客户端只支持 macOS**：依赖 `pngpaste` 与 `NSPasteboard`。
  远端 macOS / Linux 都支持。
- **需要免密 SSH**：先 `ssh-copy-id user@host`。
- **走公网时**把 `DROP_HOST` 指向你的中继入口即可（例如 ECS Relay 的
  `user@<relay-ip>`），链路与本地局域网一致。
