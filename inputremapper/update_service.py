# -*- coding: utf-8 -*-
# input-remapper - GUI for device specific keyboard mappings
# Copyright (C) 2026 sezanzeb <b8x45ygc9@mozmail.com>
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

"""Forge-backed update lookup and package download helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from inputremapper.user import is_flatpak

# Releases are published by the build chain, which runs on GitHub. Every part
# is overridable so another forge, owner or repository can be pointed at
# without touching the code — a Gitea instance exposes the same release API
# shape under /api/v1/repos/<owner>/<repo>.
FORGE_OWNER = os.environ.get("INPUT_REMAPPER_FORGE_OWNER", "gypg7p6c24-byte")
FORGE_REPO = os.environ.get("INPUT_REMAPPER_FORGE_REPO", "input-remapper")
FORGE_WEB_URL = os.environ.get(
    "INPUT_REMAPPER_FORGE_URL", "https://github.com"
).rstrip("/")
FORGE_API_URL = os.environ.get(
    "INPUT_REMAPPER_FORGE_API_URL", "https://api.github.com"
).rstrip("/")
# Optional, for a forge whose releases are not readable anonymously. Never
# shipped with the app: environment only.
FORGE_TOKEN_ENV = "INPUT_REMAPPER_FORGE_TOKEN"
RELEASES_BASE_URL = f"{FORGE_WEB_URL}/{FORGE_OWNER}/{FORGE_REPO}/releases"
FORGE_API_BASE_URL = f"{FORGE_API_URL}/repos/{FORGE_OWNER}/{FORGE_REPO}"
CHANNEL_RELEASE_TAGS = {
    "stable": "stable-latest",
    "dev": "dev-latest",
}
DEBIAN_VERSION_RE = re.compile(r"^input-remapper-(?P<version>.+)\.deb$")
FLATPAK_VERSION_RE = re.compile(r"^input-remapper-(?P<version>.+)\.(?:flatpak|flatpakref)$")
VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:\.dev(?P<dev>\d+))?$")


class UpdateError(RuntimeError):
    """Raised when update discovery or download fails."""


def normalize_version(value: str) -> str:
    """Convert Debian-ish versions into something packaging.Version accepts."""
    normalized = value.strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    normalized = normalized.replace("~dev", ".dev")
    normalized = normalized.replace("-dev", ".dev")
    return normalized


def parse_version(value: str) -> tuple[int, int, int, int, int] | None:
    """Parse app versions into a lexicographically comparable tuple."""
    match = VERSION_RE.fullmatch(normalize_version(value))
    if match is None:
        return None

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    dev = match.group("dev")
    if dev is None:
        return (major, minor, patch, 1, 0)

    return (major, minor, patch, 0, int(dev))


def release_tag_for_channel(channel: str) -> str:
    """Resolve a channel into its rolling release tag."""
    return CHANNEL_RELEASE_TAGS.get(channel, CHANNEL_RELEASE_TAGS["stable"])


def release_page_for_channel(channel: str) -> str:
    """Return the human-facing release page for a channel."""
    return f"{RELEASES_BASE_URL}/tag/{release_tag_for_channel(channel)}"


@dataclass(frozen=True)
class UpdateRelease:
    channel: str
    version: str
    debian_version: str
    release_url: str
    asset_name: str
    asset_url: str

    def parsed_version(self) -> tuple[int, int, int, int, int] | None:
        return parse_version(self.version)

    def differs_from(self, local_version: str) -> bool:
        remote = self.parsed_version()
        local = parse_version(local_version)
        if remote is None or local is None:
            return normalize_version(self.version) != normalize_version(local_version)
        return remote != local

    def is_newer_than(self, local_version: str) -> bool:
        remote = self.parsed_version()
        local = parse_version(local_version)
        if remote is None or local is None:
            return False
        return remote > local

    def is_older_than(self, local_version: str) -> bool:
        remote = self.parsed_version()
        local = parse_version(local_version)
        if remote is None or local is None:
            return False
        return remote < local


def forge_token() -> str:
    """Optional Gitea token; empty when releases are readable anonymously."""
    return os.environ.get(FORGE_TOKEN_ENV, "").strip()


def _auth_headers() -> dict[str, str]:
    token = forge_token()
    if not token:
        return {}
    return {"Authorization": f"token {token}"}


def _http_get_json(url: str) -> dict[str, Any]:
    req = request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "input-remapper-update-check",
            **_auth_headers(),
        },
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(f"No release published yet for {url}") from exc
        if exc.code in (401, 403) and not forge_token():
            raise UpdateError(
                f"HTTP {exc.code} for {url} — releases are not readable "
                f"anonymously on this forge; set {FORGE_TOKEN_ENV}"
            ) from exc
        raise UpdateError(f"HTTP {exc.code} for {url}") from exc
    except error.URLError as exc:
        raise UpdateError(f"Network error: {exc.reason}") from exc


def _asset_version_from_name(asset_name: str) -> str | None:
    match = DEBIAN_VERSION_RE.match(asset_name) or FLATPAK_VERSION_RE.match(asset_name)
    if not match:
        return None
    return match.group("version")


def _preferred_asset_suffixes() -> tuple[str, ...]:
    """On SteamOS/Flatpak prefer the .flatpak bundle; otherwise the .deb."""
    if is_flatpak():
        return (".flatpak", ".flatpakref", ".deb")
    return (".deb",)


def fetch_release(channel: str) -> UpdateRelease:
    """Fetch rolling release metadata for a channel."""
    tag = release_tag_for_channel(channel)
    payload = _http_get_json(f"{FORGE_API_BASE_URL}/releases/tags/{tag}")
    assets = payload.get("assets", [])

    selected = None
    for suffix in _preferred_asset_suffixes():
        selected = next(
            (
                asset
                for asset in assets
                if isinstance(asset, dict)
                and str(asset.get("name", "")).endswith(suffix)
                and asset.get("browser_download_url")
            ),
            None,
        )
        if selected is not None:
            break
    if selected is None:
        wanted = "/".join(_preferred_asset_suffixes())
        raise UpdateError(f"No {wanted} asset found for channel {channel}")

    asset_name = str(selected["name"])
    debian_version = _asset_version_from_name(asset_name)
    if not debian_version:
        raise UpdateError(f"Cannot parse package version from asset {asset_name}")

    # Prefer the release title as displayed version, but only when it is an
    # actual version ("2.3.1.dev1"); marketing titles fall back to the
    # version parsed from the asset name.
    release_name = str(payload.get("name") or "")
    if parse_version(release_name) is not None:
        display_version = normalize_version(release_name)
    else:
        display_version = normalize_version(debian_version)
    return UpdateRelease(
        channel=channel,
        version=display_version,
        debian_version=debian_version,
        release_url=str(payload.get("html_url") or release_page_for_channel(channel)),
        asset_name=asset_name,
        asset_url=str(selected["browser_download_url"]),
    )


def download_release_asset(release: UpdateRelease, dest_dir: str | None = None) -> str:
    """Download the release asset (.deb or .flatpak) and return the local path."""
    target_dir = dest_dir or tempfile.gettempdir()
    os.makedirs(target_dir, exist_ok=True)
    _, suffix = os.path.splitext(release.asset_name)
    with tempfile.NamedTemporaryFile(
        prefix=f"input-remapper-{release.channel}-",
        suffix=suffix or ".deb",
        dir=target_dir,
        delete=False,
    ) as handle:
        target_path = handle.name

    req = request.Request(
        release.asset_url,
        headers={
            "User-Agent": "input-remapper-update-install",
            **_auth_headers(),
        },
    )
    try:
        with request.urlopen(req, timeout=120) as response, open(
            target_path, "wb"
        ) as output:
            shutil.copyfileobj(response, output)
    except Exception as exc:
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise UpdateError(f"Failed to download update: {exc}") from exc

    return target_path
