#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from pathlib import Path


CONTROL_PATH = Path(__file__).resolve().parents[2] / "DEBIAN" / "control"


class TestUbuntuControl(unittest.TestCase):
    def setUp(self):
        self.control = CONTROL_PATH.read_text(encoding="utf-8")
        self.depends = self._parse_control_list("Depends")
        self.recommends = self._parse_control_list("Recommends")

    def _parse_control_list(self, field_name):
        line = next(
            line for line in self.control.splitlines() if line.startswith(f"{field_name}:")
        )
        return [entry.strip() for entry in line.split(":", 1)[1].split(",")]

    def test_runtime_depends_excludes_build_dependencies(self):
        for dependency in (
            "build-essential",
            "libpython3-dev",
            "libdbus-1-dev",
            "libgtksourceview-4-dev",
            "gettext",
        ):
            self.assertNotIn(dependency, self.depends)

    def test_runtime_depends_match_ubuntu_runtime_packages(self):
        self.assertNotIn("policykit-1", self.depends)
        self.assertIn("pkexec", self.depends)
        self.assertIn("polkitd", self.depends)
        self.assertIn("gir1.2-gtk-3.0", self.depends)
        self.assertIn("gir1.2-gtksource-4", self.depends)

    def test_tray_indicator_is_optional_on_ubuntu(self):
        self.assertNotIn("gir1.2-appindicator3-0.1", self.depends)
        self.assertNotIn("gir1.2-ayatanaappindicator3-0.1", self.depends)
        self.assertIn("gir1.2-appindicator3-0.1", self.recommends)
