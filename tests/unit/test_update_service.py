#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from inputremapper.update_service import (
    FORGE_API_BASE_URL,
    FORGE_TOKEN_ENV,
    UpdateRelease,
    _auth_headers,
    fetch_release,
    forge_token,
    normalize_version,
    release_page_for_channel,
)


class TestUpdateService(unittest.TestCase):
    def test_normalize_version(self):
        self.assertEqual(normalize_version("2.3.1~dev1"), "2.3.1.dev1")
        self.assertEqual(normalize_version("v2.3.1"), "2.3.1")

    def test_release_page_for_channel(self):
        self.assertTrue(release_page_for_channel("stable").endswith("/tag/stable-latest"))
        self.assertTrue(release_page_for_channel("dev").endswith("/tag/dev-latest"))

    def test_update_release_version_comparisons(self):
        release = UpdateRelease(
            channel="dev",
            version="2.3.1.dev1",
            debian_version="2.3.1~dev1",
            release_url="https://example.invalid/release",
            asset_name="input-remapper-2.3.1~dev1.deb",
            asset_url="https://example.invalid/input-remapper-2.3.1~dev1.deb",
        )
        self.assertTrue(release.is_newer_than("2.2.0"))
        self.assertTrue(release.differs_from("2.2.0"))
        self.assertFalse(release.is_older_than("2.2.0"))

    def test_a_rolling_dev_build_is_offered_over_the_previous_one(self):
        """The dev channel stamps <next version>.dev<run> into every build.

        Two builds must not compare equal, or the updater concludes "already on
        it" and never enables the install button — the whole reason the in-app
        updater never worked. And a dev build of the next version must sort
        above the released one it supersedes.
        """
        build = UpdateRelease(
            channel="dev",
            version="1.0.1.dev43",
            debian_version="1.0.1.dev43",
            release_url="https://example.invalid/release",
            asset_name="input-remapper-1.0.1.dev43.flatpak",
            asset_url="https://example.invalid/input-remapper-1.0.1.dev43.flatpak",
        )
        self.assertTrue(build.is_newer_than("1.0.1.dev42"))
        self.assertTrue(build.differs_from("1.0.1.dev42"))
        self.assertTrue(build.is_newer_than("1.0.0"))
        self.assertFalse(build.differs_from("1.0.1.dev43"))

    def test_the_newest_bundle_wins_over_one_left_by_an_earlier_build(self):
        """A rolling release can still carry the previous build's bundle.

        Since every build has its own version, a new bundle no longer replaces
        the previous one by name. Picking the first asset listed would offer an
        older build than the one just published.
        """
        payload = {
            "name": "1.0.1.dev7",
            "html_url": "https://example.invalid/release",
            "assets": [
                {
                    "name": "input-remapper-1.0.0.flatpak",
                    "browser_download_url": "https://example.invalid/old.flatpak",
                },
                {
                    "name": "input-remapper-1.0.1.dev7.flatpak",
                    "browser_download_url": "https://example.invalid/new.flatpak",
                },
            ],
        }
        with patch(
            "inputremapper.update_service._http_get_json", return_value=payload
        ), patch("inputremapper.update_service.is_flatpak", return_value=True):
            release = fetch_release("dev")

        self.assertEqual(release.asset_name, "input-remapper-1.0.1.dev7.flatpak")
        self.assertEqual(release.version, "1.0.1.dev7")
        self.assertTrue(release.is_newer_than("1.0.0"))

    def test_fetch_release_parses_deb_asset(self):
        payload = {
            "name": "2.3.1.dev1",
            "html_url": "https://example.invalid/release",
            "assets": [
                {
                    "name": "input-remapper-2.3.1~dev1.deb",
                    "browser_download_url": "https://example.invalid/input-remapper-2.3.1~dev1.deb",
                }
            ],
        }
        with patch("inputremapper.update_service._http_get_json", return_value=payload):
            release = fetch_release("dev")

        self.assertEqual(release.channel, "dev")
        self.assertEqual(release.version, "2.3.1.dev1")
        self.assertEqual(release.debian_version, "2.3.1~dev1")


class TestForgeTarget(unittest.TestCase):
    def test_the_update_feed_points_at_the_build_chain(self):
        self.assertTrue(
            FORGE_API_BASE_URL.endswith("/repos/gypg7p6c24-byte/input-remapper")
        )

    def test_token_comes_from_the_environment_and_is_sent_as_a_header(self):
        with patch.dict("os.environ", {FORGE_TOKEN_ENV: "  secret  "}):
            self.assertEqual(forge_token(), "secret")
            self.assertEqual(_auth_headers(), {"Authorization": "token secret"})

    def test_no_token_means_no_authorization_header(self):
        # the forge serves its Releases unit anonymously: no header at all
        with patch.dict("os.environ", {FORGE_TOKEN_ENV: ""}):
            self.assertEqual(forge_token(), "")
            self.assertEqual(_auth_headers(), {})


if __name__ == "__main__":
    unittest.main()
