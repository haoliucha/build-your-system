#!/bin/bash
# uninstall-dropfile.sh — 卸载 dropfile（客户端 + 远端 + 快捷键）。
#
# 一键运行（在装了 dropfile 的那台机器上跑）：
#   curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/uninstall-dropfile.sh | bash -s
#
# 选项：
#   --keep-remote    不动远端（只卸本地命令、配置、快捷键）
#   --purge-drops    连远端 ~/Drops 里的文件一起删 —— 那是**数据**，默认保留
#   --dry-run        只打印将要删什么，不实际删
#
# 默认**不删** ~/Drops：里面是你传过去的文件，删了不可恢复。
set -euo pipefail

DROP_HOST=""
KEEP_REMOTE=0
PURGE_DROPS=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-remote) KEEP_REMOTE=1; shift ;;
    --purge-drops) PURGE_DROPS=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     sed -n '2,16p' "$0" 2>/dev/null || echo "见 README"; exit 0 ;;
    -*)            echo "未知选项: $1" >&2; exit 1 ;;
    *)             DROP_HOST="$1"; shift ;;
  esac
done

# 选一个**真能用**的 python3：Homebrew 的 python 可能因 pyexpat 与系统 libexpat
# 版本不匹配而 import plistlib 直接失败（实测 3.14.4 就是坏的），而 PATH 里
# 解析到的往往正是它。只查 `command -v python3` 存在是不够的，得实际试一下。
pick_python() {
  local p
  for p in /usr/bin/python3 "$(command -v python3 2>/dev/null || true)"; do
    [[ -x "$p" ]] || continue
    "$p" -c 'import json, plistlib' >/dev/null 2>&1 && { printf '%s' "$p"; return 0; }
  done
  return 1
}

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
skip() { printf '  \033[90m·\033[0m %s\n' "$1"; }
sec()  { printf '\n\033[1m── %s\033[0m\n' "$1"; }
run()  { if [[ $DRY_RUN == 1 ]]; then echo "    (dry-run) $*"; else eval "$@"; fi; }

# 卸载只是尽力而为：没有可用 python 时跳过依赖它的两节，不中断整体流程
PY3="$(pick_python || true)"

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/dropimg"

echo "══════════════════════════════════════════"
echo "  dropfile 卸载"
[[ $DRY_RUN == 1 ]] && echo "  模式: DRY RUN（只看不删）"
echo "══════════════════════════════════════════"

