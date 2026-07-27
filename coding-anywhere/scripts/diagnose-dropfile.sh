#!/bin/bash
# diagnose-dropfile.sh — 排查「按了快捷键没反应 / 反应不对」。
#
# 一键运行（在**你面前那台**、按键盘的机器上跑，不是远端）：
#   curl -fsSL https://raw.githubusercontent.com/haoliucha/build-your-system/main/coding-anywhere/scripts/diagnose-dropfile.sh | bash
#
# 只读检查，不修改任何东西。
#
# 最常见的三种情况：
#   1. 在远端机器上按的快捷键 —— Karabiner 跑在本地，按键根本没被拦截
#   2. 本地没装 Karabiner-Elements —— 安装器会 warn 但不中止，容易被忽略
#   3. 装了但规则写进了未选中的 profile —— 规则在，就是不生效

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
sec()  { printf '\n\033[1m── %s\033[0m\n' "$1"; }

echo "══════════════════════════════════════════"
echo "  dropfile 快捷键诊断"
echo "══════════════════════════════════════════"
echo "  机器: $(hostname)   macOS $(sw_vers -productVersion 2>/dev/null || echo '?')"

sec "0. 你是不是在远端机器上跑这个诊断？"
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  bad "当前是 SSH 会话 —— 你在远端机器上"
  echo "     Karabiner 跑在你**面前那台**机器上，快捷键由它拦截。"
  echo "     请到本地那台（开着 iTerm2、你敲键盘的那台）重跑本诊断。"
  echo "     这本身就可能是问题原因。"
else
  ok "本地会话（正确的诊断位置）"
fi

sec "1. 客户端命令"
if [[ -x "$HOME/.local/bin/dropfile" ]]; then
  ok "$HOME/.local/bin/dropfile"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ok "~/.local/bin 在 PATH 中" ;;
    *) warn "~/.local/bin 不在 PATH（不影响快捷键，只影响手敲 dropfile）" ;;
  esac
else
  bad "没装 dropfile —— 先跑安装器"
fi
[[ -L "$HOME/.local/bin/dropimg" ]] && ok "dropimg → dropfile 别名在"

sec "2. 配置"
if [[ -f "$HOME/.config/dropimg/config" ]]; then
  grep -v '^#' "$HOME/.config/dropimg/config" | grep . | sed 's/^/     /'
else
  warn "没有配置文件（不致命 —— 目标主机可从当前 SSH 会话自动识别）"
fi

sec "3. Karabiner-Elements"
KOK=1
if [[ -d /Applications/Karabiner-Elements.app ]]; then
  ok "已安装"
else
  bad "未安装 —— 快捷键不可能生效"
  echo "     brew install --cask karabiner-elements   然后重跑安装器"
  KOK=0
fi
if pgrep -q karabiner_console_user_server; then
  ok "karabiner_console_user_server 在运行"
else
  [[ $KOK == 1 ]] && bad "进程没在跑 —— 打开 Karabiner-Elements.app 一次"
  KOK=0
fi

sec "4. 快捷键规则"
KJSON="$HOME/.config/karabiner/karabiner.json"
if [[ ! -f "$KJSON" ]]; then
  bad "没有 $KJSON"
else
  python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/karabiner/karabiner.json")
d = json.load(open(p))
found = []
for pr in d.get("profiles", []):
    sel = pr.get("selected", False)
    for r in pr.get("complex_modifications", {}).get("rules", []):
        for m in r.get("manipulators", []):
            f = m.get("from", {})
            mods = sorted(f.get("modifiers", {}).get("mandatory", []))
            cmd = (m.get("to") or [{}])[0].get("shell_command", "")
            if "dropfile" in cmd or "dropimg" in cmd:
                found.append((pr.get("name"), sel, f.get("key_code"), mods, cmd,
                              r.get("description", "")))
if not found:
    print("  \033[31m✗\033[0m 没有任何指向 dropfile/dropimg 的规则 —— 快捷键不会触发")
    print("     重跑安装器；若用了 --no-karabiner 则不会写规则")
