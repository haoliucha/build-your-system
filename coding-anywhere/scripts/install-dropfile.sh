#!/bin/bash
# install-dropfile.sh — 只安装「终端远程传文件」能力（dropfile），不装整个插件。
#
# 在线一键安装（推荐）：
#   curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/install-dropfile.sh | bash -s -- user@host
#
# 本地安装（仓库/插件目录内）：
#   bash install-dropfile.sh user@host
#
# 选项：
#   --key <组合>        全局快捷键，默认 ctrl+opt+v；格式如 cmd+shift+i
#   --no-karabiner      不配置快捷键，只装命令
#   --no-cleanup        不在远端安装定期清理任务
#   --max-mb <N>        文件大小上限，默认 15
#   --remote-dir <路径>  远端落盘目录，默认 ~/Drops
#   --dry-run           只打印将要做什么
#
# 卸载：
#   rm -f ~/.local/bin/dropfile ~/.local/bin/dropimg
#   rm -rf ~/.config/dropimg
#   ssh user@host 'rm -f ~/bin/drop-file.sh'
#   # 再从 ~/.config/karabiner/karabiner.json 删掉 description 含 dropfile 的那条规则
set -euo pipefail

REPO="${DROPFILE_REPO:-haoliucha/build-your-system}"
# 合并前想验证在线流程，或想从 fork 装，可以覆盖分支：
#   DROPFILE_BRANCH=feat/xxx curl -fsSL <url> | bash -s -- user@host
BRANCH="${DROPFILE_BRANCH:-main}"
SUBDIR="coding-anywhere/scripts"

# 下载源按序回退：
#   raw       —— 保证拿到最新（刚 push 就能取到）
#   jsdelivr  —— CDN，国内可达性最好，但对 @main 有缓存延迟
#   ghfast    —— 反代兜底
mirror_urls() {  # $1 = 文件名
  # raw 带 cache-buster：raw.githubusercontent.com 有几分钟 CDN 缓存，
  # 刚合并就安装会拿到旧脚本（实测过）。加个变化的 query 强制回源。
  echo "https://raw.githubusercontent.com/$REPO/$BRANCH/$SUBDIR/$1?cb=$(date +%s)"
  echo "https://cdn.jsdelivr.net/gh/$REPO@$BRANCH/$SUBDIR/$1"
  echo "https://ghfast.top/https://raw.githubusercontent.com/$REPO/$BRANCH/$SUBDIR/$1"
}

# ---------- 参数 ----------
DROP_HOST=""
HOTKEY="ctrl+opt+v"
WITH_KARABINER=1
WITH_CLEANUP=1
MAX_MB=15
REMOTE_DIR='$HOME/Drops'
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key)          HOTKEY="$2"; shift 2 ;;
    --no-karabiner) WITH_KARABINER=0; shift ;;
    --no-cleanup)   WITH_CLEANUP=0; shift ;;
    --max-mb)       MAX_MB="$2"; shift 2 ;;
    --remote-dir)   REMOTE_DIR="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      sed -n '2,26p' "$0" 2>/dev/null || echo "见 README"; exit 0 ;;
    -*)             echo "未知选项: $1" >&2; exit 1 ;;
    *)              DROP_HOST="$1"; shift ;;
  esac
done

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/dropimg"
REMOTE_BIN='$HOME/bin'

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
err()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; }
step() { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }
die()  { err "$1"; exit 1; }

[[ -n "$DROP_HOST" ]] || die "缺少目标主机。用法: ... | bash -s -- user@host"
[[ "$(uname)" == "Darwin" ]] || die "客户端目前只支持 macOS（依赖 NSPasteboard / osascript）"

# 管道执行时 BASH_SOURCE 不是真实文件，此时走在线下载
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  SCRIPT_DIR=""
fi

STAGE="$(mktemp -d -t dropfile-install)"
trap 'rm -rf "$STAGE"' EXIT

# 取一个脚本文件到 $STAGE：优先本地，否则按镜像顺序下载
fetch() {
  local name="$1" dest="$STAGE/$1"
  if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/$name" ]]; then
    cp "$SCRIPT_DIR/$name" "$dest"
    echo "local"
    return 0
  fi
  local url
  while read -r url; do
    if curl -fsSL --max-time 25 "$url" -o "$dest" 2>/dev/null && [[ -s "$dest" ]]; then
      # 简单完整性检查：必须是 shell 脚本，避免把 404 页面存下来
      if head -1 "$dest" | grep -q '^#!/bin/bash'; then
        echo "$(echo "$url" | sed -E 's#https://([^/]+)/.*#\1#')"
        return 0
      fi
    fi
  done < <(mirror_urls "$name")
  return 1
}

