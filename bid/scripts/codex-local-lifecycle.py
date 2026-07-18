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


class ConflictError(RuntimeError):
    pass


class ConcurrentModificationError(ConflictError):
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


class LocalLifecycle:
    def __init__(self, bid_root: Path) -> None:
        self.bid_root = bid_root.resolve(strict=True)
        self.source_root = Path.home() / "plugins/bid"
        self.marketplace_file = Path.home() / ".agents/plugins/marketplace.json"

    def is_expected_source_symlink(self) -> bool:
        if not self.source_root.is_symlink():
            return False
        try:
            return self.source_root.resolve(strict=True) == self.bid_root
        except (OSError, RuntimeError):
            return False

    def load_marketplace(self) -> MarketplaceState:
        if self.marketplace_file.is_symlink():
            raise ConflictError(
                f"{self.marketplace_file} is a symlink; refusing to modify it."
            )
        if not lexists(self.marketplace_file):
            return MarketplaceState(False, None, None, None, False)

        file_stat = self.marketplace_file.stat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise ConflictError(f"{self.marketplace_file} is not a regular file.")
        original_bytes = self.marketplace_file.read_bytes()
        try:
            marketplace = json.loads(original_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConflictError(
                f"cannot parse {self.marketplace_file}: {error}"
            ) from error
        if not isinstance(marketplace, dict):
            raise ConflictError(
                f"{self.marketplace_file} must contain a JSON object."
            )
        if marketplace.get("name") != MARKETPLACE_NAME:
            raise ConflictError(
                f"{self.marketplace_file} name must be exactly {MARKETPLACE_NAME!r}."
            )
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list):
            raise ConflictError(
                f"{self.marketplace_file} must contain a plugins list."
            )

        bid_entries = [
            plugin
            for plugin in plugins
            if isinstance(plugin, dict) and plugin.get("name") == "bid"
        ]
        if bid_entries and not (
            len(bid_entries) == 1 and bid_entries[0] == BID_ENTRY
        ):
            raise ConflictError(
                f"{self.marketplace_file} contains a different bid entry."
            )
        return MarketplaceState(
            True,
            original_bytes,
            stat.S_IMODE(file_stat.st_mode),
            marketplace,
            bool(bid_entries),
        )

    @staticmethod
    def default_marketplace() -> dict[str, object]:
        return {
            "name": MARKETPLACE_NAME,
            "interface": {"displayName": "Local Build Your System"},
            "plugins": [],
        }

    @staticmethod
    def encoded_marketplace(payload: dict[str, object]) -> bytes:
        return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )

    def current_marketplace_bytes(self) -> bytes | None:
        if self.marketplace_file.is_symlink():
            raise ConcurrentModificationError(
                f"concurrent modification replaced {self.marketplace_file} "
                "with a symlink"
            )
        if not lexists(self.marketplace_file):
            return None
        try:
            file_stat = self.marketplace_file.stat()
        except OSError as error:
            raise ConcurrentModificationError(
                f"cannot inspect {self.marketplace_file}: {error}"
            ) from error
        if not stat.S_ISREG(file_stat.st_mode):
            raise ConcurrentModificationError(
                f"concurrent modification replaced {self.marketplace_file} "
                "with a non-regular path"
            )
        return self.marketplace_file.read_bytes()

    def require_marketplace_snapshot(self, expected_bytes: bytes | None) -> None:
        current_bytes = self.current_marketplace_bytes()
        if current_bytes != expected_bytes:
            raise ConcurrentModificationError(
                f"concurrent modification detected at {self.marketplace_file}; "
                "refusing to overwrite it"
            )

    def atomic_replace_marketplace(
        self, data: bytes, file_mode: int, expected_bytes: bytes | None
    ) -> None:
        self.marketplace_file.parent.mkdir(parents=True, exist_ok=True)
        self.require_marketplace_snapshot(expected_bytes)
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.marketplace_file.name}.",
            suffix=".tmp",
            dir=self.marketplace_file.parent,
        )
        try:
            os.fchmod(temp_fd, file_mode)
            with os.fdopen(temp_fd, "wb") as temp_file:
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            self.require_marketplace_snapshot(expected_bytes)
            os.replace(temp_name, self.marketplace_file)
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def write_marketplace(
        self,
        payload: dict[str, object],
        file_mode: int | None,
        expected_bytes: bytes | None,
    ) -> bytes:
        written_bytes = self.encoded_marketplace(payload)
        self.atomic_replace_marketplace(
            written_bytes, file_mode or 0o600, expected_bytes
        )
        return written_bytes

    def restore_marketplace(
        self, state: MarketplaceState, expected_written_bytes: bytes
    ) -> None:
        if state.existed:
            if state.original_bytes is None or state.original_mode is None:
                raise RuntimeError("missing marketplace rollback snapshot")
            self.atomic_replace_marketplace(
                state.original_bytes,
                state.original_mode,
                expected_written_bytes,
            )
            return

        self.require_marketplace_snapshot(expected_written_bytes)
        self.marketplace_file.unlink()

    def validate_source(self) -> bool:
        if not lexists(self.source_root):
            return False
        if self.is_expected_source_symlink():
            return True
        if self.source_root.is_symlink():
            raise ConflictError(
                f"{self.source_root} is a symlink to a different target."
            )
        raise ConflictError(
            f"{self.source_root} exists and is not the expected symlink."
        )

    @staticmethod
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
        self,
        state: MarketplaceState,
        marketplace_written_bytes: bytes | None,
        source_created: bool,
    ) -> None:
        errors: list[str] = []
        if marketplace_written_bytes is not None:
            try:
                self.restore_marketplace(state, marketplace_written_bytes)
            except Exception as error:  # noqa: BLE001 - collect all rollback errors.
                errors.append(str(error))
        if source_created:
            try:
                if not self.is_expected_source_symlink():
                    raise RuntimeError(
                        f"rollback refused unexpected source path: {self.source_root}"
                    )
                self.source_root.unlink()
            except Exception as error:  # noqa: BLE001 - collect all rollback errors.
                errors.append(str(error))
        if errors:
            raise RuntimeError("; ".join(errors))

    def install(self) -> int:
        state = self.load_marketplace()
        source_preexisted = self.validate_source()

        marketplace_changed = not state.bid_present
        marketplace_written_bytes: bytes | None = None
        source_created = False
        try:
            if not source_preexisted:
                self.source_root.parent.mkdir(parents=True, exist_ok=True)
                self.source_root.symlink_to(self.bid_root)
                source_created = True

            if marketplace_changed:
                marketplace = (
                    state.payload
                    if state.payload is not None
                    else self.default_marketplace()
                )
                plugins = marketplace["plugins"]
                if not isinstance(plugins, list):
                    raise RuntimeError("validated plugins list changed unexpectedly")
                plugins.append(BID_ENTRY)
                marketplace_written_bytes = self.write_marketplace(
                    marketplace, state.original_mode, state.original_bytes
                )
        except Exception:
            self.rollback_install(
                state, marketplace_written_bytes, source_created
            )
            raise

        codex_returncode = self.run_codex("add")
        if codex_returncode != 0:
            try:
                self.rollback_install(
                    state, marketplace_written_bytes, source_created
                )
            except Exception as error:  # noqa: BLE001 - report incomplete rollback.
                print(
                    f"codex plugin add failed ({codex_returncode}). "
                    f"Rollback incomplete: {error}",
                    file=sys.stderr,
                )
                return 1
            print(
                f"codex plugin add failed ({codex_returncode}); "
                "local changes rolled back.",
                file=sys.stderr,
            )
            return codex_returncode

        print(f"Source: {self.source_root} -> {self.bid_root}")
        print(f"Marketplace: {self.marketplace_file}")
        print("Reminder: start a new Codex task to refresh the skill index.")
        return 0

    def report_failed_compensation(
        self,
        original_error: Exception,
        rollback_errors: list[str],
        compensation_returncode: int,
    ) -> None:
        print(
            "Partial state recovery required: codex plugin remove succeeded, "
            f"local uninstall failed ({original_error}), and compensation add "
            f"failed ({compensation_returncode}).",
            file=sys.stderr,
        )
        if rollback_errors:
            print(
                "Local rollback also failed: " + "; ".join(rollback_errors),
                file=sys.stderr,
            )
        print(f"Run: codex plugin add {PLUGIN_REF}", file=sys.stderr)
        print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
        print(f"Source symlink: {self.source_root}", file=sys.stderr)
        print(f"Source repository: {self.bid_root}", file=sys.stderr)

    def compensate_failed_uninstall(
        self,
        original_error: Exception,
        state: MarketplaceState,
        marketplace_written_bytes: bytes | None,
    ) -> int:
        rollback_errors: list[str] = []
        if marketplace_written_bytes is not None:
            try:
                self.restore_marketplace(state, marketplace_written_bytes)
            except Exception as error:  # noqa: BLE001 - continue to Codex compensation.
                rollback_errors.append(str(error))

        compensation_returncode = self.run_codex("add")
        if compensation_returncode != 0:
            self.report_failed_compensation(
                original_error, rollback_errors, compensation_returncode
            )
            return 1

        print(
            f"Local uninstall failed after codex plugin remove: {original_error}",
            file=sys.stderr,
        )
        if rollback_errors:
            print(
                "Local rollback incomplete: " + "; ".join(rollback_errors),
                file=sys.stderr,
            )
        else:
            print(
                "Local marketplace and source state were restored or preserved.",
                file=sys.stderr,
            )
        print(
            "Compensation succeeded: codex plugin add restored the "
            "Codex-owned installed configuration and cache.",
            file=sys.stderr,
        )
        return 1

    def uninstall(self) -> int:
        state = self.load_marketplace()
        source_present = self.validate_source()

        if not state.existed and not source_present:
            print(
                "Already locally absent: no bid marketplace entry or source symlink."
            )
            return 0
        if state.existed and not state.bid_present and not source_present:
            print(
                "Already locally absent: no bid marketplace entry or source symlink."
            )
            return 0
        if not state.existed or not state.bid_present or not source_present:
            raise ConflictError(
                "local bid state is partial; expected both the exact marketplace "
                "entry and source symlink before uninstall."
            )

        if (
            state.payload is None
            or state.original_bytes is None
            or state.original_mode is None
        ):
            raise RuntimeError("missing uninstall snapshot")
        plugins = state.payload["plugins"]
        if not isinstance(plugins, list):
            raise RuntimeError("validated plugins list changed unexpectedly")
        plugins.remove(BID_ENTRY)

        codex_returncode = self.run_codex("remove")
        if codex_returncode != 0:
            print(
                f"codex plugin remove failed ({codex_returncode}); "
                "local state unchanged.",
                file=sys.stderr,
            )
            return codex_returncode

        marketplace_written_bytes: bytes | None = None
        try:
            marketplace_written_bytes = self.write_marketplace(
                state.payload, state.original_mode, state.original_bytes
            )
            if not self.is_expected_source_symlink():
                raise ConcurrentModificationError(
                    f"source symlink changed during uninstall: {self.source_root}"
                )
            self.source_root.unlink()
        except Exception as error:  # noqa: BLE001 - compensate the completed remove.
            return self.compensate_failed_uninstall(
                error, state, marketplace_written_bytes
            )

        print(
            "Removed Codex-owned installed configuration and cache with "
            f"codex plugin remove {PLUGIN_REF}."
        )
        print(f"Removed local bid registration from {self.marketplace_file}")
        print(f"Unlinked source symlink: {self.source_root}")
        print(f"Preserved source repository: {self.bid_root}")
        print(
            "Preserved Claude state, project .claude/memory/, and unrelated "
            "marketplace entries."
        )
        return 0


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"install", "uninstall"}:
        print(
            f"Usage: {Path(sys.argv[0]).name} install|uninstall BID_ROOT",
            file=sys.stderr,
        )
        return 2
    lifecycle = LocalLifecycle(Path(sys.argv[2]))
    return lifecycle.install() if sys.argv[1] == "install" else lifecycle.uninstall()


try:
    raise SystemExit(main())
except ConflictError as error:
    print(f"Conflict: {error}", file=sys.stderr)
    raise SystemExit(1) from error
except Exception as error:  # noqa: BLE001 - CLI emits one actionable failure.
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1) from error