# ---------- 找远端主机 ----------
# 配置文件里的 DROP_HOST 最可靠：它记录了当初装到哪台
if [[ -z "$DROP_HOST" && -f "$CONFIG_DIR/config" ]]; then
  DROP_HOST="$(/usr/bin/grep -E '^DROP_HOST=' "$CONFIG_DIR/config" 2>/dev/null \
               | /usr/bin/sed -E 's/^DROP_HOST="?([^"]*)"?.*/\1/' | /usr/bin/head -1)"
fi

sec "1. 本地命令"
for f in "$BIN_DIR/dropfile" "$BIN_DIR/dropimg"; do
  if [[ -e "$f" || -L "$f" ]]; then
    run "rm -f '$f'"; ok "删除 $f"
  else
    skip "不存在 $f"
  fi
done

sec "2. 本地配置"
if [[ -d "$CONFIG_DIR" ]]; then
  # 配置目录里可能还有安装器留下的 iTerm2 偏好备份，一并列出来再删
  for x in "$CONFIG_DIR"/*; do [[ -e "$x" ]] && skip "包含 $(basename "$x")"; done
  run "rm -rf '$CONFIG_DIR'"; ok "删除 $CONFIG_DIR"
else
  skip "不存在 $CONFIG_DIR"
fi

sec "3. Karabiner 规则"
KJSON="$HOME/.config/karabiner/karabiner.json"
if [[ -f "$KJSON" ]]; then
  if [[ $DRY_RUN == 1 ]]; then
    "$PY3" - <<'PY'
import json, os
d = json.load(open(os.path.expanduser("~/.config/karabiner/karabiner.json")))
n = sum(1 for pr in d.get("profiles", [])
          for r in pr.get("complex_modifications", {}).get("rules", [])
          for m in r.get("manipulators", [])
          if "drop" in str(m.get("to", "")))
print(f"    (dry-run) 会移除 {n} 条 drop 相关规则")
PY
  else
    cp "$KJSON" "$KJSON.bak.$(date +%Y%m%d_%H%M%S)"
    "$PY3" - <<'PY'
import json, os
p = os.path.expanduser("~/.config/karabiner/karabiner.json")
d = json.load(open(p))
n = 0
for pr in d.get("profiles", []):
    rules = pr.get("complex_modifications", {}).get("rules", [])
    before = len(rules)
    rules[:] = [r for r in rules
                if not any("drop" in str(m.get("to", "")) for m in r.get("manipulators", []))]
    n += before - len(rules)
json.dump(d, open(p, "w"), ensure_ascii=False, indent=4)
print(f"  \033[32m✓\033[0m 移除 {n} 条规则（原配置已备份为 karabiner.json.bak.*）")
PY
  fi
else
  skip "没有 karabiner.json"
fi

sec "4. iTerm2 Coprocess 绑定"
# 刻意只检测不自动删：这条是你在 GUI 里手动加的，而且改 plist 需要重启 iTerm2
# 才生效（偏好由 cfprefsd 托管），在 GUI 里删则立即生效
if "$PY3" - 2>/dev/null <<'PY'
import plistlib, subprocess, sys
raw = subprocess.run(['defaults','export','com.googlecode.iterm2','-'],
                     capture_output=True).stdout
d = plistlib.loads(raw) if raw else {}
hits = [k for k, v in d.get("GlobalKeyMap", {}).items()
        if "dropfile" in str(v.get("Text", "")) or "dropimg" in str(v.get("Text", ""))]
if hits:
    print("  ! 检测到 iTerm2 里还有 dropfile 绑定:")
    for k in hits:
        print(f"      {k}")
    print("    在 iTerm2 → Settings → Keys → Key Bindings 里删除（立即生效）")
    sys.exit(0)
sys.exit(1)
PY
then :; else skip "没有 iTerm2 绑定"; fi

sec "5. 远端"
if [[ $KEEP_REMOTE == 1 ]]; then
  skip "跳过（--keep-remote）"
elif [[ -z "$DROP_HOST" ]]; then
  warn "不知道远端是哪台（配置已删或从未安装）"
  warn "需要的话手动指定: bash uninstall-dropfile.sh user@host"
else
  echo "  目标: $DROP_HOST"
  if [[ $DRY_RUN == 1 ]]; then
    echo "    (dry-run) 删除远端 ~/bin/drop-file.sh、~/bin/drop-image.sh、清理任务"
  elif ssh -n -o BatchMode=yes -o ConnectTimeout=8 "$DROP_HOST" true 2>/dev/null; then
    ssh -n -o BatchMode=yes "$DROP_HOST" '
      rm -f ~/bin/drop-file.sh ~/bin/drop-image.sh
      launchctl bootout gui/$(id -u)/com.dropimg.cleanup 2>/dev/null
      rm -f ~/Library/LaunchAgents/com.dropimg.cleanup.plist
      crontab -l 2>/dev/null | grep -v dropimg-cleanup | crontab - 2>/dev/null || true
      echo "  ok"
    ' >/dev/null 2>&1 && ok "远端脚本与清理任务已删除" || warn "远端清理部分失败"

    n="$(ssh -n -o BatchMode=yes "$DROP_HOST" 'ls ~/Drops 2>/dev/null | wc -l | tr -d " "' 2>/dev/null || echo 0)"
    if [[ $PURGE_DROPS == 1 ]]; then
      ssh -n -o BatchMode=yes "$DROP_HOST" 'rm -rf ~/Drops' 2>/dev/null \
        && ok "已删除远端 ~/Drops（$n 个文件）" || warn "删除 ~/Drops 失败"
    else
      skip "保留远端 ~/Drops（$n 个文件）—— 那是数据，要删加 --purge-drops"
    fi
  else
    warn "$DROP_HOST 连不上，远端未清理"
    warn "机器可用后手动跑: ssh $DROP_HOST 'rm -f ~/bin/drop-file.sh ~/bin/drop-image.sh'"
  fi
fi

sec "6. 日志"
for f in /tmp/dropimg-debug.log /tmp/dropimg-cleanup.log; do
  [[ -f "$f" ]] && { run "rm -f '$f'"; ok "删除 $f"; } || skip "不存在 $f"
done

echo
echo "══════════════════════════════════════════"
if [[ $DRY_RUN == 1 ]]; then
  echo "  DRY RUN 结束，什么都没删"
else
  echo "  卸载完成"
  echo
  echo "  重装:"
  echo "    curl -fsSL \"https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/install-dropfile.sh?cb=\$(date +%s)\" | bash -s"
fi
echo "══════════════════════════════════════════"
