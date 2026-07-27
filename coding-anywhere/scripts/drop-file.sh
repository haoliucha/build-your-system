#!/bin/bash
# drop-file.sh — 装在**远端主机**上。从 stdin 读 base64，解码落盘，回显绝对路径。
#
# 由客户端的 dropfile 通过 SSH 调用：
#   base64 < file.pdf | ssh user@host 'bash ~/bin/drop-file.sh "report.pdf"'
#
# 参数：
#   $1  原文件名（可选）。给了就沿用（经 sanitize），没给就按 mime 猜后缀。
#
# 输出：落盘文件的绝对路径（单行）—— 客户端会原样送进剪贴板。
#
# 安全：$1 来自客户端，不可信。必须 basename 去路径、剔除控制字符，
#       否则 "../../.ssh/authorized_keys" 这类文件名会写到 Drops 之外。
set -euo pipefail

DROP_DIR="${DROP_DIR:-$HOME/Drops}"
MAX_MB="${DROPFILE_MAX_MB:-15}"
MAX_BYTES=$(( MAX_MB * 1024 * 1024 ))
mkdir -p "$DROP_DIR"

ORIG_NAME="${1:-}"
TS="$(date +%Y%m%d_%H%M%S)"
TMP="$DROP_DIR/.drop_${TS}.$$"
B64="$DROP_DIR/.drop_${TS}.$$.b64"
trap 'rm -f "$TMP" "$B64"' EXIT

# tr 去空白：base64 常带换行分组，SSH 传输也可能引入 \r
tr -d '[:space:]' > "$B64"

# 解码标志跨平台：GNU coreutils 和新版 macOS 用 -d，旧版 macOS(BSD) 只有 -D
if ! base64 -d < "$B64" > "$TMP" 2>/dev/null; then
  if ! base64 -D < "$B64" > "$TMP" 2>/dev/null; then
    echo "ERROR: base64 decode failed" >&2
    exit 1
  fi
fi
rm -f "$B64"

if [[ ! -s "$TMP" ]]; then
  echo "ERROR: decoded payload empty" >&2
  exit 1
fi

# 大小复核。客户端已经拦过一次，这里是防御 —— 客户端可能被绕过或版本不一致
SIZE="$(wc -c < "$TMP" | tr -d ' ')"
if (( SIZE > MAX_BYTES )); then
  echo "ERROR: file is $((SIZE / 1024 / 1024))MB, exceeds ${MAX_MB}MB limit" >&2
  exit 1
fi

if [[ -n "$ORIG_NAME" ]]; then
  # ---- sanitize 客户端传来的文件名 ----
  NAME="$(basename -- "$ORIG_NAME")"          # 去掉任何路径成分
  NAME="$(printf '%s' "$NAME" | tr -d '[:cntrl:]')"  # 去控制字符
  NAME="${NAME// /_}"                          # 空格换下划线：终端里粘路径时空格会断开
  NAME="${NAME//\//_}"                         # 兜底：basename 之后不该还有 /
  case "$NAME" in
    ""|"."|"..") NAME="file" ;;
    .*)          NAME="_${NAME}" ;;            # 不生成隐藏文件
  esac
  DEST="$DROP_DIR/${TS}_${NAME}"               # 时间戳前缀，避免同名覆盖
else
  # ---- 没有文件名（剪贴板图片等）：按 mime 猜后缀 ----
  case "$(file -b --mime-type "$TMP")" in
    image/png)             EXT=png ;;
    image/jpeg)            EXT=jpg ;;
    image/heic|image/heif) EXT=heic ;;
    image/gif)             EXT=gif ;;
    image/webp)            EXT=webp ;;
    image/tiff)            EXT=tiff ;;
    application/pdf)       EXT=pdf ;;
    text/plain)            EXT=txt ;;
    application/zip)       EXT=zip ;;
    *)                     EXT=bin ;;
  esac
  DEST="$DROP_DIR/${TS}.${EXT}"
fi

mv "$TMP" "$DEST"
trap - EXIT

echo "$DEST"
