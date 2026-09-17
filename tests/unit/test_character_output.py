#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# input-remapper - GUI for device specific keyboard mappings
# Copyright (C) 2025 sezanzeb <b8x45ygc9@mozmail.com>
#
# This file is part of input-remapper.
#
# input-remapper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# input-remapper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with input-remapper.  If not, see <https://www.gnu.org/licenses/>.

"""Typing a character as the output, on a layout that is not QWERTY."""

import unittest
from unittest.mock import patch

from evdev.ecodes import EV_KEY, KEY_M, KEY_2, KEY_EQUAL

try:
    from pydantic.v1 import ValidationError
except ImportError:
    from pydantic import ValidationError

from inputremapper.configs.keyboard_layout import KeyboardLayout, keyboard_layout
from inputremapper.configs.mapping import Mapping
from tests.lib.test_setup import test_setup


def _mapping(output_symbol: str) -> Mapping:
    return Mapping(
        input_combination=[{"type": EV_KEY, "code": 1}],
        target_uinput="keyboard",
        output_symbol=output_symbol,
    )


@test_setup
class TestCharacterOutput(unittest.TestCase):
    def setUp(self):
        # An AZERTY row: "," sits on the physical QWERTY "m" key, "é" needs
        # shift, "+" needs shift too and would otherwise look like a macro.
        self._characters = keyboard_layout._characters
        keyboard_layout._characters = {
            ",": [KEY_M, []],
            "é": [KEY_2, ["Shift_L"]],
            "+": [KEY_EQUAL, ["Shift_L"]],
        }

    def tearDown(self):
        keyboard_layout._characters = self._characters

    def test_character_without_modifier_is_the_physical_key(self):
        mapping = _mapping(",")
        self.assertEqual(mapping.get_output_type_code(), (EV_KEY, KEY_M))

    def test_character_with_modifier_becomes_a_macro(self):
        mapping = _mapping("é")
        # the X keysym name of the modifier is not in the layout when no
        # session layout could be read, so the evdev name is used
        self.assertIn("modify(KEY_LEFTSHIFT,", mapping.output_symbol)
        self.assertEqual(keyboard_layout.get("KEY_2"), KEY_2)

    def test_plus_is_a_character_not_a_macro(self):
        # "+" passes Parser.is_this_a_macro, which used to make it fail parsing
        self.assertIn("modify(KEY_LEFTSHIFT,", _mapping("+").output_symbol)

    def test_symbol_names_are_untouched(self):
        self.assertEqual(_mapping("KEY_M").output_symbol, "KEY_M")
        self.assertEqual(_mapping("a").output_symbol, "a")

    def test_unknown_character_is_rejected_with_a_hint(self):
        with self.assertRaises(ValidationError) as context:
            _mapping("ø")
        self.assertIn("KEY_M", str(context.exception))


@test_setup
class TestLayoutFailure(unittest.TestCase):
    def test_evdev_names_survive_a_broken_layout(self):
        """A failure while reading the session layout used to leave the table
        half-filled for good, because populate only ever runs once."""
        layout = KeyboardLayout()
        with patch.object(
            KeyboardLayout, "_learn_characters", side_effect=OSError("no display")
        ):
            layout.populate()

        self.assertEqual(layout.get("KEY_M"), KEY_M)
        self.assertEqual(layout.get("disable"), -1)


if __name__ == "__main__":
    unittest.main()
