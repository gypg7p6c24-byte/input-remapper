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
import pwd
import shlex
import time
from logging.handlers import RotatingFileHandler
from typing import cast

from inputremapper.logging.formatter import ColorfulFormatter

from inputremapper.installation_info import VERSION, COMMIT_HASH
from inputremapper.user import UserUtils


start = time.time()

previous_key_debug_log = None
previous_write_debug_log = None

MONITOR_ENV = "INPUT_REMAPPER_MONITOR"
MONITOR_PATH_ENV = "INPUT_REMAPPER_MONITOR_PATH"
MONITOR_DEFAULT_FILENAME = "pilot-monitor.log"
MONITOR_MAX_BYTES = 20 * 1024 * 1024
MONITOR_BACKUP_COUNT = 8


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def monitoring_enabled() -> bool:
    raw = os.getenv(MONITOR_ENV)
    if raw is None:
        # Pilot mode enabled by default; set INPUT_REMAPPER_MONITOR=0 to disable.
        return True
    return _is_truthy(raw)


def monitor_log_path() -> str:
    path = os.getenv(MONITOR_PATH_ENV)
    if path:
        return os.path.abspath(os.path.expanduser(path))

    xdg_config_home = os.getenv("XDG_CONFIG_HOME", os.path.join(UserUtils.home, ".config"))
    return os.path.join(
        xdg_config_home,
        "input-remapper-2",
        "logs",
        MONITOR_DEFAULT_FILENAME,
    )


def monitor_env_prefix() -> str:
    if not monitoring_enabled():
        return ""

    path = monitor_log_path()
    return (
        "env "
        f"{MONITOR_ENV}=1 "
        f"{MONITOR_PATH_ENV}={shlex.quote(path)} "
    )


def monitor_env_vars() -> dict[str, str]:
    if not monitoring_enabled():
        return {}
    return {
        MONITOR_ENV: "1",
        MONITOR_PATH_ENV: monitor_log_path(),
    }


def _monitor_log(level: int, tag: str, message: str, *args) -> None:
    if not monitoring_enabled():
        return
    logger.log(level, f"MONITOR_{tag} " + message, *args)


def monitor_debug(tag: str, message: str, *args) -> None:
    _monitor_log(logging.DEBUG, tag, message, *args)


def monitor_info(tag: str, message: str, *args) -> None:
    _monitor_log(logging.INFO, tag, message, *args)


def _monitor_owner_ids() -> tuple[int, int] | None:
    try:
        passwd = pwd.getpwnam(UserUtils.user)
    except KeyError:
        return None
    return passwd.pw_uid, passwd.pw_gid


def _restore_user_ownership(path: str) -> None:
    owner = _monitor_owner_ids()
    if owner is None or os.geteuid() != 0:
        return

    uid, gid = owner
    if uid == 0:
        return

    try:
        os.chown(path, uid, gid)
    except OSError:
        pass


def _create_monitor_handler(path: str) -> RotatingFileHandler:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    _restore_user_ownership(directory)

    handler = RotatingFileHandler(
        path,
        maxBytes=MONITOR_MAX_BYTES,
        backupCount=MONITOR_BACKUP_COUNT,
        encoding="utf-8",
    )
    _restore_user_ownership(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

    handler._input_remapper_monitor_handler = True
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(process)d %(name)s %(levelname)s %(filename)s:%(lineno)d: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


class Logger(logging.Logger):

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
        is_monitoring = monitoring_enabled()
        if debug or is_monitoring:
            self.setLevel(logging.DEBUG)
        else:
            self.setLevel(logging.INFO)

        for handler in self.handlers:
            if getattr(handler, "_input_remapper_monitor_handler", False):
                continue
            handler.setFormatter(ColorfulFormatter(debug))
            if getattr(handler, "_input_remapper_stream_handler", False):
                handler.setLevel(logging.DEBUG if debug else logging.INFO)

    @classmethod
    def bootstrap_logger(cls):
        # https://github.com/python/typeshed/issues/1801
        logging.setLoggerClass(cls)
        logger = cast(cls, logging.getLogger("input-remapper"))
        monitor_path = None

        stream_handler = logging.StreamHandler()
        stream_handler._input_remapper_stream_handler = True
        stream_handler.setFormatter(ColorfulFormatter(False))
        stream_handler.setLevel(logging.INFO)
        logger.addHandler(stream_handler)

        if monitoring_enabled():
            path = monitor_log_path()
            monitor_path = path
            try:
                monitor_handler = _create_monitor_handler(path)
            except OSError as error:
                monitor_path = None
                logger.warning(
                    'Pilot monitoring disabled for "%s": %s',
                    path,
                    error,
                )
            else:
                logger.addHandler(monitor_handler)

        logger.setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        if monitor_path:
            logger.info('Pilot monitoring enabled, writing to "%s"', monitor_path)
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
