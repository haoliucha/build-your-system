from __future__ import annotations

import unittest

from helpers import REFERENCE_NAMES, SHARED, STYLE_NAMES


class SharedSourceTests(unittest.TestCase):
    def test_all_reference_files_exist(self):
        for name in REFERENCE_NAMES:
            with self.subTest(name=name):
                self.assertTrue((SHARED / "references" / name).is_file())

    def test_all_style_files_exist(self):
        for name in STYLE_NAMES:
            with self.subTest(name=name):
                self.assertTrue((SHARED / "styles" / name).is_file())


if __name__ == "__main__":
    unittest.main()

