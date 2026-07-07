#!/usr/bin/env bash
#
# cover-gen.sh — X 文章封面一键流水线(codex imagegen 直出 2.5:1 → 后处理 → 门禁 → 缩略图)
#
# 用法:
#   cover-gen.sh gen  <文章目录> <prompt文件>   # codex exec headless 直出(纪律句由本脚本注入,prompt 只写画面内容)
#   cover-gen.sh from <原图>     <文章目录>     # 已有原图(如 Codex 桌面 app 出的)只走后处理+门禁
#   cover-gen.sh selftest                       # 自检(不调 codex)
#
# 产物:<文章目录>/images/cover.png(2.5:1)+ thumb-375.png + src/cover-raw-<WxH>.png(原图留档)
# 出图纪律真源 = 本脚本 gen 模式的注入段(禁叠字/禁 glow/带单位/单曲线/中文逐字/自查重出 ≤1 次)。
# X 文章封面框 = 2.5:1(CDN 实存 900×360);非 2.5:1 上传会被 X 中心裁切丢内容。
# 依赖:codex CLI(gen 模式)+ imagegen skill(gpt-image-2)+ magick + sips(macOS)。
# 门禁:比例 2.45–2.55;FAIL → 退出码 1。
#
set -uo pipefail

SIZE="2400x960"            # 2.5:1,gpt-image-2 任意尺寸约束内(边 16 倍数、比例 ≤3:1)
FAILS=0
fail() { echo "FAIL  $1"; FAILS=$((FAILS+1)); }
warn() { echo "WARN  $1"; }
ok()   { echo "ok    $1"; }

need() { command -v "$1" >/dev/null 2>&1 || { echo "FAIL  缺 $1"; exit 1; }; }

dims() { # $1 图片 → 输出 "W H"
  local w h
  w=$(sips -g pixelWidth  "$1" 2>/dev/null | awk '/pixelWidth/{print $2}')
  h=$(sips -g pixelHeight "$1" 2>/dev/null | awk '/pixelHeight/{print $2}')
  [ -n "$w" ] && [ -n "$h" ] && echo "$w $h"
}

