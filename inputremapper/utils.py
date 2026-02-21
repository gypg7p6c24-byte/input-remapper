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
from typing import Optional, NewType, Iterable, List, Tuple, Dict, Any

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


def _steam_userdata_dirs() -> List[str]:
    users: List[str] = []
    for root in _steam_roots():
        userdata = os.path.join(root, "userdata")
        if not os.path.isdir(userdata):
            continue
        try:
            entries = os.listdir(userdata)
        except OSError:
            continue
        for entry in entries:
            path = os.path.join(userdata, entry)
            if os.path.isdir(path):
                users.append(path)
    return users


def _steam_shortcuts_files() -> List[str]:
    files: List[str] = []
    for user_dir in _steam_userdata_dirs():
        path = os.path.join(user_dir, "config", "shortcuts.vdf")
        if os.path.isfile(path):
            files.append(path)
    return files


def _read_cstring(data: bytes, index: int) -> Tuple[str, int]:
    try:
        end = data.index(0, index)
    except ValueError:
        return "", len(data)
    return data[index:end].decode("utf-8", "replace"), end + 1


def _read_wstring(data: bytes, index: int) -> Tuple[str, int]:
    chunks = []
    while index + 1 < len(data):
        if data[index] == 0 and data[index + 1] == 0:
            index += 2
            break
        chunks.append(data[index : index + 2])
        index += 2
    return b"".join(chunks).decode("utf-16le", "replace"), index


def _parse_binary_vdf(data: bytes) -> Dict[str, Any]:
    type_end = 0x08
    type_object = 0x00
    type_string = 0x01
    type_int32 = 0x02
    type_float = 0x03
    type_ptr = 0x04
    type_wstring = 0x05
    type_color = 0x06
    type_uint64 = 0x07

    def parse_obj(idx: int) -> Tuple[Dict[str, Any], int]:
        obj: Dict[str, Any] = {}
        while idx < len(data):
            token = data[idx]
            idx += 1
            if token == type_end:
                break
            key, idx = _read_cstring(data, idx)
            if token == type_object:
                value, idx = parse_obj(idx)
            elif token == type_string:
                value, idx = _read_cstring(data, idx)
            elif token == type_int32:
                if idx + 4 > len(data):
                    return obj, len(data)
                value = int.from_bytes(data[idx : idx + 4], "little", signed=True)
                idx += 4
            elif token == type_float:
                if idx + 4 > len(data):
                    return obj, len(data)
                value = struct.unpack("<f", data[idx : idx + 4])[0]
                idx += 4
            elif token == type_ptr:
                if idx + 4 > len(data):
                    return obj, len(data)
                value = int.from_bytes(data[idx : idx + 4], "little", signed=False)
                idx += 4
            elif token == type_wstring:
                value, idx = _read_wstring(data, idx)
            elif token == type_color:
                if idx + 4 > len(data):
                    return obj, len(data)
                value = tuple(data[idx : idx + 4])
                idx += 4
            elif token == type_uint64:
                if idx + 8 > len(data):
                    return obj, len(data)
                value = int.from_bytes(data[idx : idx + 8], "little", signed=False)
                idx += 8
            else:
                return obj, len(data)
            obj[key] = value
        return obj, idx

    root, _ = parse_obj(0)
    return root


