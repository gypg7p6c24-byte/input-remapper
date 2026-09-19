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


import concurrent.futures
import os
import tempfile
import threading
import unittest

from inputremapper.configs.paths import PathUtils
from tests.lib.test_setup import test_setup
from tests.lib.tmp import tmp


def _raise(error):
    raise error


@test_setup
class TestPaths(unittest.TestCase):
    def test_touch(self):
        with tempfile.TemporaryDirectory() as local_tmp:
            path_abcde = os.path.join(local_tmp, "a/b/c/d/e")
            PathUtils.touch(path_abcde)
            self.assertTrue(os.path.exists(path_abcde))
            self.assertTrue(os.path.isfile(path_abcde))
            self.assertRaises(
                ValueError,
                lambda: PathUtils.touch(os.path.join(local_tmp, "a/b/c/d/f/")),
            )

    def test_mkdir(self):
        with tempfile.TemporaryDirectory() as local_tmp:
            path_bcde = os.path.join(local_tmp, "b/c/d/e")
            PathUtils.mkdir(path_bcde)
            self.assertTrue(os.path.exists(path_bcde))
            self.assertTrue(os.path.isdir(path_bcde))

    def test_create_the_same_path_concurrently(self):
        """The gui, the service and the reader start at the same time."""
        with tempfile.TemporaryDirectory() as local_tmp:
            path_abc = os.path.join(local_tmp, "a/b/c")
            barrier = threading.Barrier(8)

            def create():
                barrier.wait()
                PathUtils.mkdir(path_abc)
                PathUtils.touch(os.path.join(path_abc, "pipe"))

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(create) for _ in range(8)]
                for future in futures:
                    # raises whatever the thread raised, FileExistsError included
                    future.result()

            self.assertTrue(os.path.isdir(path_abc))
            self.assertTrue(os.path.isfile(os.path.join(path_abc, "pipe")))

    def test_get_preset_path(self):
        self.assertTrue(
            PathUtils.get_preset_path().startswith(PathUtils.get_config_path())
        )
        self.assertTrue(PathUtils.get_preset_path().endswith("presets"))
        self.assertTrue(PathUtils.get_preset_path("a").endswith("presets/a"))
        self.assertTrue(
            PathUtils.get_preset_path("a", "b").endswith("presets/a/b.json")
        )

    def test_get_config_path(self):
        # might end with /beta_XXX
        self.assertTrue(
            PathUtils.get_config_path().startswith(f"{tmp}/.config/input-remapper")
        )
        self.assertTrue(PathUtils.get_config_path("a", "b").endswith("a/b"))

    def test_split_all(self):
        self.assertListEqual(PathUtils.split_all("a/b/c/d"), ["a", "b", "c", "d"])