# ---------- 后处理:原图 → cover.png(2.5:1)+ thumb + 留档 ----------
postprocess() { # $1 原图, $2 文章目录
  local RAW="$1" DIR="$2"
  [ -f "$RAW" ] || { fail "原图不存在: $RAW"; return 1; }
  [ -d "$DIR" ] || { fail "文章目录不存在: $DIR"; return 1; }
  mkdir -p "$DIR/images/src"

  local WH W H R
  WH=$(dims "$RAW") || true
  [ -n "${WH:-}" ] || { fail "读不到原图尺寸: $RAW"; return 1; }
  W=${WH% *}; H=${WH#* }
  R=$(awk -v w="$W" -v h="$H" 'BEGIN{printf "%.3f", w/h}')

  local COVER="$DIR/images/cover.png" TMPOUT
  TMPOUT="$(mktemp -t coverXXXX).png"

  if awk -v r="$R" 'BEGIN{exit !(r>=2.45 && r<=2.55)}'; then
    ok "原图 ${W}×${H} = ${R}:1,已是 2.5:1(直出),不裁切"
    magick "$RAW" "$TMPOUT" || { fail "magick 转换失败"; return 1; }
  elif awk -v r="$R" 'BEGIN{exit !(r>=2.25 && r<=3.00)}'; then
    # 近轴自愈:比例接近 2.5:1(直出取整偏差)→ 居中裁到精确 2.5:1,损失 ≤9%
    local NW NH
    if awk -v r="$R" 'BEGIN{exit !(r<2.5)}'; then
      NW=$W; NH=$(awk -v w="$W" 'BEGIN{printf "%d", w/2.5}')     # 偏窄 → 裁高
    else
      NH=$H; NW=$(awk -v h="$H" 'BEGIN{printf "%d", h*2.5}')     # 偏宽 → 裁宽
    fi
    warn "原图 ${W}×${H} = ${R}:1(近 2.5:1)→ 居中裁到 ${NW}×${NH}"
    magick "$RAW" -gravity center -crop "${NW}x${NH}+0+0" +repage "$TMPOUT" || { fail "裁切失败"; return 1; }
  elif awk -v r="$R" 'BEGIN{exit !(r>=1.40 && r<=1.60)}'; then
    # 兜底:旧"安全带构图"3:2 原图(内容压中央 2.5:1 带)→ 裁中央
    local CH2
    CH2=$(awk -v w="$W" 'BEGIN{printf "%d", w/2.5}')
    warn "原图 ${W}×${H} = ${R}:1(3:2 安全带构图)→ 裁中央 ${W}×${CH2};新封面请直接按 2.5:1 直出"
    magick "$RAW" -gravity center -crop "${W}x${CH2}+0+0" +repage "$TMPOUT" || { fail "裁切失败"; return 1; }
  else
    fail "原图 ${W}×${H} = ${R}:1,既非 2.5:1 也非近轴/3:2 安全带 → 按 2.5:1 横幅构图重出"
    return 1
  fi

  # 覆盖前留档旧封面;原图存 src
  if [ -f "$COVER" ]; then
    cp "$COVER" "$DIR/images/src/cover-prev-$(date +%Y%m%d-%H%M%S).png"
    ok "旧封面已留档 images/src/cover-prev-*.png"
  fi
  cp "$TMPOUT" "$COVER"; rm -f "$TMPOUT"
  [ "$RAW" -ef "$COVER" ] 2>/dev/null || cp "$RAW" "$DIR/images/src/cover-raw-${W}x${H}.png"
  magick "$COVER" -resize 375x "$DIR/images/thumb-375.png" || warn "缩略图生成失败"

  # 门禁(X 封面框 2.5:1,容差 2.45–2.55)
  WH=$(dims "$COVER"); W=${WH% *}; H=${WH#* }
  R=$(awk -v w="$W" -v h="$H" 'BEGIN{printf "%.3f", w/h}')
  if awk -v r="$R" 'BEGIN{exit !(r>=2.45 && r<=2.55)}'; then
    ok "封面比例门禁 ${W}×${H} = ${R}:1(X 框 2.5:1)"
  else
    fail "封面比例 ${W}×${H} = ${R}:1 ≠ 2.5:1"
    return 1
  fi

  echo ""
  echo "===== 人工/agent QC(机器判不了,逐条看)====="
  echo "  1. Read $DIR/images/thumb-375.png:主标题+主数字可读?中文零乱码?(单次生成有文字方差,逐字校对不可省)"
  echo "  2. 无 glow/外发光/霓虹光晕?文字锐利实心?"
  echo "  3. 大数字带单位?曲线单条干净(非散点+阶梯伪图表)?"
  echo "  4. 单一图形钩子 = 文章核心观察?"
  echo "  5. 封面上的数字/榜位是时效 peg,草稿滞留后发布前要重核"
  echo "  6. X 上传后会弹 2.5:1 裁切框,必须点「应用」;本图已是 2.5:1 = 无操作裁切"
  echo "  (op-x 项目另见 playbook/visual.md 评审协议:冲高分用同评审「修复→复审」收敛)"
}

# ---------- gen:codex headless 直出 ----------
do_gen() { # $1 文章目录, $2 prompt 文件(只写画面内容)
  local DIR="$1" PF="$2"
  [ -f "$PF" ] || { echo "FAIL  prompt 文件不存在: $PF"; exit 1; }
  need codex; need magick; need sips
  local WORK RAWOUT LOG
  WORK="$(mktemp -d -t covergenXXXX)"
  RAWOUT="$WORK/raw.png"; LOG="$WORK/codex.log"

  # 纪律句机器注入(人只写画面内容,别在 prompt 里重复这些)
  {
    echo "用 imagegen skill 的 image_gen 工具直出整张 X 文章封面(含全部文字),size 参数传 \"${SIZE}\"(= 2.5:1,X 封面框;gpt-image-2 支持任意 WIDTHxHEIGHT)。若工具对尺寸取整,不必重试凑精确像素——**成图宽高比必须在 2.45:1 到 2.55:1 之间**即合格,否则才重出。整张一次性直出,按 2.5:1 横幅构图。"
    echo ""
    cat "$PF"
    echo ""
    echo "硬纪律(违反任何一条 = 重做):"
    echo "1. 禁止事后本地叠字/排版合成/二次编辑;禁止写任何渲染脚本(Swift/PIL/ImageMagick/SVG 一律禁止)。所有文字由 image_gen 生成时直接画进图里。"
    echo "2. 硬禁 glow/外发光/渐变雾/霓虹光晕;文字线条锐利实心。"
    echo "3. 大数字必须带单位;趋势只画单条干净曲线,不画散点+阶梯柱拼凑的伪图表。"
    echo "4. 中文逐字正确(Hiragino Sans GB 观感)、英文/仓库名逐字符正确;图标/方框/箭头/星形自己画,不用 emoji。"
    echo ""
    echo "生成次数上限:首张有明显硬伤(乱码/伪图表/glow/比例错)时最多自查重出 1 次(全程 ≤2 次生成);字距/微调级瑕疵不重出,如实报告即可——精修由外部评审流程负责,别烧配额。"
    echo ""
    echo "输出协议:生成成功后把你本会话刚生成的图 cp 到 ${RAWOUT},然后输出一行 \"RESULT: OK\";若 image_gen 工具不可用或失败,输出 \"RESULT: FAIL <原因>\" 并停止,禁止用其他方式生成。"
  } > "$WORK/prompt.txt"

  echo "codex 直出中(size ${SIZE},日志 $LOG)…"
  local T0; T0=$(date +%s)
  codex exec --skip-git-repo-check -c service_tier="fast" - < "$WORK/prompt.txt" > "$LOG" 2>&1
  local RC=$?

  if ! grep -q "RESULT: OK" "$LOG"; then
    echo "FAIL  codex 未报 RESULT: OK(exit $RC)。日志尾部:"
    tail -5 "$LOG" | sed 's/^/  | /'
    grep -qiE "usage limit|rate limit|try again" "$LOG" && echo "  ↑ 疑似用量上限,稍后重跑"
    exit 1
  fi
  [ -f "$RAWOUT" ] || { echo "FAIL  codex 报 OK 但产物不存在: $RAWOUT(别信模型自报路径)"; exit 1; }
  # 新鲜度:产物必须晚于本次启动(防 codex 拷了陈图)
  local MT; MT=$(stat -f %m "$RAWOUT" 2>/dev/null || stat -c %Y "$RAWOUT" 2>/dev/null)
  [ "${MT:-0}" -ge "$T0" ] || { echo "FAIL  产物 mtime 早于本次生成,疑似陈图: $RAWOUT"; exit 1; }
  ok "codex 直出成功: $RAWOUT"

  postprocess "$RAWOUT" "$DIR"
}

# ---------- selftest:不调 codex,验证后处理+门禁 ----------
do_selftest() {
  need magick; need sips
  local TMP PASS=0 FAILED=0
  TMP="$(mktemp -d -t coverstXXXX)"
  trap "rm -rf '$TMP'" EXIT
  chk() { if [ "$2" -eq "$3" ]; then echo "PASS  $1"; PASS=$((PASS+1)); else echo "FAIL  $1 (期望 $2 实得 $3)"; FAILED=$((FAILED+1)); fi; }

  # A. 2.5:1 直出原图 → 不裁切直过
  mkdir -p "$TMP/a"; magick -size 2400x960 xc:'#0b1322' "$TMP/raw-a.png"
  ( postprocess "$TMP/raw-a.png" "$TMP/a" ) >/dev/null 2>&1; chk "2.5:1 直出原图应 PASS" 0 $?
  [ -f "$TMP/a/images/cover.png" ] && [ -f "$TMP/a/images/thumb-375.png" ] \
    && { echo "PASS  产出 cover.png + thumb-375.png"; PASS=$((PASS+1)); } \
    || { echo "FAIL  缺 cover/thumb 产物"; FAILED=$((FAILED+1)); }

  # B. 3:2 安全带原图 → 裁中央后过门禁(兜底路径)
  mkdir -p "$TMP/b"; magick -size 1536x1024 xc:'#0b1322' "$TMP/raw-b.png"
  ( postprocess "$TMP/raw-b.png" "$TMP/b" ) >/dev/null 2>&1; chk "3:2 安全带原图应裁切后 PASS" 0 $?
  local WH; WH=$(dims "$TMP/b/images/cover.png")
  awk -v w="${WH% *}" -v h="${WH#* }" 'BEGIN{exit !(w/h>=2.45 && w/h<=2.55)}' \
    && { echo "PASS  裁切产物比例在门禁内($WH)"; PASS=$((PASS+1)); } \
    || { echo "FAIL  裁切产物比例出界($WH)"; FAILED=$((FAILED+1)); }

  # C. 错比例(1:1)→ FAIL
  mkdir -p "$TMP/c"; magick -size 800x800 xc:'#0b1322' "$TMP/raw-c.png"
  ( postprocess "$TMP/raw-c.png" "$TMP/c" ) >/dev/null 2>&1; chk "错比例原图应 FAIL" 1 $?

  # E. 近轴原图(2048×880 = 2.33:1)→ 自愈裁切后 PASS
  mkdir -p "$TMP/e"; magick -size 2048x880 xc:'#0b1322' "$TMP/raw-e.png"
  ( postprocess "$TMP/raw-e.png" "$TMP/e" ) >/dev/null 2>&1; chk "近轴原图应自愈裁切后 PASS" 0 $?
  WH=$(dims "$TMP/e/images/cover.png")
  awk -v w="${WH% *}" -v h="${WH#* }" 'BEGIN{exit !(w/h>=2.45 && w/h<=2.55)}' \
    && { echo "PASS  近轴自愈产物比例在门禁内($WH)"; PASS=$((PASS+1)); } \
    || { echo "FAIL  近轴自愈产物比例出界($WH)"; FAILED=$((FAILED+1)); }

  # D. 覆盖保护:已有 cover.png 再跑一次 → 旧图留档 cover-prev-*
  ( postprocess "$TMP/raw-a.png" "$TMP/a" ) >/dev/null 2>&1
  ls "$TMP/a/images/src/"cover-prev-*.png >/dev/null 2>&1 \
    && { echo "PASS  旧封面覆盖前留档"; PASS=$((PASS+1)); } \
    || { echo "FAIL  旧封面未留档"; FAILED=$((FAILED+1)); }

  echo ""
  echo "cover-gen selftest: $FAILED fail"
  [ "$FAILED" -eq 0 ] || exit 1
  echo "封面流水线自测通过 ✓"
}

case "${1:-}" in
  gen)      DIR="${2:?用法: cover-gen.sh gen <文章目录> <prompt文件>}"; PF="${3:?缺 prompt 文件}"; do_gen "$DIR" "$PF"; [ "$FAILS" -eq 0 ] || exit 1 ;;
  from)     RAW="${2:?用法: cover-gen.sh from <原图> <文章目录>}"; DIR="${3:?缺文章目录}"; need magick; need sips; postprocess "$RAW" "$DIR"; [ "$FAILS" -eq 0 ] || exit 1 ;;
  selftest) do_selftest ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
