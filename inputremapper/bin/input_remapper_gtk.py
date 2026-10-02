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

"""Starts the user interface."""

from __future__ import annotations

import atexit
import fcntl
import os
import subprocess
import sys
import tempfile
from argparse import ArgumentParser
from typing import Tuple

import gi

from inputremapper.bin.process_utils import ProcessUtils

gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gtk, GLib

# Wayland compositors associate a window with its desktop entry by app_id, and
# GTK derives app_id from the program name (input-remapper-gtk). Inside Flatpak
# the exported entry is named after the app-id instead, so nothing matches and
# Plasma falls back to the generic Wayland logo. Announce the app-id as program
# name, before any window exists. Outside Flatpak the default already matches
# input-remapper-gtk.desktop.
if "FLATPAK_ID" in os.environ:
    GLib.set_prgname(os.environ["FLATPAK_ID"])

# https://github.com/Nuitka/Nuitka/issues/607#issuecomment-650217096
Gtk.init()

from inputremapper.gui.gettext import _, LOCALE_DIR
from inputremapper.gui.reader_service import ReaderService
from inputremapper.daemon import DaemonProxy, Daemon
from inputremapper.logging.logger import logger, monitor_log_path
from inputremapper.gui.messages.message_broker import MessageBroker, MessageType
from inputremapper.configs.keyboard_layout import keyboard_layout
from inputremapper.gui.data_manager import DataManager
from inputremapper.gui.user_interface import UserInterface
from inputremapper.gui.controller import Controller
from inputremapper.injection.global_uinputs import GlobalUInputs, FrontendUInput
from inputremapper.groups import _Groups
from inputremapper.gui.reader_client import ReaderClient
from inputremapper.configs.global_config import GlobalConfig
from inputremapper.configs.migrations import Migrations

# Kept open so the lock lives as long as the process.
_instance_lock = None


class InputRemapperGtkBin:
    @staticmethod
    def _show_startup_error(summary: str) -> None:
        details = f"{summary}\n\nLog: {monitor_log_path()}"
        dialog = Gtk.MessageDialog(
            None,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.ERROR,
            Gtk.ButtonsType.CLOSE,
            "Input Remapper failed to start",
        )
        dialog.format_secondary_text(details)
        dialog.run()
        dialog.destroy()

    @staticmethod
    def _acquire_single_instance_lock() -> bool:
        """Take the GUI lock for the lifetime of the process. False if held."""
        global _instance_lock
        if _instance_lock is not None:
            return True

        flatpak_id = os.environ.get("FLATPAK_ID")
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if flatpak_id and runtime_dir:
            # The sandbox shares this directory between instances of the app.
            folder = os.path.join(runtime_dir, "app", flatpak_id)
        else:
            folder = os.path.join(
                tempfile.gettempdir(), f"input-remapper-{os.getuid()}"
            )
        os.makedirs(folder, exist_ok=True)

        _instance_lock = open(os.path.join(folder, "gui.lock"), "w")
        try:
            fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    @staticmethod
    def _background_permission_allowed_non_interactive() -> bool:
        try:
            result = subprocess.run(
                [
                    "pkcheck",
                    "--action-id",
                    "inputremapper",
                    "--process",
                    str(os.getpid()),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def main() -> Tuple[
        UserInterface,
        Controller,
        DataManager,
        MessageBroker,
        DaemonProxy,
        GlobalConfig,
    ]:
        try:
            parser = ArgumentParser()
            parser.add_argument(
                "-d",
                "--debug",
                action="store_true",
                dest="debug",
                help=_("Displays additional debug information"),
                default=False,
            )

            options = parser.parse_args(sys.argv[1:])
            logger.update_verbosity(options.debug)
            logger.log_info("input-remapper-gtk")
            logger.debug("Using locale directory: {}".format(LOCALE_DIR))

            # Login can start the GUI twice in the same second (XDG autostart and
            # session restore). Only the first one goes on.
            if not InputRemapperGtkBin._acquire_single_instance_lock():
                logger.info("Another input-remapper GUI is already starting, exiting")
                sys.exit(0)

            global_uinputs = GlobalUInputs(FrontendUInput)

            migrations = Migrations(global_uinputs)
            migrations.migrate()

            message_broker = MessageBroker()

            global_config = GlobalConfig()

            # Create the ReaderClient before we start the reader-service, otherwise the
            # privileged service creates and owns those pipes, and then they cannot be accessed
            # by the user.
            reader_client = ReaderClient(message_broker, _Groups())

            if ProcessUtils.count_python_processes("input-remapper-gtk") >= 2:
                logger.warning(
                    "Another input-remapper GUI is already running. "
                    "This can cause problems while recording keys"
                )

            start_hidden = os.environ.get("INPUT_REMAPPER_START_HIDDEN") == "1"
            non_interactive_allowed = (
                InputRemapperGtkBin._background_permission_allowed_non_interactive()
            )
            logger.info(
                "Startup mode hidden=%s non-interactive background auth allowed=%s",
                start_hidden,
                non_interactive_allowed,
            )
            started = InputRemapperGtkBin.start_reader_service(
                allow_user_interaction=False,
                fail_hard=False,
            )
            if started:
                logger.info(
                    "Startup: reader-service started without interactive prompt"
                )
            else:
                logger.info(
                    "Startup: deferring reader-service startup "
                    "(background permission unavailable)"
                )

            daemon = Daemon.connect()

            data_manager = DataManager(
                message_broker,
                global_config,
                reader_client,
                daemon,
                global_uinputs,
                keyboard_layout,
            )
            controller = Controller(message_broker, data_manager)
            user_interface = UserInterface(message_broker, controller)
            controller.set_gui(user_interface)

            message_broker.signal(MessageType.init)

            atexit.register(lambda: InputRemapperGtkBin.stop(daemon, controller))

            Gtk.main()

            # For tests:
            return (
                user_interface,
                controller,
                data_manager,
                message_broker,
                daemon,
                global_config,
            )
        except SystemExit as error:
            if error.code not in (None, 0):
                logger.exception("GUI startup aborted with exit code %s", error.code)
                InputRemapperGtkBin._show_startup_error(
                    f"Startup aborted with exit code {error.code}."
                )
            raise
        except Exception as error:
            logger.exception("GUI startup failed")
            InputRemapperGtkBin._show_startup_error(str(error))
            sys.exit(1)

    @staticmethod
    def start_reader_service(
        allow_user_interaction: bool = True, fail_hard: bool = True
    ) -> bool:
        if ProcessUtils.count_python_processes("input-remapper-reader-service") >= 1:
            logger.info("Found an input-remapper-reader-service to already be running")
            return True

        try:
            ReaderService.pkexec_reader_service(
                allow_user_interaction=allow_user_interaction
            )
            return True
        except Exception as e:
            if not fail_hard:
                logger.info("Deferring reader-service startup: %s", e)
                return False
            logger.error(e)
            sys.exit(11)

    @staticmethod
    def stop(daemon, controller):
        if isinstance(daemon, Daemon):
            # have fun debugging completely unrelated tests if you remove this
            daemon.stop_all()

        controller.close()
