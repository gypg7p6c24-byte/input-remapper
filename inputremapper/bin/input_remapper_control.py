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

"""Control the dbus service from the command line."""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from enum import Enum
from typing import Optional

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from inputremapper.configs.global_config import GlobalConfig
from inputremapper.configs.migrations import Migrations
from inputremapper.injection.global_uinputs import GlobalUInputs, FrontendUInput
from inputremapper.logging.logger import logger
from inputremapper.user import UserUtils


class Commands(Enum):
    AUTOLOAD = "autoload"
    START = "start"
    STOP = "stop"
    STOP_ALL = "stop-all"
    HELLO = "hello"
    QUIT = "quit"


class Internals(Enum):
    # internal stuff that the gui uses
    START_DAEMON = "start-daemon"
    START_READER_SERVICE = "start-reader-service"
    SET_POLKIT = "set-polkit"
    INSTALL_PACKAGE = "install-package"
    UNINSTALL = "uninstall"


class Options:
    command: str
    config_dir: str
    preset: str
    device: str
    list_devices: bool
    key_names: str
    debug: bool
    version: str
    polkit: Optional[str]
    package_path: Optional[str]
    remove_config: bool


class InputRemapperControlBin:
    def __init__(
        self,
        global_config: GlobalConfig,
        migrations: Migrations,
    ):
        self.global_config = global_config
        self.migrations = migrations

    @staticmethod
    def main(options: Options) -> None:
        global_config = GlobalConfig()
        global_uinputs = GlobalUInputs(FrontendUInput)
        migrations = Migrations(global_uinputs)
        input_remapper_control = InputRemapperControlBin(
            global_config,
            migrations,
        )

        if options.debug:
            logger.update_verbosity(True)

        if options.version:
            logger.log_info()
            return

        logger.debug('Call for "%s"', sys.argv)

        boot_finished_ = input_remapper_control.boot_finished()
        is_root = UserUtils.user == "root"
        is_autoload = options.command == Commands.AUTOLOAD
        config_dir_set = options.config_dir is not None
        if is_autoload and not boot_finished_ and is_root and not config_dir_set:
            # this is probably happening during boot time and got
            # triggered by udev. There is no need to try to inject anything if the
            # service doesn't know where to look for a config file. This avoids a lot
            # of confusing service logs. And also avoids potential for problems when
            # input-remapper-control stresses about evdev, dbus and multiprocessing already
            # while the system hasn't even booted completely.
            logger.warning("Skipping autoload command without a logged in user")
            return

        if options.command is not None:
            if options.command in [command.value for command in Internals]:
                input_remapper_control.internals(
                    options.command,
                    options.debug,
                    options.polkit,
                    options.package_path,
                    options.remove_config,
                )
            elif options.command in [command.value for command in Commands]:
                from inputremapper.daemon import Daemon

                daemon = Daemon.connect(fallback=False)

                input_remapper_control.set_daemon(daemon)

                input_remapper_control.communicate(
                    options.command,
                    options.device,
                    options.config_dir,
                    options.preset,
                )
            else:
                logger.error('Unknown command "%s"', options.command)
        else:
            if options.list_devices:
                input_remapper_control.list_devices()

            if options.key_names:
                input_remapper_control.list_key_names()

        if options.command:
            logger.info("Done")

    def list_devices(self):
        logger.setLevel(logging.ERROR)
        from inputremapper.groups import groups

        for group in groups:
            print(group.key)

    def list_key_names(self):
        from inputremapper.configs.keyboard_layout import keyboard_layout

        print("\n".join(keyboard_layout.list_names()))

    def communicate(
        self,
        command: str,
        device: str,
        config_dir: Optional[str],
        preset: str,
    ) -> None:
        """Commands that require a running daemon."""
        if self.daemon is None:
            # probably broken tests
            logger.error("Daemon missing")
            sys.exit(5)

        if config_dir is not None:
            self._load_config(config_dir)

        self.ensure_migrated()

        if command == Commands.AUTOLOAD.value:
            self._autoload(device)

        if command == Commands.START.value:
            self._start(device, preset)

        if command == Commands.STOP.value:
            self._stop(device)

        if command == Commands.STOP_ALL.value:
            self.daemon.stop_all()

        if command == Commands.HELLO.value:
            self._hello()

        if command == Commands.QUIT.value:
            self._quit()

    def _hello(self):
        response = self.daemon.hello("hello")
        logger.info('Daemon answered with "%s"', response)

    def _load_config(self, config_dir: str) -> None:
        path = os.path.abspath(
            os.path.expanduser(os.path.join(config_dir, "config.json"))
        )
        if not os.path.exists(path):
            logger.error('"%s" does not exist', path)
            sys.exit(6)

        logger.info('Using config from "%s" instead', path)
        self.global_config.load_config(path)

    def ensure_migrated(self) -> None:
        # import stuff late to make sure the correct log level is applied
        # before anything is logged
        # TODO since imports shouldn't run any code, this is fixed by moving towards DI
        from inputremapper.user import UserUtils

        if UserUtils.user != "root":
            # Might be triggered by udev, so skip the root user.
            # This will also refresh the config of the daemon if the user changed
            # it in the meantime.
            # config_dir is either the cli arg or the default path in home
            config_dir = os.path.dirname(self.global_config.path)
            self.daemon.set_config_dir(config_dir)
            self.migrations.migrate()

    def _stop(self, device: str) -> None:
        group = self._require_group(device)
        self.daemon.stop_injecting(group.key)

    def _quit(self) -> None:
        try:
            self.daemon.quit()
        except GLib.GError as error:
            if "NoReply" in str(error):
                # The daemon is expected to terminate, so there won't be a reply.
                return

            raise

    def _start(self, device: str, preset: str) -> None:
        group = self._require_group(device)

        logger.info(
            'Starting injection: "%s", "%s"',
            device,
            preset,
        )

        self.daemon.start_injecting(group.key, preset)

    def _require_group(self, device: str):
        # import stuff late to make sure the correct log level is applied
        # before anything is logged
        # TODO since imports shouldn't run any code, this is fixed by moving towards DI
        from inputremapper.groups import groups

        if device is None:
            logger.error("--device missing")
            sys.exit(3)

        if device.startswith("/dev"):
            group = groups.find(path=device)
        else:
            group = groups.find(key=device)

        if group is None:
            logger.error(
                'Device "%s" is unknown or not an appropriate input device',
                device,
            )
            sys.exit(4)

        return group

    def _autoload(self, device: str) -> None:
        # if device was specified, autoload for that one. if None autoload
        # for all devices.
        if device is None:
            logger.info("Autoloading all")
            self.daemon.autoload(timeout=10000)
        else:
            group = self._require_group(device)
            logger.info("Asking daemon to autoload for %s", device)
            self.daemon.autoload_single(group.key, timeout=2000)

    def internals(
        self,
        command: str,
        debug: bool,
        polkit: Optional[str] = None,
        package_path: Optional[str] = None,
        remove_config: bool = False,
    ) -> None:
        """Methods that are needed to get the gui to work and that require root.

        input-remapper-control should be started with sudo or pkexec for this.
        """
        debug = " -d" if debug else ""

        if command == Internals.START_READER_SERVICE.value:
            cmd = f"input-remapper-reader-service{debug}"
        elif command == Internals.START_DAEMON.value:
            cmd = f"input-remapper-service --hide-info{debug}"
        elif command == Internals.SET_POLKIT.value:
            if polkit not in ("enable", "disable"):
                logger.error("--polkit must be 'enable' or 'disable'")
                sys.exit(2)
            self._set_polkit_rule(enable=(polkit == "enable"))
            return
        elif command == Internals.INSTALL_PACKAGE.value:
            self._install_package(package_path)
            return
        elif command == Internals.UNINSTALL.value:
            self._uninstall(remove_config=remove_config)
            return
        else:
            return

        # daemonize
        cmd = f"{cmd} &"
        logger.debug(f"Running `{cmd}`")
        os.system(cmd)

    def _run_optional_command(self, *cmd: str) -> int:
        logger.debug("Running `%s`", " ".join(cmd))
        try:
            return subprocess.call(
                list(cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.debug("Command not found: %s", cmd[0])
            return 127

    def _remove_path(self, path: str) -> None:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            logger.info("Removed %s", path)
        except FileNotFoundError:
            logger.debug("Path already absent: %s", path)
        except OSError as exc:
            logger.warning("Failed to remove %s: %s", path, exc)

    def _uninstall(self, remove_config: bool) -> None:
        logger.info("Uninstall requested remove_config=%s", remove_config)

        # stop/disable potential service units first
        for unit in ("input-remapper.service", "inputremapper-daemon.service"):
            self._run_optional_command("systemctl", "disable", "--now", unit)

        # remove only the current user's rule
        self._remove_path(self._polkit_rule_path(UserUtils.user))

        # remove desktop autostart entries
        user_autostart = os.path.join(
            UserUtils.home,
            ".config",
            "autostart",
            "input-remapper-gtk-autostart.desktop",
        )
        self._remove_path(user_autostart)
        self._remove_path("/etc/xdg/autostart/input-remapper-gtk-autostart.desktop")

        package_candidates = [
            "input-remapper",
            "input-remapper-daemon",
            "inputremapper-daemon",
        ]
        installed_packages = []
        for package in package_candidates:
            if (
                subprocess.call(
                    ["dpkg-query", "-W", "-f=${db:Status-Status}", package],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                == 0
            ):
                installed_packages.append(package)

        if installed_packages:
            if shutil.which("apt-get"):
                code = self._run_optional_command(
                    "apt-get",
                    "-y",
                    "purge",
                    *installed_packages,
                )
                if code != 0:
                    fallback_code = self._run_optional_command(
                        "dpkg", "--purge", *installed_packages
                    )
                    if fallback_code == 0:
                        logger.info(
                            "apt-get purge failed with code %s, dpkg fallback succeeded",
                            code,
                        )
                    else:
                        logger.warning(
                            "apt-get purge failed with code %s and dpkg fallback failed with code %s",
                            code,
                            fallback_code,
                        )
            else:
                self._run_optional_command("dpkg", "--purge", *installed_packages)
        else:
            logger.info("No installed input-remapper packages found via dpkg")

        if remove_config:
            config_dir = os.path.join(UserUtils.home, ".config", "input-remapper-2")
            self._remove_path(config_dir)
        else:
            logger.info(
                "Keeping presets/config at %s",
                os.path.join(UserUtils.home, ".config", "input-remapper-2"),
            )

    def _install_package(self, package_path: Optional[str]) -> None:
        if not package_path:
            logger.error("--package-path missing")
            sys.exit(7)

        path = os.path.abspath(os.path.expanduser(package_path))
        if not os.path.isfile(path):
            logger.error('Package "%s" does not exist', path)
            sys.exit(7)

        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"

        commands = []
        if shutil.which("apt-get"):
            commands.append(
                [
                    "apt-get",
                    "-y",
                    "--allow-downgrades",
                    "install",
                    path,
                ]
            )
        if shutil.which("apt"):
            commands.append(
                [
                    "apt",
                    "-y",
                    "--allow-downgrades",
                    "install",
                    path,
                ]
            )

        for command in commands:
            logger.info("Installing package via `%s`", " ".join(command))
            if subprocess.call(command, env=env) == 0:
                try:
                    os.remove(path)
                except OSError:
                    pass
                return

        logger.error('Failed to install package "%s"', path)
        sys.exit(10)

    def _polkit_rule_path(self, user: str) -> str:
        filename = f"90-input-remapper-{user}.rules"
        return os.path.join("/etc", "polkit-1", "rules.d", filename)

    def _set_polkit_rule(self, enable: bool) -> None:
        user = UserUtils.user
        path = self._polkit_rule_path(user)
        rules_dir = os.path.dirname(path)

        if enable:
            os.makedirs(rules_dir, exist_ok=True)
            rule = (
                "polkit.addRule(function(action, subject) {\n"
                f"  if (action.id == \"inputremapper\" && subject.user == \"{user}\""
                " && subject.active) {\n"
                "    return polkit.Result.YES;\n"
                "  }\n"
                "});\n"
            )
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(rule)
            logger.info("Installed polkit rule at %s", path)
        else:
            try:
                os.remove(path)
                logger.info("Removed polkit rule at %s", path)
            except FileNotFoundError:
                logger.info("Polkit rule already absent at %s", path)

    def _ensure_polkit_rule_for_user(self) -> None:
        """Install per-user polkit rule once so regular launches stay passwordless."""
        user = UserUtils.user
        if user == "root":
            logger.debug("Skipping automatic polkit rule install for root user")
            return

        path = self._polkit_rule_path(user)
        if os.path.isfile(path):
            logger.debug("Polkit rule already present at %s", path)
            return

        logger.info("Installing one-time polkit rule for user %s", user)
        self._set_polkit_rule(enable=True)

    def _num_logged_in_users(self) -> int:
        """Check how many users are logged in."""
        who = subprocess.run(["who"], stdout=subprocess.PIPE).stdout.decode()
        return len([user for user in who.split("\n") if user.strip() != ""])

    def _is_systemd_finished(self) -> bool:
        """Check if systemd finished booting."""
        try:
            systemd_analyze = subprocess.run(
                ["systemd-analyze"], stdout=subprocess.PIPE
            )
        except FileNotFoundError:
            # probably not systemd, lets assume true to not block input-remapper for good
            # on certain installations
            return True

        if "finished" in systemd_analyze.stdout.decode():
            # it writes into stderr otherwise or something
            return True

        return False

    def boot_finished(self) -> bool:
        """Check if booting is completed."""
        # Get as much information as needed to really safely determine if booting up is
        # complete.
        # - `who` returns an empty list on some system for security purposes
        # - something might be broken and might make systemd_analyze fail:
        #       Bootup is not yet finished
        #       (org.freedesktop.systemd1.Manager.FinishTimestampMonotonic=0).
        #       Please try again later.
        #       Hint: Use 'systemctl list-jobs' to see active jobs
        if self._is_systemd_finished():
            logger.debug("System is booted")
            return True

        if self._num_logged_in_users() > 0:
            logger.debug("User(s) logged in")
            return True

        return False

    def set_daemon(self, daemon):
        # TODO DI?
        self.daemon = daemon

    @staticmethod
    def parse_args() -> Options:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--command",
            action="store",
            dest="command",
            help=(
                "Communicate with the daemon. Available commands are "
                f"{', '.join([command.value for command in Commands])}"
            ),
            default=None,
            metavar="NAME",
        )
        parser.add_argument(
            "--config-dir",
            action="store",
            dest="config_dir",
            help=(
                "path to the config directory containing config.json, "
                "xmodmap.json and the presets folder. "
                "defaults to ~/.config/input-remapper/"
            ),
            default=None,
            metavar="PATH",
        )
        parser.add_argument(
            "--preset",
            action="store",
            dest="preset",
            help="The filename of the preset without the .json extension.",
            default=None,
            metavar="NAME",
        )
        parser.add_argument(
            "--device",
            action="store",
            dest="device",
            help="One of the device keys from --list-devices",
            default=None,
            metavar="NAME",
        )
        parser.add_argument(
            "--list-devices",
            action="store_true",
            dest="list_devices",
            help="List available device keys and exit",
            default=False,
        )
        parser.add_argument(
            "--symbol-names",
            action="store_true",
            dest="key_names",
            help="Print all available names for the preset",
            default=False,
        )
        parser.add_argument(
            "-d",
            "--debug",
            action="store_true",
            dest="debug",
            help="Displays additional debug information",
            default=False,
        )
        parser.add_argument(
            "-v",
            "--version",
            action="store_true",
            dest="version",
            help="Print the version and exit",
            default=False,
        )
        parser.add_argument(
            "--polkit",
            action="store",
            dest="polkit",
            help="Enable or disable the polkit rule for password-less access",
            choices=["enable", "disable"],
            default=None,
            metavar="STATE",
        )
        parser.add_argument(
            "--package-path",
            action="store",
            dest="package_path",
            help="Used with --command install-package: path to the .deb package",
            default=None,
            metavar="PATH",
        )
        parser.add_argument(
            "--remove-config",
            action="store_true",
            dest="remove_config",
            help="Used with --command uninstall: also remove presets/config files",
            default=False,
        )

        return parser.parse_args(sys.argv[1:])  # type: ignore
