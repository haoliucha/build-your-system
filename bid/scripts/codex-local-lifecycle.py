from __future__ import annotations

import errno
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
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


@dataclass(frozen=True)
class MarketplaceSnapshot:
    exists: bool
    file_type: int | None
    device: int | None
    inode: int | None
    permission_mode: int | None
    mtime_ns: int | None
    size: int | None
    data: bytes | None

    @classmethod
    def absent(cls) -> MarketplaceSnapshot:
        return cls(False, None, None, None, None, None, None, None)

    @property
    def is_regular(self) -> bool:
        return self.file_type == stat.S_IFREG


@dataclass(frozen=True)
class SourceSnapshot:
    exists: bool
    file_type: int | None
    device: int | None
    inode: int | None
    mtime_ns: int | None
    raw_target: str | None
    resolved_target: Path | None

    @classmethod
    def absent(cls) -> SourceSnapshot:
        return cls(False, None, None, None, None, None, None)


@dataclass
class MarketplaceState:
    existed: bool
    original_bytes: bytes | None
    original_mode: int | None
    payload: dict[str, object] | None
    bid_present: bool
    original_snapshot: MarketplaceSnapshot


class LocalLifecycle:
    def __init__(self, bid_root: Path) -> None:
        self.bid_root = bid_root.resolve(strict=True)
        self.source_root = Path.home() / "plugins/bid"
        self.marketplace_file = Path.home() / ".agents/plugins/marketplace.json"
        self.lock_file = self.marketplace_file.with_name(
            f".{self.marketplace_file.name}.lock"
        )

    @staticmethod
    def marketplace_stat_fields(
        file_stat: os.stat_result,
    ) -> tuple[int, int, int, int, int, int]:
        return (
            stat.S_IFMT(file_stat.st_mode),
            file_stat.st_dev,
            file_stat.st_ino,
            stat.S_IMODE(file_stat.st_mode),
            file_stat.st_mtime_ns,
            file_stat.st_size,
        )

    def capture_marketplace_snapshot(self) -> MarketplaceSnapshot:
        try:
            path_stat = self.marketplace_file.lstat()
        except FileNotFoundError:
            return MarketplaceSnapshot.absent()

        if not stat.S_ISREG(path_stat.st_mode):
            return MarketplaceSnapshot(
                True,
                stat.S_IFMT(path_stat.st_mode),
                path_stat.st_dev,
                path_stat.st_ino,
                stat.S_IMODE(path_stat.st_mode),
                path_stat.st_mtime_ns,
                path_stat.st_size,
                None,
            )

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            file_fd = os.open(self.marketplace_file, flags)
        except OSError as error:
            raise ConcurrentModificationError(
                f"cannot capture a stable snapshot of {self.marketplace_file}: "
                f"{error}"
            ) from error

        with os.fdopen(file_fd, "rb") as marketplace:
            before_stat = os.fstat(marketplace.fileno())
            data = marketplace.read()
            after_stat = os.fstat(marketplace.fileno())

        if self.marketplace_stat_fields(before_stat) != self.marketplace_stat_fields(
            after_stat
        ):
            raise ConcurrentModificationError(
                f"concurrent modification detected while reading "
                f"{self.marketplace_file}"
            )
        try:
            final_path_stat = self.marketplace_file.lstat()
        except FileNotFoundError as error:
            raise ConcurrentModificationError(
                f"concurrent modification removed {self.marketplace_file}"
            ) from error
        if self.marketplace_stat_fields(
            after_stat
        ) != self.marketplace_stat_fields(final_path_stat):
            raise ConcurrentModificationError(
                f"concurrent replacement detected while reading "
                f"{self.marketplace_file}"
            )

        return MarketplaceSnapshot(
            True,
            stat.S_IFMT(after_stat.st_mode),
            after_stat.st_dev,
            after_stat.st_ino,
            stat.S_IMODE(after_stat.st_mode),
            after_stat.st_mtime_ns,
            after_stat.st_size,
            data,
        )

    @staticmethod
    def source_stat_fields(
        file_stat: os.stat_result,
    ) -> tuple[int, int, int, int]:
        return (
            stat.S_IFMT(file_stat.st_mode),
            file_stat.st_dev,
            file_stat.st_ino,
            file_stat.st_mtime_ns,
        )

    def capture_source_snapshot(self) -> SourceSnapshot:
        try:
            before_stat = self.source_root.lstat()
        except FileNotFoundError:
            return SourceSnapshot.absent()

        raw_target: str | None = None
        resolved_target: Path | None = None
        if stat.S_ISLNK(before_stat.st_mode):
            try:
                raw_target = os.readlink(self.source_root)
                resolved_target = self.source_root.resolve(strict=True)
            except (OSError, RuntimeError):
                resolved_target = None
        try:
            after_stat = self.source_root.lstat()
        except FileNotFoundError as error:
            raise ConcurrentModificationError(
                f"source path changed while inspecting {self.source_root}"
            ) from error
        if self.source_stat_fields(before_stat) != self.source_stat_fields(after_stat):
            raise ConcurrentModificationError(
                f"source path changed while inspecting {self.source_root}"
            )
        if stat.S_ISLNK(after_stat.st_mode):
            try:
                if os.readlink(self.source_root) != raw_target:
                    raise ConcurrentModificationError(
                        "source link target changed while inspecting "
                        f"{self.source_root}"
                    )
            except FileNotFoundError as error:
                raise ConcurrentModificationError(
                    f"source path changed while inspecting {self.source_root}"
                ) from error

        return SourceSnapshot(
            True,
            stat.S_IFMT(after_stat.st_mode),
            after_stat.st_dev,
            after_stat.st_ino,
            after_stat.st_mtime_ns,
            raw_target,
            resolved_target,
        )

    @contextmanager
    def lifecycle_lock(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            lock_fd = os.open(self.lock_file, flags, 0o600)
        except OSError as error:
            raise ConflictError(
                f"cannot open lifecycle lock {self.lock_file}: {error}"
            ) from error
        try:
            lock_stat = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_stat.st_mode):
                raise ConflictError(
                    f"lifecycle lock is not a regular file: {self.lock_file}"
                )
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                raise ConflictError(
                    "another local plugin lifecycle is already running; "
                    f"lock: {self.lock_file}"
                ) from error
            try:
                lock_path_stat = self.lock_file.lstat()
            except FileNotFoundError as error:
                raise ConflictError(
                    f"lifecycle lock path changed: {self.lock_file}"
                ) from error
            if (
                lock_path_stat.st_dev != lock_stat.st_dev
                or lock_path_stat.st_ino != lock_stat.st_ino
                or not stat.S_ISREG(lock_path_stat.st_mode)
            ):
                raise ConflictError(
                    f"lifecycle lock path changed: {self.lock_file}"
                )
            try:
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

    def load_marketplace(self) -> MarketplaceState:
        snapshot = self.capture_marketplace_snapshot()
        if snapshot.file_type == stat.S_IFLNK:
            raise ConflictError(
                f"{self.marketplace_file} is a symlink; refusing to modify it."
            )
        if not snapshot.exists:
            return MarketplaceState(False, None, None, None, False, snapshot)

        if not snapshot.is_regular:
            raise ConflictError(f"{self.marketplace_file} is not a regular file.")
        if snapshot.data is None or snapshot.permission_mode is None:
            raise RuntimeError("regular marketplace snapshot is incomplete")
        original_bytes = snapshot.data
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
            snapshot.permission_mode,
            marketplace,
            bool(bid_entries),
            snapshot,
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

    def require_marketplace_snapshot(
        self, expected_snapshot: MarketplaceSnapshot
    ) -> None:
        current_snapshot = self.capture_marketplace_snapshot()
        if current_snapshot != expected_snapshot:
            raise ConcurrentModificationError(
                f"concurrent modification detected at {self.marketplace_file}; "
                "existence, type, identity, permissions, mtime, size, or bytes "
                "changed; refusing to overwrite it"
            )

    def atomic_replace_marketplace(
        self,
        data: bytes,
        file_mode: int,
        expected_snapshot: MarketplaceSnapshot,
    ) -> MarketplaceSnapshot:
        self.marketplace_file.parent.mkdir(parents=True, exist_ok=True)
        self.require_marketplace_snapshot(expected_snapshot)
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.marketplace_file.name}.",
            suffix=".tmp",
            dir=self.marketplace_file.parent,
        )
        try:
            with os.fdopen(temp_fd, "wb") as temp_file:
                os.fchmod(temp_file.fileno(), file_mode)
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_stat = os.fstat(temp_file.fileno())
                written_snapshot = MarketplaceSnapshot(
                    True,
                    stat.S_IFMT(temp_stat.st_mode),
                    temp_stat.st_dev,
                    temp_stat.st_ino,
                    stat.S_IMODE(temp_stat.st_mode),
                    temp_stat.st_mtime_ns,
                    temp_stat.st_size,
                    data,
                )
            self.require_marketplace_snapshot(expected_snapshot)
            os.replace(temp_name, self.marketplace_file)
            current_snapshot = self.capture_marketplace_snapshot()
            if current_snapshot != written_snapshot:
                raise ConcurrentModificationError(
                    f"concurrent replacement detected immediately after writing "
                    f"{self.marketplace_file}"
                )
            return current_snapshot
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
        expected_snapshot: MarketplaceSnapshot,
    ) -> MarketplaceSnapshot:
        written_bytes = self.encoded_marketplace(payload)
        return self.atomic_replace_marketplace(
            written_bytes, file_mode or 0o600, expected_snapshot
        )

    def restore_marketplace(
        self, state: MarketplaceState, expected_written_snapshot: MarketplaceSnapshot
    ) -> None:
        if state.existed:
            if state.original_bytes is None or state.original_mode is None:
                raise RuntimeError("missing marketplace rollback snapshot")
            self.atomic_replace_marketplace(
                state.original_bytes,
                state.original_mode,
                expected_written_snapshot,
            )
            return

        self.require_marketplace_snapshot(expected_written_snapshot)
        self.marketplace_file.unlink()

    def validate_source(self) -> SourceSnapshot | None:
        snapshot = self.capture_source_snapshot()
        if not snapshot.exists:
            return None
        if (
            snapshot.file_type == stat.S_IFLNK
            and snapshot.resolved_target == self.bid_root
        ):
            return snapshot
        if snapshot.file_type == stat.S_IFLNK:
            raise ConflictError(
                f"{self.source_root} is a symlink to a different target."
            )
        raise ConflictError(
            f"{self.source_root} exists and is not the expected symlink."
        )

    def require_source_snapshot(self, expected_snapshot: SourceSnapshot) -> None:
        current_snapshot = self.capture_source_snapshot()
        if (
            current_snapshot != expected_snapshot
            or current_snapshot.file_type != stat.S_IFLNK
            or current_snapshot.resolved_target != self.bid_root
        ):
            raise ConcurrentModificationError(
                f"source symlink changed concurrently: {self.source_root}; "
                f"expected the original link to {self.bid_root}"
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
        marketplace_written_snapshot: MarketplaceSnapshot | None,
        source_created_snapshot: SourceSnapshot | None,
    ) -> None:
        errors: list[str] = []
        if marketplace_written_snapshot is not None:
            try:
                self.restore_marketplace(state, marketplace_written_snapshot)
            except Exception as error:  # noqa: BLE001 - collect all rollback errors.
                errors.append(str(error))
        if source_created_snapshot is not None:
            try:
                self.require_source_snapshot(source_created_snapshot)
                self.source_root.unlink()
            except Exception as error:  # noqa: BLE001 - collect all rollback errors.
                errors.append(str(error))
        if errors:
            raise RuntimeError("; ".join(errors))

    def install(self) -> int:
        state = self.load_marketplace()
        source_preexisting_snapshot = self.validate_source()

        marketplace_changed = not state.bid_present
        marketplace_written_snapshot: MarketplaceSnapshot | None = None
        source_created_snapshot: SourceSnapshot | None = None
        try:
            if source_preexisting_snapshot is None:
                self.source_root.parent.mkdir(parents=True, exist_ok=True)
                self.source_root.symlink_to(self.bid_root)
                source_created_snapshot = self.validate_source()
                if source_created_snapshot is None:
                    raise RuntimeError("created source symlink disappeared")

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
                marketplace_written_snapshot = self.write_marketplace(
                    marketplace, state.original_mode, state.original_snapshot
                )
        except Exception:
            self.rollback_install(
                state, marketplace_written_snapshot, source_created_snapshot
            )
            raise

        codex_returncode = self.run_codex("add")
        if codex_returncode != 0:
            try:
                self.rollback_install(
                    state, marketplace_written_snapshot, source_created_snapshot
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
        marketplace_written_snapshot: MarketplaceSnapshot | None,
        source_preflight_snapshot: SourceSnapshot,
    ) -> int:
        rollback_errors: list[str] = []
        if marketplace_written_snapshot is not None:
            try:
                self.restore_marketplace(state, marketplace_written_snapshot)
            except Exception as error:  # noqa: BLE001 - continue to Codex compensation.
                rollback_errors.append(str(error))

        try:
            self.require_source_snapshot(source_preflight_snapshot)
        except Exception as source_error:  # noqa: BLE001 - source trust gates add.
            print(
                "Partial state recovery required: codex plugin remove succeeded "
                f"and local uninstall failed ({original_error}).",
                file=sys.stderr,
            )
            if rollback_errors:
                print(
                    "Local rollback also failed: " + "; ".join(rollback_errors),
                    file=sys.stderr,
                )
            print(
                "Compensation add was not run because the local source changed "
                f"concurrently: {source_error}",
                file=sys.stderr,
            )
            print(
                "Codex-owned installed configuration and cache remain removed.",
                file=sys.stderr,
            )
            print(f"Inspect/fix source symlink: {self.source_root}", file=sys.stderr)
            print(f"Expected source target: {self.bid_root}", file=sys.stderr)
            print(f"Then run: codex plugin add {PLUGIN_REF}", file=sys.stderr)
            print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
            return 1

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
                "Local marketplace changes owned by this run were restored or "
                "no marketplace write occurred.",
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
        source_preflight_snapshot = self.validate_source()

        if not state.existed and source_preflight_snapshot is None:
            print(
                "Already locally absent: no bid marketplace entry or source symlink."
            )
            return 0
        if (
            state.existed
            and not state.bid_present
            and source_preflight_snapshot is None
        ):
            print(
                "Already locally absent: no bid marketplace entry or source symlink."
            )
            return 0
        if (
            not state.existed
            or not state.bid_present
            or source_preflight_snapshot is None
        ):
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

        marketplace_written_snapshot: MarketplaceSnapshot | None = None
        try:
            self.require_source_snapshot(source_preflight_snapshot)
            marketplace_written_snapshot = self.write_marketplace(
                state.payload, state.original_mode, state.original_snapshot
            )
            self.require_source_snapshot(source_preflight_snapshot)
            self.source_root.unlink()
        except Exception as error:  # noqa: BLE001 - compensate the completed remove.
            return self.compensate_failed_uninstall(
                error,
                state,
                marketplace_written_snapshot,
                source_preflight_snapshot,
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
    with lifecycle.lifecycle_lock():
        return (
            lifecycle.install()
            if sys.argv[1] == "install"
            else lifecycle.uninstall()
        )


try:
    raise SystemExit(main())
except ConflictError as error:
    print(f"Conflict: {error}", file=sys.stderr)
    raise SystemExit(1) from error
except Exception as error:  # noqa: BLE001 - CLI emits one actionable failure.
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1) from error
