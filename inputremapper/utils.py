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


"""Utility functions."""

import os
import re
import sys
from hashlib import md5
from typing import Optional, NewType, Iterable, List, Tuple, Dict

import evdev

DeviceHash = NewType("DeviceHash", str)


def is_service() -> bool:
    return sys.argv[0].endswith("input-remapper-service")


def get_device_hash(device: evdev.InputDevice) -> DeviceHash:
    """get a unique hash for the given device."""
    # The builtin hash() function can not be used because it is randomly
    # seeded at python startup.
    # A non-cryptographic hash would be faster but there is none in the standard lib
    # This hash needs to stay the same across reboots, and even stay the same when
    # moving the config to a new computer.
    s = str(device.capabilities(absinfo=False)) + device.name
    return DeviceHash(md5(s.encode()).hexdigest().lower())


def get_evdev_constant_name(type_: Optional[int], code: Optional[int], *_) -> str:
    """Handy function to get the evdev constant name for display purposes.

    Returns "unknown" for unknown events.
    """
    # using this function is more readable than
    #   type_, code = event.type_and_code
    #   name = evdev.ecodes.bytype[type_][code]
    name = evdev.ecodes.bytype.get(type_, {}).get(code)

    if type(name) in [list, tuple]:
        # python-evdev >= 1.8.0 uses tuples
        name = name[0]

    if name is None:
        return "unknown"

    return name


def _steam_roots() -> List[str]:
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".steam", "steam"),
        os.path.join(home, ".steam", "root"),
        os.path.join(home, ".local", "share", "Steam"),
        # Snap installs
        os.path.join(home, "snap", "steam", "common", ".steam", "steam"),
        os.path.join(home, "snap", "steam", "common", ".local", "share", "Steam"),
    ]
    return [path for path in candidates if os.path.isdir(path)]


def _unescape_vdf(value: str) -> str:
    return value.replace("\\\\", "\\").replace('\\"', '"')


def _parse_libraryfolders(path: str) -> Iterable[str]:
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            contents = file.read()
    except OSError:
        return []

    paths = set()

    # Newer format: "path" "/home/user/SteamLibrary"
    for match in re.findall(r'"path"\s*"([^"]+)"', contents):
        paths.add(_unescape_vdf(match))

    # Older format: "0" "/home/user/SteamLibrary"
    for match in re.findall(r'"\d+"\s*"([^"]+)"', contents):
        if "/" in match:
            paths.add(_unescape_vdf(match))

    return paths


def _steam_library_dirs() -> List[str]:
    libraries = set()
    for root in _steam_roots():
        libraries.add(os.path.join(root, "steamapps"))
        library_folders = os.path.join(root, "steamapps", "libraryfolders.vdf")
        for lib_path in _parse_libraryfolders(library_folders):
            libraries.add(os.path.join(os.path.expanduser(lib_path), "steamapps"))

    return [path for path in libraries if os.path.isdir(path)]


def _parse_appmanifest(path: str) -> Optional[Tuple[str, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            contents = file.read()
    except OSError:
        return None

    name_match = re.search(r'"name"\s*"([^"]+)"', contents)
    appid_match = re.search(r'"appid"\s*"(\d+)"', contents)
    if not name_match:
        return None

    name = _unescape_vdf(name_match.group(1))
    appid = appid_match.group(1) if appid_match else ""
    return appid, name


def get_steam_installed_games() -> List[Tuple[str, str]]:
    """Return a list of (appid, name) for locally installed Steam games."""
    games: dict[str, str] = {}

    library_dirs = _steam_library_dirs()

    for library in library_dirs:
        try:
            entries = os.listdir(library)
        except OSError:
            continue

        for entry in entries:
            if not entry.startswith("appmanifest_") or not entry.endswith(".acf"):
                continue

            appid_from_name = entry[len("appmanifest_") : -len(".acf")]
            manifest_path = os.path.join(library, entry)
            parsed = _parse_appmanifest(manifest_path)
            if parsed is None:
                continue

            appid, name = parsed
            appid = appid or appid_from_name
            if appid:
                games[appid] = name

    return sorted(games.items(), key=lambda item: item[1].lower())
