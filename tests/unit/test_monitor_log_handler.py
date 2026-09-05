#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The monitor log is written by root into the user's home: no symlink following."""

import errno
import logging
import os
import shutil
import tempfile
import unittest

from inputremapper.logging.logger import _NoFollowRotatingFileHandler


class TestMonitorLogHandler(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def _handler(self, path):
        return _NoFollowRotatingFileHandler(
            path, maxBytes=1024, backupCount=1, encoding="utf-8"
        )

    def test_refuses_a_symlinked_log_path(self):
        victim = os.path.join(self.directory, "victim")
        with open(victim, "w", encoding="utf-8") as handle:
            handle.write("untouched")

        link = os.path.join(self.directory, "pilot-monitor.log")
        os.symlink(victim, link)

        with self.assertRaises(OSError) as context:
            self._handler(link)
        self.assertEqual(context.exception.errno, errno.ELOOP)

        with open(victim, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "untouched")

    def test_writes_a_regular_file_with_restrictive_mode(self):
        path = os.path.join(self.directory, "pilot-monitor.log")
        handler = self._handler(path)
        handler.emit(
            logging.LogRecord("test", logging.INFO, "file.py", 1, "hello", None, None)
        )
        handler.close()

        with open(path, encoding="utf-8") as handle:
            self.assertIn("hello", handle.read())
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
