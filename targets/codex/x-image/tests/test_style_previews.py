from __future__ import annotations

import hashlib
import struct
import unittest

from helpers import SHARED, STYLE_IDS, read_json_optional, read_optional


def png_dimensions(path):
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


class StylePreviewTests(unittest.TestCase):
    def setUp(self):
        self.preview_dir = SHARED / "previews"
        self.manifest_path = self.preview_dir / "manifest.json"
        self.manifest = read_json_optional(self.manifest_path)

    def test_manifest_covers_every_builtin_style_in_stable_order(self):
        self.assertEqual(self.manifest.get("schemaVersion"), 1)
        entries = self.manifest.get("styles", [])
        self.assertEqual(
            [entry.get("id") for entry in entries],
            list(STYLE_IDS),
        )

    def test_each_style_has_a_versioned_static_png_preview(self):
        for entry in self.manifest.get("styles", []):
            style_id = entry.get("id")
            path = self.preview_dir / entry.get("preview", "")
            with self.subTest(style_id=style_id):
                self.assertEqual(entry.get("ratio"), "16:9")
                self.assertEqual(entry.get("benchmark"), "capture-clarify-connect-express")
                self.assertTrue(entry.get("displayNameZh"))
                self.assertTrue(entry.get("useForZh"))
                self.assertTrue(path.is_file())
                if path.is_file():
                    width, height = png_dimensions(path)
                    self.assertGreaterEqual(width, 1600)
                    self.assertGreaterEqual(height, 900)
                    self.assertAlmostEqual(width / height, 16 / 9, delta=0.02)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    self.assertEqual(entry.get("sha256"), digest)

    def test_gallery_explains_zero_cost_and_reference_semantics(self):
        gallery = read_optional(self.preview_dir / "README.md")
        for phrase in (
            "zero generation calls",
            "same neutral benchmark",
            "style reference, not a pixel-level promise",
            "terminal-tech",
            "editorial-material",
            "data-editorial",
            "tactile-systems",
            "isometric-systems",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, gallery)


if __name__ == "__main__":
    unittest.main()
