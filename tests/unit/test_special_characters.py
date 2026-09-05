#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Typing characters the layout only reaches through a shift level."""

import unittest

from evdev.ecodes import EV_KEY, KEY_2, KEY_E, KEY_LEFTSHIFT, KEY_RIGHTALT

from inputremapper.configs.keyboard_layout import keyboard_layout


class TestCharacterLookup(unittest.TestCase):
    def setUp(self):
        keyboard_layout.populate()
        self._saved = keyboard_layout._characters
        keyboard_layout._characters = {
            "@": [KEY_2, ["ISO_Level3_Shift"]],
            "E": [KEY_E, ["Shift_L"]],
            "e": [KEY_E, []],
        }
        keyboard_layout._set("ISO_Level3_Shift", KEY_RIGHTALT)
        keyboard_layout._set("Shift_L", KEY_LEFTSHIFT)

    def tearDown(self):
        keyboard_layout._characters = self._saved

    def test_get_character(self):
        self.assertEqual(
            keyboard_layout.get_character("@"), (KEY_2, ["ISO_Level3_Shift"])
        )
        self.assertEqual(keyboard_layout.get_character("e"), (KEY_E, []))
        self.assertIsNone(keyboard_layout.get_character("ab"))
        self.assertIsNone(keyboard_layout.get_character("\u00e9"))

    def test_key_task_wraps_the_press_in_its_modifiers(self):
        import asyncio

        from inputremapper.injection.macros.tasks.key import KeyTask

        written = []

        async def run():
            task = KeyTask.__new__(KeyTask)
            task.get_argument = lambda _name: type(
                "V", (), {"get_value": lambda s: "@"}
            )()

            async def no_pause():
                return None

            task.keycode_pause = no_pause
            await task.run(lambda *event: written.append(event))

        asyncio.run(run())

        self.assertEqual(
            written,
            [
                (EV_KEY, KEY_RIGHTALT, 1),
                (EV_KEY, KEY_2, 1),
                (EV_KEY, KEY_2, 0),
                (EV_KEY, KEY_RIGHTALT, 0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
