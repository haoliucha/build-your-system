#!/bin/bash
# Load user context at session start.
# 检测当前目录是否是有效 Vault；未初始化时只显示引导，已初始化时优先使用
# session-context.py，失败则回退到下面的 Bash 拼接。Hook 无论如何都不阻断宿主。

# 检查必需目录（PARA + GTD + Memory）。
REQUIRED_DIRS=("00-Inbox" "10-Projects" "20-Areas" "30-Resources" "40-Archives" "50-GTD" "60-Memory")
MISSING_DIRS=()

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        MISSING_DIRS+=("$dir")
    fi
done

# profile.md 有实际内容且必需目录齐全时，视为已完成初始化。
SETUP_COMPLETE=false
if [ -f "60-Memory/profile.md" ]; then
    LINE_COUNT=$(wc -l < "60-Memory/profile.md" 2>/dev/null | tr -d ' ')
    if [ "${LINE_COUNT:-0}" -gt 5 ]; then
        SETUP_COMPLETE=true
    fi
fi

if [ ${#MISSING_DIRS[@]} -gt 0 ] || [ "$SETUP_COMPLETE" = false ]; then
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  Personal Assistant Plugin (CODE+)                       ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
    echo "【系统状态：未初始化】"
    echo ""

    if [ ${#MISSING_DIRS[@]} -gt 0 ]; then
        echo "缺失目录: ${MISSING_DIRS[*]}"
    fi
    if [ "$SETUP_COMPLETE" = false ]; then
        echo "用户画像: 未配置"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "【重要】检测到首次使用，请立即运行 /assistant:a-setup 完成初始化。"
    echo "初始化后可使用 /assistant:c-capture 捕获内容和 /assistant:o-tasks 查看任务。"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Claude：请先告知用户需要完成初始化，并询问是否现在运行 /assistant:a-setup。"
    exit 0
fi

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
echo "插件根目录: $PLUGIN_ROOT"

# 统一脚本输出为空或失败时的兼容回退，保留旧 hook 的关键上下文。
fallback_context() {
    echo "## 快速上下文加载"
    echo ""

    if [ -f "60-Memory/profile.md" ]; then
        echo "### 用户画像"
        awk '
            NR == 1 && $0 == "---" { in_frontmatter = 1; next }
            in_frontmatter && $0 == "---" { in_frontmatter = 0; closed = 1; next }
            !in_frontmatter { print }
        ' "60-Memory/profile.md"
        echo ""
    fi

    if [ -f "60-Memory/preferences.md" ]; then
        echo "### 偏好配置"
        grep -E "起床时间|深度工作|结束工作|结束时间|上床时间|language|惩罚" "60-Memory/preferences.md" 2>/dev/null || echo "使用默认配置"
        echo ""
    fi

    if [ -f "50-GTD/active.md" ]; then
        echo "### 今日重点 (MIT)"
        sed -n '/^## 今日重点/,/^---/p' "50-GTD/active.md" | head -10
        echo ""
    fi

    echo "---"
    echo "当前时间: $(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M %A')"
}

CONTEXT_OUTPUT="$(python3 "$PLUGIN_ROOT/scripts/session-context.py" 2>/dev/null)"
PYTHON_STATUS=$?
if [ "$PYTHON_STATUS" -eq 0 ] && [ -n "$CONTEXT_OUTPUT" ]; then
    printf '%s\n' "$CONTEXT_OUTPUT"
else
    fallback_context
fi

exit 0
