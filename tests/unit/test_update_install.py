#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import unittest
from unittest.mock import patch

import gi

gi.require_version("Gtk", "3.0")

from inputremapper.gui.user_interface import UserInterface
from inputremapper.user import flatpak_scope_flags


class TestFlatpakScopeFlags(unittest.TestCase):
    def test_system_scope_stays_interactive(self):
        """--noninteractive forbids flatpak to ask polkit for the privileged
        InstallBundle operation, which is then refused outright."""
        with patch("inputremapper.user.flatpak_installation_scope", lambda: "--system"):
            self.assertEqual(flatpak_scope_flags(), ["--system"])

    def test_user_scope_stays_silent(self):
        with patch("inputremapper.user.flatpak_installation_scope", lambda: "--user"):
            self.assertEqual(flatpak_scope_flags(), ["--user", "--noninteractive"])


class TestHostCommandOutput(unittest.TestCase):
    def test_failure_reports_what_the_installer_said(self):
        """A bare exit code could only be turned into a cause by relaunching the
        app from a terminal. The installer's own message has to reach the user."""
        message = (
            "Error: Failed to install bundle io.github.sezanzeb.input_remapper: "
            "Flatpak system operation InstallBundle not allowed for user"
        )
        result = subprocess.CompletedProcess([], 1, stdout="", stderr=message + "\n")
        with patch("subprocess.run", return_value=result):
            error = UserInterface._run_host_command(
                None, ["flatpak-spawn", "--host", "flatpak", "install"], capture=True
            )
        self.assertIn(message, error)

    def test_success_reports_nothing(self):
        result = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch("subprocess.run", return_value=result):
            self.assertIsNone(
                UserInterface._run_host_command(None, ["true"], capture=True)
            )


if __name__ == "__main__":
    unittest.main()