def _get_shortcut_field(entry: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        if key in entry:
            return entry.get(key)
    lowered = {key.lower(): key for key in entry.keys()}
    for key in keys:
        original = lowered.get(key.lower())
        if original:
            return entry.get(original)
    return None


def _first_command_token(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if text[0] in ('"', "'"):
        quote = text[0]
        end = text.find(quote, 1)
        if end > 1:
            return text[1:end]
    return text.split()[0]


def _normalize_shortcut_path(value: str) -> str:
    if not value:
        return ""
    token = _first_command_token(value)
    token = token.strip().strip('"').strip("'")
    token = os.path.expanduser(os.path.expandvars(token))
    return token


def _normalize_shortcut_appid(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return str(numeric & 0xFFFFFFFF)


def get_steam_shortcuts() -> List[Tuple[str, str, str, str, str]]:
    """Return a list of (appid, name, exe, startdir, launch_options) from shortcuts.vdf."""
    shortcuts: List[Tuple[str, str, str, str, str]] = []
    seen_appids: set[str] = set()

    for path in _steam_shortcuts_files():
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        parsed = _parse_binary_vdf(data)
        entries = parsed.get("shortcuts")
        if not isinstance(entries, dict):
            continue
        for _key, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            appid = _normalize_shortcut_appid(_get_shortcut_field(entry, "appid"))
            name = _get_shortcut_field(entry, "appname", "AppName")
            exe = _get_shortcut_field(entry, "exe", "Exe")
            startdir = _get_shortcut_field(entry, "StartDir", "startdir", "startDir")
            launch_options = _get_shortcut_field(
                entry, "LaunchOptions", "launchoptions", "launchOptions"
            )
            if not appid or not name:
                continue
            if appid in seen_appids:
                continue
            seen_appids.add(appid)
            shortcuts.append(
                (
                    appid,
                    str(name),
                    _normalize_shortcut_path(str(exe or "")),
                    _normalize_shortcut_path(str(startdir or "")),
                    str(launch_options or ""),
                )
            )
    return shortcuts


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


def _parse_appmanifest_details(path: str) -> Optional[Tuple[str, str, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            contents = file.read()
    except OSError:
        return None

    name_match = re.search(r'"name"\s*"([^"]+)"', contents)
    appid_match = re.search(r'"appid"\s*"(\d+)"', contents)
    dir_match = re.search(r'"installdir"\s*"([^"]+)"', contents)
    if not name_match or not dir_match:
        return None

    name = _unescape_vdf(name_match.group(1))
    appid = appid_match.group(1) if appid_match else ""
    installdir = _unescape_vdf(dir_match.group(1))
    return appid, name, installdir


def _is_steam_runtime(
    name: str, installdir: Optional[str] = None, appid: Optional[str] = None
) -> bool:
    """Return True for Steam runtimes/tools that shouldn't appear in the game list."""
    known_runtime_appids = {
        "1070560",  # Steam Linux Runtime 1.0 (scout)
        "1391110",  # Steam Linux Runtime 2.0 (soldier)
        "1628350",  # Steam Linux Runtime 3.0 (sniper)
        "228980",  # Steamworks Common Redistributables
        "1161040",  # Proton BattlEye Runtime
        "1493710",  # Proton Experimental
        "2180100",  # Proton Hotfix
        "3658110",  # Proton 10.0
    }
    if appid and appid in known_runtime_appids:
        return True
    haystack = f"{name} {installdir or ''}".lower()
    if "proton" in haystack:
        return True
    if "steam linux runtime" in haystack:
        return True
    if "steamworks common redistributables" in haystack:
        return True
    if "steamworks shared" in haystack:
        return True
    return False


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
            if appid and not _is_steam_runtime(name, appid=appid):
                games[appid] = name

    for appid, name, *_ in get_steam_shortcuts():
        if appid and name and appid not in games:
            games[appid] = name

    return sorted(games.items(), key=lambda item: item[1].lower())


def get_steam_installed_game_paths() -> List[Tuple[str, str, str]]:
    """Return a list of (appid, name, install_path) for locally installed Steam games."""
    games: dict[str, Tuple[str, str]] = {}

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
            parsed = _parse_appmanifest_details(manifest_path)
            if parsed is None:
                continue

            appid, name, installdir = parsed
            appid = appid or appid_from_name
            if not appid or not installdir:
                continue
            if _is_steam_runtime(name, installdir, appid=appid):
                continue

            install_path = os.path.join(library, "common", installdir)
            games[appid] = (name, install_path)

    result: List[Tuple[str, str, str]] = []
    for appid, (name, install_path) in games.items():
        result.append((appid, name, install_path))

    skip_paths = {"/usr/bin", "/usr/bin/flatpak", "/usr/bin/env"}
    for appid, name, exe, startdir, _launch in get_steam_shortcuts():
        base_path = startdir or exe
        if not base_path:
            continue
        if base_path in skip_paths:
            continue
        result.append((appid, name, base_path))

    return sorted(result, key=lambda item: item[1].lower())
