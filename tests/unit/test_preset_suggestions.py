#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bindings that recur across presets are the ones worth proposing."""

import json
import os
import shutil
import tempfile
import unittest

from inputremapper.configs.preset_suggestions import suggest_bindings


def _binding(code, symbol):
    return {
        "input_combination": [{"type": 1, "code": code}],
        "target_uinput": "keyboard",
        "output_symbol": symbol,
    }


class TestPresetSuggestions(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def _write(self, name, bindings):
        path = os.path.join(self.directory, name)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(bindings, file)
        return path

    def test_proposes_what_recurs_and_ignores_one_offs(self):
        common = _binding(30, "a")
        also_common = _binding(31, "b")
        one_off = _binding(32, "c")

        paths = [
            self._write("p1.json", [common, also_common, one_off]),
            self._write("p2.json", [common, also_common]),
            self._write("p3.json", [common]),
        ]

        suggestions = suggest_bindings(paths)
        # most frequent first, the one-off is left out
        self.assertEqual(suggestions, [common, also_common])

    def test_a_binding_repeated_inside_one_preset_is_not_a_habit(self):
        binding = _binding(30, "a")
        paths = [self._write("p1.json", [binding, dict(binding, name="copy")])]
        self.assertEqual(suggest_bindings(paths), [])

    def test_never_proposes_two_bindings_for_the_same_input(self):
        first = _binding(30, "a")
        second = _binding(30, "b")
        paths = [
            self._write("p1.json", [first, second]),
            self._write("p2.json", [first, second]),
        ]
        suggestions = suggest_bindings(paths)
        self.assertEqual(len(suggestions), 1)

    def test_limit_and_threshold(self):
        bindings = [_binding(30 + i, chr(97 + i)) for i in range(12)]
        paths = [
            self._write("p1.json", bindings),
            self._write("p2.json", bindings),
        ]
        self.assertEqual(len(suggest_bindings(paths)), 10)
        self.assertEqual(len(suggest_bindings(paths, minimum_presets=3)), 0)

    def test_survives_corrupt_and_missing_files(self):
        broken = os.path.join(self.directory, "broken.json")
        with open(broken, "w", encoding="utf-8") as file:
            file.write("{not json")
        paths = [broken, os.path.join(self.directory, "absent.json")]
        self.assertEqual(suggest_bindings(paths), [])


if __name__ == "__main__":
    unittest.main()