echo "══════════════════════════════════════════════"
echo "  dropfile 安装器（终端远程传文件）"
echo "  目标主机 : $DROP_HOST"
echo "  快捷键   : $([[ $WITH_KARABINER == 1 ]] && echo "$HOTKEY" || echo "(不配置)")"
echo "  大小上限 : ${MAX_MB}MB"
echo "  远端目录 : $REMOTE_DIR"
[[ $DRY_RUN == 1 ]] && echo "  模式     : DRY RUN（不实际改动）"
echo "══════════════════════════════════════════════"

# ---------- 1. 取脚本 ----------
step 1/6 "获取脚本"
if [[ $DRY_RUN == 0 ]]; then
  for f in dropfile drop-file.sh; do
    # ${f} 必须带花括号：后面紧跟全角括号时，set -u 下 bash 会把多字节
    # 首字节吞进变量名，报 "f?: unbound variable"。这行只在下载失败时执行，
    # 正常路径测不出来
    src="$(fetch "$f")" || die "拿不到 ${f}（本地没有，且所有下载源都失败）"
    ok "$f ← $src"
  done
else
  echo "    (dry-run) 获取 dropfile / drop-file.sh"
fi

# ---------- 2. 依赖 ----------
step 2/6 "检查依赖"
PNGPASTE=""
for c in /opt/homebrew/bin/pngpaste /usr/local/bin/pngpaste; do
  [[ -x "$c" ]] && PNGPASTE="$c" && break
done
if [[ -z "$PNGPASTE" ]]; then
  # pngpaste 只有"剪贴板截图"这一条来源需要；传文件不依赖它，所以缺了不致命
  if command -v brew >/dev/null 2>&1 && [[ $DRY_RUN == 0 ]]; then
    warn "未找到 pngpaste，正在安装（截图直传需要它）…"
    brew install pngpaste </dev/null >/dev/null 2>&1 || warn "pngpaste 安装失败，截图直传将不可用"
    for c in /opt/homebrew/bin/pngpaste /usr/local/bin/pngpaste; do
      [[ -x "$c" ]] && PNGPASTE="$c" && break
    done
  else
    warn "未找到 pngpaste —— 传文件不受影响，但「截图直传」会不可用"
    warn "需要时: brew install pngpaste"
  fi
fi
[[ -n "$PNGPASTE" ]] && ok "pngpaste: $PNGPASTE"
command -v python3 >/dev/null 2>&1 || die "需要 python3（用于安全地修改 Karabiner 的 JSON 配置）"
ok "python3: $(command -v python3)"

# ---------- 3. 免密 SSH ----------
step 3/6 "验证到 $DROP_HOST 的免密 SSH"
if [[ $DRY_RUN == 0 ]]; then
  if ! remote_host="$(ssh -n -o BatchMode=yes -o ConnectTimeout=8 "$DROP_HOST" 'hostname' 2>&1)"; then
    err "免密 SSH 不通:"
    echo "$remote_host" | sed 's/^/      /'
    echo
    echo "  先把公钥装上再重试:  ssh-copy-id $DROP_HOST"
    exit 1
  fi
  ok "连通，远端 hostname = $remote_host"
else
  echo "    (dry-run) ssh $DROP_HOST hostname"
fi

# ---------- 4. 远端 ----------
step 4/6 "安装远端落盘脚本 → $DROP_HOST:$REMOTE_BIN/drop-file.sh"
if [[ $DRY_RUN == 0 ]]; then
  ssh -n -o BatchMode=yes "$DROP_HOST" "mkdir -p $REMOTE_BIN $REMOTE_DIR"
  # scp 的远端路径不经过 shell 展开（ssh 会，scp 不会），必须用相对 home 的路径
  scp -q "$STAGE/drop-file.sh" "$DROP_HOST:bin/drop-file.sh"
  ssh -n -o BatchMode=yes "$DROP_HOST" "chmod +x $REMOTE_BIN/drop-file.sh"
  ok "已安装并 chmod +x"

  if [[ $WITH_CLEANUP == 1 ]]; then
    remote_os="$(ssh -n -o BatchMode=yes "$DROP_HOST" 'uname' 2>/dev/null || echo unknown)"
    if [[ "$remote_os" == "Darwin" ]]; then
      # plist 在本地生成再 scp：直接在 ssh 里嵌套 heredoc 要三层转义，XML 的引号极易出错
      PL="$STAGE/cleanup.plist"
      cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.dropimg.cleanup</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string><string>-c</string>
        <string>/usr/bin/find $REMOTE_DIR -type f -mtime +7 -print -delete</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/tmp/dropimg-cleanup.log</string>
    <key>StandardErrorPath</key><string>/tmp/dropimg-cleanup.log</string>
