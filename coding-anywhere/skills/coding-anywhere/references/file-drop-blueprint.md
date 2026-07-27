# 终端远程传文件蓝图（dropfile）

> 解决：在终端里 SSH 到远端跑 tmux + Claude Code 时，**⌘V 粘不了图、更传不了文件**。

---

## 1. 根因：这不是 mosh 的问题

很多人以为是 mosh 把图片吃掉了。不是。

**PTY 是字符设备**，只传字节流。终端模拟器收到 `⌘V` 时，只会从系统剪贴板取
`public.utf8-plain-text` 类型；剪贴板里的 `public.png` / 文件引用**根本没有通道可走**。

所以普通 `ssh -t` 贴不了、`mosh` 贴不了、任何终端方案都贴不了。

**唯一解法**：内容走**带外通道**（out-of-band）落到远端文件系统，
终端里只流转一个**路径字符串**，让 Claude Code 按路径读取。

```
┌──────────────┐                          ┌──────────────┐
│  本地 Mac    │   ①终端通道(PTY,字符)     │   远端主机   │
│              │ ───────────────────────► │              │
│ 剪贴板/文件  │                          │  tmux        │
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
截图 / 复制文件 / 指定路径
  │
  │ 按全局快捷键（默认 Ctrl+Opt+V），或直接 dropfile <文件>
  ▼
AUTO_PASTE=1 ~/.local/bin/dropfile
  │
  ├─ 决定来源（优先级见第 3 节）
  ├─ 大小检查（默认 15MB 上限）
  ├─ base64 编码
  ├─ ssh user@host 'DROPFILE_MAX_MB=15 bash ~/bin/drop-file.sh "原文件名"'   ← 带外通道
  │     远端：解码 → 复核大小 → sanitize 文件名 → 落盘 ~/Drops/ → 回显绝对路径
  ├─ 路径 pbcopy 回本机剪贴板（**不带尾随换行**）
  ├─ 等修饰键释放 + 等剪贴板就绪                    ← 关键，见 4.5
  └─ 模拟 ⌘V 粘到前台窗口
  ▼
Claude Code 输入框出现 /home/user/Drops/20260727_130248_报告.md
```

---

## 3. 来源优先级

`dropfile` 按这个顺序找内容，**顺序本身是设计决策**：

| 序 | 来源 | 文件名 | 说明 |
|----|------|--------|------|
| 1 | 命令行参数 | 保留原名 | `dropfile a.pdf b.zip` 可多个 |
| 2 | 剪贴板**文件引用** | 保留原名 | Finder 里复制的文件 |
| 3 | 剪贴板**图片数据** | 无，按 mime 猜后缀 | 截图 ⌘⇧⌃4、网页复制图片 |

> [!important] 为什么文件引用排在图片数据之前
> 从 Finder 复制一个 PNG 时，剪贴板**同时**有 file URL 和图片数据。
> 若先走 `pngpaste`，会丢掉原文件名，还会把图片**重编码**一遍
> （实测 463 字节的 PNG 出来变成 182 字节）。
> 有原文件就传原始字节 —— 这才是用户期待的行为。

---

## 4. 六条关键设计取舍

> 改脚本时不要顺手"简化"掉，每一条都是踩出来的。

### 4.1 所有外部命令写死绝对路径

Karabiner / 快捷键触发的是 **GUI 上下文**，PATH 被消毒成 `/usr/bin:/bin`。
`pngpaste` 装在 `/opt/homebrew/bin`（Apple Silicon）或 `/usr/local/bin`（Intel），
不写绝对路径必然 `command not found`，而且错误发生在 GUI 里，你看不到。

### 4.2 `pbcopy` 用 `printf '%s'` 而不是 `echo`

多一个尾随换行，⌘V 粘进 Claude Code 会**立刻提交**，来不及在路径后面补
"看这个文件，帮我…"。去掉换行后光标停在路径末尾。

多文件时中间的换行**要保留** —— Claude Code 会把每一行都识别为一个 attachment。

### 4.3 远端必须 sanitize 文件名

文件名由客户端传来，**不可信**。远端要 `basename` 去掉路径成分、剔除控制字符，
否则 `../../.ssh/authorized_keys` 这类名字会写到 Drops 之外。

同时把空格换成 `_`：终端里粘贴路径时空格会把路径截断。中文保留不动。
落盘名加时间戳前缀 `<ts>_<name>`，避免同名覆盖。

### 4.4 大小限制两侧都要检查

- **客户端**：快速失败，不浪费带宽（base64 会让体积涨 4/3）
- **远端**：防御版本不一致、脚本被绕过这类**意外**

客户端会把 `DROPFILE_MAX_MB` 一并传给远端 —— 否则 `DROPFILE_MAX_MB=50 dropfile big.zip`
只放宽了客户端，远端仍按自己的默认值拒绝。

> 注意这里的定位：远端检查防的是**意外**，不是多租户下的**恶意**。
> 自己的两台机器之间，尊重客户端显式配置是合理的。

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
2. 条件二：系统剪贴板的文本确实等于我们刚写入的内容

两个条件都满足（或超过 1.5s 预算）才发送。这样对上述任一根因都成立，
也对**未知的**第四种原因成立。

> [!warning] 海森堡陷阱
> 开发过程中出现过一次典型的观测者效应：把实现从 AppleScript 换成
> JXA + `ObjC.import("AppKit")` 后问题"自己好了"——因为加载 AppKit 让启动
> **慢了 48ms**（实测 21ms → 69ms），恰好躲过竞态窗口。
> **靠偶然延迟工作的代码，换台更快的机器就会复发。**
>
> 相应地，所有等待逻辑都放在**一次** `osascript` 调用内完成 ——
> 拆成多次调用会各自引入 ~50ms 启动开销，等于又在偷偷加固定延迟。

