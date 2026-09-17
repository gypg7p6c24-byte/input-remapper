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

## System permissions

Remapping needs kernel access to `uinput`. On SteamOS that access is already
granted by Valve's `uaccess` rule, so **the app asks for nothing at install or at
first launch**, and remapping works out of the box.

Two host-side actions do ask for a password, and only when you trigger them:

| What you do | What is written on the host |
|---|---|
| Settings → run in background / autostart | a polkit rule, `/etc/polkit-1/rules.d/90-input-remapper-<user>.rules` |
| Settings → Uninstall | removes that rule, and the udev rule if present |

On a distribution without Valve's rule, device access is granted by
[`install/flatpak/host/input-remapper-device-access`](../install/flatpak/host/input-remapper-device-access)
(`enable`), run on the host via `flatpak-spawn --host pkexec`: it writes a udev
rule to `/etc/udev/rules.d/`, loads `uinput` at boot and adds the user to the
`input` group. **Your presets are always kept** unless you explicitly ask to
remove them.

Both rules live in `/etc`, outside the Flatpak. Removing the app **from Discover**
therefore leaves them behind — use Settings → Uninstall first, see below.

## Install and reinstall

Build/packaging details and the current porting checklist are in
[`install/flatpak/README.md`](../install/flatpak/README.md).

End-user flow: download the bundle → double-click → **Install** in Discover →
launch it. The app lives in the tray; closing the window keeps it running,
"Quit" from the tray stops it.

**Recommended procedure, and why it is in this order.** Discover installs
**system-wide**, the in-app updater follows the scope of the running instance, and
the two host rules above are not owned by the package. So:

1. **Uninstall the old copy from inside the app first** — Settings → Uninstall.
   It drops the host rules, which Discover would leave behind, then removes the
   Flatpak. Keep "also remove presets" unticked to keep your presets.
2. **Check nothing is left**, and in particular that there is only ever one copy:

   ```
   flatpak list --app --columns=application,version,installation
   ```

   Exactly one `input-remapper` line is expected. Two lines (`system` and `user`)
   mean two copies are installed; remove the one you do not want with
   `flatpak uninstall --system` or `--user`.
3. **Install the new bundle** by double-clicking it in Discover. Two password
   prompts in a row are normal when the GNOME 47 runtime is not on the machine
   yet: Flatpak authorises the runtime install and the app install separately.
4. **Afterwards, update from the app** (Settings → Check for Updates). It
   installs into the same scope as the running copy, so it does not create a
   second one.

Discover's **"Delete settings and user data"** only clears the sandbox's own data
under `~/.var/app/`. Presets live on the host in `~/.config/input-remapper-2`
and are **not** touched by it.

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

1. In the app: **Settings → Uninstall** (removes the host rules; keeps presets
   unless you tick "also remove presets"). It then removes the Flatpak itself,
   from the same scope the running copy is installed in.
2. Only if step 1 is unavailable, remove the Flatpak from Discover or with
   `flatpak uninstall io.github.sezanzeb.input_remapper` — this leaves the host
   rules in `/etc` behind.

## Updates

The in-app updater reads the rolling releases `dev-latest` (dev channel) and
`stable-latest` (stable channel) published by the build chain, and on SteamOS
offers the matching **Flatpak** bundle instead of the `.deb`.

It decides by **comparing version strings**, so every dev build carries its own
number: `<next version>.dev<build>`, for example `1.0.1.dev44` while `1.0.0` is
the stable. A channel that republished the same number could never offer
anything — the app would report "already on the selected channel version" and
leave the install button disabled.

No credentials are needed. The feed can be pointed elsewhere without touching
the code, through `INPUT_REMAPPER_FORGE_OWNER`, `INPUT_REMAPPER_FORGE_REPO`,
`INPUT_REMAPPER_FORGE_URL` and `INPUT_REMAPPER_FORGE_API_URL` — a Gitea
instance exposes the same release API shape. `INPUT_REMAPPER_FORGE_TOKEN`
authenticates the request when a forge does not serve its releases anonymously.

## Status

The Flatpak packaging is being finalised and iterated on-device. See the porting
checklist in [`install/flatpak/README.md`](../install/flatpak/README.md).
