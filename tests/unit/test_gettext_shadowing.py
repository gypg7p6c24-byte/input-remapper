# -*- coding: utf-8 -*-
# input-remapper - GUI for device specific keyboard mappings
# Copyright (C) 2026 sezanzeb <b8x45ygc9@mozmail.com>
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

"""`_` is gettext. A parameter named `_` shadows it for the whole function.

Signal handlers are written as `def on_click(self, *_)`, so `_("text")` inside
one calls a tuple and raises. GTK swallows exceptions raised by signal
handlers: the button silently does nothing. Nothing warns about this while
writing the code, so check it here instead of hunting it in a GUI.
"""

import ast
import pathlib
import unittest

SOURCE_DIR = pathlib.Path(__file__).resolve().parents[2] / "inputremapper"


def _parameter_names(args: ast.arguments) -> set:
    names = {arg.arg for arg in args.posonlyargs + args.args + args.kwonlyargs}
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            names.add(extra.arg)
    return names


class TestGettextShadowing(unittest.TestCase):
    def test_no_function_shadows_gettext(self):
        offenders = []

        for path in sorted(SOURCE_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if "_" not in _parameter_names(node.args):
                    continue
                calls = [
                    child.lineno
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "_"
                ]
                if calls:
                    offenders.append(
                        f"{path.name}:{node.lineno} {node.name} "
                        f"takes a parameter named `_` and calls _() "
                        f"on line(s) {calls}"
                    )

        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
