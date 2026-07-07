#!/usr/bin/env bash
# check-residuals.sh — 残留词/敏感词清零校验(对抗审校 skill 配套脚本)
#
# 设计动机(实战教训固化):
#   1) `grep ... | head` 会掩盖 grep 退出码,造成「已清零」假阴性 → 本脚本判据只用 grep -c 计数。
#   2) 报错的检查 != 通过的检查 → 文件缺失/模式非法一律退出码 2,绝不混入「清零」。
#   3) 检查器本身要可反向验证 → selftest 注入已知脏词,确认本脚本真的抓得到。
#
# 用法:
#   bash check-residuals.sh scan <词表.txt> <文件...>
#   bash check-residuals.sh selftest
#
# 词表格式: 每行一个 grep -E 模式;空行与 # 开头行忽略。
# 退出码:   0=全部清零 / 1=存在命中(明细已打印,需人工分类) / 2=用法或检查本身错误
# 兼容性:   macOS BSD grep 与 GNU grep 均可(只用 -c/-n/-E);不使用 GNU 专属选项。
# 提醒:     命中≠泄露——「禁止出现XX」的规则自述要人工分类后再定性。

set -u

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

scan() {
  terms_file="${1:-}"
  [ -n "$terms_file" ] || usage
  shift
  [ -f "$terms_file" ] || { echo "ERROR: 词表不存在: $terms_file" >&2; exit 2; }
  [ "$#" -ge 1 ] || { echo "ERROR: 至少提供一个待查文件" >&2; exit 2; }

  # 先验:全部目标文件必须存在——文件缺失 = 检查报错,绝不算「清零」
  missing=0
  for f in "$@"; do
    [ -f "$f" ] || { echo "ERROR: 待查文件不存在: $f" >&2; missing=1; }
  done
  [ "$missing" -eq 0 ] || exit 2

  total=0
  patterns=0
  while IFS= read -r pat || [ -n "$pat" ]; do
    case "$pat" in ''|'#'*) continue ;; esac
    patterns=$((patterns + 1))
    for f in "$@"; do
      n="$(grep -c -E -- "$pat" "$f")"
      rc=$?
      # grep -c: 有命中 rc=0;无命中 rc=1 但仍打印 0;rc>=2 = grep 自身出错(如模式非法)
      if [ "$rc" -ge 2 ]; then
        echo "ERROR: grep 执行失败(rc=$rc) pattern='$pat' file=$f —— 检查报错不算通过" >&2
        exit 2
      fi
      if [ "${n:-0}" -gt 0 ]; then
        echo "HIT  count=$n  pattern='$pat'  file=$f"
        # 明细仅供人工分类展示;清零判据是上面的计数,不受此处影响
        grep -n -E -- "$pat" "$f" | sed -n '1,5p' | sed 's/^/       /'
        total=$((total + n))
      fi
    done
  done < "$terms_file"

  [ "$patterns" -ge 1 ] || { echo "ERROR: 词表无有效模式(全空/全注释)" >&2; exit 2; }

  if [ "$total" -eq 0 ]; then
    echo "CLEAN: $patterns 个模式在 $# 个文件中 0 命中"
    exit 0
  else
    echo "DIRTY: 共 $total 处命中 —— 人工分类后处理(注意:「禁止出现XX」的规则自述不是泄露)"
    exit 1
  fi
}

selftest() {
  tmpdir="$(mktemp -d)" || { echo "ERROR: mktemp 失败" >&2; exit 2; }
  trap 'rm -rf "$tmpdir"' EXIT

  terms="$tmpdir/terms.txt"
  dirty="$tmpdir/dirty.md"
  clean="$tmpdir/clean.md"
  printf '%s\n' '# 教学词表' 'FORBIDDEN_TOKEN_[0-9]+' > "$terms"
  printf '%s\n' '正文第一行' '这里埋一个 FORBIDDEN_TOKEN_100 已知脏词' > "$dirty"
  printf '%s\n' '干净文档,无脏词' > "$clean"

  echo "== selftest 1/3: 注入已知脏词,检查器必须抓到(期望 rc=1) =="
  ( scan "$terms" "$dirty" ) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 1 ] || { echo "SELFTEST FAIL: 期望 rc=1 实得 rc=$rc —— 检查器空转,不可信"; exit 2; }
  echo "PASS: 已知脏词被抓到"

  echo "== selftest 2/3: 干净文件必须清零(期望 rc=0) =="
  ( scan "$terms" "$clean" ) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 0 ] || { echo "SELFTEST FAIL: 期望 rc=0 实得 rc=$rc"; exit 2; }
  echo "PASS: 干净文件确认清零"

  echo "== selftest 3/3: 文件缺失必须按报错处理(期望 rc=2) =="
  ( scan "$terms" "$tmpdir/no-such-file.md" ) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 2 ] || { echo "SELFTEST FAIL: 期望 rc=2 实得 rc=$rc —— 报错被当通过"; exit 2; }
  echo "PASS: 报错的检查不等于通过的检查"

  echo "SELFTEST OK: 检查器有效性已反向验证"
  exit 0
}

case "${1:-}" in
  scan)     shift; scan "$@" ;;
  selftest) selftest ;;
  *)        usage ;;
esac
