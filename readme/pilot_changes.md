# Pilot Changes (Input Remapper Fork)

This document summarizes the functional and technical changes introduced in this fork during the pilot cycle.
It is intended as a quick delta between upstream `input-remapper` behavior and the current local working tree.

## Functional Changes

1. Added a persistent pilot monitoring log (rotating file) enabled by default.
2. Improved hidden startup behavior:
   - tries non-interactive reader startup first,
   - avoids blocking password prompts at hidden boot when background permission is not available.
3. Reworked autostart/background-permission flow:
   - explicit permission checks,
   - explicit revoke of temporary polkit authorization when needed,
   - better UI resynchronization after toggle actions.
4. Added in-app uninstall flow from **Settings**:
   - uninstall app/services/polkit/autostart entries,
   - optional removal of presets/config.
5. Hardened mapping editor persistence:
   - while typing, invalid intermediate output symbols are no longer persisted.
6. Added legacy output symbol normalization on preset load:
   - old symbols like `&` are normalized to key names like `ampersand`.

## File-Level Changes

All files below are **modified** (no new tracked file except this document, no deleted tracked file):

1. `data/input-remapper.glade`
   - Added Settings sections: **Automation** and **Install**.
   - Added `settings_uninstall_button` wired to uninstall handler.
2. `inputremapper/bin/input_remapper_control.py`
   - Added internal command `uninstall`.
   - Added `--remove-config` option.
   - Implemented uninstall routine (systemd stop/disable, polkit cleanup, autostart cleanup, package purge).
   - Removed automatic polkit-rule creation from `start-reader-service`.
3. `inputremapper/bin/input_remapper_gtk.py`
   - Added non-interactive background permission probe via `pkcheck`.
   - Hidden start now attempts non-interactive reader startup and defers cleanly when not authorized.
4. `inputremapper/configs/keyboard_layout.py`
   - Removed user symbol alias resolution in `KeyboardLayout.get`.
5. `inputremapper/daemon.py`
   - Propagates monitor env vars when starting daemon via `pkexec`.
6. `inputremapper/gui/components/editor.py`
   - Uses non-persistent mapping updates while typing (`persist=False`).
   - Persists only when mapping is valid.
7. `inputremapper/gui/controller.py`
   - Added `persist` parameter to `update_mapping`.
8. `inputremapper/gui/data_manager.py`
   - Added legacy output symbol alias map + normalization on preset load.
9. `inputremapper/gui/reader_service.py`
   - Added `allow_user_interaction` parameter for reader startup.
   - Supports non-interactive `pkexec --disable-internal-agent`.
   - Propagates monitor env vars.
10. `inputremapper/gui/user_interface.py`
   - Settings toggle wiring/logging/sync updates.
   - Background permission checks now combine rule presence + non-interactive `pkcheck`.
   - Added uninstall dialog flow and execution.
   - Added fallback glade handler `on_gtk_settings_uninstall_clicked`.
11. `inputremapper/logging/logger.py`
   - Added rotating monitor log output with env-based configuration:
     - `INPUT_REMAPPER_MONITOR`
     - `INPUT_REMAPPER_MONITOR_PATH`
   - Monitoring defaults to enabled for pilot.
12. `tests/unit/test_system_mapping.py`
   - Removed tests tied to removed keyboard symbol alias behavior.

## Added / Removed Behavior Summary

### Added

1. Pilot monitoring log pipeline.
2. Settings uninstall UX + internal uninstall command.
3. Better hidden-boot behavior and permission-state diagnostics.
4. Legacy symbol migration on preset load.

### Removed

1. Direct symbol aliases in `KeyboardLayout.get` (e.g. `"1"` -> `KEY_1`, `","` -> `comma`) at lookup layer.
2. Automatic polkit rule creation side-effect in `start-reader-service`.

## Monitoring Log Path

Default path (if not overridden):

`~/.config/input-remapper-2/logs/pilot-monitor.log`

Env override:

1. `INPUT_REMAPPER_MONITOR=0` to disable monitor file logging.
2. `INPUT_REMAPPER_MONITOR_PATH=/custom/path.log` to set a custom file path.

## Notes for Review / PR Prep

1. Current document reflects the local working tree state.
2. Before opening PR:
   - run targeted tests for modified flows,
   - verify uninstall on a clean machine profile,
   - confirm monitor default-on policy is acceptable upstream.
