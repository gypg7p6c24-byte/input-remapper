# Input Remapper on SteamOS / Steam Deck

This page covers installing and using Input Remapper on **SteamOS** (PC or Steam
Deck) in **Desktop mode (KDE Plasma)**. For Ubuntu, see the main
[README](../README.md).

## Download

**Download `input-remapper-<version>.flatpak`** from the `dev-latest` release
(rolling development build, no account required).

In Desktop mode, double-click the downloaded file to install it via **Discover**,
or from a terminal:

```
flatpak install --user ~/Downloads/input-remapper-*.flatpak
```

Then launch **Input Remapper** from the application menu. Every push to the `dev`
branch republishes this file automatically (the `dev-latest` release), so the
link always serves the newest build. Once installed, the app can update itself
from Settings (the update downloads the new bundle and installs it on the host).

## Why this is different from a normal Linux install

SteamOS uses a **read-only, immutable** system. Anything installed into the
system with `pacman` is **erased on the next OS update**, and the graphical
libraries Input Remapper needs are not part of the base image. So instead of a
native install, SteamOS uses a **Flatpak**, which:

- bundles every dependency (GTK3, GtkSourceView4, PyGObject, tray indicator,
  and the Python libraries),
- installs under `/home`, so it **survives SteamOS updates**,
- installs and uninstalls in **one click** (no terminal), via the bundle or the
  Discover store.

## The one system permission

Remapping needs kernel access to `uinput`. A sandbox can't grant that itself, so
it is done **once**, from inside the app, behind a **single password prompt**:

- a udev rule is written to `/etc/udev/rules.d/` (`/etc` survives OS updates),
- the `uinput` module is loaded at boot,
- your user is added to the `input` group.

Helper script: [`install/flatpak/host/input-remapper-device-access`](../install/flatpak/host/input-remapper-device-access),
run on the host via `flatpak-spawn --host pkexec`. Disabling it later removes the
rule. **Your presets are always kept** unless you explicitly ask to remove them.

## Install

Build/packaging details and the current porting checklist are in
[`install/flatpak/README.md`](../install/flatpak/README.md).

End-user flow: download the bundle → double-click → **Install** in Discover →
first launch asks for your password once to enable device access → done. The
app lives in the tray; closing the window keeps it running, "Quit" from the
tray stops it.

## Per-game presets (Steam and non-Steam)

Input Remapper detects the running game and loads the preset you bound to it,
then reverts when the game closes. This works for:

- **Steam games** — detected from Steam's launch environment (`SteamAppId`,
  Proton compatibility variables, the command line).
- **Non-Steam games** — add the game to Steam with *Games → Add a Non-Steam
  Game to My Library*; it is detected through Steam's `shortcuts.vdf`.

Libraries on the **internal drive and microSD** are both scanned (via Steam's
`libraryfolders.vdf`). Bind a preset to a game in the editor, enable autostart so
the app runs hidden in the tray, and presets switch automatically as you launch
and close games.

## Uninstall (one click)

1. In the app: **Settings → Uninstall** (removes device access; keeps presets
   unless you tick "also remove presets").
2. Remove the Flatpak (Discover, or
   `flatpak uninstall io.github.sezanzeb.input_remapper`).

## Updates

The in-app updater reads the rolling releases `dev-latest` (dev channel) and
`stable-latest` (stable channel) published by the build chain, and on SteamOS
offers the matching **Flatpak** bundle instead of the `.deb`.

No credentials are needed. The feed can be pointed elsewhere without touching
the code, through `INPUT_REMAPPER_FORGE_OWNER`, `INPUT_REMAPPER_FORGE_REPO`,
`INPUT_REMAPPER_FORGE_URL` and `INPUT_REMAPPER_FORGE_API_URL` — a Gitea
instance exposes the same release API shape. `INPUT_REMAPPER_FORGE_TOKEN`
authenticates the request when a forge does not serve its releases anonymously.

## Status

The Flatpak packaging is being finalised and iterated on-device. See the porting
checklist in [`install/flatpak/README.md`](../install/flatpak/README.md).
