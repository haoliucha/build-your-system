#!/usr/bin/env bash
# extract-frames.sh — 录屏固定节奏抽帧 + 编号 contact sheet(帧号→时间映射)
#
# 用法:
#   bash extract-frames.sh <video> <outdir> [fps] [cols]
#     fps   抽帧节奏,默认 1(每秒 1 帧;慢操作录屏可 0.5,操作密集可 2)
#     cols  contact sheet 每行帧数,默认 6(每张 sheet 6x5 = 30 帧)
#
# 产物:
#   <outdir>/frames/f0001.png ...    全分辨率原帧(关键画面精读用)
#   <outdir>/sheets/sheet_00.png ... 带帧号标签的 contact sheet(定位用)
#
# 帧号→时间: fps=F 时,fNNNN 的 N 对应约 (N-1)/F 秒
#
# 设计说明:
# - 刻意不用 ffmpeg select='gt(scene,T)' 场景检测——移动应用录屏的滚动与
#   转场动画会击穿帧差法(阈值高漏真切换、阈值低爆冗余),固定节奏最稳。
# - macOS 下 montage -label 不显式指定字体文件路径会静默不渲染标签,
#   此处内置系统字体探测;其他平台用 FONT=/path/to/font 环境变量传入。
#
# 依赖: ffmpeg + ImageMagick 7 (magick)。macOS: brew install ffmpeg imagemagick
set -euo pipefail

VIDEO="${1:?用法: extract-frames.sh <video> <outdir> [fps] [cols]}"
OUTDIR="${2:?需要输出目录}"
FPS="${3:-1}"
COLS="${4:-6}"
ROWS=5

command -v ffmpeg >/dev/null 2>&1 || { echo "缺 ffmpeg: brew install ffmpeg" >&2; exit 1; }
command -v magick >/dev/null 2>&1 || { echo "缺 ImageMagick 7: brew install imagemagick" >&2; exit 1; }
[ -f "$VIDEO" ] || { echo "视频不存在: $VIDEO" >&2; exit 1; }

# 字体探测(macOS 优先;标签为纯数字/字母,Helvetica 足够)
FONT="${FONT:-}"
if [ -z "$FONT" ]; then
  for f in "/System/Library/Fonts/Helvetica.ttc" \
           "/System/Library/Fonts/Supplemental/Arial.ttf" \
           "/System/Library/Fonts/PingFang.ttc"; do
    if [ -f "$f" ]; then FONT="$f"; break; fi
  done
fi
[ -n "$FONT" ] || { echo "找不到系统字体,请传 FONT=/path/to/font" >&2; exit 1; }

mkdir -p "$OUTDIR/frames" "$OUTDIR/sheets"
rm -f "$OUTDIR/frames/"f*.png "$OUTDIR/sheets/"sheet_*.png

echo "[1/2] 固定节奏抽帧 fps=$FPS ..."
ffmpeg -hide_banner -loglevel error -i "$VIDEO" -vf "fps=$FPS" "$OUTDIR/frames/f%04d.png"

N=$(find "$OUTDIR/frames" -name 'f*.png' | wc -l | tr -d ' ')
[ "$N" -gt 0 ] || { echo "抽帧结果为 0,请检查视频文件" >&2; exit 1; }
echo "  抽出 $N 帧;帧号→时间: fNNNN 的 N ≈ (N-1)/$FPS 秒"

echo "[2/2] 生成编号 contact sheet (font=$FONT) ..."
magick montage "$OUTDIR/frames/"f*.png \
  -font "$FONT" -pointsize 30 -label '%t' \
  -tile "${COLS}x${ROWS}" -geometry 320x+6+6 \
  -background '#1e1e1e' -fill white \
  "$OUTDIR/sheets/sheet_%02d.png"

S=$(find "$OUTDIR/sheets" -name 'sheet_*.png' | wc -l | tr -d ' ')
echo "完成: $N 帧 / $S 张 sheet → $OUTDIR"
echo ""
echo "下一步(必做): 先打开第一张 sheet 自检——帧号标签是否渲染、缩略图能否辨认界面;"
echo "确认可读后再批量检查全部 sheet;关键画面回看 frames/fNNNN.png 全分辨率原帧。"
