#!/usr/bin/env bash
# extract-frames.sh — 长录屏固定节奏抽帧 + 编号 contact sheet + 像素取样
# 依赖: ffmpeg + ImageMagick 7 (magick/montage)。macOS: brew install ffmpeg imagemagick
# 方法背景见 ../references/screencast-frame-sampling.md
set -euo pipefail

cmd="${1:-}"
shift || true

case "$cmd" in
  frames)
    video="${1:?用法: extract-frames.sh frames <录屏文件> <输出目录> [间隔秒,默认3]}"
    outdir="${2:?缺输出目录}"
    interval="${3:-3}"
    mkdir -p "$outdir"
    # 固定节奏采样。禁用 mpdecimate 运动去重——滚动动画会击穿它产出海量冗余帧。
    ffmpeg -hide_banner -loglevel error -i "$video" -vf "fps=1/${interval}" -q:v 2 "$outdir/f%04d.jpg"
    count=$(find "$outdir" -name 'f*.jpg' | wc -l | tr -d ' ')
    echo "抽帧完成: ${count} 帧 → $outdir (间隔 ${interval}s)"
    ;;

  sheet)
    framesdir="${1:?用法: extract-frames.sh sheet <帧目录> <输出目录> [每行列数,默认6]}"
    outdir="${2:?缺输出目录}"
    cols="${3:-6}"
    per_sheet=$((cols * cols))
    mkdir -p "$outdir"
    files=()
    while IFS= read -r f; do files+=("$f"); done < <(find "$framesdir" -name 'f*.jpg' | sort)
    total=${#files[@]}
    [ "$total" -gt 0 ] || { echo "错误: $framesdir 下没有 f*.jpg 帧" >&2; exit 1; }
    sheet=1
    for ((i = 0; i < total; i += per_sheet)); do
      chunk=("${files[@]:i:per_sheet}")
      montage -label '%f' "${chunk[@]}" -tile "${cols}x" -geometry '320x+4+4' \
        "$outdir/sheet-$(printf '%02d' "$sheet").png"
      sheet=$((sheet + 1))
    done
    echo "contact sheet 完成: $((sheet - 1)) 张 → $outdir"
    echo "阅读纪律: 先通读 sheet 定位关注帧编号,再回原帧放大细读(勿逐帧 Read 全部原图)"
    ;;

  pixel)
    img="${1:?用法: extract-frames.sh pixel <图片> <x> <y>}"
    x="${2:?缺 x 坐标}"
    y="${3:?缺 y 坐标}"
    # 输出该点 hex 色值。取样纪律: 选稳定帧(避开转场/滚动帧),多帧交叉验证。
    magick "$img" -format "#%[hex:p{$x,$y}]\n" info:
    ;;

  *)
    cat <<'EOF'
用法:
  extract-frames.sh frames <录屏文件> <输出目录> [间隔秒=3]   固定节奏抽帧
  extract-frames.sh sheet  <帧目录>   <输出目录> [列数=6]     拼编号 contact sheet
  extract-frames.sh pixel  <图片> <x> <y>                     取样单点像素 hex 色值
EOF
    exit 1
    ;;
esac
