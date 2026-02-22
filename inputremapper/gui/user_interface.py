# -*- coding: utf-8 -*-
# input-remapper - GUI for device specific keyboard mappings
# Copyright (C) 2025 sezanzeb <b8x45ygc9@mozmail.com>
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


"""User Interface."""
import os
import subprocess
from typing import Dict, Callable, Tuple

import gi

import gi

try:
    gi.require_version("AppIndicator3", "0.1")
except Exception:
    pass

from gi.repository import Gtk, GtkSource, Gdk, GObject

try:
    from gi.repository import AppIndicator3

    APPINDICATOR_AVAILABLE = True
except Exception:
    AppIndicator3 = None
    APPINDICATOR_AVAILABLE = False

from inputremapper.configs.data import get_data_path
from inputremapper.configs.input_config import InputCombination
from inputremapper.configs.mapping import MappingData
from inputremapper.gui.autocompletion import Autocompletion
from inputremapper.gui.components.common import Breadcrumbs
from inputremapper.gui.components.device_groups import DeviceGroupSelection
from inputremapper.gui.components.editor import (
    MappingListBox,
    TargetSelection,
    CodeEditor,
    RecordingToggle,
    RecordingStatus,
    AutoloadSwitch,
    LinkGameDropdown,
    GameAutoSwitcher,
    ReleaseCombinationSwitch,
    CombinationListbox,
    AnalogInputSwitch,
    TriggerThresholdInput,
    OutputAxisSelector,
    ReleaseTimeoutInput,
    TransformationDrawArea,
    Sliders,
    RelativeInputCutoffInput,
    KeyAxisStackSwitcher,
    RequireActiveMapping,
    GdkEventRecorder,
)
from inputremapper.gui.components.main import Stack, StatusBar
from inputremapper.gui.components.presets import PresetSelection
from inputremapper.gui.controller import Controller
from inputremapper.gui.gettext import _
from inputremapper.gui.messages.message_broker import (
    MessageBroker,
    MessageType,
)
from inputremapper.gui.messages.message_data import UserConfirmRequest
from inputremapper.gui.utils import (
    HandlerDisabled,
    gtk_iteration,
)
from inputremapper.injection.injector import InjectorStateMessage
from inputremapper.logging.logger import logger, COMMIT_HASH, VERSION, EVDEV_VERSION
from inputremapper.user import UserUtils

# https://cjenkins.wordpress.com/2012/05/08/use-gtksourceview-widget-in-glade/
GObject.type_register(GtkSource.View)
# GtkSource.View() also works:
# https://stackoverflow.com/questions/60126579/gtk-builder-error-quark-invalid-object-type-webkitwebview


def on_close_about(about, _):
    """Hide the about dialog without destroying it."""
    about.hide()
    return True


AUTOSTART_FILENAME = "input-remapper-gtk-autostart.desktop"
AUTOSTART_HIDDEN_KEY = "X-Input-Remapper-AutoHidden"


