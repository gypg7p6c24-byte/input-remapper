#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A corrupt shortcuts.vdf must not take the GUI down with it."""

import unittest

from inputremapper.utils import _parse_binary_vdf


class TestBinaryVdfParser(unittest.TestCase):
    def test_zero_filled_file_does_not_recurse(self):
        # a Steam crash leaves truncated / zero-filled files behind; every two
        # null bytes used to open another nesting level, until RecursionError
        self.assertIsInstance(_parse_binary_vdf(b"\x00" * 20000), dict)

    def test_truncated_file_returns_what_it_could_read(self):
        self.assertIsInstance(_parse_binary_vdf(b"\x00shortcuts\x00\x00"), dict)

    def test_parses_a_simple_document(self):
        data = b"\x00shortcuts\x00\x000\x00\x01appname\x00Doom\x00\x08\x08\x08"
        parsed = _parse_binary_vdf(data)
        self.assertEqual(parsed["shortcuts"]["0"]["appname"], "Doom")


if __name__ == "__main__":
    unittest.main()
