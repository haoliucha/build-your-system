from __future__ import annotations

import unittest
from pathlib import Path

from helpers import CODEX_X_IMAGE, CLAUDE_X, shared_reference_text


class PromptContractTests(unittest.TestCase):
    def setUp(self):
        self.text = shared_reference_text()

    def assert_contract_contains(self, *phrases: str):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_single_call_and_original_output_contract(self):
        self.assert_contract_contains(
            "exactly once",
            "built-in image_gen",
            "no retry",
            "no edit",
            "no post-processing",
            "copy or move the original",
            "actual dimensions",
        )

    def test_path_only_and_explicit_intent_routing(self):
        self.assert_contract_contains(
            "Path-only requests default to exactly one cover.",
            "Explicit cover or illustration language overrides the path-only default.",
            "Illustration requests without a count default to exactly one strongest cognitive anchor.",
        )

    def test_output_directory_defaults(self):
        self.assert_contract_contains(
            "File sources save to a sibling `images/` directory.",
            "Directory sources save to `<source-directory>/images/`.",
            "Direct text, data, and brief inputs save to `<current-working-directory>/images/`.",
        )

    def test_collision_versioning_never_overwrites(self):
        self.assert_contract_contains(
            "Never overwrite an existing asset.",
            "`-v2`",
            "`-v3`",
            "first unused filename",
        )

    def test_ratio_advice_and_override(self):
        self.assert_contract_contains(
            "2.5:1",
            "16:9",
            "3:2",
            "3:4",
            "1:1",
            "2400 × 960",
            "2048 × 1152",
            "1536 × 1024",
            "1536 × 2048",
            "2048 × 2048",
            "A user ratio overrides the intent preset when it is at most 3:1.",
            "Reject ratios wider than 3:1",
            "nearest valid alternative",
        )

    def test_multi_image_failure_stops_remaining_calls(self):
        self.assert_contract_contains(
            "Stop remaining calls after the first failed asset.",
            "Preserve every completed original asset.",
        )

    def test_exact_visible_text_and_data(self):
        self.assert_contract_contains(
            "Exact visible text",
            "quoted verbatim",
            "values",
            "units",
            "category order",
            "axis semantics",
        )

    def test_prompt_schema_and_qa_severity(self):
        self.assert_contract_contains(
            "Use case",
            "Asset type",
            "Primary request",
            "Source-derived content",
            "Style ID",
            "Layout pattern",
            "Single-call instruction",
            "P0",
            "P1",
            "P2",
            "FAIL without regeneration",
        )

    def test_production_paths_forbid_legacy_and_modification_tools(self):
        roots = (
            CLAUDE_X / "commands" / "image.md",
            CLAUDE_X / "skills" / "x-image",
            CLAUDE_X / "shared" / "x-image",
            CODEX_X_IMAGE / ".codex-plugin",
            CODEX_X_IMAGE / "skills",
            CODEX_X_IMAGE / "scripts",
            CODEX_X_IMAGE / "README.md",
        )
        suffixes = {".md", ".sh", ".json"}
        files: list[Path] = []
        for root in roots:
            if root.is_file():
                files.append(root)
            elif root.is_dir():
                files.extend(
                    path
                    for path in root.rglob("*")
                    if path.is_file() and path.suffix in suffixes
                )
        text = "\n".join(path.read_text(encoding="utf-8") for path in files)
        forbidden = (
            "codex exec",
            "magick",
            "sips",
            "ImageMagick",
            "generate-batch",
            "image_gen.py",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()

