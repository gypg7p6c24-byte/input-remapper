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

"""Propose the bindings a user keeps repeating when a new preset is created.

Presets are read as raw JSON rather than through `Preset`, so counting stays
free of the GUI model and of any validation that would reject a mapping written
by an older version.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Tuple

from inputremapper.configs.paths import PathUtils
from inputremapper.logging.logger import logger

# A binding seen in a single preset is a one-off, not a habit.
DEFAULT_MINIMUM_PRESETS = 2

# More than a screenful of pre-filled rows would be a nuisance to clean up.
DEFAULT_LIMIT = 10


def _signature(mapping: dict) -> str:
    """A stable identity for "the same binding", ignoring cosmetic fields."""
    return json.dumps(
        {key: mapping[key] for key in sorted(mapping) if key not in ("name",)},
        sort_keys=True,
        default=str,
    )


def _read_preset(path: str) -> List[dict]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            content = json.load(file)
    except (OSError, ValueError) as error:
        logger.debug('Ignoring unreadable preset "%s": %s', path, error)
        return []
    if not isinstance(content, list):
        return []
    return [entry for entry in content if isinstance(entry, dict)]


def count_bindings(paths: List[str]) -> Dict[str, Tuple[int, dict]]:
    """How many distinct presets contain each binding."""
    counts: Dict[str, Tuple[int, dict]] = {}
    for path in paths:
        seen_here = set()
        for mapping in _read_preset(path):
            if not mapping.get("input_combination"):
                continue
            signature = _signature(mapping)
            if signature in seen_here:
                continue
            seen_here.add(signature)
            occurrences, example = counts.get(signature, (0, mapping))
            counts[signature] = (occurrences + 1, example)
    return counts


def suggest_bindings(
    paths: List[str],
    minimum_presets: int = DEFAULT_MINIMUM_PRESETS,
    limit: int = DEFAULT_LIMIT,
) -> List[dict]:
    """The most recurrent bindings of `paths`, most frequent first.

    Bindings that would collide on the same input are dropped: a preset cannot
    hold two mappings for one input combination.
    """
    counts = count_bindings(paths)
    ranked = sorted(
        (entry for entry in counts.values() if entry[0] >= minimum_presets),
        key=lambda entry: (-entry[0], _signature(entry[1])),
    )

    suggestions: List[dict] = []
    used_inputs = set()
    for _occurrences, mapping in ranked:
        combination = json.dumps(mapping["input_combination"], sort_keys=True)
        if combination in used_inputs:
            continue
        used_inputs.add(combination)
        suggestions.append(mapping)
        if len(suggestions) >= limit:
            break
    return suggestions


def existing_preset_paths() -> List[str]:
    """Every preset of every device known to this user."""
    pattern = os.path.join(glob.escape(PathUtils.get_preset_path()), "*", "*.json")
    return sorted(glob.glob(pattern))