### 4.6 环境变量必须优先于配置文件

配置文件里是直接赋值（`DROP_HOST=...`）。如果先 `source` 再取默认值，
配置文件会把环境变量**覆盖掉**，`DROP_HOST=user@other dropfile` 这种
临时指定目标机的用法会**静默失效** —— 推到配置文件里那台去。

正确做法：source 之前先把环境变量存进临时变量，source 之后再让它们赢。

---

## 5. 踩过的 shell 坑（都已修）

| 坑 | 现象 | 原因与修法 |
|----|------|-----------|
| **变量名后紧跟全角标点** | `DROP_HOST?: unbound variable` | `"失败（$DROP_HOST）"` 在 `set -u` 下，bash 会把全角括号的首字节吞进变量名。必须写 `${DROP_HOST}`。这行只在 SSH **失败**时执行，正常路径测不出来 |
| **scp 远端路径不展开** | `dest open "$HOME/bin/x": No such file` | `ssh` 的命令串经远端 shell 展开，`scp` 的路径**不会**。要用相对 home 的 `host:bin/x` |
| **`base64 -d` vs `-D`** | 旧版 macOS 解码失败 | GNU 与新版 macOS 用 `-d`，旧版 macOS(BSD) 只有 `-D`。先试 `-d` 再回退 `-D` |
| **`set -e` 下取 `$?`** | 错误分支永远不执行 | `python3 <<PY ... PY` 失败会直接终止脚本，`kout=$?` 拿不到。要用 `if cmd; then ... else ... fi` 包住 |

> 顺带澄清一个**不是**坑的：`set -e` 下 `[[ 条件 ]] && 命令` 当条件为假时
> **不会**终止脚本（实测退出码正常）。这点容易想当然。

---

## 6. 安装

**在线一键**（只装 dropfile，不装整个插件）：

```bash
curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/install-dropfile.sh | bash -s -- user@host
```

安装器按 `raw → jsDelivr → ghfast` 顺序回退取脚本（raw 保证最新，
jsDelivr 保证国内可达），然后：检查依赖 → 验证免密 SSH → 装远端脚本与清理任务 →
装本地命令与配置 → 写 Karabiner 快捷键 → **推一个测试文件自检**。

| 选项 | 说明 |
|------|------|
| `--key cmd+shift+i` | 换快捷键（默认 `ctrl+opt+v`） |
| `--no-karabiner` | 不配快捷键，只装命令 |
| `--no-cleanup` | 不装远端定期清理 |
| `--max-mb 50` | 改大小上限（默认 15） |
| `--remote-dir '$HOME/img'` | 换远端落盘目录 |
| `--dry-run` | 只打印将要做什么 |

选快捷键时避开目标终端已占用的组合。iTerm2 里 `Cmd+Shift+V`（Paste Special）
和 `Cmd+Shift+D`（Split）都有用途，`Ctrl+Opt+V` 通常是空的。

安装器会创建 `dropimg` 作为 `dropfile` 的软链接，老的用法和快捷键不会 break。

---

## 7. 用法

```bash
dropfile                      # 剪贴板内容（复制的文件 或 截图）
dropfile report.pdf           # 指定文件
dropfile a.png b.zip c.md     # 多个文件，返回多行路径
DROPFILE_MAX_MB=50 dropfile big.zip   # 临时放宽上限
DROP_HOST=user@other dropfile foo.pdf # 临时换目标机
```

日常最短路径：**截图 → `Ctrl+Opt+V` → 接着打字说明 → 回车**。

---

## 8. 排查

| 现象 | 排查 |
|------|------|
| 按快捷键**完全没反应也没通知** | Karabiner IPC 失联（`invalid shared secret`），看 `/var/log/karabiner/core_service.log`，`launchctl kickstart -k gui/$(id -u)/org.pqrs.karabiner.karabiner_console_user_server` |
| 弹通知"路径已复制，请手动 ⌘V" | 自动粘贴被拦：系统设置 → 隐私与安全性 → **辅助功能**，勾上 Karabiner-Elements。不修也能用，手动 ⌘V 即可 |
| **需要按两次**（快捷键 + 手动 ⌘V） | 条件等待没生效或超时太短。打开 `DROPIMG_DEBUG_LOG`，看 `waitMods` / `clipOK` 两个字段 |
| `剪贴板里没有文件` | 剪贴板确实是空的或非文件（常见：上一次 dropfile 已把它换成了路径） |
| `超过 15MB 上限` | 用 `DROPFILE_MAX_MB=50` 放宽，或先压缩 |
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
- `clipOK=false` → 剪贴板在预算内始终没变成目标内容，是条线索

---

## 9. 副作用与边界

- **剪贴板会被路径覆盖**：跑完后剪贴板里是路径。想把同一份内容再推一次需重新复制。
  这是刻意取舍，换来"粘完即用"。
- **文件名里的空格会变成 `_`**：终端里粘路径时空格会截断。中文不受影响。
- **客户端只支持 macOS**：依赖 `NSPasteboard` / `osascript`；`pngpaste` 只有截图这条来源需要。
  远端 macOS / Linux 都支持。
- **需要免密 SSH**：先 `ssh-copy-id user@host`。
- **走公网时**把 `DROP_HOST` 指向中继入口即可（例如 ECS Relay 的 `user@<relay-ip>`），
  链路与局域网一致。
- **大文件会慢**：base64 让体积涨 4/3，公网上 15MB 要传 20MB。