for name, sel, key, mods, cmd, desc in found:
    mark = "\033[32m✓\033[0m" if sel else "\033[31m✗\033[0m"
    print(f"  {mark} profile={name} selected={sel}")
    print(f"     组合键: {'+'.join(mods)}+{key}")
    print(f"     命令:   {cmd}")
    if not sel:
        print("     \033[31m这个 profile 没有被选中，规则不生效！\033[0m")
        print("     打开 Karabiner-Elements → Profiles → 选中它")
PY
fi

sec "5. 该组合键是否被别的规则抢了"
python3 - <<'PY' 2>/dev/null
import json, os
p = os.path.expanduser("~/.config/karabiner/karabiner.json")
if os.path.exists(p):
    d = json.load(open(p))
    tgt = None
    for pr in d.get("profiles", []):
        for r in pr.get("complex_modifications", {}).get("rules", []):
            for m in r.get("manipulators", []):
                cmd = (m.get("to") or [{}])[0].get("shell_command", "")
                if "dropfile" in cmd or "dropimg" in cmd:
                    f = m.get("from", {})
                    tgt = (f.get("key_code"), sorted(f.get("modifiers", {}).get("mandatory", [])))
    if tgt:
        dup = []
        for pr in d.get("profiles", []):
            for r in pr.get("complex_modifications", {}).get("rules", []):
                for m in r.get("manipulators", []):
                    f = m.get("from", {})
                    cmd = (m.get("to") or [{}])[0].get("shell_command", "")
                    if (f.get("key_code"), sorted(f.get("modifiers", {}).get("mandatory", []))) == tgt \
                       and "dropfile" not in cmd and "dropimg" not in cmd:
                        dup.append(r.get("description", "(无描述)"))
        if dup:
            print("  \033[33m!\033[0m 同一组合键还被这些规则占用:", "; ".join(dup))
        else:
            print("  \033[32m✓\033[0m 没有冲突规则")
PY

sec "6. 辅助功能权限（影响自动粘贴，不影响推送）"
if sqlite3 "/Library/Application Support/com.apple.TCC/TCC.db" \
   "select 1 from access where service='kTCCServiceAccessibility' and client like '%karabiner%' and auth_value=2 limit 1" 2>/dev/null | grep -q 1; then
  ok "Karabiner 有辅助功能权限"
else
  warn "读不到或未授权（需要终端有完全磁盘访问才能查 TCC）"
  echo "     若表现为「路径已复制但没自动粘贴」，去系统设置 → 隐私与安全性 → 辅助功能勾上 Karabiner"
fi

sec "7. 绕开快捷键，直接跑 dropfile"
if [[ -x "$HOME/.local/bin/dropfile" ]]; then
  out="$("$HOME/.local/bin/dropfile" 2>&1)" && ok "推送成功 → $out" || echo "     输出: $out"
  echo "     （剪贴板为空时报「剪贴板里既没有文件也没有图片」是正常的）"
else
  bad "dropfile 不存在，跳过"
fi

cat <<'EOF'

══════════════════════════════════════════
  怎么读这份结果
══════════════════════════════════════════
  第 0 节说你在 SSH 里     → 跑错机器了，去本地那台重跑
  第 3 节 Karabiner 未装/未跑 → 装上并打开一次，再重跑安装器
  第 4 节没有规则          → 重跑安装器（别加 --no-karabiner）
  第 4 节 profile 未选中    → Karabiner → Profiles 选中它
  第 7 节能推送但快捷键没反应 → 是触发环节的问题，不是 dropfile 的问题

  按快捷键后若收到英文的
  "No image found in clipboard. You're SSH'd; try scp?"
  —— 那是**远端的 Claude Code** 在说话，说明按键穿透了本地 Karabiner
  直接传到了远端，即快捷键完全没被拦截。重点查第 0/3/4 节。
EOF
