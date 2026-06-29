# Input Remapper on SteamOS / Steam Deck (Flatpak)

Target: **SteamOS in Desktop mode (KDE Plasma)** on a PC or Steam Deck.

Goal: stay as close as possible to a **one-click, no-terminal** install that
survives SteamOS updates. Flatpak is used because it bundles every graphical
library the window needs and installs under `/home` (untouched by OS updates).

## Why Flatpak (and not a native install)

SteamOS has a read-only, immutable system. Anything installed into the system
(`/usr`) with `pacman` is wiped on the next OS update, and the graphical
libraries Input Remapper needs (GTK3, GtkSourceView4, PyGObject, an AppIndicator
for the tray) are not part of the base image and cannot be added reliably.
Flatpak side-steps all of this.

## The one irreducible system permission

Remapping needs kernel-level access to `uinput` (to inject events) and to read
all input devices. A sandbox cannot grant itself that. It is handled **once**,
from inside the app, behind a **single password prompt** (no terminal):

- a udev rule is written to `/etc/udev/rules.d/99-input-remapper.rules`
  (`/etc` persists across SteamOS updates), and
- the current user is added to the `input` group.

Uninstalling from the app reverses this (also one password prompt). Presets are
kept by default.

## Install (testing, until published to a repo)

In Desktop mode:

```
flatpak install -y flathub org.gnome.Platform//47 org.gnome.Sdk//47
flatpak-builder --user --install --force-clean build-dir \
    install/flatpak/io.github.sezanzeb.input_remapper.yml
```

Once published, the end-user flow is fully one-click: open the bundle / the
Discover store entry, click Install — done.

## Uninstall (one-click)

- In the app: Settings → **Uninstall** (removes the udev rule + group, keeps
  presets unless you tick "also remove presets").
- Then remove the Flatpak: `flatpak uninstall io.github.sezanzeb.input_remapper`
  (or the trash/uninstall action in Discover).

## Updates

The in-app updater already supports release **channels** (stable / dev) pointed
at the GitHub repo. On SteamOS it offers the matching Flatpak bundle instead of
the `.deb` (see `inputremapper/update_service.py`).

---

## Porting status — needs on-device iteration

This is the first packaging cut. The following must be confirmed/finished on a
real SteamOS machine, because they cannot be validated off-device:

1. **Dependency pinning in the manifest** — replace the placeholder Python
   wheel list and `sha256` values using `flatpak-pip-generator` for the runtime
   Python version. Confirm the `gtksourceview4` and `libayatana-appindicator`
   module builds (pull their sub-dependencies if the build reports missing ones).
2. **Service bus model inside the sandbox** — the injection service currently
   owns `inputremapper.Control` on the **system** bus and runs as root. Inside
   the sandbox it must run as the user on the **session** bus, relying on the
   host udev rule for `uinput`/device access. This is the main code adaptation
   to verify (`data/input-remapper.service`, `inputremapper/daemon.py`,
   `data/inputremapper.Control.conf`).
3. **Tray icon** on the KDE panel via `org.kde.StatusNotifierWatcher`.

Iteration loop: run the build on the device, paste the first error, fix, repeat.
