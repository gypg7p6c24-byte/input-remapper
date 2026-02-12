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
import struct
import sys
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


def _read_cstring(data: bytes, offset: int) -> Tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end == -1:
        return "", len(data)
    value = data[offset:end].decode("utf-8", errors="ignore")
    return value, end + 1


def _skip_wstring(data: bytes, offset: int) -> int:
    # UTF-16LE null-terminated
    while offset + 1 < len(data):
        if data[offset : offset + 2] == b"\x00\x00":
            return offset + 2
        offset += 2
    return len(data)


def _read_kv_object_find_common_type(
    data: bytes, offset: int
) -> Tuple[Optional[str], int]:
    while offset < len(data):
        key_type = data[offset]
        offset += 1
        if key_type == 0x08:
            return None, offset

        key, offset = _read_cstring(data, offset)

        if key_type == 0x00:
            if key == "common":
                common_type, offset = _read_kv_object_find_type_in_common(data, offset)
                return common_type, offset
            _, offset = _read_kv_object_find_common_type(data, offset)
            continue

        if key_type == 0x01:
            _, offset = _read_cstring(data, offset)
        elif key_type in (0x02, 0x03, 0x04, 0x06):
            offset += 4
        elif key_type == 0x05:
            offset = _skip_wstring(data, offset)
        elif key_type == 0x07:
            offset += 8
        else:
            return None, len(data)

    return None, offset


def _read_kv_object_find_type_in_common(data: bytes, offset: int) -> Tuple[Optional[str], int]:
    while offset < len(data):
        key_type = data[offset]
        offset += 1
        if key_type == 0x08:
            return None, offset

        key, offset = _read_cstring(data, offset)

        if key_type == 0x00:
            _, offset = _read_kv_object_find_type_in_common(data, offset)
            continue

        if key_type == 0x01:
            value, offset = _read_cstring(data, offset)
            if key == "type":
                return value, offset
        elif key_type in (0x02, 0x03, 0x04, 0x06):
            offset += 4
        elif key_type == 0x05:
            offset = _skip_wstring(data, offset)
        elif key_type == 0x07:
            offset += 8
        else:
            return None, len(data)

    return None, offset


def _find_common_offsets(data: bytes) -> List[int]:
    offsets: List[int] = []
    marker = b"\x00common\x00"
    start = 0
    while True:
        idx = data.find(marker, start)
        if idx == -1:
            break
        offsets.append(idx + len(marker))
        start = idx + 1
    return offsets


def _find_type_by_scan(entry: bytes) -> Optional[str]:
    common_idx = entry.find(b"\x00common\x00")
    if common_idx == -1:
        return None

    # Look ahead for a string type key in the common block.
    scan_start = common_idx + len(b"\x00common\x00")
    scan_end = min(len(entry), scan_start + 8192)
    type_marker = b"\x01type\x00"
    idx = entry.find(type_marker, scan_start, scan_end)
    if idx == -1:
        return None

    value_start = idx + len(type_marker)
    value, _ = _read_cstring(entry, value_start)
    return value or None


def _read_appinfo_types(path: str) -> Dict[str, str]:
    try:
        with open(path, "rb") as file:
            data = file.read()
    except OSError:
        logger.debug('Failed to read appinfo.vdf at "%s"', path)
        return {}

    offset = 0
    if len(data) < 8:
        return {}

    # skip header magic + universe
    offset += 8
    types: Dict[str, str] = {}

    while offset + 8 <= len(data):
        appid = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if appid == 0:
            break

        size = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if size <= 0 or offset + size > len(data):
            break

        entry = data[offset : offset + size]
        offset += size

        # appinfo entry header is 48 bytes before the keyvalues blob
        kv_start = 48
        if len(entry) <= kv_start:
            continue

        app_type, _ = _read_kv_object_find_common_type(entry, kv_start)
        if not app_type:
            for common_offset in _find_common_offsets(entry):
                app_type, _ = _read_kv_object_find_type_in_common(entry, common_offset)
                if app_type:
                    break
        if not app_type:
            app_type = _find_type_by_scan(entry)
        if app_type:
            types[str(appid)] = app_type

    logger.debug(
        "Parsed appinfo.vdf: %d app types found (path=%s)", len(types), path
    )
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