class TrayIcon:
    """System tray icon with basic show/quit actions."""

    def __init__(self, ui: "UserInterface"):
        self._ui = ui
        self._icon = None
        self._indicator = None
        self._menu = Gtk.Menu()
        self._item_show = Gtk.MenuItem(label=_("Show"))
        self._item_quit = Gtk.MenuItem(label=_("Quit"))
        self._item_show.connect("activate", self._on_show)
        self._item_quit.connect("activate", self._on_quit)
        self._menu.append(self._item_show)
        self._menu.append(self._item_quit)
        self._menu.show_all()

        if APPINDICATOR_AVAILABLE:
            self._indicator = AppIndicator3.Indicator.new(
                "input-remapper",
                "input-remapper",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self._indicator.set_icon_full("input-remapper", "input-remapper")
            self._indicator.set_menu(self._menu)
            logger.info("Tray backend: AppIndicator")
        else:
            self._icon = Gtk.StatusIcon()
            self._icon.set_from_icon_name("input-remapper")
            self._icon.set_tooltip_text("input-remapper")
            self._icon.connect("activate", self._on_activate)
            self._icon.connect("popup-menu", self._on_popup_menu)
            logger.info("Tray backend: StatusIcon")

    def _on_activate(self, *_):
        if not self._ui.window.get_visible():
            self._ui.show_window()

    def _on_popup_menu(self, _icon, button, time):
        self._menu.popup(None, None, None, None, button, time)

    def _on_show(self, *_):
        self._ui.show_window()

    def _on_quit(self, *_):
        self._ui.controller.close()

class UserInterface:
    """The input-remapper gtk window."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
    ):
        self.message_broker = message_broker
        self.controller = controller

        # all shortcuts executed when ctrl+...
        self.shortcuts: Dict[int, Callable] = {
            Gdk.KEY_q: self.controller.close,
            Gdk.KEY_r: self.controller.refresh_groups,
            Gdk.KEY_Delete: self.controller.stop_injecting,
            Gdk.KEY_n: self.controller.add_preset,
        }

        # stores the ids for all the listeners attached to the gui
        self.gtk_listeners: Dict[Callable, int] = {}

        self.message_broker.subscribe(MessageType.terminate, lambda _: self.close())

        self.builder = Gtk.Builder()
        self._build_ui()
        self.window: Gtk.Window = self.get("window")
        self.about: Gtk.Window = self.get("about-dialog")
        self.combination_editor: Gtk.Dialog = self.get("combination-editor")

        self._create_dialogs()
        self._create_components()
        self._connect_gtk_signals()
        self._connect_message_listener()
        self._connect_settings_controls()

        self.window.show()
        # hide everything until stuff is populated
        self.get("vertical-wrapper").set_opacity(0)
        # if any of the next steps take a bit to complete, have the window
        # already visible (without content) to make it look more responsive.
        gtk_iteration()

        # now show the proper finished content of the window
        self.get("vertical-wrapper").set_opacity(1)
        self._tray_icon = TrayIcon(self)
        self.sync_settings_toggles()
        if os.environ.get("INPUT_REMAPPER_START_HIDDEN") == "1":
            self.close()
        else:
            self.window.present()

    def _build_ui(self):
        """Build the window from stylesheet and gladefile."""
        css_provider = Gtk.CssProvider()

        with open(get_data_path("style.css"), "r") as file:
            css_provider.load_from_data(bytes(file.read(), encoding="UTF-8"))

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        gladefile = get_data_path("input-remapper.glade")
        self.builder.add_from_file(gladefile)
        self.builder.connect_signals(self)

    def _create_components(self):
        """Setup all objects which manage individual components of the ui."""
        message_broker = self.message_broker
        controller = self.controller
        DeviceGroupSelection(message_broker, controller, self.get("device_selection"))
        PresetSelection(message_broker, controller, self.get("preset_selection"))
        MappingListBox(message_broker, controller, self.get("selection_label_listbox"))
        TargetSelection(message_broker, controller, self.get("target-selector"))

        Breadcrumbs(
            message_broker,
            self.get("selected_device_name"),
            show_device_group=True,
        )
        Breadcrumbs(
            message_broker,
            self.get("selected_preset_name"),
            show_device_group=True,
            show_preset=True,
        )

        Stack(message_broker, controller, self.get("main_stack"))
        RecordingToggle(message_broker, controller, self.get("key_recording_toggle"))
        StatusBar(
            message_broker,
            controller,
            self.get("status_bar"),
            self.get("error_status_icon"),
            self.get("warning_status_icon"),
        )
        RecordingStatus(message_broker, self.get("recording_status"))
        AutoloadSwitch(message_broker, controller, self.get("preset_autoload_switch"))
        LinkGameDropdown(
            message_broker, controller, self.get("preset_game_link_combo")
        )
        GameAutoSwitcher(controller.data_manager, message_broker)
        ReleaseCombinationSwitch(
            message_broker, controller, self.get("release-combination-switch")
        )
        CombinationListbox(message_broker, controller, self.get("combination-listbox"))
        AnalogInputSwitch(message_broker, controller, self.get("analog-input-switch"))
        TriggerThresholdInput(
            message_broker, controller, self.get("trigger-threshold-spin-btn")
        )
        RelativeInputCutoffInput(
            message_broker, controller, self.get("input-cutoff-spin-btn")
        )
        OutputAxisSelector(message_broker, controller, self.get("output-axis-selector"))
        KeyAxisStackSwitcher(
            message_broker,
            controller,
            self.get("editor-stack"),
            self.get("key_macro_toggle_btn"),
            self.get("analog_toggle_btn"),
        )
        ReleaseTimeoutInput(
            message_broker, controller, self.get("release-timeout-spin-button")
        )
        TransformationDrawArea(
            message_broker, controller, self.get("transformation-draw-area")
        )
        Sliders(
            message_broker,
            controller,
            self.get("gain-scale"),
            self.get("deadzone-scale"),
            self.get("expo-scale"),
        )

        GdkEventRecorder(self.window, self.get("gdk-event-recorder-label"))

        RequireActiveMapping(
            message_broker,
            self.get("edit-combination-btn"),
            require_recorded_input=True,
        )
        RequireActiveMapping(
            message_broker,
            self.get("output"),
            require_recorded_input=True,
        )
        RequireActiveMapping(
            message_broker,
            self.get("delete-mapping"),
            require_recorded_input=False,
        )

        # code editor and autocompletion
        code_editor = CodeEditor(message_broker, controller, self.get("code_editor"))
        autocompletion = Autocompletion(message_broker, controller, code_editor)
        autocompletion.set_relative_to(self.get("code_editor_container"))
        self.autocompletion = autocompletion  # only for testing

    def _create_dialogs(self):
        """Setup different dialogs, such as the about page."""
        self.about.connect("delete-event", on_close_about)
        # set_position needs to be done once initially, otherwise the
        # dialog is not centered when it is opened for the first time
        self.about.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.get("version-label").set_text(
            f"input-remapper {VERSION} {COMMIT_HASH[:7]}"
            f"\npython-evdev {EVDEV_VERSION}"
            if EVDEV_VERSION
            else ""
        )

    def _connect_gtk_signals(self):
        self.get("delete_preset").connect(
            "clicked", lambda *_: self.controller.delete_preset()
        )
        self.get("copy_preset").connect(
            "clicked", lambda *_: self.controller.copy_preset()
        )
        self.get("create_preset").connect(
            "clicked", lambda *_: self.controller.add_preset()
        )
        self.get("apply_preset").connect(
            "clicked", lambda *_: self.controller.start_injecting()
        )
        self.get("stop_injection_preset_page").connect(
            "clicked", lambda *_: self.controller.stop_injecting()
        )
        self.get("stop_injection_editor_page").connect(
            "clicked", lambda *_: self.controller.stop_injecting()
        )
        self.get("rename-button").connect("clicked", self.on_gtk_rename_clicked)
        self.get("preset_name_input").connect(
            "key-release-event", self.on_gtk_preset_name_input_return
        )
        self.get("create_mapping_button").connect(
            "clicked", lambda *_: self.controller.create_mapping()
        )
        self.get("delete-mapping").connect(
            "clicked", lambda *_: self.controller.delete_mapping()
        )
        self.combination_editor.connect(
            # it only takes self as argument, but delete-events provides more
            # probably a gtk bug
            "delete-event",
            lambda dialog, *_: Gtk.Widget.hide_on_delete(dialog),
        )
        self.get("edit-combination-btn").connect(
            "clicked", lambda *_: self.combination_editor.show()
        )
        self.get("remove-event-btn").connect(
            "clicked", lambda *_: self.controller.remove_event()
        )
        self.connect_shortcuts()

    def _connect_message_listener(self):
        self.message_broker.subscribe(
            MessageType.mapping, self.update_combination_label
        )
        self.message_broker.subscribe(
            MessageType.injector_state, self.on_injector_state_msg
        )
        self.message_broker.subscribe(
            MessageType.user_confirm_request, self._on_user_confirm_request
        )

    def _connect_settings_controls(self):
        """Attach handlers for settings toggles."""
        self._settings_autostart_switch = self.get("settings_autostart_switch")
        self._settings_autohide_switch = self.get("settings_autohide_switch")

        if self._settings_autostart_switch is not None:
            self._settings_autostart_switch.connect(
                "state-set", self._on_settings_autostart_toggled
            )
        if self._settings_autohide_switch is not None:
            self._settings_autohide_switch.connect(
                "state-set", self._on_settings_autohide_toggled
            )

    def sync_settings_toggles(self):
        """Keep settings toggles in sync with stored state."""
        if self._settings_autostart_switch is None:
            return

        autostart_enabled = self.get_autostart_enabled()
        autohide_enabled = self.get_autostart_hidden()

        with HandlerDisabled(self._settings_autostart_switch, self._on_settings_autostart_toggled):
            self._settings_autostart_switch.set_active(autostart_enabled)

        if self._settings_autohide_switch is not None:
            with HandlerDisabled(self._settings_autohide_switch, self._on_settings_autohide_toggled):
                self._settings_autohide_switch.set_active(
                    autohide_enabled if autostart_enabled else False
                )
                self._settings_autohide_switch.set_sensitive(autostart_enabled)

    def apply_autostart_toggle(self, desired: bool) -> bool:
        logger.info("Settings autostart toggle requested: %s", desired)
        if desired:
            if not self.confirm_autostart_permission():
                logger.info("Settings autostart toggle cancelled by user")
                return False
            if not self.get_background_permission_enabled():
                logger.info("Enabling background permission for autostart")
                if not self.set_background_permission_enabled(True):
                    logger.warning("Failed enabling background permission")
                    return False
        else:
            logger.info("Disabling background permission for autostart")
            if not self.set_background_permission_enabled(False):
                logger.warning("Failed disabling background permission")
                return False
        return self.set_autostart_enabled(desired)

    def apply_autohide_toggle(self, desired: bool) -> bool:
        if desired and not self.confirm_autohide():
            return False
        return self.set_autostart_hidden(desired)

    def _on_settings_autostart_toggled(self, _switch, state):
        desired = bool(state)
        if not self.apply_autostart_toggle(desired):
            self.sync_settings_toggles()
            return True
        return False

    def _on_settings_autohide_toggled(self, _switch, state):
        desired = bool(state)
        if not self.apply_autohide_toggle(desired):
            self.sync_settings_toggles()
            return True
        return False

    def _create_checkbox_dialog(
        self, primary: str, secondary: str, checkbox_label: str
    ) -> Tuple[Gtk.MessageDialog, Gtk.CheckButton]:
        dialog = self._create_dialog(primary, secondary)
        checkbox = Gtk.CheckButton(label=checkbox_label)
        checkbox.set_margin_top(6)
        dialog.get_content_area().pack_end(checkbox, False, False, 0)
        dialog.show_all()
        return dialog, checkbox

    def confirm_autohide(self) -> bool:
        if self.controller.data_manager.get_autohide_warning_dismissed():
            return True

        primary = _("Auto Hidden Enabled")
        secondary = _(
            "The window will stay hidden on startup. You can reopen it from the tray "
            "icon in the top bar by clicking the icon."
        )
        dialog, checkbox = self._create_checkbox_dialog(
            primary, secondary, _("Don't show this again")
        )
        response = dialog.run()
        dismissed = checkbox.get_active() and response == Gtk.ResponseType.ACCEPT
        dialog.hide()

        if dismissed:
            self.controller.data_manager.set_autohide_warning_dismissed(True)

        return response == Gtk.ResponseType.ACCEPT

    def _create_dialog(self, primary: str, secondary: str) -> Gtk.MessageDialog:
        """Create a message dialog with cancel and confirm buttons."""
        message_dialog = Gtk.MessageDialog(
            self.window,
            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            Gtk.MessageType.QUESTION,
            Gtk.ButtonsType.NONE,
            primary,
        )

        if secondary:
            message_dialog.format_secondary_text(secondary)

        message_dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)

        confirm_button = message_dialog.add_button("Confirm", Gtk.ResponseType.ACCEPT)
        confirm_button.get_style_context().add_class(Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION)

        return message_dialog

    def _on_user_confirm_request(self, msg: UserConfirmRequest):
        # if the message contains a line-break, use the first chunk for the primary
        # message, and the rest for the secondary message.
        chunks = msg.msg.split("\n")
        primary = chunks[0]
        secondary = " ".join(chunks[1:])

        message_dialog = self._create_dialog(primary, secondary)

        response = message_dialog.run()
        msg.respond(response == Gtk.ResponseType.ACCEPT)

        message_dialog.hide()

    def on_injector_state_msg(self, msg: InjectorStateMessage):
        """Update the ui to reflect the status of the injector."""
        stop_injection_preset_page: Gtk.Button = self.get("stop_injection_preset_page")
        stop_injection_editor_page: Gtk.Button = self.get("stop_injection_editor_page")
        recording_toggle: Gtk.ToggleButton = self.get("key_recording_toggle")

        if msg.active():
            stop_injection_preset_page.set_opacity(1)
            stop_injection_editor_page.set_opacity(1)
            stop_injection_preset_page.set_sensitive(True)
            stop_injection_editor_page.set_sensitive(True)
            recording_toggle.set_opacity(0.5)
        else:
            stop_injection_preset_page.set_opacity(0.5)
            stop_injection_editor_page.set_opacity(0.5)
            stop_injection_preset_page.set_sensitive(True)
            stop_injection_editor_page.set_sensitive(True)
            recording_toggle.set_opacity(1)

    def disconnect_shortcuts(self):
        """Stop listening for shortcuts.

        e.g. when recording key combinations
        """
        try:
            self.window.disconnect(self.gtk_listeners.pop(self.on_gtk_shortcut))
        except KeyError:
            logger.debug("key listeners seem to be not connected")

    def connect_shortcuts(self):
        """Start listening for shortcuts."""
        if not self.gtk_listeners.get(self.on_gtk_shortcut):
            self.gtk_listeners[self.on_gtk_shortcut] = self.window.connect(
                "key-press-event", self.on_gtk_shortcut
            )

    def get(self, name: str):
        """Get a widget from the window."""
        return self.builder.get_object(name)

    def close(self):
        """Close the window."""
        logger.debug("Closing window")
        self.window.hide()

    def show_window(self):
        """Show and focus the window."""
        self.window.show()
        self.window.present()
        self.controller.refresh_groups()

    def update_combination_label(self, mapping: MappingData):
        """Listens for mapping and updates the combination label."""
        label: Gtk.Label = self.get("combination-label")
        if mapping.input_combination.beautify() == label.get_label():
            return
        if mapping.input_combination == InputCombination.empty_combination():
            label.set_opacity(0.5)
            label.set_label(_("no input configured"))
            return

        label.set_opacity(1)
        label.set_label(mapping.input_combination.beautify())

    def on_gtk_shortcut(self, _, event: Gdk.EventKey):
        """Execute shortcuts."""
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            try:
                self.shortcuts[event.keyval]()
            except KeyError:
                pass

    def on_gtk_close(self, *_):
        self.close()
        return True

    def _autostart_user_path(self) -> str:
        return os.path.join(
            os.path.expanduser("~"), ".config", "autostart", AUTOSTART_FILENAME
        )

    def _autostart_system_path(self) -> str:
        return os.path.join("/etc", "xdg", "autostart", AUTOSTART_FILENAME)

    def _polkit_rule_path(self) -> str:
        filename = f"90-input-remapper-{UserUtils.user}.rules"
        return os.path.join("/etc", "polkit-1", "rules.d", filename)

    def _read_autostart_file(self, path: str) -> Dict[str, str]:
        data: Dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if "=" not in line:
                        continue
                    key, value = line.strip().split("=", 1)
                    data[key.strip()] = value.strip()
        except OSError:
            return {}
        return data

    def _autostart_file_disabled(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if "=" not in line:
                        continue
                    key, value = line.strip().split("=", 1)
                    key = key.strip().lower()
                    value = value.strip().lower()
                    if key == "hidden" and value == "true":
                        return True
                    if key == "x-gnome-autostart-enabled" and value == "false":
                        return True
        except OSError:
            return False
        return False

    def get_autostart_enabled(self) -> bool:
        user_path = self._autostart_user_path()
        if os.path.isfile(user_path):
            return not self._autostart_file_disabled(user_path)
        system_path = self._autostart_system_path()
        if os.path.isfile(system_path):
            return not self._autostart_file_disabled(system_path)
        return False

    def get_autostart_hidden(self) -> bool:
        user_path = self._autostart_user_path()
        if not os.path.isfile(user_path):
            return False
        data = self._read_autostart_file(user_path)
        value = data.get(AUTOSTART_HIDDEN_KEY)
        if value is not None:
            return value.strip().lower() == "true"
        exec_value = data.get("Exec", "")
        return "INPUT_REMAPPER_START_HIDDEN=1" in exec_value

    def get_background_permission_enabled(self) -> bool:
        path = self._polkit_rule_path()
        try:
            enabled = os.path.isfile(path)
            logger.info("Background permission rule present=%s path=%s", enabled, path)
            return enabled
        except OSError:
            return False

    def set_background_permission_enabled(self, enabled: bool) -> bool:
        action = "enable" if enabled else "disable"
        logger.info("Requesting background permission action=%s", action)
        cmd = [
            "pkexec",
            "input-remapper-control",
            "--command",
            "set-polkit",
            "--polkit",
            action,
        ]
        exit_code = subprocess.call(cmd)
        if exit_code != 0:
            logger.warning("Failed to update polkit rule, code %s", exit_code)
            return False
        if not enabled:
            self._revoke_polkit_temp_authorization()
        logger.info("Background permission action=%s succeeded", action)
        return True

    def _revoke_polkit_temp_authorization(self) -> None:
        """Best-effort revocation so next privileged action asks for password again."""
        try:
            exit_code = subprocess.call(
                ["pkcheck", "--revoke-temp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Polkit temporary authorization revoke exit_code=%s", exit_code)
        except FileNotFoundError:
            logger.info("pkcheck not found, skipping temporary authorization revoke")

    def confirm_autostart_permission(self) -> bool:
        if self.controller.data_manager.get_autostart_warning_dismissed():
            return True

        primary = _("Enable autostart without repeated passwords?")
        secondary = _(
            "To start in the background after reboot and keep your mappings active, "
            "Input Remapper needs a one-time permission for your user. You can disable "
            "autostart later in Settings."
        )
        dialog, checkbox = self._create_checkbox_dialog(
            primary, secondary, _("Don't show this again")
        )
        response = dialog.run()
        dismissed = checkbox.get_active() and response == Gtk.ResponseType.ACCEPT
        dialog.hide()

        if dismissed:
            self.controller.data_manager.set_autostart_warning_dismissed(True)

        return response == Gtk.ResponseType.ACCEPT

    def set_autostart_enabled(self, enabled: bool) -> bool:
        user_path = self._autostart_user_path()
        try:
            os.makedirs(os.path.dirname(user_path), exist_ok=True)
            self._write_autostart_file(user_path, enabled, self.get_autostart_hidden())
            return True
        except OSError as exc:
            logger.warning("Failed to update autostart: %s", exc)
            return False

    def set_autostart_hidden(self, hidden: bool) -> bool:
        user_path = self._autostart_user_path()
        try:
            os.makedirs(os.path.dirname(user_path), exist_ok=True)
            self._write_autostart_file(user_path, self.get_autostart_enabled(), hidden)
            return True
        except OSError as exc:
            logger.warning("Failed to update autostart hidden: %s", exc)
            return False

    def _write_autostart_file(self, path: str, enabled: bool, hidden: bool) -> None:
        exec_cmd = "input-remapper-gtk"
        if hidden:
            exec_cmd = "env INPUT_REMAPPER_START_HIDDEN=1 input-remapper-gtk"
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            "Name=input-remapper-gtk",
            f"Exec={exec_cmd}",
            "Icon=input-remapper",
            f"{AUTOSTART_HIDDEN_KEY}={'true' if hidden else 'false'}",
        ]
        if enabled:
            lines.append("X-GNOME-Autostart-enabled=true")
        else:
            lines.append("Hidden=true")
            lines.append("X-GNOME-Autostart-enabled=false")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def on_gtk_about_clicked(self, _):
        """Show the about/help dialog."""
        self.about.show()

    def on_gtk_about_key_press(self, _, event):
        """Hide the about/help dialog."""
        gdk_keycode = event.get_keyval()[1]
        if gdk_keycode == Gdk.KEY_Escape:
            self.about.hide()

    def on_gtk_rename_clicked(self, *_):
        name = self.get("preset_name_input").get_text()
        self.controller.rename_preset(name)
        self.get("preset_name_input").set_text("")

    def on_gtk_preset_name_input_return(self, _, event: Gdk.EventKey):
        if event.keyval == Gdk.KEY_Return:
            self.on_gtk_rename_clicked()
