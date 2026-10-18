#!/usr/bin/env python3
"""在 Codex 中安装 / 升级一个只按 Vault 启用的插件（如 assistant）。

`codex plugin add` 没有安装范围选项，无论在哪个目录执行都会往全局
`~/.codex/config.toml` 写入 `[plugins."<id>"] enabled = true`，使插件在所有项目启用。
本脚本在 add 之后删除这个全局条目，确保每个 Vault 的 `.codex/config.toml` 启用该插件，
再在 Vault 内外用 `codex plugin list --json` 核对，结果不符时以非零退出。

用法：
  python3 scripts/codex-install-vault-plugin.py assistant /Users/jliu/Projects/vault [更多 Vault ...] [--skip-upgrade]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MARKETPLACE = "build-your-system"
REPO = Path(__file__).resolve().parents[1]
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
GLOBAL_CONFIG = CODEX_HOME / "config.toml"


def run(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"命令失败：{' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout


def table_pattern(plugin_id):
    # 匹配整张 [plugins."<id>"] 表：表头到下一个表头（或文件尾）之前的内容。
    header = re.escape(f'[plugins."{plugin_id}"]')
    return re.compile(rf"^{header}[ \t]*\n(?:(?![\[#]).*\n?)*", re.MULTILINE)


def strip_global_entry(plugin_id):
    text = GLOBAL_CONFIG.read_text(encoding="utf-8")
    new_text, count = table_pattern(plugin_id).subn("", text)
    if count:
        GLOBAL_CONFIG.write_text(new_text, encoding="utf-8")
    return count


def ensure_vault_enabled(vault, plugin_id):
    config = vault / ".codex/config.toml"
    config.parent.mkdir(exist_ok=True)
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    block = f'[plugins."{plugin_id}"]\nenabled = true\n'
    pattern = table_pattern(plugin_id)
    if pattern.search(text):
        text = pattern.sub(block, text, count=1)
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    config.write_text(text, encoding="utf-8")


def plugin_state(plugin_id, cwd):
    payload = json.loads(run(["codex", "plugin", "list", "--json"], cwd=cwd))
    for item in payload.get("installed", []):
        if item.get("pluginId") == plugin_id:
            return item
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plugin")
    parser.add_argument("vaults", nargs="+", type=Path)
    parser.add_argument("--skip-upgrade", action="store_true",
                        help="跳过 marketplace upgrade（本地快照已含目标版本、或 GitHub 克隆超时时用）")
    args = parser.parse_args()

    plugin_id = f"{args.plugin}@{MARKETPLACE}"
    manifest = REPO / args.plugin / ".codex-plugin/plugin.json"
    expected = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    vaults = [v.resolve() for v in args.vaults]
    for vault in vaults:
        if not vault.is_dir():
            sys.exit(f"Vault 目录不存在：{vault}")

    shutil.copy2(GLOBAL_CONFIG, GLOBAL_CONFIG.with_suffix(".toml.bak-vault-plugin"))
    if not args.skip_upgrade:
        run(["codex", "plugin", "marketplace", "upgrade", MARKETPLACE])
    run(["codex", "plugin", "add", plugin_id])
    removed = strip_global_entry(plugin_id)
    for vault in vaults:
        ensure_vault_enabled(vault, plugin_id)

    errors = []
    for vault in vaults:
        state = plugin_state(plugin_id, vault)
        if not state or not state.get("enabled") or state.get("version") != expected:
            errors.append(f"{vault}: 期望 enabled {expected}，实际 {state}")
    with tempfile.TemporaryDirectory() as outside:
        state = plugin_state(plugin_id, outside)
        if state and state.get("enabled"):
            errors.append(f"Vault 外仍启用：{state}")

    cache = CODEX_HOME / "plugins/cache" / MARKETPLACE / args.plugin / expected
    if not cache.is_dir():
        errors.append(f"缺少缓存目录：{cache}")

    if errors:
        sys.exit("核对失败：\n- " + "\n- ".join(errors))
    print(f"{plugin_id} {expected}：已安装到 {cache}")
    print(f"全局条目已删除 {removed} 处；Vault 内启用：{', '.join(map(str, vaults))}；Vault 外未启用")


if __name__ == "__main__":
    main()
