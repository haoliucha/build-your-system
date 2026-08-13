#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def versioned_candidate(requested: Path, version: int) -> Path:
    if version == 1:
        return requested
    return requested.with_name(
        f"{requested.stem}-v{version}{requested.suffix}"
    )


def copy_to_temporary_file(source: Path, directory: Path) -> tuple[Path, str]:
    digest = hashlib.sha256()
    temporary_path: Path | None = None

    try:
        with source.open("rb") as source_file:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".x-image-place-",
                dir=directory,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                while chunk := source_file.read(1024 * 1024):
                    temporary_file.write(chunk)
                    digest.update(chunk)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

        os.chmod(temporary_path, source.stat().st_mode & 0o777)
        return temporary_path, digest.hexdigest()
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def place_original(source: Path, requested: Path) -> tuple[Path, str]:
    source = source.expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"Source is not a file: {source}")

    requested = requested.expanduser().resolve(strict=False)
    requested.parent.mkdir(parents=True, exist_ok=True)

    temporary_path, sha256 = copy_to_temporary_file(
        source,
        requested.parent,
    )
    try:
        version = 1
        while True:
            candidate = versioned_candidate(requested, version)
            try:
                os.link(temporary_path, candidate)
            except FileExistsError:
                version += 1
                continue
            return candidate, sha256
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Place an original generated file without overwriting an "
            "existing destination."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    placed, sha256 = place_original(args.source, args.destination)
    print(
        json.dumps(
            {
                "path": str(placed),
                "sha256": sha256,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
