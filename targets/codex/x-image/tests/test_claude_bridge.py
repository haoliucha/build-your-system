from __future__ import annotations

import unittest

from helpers import CLAUDE_X, read_optional


class ClaudeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.command = read_optional(CLAUDE_X / "commands" / "image.md")
        self.skill = read_optional(
            CLAUDE_X / "skills" / "x-image" / "SKILL.md"
        )
        self.text = self.command + "\n" + self.skill

    def test_delegates_to_codex_rescue_once(self):
        self.assertIn("codex:codex-rescue", self.text)
        self.assertIn("exactly once", self.text)
        self.assertIn("--fresh", self.text)
        self.assertIn("--wait", self.text)
        self.assertIn("verbatim", self.text.lower())

    def test_requires_synchronous_blocking_transport(self):
        for name, source in (
            ("command", self.command),
            ("skill", self.skill),
        ):
            with self.subTest(name=name):
                self.assertIn("run_in_background: false", source)
                self.assertIn(
                    "If the Agent tool still launches the subagent in the background",
                    source,
                )
                self.assertIn("TaskOutput", source)
                self.assertIn("block: true", source)
                self.assertIn("same Rescue task", source)

    def test_forbids_intermediate_user_visible_messages(self):
        for phrase in (
            "Do not announce delegation",
            "Do not emit progress or status messages",
            "only user-visible assistant message",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_forwards_arguments_and_working_directory(self):
        self.assertIn("$ARGUMENTS", self.command)
        self.assertIn("current working directory", self.text.lower())
        self.assertIn("native `x-image` skill", self.text)

    def test_marks_claude_rescue_origin(self):
        for phrase in (
            "Invocation origin: Claude through Codex Rescue",
            "Host: Claude through Codex Rescue",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_requires_codex_to_own_the_complete_workflow(self):
        for phrase in (
            "source analysis",
            "built-in ImageGen call",
            "file placement",
            "QA",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_has_no_owned_codex_or_image_pipeline(self):
        forbidden = [
            "codex exec",
            "cover-gen.sh",
            "magick",
            "sips",
            "image_gen(",
        ]
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, self.text)

    def test_has_setup_failure_instruction(self):
        self.assertIn("/codex:setup", self.text)
        self.assertIn("unavailable", self.text.lower())
        self.assertIn("unauthenticated", self.text.lower())


if __name__ == "__main__":
    unittest.main()
