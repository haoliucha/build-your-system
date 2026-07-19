from __future__ import annotations

import copy
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
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


class CodexStateRecoveryError(RuntimeError):
    def __init__(self, message: str, interruption_exit_code: int | None) -> None:
        super().__init__(message)
        self.interruption_exit_code = interruption_exit_code


class ParentTermination(KeyboardInterrupt):
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
class SourceTreeSnapshot:
    digest: str
    entry_count: int
    total_file_bytes: int


@dataclass(frozen=True)
class SourceSnapshot:
    exists: bool
    file_type: int | None
    device: int | None
    inode: int | None
    mtime_ns: int | None
    raw_target: str | None
    resolved_target: Path | None
    tree: SourceTreeSnapshot | None

    @classmethod
    def absent(cls) -> SourceSnapshot:
        return cls(False, None, None, None, None, None, None, None)


@dataclass(frozen=True)
class CodexCommandResult:
    returncode: int
    interrupted: bool
    interruption_exit_code: int | None = None


@dataclass
class MarketplaceState:
    existed: bool
    original_bytes: bytes | None
    original_mode: int | None
    payload: dict[str, object] | None
    bid_present: bool
    original_snapshot: MarketplaceSnapshot


@dataclass(frozen=True)
class MarketplaceWriteLease:
    written_snapshot: MarketplaceSnapshot
    original_quarantine: Path | None


TERMINATION_SIGNALS = {signal.SIGINT, signal.SIGTERM}


@contextmanager
def defer_termination_signals():
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, TERMINATION_SIGNALS)
    try:
        yield previous_mask
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


@contextmanager
def parent_termination_handler():
    previous_handler = signal.getsignal(signal.SIGTERM)

    def raise_parent_termination(_signum: int, _frame: object) -> None:
        raise ParentTermination

    signal.signal(signal.SIGTERM, raise_parent_termination)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


