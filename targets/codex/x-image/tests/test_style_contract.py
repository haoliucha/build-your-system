from __future__ import annotations

import unittest

from helpers import SHARED, STYLE_NAMES, read_optional, shared_reference_text


class StyleContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = read_optional(
            SHARED / "references" / "style-policy.md"
        )
        self.styles = {
            name: read_optional(SHARED / "styles" / name)
            for name in STYLE_NAMES
        }

    def test_all_approved_style_ids_exist(self):
        combined = "\n".join(self.styles.values())
        for style_id in (
            "terminal-tech",
            "editorial-material",
            "data-editorial",
            "tactile-systems",
            "isometric-systems",
        ):
            with self.subTest(style_id=style_id):
                self.assertIn(f"id: {style_id}", combined)

    def test_each_style_has_the_complete_spec_fields(self):
        fields = (
            "id:",
            "use-for:",
            "background:",
            "palette:",
            "accent:",
            "medium:",
            "lighting:",
            "composition:",
            "text-rules:",
            "avoid:",
        )
        for name, text in self.styles.items():
            for field in fields:
                with self.subTest(style=name, field=field):
                    self.assertIn(field, text)

    def test_style_merge_precedence(self):
        self.assertIn(
            "explicit user request > asset intent > content semantics > default preset",
            self.policy,
        )

    def test_global_hard_constraints_are_non_overridable(self):
        for phrase in (
            "Global hard constraints are non-overridable.",
            "apply after the style merge",
            "custom style cannot disable",
            "one-call generation",
            "no retry",
            "no post-processing",
            "ratio safety",
            "factual accuracy",
            "legibility",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.policy)

    def test_style_is_locked_across_a_set(self):
        for phrase in (
            "locked style across a set",
            "Style ID",
            "accent color",
            "material and lighting",
            "label treatment",
            "composition density",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.policy)

    def test_custom_style_is_task_local(self):
        self.assertIn("task-local Style Spec", self.policy)
        self.assertIn("does not modify the built-in presets", self.policy)

    def test_terminal_motifs_cannot_create_extra_glyphs(self):
        terminal = self.styles["terminal-tech.md"]
        self.assertIn(
            "Terminal motifs must use abstract geometry only.",
            terminal,
        )
        for phrase in (
            "cursor glyphs",
            "prompt symbols",
            "code characters",
            "pseudo-text",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, terminal)

    def test_data_labels_use_one_nonduplicated_labeling_method(self):
        data_style = self.styles["data-editorial.md"]
        for phrase in (
            "Use exactly one label per category.",
            "Never split a required combined label",
            "standalone category name",
            "Do not repeat category names on an axis",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, data_style)

    def test_editorial_material_cannot_imply_extra_writing(self):
        editorial = self.styles["editorial-material.md"]
        for phrase in (
            "Exact visible text is an exhaustive allowlist.",
            "all other material surfaces completely blank",
            "question marks",
            "ruled lines",
            "grids",
            "body-copy bars",
            "placeholder blocks",
            "pseudo-writing",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, editorial)

    def test_tactile_systems_is_a_specialized_physical_system_diagram(self):
        tactile = self.styles["tactile-systems.md"]
        for phrase in (
            "layered paper",
            "card modules",
            "causal loops",
            "process maps",
            "not a generic editorial-material illustration",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, tactile)

    def test_isometric_systems_uses_spatial_mechanisms_without_factory_cliches(self):
        isometric = self.styles["isometric-systems.md"]
        for phrase in (
            "isometric",
            "conveyors",
            "spatial process",
            "front-facing label plates",
            "factory scenery",
            "robots",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, isometric)

    def test_new_styles_are_routed_without_changing_the_default(self):
        for phrase in (
            "`tactile-systems`",
            "`isometric-systems`",
            "The default preset remains `editorial-material`.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.policy)

    def test_chinese_aliases_route_to_the_new_builtin_styles(self):
        for phrase in (
            "`纸张材料风` and `纸片系统图` route to `tactile-systems`",
            "`等距机械装置` and `等距机械风` route to `isometric-systems`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.policy)


if __name__ == "__main__":
    unittest.main()
