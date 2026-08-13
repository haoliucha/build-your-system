#!/bin/zsh

set -euo pipefail

PLUGIN_NAME="assistant"
MARKETPLACE_NAME="local-build-your-system"
EXPECTED_VERSION="2.0.0"
PLUGIN_VERSION="${EXPECTED_VERSION}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
TARGET_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SOURCE_ROOT="${HOME}/plugins/${PLUGIN_NAME}"
MARKETPLACE_FILE="${HOME}/.agents/plugins/marketplace.json"
CACHE_ROOT="${HOME}/.codex/plugins/cache/${MARKETPLACE_NAME}/${PLUGIN_NAME}/${PLUGIN_VERSION}"

mkdir -p "${HOME}/plugins" "${HOME}/.agents/plugins"
ln -sfn "${TARGET_ROOT}" "${SOURCE_ROOT}"

MARKETPLACE_FILE="${MARKETPLACE_FILE}" python3 <<'PY'
import json
import os
from pathlib import Path

marketplace_file = Path(os.environ["MARKETPLACE_FILE"])
entry = {
    "name": "assistant",
    "source": {"source": "local", "path": "./plugins/assistant"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}

if marketplace_file.exists():
    data = json.loads(marketplace_file.read_text(encoding="utf-8"))
else:
    data = {"plugins": []}

plugins = [plugin for plugin in data.get("plugins", []) if plugin.get("name") != entry["name"]]
plugins.append(entry)
data["plugins"] = plugins

marketplace_file.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

mkdir -p "$(dirname "${CACHE_ROOT}")"
rm -rf "${CACHE_ROOT}"
mkdir -p "${CACHE_ROOT}"
rsync -a --delete --exclude '.git' "${SOURCE_ROOT}/" "${CACHE_ROOT}/"

codex plugin add "${PLUGIN_NAME}@${MARKETPLACE_NAME}" --json >/dev/null

PLUGIN_NAME="${PLUGIN_NAME}" \
MARKETPLACE_NAME="${MARKETPLACE_NAME}" \
EXPECTED_VERSION="${EXPECTED_VERSION}" \
python3 - <<'PY'
import json
import os
import subprocess

plugin_id = f'{os.environ["PLUGIN_NAME"]}@{os.environ["MARKETPLACE_NAME"]}'
result = subprocess.run(
    ["codex", "plugin", "list", "--json"],
    check=True,
    capture_output=True,
    text=True,
)
payload = json.loads(result.stdout)
matches = [item for item in payload.get("installed", []) if item.get("pluginId") == plugin_id]
if len(matches) != 1:
    raise SystemExit(f"expected one installed plugin entry for {plugin_id}, got {len(matches)}")
plugin = matches[0]
if not plugin.get("installed") or not plugin.get("enabled"):
    raise SystemExit(f"{plugin_id} is not installed and enabled")
if plugin.get("version") != os.environ["EXPECTED_VERSION"]:
    raise SystemExit(
        f'{plugin_id} version mismatch: expected {os.environ["EXPECTED_VERSION"]}, '
        f'got {plugin.get("version")}'
    )
PY

echo "Linked ${PLUGIN_NAME} to ${SOURCE_ROOT}"
echo "Updated personal marketplace: ${MARKETPLACE_FILE}"
echo "Installed ${PLUGIN_NAME} to ${CACHE_ROOT}"
