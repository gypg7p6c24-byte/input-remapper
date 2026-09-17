#!/usr/bin/env python3
"""Detach every asset from a release, so a rolling tag carries one build only.

Every build publishes its asset under its own version
(input-remapper-1.0.1.dev7.flatpak), so a new bundle no longer replaces the
previous one by name: without this the rolling release accumulates every build
ever made, and the in-app updater has to choose among them.

Runs inside the flatpak-builder container, which has python3 but neither `gh`
nor `jq`. It uses the standard library only, and it fails loudly: a cleanup that
reports success without removing anything is how the release ended up carrying
three bundles in the first place.

Usage: clear-release-assets.py <owner/repo> <tag> [--dry-run]
Token: GITHUB_TOKEN or GH_TOKEN (not needed for --dry-run).
"""

from __future__ import annotations

import json
import os
import sys
from urllib import error, request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")


def call(url: str, method: str, token: str) -> tuple[int, bytes]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "input-remapper-release-cleanup",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as response:
            return response.status, response.read()
    except error.HTTPError as exc:
        return exc.code, exc.read()


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    repo, tag = args
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token and not dry_run:
        raise SystemExit("No GITHUB_TOKEN / GH_TOKEN in the environment")

    status, body = call(f"{API}/repos/{repo}/releases/tags/{tag}", "GET", token)
    if status == 404:
        print(f"{tag} does not exist yet, nothing to detach")
        return 0
    if status != 200:
        raise SystemExit(f"GET {tag} returned HTTP {status}: {body[:300]!r}")

    assets = json.loads(body).get("assets", [])
    if not assets:
        print(f"{tag} carries no asset, nothing to detach")
        return 0

    for asset in assets:
        name, asset_id = asset["name"], asset["id"]
        if dry_run:
            print(f"would detach {name} (id {asset_id})")
            continue
        status, body = call(
            f"{API}/repos/{repo}/releases/assets/{asset_id}", "DELETE", token
        )
        # 404 means someone else removed it in the meantime, which is the
        # outcome we wanted anyway.
        if status not in (204, 404):
            raise SystemExit(f"DELETE {name} returned HTTP {status}: {body[:300]!r}")
        print(f"detached {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
