#!/bin/bash
# Terminal-type detection from environment variables.
# Sets globals: terminal_type, claude_session_id, desktop_session_id
#
# The Claude desktop app (Code tab) is checked first: it is the most specific
# signal (entrypoint/bundle id AND a well-formed host session id) and it sets
# none of the terminal variables the other branches look at, so it cannot
# shadow them.
#
# When inside tmux, the script additionally walks the tmux client's
# process ancestry to identify the host GUI app (iTerm2 / Cursor / VS Code)
# so we can pick the right jump path. Without this, a tmux session hosted
# inside Cursor's integrated terminal would be misclassified as iterm+tmux
# and the jump would fail to find an iTerm session.

detect_terminal() {
    terminal_type=""
    claude_session_id=""
    desktop_session_id=""

    if _detect_claude_desktop; then
        terminal_type="claude-desktop"
    elif [ -n "$TMUX" ] && [ -n "$TMUX_PANE" ]; then
        local host
        host=$(_detect_tmux_host)
        case "$host" in
            cursor)  terminal_type="cursor+tmux" ;;
            vscode)  terminal_type="vscode+tmux" ;;
            iterm)   terminal_type="iterm+tmux" ;;
            *)       terminal_type="iterm+tmux" ;;  # fallback: assume iTerm
        esac
    elif [ -n "$ITERM_SESSION_ID" ]; then
        terminal_type="iterm"
        claude_session_id="${ITERM_SESSION_ID##*:}"
    elif [[ "$VSCODE_GIT_ASKPASS_NODE" == *"Cursor.app"* ]]; then
        terminal_type="cursor"
    elif [[ "$VSCODE_GIT_ASKPASS_NODE" == *"Visual Studio Code"* ]]; then
        terminal_type="vscode"
    elif [ "$TERM_PROGRAM" = "vscode" ]; then
        terminal_type="cursor"
    else
        terminal_type="unknown"
    fi
}

# Claude desktop app (Code tab) detection.
# Sets desktop_session_id and returns 0 when the hook is running inside a
# desktop-hosted Claude Code session.
#
# The host injects CLAUDE_CODE_HOST_SESSION_ID (its own session id, distinct
# from CLAUDE_CODE_SESSION_ID which is the CLI's). It is what the
# claude://code/continue deep link expects, so an id that fails the app's own
# regex is useless to us — in that case we report "not desktop" and let the
# remaining branches run rather than producing a terminal_type we cannot act on.
_detect_claude_desktop() {
    [ "$CLAUDE_CODE_ENTRYPOINT" = "claude-desktop" ] \
        || [ "$__CFBundleIdentifier" = "com.anthropic.claudefordesktop" ] \
        || return 1
    [[ "$CLAUDE_CODE_HOST_SESSION_ID" =~ ^local_[A-Za-z0-9-]{1,64}$ ]] || return 1
    desktop_session_id="$CLAUDE_CODE_HOST_SESSION_ID"
    return 0
}

# Identify the GUI app hosting the current tmux session by walking the
# parent process tree from the tmux client's tty up to a known terminal app.
# Output: "iterm" | "cursor" | "vscode" | "" (if undetermined)
#
# Requires: tmux, lsof, ps
_detect_tmux_host() {
    command -v tmux >/dev/null 2>&1 || return 1
    command -v lsof >/dev/null 2>&1 || return 1

    local session_id client_tty pid cmd depth

    session_id=$(tmux display-message -t "$TMUX_PANE" -p '#{session_id}' 2>/dev/null)
    [ -z "$session_id" ] && return 1

    client_tty=$(tmux list-clients -t "$session_id" -F '#{client_tty}' 2>/dev/null | head -1)
    [ -z "$client_tty" ] && return 1

    # The tty is held by a shell whose ancestor chain reaches the GUI app.
    pid=$(lsof -t "$client_tty" 2>/dev/null | head -1)
    [ -z "$pid" ] && return 1

    depth=0
    while [ -n "$pid" ] && [ "$pid" != "1" ] && [ "$depth" -lt 20 ]; do
        cmd=$(ps -p "$pid" -o comm= 2>/dev/null)
        case "$cmd" in
            *iTerm*)
                echo "iterm"
                return 0
                ;;
            *Cursor*)
                echo "cursor"
                return 0
                ;;
            */Visual\ Studio\ Code* | */Code\ Helper* | *Electron*Visual*)
                echo "vscode"
                return 0
                ;;
        esac
        pid=$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d ' ')
        depth=$((depth + 1))
    done
    return 1
}
