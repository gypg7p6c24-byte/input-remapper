import os
import re

STEAM_PATH = os.path.expanduser("~/.local/share/Steam/steamapps")

def get_installed_games():
    games = []

    if not os.path.isdir(STEAM_PATH):
        return games

    for f in os.listdir(STEAM_PATH):
        if f.startswith("appmanifest_") and f.endswith(".acf"):
            with open(os.path.join(STEAM_PATH, f)) as fp:
                text = fp.read()

            name = re.search(r'"name"\s+"([^"]+)"', text)
            appid = re.search(r'"appid"\s+"([^"]+)"', text)

            if name and appid:
                games.append({
                    "name": name.group(1),
                    "appid": appid.group(1)
                })

    return sorted(games, key=lambda x: x["name"])
