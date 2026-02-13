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

"""Logging setup for input-remapper."""

import logging
import os
import time
from typing import Optional
from typing import cast

from inputremapper.logging.formatter import ColorfulFormatter

from inputremapper.installation_info import VERSION, COMMIT_HASH


start = time.time()

previous_key_debug_log = None
previous_write_debug_log = None


class Logger(logging.Logger):
    _file_handler: Optional[logging.Handler] = None
    _file_handler_path: Optional[str] = None

    def debug_mapping_handler(self, mapping_handler):
        """Parse the structure of a mapping_handler and log it."""
        if not self.isEnabledFor(logging.DEBUG):
            return

        lines_and_indent = self._parse_mapping_handler(mapping_handler)
        for line in lines_and_indent:
            indent = "    "
            msg = indent * line[1] + line[0]
            self._log(logging.DEBUG, msg, args=None)

    def write(self, key, uinput):
        """Log that an event is being written

        Parameters
        ----------
        key
            anything that can be string formatted, but usually a tuple of
            (type, code, value) tuples
        """
        # pylint: disable=protected-access
        if not self.isEnabledFor(logging.DEBUG):
            return

        global previous_write_debug_log

        str_key = repr(key)
        str_key = str_key.replace(",)", ")")

        msg = f'Writing {str_key} to "{uinput.name}"'

        if msg == previous_write_debug_log:
            # avoid some super spam from EV_ABS events
            return

        previous_write_debug_log = msg

        self._log(logging.DEBUG, msg, args=None, stacklevel=2)

    def _parse_mapping_handler(self, mapping_handler):
        indent = 0
        lines_and_indent = []
        while True:
            if isinstance(mapping_handler, list):
                for sub_handler in mapping_handler:
                    sub_list = self._parse_mapping_handler(sub_handler)
                    for line in sub_list:
                        line[1] += indent
                    lines_and_indent.extend(sub_list)
                break

            lines_and_indent.append([repr(mapping_handler), indent])
            try:
                mapping_handler = mapping_handler.child
            except AttributeError:
                break

            indent += 1
        return lines_and_indent

    def is_debug(self) -> bool:
        """True, if the logger is currently in DEBUG mode."""
        return self.level <= logging.DEBUG

    def log_info(self, name: str = "input-remapper") -> None:
        """Log version and name to the console."""
        logger.info(
            "%s %s %s https://github.com/sezanzeb/input-remapper",
            name,
            VERSION,
            COMMIT_HASH,
        )

        if EVDEV_VERSION:
            logger.info("python-evdev %s", EVDEV_VERSION)

        if self.is_debug():
            logger.warning(
                "Debug level will log all your keystrokes! Do not post this "
                "output in the internet if you typed in sensitive or private "
                "information with your device!"
            )

    def update_verbosity(self, debug: bool) -> None:
        """Set the logging verbosity according to the settings object."""
        if debug:
            self.setLevel(logging.DEBUG)
        else:
            self.setLevel(logging.INFO)

        for handler in self.handlers:
            handler.setFormatter(ColorfulFormatter(debug))

        self._configure_file_handler(debug)

    def _configure_file_handler(self, debug: bool) -> None:
        if not debug:
            if self._file_handler is not None:
                self.removeHandler(self._file_handler)
                try:
                    self._file_handler.close()
                finally:
                    self._file_handler = None
                    self._file_handler_path = None
            return

        if self._file_handler is not None:
            return

        path = _default_debug_log_path()
        if not path:
            return

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            # Ignore directory creation errors; FileHandler will raise if needed.
            pass

        try:
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(process)d %(levelname)s %(filename)s:%(lineno)d: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            self.addHandler(handler)
            self._file_handler = handler
            self._file_handler_path = path
            self.info("Debug logs will be written to %s", path)
        except Exception as exc:
            self.warning("Could not open debug log file %s: %s", path, exc)

    @classmethod
    def bootstrap_logger(cls):
        # https://github.com/python/typeshed/issues/1801
        logging.setLoggerClass(cls)
        logger = cast(cls, logging.getLogger("input-remapper"))

        handler = logging.StreamHandler()
        handler.setFormatter(ColorfulFormatter(False))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        return logger


logger = Logger.bootstrap_logger()


EVDEV_VERSION = None
try:
    from importlib.metadata import version

    EVDEV_VERSION = version("evdev")
except Exception as error:
    logger.info("Could not figure out the evdev version")
    logger.debug(error)

# check if the version is something like 1.5.0-beta or 1.5.0-beta.5
IS_BETA = "beta" in VERSION


def _default_debug_log_path() -> Optional[str]:
    path = os.environ.get("INPUT_REMAPPER_DEBUG_LOG")
    if path:
        return path

    uid = os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID")
    user = os.environ.get("PKEXEC_USER") or os.environ.get("SUDO_USER")
    home = None
    if user:
        home = os.path.expanduser(f"~{user}")
    if not home and uid:
        try:
            import pwd

            home = pwd.getpwuid(int(uid)).pw_dir
        except Exception:
            home = None
    if not home:
        home = os.path.expanduser("~")

    if home:
        return os.path.join(home, ".config", "input-remapper-2", "debug.log")

    return os.path.join("/tmp", "input-remapper-debug.log")
