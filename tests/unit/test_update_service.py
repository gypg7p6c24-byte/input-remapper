#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from inputremapper.update_service import (
    UpdateRelease,
    fetch_release,
    normalize_version,
    release_page_for_channel,
)


class TestUpdateService(unittest.TestCase):
    def test_normalize_version(self):
        self.assertEqual(normalize_version("2.2.1~dev1"), "2.2.1.dev1")
        self.assertEqual(normalize_version("v2.2.0"), "2.2.0")

    def test_release_page_for_channel(self):
        self.assertTrue(release_page_for_channel("stable").endswith("/tag/stable-latest"))
        self.assertTrue(release_page_for_channel("dev").endswith("/tag/dev-latest"))

    def test_update_release_version_comparisons(self):
        release = UpdateRelease(
            channel="dev",
            version="2.2.1.dev1",
            debian_version="2.2.1~dev1",
            release_url="https://example.invalid/release",
            asset_name="input-remapper-2.2.1~dev1.deb",
            asset_url="https://example.invalid/input-remapper-2.2.1~dev1.deb",
        )
        self.assertTrue(release.is_newer_than("2.2.0"))
        self.assertTrue(release.differs_from("2.2.0"))
        self.assertFalse(release.is_older_than("2.2.0"))

    def test_fetch_release_parses_deb_asset(self):
        payload = {
            "name": "2.2.1.dev1",
            "html_url": "https://example.invalid/release",
            "assets": [
                {
                    "name": "input-remapper-2.2.1~dev1.deb",
                    "browser_download_url": "https://example.invalid/input-remapper-2.2.1~dev1.deb",
                }
            ],
        }
        with patch("inputremapper.update_service._http_get_json", return_value=payload):
            release = fetch_release("dev")

        self.assertEqual(release.channel, "dev")
        self.assertEqual(release.version, "2.2.1.dev1")
        self.assertEqual(release.debian_version, "2.2.1~dev1")


if __name__ == "__main__":
    unittest.main()
