#!/usr/bin/env python3
"""中继 ECS 上的 ForceCommand 分流器：按登录用户把会话透传到对应的后端 Mac。

部署位置：ECS 的 /usr/local/bin/coding-anywhere-forwarder（由 sshd_config 的
`Match User <relay-user>` → `ForceCommand env CA_* ... <此脚本>` 调起）。
这个文件是线上那份的**源**，改完必须 scp 回 ECS 才生效，见
skills/coding-anywhere/references/ecs-relay-blueprint.md §3.4。

三条出路（客户端看不到自己被转发了两跳）：
  - 无 SSH_ORIGINAL_COMMAND → 交互式登录，带 pty 进后端登录 shell
  - 命令里含 mosh-server   → mosh-server 在 ECS 本机起，remote command 再透传到后端
  - 其他                   → 原样透传，pty 与否跟随客户端（见 client_requested_tty）
"""

import json
import os
import shlex
import sys
from typing import List, Optional, Tuple


def required_env(name: str) -> str:
    """路由参数没有默认值 —— 缺了就断连,不猜。

    这三个变量决定"连到哪台后端",给默认值意味着配错时用户会连上一台
    能用但不是自己那台的机器 —— 比连不上更难排查(而且是静默的)。
    """
    value = os.environ.get(name, "").strip()
    if not value:
        sys.stderr.write(
            f"coding-anywhere-forwarder: 缺少 {name}"
            "（应由 sshd_config 的 Match 块用 ForceCommand env ... 注入）\n"
        )
        raise SystemExit(78)  # EX_CONFIG
    return value


SSH_BIN = os.environ.get("CA_SSH_BIN", "/usr/bin/ssh")
MOSH_SERVER_BIN = os.environ.get("CA_MOSH_SERVER_BIN", "/usr/bin/mosh-server")
IDENTITY_FILE = required_env("CA_IDENTITY_FILE")
BACKEND_USER = required_env("CA_BACKEND_USER")
BACKEND_PORT = required_env("CA_BACKEND_PORT")
KNOWN_HOSTS_FILE = os.environ.get(
    "CA_KNOWN_HOSTS_FILE", os.path.expanduser("~/.ssh/known_hosts.coding-anywhere")
)
BACKEND_HOST = os.environ.get("CA_BACKEND_HOST", "127.0.0.1")
DRY_RUN = os.environ.get("CA_FORCECOMMAND_DRY_RUN") == "1"
FORCED_MOSH_PORT = os.environ.get("CA_FORCED_MOSH_PORT", "").strip()
LOG_FILE = os.environ.get("CA_LOG_FILE", "/tmp/coding-anywhere-forwarder.log")


def backend_ssh_base(force_tty: bool) -> List[str]:
    argv = [
        SSH_BIN,
        "-i",
        IDENTITY_FILE,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS_FILE}",
        "-p",
        BACKEND_PORT,
    ]
    if force_tty:
        argv.append("-tt")
    argv.append(f"{BACKEND_USER}@{BACKEND_HOST}")
    return argv


def emit(mode: str, argv: List[str]) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "mode": mode,
                        "original": os.environ.get("SSH_ORIGINAL_COMMAND", ""),
                        "argv": argv,
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    if DRY_RUN:
        print(json.dumps({"mode": mode, "argv": argv}))
        return
    os.execv(argv[0], argv)


