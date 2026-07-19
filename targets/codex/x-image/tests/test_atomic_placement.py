from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CODEX_X_IMAGE


SCRIPT = CODEX_X_IMAGE / "scripts" / "place-original.py"


class AtomicPlacementTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file())

    def run_script(self, source: Path, destination: Path) -> dict[str, str]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(source),
                str(destination),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_re_resolves_when_destination_appears_after_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "generated.png"
            destination = root / "article.png"
            source_bytes = b"original-image-bytes"
            source.write_bytes(source_bytes)

            self.assertFalse(destination.exists())
            destination.write_bytes(b"concurrent-winner")

            report = self.run_script(source, destination)
            placed = Path(report["path"])

            self.assertEqual(destination.read_bytes(), b"concurrent-winner")
            self.assertEqual(placed.name, "article-v2.png")
            self.assertEqual(placed.read_bytes(), source_bytes)
            self.assertEqual(
                report["sha256"],
                hashlib.sha256(source_bytes).hexdigest(),
            )

    def test_concurrent_placements_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_a = root / "generated-a.png"
            source_b = root / "generated-b.png"
            destination = root / "article.png"
            bytes_a = b"a" * 1024 * 1024
            bytes_b = b"b" * 1024 * 1024
            source_a.write_bytes(bytes_a)
            source_b.write_bytes(bytes_b)

            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(SCRIPT),
                        str(source),
                        str(destination),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for source in (source_a, source_b)
            ]
            reports = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, stderr)
                reports.append(json.loads(stdout))

            placed = [Path(report["path"]) for report in reports]
            self.assertEqual(
                {path.name for path in placed},
                {"article.png", "article-v2.png"},
            )
            self.assertEqual(
                {path.read_bytes() for path in placed},
                {bytes_a, bytes_b},
            )
            self.assertEqual(
                list(root.glob(".x-image-place-*")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