</dict>
</plist>
PLIST
      if ssh -n -o BatchMode=yes "$DROP_HOST" 'mkdir -p ~/Library/LaunchAgents' \
         && scp -q "$PL" "$DROP_HOST:Library/LaunchAgents/com.dropimg.cleanup.plist" \
         && ssh -n -o BatchMode=yes "$DROP_HOST" 'launchctl bootout gui/$(id -u)/com.dropimg.cleanup 2>/dev/null; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dropimg.cleanup.plist'; then
        ok "清理任务已注册（每周日 03:00 清 7 天前的文件）"
      else
        warn "清理任务注册失败（不影响主功能）"
      fi
    else
      ssh -n -o BatchMode=yes "$DROP_HOST" "bash -lc '
        ( crontab -l 2>/dev/null | grep -v dropimg-cleanup ;
          echo \"0 3 * * 0 find $REMOTE_DIR -type f -mtime +7 -delete # dropimg-cleanup\" ) | crontab -
      '" && ok "crontab 清理任务已安装" || warn "crontab 安装失败（不影响主功能）"
    fi
  fi
else
  echo "    (dry-run) 安装远端脚本与清理任务"
fi

# ---------- 5. 本地 ----------
step 5/6 "安装本地命令 → $BIN_DIR/dropfile"
if [[ $DRY_RUN == 0 ]]; then
  mkdir -p "$BIN_DIR" "$CONFIG_DIR"
  install -m 0755 "$STAGE/dropfile" "$BIN_DIR/dropfile"
  ok "$BIN_DIR/dropfile"
  # dropimg 作为别名保留：老用户的肌肉记忆和已有快捷键不会 break
  ln -sf "$BIN_DIR/dropfile" "$BIN_DIR/dropimg"
  ok "$BIN_DIR/dropimg → dropfile（兼容别名）"

  cat > "$CONFIG_DIR/config" <<EOF
# dropfile 配置（由 install-dropfile.sh 生成）
#
# 目标主机的优先级：
#   1. 环境变量        DROP_HOST=user@other dropfile foo.pdf
#   2. 自动识别        读当前前台终端窗口那条 ssh 的 user@host
#   3. 下面这个值      前两者都没有时才用
#
# 也就是说：你 ssh 连着哪台，dropfile 默认就推给哪台，通常不用管这里。
# 想关掉自动识别： DROPFILE_AUTODETECT=0
DROP_HOST="$DROP_HOST"
REMOTE_SCRIPT_FILE="$REMOTE_BIN/drop-file.sh"
DROPFILE_MAX_MB=$MAX_MB
PNGPASTE="$PNGPASTE"
# 排查问题时取消下面这行注释，会记录每次自动粘贴的等待与结果
# DROPIMG_DEBUG_LOG="/tmp/dropimg-debug.log"
EOF
  ok "$CONFIG_DIR/config"
else
  echo "    (dry-run) 安装 dropfile 与配置"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ok "$BIN_DIR 已在 PATH 中" ;;
  *) warn "$BIN_DIR 不在 PATH。把这行加进 ~/.zshrc:"
     echo "      export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ---------- 6. 快捷键 ----------
if [[ $WITH_KARABINER == 1 ]]; then
  step 6/6 "配置 Karabiner 全局快捷键 $HOTKEY"
  KJSON="$HOME/.config/karabiner/karabiner.json"
  if [[ ! -f "$KJSON" ]]; then
    warn "未找到 $KJSON —— 没装 Karabiner-Elements？"
    warn "装了之后重跑本安装器，或手动绑定快捷键执行:"
    echo "      AUTO_PASTE=1 $BIN_DIR/dropfile"
  elif [[ $DRY_RUN == 1 ]]; then
    echo "    (dry-run) 向 karabiner.json 写入 $HOTKEY 规则"
  else
    cp "$KJSON" "$KJSON.bak.$(date +%Y%m%d_%H%M%S)"
    # 用 if 包住而不是事后取 $?：set -e 下 python3 非 0 会直接终止脚本
    if HOTKEY="$HOTKEY" BIN_DIR="$BIN_DIR" python3 <<'PY'
import json, os, sys

