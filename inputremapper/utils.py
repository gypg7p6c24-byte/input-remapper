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
import io
from hashlib import md5
from typing import Optional, NewType, Iterable, List, Tuple, Dict

import evdev
from inputremapper.logging.logger import logger

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


def _find_appinfo_path() -> Optional[str]:
    for root in _steam_roots():
        candidates = [
            os.path.join(root, "appinfo.vdf"),
            os.path.join(root, "appcache", "appinfo.vdf"),
            os.path.join(root, "steamapps", "appinfo.vdf"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
    return None


def _read_appinfo_types(path: str) -> Dict[str, str]:
    try:
        with open(path, "rb") as file:
            blob = file.read()
    except Exception as exc:
        logger.debug('Failed to read appinfo.vdf "%s": %s', path, exc)
        return {}

    logger.debug("appinfo.vdf path=%s bytes=%d", path, len(blob))

    types: Dict[str, str] = {}

    # 1) Try steamfiles (supports newer appinfo formats)
    try:
        from steamfiles import appinfo as steamfiles_appinfo  # type: ignore

        logger.debug("appinfo parser=steamfiles")
        with open(path, "rb") as file:
            appinfo_data = steamfiles_appinfo.load(file)

        logger.debug("steamfiles entries=%d", len(appinfo_data))

        missing_common = 0
        missing_type = 0
        sample_logged = 0

        for appid, entry in appinfo_data.items():
            # entry likely contains metadata + 'data' blob
            data_block = entry.get("data", entry)
            appinfo_block = data_block.get("appinfo", data_block)
            common = appinfo_block.get("common", {})
            app_type = common.get("type")

            if not common:
                missing_common += 1
            if not app_type:
                missing_type += 1

            if app_type:
                types[str(appid)] = app_type
                if sample_logged < 5:
                    logger.debug(
                        "steamfiles type appid=%s name=%s type=%s",
                        appid,
                        common.get("name"),
                        app_type,
                    )
                    sample_logged += 1

        logger.debug(
            "steamfiles types=%d missing_common=%d missing_type=%d",
            len(types),
            missing_common,
            missing_type,
        )

        if types:
            return types
    except Exception as exc:
        logger.debug("steamfiles parse failed: %s", exc)

    # 2) Try steam (older appcache parser)
    try:
        from steam.utils.appcache import parse_appinfo  # type: ignore

        logger.debug("appinfo parser=steam")
        header, apps = parse_appinfo(io.BytesIO(blob))
        logger.debug("steam header=%s", header)

        missing_common = 0
        missing_type = 0
        sample_logged = 0

        for entry in apps:
            appid = entry.get("appid")
            data_block = entry.get("data", {})
            appinfo_block = data_block.get("appinfo", {})
            common = appinfo_block.get("common", {})
            app_type = common.get("type")

            if not common:
                missing_common += 1
            if not app_type:
                missing_type += 1

            if appid is not None and app_type:
                types[str(appid)] = app_type
                if sample_logged < 5:
                    logger.debug(
                        "steam type appid=%s name=%s type=%s",
                        appid,
                        common.get("name"),
                        app_type,
                    )
                    sample_logged += 1

        logger.debug(
            "steam types=%d missing_common=%d missing_type=%d",
            len(types),
            missing_common,
            missing_type,
        )
    except Exception as exc:
        logger.debug("steam parse failed: %s", exc)

    return types


def get_steam_installed_games() -> List[Tuple[str, str]]:
    """Return a list of (appid, name) for locally installed Steam games."""
    games: dict[str, str] = {}
    appinfo_types: Dict[str, str] = {}
    appinfo_path = _find_appinfo_path()
    if appinfo_path:
        appinfo_types = _read_appinfo_types(appinfo_path)
    else:
        logger.debug("No appinfo.vdf found in known Steam roots")

    library_dirs = _steam_library_dirs()
    logger.debug("Steam library dirs: %s", library_dirs)
    total_manifests = 0
    filtered_by_type = 0

    for library in library_dirs:
        try:
            entries = os.listdir(library)
        except OSError:
            continue

        for entry in entries:
            if not entry.startswith("appmanifest_") or not entry.endswith(".acf"):
                continue
            total_manifests += 1

            appid_from_name = entry[len("appmanifest_") : -len(".acf")]
            manifest_path = os.path.join(library, entry)
            parsed = _parse_appmanifest(manifest_path)
            if parsed is None:
                continue

            appid, name = parsed
            appid = appid or appid_from_name
            if appid:
                if appinfo_types:
                    app_type = appinfo_types.get(appid)
                    logger.debug(
                        "manifest appid=%s name=%s appinfo_type=%s",
                        appid,
                        name,
                        app_type,
                    )
                    if app_type != "game":
                        filtered_by_type += 1
                        continue
                games[appid] = name

    logger.debug(
        "Steam games: manifests=%d, filtered_non_game=%d, games=%d",
        total_manifests,
        filtered_by_type,
        len(games),
    )
    return sorted(games.items(), key=lambda item: item[1].lower())
