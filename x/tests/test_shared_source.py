from __future__ import annotations

import unittest

from helpers import REFERENCE_NAMES, STYLE_NAMES, X_IMAGE


class SharedSourceTests(unittest.TestCase):
    def test_all_reference_files_exist_in_the_shared_skill(self):
        for name in REFERENCE_NAMES:
            with self.subTest(name=name):
                self.assertTrue((X_IMAGE / "references" / name).is_file())

    def test_all_style_files_exist_in_the_shared_skill(self):
        for name in STYLE_NAMES:
            with self.subTest(name=name):
                self.assertTrue((X_IMAGE / "styles" / name).is_file())


if __name__ == "__main__":
    unittest.main()
