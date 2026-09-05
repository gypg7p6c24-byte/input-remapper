#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The polkit rule must only ever hand out passwordless service startup.

The rule is JavaScript evaluated by polkit, so it is checked here by running it
in a real JS engine (node) against a stub `polkit` object. Skipped when node is
not installed.
"""

import json
import shutil
import subprocess
import unittest

from inputremapper.polkit_rule import polkit_rule_body

NODE = shutil.which("node") or shutil.which("nodejs")

HARNESS = """
var polkit = {
  Result: {YES: "YES", NOT_HANDLED: "NOT_HANDLED", AUTH_ADMIN: "AUTH_ADMIN"},
  _rule: null,
  addRule: function (fn) { this._rule = fn; },
};
%(rule)s
var cases = %(cases)s;
var out = cases.map(function (c) {
  return polkit._rule(
    {id: c.id, lookup: function (key) { return key == "command_line" ? c.line : null; }},
    {user: c.user, active: c.active}
  );
});
console.log(JSON.stringify(out));
"""


def _evaluate(cases):
    script = HARNESS % {
        "rule": polkit_rule_body("pierre"),
        "cases": json.dumps(cases),
    }
    result = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def _case(line, user="pierre", active=True, id="inputremapper"):
    return {"line": line, "user": user, "active": active, "id": id}


BIN = "/usr/bin/input-remapper-control"


@unittest.skipUnless(NODE, "node is required to evaluate the polkit rule")
class TestPolkitRule(unittest.TestCase):
    def test_allows_only_the_background_services(self):
        verdicts = _evaluate(
            [
                _case(f"{BIN} --command start-daemon"),
                _case(f"{BIN} --command start-daemon -d"),
                _case(f"{BIN} --command start-reader-service"),
                _case(f"{BIN}  --command  start-reader-service  -d "),
            ]
        )
        self.assertEqual(verdicts, ["YES"] * 4)

    def test_refuses_privileged_management_commands(self):
        # these are the ones that run arbitrary code as root
        verdicts = _evaluate(
            [
                _case(f"{BIN} --command install-package --package-path /tmp/evil.deb"),
                _case(f"{BIN} --command uninstall --remove-config"),
                _case(f"{BIN} --command set-polkit --polkit enable"),
                # argparse keeps the LAST --command, so a smuggled second one
                # must not be waved through by matching the first
                _case(f"{BIN} --command start-daemon --command install-package"),
                # extra arguments alongside an allowed command
                _case(f"{BIN} --command start-daemon --package-path /tmp/evil.deb"),
            ]
        )
        self.assertEqual(verdicts, ["NOT_HANDLED"] * 5)

    def test_refuses_other_subjects_and_programs(self):
        verdicts = _evaluate(
            [
                _case(f"{BIN} --command start-daemon", user="mallory"),
                _case(f"{BIN} --command start-daemon", active=False),
                _case(f"{BIN} --command start-daemon", id="org.freedesktop.other"),
                _case("/tmp/input-remapper-control-evil --command start-daemon"),
                _case(""),
            ]
        )
        self.assertEqual(verdicts, ["NOT_HANDLED"] * 5)


if __name__ == "__main__":
    unittest.main()
