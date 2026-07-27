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
import re
import shlex
import sys
from typing import List, Optional, Tuple

# 命令前缀里的 VAR=value（`LANG=en_US.UTF-8 mosh-server new …`）
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


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


def mosh_invocation_index(argv: List[str]) -> Optional[int]:
    """argv 是不是一次真正的 `mosh-server new …` 调用；是则返回该 token 的下标。

    只在 argv **开头**认（允许 `LANG=… mosh-server new …` 这种环境变量前缀，
    `mosh --server=` 会生成这种形态）。理由是"被执行的那个命令"才算调用：
    `echo mosh-server new` 里的 mosh-server 是数据不是命令，在任何别的位置
    出现都只是被提到而已。放宽到"任意位置出现"会让这类命令被劫持到
    ECS 本机起 mosh-server，用户真正想跑的命令根本送不到后端。
    """
    index = 0
    while index < len(argv) and ENV_ASSIGNMENT_RE.match(argv[index]):
        index += 1
    if (
        index + 1 < len(argv)
        and is_mosh_server_token(argv[index])
        and argv[index + 1] == "new"
    ):
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


def mosh_candidates(original: str) -> List[List[str]]:
    """可能承载 mosh 调用的两种形态：命令本身，或一层显式的 shell wrapper。

    刻意**不**做"从字符串里第一次出现 mosh-server 的位置切一刀"那种兜底 ——
    那样 `echo mosh-server new` 也会被切出一个看着合法的 argv。要支持新的
    包装形态就往这里显式加一条，不要退回按子串猜。
    """
    argv = safe_split(original)
    if not argv:
        return []

    candidates = [argv]
    if (
        len(argv) >= 3
        and os.path.basename(argv[0]) in {"sh", "bash", "zsh"}
        and argv[1] in {"-c", "-lc", "-cl"}
    ):
        wrapped = safe_split(argv[2])
        if wrapped:
            candidates.append(wrapped)
    return candidates


def extract_mosh_forwarded_args(original: str) -> Optional[Tuple[List[str], List[str]]]:
    for candidate in mosh_candidates(original):
        mosh_index = mosh_invocation_index(candidate)
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
        # 无命令也要跟随客户端：`ssh -T relay` / 脚本里非终端 stdin 的无命令会话
        # 都是明确不要终端的，强行 -tt 会把它变成终端会话（还会打开行处理）。
        emit("interactive-ssh", backend_ssh_base(force_tty=client_requested_tty()))
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
