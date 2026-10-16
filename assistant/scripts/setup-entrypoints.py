#!/usr/bin/env python3
"""Create/check shared Vault instructions; update only Assistant's marked block."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
import stat
import tempfile

BEGIN = b'<!-- assistant:begin -->'
END = b'<!-- assistant:end -->'
TEMPLATE = Path(__file__).resolve().parents[1] / 'templates/AGENTS.md'


class Conflict(ValueError):
    pass


@dataclass(frozen=True)
class Snapshot:
    kind: str
    content: bytes | str | None = None
    mode: int = 0o644


def snapshot(path: Path) -> Snapshot:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return Snapshot('missing')
    if stat.S_ISLNK(info.st_mode):
        return Snapshot('link', os.readlink(path))
    if stat.S_ISREG(info.st_mode):
        return Snapshot('file', path.read_bytes(), stat.S_IMODE(info.st_mode))
    return Snapshot('special')


def managed_content(original: bytes, block: bytes) -> bytes:
    begins, ends = original.count(BEGIN), original.count(END)
    if begins == ends == 0:
        separator = b'' if not original or original.endswith(b'\n\n') else b'\n' if original.endswith(b'\n') else b'\n\n'
        return original + separator + block + b'\n'
    # Marker examples in prose/code fences do not grant ownership of user content.
    actual = []
    fence = None
    for line in original.splitlines():
        stripped = line.strip()
        if stripped.startswith((b'```', b'~~~')):
            token = stripped[:3]
            fence = None if fence == token else token if fence is None else fence
        elif fence is None and stripped in (BEGIN, END):
            actual.append(stripped)
    if actual != [BEGIN, END]:
        raise Conflict('Assistant 标记必须在代码块之外单独成行；未修改入口文件。')
    if begins != 1 or ends != 1 or original.index(BEGIN) > original.index(END):
        raise Conflict('AGENTS.md 的 Assistant 标记缺失、重复或顺序错误；未修改任何入口文件。')
    start, end = original.index(BEGIN), original.index(END) + len(END)
    return original[:start] + block + original[end:]


def plan(vault: Path, template: Path = TEMPLATE):
    if not vault.is_dir():
        raise Conflict('Vault 目录不存在；请先完成 a-setup 的目录初始化。')
    override = snapshot(vault / 'AGENTS.override.md')
    if override.kind != 'missing' and not (override.kind == 'file' and not override.content):
        raise Conflict('AGENTS.override.md 会覆盖共享入口；请先核对并处理，初始化不会改动它。')
    before = {name: snapshot(vault / name) for name in ('AGENTS.md', 'CLAUDE.md')}
    agents, claude = before['AGENTS.md'], before['CLAUDE.md']
    if agents.kind not in {'file', 'missing'}:
        raise Conflict('AGENTS.md 必须是普通文件或不存在；不会沿链接修改其他位置。')
    if claude.kind == 'special':
        raise Conflict('CLAUDE.md 不是普通文件或符号链接，请先核对。')
    if claude.kind == 'link' and claude.content != 'AGENTS.md':
        raise Conflict('CLAUDE.md 已指向其他位置；不会替换既有链接。')

    original = agents.content if agents.kind == 'file' else b''
    if claude.kind == 'file':
        if claude.content.strip() in {b'@AGENTS.md', b''}:
            pass
        elif agents.kind == 'missing':
            original = claude.content  # Move the only existing source without discarding it.
        elif claude.content != agents.content:
            raise Conflict('AGENTS.md 与 CLAUDE.md 含独立内容；请先审阅合并到 AGENTS.md，再将 CLAUDE.md 替换为相对链接。未修改任何入口文件。')
    if not original:
        original = '# 工作区指令\n'.encode('utf-8')
    # Old bridges may read CLAUDE.md explicitly; linking would turn that into self-reading.
    text = original.decode('utf-8', errors='replace')
    if (re.search(r'(?im)^\s*(?:[-*]|\d+\.)?\s*(?:read|读|读取|阅读)\s+`?CLAUDE\.md', text)
            or re.search(r'(?m)^\s*@(AGENTS|CLAUDE)\.md\s*$', text)):
        raise Conflict('现有指令会循环读取共享入口；请先移除自引用，再创建链接。')
    block = template.read_bytes().strip(b'\r\n')
    if block.count(BEGIN) != 1 or block.count(END) != 1 or not block.startswith(BEGIN) or not block.endswith(END):
        raise Conflict('插件入口模板标记无效。')
    mode = agents.mode if agents.kind == 'file' else claude.mode if claude.kind == 'file' else 0o644
    desired = {'AGENTS.md': Snapshot('file', managed_content(original, block), mode),
               'CLAUDE.md': Snapshot('link', 'AGENTS.md')}
    changes = [name for name in before if before[name] != desired[name]]
    return before, desired, changes


def prepare(path: Path, value: Snapshot):
    if value.kind == 'file':
        path.write_bytes(value.content)
        path.chmod(value.mode)
    elif value.kind == 'link':
        path.symlink_to(value.content)


def apply(vault: Path, before, desired, changes):
    if not changes:
        return
    # Prepare every replacement first. An unsupported symlink fails before touching AGENTS.
    with tempfile.TemporaryDirectory(prefix='.assistant-entrypoints-', dir=vault) as tmp:
        staging = Path(tmp)
        for name in changes:
            prepare(staging / name, desired[name])
            prepare(staging / (name + '.before'), before[name])
        if any(snapshot(vault / name) != value for name, value in before.items()):
            raise Conflict('入口文件在检查后发生变化；未应用计划，请重新检查。')
        completed = []
        try:
            for name in changes:
                if snapshot(vault / name) != before[name]:
                    raise Conflict(f'{name} 在写入前发生变化；已停止并回滚本次修改。')
                os.replace(staging / name, vault / name)
                completed.append(name)
        except (OSError, Conflict):
            for name in reversed(completed):
                if snapshot(vault / name) != desired[name]:
                    raise Conflict(f'{name} 出现并发修改；未回滚该文件，请人工核对。')
                if before[name].kind == 'missing':
                    (vault / name).unlink()
                else:
                    os.replace(staging / (name + '.before'), vault / name)
            raise


def run(vault: Path, *, write: bool = False, template: Path = TEMPLATE) -> dict:
    before, desired, changes = plan(vault, template)
    if write:
        apply(vault, before, desired, changes)
    return {'status': 'updated' if write and changes else 'pending' if changes else 'ok',
            'vault': str(vault), 'changed_files': changes,
            'source': 'AGENTS.md', 'link': {'CLAUDE.md': 'AGENTS.md'}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', default='.', help='Target Vault; defaults to cwd')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true', help='Apply a safe plan')
    modes.add_argument('--check', action='store_true', help='Check only (default); exit 1 if changes are needed')
    args = parser.parse_args()
    try:
        result = run(Path(args.vault).expanduser().resolve(), write=args.apply)
    except (Conflict, OSError) as exc:
        print(json.dumps({'status': 'conflict' if isinstance(exc, Conflict) else 'error', 'reason': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['status'] == 'pending' else 0


if __name__ == '__main__':
    raise SystemExit(main())
