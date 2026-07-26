#!/bin/bash
# drop-image.sh — 装在**远端主机**上。从 stdin 读 base64，解码落盘，回显绝对路径。
#
# 由客户端的 dropimg 通过 SSH 调用：
#   base64 < image.png | ssh user@host 'bash ~/bin/drop-image.sh'
#
# 输出：落盘文件的绝对路径（单行，无多余内容）—— 客户端会原样送进剪贴板。
set -euo pipefail

DROP_DIR="${DROP_DIR:-$HOME/Drops}"
mkdir -p "$DROP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
TMP="$DROP_DIR/.drop_${TS}.bin"
trap 'rm -f "$TMP"' EXIT

# tr 去空白：base64 编码常带换行分组，且 SSH 传输可能引入 \r
B64="$DROP_DIR/.drop_${TS}.b64"
trap 'rm -f "$TMP" "$B64"' EXIT
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

# 用 file 检测真实 mime，而不是信任后缀：
# 剪贴板可能给出 HEIC，盲目命名成 .png 会让下游读图失败
case "$(file -b --mime-type "$TMP")" in
  image/png)             EXT=png ;;
  image/jpeg)            EXT=jpg ;;
  image/heic|image/heif) EXT=heic ;;
  image/gif)             EXT=gif ;;
  image/webp)            EXT=webp ;;
  image/tiff)            EXT=tiff ;;
  *)
    echo "ERROR: payload is not a recognized image type" >&2
    exit 1
    ;;
esac

DEST="$DROP_DIR/${TS}.${EXT}"
mv "$TMP" "$DEST"
trap - EXIT

echo "$DEST"
