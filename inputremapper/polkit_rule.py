# -*- coding: utf-8 -*-
# input-remapper - GUI for device specific keyboard mappings
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

"""The per-user polkit rule that makes the background services passwordless.

Kept in its own module, free of GTK/evdev imports, so it can be unit tested.

The polkit action covers the whole `input-remapper-control` binary, so a
blanket `Result.YES` would also hand out `install-package` and `uninstall` —
arbitrary root code execution for anything able to run commands as this user.
The rule therefore whitelists the exact argument vectors the GUI uses on every
launch, and lets everything else fall through to the admin prompt declared in
the .policy file.
"""

from __future__ import annotations

import json

# Bumped whenever the rule body changes, so machines carrying an older (more
# permissive) rule get it rewritten instead of kept forever.
POLKIT_RULE_VERSION = "2"

PASSWORDLESS_COMMANDS = ("start-daemon", "start-reader-service")

RULE_MARKER = f"// input-remapper polkit rule v{POLKIT_RULE_VERSION}"


def polkit_rule_body(user: str) -> str:
    """Render the polkit rule granting passwordless service startup to `user`."""
    allowed = " || ".join(f'command == "{name}"' for name in PASSWORDLESS_COMMANDS)
    return f"""{RULE_MARKER}
polkit.addRule(function(action, subject) {{
  if (action.id != "inputremapper") {{
    return polkit.Result.NOT_HANDLED;
  }}
  if (subject.user != {json.dumps(user)} || !subject.active) {{
    return polkit.Result.NOT_HANDLED;
  }}
  var line = action.lookup("command_line");
  if (!line) {{
    return polkit.Result.NOT_HANDLED;
  }}
  var argv = line.split(/\\s+/).filter(function(part) {{
    return part != "";
  }});
  if (argv.length < 1) {{
    return polkit.Result.NOT_HANDLED;
  }}
  var program = argv.shift();
  if (!/(^|\\/)input-remapper-control$/.test(program)) {{
    return polkit.Result.NOT_HANDLED;
  }}
  var command = null;
  for (var i = 0; i < argv.length; i++) {{
    if (argv[i] == "-d" || argv[i] == "--debug") {{
      continue;
    }}
    if (argv[i] == "--command" && i + 1 < argv.length) {{
      if (command !== null) {{
        return polkit.Result.NOT_HANDLED;
      }}
      command = argv[i + 1];
      i++;
      continue;
    }}
    return polkit.Result.NOT_HANDLED;
  }}
  if ({allowed}) {{
    return polkit.Result.YES;
  }}
  return polkit.Result.NOT_HANDLED;
}});
"""
