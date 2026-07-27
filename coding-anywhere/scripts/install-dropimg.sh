#!/bin/bash
# install-dropimg.sh — 一键安装「终端远程贴图」能力（客户端 + 远端 + 快捷键）。
#
# 用法：
#   bash install-dropimg.sh <user@host> [选项]
#
# 选项：
#   --key <组合>       全局快捷键，默认 ctrl+opt+v。格式如 cmd+shift+i、ctrl+opt+v
#   --no-karabiner     不配置 Karabiner 快捷键（只装命令，手动跑 dropimg）
#   --no-cleanup       不在远端安装 Drops 定期清理任务
#   --remote-dir <路径> 远端落盘目录，默认 ~/Drops
#   --dry-run          只打印将要做什么，不实际改动
#
# 示例：
#   bash install-dropimg.sh jliu@192.168.1.10
#   bash install-dropimg.sh jliu@mini.local --key cmd+shift+i
#   bash install-dropimg.sh jliu@1.2.3.4 --no-karabiner
set -euo pipefail

# ---------- 参数 ----------
DROP_HOST=""
HOTKEY="ctrl+opt+v"
WITH_KARABINER=1
WITH_CLEANUP=1
REMOTE_DIR='$HOME/Drops'
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key)          HOTKEY="$2"; shift 2 ;;
    --no-karabiner) WITH_KARABINER=0; shift ;;
    --no-cleanup)   WITH_CLEANUP=0; shift ;;
    --remote-dir)   REMOTE_DIR="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      sed -n '2,22p' "$0"; exit 0 ;;
    -*)             echo "未知选项: $1" >&2; exit 1 ;;
    *)              DROP_HOST="$1"; shift ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/dropimg"
REMOTE_BIN='$HOME/bin'

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
err()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; }
step() { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }
die()  { err "$1"; exit 1; }
run()  { if [[ $DRY_RUN == 1 ]]; then echo "    (dry-run) $*"; else eval "$@"; fi; }

[[ -n "$DROP_HOST" ]] || die "缺少目标主机。用法: bash install-dropimg.sh <user@host>"
[[ "$(uname)" == "Darwin" ]] || die "客户端目前只支持 macOS（依赖 pngpaste / NSPasteboard）"

echo "══════════════════════════════════════════════"
echo "  dropimg 安装器"
echo "  目标主机 : $DROP_HOST"
echo "  快捷键   : $([[ $WITH_KARABINER == 1 ]] && echo "$HOTKEY" || echo "(不配置)")"
echo "  远端目录 : $REMOTE_DIR"
[[ $DRY_RUN == 1 ]] && echo "  模式     : DRY RUN（不实际改动）"
echo "══════════════════════════════════════════════"

# ---------- 1. 依赖 ----------
step 1/6 "检查依赖"

PNGPASTE=""
for c in /opt/homebrew/bin/pngpaste /usr/local/bin/pngpaste; do
  [[ -x "$c" ]] && PNGPASTE="$c" && break
done
if [[ -z "$PNGPASTE" ]]; then
  if command -v brew >/dev/null 2>&1; then
    warn "未找到 pngpaste，正在安装…"
    run "brew install pngpaste"
    for c in /opt/homebrew/bin/pngpaste /usr/local/bin/pngpaste; do
      [[ -x "$c" ]] && PNGPASTE="$c" && break
    done
    [[ -n "$PNGPASTE" || $DRY_RUN == 1 ]] || die "pngpaste 安装失败"
  else
    die "未找到 pngpaste 且没有 brew。请先安装 Homebrew，或手动 brew install pngpaste"
  fi
fi
ok "pngpaste: ${PNGPASTE:-(将安装)}"

command -v python3 >/dev/null 2>&1 || die "需要 python3（用于安全地修改 Karabiner 的 JSON 配置）"
ok "python3: $(command -v python3)"

# ---------- 2. 免密 SSH ----------
step 2/6 "验证到 $DROP_HOST 的免密 SSH"

if [[ $DRY_RUN == 0 ]]; then
  if ! remote_host="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$DROP_HOST" 'hostname' 2>&1)"; then
    err "免密 SSH 不通:"
    echo "$remote_host" | sed 's/^/      /'
    echo
    echo "  先把公钥装上再重试:"
    echo "      ssh-copy-id $DROP_HOST"
    exit 1
  fi
  ok "连通，远端 hostname = $remote_host"
