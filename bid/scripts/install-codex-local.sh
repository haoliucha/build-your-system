#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
BID_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"

case "$#:${1:-}" in
  0:) mode="install" ;;
  1:--uninstall) mode="uninstall" ;;
  *)
    printf 'Usage: %s [--uninstall]\n' "$0" >&2
    exit 2
    ;;
esac

BID_ROOT="$BID_ROOT" python3 - "$mode" <<'PY'
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


MARKETPLACE_NAME = "local-build-your-system"
PLUGIN_REF = f"bid@{MARKETPLACE_NAME}"
BID_ENTRY = {
    "name": "bid",
    "source": {"source": "local", "path": "./plugins/bid"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}

bid_root = Path(os.environ["BID_ROOT"]).resolve(strict=True)
source_root = Path.home() / "plugins/bid"
marketplace_file = Path.home() / ".agents/plugins/marketplace.json"
mode = sys.argv[1]


class ConflictError(RuntimeError):
    pass


@dataclass
class MarketplaceState:
    existed: bool
    original_bytes: bytes | None
    original_mode: int | None
    payload: dict[str, object] | None
    bid_present: bool


def lexists(path: Path) -> bool:
    return os.path.lexists(path)


def is_expected_source_symlink() -> bool:
    if not source_root.is_symlink():
        return False
    try:
        return source_root.resolve(strict=True) == bid_root
    except (OSError, RuntimeError):
        return False


def load_marketplace() -> MarketplaceState:
    if marketplace_file.is_symlink():
        raise ConflictError(f"{marketplace_file} is a symlink; refusing to modify it.")
    if not lexists(marketplace_file):
        return MarketplaceState(False, None, None, None, False)

    file_stat = marketplace_file.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ConflictError(f"{marketplace_file} is not a regular file.")
    original_bytes = marketplace_file.read_bytes()
    try:
        marketplace = json.loads(original_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConflictError(f"cannot parse {marketplace_file}: {error}") from error
    if not isinstance(marketplace, dict):
        raise ConflictError(f"{marketplace_file} must contain a JSON object.")
    if marketplace.get("name") != MARKETPLACE_NAME:
        raise ConflictError(
            f"{marketplace_file} name must be exactly {MARKETPLACE_NAME!r}."
        )
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        raise ConflictError(f"{marketplace_file} must contain a plugins list.")

    bid_entries = [
        plugin
        for plugin in plugins
        if isinstance(plugin, dict) and plugin.get("name") == "bid"
    ]
    if bid_entries and not (len(bid_entries) == 1 and bid_entries[0] == BID_ENTRY):
        raise ConflictError(f"{marketplace_file} contains a different bid entry.")
    return MarketplaceState(
        True,
        original_bytes,
        stat.S_IMODE(file_stat.st_mode),
        marketplace,
        bool(bid_entries),
    )


def default_marketplace() -> dict[str, object]:
    return {
        "name": MARKETPLACE_NAME,
        "interface": {"displayName": "Local Build Your System"},
        "plugins": [],
    }


def encoded_marketplace(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write_bytes(path: Path, data: bytes, file_mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(temp_fd, file_mode)
        with os.fdopen(temp_fd, "wb") as temp_file:
            temp_file.write(data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_marketplace(payload: dict[str, object], file_mode: int | None) -> None:
    atomic_write_bytes(marketplace_file, encoded_marketplace(payload), file_mode or 0o600)


def restore_marketplace(state: MarketplaceState) -> None:
    if state.existed:
        if state.original_bytes is None or state.original_mode is None:
            raise RuntimeError("missing marketplace rollback snapshot")
        atomic_write_bytes(
            marketplace_file, state.original_bytes, state.original_mode
        )
    elif lexists(marketplace_file):
        if marketplace_file.is_symlink() or not marketplace_file.is_file():
            raise RuntimeError(
                f"rollback refused unexpected marketplace path: {marketplace_file}"
            )
        marketplace_file.unlink()


def validate_source() -> bool:
    if not lexists(source_root):
        return False
    if is_expected_source_symlink():
        return True
    if source_root.is_symlink():
        raise ConflictError(f"{source_root} is a symlink to a different target.")
    raise ConflictError(f"{source_root} exists and is not the expected symlink.")


def run_codex(action: str) -> int:
    try:
        completed = subprocess.run(
            ["codex", "plugin", action, PLUGIN_REF], check=False
        )
    except OSError as error:
        print(f"codex plugin {action} failed: {error}", file=sys.stderr)
        return 1
    return completed.returncode if completed.returncode >= 0 else 1


def rollback_install(
    state: MarketplaceState, marketplace_changed: bool, source_created: bool
) -> None:
    errors: list[str] = []
    if marketplace_changed:
        try:
            restore_marketplace(state)
        except Exception as error:  # noqa: BLE001 - report every rollback failure.
            errors.append(str(error))
    if source_created:
        try:
            if not is_expected_source_symlink():
                raise RuntimeError(
                    f"rollback refused unexpected source path: {source_root}"
                )
            source_root.unlink()
        except Exception as error:  # noqa: BLE001 - report every rollback failure.
            errors.append(str(error))
    if errors:
        raise RuntimeError("; ".join(errors))


def install() -> int:
    state = load_marketplace()
    source_preexisted = validate_source()

    marketplace_changed = not state.bid_present
    source_created = False
    try:
        if not source_preexisted:
            source_root.parent.mkdir(parents=True, exist_ok=True)
            source_root.symlink_to(bid_root)
            source_created = True

        if marketplace_changed:
            marketplace = (
                state.payload if state.payload is not None else default_marketplace()
            )
            plugins = marketplace["plugins"]
            if not isinstance(plugins, list):
                raise RuntimeError("validated plugins list changed unexpectedly")
            plugins.append(BID_ENTRY)
            write_marketplace(marketplace, state.original_mode)
    except Exception:
        rollback_install(state, marketplace_changed, source_created)
        raise

    codex_returncode = run_codex("add")
    if codex_returncode != 0:
        try:
            rollback_install(state, marketplace_changed, source_created)
        except Exception as error:  # noqa: BLE001 - surface rollback failure clearly.
            print(f"Rollback failed: {error}", file=sys.stderr)
            return 1
        print(
            f"codex plugin add failed ({codex_returncode}); local changes rolled back.",
            file=sys.stderr,
        )
        return codex_returncode

    print(f"Source: {source_root} -> {bid_root}")
    print(f"Marketplace: {marketplace_file}")
    print("Reminder: start a new Codex task to refresh the skill index.")
    return 0


def uninstall() -> int:
    state = load_marketplace()
    source_present = validate_source()

    if not state.existed and not source_present:
        print("Already locally absent: no bid marketplace entry or source symlink.")
        return 0
    if state.existed and not state.bid_present and not source_present:
        print("Already locally absent: no bid marketplace entry or source symlink.")
        return 0
    if not state.existed or not state.bid_present or not source_present:
        raise ConflictError(
            "local bid state is partial; expected both the exact marketplace entry "
            "and source symlink before uninstall."
        )

    codex_returncode = run_codex("remove")
    if codex_returncode != 0:
        print(
            f"codex plugin remove failed ({codex_returncode}); local state unchanged.",
            file=sys.stderr,
        )
        return codex_returncode

    if state.payload is None or state.original_bytes is None or state.original_mode is None:
        raise RuntimeError("missing uninstall snapshot")
    plugins = state.payload["plugins"]
    if not isinstance(plugins, list):
        raise RuntimeError("validated plugins list changed unexpectedly")
    plugins.remove(BID_ENTRY)

    write_marketplace(state.payload, state.original_mode)
    try:
        if not is_expected_source_symlink():
            raise RuntimeError(f"source symlink changed during uninstall: {source_root}")
        source_root.unlink()
    except Exception:
        atomic_write_bytes(
            marketplace_file, state.original_bytes, state.original_mode
        )
        raise

    print(f"Removed local bid registration from {marketplace_file}")
    print(f"Unlinked source symlink: {source_root}")
    print(f"Preserved source directory: {bid_root}")
    print("Project .claude/memory/ and plugin caches were not deleted.")
    return 0


try:
    raise SystemExit(install() if mode == "install" else uninstall())
except ConflictError as error:
    print(f"Conflict: {error}", file=sys.stderr)
    raise SystemExit(1) from error
except Exception as error:  # noqa: BLE001 - CLI emits a single actionable failure.
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1) from error
PY
