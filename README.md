<p align="center"><img src="data/input-remapper.svg" width=100/></p>

<h1 align="center">Input Remapper</h1>

<p align="center">
  An easy to use tool for Linux to change the behaviour of your input devices.<br/>
  Supports X11, Wayland, combinations, programmable macros, joysticks, wheels,<br/>
  triggers, keys, mouse-movements and more. Maps any input to any other input.
</p>

<p align="center"><a href="readme/usage.md">Usage</a> - <a href="readme/macros.md">Macros</a> - <a href="#installation">Installation</a> - <a href="readme/development.md">Development</a> - <a href="readme/examples.md">Examples</a></p>

<p align="center"><img src="readme/pylint.svg"/> <img src="readme/coverage.svg"/></p>

## Fork Status

This repository is a modified fork of the official Input Remapper project:
https://github.com/sezanzeb/input-remapper

This fork is not an official upstream release. It is actively developed and validated through pilot sessions before proposing upstream changes.

Branch policy for this fork:
- `main`: stable branch used as production baseline.
- `dev`: integration branch for ongoing changes and tests.
- Current validation target: Ubuntu.
- Debian and other distro feedback is welcome, but this fork is not documented as validated there yet.

<p align="center">
  <img src="readme/screenshot.png" width="48%"/>
  &#160;
  <img src="readme/screenshot_2.png" width="48%"/>
</p>

<br/>

## Fork Additions

- Ubuntu-first packaging and install flow validated with App Center.
- Clean uninstall flow from the application, with presets kept by default.
- Autostart toggle with privilege prompt.
- Auto-hide support with tray icon behavior validated in normal use.
- Stable `main` branch and separate `dev` integration branch.

<br/>

## Installation

### Ubuntu

1. Open the [stable release page](https://github.com/gypg7p6c24-byte/input-remapper/releases/tag/stable-latest).
2. Download the `.deb` asset attached to that release.
   Current stable file: `input-remapper-2.2.0.deb`
3. Double-click the downloaded file.
4. App Center opens.
5. Click `Install`.
6. Enter your password when asked.
7. Launch `Input Remapper` from the applications list.

This is the supported install flow for this fork.

### Notes

- The current documented target is Ubuntu.
- Debian and other distributions are not yet documented as validated in this fork.
- GitHub Issues are currently disabled on this fork.