class LocalLifecycle:
    CODEX_INTERRUPT_GRACE_SECONDS = 5.0
    SOURCE_TREE_MAX_ENTRIES = 4096
    SOURCE_TREE_MAX_BYTES = 64 * 1024 * 1024
    SOURCE_TREE_IGNORED_DIRS = frozenset(
        {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    )
    SOURCE_TREE_IGNORED_FILES = frozenset({".DS_Store"})
    SOURCE_TREE_IGNORED_SUFFIXES = (".pyc", ".pyo", ".swp", "~")

    def __init__(self, bid_root: Path) -> None:
        self.bid_root = bid_root.resolve(strict=True)
        self.source_root = Path.home() / "plugins/bid"
        self.marketplace_file = Path.home() / ".agents/plugins/marketplace.json"
        self.lock_file = self.marketplace_file.with_name(
            f".{self.marketplace_file.name}.lock"
        )
        self.recovery_artifacts: list[Path] = []

    def record_recovery_artifact(self, path: Path) -> None:
        if path not in self.recovery_artifacts:
            self.recovery_artifacts.append(path)

    def forget_recovery_artifact(self, path: Path) -> None:
        if path in self.recovery_artifacts:
            self.recovery_artifacts.remove(path)

    def report_recovery_artifacts(self) -> None:
        for path in self.recovery_artifacts:
            if os.path.lexists(path):
                print(f"Recovery artifact retained: {path}", file=sys.stderr)

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

    def capture_marketplace_snapshot_at(self, path: Path) -> MarketplaceSnapshot:
        try:
            path_stat = path.lstat()
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
            file_fd = os.open(path, flags)
        except OSError as error:
            raise ConcurrentModificationError(
                f"cannot capture a stable snapshot of {path}: {error}"
            ) from error

        with os.fdopen(file_fd, "rb") as marketplace:
            before_stat = os.fstat(marketplace.fileno())
            data = marketplace.read()
            after_stat = os.fstat(marketplace.fileno())

        if self.marketplace_stat_fields(before_stat) != self.marketplace_stat_fields(
            after_stat
        ):
            raise ConcurrentModificationError(
                f"concurrent modification detected while reading {path}"
            )
        try:
            final_path_stat = path.lstat()
        except FileNotFoundError as error:
            raise ConcurrentModificationError(
                f"concurrent modification removed {path}"
            ) from error
        if self.marketplace_stat_fields(after_stat) != self.marketplace_stat_fields(
            final_path_stat
        ):
            raise ConcurrentModificationError(
                f"concurrent replacement detected while reading {path}"
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

    def capture_marketplace_snapshot(self) -> MarketplaceSnapshot:
        return self.capture_marketplace_snapshot_at(self.marketplace_file)

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

    @classmethod
    def source_tree_path_is_ignored(cls, path: Path, is_directory: bool) -> bool:
        if is_directory:
            return path.name in cls.SOURCE_TREE_IGNORED_DIRS
        return path.name in cls.SOURCE_TREE_IGNORED_FILES or path.name.endswith(
            cls.SOURCE_TREE_IGNORED_SUFFIXES
        )

    def scan_source_tree(self) -> SourceTreeSnapshot:
        paths = [self.bid_root]

        def include_path(path: Path) -> None:
            paths.append(path)
            if len(paths) > self.SOURCE_TREE_MAX_ENTRIES:
                raise ConflictError(
                    "plugin source content exceeds the bounded snapshot entry "
                    f"limit ({len(paths)} > {self.SOURCE_TREE_MAX_ENTRIES})"
                )

        try:
            pending_directories = [self.bid_root]
            while pending_directories:
                directory_path = pending_directories.pop()
                child_directories: list[Path] = []
                with os.scandir(directory_path) as entries:
                    for entry in entries:
                        path = Path(entry.path)
                        is_directory = entry.is_dir(follow_symlinks=False)
                        if self.source_tree_path_is_ignored(path, is_directory):
                            continue
                        include_path(path)
                        if is_directory:
                            child_directories.append(path)
                pending_directories.extend(sorted(child_directories, reverse=True))
        except OSError as error:
            raise ConcurrentModificationError(
                f"cannot enumerate plugin source content at {self.bid_root}: {error}"
            ) from error

        paths = sorted(
            paths,
            key=lambda path: path.relative_to(self.bid_root).as_posix(),
        )
        digest = hashlib.sha256()
        total_file_bytes = 0
        for path in paths:
            relative_path = "."
            if path != self.bid_root:
                relative_path = path.relative_to(self.bid_root).as_posix()
            try:
                before_stat = path.lstat()
            except OSError as error:
                raise ConcurrentModificationError(
                    f"plugin source content changed while snapshotting {path}: {error}"
                ) from error
            file_type = stat.S_IFMT(before_stat.st_mode)
            mode = stat.S_IMODE(before_stat.st_mode)
            digest.update(relative_path.encode("utf-8", "surrogateescape"))
            digest.update(b"\0")
            digest.update(f"{file_type}:{mode}".encode("ascii"))
            digest.update(b"\0")

            if stat.S_ISDIR(before_stat.st_mode):
                digest.update(
                    f"{before_stat.st_dev}:{before_stat.st_ino}".encode("ascii")
                )
                digest.update(b"\0")
                continue
            if stat.S_ISLNK(before_stat.st_mode):
                raise ConflictError(
                    "plugin source tree contains an unsupported symlink; "
                    f"refusing to follow content outside the bounded tree: {path}"
                )
            if not stat.S_ISREG(before_stat.st_mode):
                raise ConflictError(
                    f"plugin source contains unsupported file type: {path}"
                )

            total_file_bytes += before_stat.st_size
            if total_file_bytes > self.SOURCE_TREE_MAX_BYTES:
                raise ConflictError(
                    "plugin source content exceeds the bounded snapshot byte limit "
                    f"({total_file_bytes} > {self.SOURCE_TREE_MAX_BYTES})"
                )
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                file_fd = os.open(path, flags)
            except OSError as error:
                raise ConcurrentModificationError(
                    f"cannot read stable plugin source file {path}: {error}"
                ) from error
            with os.fdopen(file_fd, "rb") as source_file:
                opened_stat = os.fstat(source_file.fileno())
                data = source_file.read(before_stat.st_size + 1)
                after_stat = os.fstat(source_file.fileno())
            try:
                final_path_stat = path.lstat()
            except OSError as error:
                raise ConcurrentModificationError(
                    f"plugin source file changed while snapshotting {path}: {error}"
                ) from error
            expected_fields = self.marketplace_stat_fields(before_stat)
            if (
                expected_fields != self.marketplace_stat_fields(opened_stat)
                or expected_fields != self.marketplace_stat_fields(after_stat)
                or expected_fields != self.marketplace_stat_fields(final_path_stat)
                or len(data) != before_stat.st_size
            ):
                raise ConcurrentModificationError(
                    f"plugin source file changed while snapshotting {path}"
                )
            digest.update(
                f"{before_stat.st_dev}:{before_stat.st_ino}:"
                f"{before_stat.st_mtime_ns}:{before_stat.st_size}".encode("ascii")
            )
            digest.update(b"\0")
            digest.update(data)
            digest.update(b"\0")

        return SourceTreeSnapshot(digest.hexdigest(), len(paths), total_file_bytes)

    def capture_source_tree_snapshot(self) -> SourceTreeSnapshot:
        first = self.scan_source_tree()
        second = self.scan_source_tree()
        if first != second:
            raise ConcurrentModificationError(
                f"plugin source content changed while snapshotting {self.bid_root}"
            )
        return second

    def capture_source_snapshot_at(self, source_path: Path) -> SourceSnapshot:
        try:
            before_stat = source_path.lstat()
        except FileNotFoundError:
            return SourceSnapshot.absent()

        raw_target: str | None = None
        resolved_target: Path | None = None
        if stat.S_ISLNK(before_stat.st_mode):
            try:
                raw_target = os.readlink(source_path)
                resolved_target = source_path.resolve(strict=True)
            except (OSError, RuntimeError):
                resolved_target = None
        try:
            after_stat = source_path.lstat()
        except FileNotFoundError as error:
            raise ConcurrentModificationError(
                f"source path changed while inspecting {source_path}"
            ) from error
        if self.source_stat_fields(before_stat) != self.source_stat_fields(after_stat):
            raise ConcurrentModificationError(
                f"source path changed while inspecting {source_path}"
            )
        if stat.S_ISLNK(after_stat.st_mode):
            try:
                if os.readlink(source_path) != raw_target:
                    raise ConcurrentModificationError(
                        f"source link target changed while inspecting {source_path}"
                    )
            except FileNotFoundError as error:
                raise ConcurrentModificationError(
                    f"source path changed while inspecting {source_path}"
                ) from error

        tree_snapshot = (
            self.capture_source_tree_snapshot()
            if resolved_target == self.bid_root
            else None
        )
        try:
            final_stat = source_path.lstat()
        except FileNotFoundError as error:
            raise ConcurrentModificationError(
                f"source path changed while inspecting {source_path}"
            ) from error
        if self.source_stat_fields(after_stat) != self.source_stat_fields(final_stat):
            raise ConcurrentModificationError(
                f"source path changed while inspecting {source_path}"
            )
        if stat.S_ISLNK(final_stat.st_mode):
            try:
                final_target = os.readlink(source_path)
            except FileNotFoundError as error:
                raise ConcurrentModificationError(
                    f"source path changed while inspecting {source_path}"
                ) from error
            if final_target != raw_target:
                raise ConcurrentModificationError(
                    f"source link target changed while inspecting {source_path}"
                )

        return SourceSnapshot(
            True,
            stat.S_IFMT(final_stat.st_mode),
            final_stat.st_dev,
            final_stat.st_ino,
            final_stat.st_mtime_ns,
            raw_target,
            resolved_target,
            tree_snapshot,
        )

    def capture_source_snapshot(self) -> SourceSnapshot:
        return self.capture_source_snapshot_at(self.source_root)

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
                raise ConflictError(f"lifecycle lock path changed: {self.lock_file}")
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
            raise ConflictError(f"{self.marketplace_file} must contain a JSON object.")
        if marketplace.get("name") != MARKETPLACE_NAME:
            raise ConflictError(
                f"{self.marketplace_file} name must be exactly {MARKETPLACE_NAME!r}."
            )
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list):
            raise ConflictError(f"{self.marketplace_file} must contain a plugins list.")

        bid_entries = [
            plugin
            for plugin in plugins
            if isinstance(plugin, dict) and plugin.get("name") == "bid"
        ]
        if bid_entries and not (len(bid_entries) == 1 and bid_entries[0] == BID_ENTRY):
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

    @staticmethod
    def unique_quarantine_path(path: Path, kind: str) -> Path:
        while True:
            candidate = path.with_name(f".{path.name}.{secrets.token_hex(16)}.{kind}")
            if not os.path.lexists(candidate):
                return candidate

    @staticmethod
    def rename_exclusive(source: Path, destination: Path) -> None:
        libc = ctypes.CDLL(None, use_errno=True)
        source_bytes = os.fsencode(source)
        destination_bytes = os.fsencode(destination)
        if sys.platform == "darwin":
            rename = libc.renameatx_np
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(-2, source_bytes, -2, destination_bytes, 0x00000004)
        elif hasattr(libc, "renameat2"):
            rename = libc.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(-100, source_bytes, -100, destination_bytes, 0x1)
        else:
            raise ConflictError(
                "this platform lacks an atomic no-replace rename primitive"
            )
        if result != 0:
            error_number = ctypes.get_errno()
            raise OSError(
                error_number,
                os.strerror(error_number),
                str(source),
                str(destination),
            )

    def restore_quarantine_no_clobber(
        self, quarantine: Path, destination: Path, description: str
    ) -> None:
        try:
            self.rename_exclusive(quarantine, destination)
        except OSError as error:
            raise ConcurrentModificationError(
                f"could not restore {description} without overwriting concurrent "
                f"state at {destination}; recovery artifact preserved at "
                f"{quarantine}: {error}"
            ) from error

    def quarantine_marketplace(
        self, expected_snapshot: MarketplaceSnapshot
    ) -> Path | None:
        self.require_marketplace_snapshot(expected_snapshot)
        if not expected_snapshot.exists:
            return None
        quarantine = self.unique_quarantine_path(self.marketplace_file, "quarantine")
        self.record_recovery_artifact(quarantine)
        try:
            self.rename_exclusive(self.marketplace_file, quarantine)
        except OSError as error:
            if os.path.lexists(self.marketplace_file) or not os.path.lexists(
                quarantine
            ):
                self.forget_recovery_artifact(quarantine)
            raise ConcurrentModificationError(
                f"could not atomically quarantine {self.marketplace_file}: {error}"
            ) from error
        moved_snapshot = self.capture_marketplace_snapshot_at(quarantine)
        if moved_snapshot != expected_snapshot:
            try:
                self.restore_quarantine_no_clobber(
                    quarantine, self.marketplace_file, "concurrent marketplace"
                )
            except ConcurrentModificationError as restore_error:
                raise ConcurrentModificationError(
                    "marketplace changed after final validation; moved state did "
                    f"not match the owned snapshot; {restore_error}"
                ) from restore_error
            raise ConcurrentModificationError(
                "marketplace changed after final validation; the concurrent "
                "replacement was restored without being modified"
            )
        return quarantine

    def delete_marketplace_quarantine(
        self, quarantine: Path, expected_snapshot: MarketplaceSnapshot
    ) -> None:
        if self.capture_marketplace_snapshot_at(quarantine) != expected_snapshot:
            self.record_recovery_artifact(quarantine)
            raise ConcurrentModificationError(
                "owned marketplace quarantine changed; refusing to delete it; "
                f"recovery artifact: {quarantine}"
            )
        self.record_recovery_artifact(quarantine)

    def install_marketplace_bytes(
        self,
        data: bytes,
        file_mode: int,
        expected_snapshot: MarketplaceSnapshot,
        *,
        retain_original: bool,
    ) -> MarketplaceWriteLease:
        self.marketplace_file.parent.mkdir(parents=True, exist_ok=True)
        temp_pattern = f".{self.marketplace_file.name}.*.tmp"
        preexisting_temps = set(self.marketplace_file.parent.glob(temp_pattern))
        try:
            with defer_termination_signals():
                temp_fd, temp_name = tempfile.mkstemp(
                    prefix=f".{self.marketplace_file.name}.",
                    suffix=".tmp",
                    dir=self.marketplace_file.parent,
                )
                temp_path = Path(temp_name)
                self.record_recovery_artifact(temp_path)
        except BaseException:
            for candidate in self.marketplace_file.parent.glob(temp_pattern):
                if candidate not in preexisting_temps:
                    self.record_recovery_artifact(candidate)
            raise
        original_quarantine: Path | None = None
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
            original_quarantine = self.quarantine_marketplace(expected_snapshot)
            try:
                os.link(temp_path, self.marketplace_file, follow_symlinks=False)
            except OSError as error:
                if (
                    original_quarantine is not None
                    and not self.capture_marketplace_snapshot().exists
                ):
                    self.restore_quarantine_no_clobber(
                        original_quarantine,
                        self.marketplace_file,
                        "original marketplace",
                    )
                    original_quarantine = None
                artifact = (
                    f"; original recovery artifact: {original_quarantine}"
                    if original_quarantine is not None
                    else ""
                )
                raise ConcurrentModificationError(
                    "marketplace destination was populated concurrently; refusing "
                    f"to overwrite it{artifact}: {error}"
                ) from error
            current_snapshot = self.capture_marketplace_snapshot()
            if current_snapshot != written_snapshot:
                raise ConcurrentModificationError(
                    f"concurrent replacement detected immediately after writing "
                    f"{self.marketplace_file}; original recovery artifact: "
                    f"{original_quarantine}"
                )
            if original_quarantine is not None and not retain_original:
                try:
                    self.delete_marketplace_quarantine(
                        original_quarantine, expected_snapshot
                    )
                except BaseException as cleanup_error:
                    try:
                        self.restore_marketplace_lease(
                            MarketplaceWriteLease(
                                current_snapshot, original_quarantine
                            ),
                            expected_snapshot,
                        )
                    except BaseException as restore_error:
                        raise ConcurrentModificationError(
                            "new marketplace was installed, but ownership cleanup "
                            "failed and exact rollback was incomplete: "
                            f"{cleanup_error}; {restore_error}"
                        ) from restore_error
                    raise
                original_quarantine = None
            return MarketplaceWriteLease(current_snapshot, original_quarantine)
        finally:
            if os.path.lexists(temp_path):
                self.record_recovery_artifact(temp_path)

    def atomic_replace_marketplace(
        self,
        data: bytes,
        file_mode: int,
        expected_snapshot: MarketplaceSnapshot,
    ) -> MarketplaceSnapshot:
        return self.install_marketplace_bytes(
            data,
            file_mode,
            expected_snapshot,
            retain_original=False,
        ).written_snapshot

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

        quarantine = self.quarantine_marketplace(expected_written_snapshot)
        if quarantine is None:
            raise ConcurrentModificationError(
                "owned marketplace disappeared before rollback"
            )
        self.delete_marketplace_quarantine(quarantine, expected_written_snapshot)
        if self.capture_marketplace_snapshot().exists:
            raise ConcurrentModificationError(
                "marketplace was recreated concurrently during rollback; the "
                "concurrent state was preserved"
            )

    def restore_marketplace_lease(
        self,
        lease: MarketplaceWriteLease,
        original_snapshot: MarketplaceSnapshot,
    ) -> None:
        written_quarantine = self.quarantine_marketplace(lease.written_snapshot)
        if written_quarantine is None:
            raise ConcurrentModificationError(
                "transient marketplace disappeared before exact rollback"
            )
        if original_snapshot.exists:
            original_quarantine = lease.original_quarantine
            if original_quarantine is None:
                raise RuntimeError("missing original marketplace quarantine")
            if (
                self.capture_marketplace_snapshot_at(original_quarantine)
                != original_snapshot
            ):
                raise ConcurrentModificationError(
                    "original marketplace quarantine changed; recovery artifacts "
                    f"preserved at {original_quarantine} and {written_quarantine}"
                )
            try:
                self.rename_exclusive(original_quarantine, self.marketplace_file)
            except OSError as error:
                raise ConcurrentModificationError(
                    "marketplace was populated concurrently during exact rollback; "
                    "it was preserved and recovery artifacts remain at "
                    f"{original_quarantine} and {written_quarantine}: {error}"
                ) from error
            if self.capture_marketplace_snapshot() != original_snapshot:
                raise ConcurrentModificationError(
                    "restored marketplace no longer matches its exact original "
                    f"snapshot; transient artifact: {written_quarantine}"
                )
        elif self.capture_marketplace_snapshot().exists:
            raise ConcurrentModificationError(
                "marketplace was populated concurrently during rollback; it was "
                f"preserved; transient artifact: {written_quarantine}"
            )
        self.delete_marketplace_quarantine(written_quarantine, lease.written_snapshot)

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
        self.require_source_snapshot_at(self.source_root, expected_snapshot)

    def require_source_snapshot_at(
        self, source_path: Path, expected_snapshot: SourceSnapshot
    ) -> None:
        current_snapshot = self.capture_source_snapshot_at(source_path)
        if (
            current_snapshot != expected_snapshot
            or current_snapshot.file_type != stat.S_IFLNK
            or current_snapshot.resolved_target != self.bid_root
        ):
            raise ConcurrentModificationError(
                "source symlink identity, target, or plugin content changed "
                f"concurrently: {source_path}; expected the original link "
                f"and content snapshot for {self.bid_root}"
            )

    def quarantine_source(self, expected_snapshot: SourceSnapshot) -> Path:
        self.require_source_snapshot(expected_snapshot)
        quarantine = self.unique_quarantine_path(self.source_root, "quarantine")
        self.record_recovery_artifact(quarantine)
        try:
            self.rename_exclusive(self.source_root, quarantine)
        except OSError as error:
            if os.path.lexists(self.source_root) or not os.path.lexists(quarantine):
                self.forget_recovery_artifact(quarantine)
            raise ConcurrentModificationError(
                f"could not atomically quarantine {self.source_root}: {error}"
            ) from error
        try:
            self.require_source_snapshot_at(quarantine, expected_snapshot)
        except ConcurrentModificationError as validation_error:
            try:
                self.restore_quarantine_no_clobber(
                    quarantine, self.source_root, "concurrent source link"
                )
            except ConcurrentModificationError as restore_error:
                raise ConcurrentModificationError(
                    "source changed after final validation; recovery artifact "
                    f"preserved at {quarantine}: {restore_error}"
                ) from restore_error
            raise ConcurrentModificationError(
                "source changed after final validation; the concurrent source "
                "link was restored without being modified"
            ) from validation_error
        return quarantine

    def remove_owned_source(self, expected_snapshot: SourceSnapshot) -> None:
        quarantine = self.quarantine_source(expected_snapshot)
        self.require_source_snapshot_at(quarantine, expected_snapshot)
        self.record_recovery_artifact(quarantine)
        if self.capture_source_snapshot().exists:
            raise ConcurrentModificationError(
                "source path was recreated concurrently during cleanup; the "
                "concurrent source was preserved"
            )

    def restore_removed_source(
        self, expected_snapshot: SourceSnapshot
    ) -> SourceSnapshot:
        current_snapshot = self.capture_source_snapshot()
        if current_snapshot.exists:
            self.require_source_snapshot(expected_snapshot)
            return current_snapshot
        temporary_source = self.unique_quarantine_path(self.source_root, "restore")
        try:
            temporary_source.symlink_to(self.bid_root)
            temporary_snapshot = self.capture_source_snapshot_at(temporary_source)
            if (
                temporary_snapshot.file_type != stat.S_IFLNK
                or temporary_snapshot.resolved_target != self.bid_root
                or temporary_snapshot.tree != expected_snapshot.tree
            ):
                raise ConcurrentModificationError(
                    "plugin source content changed before source restoration"
                )
            try:
                self.rename_exclusive(temporary_source, self.source_root)
            except OSError as error:
                raise ConcurrentModificationError(
                    "source destination was populated concurrently during "
                    f"restoration; it was preserved: {error}"
                ) from error
        finally:
            if os.path.lexists(temporary_source):
                self.record_recovery_artifact(temporary_source)
        restored_snapshot = self.validate_source()
        if restored_snapshot is None:
            raise RuntimeError("restored source symlink disappeared")
        if restored_snapshot.tree != expected_snapshot.tree:
            raise ConcurrentModificationError(
                "plugin source content changed before the removed source symlink "
                "could be restored"
            )
        return restored_snapshot

    @staticmethod
    def run_codex(action: str) -> CodexCommandResult:
        process: subprocess.Popen[bytes] | None = None
        parent_termination_requested = False
        interrupted = False
        interruption_exit_code: int | None = None
        returncode = 1
        previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

        def handle_parent_sigterm(_signum: int, _frame: object) -> None:
            nonlocal parent_termination_requested
            parent_termination_requested = True
            if process is not None and process.returncode is None:
                raise ParentTermination

        signal.signal(signal.SIGTERM, handle_parent_sigterm)
        try:
            try:
                with defer_termination_signals() as child_signal_mask:
                    process = subprocess.Popen(
                        ["codex", "plugin", action, PLUGIN_REF],
                        start_new_session=True,
                        preexec_fn=lambda: signal.pthread_sigmask(
                            signal.SIG_SETMASK, child_signal_mask
                        ),
                    )
                if parent_termination_requested:
                    raise ParentTermination
                returncode = process.wait()
            except OSError as error:
                print(f"codex plugin {action} failed: {error}", file=sys.stderr)
            except KeyboardInterrupt as error:
                if process is None:
                    raise
                interrupted = True
                interruption_exit_code = (
                    143 if isinstance(error, ParentTermination) else 130
                )
                print(
                    f"codex plugin {action} interrupted; terminating and "
                    "reaping the isolated CLI child before reconciling "
                    "transaction state.",
                    file=sys.stderr,
                )
                if process.returncode is not None:
                    returncode = process.returncode
                else:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    deadline = (
                        time.monotonic() + LocalLifecycle.CODEX_INTERRUPT_GRACE_SECONDS
                    )
                    while True:
                        try:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise subprocess.TimeoutExpired(process.args, 0)
                            returncode = process.wait(timeout=remaining)
                            break
                        except KeyboardInterrupt as repeated_error:
                            interrupted = True
                            if interruption_exit_code is None:
                                interruption_exit_code = (
                                    143
                                    if isinstance(repeated_error, ParentTermination)
                                    else 130
                                )
                            continue
                        except subprocess.TimeoutExpired:
                            print(
                                f"codex plugin {action} did not terminate within "
                                f"{LocalLifecycle.CODEX_INTERRUPT_GRACE_SECONDS:g}s; "
                                "sending SIGKILL.",
                                file=sys.stderr,
                            )
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            while True:
                                try:
                                    returncode = process.wait()
                                    break
                                except KeyboardInterrupt as repeated_error:
                                    interrupted = True
                                    if interruption_exit_code is None:
                                        interruption_exit_code = (
                                            143
                                            if isinstance(
                                                repeated_error, ParentTermination
                                            )
                                            else 130
                                        )
                                    continue
                            break
            normalized_returncode = returncode if returncode >= 0 else 1
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)
            if parent_termination_requested:
                interrupted = True
                interruption_exit_code = 143
        return CodexCommandResult(
            normalized_returncode, interrupted, interruption_exit_code
        )

    @staticmethod
    def codex_plugin_installed() -> bool:
        try:
            completed = subprocess.run(
                ["codex", "plugin", "list", "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise ConflictError(f"codex plugin list --json failed: {error}") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip()
            suffix = f": {detail}" if detail else ""
            raise ConflictError(
                f"codex plugin list --json failed ({completed.returncode}){suffix}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ConflictError(
                f"codex plugin list --json returned invalid JSON: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise ConflictError(
                "codex plugin list --json must return a top-level object"
            )
        installed = payload.get("installed")
        if not isinstance(installed, list):
            raise ConflictError(
                "codex plugin list --json field 'installed' must be a list"
            )

        matches: list[dict[str, object]] = []
        for index, item in enumerate(installed):
            if not isinstance(item, dict):
                raise ConflictError(
                    "codex plugin list --json installed entry "
                    f"{index} must be an object"
                )
            plugin_id = item.get("pluginId")
            if not isinstance(plugin_id, str):
                raise ConflictError(
                    "codex plugin list --json installed entry "
                    f"{index} must contain a string pluginId"
                )
            if plugin_id == PLUGIN_REF:
                matches.append(item)
            elif (
                item.get("name") == "bid"
                and item.get("marketplaceName") == MARKETPLACE_NAME
            ):
                raise ConflictError(
                    "codex plugin list --json contains an ambiguous bid entry"
                )

        if len(matches) > 1:
            raise ConflictError(
                f"codex plugin list --json contains duplicate {PLUGIN_REF} entries"
            )
        if not matches:
            return False
        match = matches[0]
        if (
            match.get("name") != "bid"
            or match.get("marketplaceName") != MARKETPLACE_NAME
            or match.get("installed") is not True
        ):
            raise ConflictError(
                f"codex plugin list --json contains a malformed {PLUGIN_REF} entry"
            )
        return True

    def require_compensation_add_contract(
        self, source_snapshot: SourceSnapshot
    ) -> MarketplaceSnapshot:
        self.require_source_snapshot(source_snapshot)
        marketplace_state = self.load_marketplace()
        if not marketplace_state.existed or not marketplace_state.bid_present:
            raise ConcurrentModificationError(
                "the exact bid marketplace entry is no longer registered"
            )
        self.require_marketplace_snapshot(marketplace_state.original_snapshot)
        self.require_source_snapshot(source_snapshot)
        return marketplace_state.original_snapshot

    def codex_plugin_installed_with_contract(
        self,
        marketplace_snapshot: MarketplaceSnapshot,
        source_snapshot: SourceSnapshot,
    ) -> bool:
        self.require_marketplace_snapshot(marketplace_snapshot)
        self.require_source_snapshot(source_snapshot)
        installed = self.codex_plugin_installed()
        self.require_marketplace_snapshot(marketplace_snapshot)
        self.require_source_snapshot(source_snapshot)
        return installed

    @staticmethod
    def recovery_interruption_exit_code(error: BaseException) -> int | None:
        if isinstance(error, CodexStateRecoveryError):
            return error.interruption_exit_code
        return None

    def restore_codex_state_with_contract(
        self,
        installed_before: bool,
        marketplace_snapshot: MarketplaceSnapshot,
        source_snapshot: SourceSnapshot,
    ) -> int | None:
        installed_now = self.codex_plugin_installed_with_contract(
            marketplace_snapshot, source_snapshot
        )
        if installed_now == installed_before:
            return None

        action = "add" if installed_before else "remove"
        self.require_marketplace_snapshot(marketplace_snapshot)
        self.require_source_snapshot(source_snapshot)
        command_result = self.run_codex(action)
        interruption_exit_code = (
            command_result.interruption_exit_code or 130
            if command_result.interrupted
            else None
        )
        try:
            installed_after = self.codex_plugin_installed_with_contract(
                marketplace_snapshot, source_snapshot
            )
        except Exception as error:
            if interruption_exit_code is not None:
                raise CodexStateRecoveryError(
                    f"codex plugin {action} poststate could not be verified after "
                    f"an interruption: {error}",
                    interruption_exit_code,
                ) from error
            raise
        if installed_after != installed_before:
            raise CodexStateRecoveryError(
                f"codex plugin {action} did not restore the pre-operation state "
                f"(return code {command_result.returncode}, "
                f"interrupted={command_result.interrupted})",
                interruption_exit_code,
            )
        return interruption_exit_code

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
                self.remove_owned_source(source_created_snapshot)
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
                with defer_termination_signals():
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
                with defer_termination_signals():
                    marketplace_written_snapshot = self.write_marketplace(
                        marketplace, state.original_mode, state.original_snapshot
                    )

            active_source_snapshot = (
                source_created_snapshot
                if source_created_snapshot is not None
                else source_preexisting_snapshot
            )
            if active_source_snapshot is None:
                raise RuntimeError("installed source snapshot disappeared")
            active_marketplace_snapshot = (
                marketplace_written_snapshot
                if marketplace_written_snapshot is not None
                else state.original_snapshot
            )
            codex_installed_before = self.codex_plugin_installed_with_contract(
                active_marketplace_snapshot, active_source_snapshot
            )
        except BaseException as original_error:
            try:
                with defer_termination_signals():
                    self.rollback_install(
                        state,
                        marketplace_written_snapshot,
                        source_created_snapshot,
                    )
            except BaseException as rollback_error:
                print(
                    "Partial state recovery required: install preparation was "
                    f"interrupted or failed ({original_error}); rollback also "
                    f"failed: {rollback_error}",
                    file=sys.stderr,
                )
            raise
        try:
            codex_result = self.run_codex("add")
            if codex_result.interrupted:
                return self.reconcile_interrupted_install(
                    codex_result.interruption_exit_code or 130,
                    codex_installed_before,
                    state,
                    marketplace_written_snapshot,
                    source_created_snapshot,
                    source_preexisting_snapshot,
                )
            if codex_result.returncode != 0:
                return self.reconcile_nonzero_install(
                    codex_result.returncode,
                    codex_installed_before,
                    active_marketplace_snapshot,
                    active_source_snapshot,
                    state,
                    marketplace_written_snapshot,
                    source_created_snapshot,
                )
            try:
                nested_interruption = self.restore_codex_state_with_contract(
                    True, active_marketplace_snapshot, active_source_snapshot
                )
            except Exception as error:  # noqa: BLE001 - exact postcondition required.
                recovery_interruption_code = self.recovery_interruption_exit_code(error)
                if recovery_interruption_code is not None:
                    return self.reconcile_interrupted_install(
                        recovery_interruption_code,
                        codex_installed_before,
                        state,
                        marketplace_written_snapshot,
                        source_created_snapshot,
                        source_preexisting_snapshot,
                    )
                try:
                    self.require_marketplace_snapshot(active_marketplace_snapshot)
                    self.require_source_snapshot(active_source_snapshot)
                except Exception as contract_error:  # noqa: BLE001 - preserve evidence.
                    print(
                        "codex plugin add returned zero, but its installed "
                        "poststate could not be verified because the exact "
                        "local/source content contract changed: "
                        f"{error}; {contract_error}. Local registration was "
                        "preserved for recovery.",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    "codex plugin add returned zero without a verified installed "
                    f"poststate: {error}",
                    file=sys.stderr,
                )
                return self.reconcile_nonzero_install(
                    1,
                    codex_installed_before,
                    active_marketplace_snapshot,
                    active_source_snapshot,
                    state,
                    marketplace_written_snapshot,
                    source_created_snapshot,
                )
            if nested_interruption is not None:
                return self.reconcile_interrupted_install(
                    nested_interruption,
                    codex_installed_before,
                    state,
                    marketplace_written_snapshot,
                    source_created_snapshot,
                    source_preexisting_snapshot,
                )
        except KeyboardInterrupt as error:
            self.reconcile_interrupted_install(
                143 if isinstance(error, ParentTermination) else 130,
                codex_installed_before,
                state,
                marketplace_written_snapshot,
                source_created_snapshot,
                source_preexisting_snapshot,
            )
            raise

        print(f"Source: {self.source_root} -> {self.bid_root}")
        print(f"Marketplace: {self.marketplace_file}")
        print("Reminder: start a new Codex task to refresh the skill index.")
        return 0

    def reconcile_interrupted_install(
        self,
        interruption_exit_code: int,
        installed_before: bool,
        state: MarketplaceState,
        marketplace_written_snapshot: MarketplaceSnapshot | None,
        source_created_snapshot: SourceSnapshot | None,
        source_preexisting_snapshot: SourceSnapshot | None,
    ) -> int:
        active_source_snapshot = (
            source_created_snapshot
            if source_created_snapshot is not None
            else source_preexisting_snapshot
        )
        if active_source_snapshot is None:
            raise RuntimeError("installed source snapshot disappeared")
        active_marketplace_snapshot = (
            marketplace_written_snapshot
            if marketplace_written_snapshot is not None
            else state.original_snapshot
        )
        recovery_interruption_code: int | None = None
        try:
            if not installed_before:
                reconcile_result = self.run_codex("remove")
                if reconcile_result.interrupted:
                    recovery_interruption_code = (
                        reconcile_result.interruption_exit_code or 130
                    )
                try:
                    nested_interruption = self.restore_codex_state_with_contract(
                        False,
                        active_marketplace_snapshot,
                        active_source_snapshot,
                    )
                    recovery_interruption_code = (
                        nested_interruption or recovery_interruption_code
                    )
                except ConcurrentModificationError:
                    installed_now = self.codex_plugin_installed()
                    if installed_now:
                        retry_result = self.run_codex("remove")
                        if self.codex_plugin_installed():
                            raise RuntimeError(
                                "codex plugin remove could not verify the exact "
                                "plugin as absent after the local contract changed"
                            )
                        if retry_result.interrupted:
                            recovery_interruption_code = (
                                retry_result.interruption_exit_code or 130
                            )
            else:
                marketplace_snapshot = self.require_compensation_add_contract(
                    active_source_snapshot
                )
                installed_now = self.codex_plugin_installed_with_contract(
                    marketplace_snapshot, active_source_snapshot
                )
                if not installed_now:
                    self.require_marketplace_snapshot(marketplace_snapshot)
                    self.require_source_snapshot(active_source_snapshot)
                    reconcile_result = self.run_codex("add")
                    if reconcile_result.interrupted:
                        recovery_interruption_code = (
                            reconcile_result.interruption_exit_code or 130
                        )
                    nested_interruption = self.restore_codex_state_with_contract(
                        True, marketplace_snapshot, active_source_snapshot
                    )
                    recovery_interruption_code = (
                        nested_interruption or recovery_interruption_code
                    )
        except Exception as error:  # noqa: BLE001 - report incomplete recovery.
            recovery_interruption_code = (
                self.recovery_interruption_exit_code(error)
                or recovery_interruption_code
            )
            print(
                "Partial state recovery required: interrupted codex plugin add "
                f"could not restore the pre-operation installed state: {error}",
                file=sys.stderr,
            )
            print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
            print(f"Source symlink: {self.source_root}", file=sys.stderr)
            return recovery_interruption_code or interruption_exit_code

        try:
            self.rollback_install(
                state, marketplace_written_snapshot, source_created_snapshot
            )
        except Exception as error:  # noqa: BLE001 - report incomplete rollback.
            print(
                "Partial state recovery required: interrupted codex plugin add "
                f"restored Codex state, but local rollback failed: {error}",
                file=sys.stderr,
            )
            return recovery_interruption_code or interruption_exit_code
        print(
            "Interrupted codex plugin add restored the pre-operation installed "
            "state; local changes rolled back.",
            file=sys.stderr,
        )
        return recovery_interruption_code or interruption_exit_code

    def reconcile_nonzero_install(
        self,
        returncode: int,
        installed_before: bool,
        active_marketplace_snapshot: MarketplaceSnapshot,
        active_source_snapshot: SourceSnapshot,
        state: MarketplaceState,
        marketplace_written_snapshot: MarketplaceSnapshot | None,
        source_created_snapshot: SourceSnapshot | None,
    ) -> int:
        recovery_interruption_code: int | None = None
        try:
            recovery_interruption_code = self.restore_codex_state_with_contract(
                installed_before,
                active_marketplace_snapshot,
                active_source_snapshot,
            )
        except Exception as error:  # noqa: BLE001 - preserve recovery contract.
            recovery_interruption_code = self.recovery_interruption_exit_code(error)
            try:
                self.require_marketplace_snapshot(active_marketplace_snapshot)
                self.require_source_snapshot(active_source_snapshot)
            except Exception as contract_error:  # noqa: BLE001 - clean owned state.
                try:
                    self.rollback_install(
                        state,
                        marketplace_written_snapshot,
                        source_created_snapshot,
                    )
                except Exception as rollback_error:  # noqa: BLE001 - report both.
                    print(
                        f"codex plugin add failed ({returncode}). Partial state "
                        "recovery required: Codex state reconciliation failed: "
                        f"{error}; local contract changed: {contract_error}; "
                        f"owned-state rollback was incomplete: {rollback_error}",
                        file=sys.stderr,
                    )
                    return recovery_interruption_code or 1
                print(
                    f"codex plugin add failed ({returncode}). Partial state "
                    "recovery required: Codex state reconciliation failed: "
                    f"{error}; local contract changed: {contract_error}; "
                    "unchanged owned local state rolled back.",
                    file=sys.stderr,
                )
                return recovery_interruption_code or 1
            print(
                f"codex plugin add failed ({returncode}). Partial state recovery "
                "required: Codex state reconciliation failed: "
                f"{error}; trusted local marketplace and source registration "
                "preserved for recovery.",
                file=sys.stderr,
            )
            print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
            print(f"Source symlink: {self.source_root}", file=sys.stderr)
            return recovery_interruption_code or 1

        rollback_error: Exception | None = None
        try:
            self.rollback_install(
                state, marketplace_written_snapshot, source_created_snapshot
            )
        except Exception as error:  # noqa: BLE001 - report both recovery failures.
            rollback_error = error

        if rollback_error is not None:
            print(
                f"codex plugin add failed ({returncode}). Partial state recovery "
                f"required: local rollback failed: {rollback_error}",
                file=sys.stderr,
            )
            return recovery_interruption_code or 1

        print(
            f"codex plugin add failed ({returncode}); Codex state reconciled and "
            "local changes rolled back.",
            file=sys.stderr,
        )
        return recovery_interruption_code or returncode

    def report_failed_compensation(
        self,
        original_error: Exception,
        rollback_errors: list[str],
        compensation_result: CodexCommandResult,
    ) -> None:
        compensation_failure = (
            f"was interrupted (return code {compensation_result.returncode})"
            if compensation_result.interrupted
            else f"failed ({compensation_result.returncode})"
        )
        print(
            "Partial state recovery required: codex plugin remove succeeded, "
            f"local uninstall failed ({original_error}), and compensation add "
            f"{compensation_failure}.",
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
        original_error: BaseException,
        state: MarketplaceState,
        marketplace_written_snapshot: MarketplaceSnapshot | None,
        source_preflight_snapshot: SourceSnapshot,
        source_unlinked: bool,
    ) -> int:
        rollback_errors: list[str] = []
        if marketplace_written_snapshot is not None:
            try:
                self.restore_marketplace(state, marketplace_written_snapshot)
            except Exception as error:  # noqa: BLE001 - continue to Codex compensation.
                rollback_errors.append(str(error))

        compensation_source_snapshot = source_preflight_snapshot
        if source_unlinked:
            try:
                compensation_source_snapshot = self.restore_removed_source(
                    source_preflight_snapshot
                )
            except Exception as error:  # noqa: BLE001 - report incomplete rollback.
                rollback_errors.append(str(error))

        try:
            compensation_marketplace_snapshot = self.require_compensation_add_contract(
                compensation_source_snapshot
            )
        except Exception as contract_error:  # noqa: BLE001 - trust gates add.
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
                "Compensation add was not run because the exact marketplace "
                "entry and source contract is no longer CAS-safe: "
                f"{contract_error}",
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

        try:
            self.require_marketplace_snapshot(compensation_marketplace_snapshot)
            self.require_source_snapshot(compensation_source_snapshot)
        except Exception as contract_error:  # noqa: BLE001 - last-moment CAS gate.
            print(
                "Partial state recovery required: compensation add was not run "
                "because the exact marketplace entry or source changed after "
                f"validation: {contract_error}",
                file=sys.stderr,
            )
            return 1

        compensation_result = self.run_codex("add")
        recovery_interruption_code = (
            compensation_result.interruption_exit_code or 130
            if compensation_result.interrupted
            else None
        )
        try:
            nested_interruption = self.restore_codex_state_with_contract(
                True,
                compensation_marketplace_snapshot,
                compensation_source_snapshot,
            )
            recovery_interruption_code = (
                nested_interruption or recovery_interruption_code
            )
        except Exception as error:  # noqa: BLE001 - do not claim compensation.
            recovery_interruption_code = (
                self.recovery_interruption_exit_code(error)
                or recovery_interruption_code
            )
            print(
                "Partial state recovery required: compensation add completed "
                "without a verified installed/source-content poststate: "
                f"{error}",
                file=sys.stderr,
            )
            self.report_failed_compensation(
                original_error, rollback_errors, compensation_result
            )
            return recovery_interruption_code or 1

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
        return recovery_interruption_code or 1

    def reconcile_interrupted_remove(
        self,
        interruption_exit_code: int,
        installed_before: bool,
        source_preflight_snapshot: SourceSnapshot,
    ) -> int:
        try:
            marketplace_snapshot = self.require_compensation_add_contract(
                source_preflight_snapshot
            )
            installed_now = self.codex_plugin_installed_with_contract(
                marketplace_snapshot, source_preflight_snapshot
            )
        except Exception as error:  # noqa: BLE001 - exact local contract gates query.
            print(
                "Partial state recovery required: interrupted codex plugin remove "
                "cannot be reconciled because the exact marketplace entry and "
                f"source contract is no longer CAS-safe: {error}",
                file=sys.stderr,
            )
            print(
                "Compensation add was not run against untrusted local state.",
                file=sys.stderr,
            )
            print(f"Inspect/fix source symlink: {self.source_root}", file=sys.stderr)
            print(f"Expected source target: {self.bid_root}", file=sys.stderr)
            print(f"Then run: codex plugin add {PLUGIN_REF}", file=sys.stderr)
            print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
            return interruption_exit_code

        if installed_now == installed_before:
            print(
                "Interrupted codex plugin remove left the pre-operation installed "
                "state intact; local state remained unchanged.",
                file=sys.stderr,
            )
            return interruption_exit_code

        action = "add" if installed_before else "remove"
        try:
            self.require_marketplace_snapshot(marketplace_snapshot)
            self.require_source_snapshot(source_preflight_snapshot)
        except Exception as error:  # noqa: BLE001 - last-moment CAS gate.
            print(
                f"Partial state recovery required: compensation {action} was not "
                "run because the exact marketplace entry or source changed after "
                f"validation: {error}",
                file=sys.stderr,
            )
            return interruption_exit_code

        reconcile_result = self.run_codex(action)
        recovery_interruption_code = (
            reconcile_result.interruption_exit_code or 130
            if reconcile_result.interrupted
            else None
        )
        try:
            nested_interruption = self.restore_codex_state_with_contract(
                installed_before,
                marketplace_snapshot,
                source_preflight_snapshot,
            )
            recovery_interruption_code = (
                nested_interruption or recovery_interruption_code
            )
        except Exception as error:  # noqa: BLE001 - verify recovery boundary.
            recovery_interruption_code = (
                self.recovery_interruption_exit_code(error)
                or recovery_interruption_code
            )
            print(
                "Partial state recovery required: interrupted codex plugin "
                f"remove compensation lacked a verified poststate: {error}",
                file=sys.stderr,
            )
            return recovery_interruption_code or interruption_exit_code
        print(
            "Interrupted codex plugin remove was compensated: the installed "
            "state was restored and local state remained unchanged.",
            file=sys.stderr,
        )
        return recovery_interruption_code or interruption_exit_code

    def reconcile_unverified_zero_remove(
        self,
        installed_before: bool,
        source_preflight_snapshot: SourceSnapshot,
        postcondition_error: Exception,
    ) -> int:
        postcondition_interruption_code = self.recovery_interruption_exit_code(
            postcondition_error
        )
        if not installed_before:
            print(
                "Partial state recovery required: codex plugin remove returned "
                "zero, but the exact local/source content contract changed before "
                f"its absent poststate could be verified: {postcondition_error}",
                file=sys.stderr,
            )
            return postcondition_interruption_code or 1
        try:
            current_marketplace_snapshot = self.require_compensation_add_contract(
                source_preflight_snapshot
            )
            recovery_interruption_code = self.restore_codex_state_with_contract(
                True,
                current_marketplace_snapshot,
                source_preflight_snapshot,
            )
        except Exception as error:  # noqa: BLE001 - report unsafe/incomplete repair.
            recovery_interruption_code = (
                self.recovery_interruption_exit_code(error)
                or postcondition_interruption_code
            )
            print(
                "Partial state recovery required: codex plugin remove returned "
                "zero without a verifiable absent poststate; compensation add "
                "was not run or safely completed: "
                f"{postcondition_error}; {error}",
                file=sys.stderr,
            )
            print(f"Run: codex plugin add {PLUGIN_REF}", file=sys.stderr)
            print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
            print(f"Source symlink: {self.source_root}", file=sys.stderr)
            return recovery_interruption_code or 1
        print(
            "codex plugin remove returned zero after the local contract changed; "
            "the pre-operation installed state was restored and concurrent local "
            "state was preserved.",
            file=sys.stderr,
        )
        return recovery_interruption_code or postcondition_interruption_code or 1

    def rollback_local_only_uninstall(
        self,
        original_error: BaseException,
        state: MarketplaceState,
        marketplace_written_snapshot: MarketplaceSnapshot | None,
        source_preflight_snapshot: SourceSnapshot,
        source_unlinked: bool,
    ) -> int:
        rollback_errors: list[str] = []
        if marketplace_written_snapshot is not None:
            try:
                self.restore_marketplace(state, marketplace_written_snapshot)
            except Exception as error:  # noqa: BLE001 - report rollback failure.
                rollback_errors.append(str(error))
        if source_unlinked:
            try:
                self.restore_removed_source(source_preflight_snapshot)
            except Exception as error:  # noqa: BLE001 - report rollback failure.
                rollback_errors.append(str(error))
        print(
            "Local cleanup failed while Codex-installed state was already absent: "
            f"{original_error}",
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
        return 1

    def create_transient_local_registration(
        self, state: MarketplaceState
    ) -> tuple[MarketplaceWriteLease, SourceSnapshot]:
        lease: MarketplaceWriteLease | None = None
        source_snapshot: SourceSnapshot | None = None
        try:
            with defer_termination_signals():
                self.source_root.parent.mkdir(parents=True, exist_ok=True)
                self.source_root.symlink_to(self.bid_root)
                source_snapshot = self.validate_source()
                if source_snapshot is None:
                    raise RuntimeError("transient source symlink disappeared")

            marketplace = copy.deepcopy(
                state.payload
                if state.payload is not None
                else self.default_marketplace()
            )
            plugins = marketplace.get("plugins")
            if not isinstance(plugins, list):
                raise RuntimeError("validated plugins list changed unexpectedly")
            plugins.append(BID_ENTRY)
            with defer_termination_signals():
                lease = self.install_marketplace_bytes(
                    self.encoded_marketplace(marketplace),
                    state.original_mode or 0o600,
                    state.original_snapshot,
                    retain_original=True,
                )
            return lease, source_snapshot
        except BaseException as original_error:
            rollback_errors: list[str] = []
            if lease is not None:
                try:
                    with defer_termination_signals():
                        self.restore_marketplace_lease(lease, state.original_snapshot)
                except BaseException as error:
                    rollback_errors.append(str(error))
            if source_snapshot is not None:
                try:
                    with defer_termination_signals():
                        self.remove_owned_source(source_snapshot)
                except BaseException as error:
                    rollback_errors.append(str(error))
            if rollback_errors:
                print(
                    "Partial state recovery required: transient registration "
                    f"setup failed ({original_error}); rollback also failed: "
                    + "; ".join(rollback_errors),
                    file=sys.stderr,
                )
            raise

    def restore_transient_local_registration(
        self,
        state: MarketplaceState,
        lease: MarketplaceWriteLease,
        source_snapshot: SourceSnapshot,
    ) -> None:
        errors: list[str] = []
        try:
            self.restore_marketplace_lease(lease, state.original_snapshot)
        except Exception as error:  # noqa: BLE001 - preserve all recovery details.
            errors.append(str(error))
        try:
            self.remove_owned_source(source_snapshot)
        except Exception as error:  # noqa: BLE001 - preserve all recovery details.
            errors.append(str(error))
        if errors:
            raise RuntimeError("; ".join(errors))

    def uninstall_with_transient_local_registration(
        self, state: MarketplaceState
    ) -> int:
        lease: MarketplaceWriteLease | None = None
        source_snapshot: SourceSnapshot | None = None
        command_started = False
        original_exit_code = 0
        try:
            with defer_termination_signals():
                lease, source_snapshot = self.create_transient_local_registration(state)
            self.codex_plugin_installed_with_contract(
                lease.written_snapshot, source_snapshot
            )
            command_started = True
            result = self.run_codex("remove")
            original_exit_code = (
                result.interruption_exit_code or 130
                if result.interrupted
                else result.returncode
            )
            installed_after = self.codex_plugin_installed_with_contract(
                lease.written_snapshot, source_snapshot
            )
            if installed_after:
                retry_result = self.run_codex("remove")
                retry_abnormal = (
                    retry_result.interrupted or retry_result.returncode != 0
                )
                if original_exit_code == 0 and retry_abnormal:
                    original_exit_code = (
                        retry_result.interruption_exit_code or 130
                        if retry_result.interrupted
                        else retry_result.returncode
                    )
                installed_after = self.codex_plugin_installed_with_contract(
                    lease.written_snapshot, source_snapshot
                )
            if installed_after:
                print(
                    "Partial state recovery required: Codex still reports the "
                    "plugin installed after bounded removal attempts. The exact "
                    "transient marketplace registration and source link were "
                    "preserved so the orphan remains discoverable.",
                    file=sys.stderr,
                )
                print(f"Marketplace: {self.marketplace_file}", file=sys.stderr)
                print(f"Source symlink: {self.source_root}", file=sys.stderr)
                return original_exit_code or 1
            with defer_termination_signals():
                self.restore_transient_local_registration(state, lease, source_snapshot)
        except KeyboardInterrupt:
            try:
                if (
                    command_started
                    and lease is not None
                    and source_snapshot is not None
                ):
                    installed_after = self.codex_plugin_installed_with_contract(
                        lease.written_snapshot, source_snapshot
                    )
                    if installed_after:
                        self.run_codex("remove")
                        installed_after = self.codex_plugin_installed_with_contract(
                            lease.written_snapshot, source_snapshot
                        )
                    if not installed_after:
                        with defer_termination_signals():
                            self.restore_transient_local_registration(
                                state, lease, source_snapshot
                            )
                elif lease is not None and source_snapshot is not None:
                    with defer_termination_signals():
                        self.restore_transient_local_registration(
                            state, lease, source_snapshot
                        )
            except BaseException as recovery_error:
                print(
                    "Partial state recovery required after interruption; exact "
                    "transient discovery state was preserved when recovery could "
                    f"not be verified: {recovery_error}",
                    file=sys.stderr,
                )
            raise
        except BaseException:
            if (
                not command_started
                and lease is not None
                and source_snapshot is not None
            ):
                with defer_termination_signals():
                    self.restore_transient_local_registration(
                        state, lease, source_snapshot
                    )
            raise

        print(
            "Verified Codex-owned installed configuration and cache absent using "
            f"a transient exact registration and codex plugin remove {PLUGIN_REF}."
        )
        print("Restored the original absent local marketplace/source state exactly.")
        print(f"Preserved source repository: {self.bid_root}")
        return original_exit_code

    def uninstall(self) -> int:
        state = self.load_marketplace()
        source_preflight_snapshot = self.validate_source()
        local_entry_present = state.existed and state.bid_present
        local_source_present = source_preflight_snapshot is not None
        if local_entry_present != local_source_present:
            raise ConflictError(
                "local bid state is partial; expected both the exact marketplace "
                "entry and source symlink before uninstall."
            )

        if not local_entry_present:
            return self.uninstall_with_transient_local_registration(state)

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

        codex_installed_before = self.codex_plugin_installed_with_contract(
            state.original_snapshot, source_preflight_snapshot
        )
        cleanup_started = False
        try:
            codex_result = self.run_codex("remove")
            if codex_result.interrupted:
                return self.reconcile_interrupted_remove(
                    codex_result.interruption_exit_code or 130,
                    codex_installed_before,
                    source_preflight_snapshot,
                )
            if codex_result.returncode != 0:
                try:
                    recovery_interruption_code = self.restore_codex_state_with_contract(
                        codex_installed_before,
                        state.original_snapshot,
                        source_preflight_snapshot,
                    )
                except Exception as error:  # noqa: BLE001 - incomplete recovery.
                    recovery_interruption_code = self.recovery_interruption_exit_code(
                        error
                    )
                    print(
                        f"codex plugin remove failed ({codex_result.returncode}); "
                        f"Codex state reconciliation failed: {error}",
                        file=sys.stderr,
                    )
                    return recovery_interruption_code or 1
                print(
                    f"codex plugin remove failed ({codex_result.returncode}); "
                    "Codex state reconciled and local state unchanged.",
                    file=sys.stderr,
                )
                return recovery_interruption_code or codex_result.returncode
            codex_removed = codex_installed_before
            marketplace_written_snapshot: MarketplaceSnapshot | None = None
            source_unlinked = False
            cleanup_started = True
            try:
                recovery_interruption_code = self.restore_codex_state_with_contract(
                    False, state.original_snapshot, source_preflight_snapshot
                )
            except Exception as error:  # noqa: BLE001 - exact contract required.
                return self.reconcile_unverified_zero_remove(
                    codex_installed_before, source_preflight_snapshot, error
                )
            if recovery_interruption_code is not None:
                return self.reconcile_interrupted_remove(
                    recovery_interruption_code,
                    codex_installed_before,
                    source_preflight_snapshot,
                )
            with defer_termination_signals():
                self.require_source_snapshot(source_preflight_snapshot)
                marketplace_written_snapshot = self.write_marketplace(
                    state.payload, state.original_mode, state.original_snapshot
                )
            with defer_termination_signals():
                self.remove_owned_source(source_preflight_snapshot)
                source_unlinked = True
        except BaseException as error:  # noqa: BLE001 - restore pre-operation state.
            if not cleanup_started:
                if isinstance(error, KeyboardInterrupt):
                    self.reconcile_interrupted_remove(
                        143 if isinstance(error, ParentTermination) else 130,
                        codex_installed_before,
                        source_preflight_snapshot,
                    )
                raise
            if not source_unlinked:
                try:
                    source_unlinked = not self.capture_source_snapshot().exists
                except Exception:
                    source_unlinked = False
            if codex_removed:
                recovery_result = self.compensate_failed_uninstall(
                    error,
                    state,
                    marketplace_written_snapshot,
                    source_preflight_snapshot,
                    source_unlinked,
                )
            else:
                recovery_result = self.rollback_local_only_uninstall(
                    error,
                    state,
                    marketplace_written_snapshot,
                    source_preflight_snapshot,
                    source_unlinked,
                )
            if isinstance(error, KeyboardInterrupt):
                raise
            return recovery_result

        if codex_installed_before:
            print(
                "Removed Codex-owned installed configuration and cache with "
                f"codex plugin remove {PLUGIN_REF}."
            )
        else:
            print(
                "Ensured Codex-owned installed configuration and cache are "
                f"absent with codex plugin remove {PLUGIN_REF}."
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
    try:
        with parent_termination_handler():
            with lifecycle.lifecycle_lock():
                return (
                    lifecycle.install()
                    if sys.argv[1] == "install"
                    else lifecycle.uninstall()
                )
    finally:
        lifecycle.report_recovery_artifacts()


try:
    raise SystemExit(main())
except ParentTermination as error:
    print(
        "Local plugin lifecycle terminated after transaction recovery.",
        file=sys.stderr,
    )
    raise SystemExit(143) from error
except KeyboardInterrupt as error:
    print(
        "Local plugin lifecycle interrupted before state could be changed safely.",
        file=sys.stderr,
    )
    raise SystemExit(130) from error
except ConflictError as error:
    print(f"Conflict: {error}", file=sys.stderr)
    raise SystemExit(1) from error
except Exception as error:  # noqa: BLE001 - CLI emits one actionable failure.
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1) from error