else
  echo "    (dry-run) ssh $DROP_HOST hostname"
fi

# ---------- 3. 远端落盘脚本 ----------
step 3/6 "安装远端落盘脚本 → $DROP_HOST:$REMOTE_BIN/drop-image.sh"

[[ -f "$SCRIPT_DIR/drop-image.sh" ]] \
  || die "找不到 $SCRIPT_DIR/drop-image.sh（请从插件目录或仓库内运行本安装器）"

if [[ $DRY_RUN == 0 ]]; then
  ssh -o BatchMode=yes "$DROP_HOST" "mkdir -p $REMOTE_BIN $REMOTE_DIR"
  # scp 的远端路径不经过 shell 展开（ssh 会，scp 不会），所以这里必须用
  # 相对 home 的路径 "bin/..." 而不是 "$HOME/bin/..."
  scp -q "$SCRIPT_DIR/drop-image.sh" "$DROP_HOST:bin/drop-image.sh"
  ssh -o BatchMode=yes "$DROP_HOST" "chmod +x $REMOTE_BIN/drop-image.sh"
  ok "已安装并 chmod +x"
else
  echo "    (dry-run) scp drop-image.sh → $DROP_HOST:$REMOTE_BIN/"
fi

# ---------- 4. 远端清理任务 ----------
if [[ $WITH_CLEANUP == 1 ]]; then
  step 4/6 "安装远端 Drops 清理任务（每周日 03:00 清 7 天前的文件）"
  if [[ $DRY_RUN == 0 ]]; then
    remote_os="$(ssh -o BatchMode=yes "$DROP_HOST" 'uname' 2>/dev/null || echo unknown)"
    if [[ "$remote_os" == "Darwin" ]]; then
      # plist 在本地生成再 scp 过去：直接在 ssh 里用嵌套 heredoc 需要三层转义，
      # XML 的引号和 $ 极易出错，不值得为省一次 scp 冒这个险
      PLIST_TMP="$(mktemp -t dropimg-cleanup)"
      cat > "$PLIST_TMP" <<PLIST
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
      if ssh -o BatchMode=yes "$DROP_HOST" 'mkdir -p ~/Library/LaunchAgents' \
         && scp -q "$PLIST_TMP" "$DROP_HOST:Library/LaunchAgents/com.dropimg.cleanup.plist" \
         && ssh -o BatchMode=yes "$DROP_HOST" 'launchctl bootout gui/$(id -u)/com.dropimg.cleanup 2>/dev/null; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dropimg.cleanup.plist'; then
        ok "LaunchAgent com.dropimg.cleanup 已注册"
      else
        warn "LaunchAgent 注册失败（不影响主功能，可稍后手动处理）"
      fi
      rm -f "$PLIST_TMP"
    else
      ssh -o BatchMode=yes "$DROP_HOST" "bash -lc '
        ( crontab -l 2>/dev/null | grep -v \"dropimg-cleanup\" ;
          echo \"0 3 * * 0 find $REMOTE_DIR -type f -mtime +7 -delete # dropimg-cleanup\" ) | crontab -
      '" && ok "crontab 清理任务已安装" || warn "crontab 安装失败（不影响主功能）"
    fi
  else
    echo "    (dry-run) 在远端安装清理任务"
  fi
else
  step 4/6 "跳过远端清理任务（--no-cleanup）"
fi

# ---------- 5. 本地命令 + 配置 ----------
step 5/6 "安装本地命令 → $BIN_DIR/dropimg"

[[ -f "$SCRIPT_DIR/dropimg" ]] || die "找不到 $SCRIPT_DIR/dropimg"

run "mkdir -p '$BIN_DIR' '$CONFIG_DIR'"
run "install -m 0755 '$SCRIPT_DIR/dropimg' '$BIN_DIR/dropimg'"
ok "$BIN_DIR/dropimg"

if [[ $DRY_RUN == 0 ]]; then
  cat > "$CONFIG_DIR/config" <<EOF
# dropimg 配置（由 install-dropimg.sh 生成）
# 环境变量同名项会覆盖这里的值
DROP_HOST="$DROP_HOST"
REMOTE_SCRIPT="$REMOTE_BIN/drop-image.sh"
PNGPASTE="$PNGPASTE"
# 排查问题时取消下面这行的注释，会记录每次自动粘贴的等待与结果
# DROPIMG_DEBUG_LOG="/tmp/dropimg-debug.log"
EOF
  ok "$CONFIG_DIR/config"
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
    echo "      AUTO_PASTE=1 $BIN_DIR/dropimg"
  elif [[ $DRY_RUN == 1 ]]; then
    echo "    (dry-run) 向 karabiner.json 写入 $HOTKEY 规则"
  else
    cp "$KJSON" "$KJSON.bak.$(date +%Y%m%d_%H%M%S)"
    # 用 if 包住而不是事后取 $? —— set -e 下 python3 一旦非 0 会直接终止脚本，
    # 后面的错误分支永远走不到
    if HOTKEY="$HOTKEY" BIN_DIR="$BIN_DIR" python3 <<'PY'
import json, os, sys, datetime

path = os.path.expanduser("~/.config/karabiner/karabiner.json")
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

DESC = "dropimg: push clipboard image to remote host"
rule = {
    "description": DESC,
    "manipulators": [{
        "from": {"key_code": key, "modifiers": {"mandatory": sorted(set(mods))}},
        "to": [{"shell_command": f"AUTO_PASTE=1 {bindir}/dropimg"}],
        "type": "basic",
    }],
}

with open(path) as f:
    cfg = json.load(f)

conflicts = []
for prof in cfg.get("profiles", []):
    cm = prof.setdefault("complex_modifications", {})
    rules = cm.setdefault("rules", [])
    for r in rules:
        if r.get("description") == DESC:
            continue
        for m in r.get("manipulators", []):
            fr = m.get("from", {})
            if fr.get("key_code") == key and \
               sorted(fr.get("modifiers", {}).get("mandatory", [])) == sorted(set(mods)):
                conflicts.append(r.get("description", "(无描述)"))
    rules[:] = [r for r in rules if r.get("description") != DESC]   # 幂等
    rules.append(rule)

with open(path, "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=4)

if conflicts:
    print("CONFLICT:" + "; ".join(conflicts))
PY
    then
      ok "规则已写入（Karabiner 会自动 reload，无需重启）"
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
  echo "    需要时手动绑定这条命令: AUTO_PASTE=1 $BIN_DIR/dropimg"
fi

# ---------- 自检 ----------
if [[ $DRY_RUN == 0 ]]; then
  step "自检" "推一张 1x1 测试图过去"
  TESTPNG="$(mktemp -t dropimg-test).png"
  # 内嵌的最小合法 PNG（1x1 透明）
  printf 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==' \
    | base64 -d > "$TESTPNG" 2>/dev/null || \
  printf 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==' \
    | base64 -D > "$TESTPNG"
  osascript -e "set the clipboard to (read (POSIX file \"$TESTPNG\") as «class PNGf»)"
  if result="$("$BIN_DIR/dropimg" 2>&1)"; then
    ok "推送成功 → $result"
    ssh -o BatchMode=yes "$DROP_HOST" "test -f '$result'" \
      && ok "已确认文件存在于远端" \
      || warn "远端找不到该文件，请检查 $REMOTE_DIR 权限"
  else
    err "自检失败: $result"
  fi
  rm -f "$TESTPNG"
fi

cat <<EOF

══════════════════════════════════════════════
  安装完成
══════════════════════════════════════════════

  日常用法:
    ① 截图（⌘⇧⌃4 复制到剪贴板）
    ② 按 $([[ $WITH_KARABINER == 1 ]] && echo "$HOTKEY" || echo "手动运行 dropimg")
    ③ 远端路径出现在光标处，接着打字说明，回车

  命令行:
    dropimg                        推送并复制路径
    DROP_HOST=user@other dropimg   临时换目标机

  配置: $CONFIG_DIR/config
  排查: 取消配置里 DROPIMG_DEBUG_LOG 那行的注释，再看 /tmp/dropimg-debug.log

EOF