def safe_split(command: str) -> List[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def shell_join(argv: List[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def is_mosh_server_token(token: str) -> bool:
    return os.path.basename(token) == "mosh-server"


def find_mosh_server_index(candidate: List[str]) -> Optional[int]:
    """找真正的 mosh 启动形态 —— `mosh-server new ...`,必须连 `new` 一起认。

    只认 basename 的话,`ssh relay 'command -v mosh-server'` 这种仅仅**提到**
    可执行文件名的命令会被误判成启动请求:ECS 上凭空起一个 mosh-server,
    而用户真正想跑的命令根本没送到后端。
    """
    for index, token in enumerate(candidate[:-1]):
        if is_mosh_server_token(token) and candidate[index + 1] == "new":
            return index
    return None


def client_requested_tty() -> bool:
    """第二跳要不要 PTY —— 直接跟随客户端在第一跳的请求。

    sshd 只在客户端显式要终端（`ssh -t` / 无命令的交互式登录）时，才给
    ForceCommand 分配 pty；管道式调用（dropfile 的 `base64 | ssh host '...'`）
    拿到的是普通 pipe。所以 isatty(0) 就是"客户端想不想要终端"的权威答案。

    曾经这里靠解析命令字符串猜（只认 tmux attach|attach-session），
    结果 `tmux new-session -A`（attach-or-create，同样要终端）落到无 pty 分支，
    在后端报 "open terminal failed: not a terminal"。猜命令永远补不全，
    而 PTY 本来就是连接层的属性，不是命令的属性。
    """
    return sys.stdin.isatty()


def normalize_tmux_args(remote_command: List[str]) -> List[str]:
    if not remote_command or remote_command[0] != "tmux":
        return remote_command

    normalized = [remote_command[0]]
    index = 1
    while index < len(remote_command):
        current = remote_command[index]
        if (
            current == "-"
            and index + 1 < len(remote_command)
            and len(remote_command[index + 1]) == 1
            and remote_command[index + 1].isalpha()
        ):
            normalized.append("-" + remote_command[index + 1])
            index += 2
            continue
        normalized.append(current)
        index += 1
    return normalized


def render_remote_command(remote_command: List[str]) -> str:
    if not remote_command:
        return ""
    remote_command = normalize_tmux_args(remote_command)
    if remote_command[0] != "tmux":
        return shell_join(remote_command)
    # ssh concatenates remote command argv into a single shell string, so the
    # zsh -lc wrapper must already be shell-quoted as one argument.
    shell_command = f"DISABLE_AUTO_TMUX=1 {shell_join(remote_command)}; exec /bin/zsh -l"
    return shell_join(["/bin/zsh", "-lc", shell_command])


def extract_mosh_forwarded_args(original: str) -> Optional[Tuple[List[str], List[str]]]:
    args = safe_split(original)
    candidates: List[List[str]] = []

    if args:
        candidates.append(args)
        for token in args:
            if "mosh-server" in token:
                nested = safe_split(token)
                if nested:
                    candidates.append(nested)

    if "mosh-server" in original:
        snippet = original[original.index("mosh-server") :]
        snippet_args = safe_split(snippet)
        if snippet_args:
            candidates.append(snippet_args)
        else:
            candidates.append(snippet.split())

    for candidate in candidates:
        mosh_index = find_mosh_server_index(candidate)
        if mosh_index is None:
            continue
        forwarded = []
        remote_command = []
        saw_port = False
        after_separator = False
        for arg in candidate[mosh_index + 1 :]:
            if after_separator:
                remote_command.append(arg)
                continue
            if arg == "--":
                after_separator = True
                continue
            if arg == "-p":
                saw_port = True
            forwarded.append(arg)
        if FORCED_MOSH_PORT and not saw_port:
            forwarded.extend(["-p", FORCED_MOSH_PORT])
        return forwarded, remote_command

    return None


def main() -> int:
    original = os.environ.get("SSH_ORIGINAL_COMMAND", "").strip()
    if not original:
        emit("interactive-ssh", backend_ssh_base(force_tty=True))
        return 0

    mosh_args = extract_mosh_forwarded_args(original)
    if mosh_args is not None:
        forwarded, remote_command = mosh_args
        backend_command = render_remote_command(remote_command)
        emit(
            "mosh-server",
            [
                MOSH_SERVER_BIN,
                *forwarded,
                "--",
                *backend_ssh_base(force_tty=True),
                *([backend_command] if backend_command else []),
            ],
        )
        return 0

    if client_requested_tty():
        emit("tty-command-ssh", [*backend_ssh_base(force_tty=True), original])
        return 0

    emit("command-ssh", [*backend_ssh_base(force_tty=False), original])
    return 0


if __name__ == "__main__":
    sys.exit(main())