path   = os.path.expanduser("~/.config/karabiner/karabiner.json")
hotkey = os.environ["HOTKEY"].lower()
bindir = os.environ["BIN_DIR"]

ALIAS = {"cmd": "command", "command": "command", "opt": "option", "alt": "option",
         "option": "option", "ctrl": "control", "control": "control", "shift": "shift"}
parts = [p.strip() for p in hotkey.split("+") if p.strip()]
if len(parts) < 2:
    sys.exit(f"快捷键格式不对: {hotkey}（应形如 ctrl+opt+v）")
key, mods = parts[-1], []
for p in parts[:-1]:
    if p not in ALIAS:
        sys.exit(f"不认识的修饰键: {p}")
    mods.append(ALIAS[p])

DESC = "dropfile: push clipboard/file to remote host"
# 旧版本装的规则描述，一并清掉避免同键两条规则
LEGACY = {"dropimg: push clipboard image to remote host"}

rule = {
    "description": DESC,
    "manipulators": [{
        "from": {"key_code": key, "modifiers": {"mandatory": sorted(set(mods))}},
        "to": [{"shell_command": f"AUTO_PASTE=1 {bindir}/dropfile"}],
        "type": "basic",
    }],
}

with open(path) as f:
    cfg = json.load(f)

conflicts = []
for prof in cfg.get("profiles", []):
    rules = prof.setdefault("complex_modifications", {}).setdefault("rules", [])
    for r in rules:
        if r.get("description") in ({DESC} | LEGACY):
            continue
        for m in r.get("manipulators", []):
            fr = m.get("from", {})
            if fr.get("key_code") == key and \
               sorted(fr.get("modifiers", {}).get("mandatory", [])) == sorted(set(mods)):
                conflicts.append(r.get("description", "(无描述)"))
    rules[:] = [r for r in rules if r.get("description") not in ({DESC} | LEGACY)]  # 幂等
    rules.append(rule)

with open(path, "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=4)

if conflicts:
    print("  ! 该组合键已被占用: " + "; ".join(conflicts))
PY
    then
      ok "规则已写入（Karabiner 自动 reload，无需重启）"
      if pgrep -q karabiner_console_user_server; then
        ok "karabiner_console_user_server 在运行"
      else
        warn "karabiner_console_user_server 没在跑，快捷键不会生效"
      fi
    else
      err "写入 Karabiner 配置失败，已保留备份 $KJSON.bak.*"
    fi
  fi
else
  step 6/6 "跳过快捷键配置（--no-karabiner）"
  echo "    需要时手动绑定: AUTO_PASTE=1 $BIN_DIR/dropfile"
fi

# ---------- 自检 ----------
if [[ $DRY_RUN == 0 ]]; then
  step "自检" "推一个测试文件过去"
  TESTF="$STAGE/dropfile-selftest.txt"
  echo "dropfile self test $(date)" > "$TESTF"
  # stdout 与 stderr 必须分开捕获：dropfile 会把"目标 xxx（自动识别…）"这类
  # 提示写到 stderr，用 2>&1 合并会让 $result 变成多行，后面的 test -f 必然失败，
  # 明明装好了却报"远端找不到该文件"
  ERRF="$STAGE/selftest.err"
  if result="$("$BIN_DIR/dropfile" "$TESTF" 2>"$ERRF")"; then
    ok "推送成功 → $result"
    if ssh -n -o BatchMode=yes "$DROP_HOST" "test -f '$result'"; then
      ok "已确认文件存在于远端"
      ssh -n -o BatchMode=yes "$DROP_HOST" "rm -f '$result'" 2>/dev/null || true
    else
      warn "远端找不到该文件，请检查 $REMOTE_DIR 权限"
    fi
  else
    err "自检失败: $(cat "$ERRF" 2>/dev/null)"
  fi
fi

cat <<EOF

══════════════════════════════════════════════
  安装完成
══════════════════════════════════════════════

  日常用法:
    截图  → $([[ $WITH_KARABINER == 1 ]] && echo "按 $HOTKEY" || echo "运行 dropfile") → 路径出现在光标处
    传文件 → dropfile report.pdf
    多文件 → dropfile a.png b.zip c.md
    Finder 里复制文件后 → dropfile（保留原文件名）

  上限 ${MAX_MB}MB，临时放宽: DROPFILE_MAX_MB=50 dropfile big.zip
  换目标机:               DROP_HOST=user@other dropfile foo.pdf

  配置: $CONFIG_DIR/config
  排查: 取消配置里 DROPIMG_DEBUG_LOG 那行注释，再看 /tmp/dropimg-debug.log

EOF
