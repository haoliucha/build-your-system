#!/usr/bin/env python3
"""中继 ECS 上的 ForceCommand 分流器：按登录用户把会话透传到对应的后端 Mac。

部署位置：ECS 的 /usr/local/bin/coding-anywhere-forwarder（由 sshd_config 的
`Match User <relay-user>` → `ForceCommand env CA_* ... <此脚本>` 调起）。
这个文件是线上那份的**源**，改完必须 scp 回 ECS 才生效，见
skills/coding-anywhere/references/ecs-relay-blueprint.md §3.4。

三条出路（客户端看不到自己被转发了两跳）：
  - 无 SSH_ORIGINAL_COMMAND    → 进后端登录 shell
  - 开头是 `mosh-server new …` → mosh-server 在 ECS 本机起，`--` 后的 remote command
                                 再透传到后端（见 mosh_candidates）
  - 其他                       → 原样透传

第二跳给不给 pty 只有一条规则：跟随客户端（见 client_requested_tty）。
唯一的例外是 mosh 分支 —— mosh 客户端本来就不请求 pty，跟随它会让整条链路
失去终端，所以那条无条件 -tt。
"""

import json
import os
import re
import shlex
import sys
from typing import List, Optional, Tuple

# 命令前缀里的 VAR=value（`LANG=en_US.UTF-8 mosh-server new …`）
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# 客户端能指定的环境变量白名单。这些赋值会作用到**在 ECS 本机启动**的
# mosh-server 上，等于客户端能往中继机的进程环境里写东西。放开就等于
# 交出 ForceCommand 逃逸：`LD_PRELOAD=/tmp/x.so mosh-server new` 会在中继机上
# 以该 relay 用户身份执行任意代码，而这个用户本来只应该能借道转发、
# 拿不到 ECS 上的 shell。同类的还有 BASH_ENV / GCONV_PATH / PYTHONSTARTUP …
# 与其逐个拉黑（永远漏），不如只放行 locale/终端这几个真实用途。
SAFE_ENV_NAME_RE = re.compile(r"^(LANG|LANGUAGE|LC_[A-Z_]+|TERM)$")


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


def backend_ssh_base(force_tty: bool, subsystem: bool = False) -> List[str]:
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
    if subsystem:
        argv.append("-s")
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


def is_sftp_subsystem_request(original: str) -> bool:
    """这次连接其实是 SFTP **子系统**请求，而不是要跑一条命令。

    OpenSSH 9 起 `scp` 默认走 SFTP：客户端发的是 `ssh -s host sftp`。
    ForceCommand 会把子系统请求压成普通命令字符串塞进 SSH_ORIGINAL_COMMAND，
    收到的具体值取决于本机 sshd_config 的 `Subsystem sftp …` —— 可能是 `sftp`、
    `internal-sftp`，也可能是解析后的绝对路径（本机实测
    `/usr/libexec/openssh/sftp-server`），所以按第一个 token 的 basename 认。

    **只看第一个 token**：`Subsystem subsystem command` 里的 command 是可以带参数的
    （`Subsystem sftp internal-sftp -d /srv`），要求整条只有一个 token 会把这类
    服务器的 sftp 请求判掉。

    当普通命令转发过去的话，后端会去执行 sftp 那个**客户端**程序，
    协议对不上直接 `Connection closed` —— 症状就是走中继的 scp 全挂
    （dropfile 安装器把 DROP_HOST 指向中继时就踩这个）。
    """
    argv = safe_split(original)
    return bool(argv) and os.path.basename(argv[0]) in {
        "sftp",
        "internal-sftp",
        "sftp-server",
    }


def validated_env_prefix(assignments: List[str]) -> List[str]:
    """白名单外的赋值一律拒绝连接，不是悄悄丢掉。

    悄悄丢掉的话，客户端指定的 locale 明明没生效却毫无提示（就是上一版的 bug）；
    而一个被拒的 LD_PRELOAD 更应该让人立刻看见，而不是当作噪音抹掉。
    """
    for assignment in assignments:
        name = assignment.split("=", 1)[0]
        if not SAFE_ENV_NAME_RE.match(name):
            sys.stderr.write(
                f"coding-anywhere-forwarder: 不接受环境变量 {name}"
                "（只允许 LANG / LANGUAGE / LC_* / TERM）\n"
            )
            raise SystemExit(78)  # EX_CONFIG
    return assignments


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


def extract_mosh_forwarded_args(
    original: str,
) -> Optional[Tuple[List[str], List[str], List[str]]]:
    """→ (环境变量前缀, 传给 mosh-server 的参数, `--` 之后的 remote command)"""
    for candidate in mosh_candidates(original):
        mosh_index = mosh_invocation_index(candidate)
        if mosh_index is None:
            continue
        # `LANG=… mosh-server new …` 里的赋值是调用的一部分，必须带上。
        # 丢掉它不会报错，只会让 mosh-server 用 ForceCommand 进程的环境跑起来 ——
        # 客户端显式指定的 locale 被静默忽略，症状是远端中文变乱码。
        env_prefix = candidate[:mosh_index]
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
        return env_prefix, forwarded, remote_command

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
        env_prefix, forwarded, remote_command = mosh_args
        backend_command = render_remote_command(remote_command)
        # 用 `env VAR=val …` 而不是改 os.environ：赋值会出现在日志的 argv 和 ps 里，
        # 排查 locale 问题时看得见，不用去猜进程继承了什么。
        # `--` 是第二道保险：赋值本身已经过 ENV_ASSIGNMENT_RE 校验（不可能以 - 开头），
        # 加上它之后任何 token 都不会被 env 当成自己的选项。
        env_prefix = validated_env_prefix(env_prefix)
        launcher = ["/usr/bin/env", "--", *env_prefix] if env_prefix else []
        emit(
            "mosh-server",
            [
                *launcher,
                MOSH_SERVER_BIN,
                *forwarded,
                "--",
                *backend_ssh_base(force_tty=True),
                *([backend_command] if backend_command else []),
            ],
        )
        return 0

    # 加 not client_requested_tty() 是为了不误伤 `ssh -t relay 'sftp somehost'`
    # ——那是真的想在后端跑 sftp 客户端。真正的子系统请求（scp / sftp）从不申请 pty，
    # 所以"没要终端"是个免费且可靠的旁证。
    if not client_requested_tty() and is_sftp_subsystem_request(original):
        # 往后端发的必须是子系统**名字**（`sftp`），不是本机 sshd 解析出来的路径 ——
        # 后端 sshd 会用自己的 Subsystem 配置把名字映射到它自己的 sftp-server
        # （macOS 上是 /usr/libexec/sftp-server，和 Linux 不是一个路径）。
        emit("sftp-subsystem-ssh", [*backend_ssh_base(force_tty=False, subsystem=True), "sftp"])
        return 0

    if client_requested_tty():
        emit("tty-command-ssh", [*backend_ssh_base(force_tty=True), original])
        return 0

    emit("command-ssh", [*backend_ssh_base(force_tty=False), original])
    return 0


if __name__ == "__main__":
    sys.exit(main())
