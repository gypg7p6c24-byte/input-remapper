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


"""All components that control a single preset."""


from __future__ import annotations

from collections import defaultdict
from typing import List, Optional, Dict, Union, Callable, Literal, Set

import cairo
from evdev.ecodes import (
    EV_KEY,
    EV_ABS,
    EV_REL,
    BTN_LEFT,
    BTN_MIDDLE,
    BTN_RIGHT,
    BTN_EXTRA,
    BTN_SIDE,
)
import json
import os
import re
import shutil
import subprocess

from gi.repository import Gtk, GtkSource, Gdk, GLib

from inputremapper.configs.input_config import InputCombination, InputConfig
from inputremapper.configs.keyboard_layout import keyboard_layout, XKB_KEYCODE_OFFSET
from inputremapper.configs.mapping import MappingData, MappingType
from inputremapper.groups import DeviceType
from inputremapper.gui.components.output_type_names import OutputTypeNames
from inputremapper.gui.controller import Controller
from inputremapper.gui.gettext import _
from inputremapper.gui.messages.message_broker import (
    MessageBroker,
    MessageType,
)
from inputremapper.gui.messages.message_data import (
    UInputsData,
    PresetData,
    CombinationUpdate,
)
from inputremapper.gui.utils import HandlerDisabled, Colors
from inputremapper.logging.logger import logger
from inputremapper.injection.mapping_handlers.axis_transform import Transformation
from inputremapper.input_event import InputEvent
from inputremapper.utils import (
    get_evdev_constant_name,
    get_steam_installed_games,
    get_steam_installed_game_paths,
)

Capabilities = Dict[int, List]

SET_KEY_FIRST = _("Record the input first")

ICON_NAMES = {
    DeviceType.GAMEPAD: "input-gaming",
    DeviceType.MOUSE: "input-mouse",
    DeviceType.KEYBOARD: "input-keyboard",
    DeviceType.GRAPHICS_TABLET: "input-tablet",
    DeviceType.TOUCHPAD: "input-touchpad",
    DeviceType.UNKNOWN: None,
}

# sort types that most devices would fall in easily to the right.
ICON_PRIORITIES = [
    DeviceType.GRAPHICS_TABLET,
    DeviceType.TOUCHPAD,
    DeviceType.GAMEPAD,
    DeviceType.MOUSE,
    DeviceType.KEYBOARD,
    DeviceType.UNKNOWN,
]


class TargetSelection:
    """The dropdown menu to select the targe_uinput of the active_mapping,

    For example "keyboard" or "gamepad".
    """

    _mapping: Optional[MappingData] = None

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        combobox: Gtk.ComboBox,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = combobox

        self._message_broker.subscribe(MessageType.uinputs, self._on_uinputs_changed)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_loaded)
        self._gui.connect("changed", self._on_gtk_target_selected)

    def _select_current_target(self):
        """Select the currently configured target."""
        if self._mapping is not None:
            with HandlerDisabled(self._gui, self._on_gtk_target_selected):
                self._gui.set_active_id(self._mapping.target_uinput)

    def _on_uinputs_changed(self, data: UInputsData):
        target_store = Gtk.ListStore(str)
        for uinput in data.uinputs.keys():
            target_store.append([uinput])

        self._gui.set_model(target_store)
        renderer_text = Gtk.CellRendererText()
        self._gui.pack_start(renderer_text, False)
        self._gui.add_attribute(renderer_text, "text", 0)
        self._gui.set_id_column(0)

        self._select_current_target()

    def _on_mapping_loaded(self, mapping: MappingData):
        self._mapping = mapping
        self._select_current_target()

    def _on_gtk_target_selected(self, *_):
        target = self._gui.get_active_id()
        self._controller.update_mapping(target_uinput=target)


class MappingListBox:
    """The listbox showing all available mapping in the active_preset."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        listbox: Gtk.ListBox,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = listbox
        self._gui.set_sort_func(self._sort_func)

        self._message_broker.subscribe(MessageType.preset, self._on_preset_changed)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_changed)
        self._gui.connect("row-selected", self._on_gtk_mapping_selected)

    @staticmethod
    def _sort_func(row1: MappingSelectionLabel, row2: MappingSelectionLabel) -> int:
        """Sort alphanumerical by name."""
        if row1.combination == InputCombination.empty_combination():
            return 1
        if row2.combination == InputCombination.empty_combination():
            return 0

        return 0 if row1.name < row2.name else 1

    def _on_preset_changed(self, data: PresetData):
        selection_labels = self._gui.get_children()
        for selection_label in selection_labels:
            selection_label.cleanup()
            self._gui.remove(selection_label)

        if not data.mappings:
            return

        for mapping in data.mappings:
            selection_label = MappingSelectionLabel(
                self._message_broker,
                self._controller,
                mapping.format_name(),
                mapping.input_combination,
            )
            self._gui.insert(selection_label, -1)
        self._gui.invalidate_sort()

    def _on_mapping_changed(self, mapping: MappingData):
        with HandlerDisabled(self._gui, self._on_gtk_mapping_selected):
            combination = mapping.input_combination

            for row in self._gui.get_children():
                if row.combination == combination:
                    self._gui.select_row(row)

    def _on_gtk_mapping_selected(self, _, row: Optional[MappingSelectionLabel]):
        if not row:
            return
        self._controller.load_mapping(row.combination)


class MappingSelectionLabel(Gtk.ListBoxRow):
    """The ListBoxRow representing a mapping inside the MappingListBox."""

    __gtype_name__ = "MappingSelectionLabel"

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        name: Optional[str],
        combination: InputCombination,
    ):
        super().__init__()
        self._message_broker = message_broker
        self._controller = controller

        if not name:
            name = combination.beautify()

        self.name = name
        self.combination = combination
        # add hotkey handler
        self.connect("key-press-event", self._on_key_press)

        # Make the child label widget break lines, important for
        # long combinations
        self.label = Gtk.Label()
        self.label.set_line_wrap(True)
        self.label.set_line_wrap_mode(Gtk.WrapMode.WORD)
        self.label.set_justify(Gtk.Justification.CENTER)
        # set the name or combination.beautify as label
        self.label.set_label(self.name)

        self.label.set_margin_top(11)
        self.label.set_margin_bottom(11)

        # button to edit the name of the mapping
        self.edit_btn = Gtk.Button()
        self.edit_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.edit_btn.set_image(
            Gtk.Image.new_from_icon_name(Gtk.STOCK_EDIT, Gtk.IconSize.MENU)
        )
        self.edit_btn.set_tooltip_text(_("Change Mapping Name") + " (F2)")
        self.edit_btn.set_margin_top(4)
        self.edit_btn.set_margin_bottom(4)
        self.edit_btn.connect("clicked", self._set_edit_mode)

        self.name_input = Gtk.Entry()
        self.name_input.set_text(self.name)
        self.name_input.set_halign(Gtk.Align.FILL)
        self.name_input.set_margin_top(4)
        self.name_input.set_margin_bottom(4)
        self.name_input.connect("activate", self._on_gtk_rename_finished)
        self.name_input.connect("key-press-event", self._on_gtk_rename_abort)

        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._box.set_center_widget(self.label)
        self._box.add(self.edit_btn)
        self._box.set_child_packing(self.edit_btn, False, False, 4, Gtk.PackType.END)
        self._box.add(self.name_input)
        self._box.set_child_packing(self.name_input, True, True, 4, Gtk.PackType.START)

        self.add(self._box)
        self.show_all()
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_changed)
        self._message_broker.subscribe(
            MessageType.combination_update, self._on_combination_update
        )

        self.edit_btn.hide()
        self.name_input.hide()

    def __repr__(self):
        return f"<MappingSelectionLabel for {self.combination} as {self.name} at {hex(id(self))}>"

    def _set_not_selected(self):
        self.edit_btn.hide()
        self.name_input.hide()
        self.label.show()

    def _set_selected(self):
        self.label.set_label(self.name)
        self.edit_btn.show()
        self.name_input.hide()
        self.label.show()

    def _set_edit_mode(self, *_):
        self.name_input.set_text(self.name)
        self.label.hide()
        self.name_input.show()
        self._controller.set_focus(self.name_input)

    def _on_key_press(self, widget, event):
        """ "Mapping Selection Row Label key handler for hotkeys"""
        if self.label.is_visible():
            # hotkeys are only meaningful when not already in edit-mapping-name-mode
            if event.keyval == Gdk.KEY_F2:
                self._set_edit_mode()
            elif event.keyval == Gdk.KEY_Delete:
                self._controller.delete_mapping()

    def _on_mapping_changed(self, mapping: MappingData):
        if mapping.input_combination != self.combination:
            self._set_not_selected()
            return
        self.name = mapping.format_name()
        self._set_selected()
        self.get_parent().invalidate_sort()

    def _on_combination_update(self, data: CombinationUpdate):
        if data.old_combination == self.combination and self.is_selected():
            self.combination = data.new_combination

    def _on_gtk_rename_finished(self, *_):
        name = self.name_input.get_text()
        if name.lower().strip() == self.combination.beautify().lower():
            name = ""
        self.name = name
        self._set_selected()
        self._controller.update_mapping(name=name)

    def _on_gtk_rename_abort(self, _, key_event: Gdk.EventKey):
        if key_event.keyval == Gdk.KEY_Escape:
            self._set_selected()

    def cleanup(self) -> None:
        """Clean up message listeners. Execute before removing from gui!"""
        self._message_broker.unsubscribe(self._on_mapping_changed)
        self._message_broker.unsubscribe(self._on_combination_update)


class GdkEventRecorder:
    """Records events delivered by GDK, similar to the ReaderService/ReaderClient."""

    _combination: List[int]
    _pressed: Set[int]

    __gtype_name__ = "GdkEventRecorder"

    def __init__(self, window: Gtk.Window, gui: Gtk.Label):
        super().__init__()
        self._combination = []
        self._pressed = set()
        self._gui = gui
        window.connect("event", self._on_gtk_event)

    def _get_button_code(self, event: Gdk.Event):
        """Get the evdev code for the given event."""
        return {
            Gdk.BUTTON_MIDDLE: BTN_MIDDLE,
            Gdk.BUTTON_PRIMARY: BTN_LEFT,
            Gdk.BUTTON_SECONDARY: BTN_RIGHT,
            9: BTN_EXTRA,
            8: BTN_SIDE,
        }.get(event.get_button().button)

    def _reset(self, event: Gdk.Event):
        """If a new combination is being typed, start from scratch."""
        gdk_event_type: int = event.type

        is_press = gdk_event_type in [
            Gdk.EventType.KEY_PRESS,
            Gdk.EventType.BUTTON_PRESS,
        ]

        if len(self._pressed) == 0 and is_press:
            self._combination = []

    def _press(self, event: Gdk.Event):
        """Remember pressed keys, write down combinations."""
        gdk_event_type: int = event.type

        if gdk_event_type == Gdk.EventType.KEY_PRESS:
            code = event.hardware_keycode - XKB_KEYCODE_OFFSET
            if code not in self._combination:
                self._combination.append(code)

            self._pressed.add(code)

        if gdk_event_type == Gdk.EventType.BUTTON_PRESS:
            code = self._get_button_code(event)
            if code not in self._combination:
                self._combination.append(code)

            self._pressed.add(code)

    def _release(self, event: Gdk.Event):
        """Clear pressed keys if this is a release event."""
        if event.type in [Gdk.EventType.KEY_RELEASE, Gdk.EventType.BUTTON_RELEASE]:
            self._pressed = set()

    def _display(self, event):
        """Show the recorded combination in the gui."""
        is_press = event.type in [
            Gdk.EventType.KEY_PRESS,
            Gdk.EventType.BUTTON_PRESS,
        ]

        if is_press and len(self._combination) > 0:
            names = [
                keyboard_layout.get_name(code)
                for code in self._combination
                if code is not None and keyboard_layout.get_name(code) is not None
            ]
            self._gui.set_text(" + ".join(names))

    def _on_gtk_event(self, _, event: Gdk.Event):
        """For all sorts of input events that gtk cares about."""
        self._reset(event)
        self._release(event)
        self._press(event)
        self._display(event)


class CodeEditor:
    """The editor used to edit the output_symbol of the active_mapping."""

    placeholder: str = _("Enter your output here")

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        editor: GtkSource.View,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self.gui = editor

        # without this the wrapping ScrolledWindow acts weird when new lines are added,
        # not offering enough space to the text editor so the whole thing is suddenly
        # scrollable by a few pixels.
        # Found this after making blind guesses with settings in glade, and then
        # actually looking at the snapshot preview! In glades editor this didn't have an
        # effect.
        self.gui.set_resize_mode(Gtk.ResizeMode.IMMEDIATE)

        # Syntax Highlighting
        # TODO there are some similarities with python, but overall it's quite useless.
        #  commented out until there is proper highlighting for input-remappers syntax.
        # Thanks to https://github.com/wolfthefallen/py-GtkSourceCompletion-example
        # language_manager = GtkSource.LanguageManager()
        # fun fact: without saving LanguageManager into its own variable it doesn't work
        #  python = language_manager.get_language("python")
        # source_view.get_buffer().set_language(python)

        self._update_placeholder()

        self.gui.get_buffer().connect("changed", self._on_gtk_changed)
        self.gui.connect("focus-in-event", self._update_placeholder)
        self.gui.connect("focus-out-event", self._update_placeholder)
        self._connect_message_listener()

    def _update_placeholder(self, *_):
        buffer = self.gui.get_buffer()
        code = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

        # test for incorrect states and fix them, without causing side effects
        with HandlerDisabled(buffer, self._on_gtk_changed):
            if self.gui.has_focus() and code == self.placeholder:
                # hide the placeholder
                buffer.set_text("")
                self.gui.get_style_context().remove_class("opaque-text")
            elif code == "":
                # show the placeholder instead
                buffer.set_text(self.placeholder)
                self.gui.get_style_context().add_class("opaque-text")
            elif code != "":
                # something is written, ensure the opacity is correct
                self.gui.get_style_context().remove_class("opaque-text")

    def _shows_placeholder(self):
        buffer = self.gui.get_buffer()
        code = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        return code == self.placeholder

    @property
    def code(self) -> str:
        """Get the user-defined macro code string."""
        if self._shows_placeholder():
            return ""

        buffer = self.gui.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

    @code.setter
    def code(self, code: str) -> None:
        """Set the text without triggering any events."""
        buffer = self.gui.get_buffer()
        with HandlerDisabled(buffer, self._on_gtk_changed):
            buffer.set_text(code)
            self._update_placeholder()
            self.gui.do_move_cursor(self.gui, Gtk.MovementStep.BUFFER_ENDS, -1, False)

    def _connect_message_listener(self):
        self._message_broker.subscribe(
            MessageType.mapping,
            self._on_mapping_loaded,
        )
        self._message_broker.subscribe(
            MessageType.recording_finished,
            self._on_recording_finished,
        )

    def _toggle_line_numbers(self):
        """Show line numbers if multiline, otherwise remove them."""
        if "\n" in self.code:
            self.gui.set_show_line_numbers(True)
            # adds a bit of space between numbers and text:
            self.gui.set_show_line_marks(True)
            self.gui.set_monospace(True)
            self.gui.get_style_context().add_class("multiline")
        else:
            self.gui.set_show_line_numbers(False)
            self.gui.set_show_line_marks(False)
            self.gui.set_monospace(False)
            self.gui.get_style_context().remove_class("multiline")

    def _on_gtk_changed(self, *_):
        if self._shows_placeholder():
            return

        self._controller.update_mapping(output_symbol=self.code)

    def _on_mapping_loaded(self, mapping: MappingData):
        code = SET_KEY_FIRST
        if not self._controller.is_empty_mapping():
            code = mapping.output_symbol or ""

        if self.code.strip().lower() != code.strip().lower():
            self.code = code

        self._toggle_line_numbers()

    def _on_recording_finished(self, _):
        self._controller.set_focus(self.gui)


class RequireActiveMapping:
    """Disable the widget if no mapping is selected."""

    def __init__(
        self,
        message_broker: MessageBroker,
        widget: Gtk.ToggleButton,
        require_recorded_input: bool,
    ):
        self._widget = widget
        self._default_tooltip = self._widget.get_tooltip_text()
        self._require_recorded_input = require_recorded_input

        self._active_preset: Optional[PresetData] = None
        self._active_mapping: Optional[MappingData] = None

        message_broker.subscribe(MessageType.preset, self._on_preset)
        message_broker.subscribe(MessageType.mapping, self._on_mapping)

    def _on_preset(self, preset_data: PresetData):
        self._active_preset = preset_data
        self._check()

    def _on_mapping(self, mapping_data: MappingData):
        self._active_mapping = mapping_data
        self._check()

    def _check(self, *__):
        if not self._active_preset or len(self._active_preset.mappings) == 0:
            self._disable()
            self._widget.set_tooltip_text(_("Add a mapping first"))
            return

        if (
            self._require_recorded_input
            and self._active_mapping
            and not self._active_mapping.has_input_defined()
        ):
            self._disable()
            self._widget.set_tooltip_text(_("Record input first"))
            return

        self._enable()
        self._widget.set_tooltip_text(self._default_tooltip)

    def _enable(self):
        self._widget.set_sensitive(True)
        self._widget.set_opacity(1)

    def _disable(self):
        self._widget.set_sensitive(False)
        self._widget.set_opacity(0.5)


class RecordingToggle:
    """The toggle that starts input recording for the active_mapping."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        toggle: Gtk.ToggleButton,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = toggle

        toggle.connect("toggled", self._on_gtk_toggle)
        # Don't leave the input when using arrow keys or tab. wait for the
        # window to consume the keycode from the reader. I.e. a tab input should
        # be recorded, instead of causing the recording to stop.
        toggle.connect("key-press-event", lambda *args: Gdk.EVENT_STOP)
        self._message_broker.subscribe(
            MessageType.recording_finished,
            self._on_recording_finished,
        )

        RequireActiveMapping(
            message_broker,
            toggle,
            require_recorded_input=False,
        )

    def _on_gtk_toggle(self, *__):
        if self._gui.get_active():
            self._controller.start_key_recording()
        else:
            self._controller.stop_key_recording()

    def _on_recording_finished(self, __):
        with HandlerDisabled(self._gui, self._on_gtk_toggle):
            self._gui.set_active(False)


class RecordingStatus:
    """Displays if keys are being recorded for a mapping."""

    def __init__(
        self,
        message_broker: MessageBroker,
        label: Gtk.Label,
    ):
        self._gui = label

        message_broker.subscribe(
            MessageType.recording_started,
            self._on_recording_started,
        )

        message_broker.subscribe(
            MessageType.recording_finished,
            self._on_recording_finished,
        )

    def _on_recording_started(self, _):
        self._gui.set_visible(True)

    def _on_recording_finished(self, _):
        self._gui.set_visible(False)


class AutoloadSwitch:
    """The switch used to toggle the autoload state of the active_preset."""

    def __init__(
        self, message_broker: MessageBroker, controller: Controller, switch: Gtk.Switch
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = switch

        self._gui.connect("state-set", self._on_gtk_toggle)
        self._message_broker.subscribe(MessageType.preset, self._on_preset_changed)

    def _on_preset_changed(self, data: PresetData):
        with HandlerDisabled(self._gui, self._on_gtk_toggle):
            self._gui.set_active(data.autoload)

    def _on_gtk_toggle(self, *_):
        self._controller.set_autoload(self._gui.get_active())


class LinkGameDropdown:
    """The dropdown used to select a Steam game to link the preset to."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.ComboBoxText,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui
        self._game_ids: Set[str] = set()

        self._populate()
        self._gui.connect("changed", self._on_gtk_changed)
        self._message_broker.subscribe(MessageType.init, self._on_init)
        self._message_broker.subscribe(MessageType.preset, self._on_preset_changed)

    def _on_init(self, _):
        self._populate()

    def _populate(self):
        self._gui.remove_all()
        self._game_ids = set()

        self._gui.append("none", _("No Game"))
        self._game_ids.add("none")

        for appid, name in get_steam_installed_games():
            self._gui.append(appid, name)
            self._game_ids.add(appid)

        with HandlerDisabled(self._gui, self._on_gtk_changed):
            self._gui.set_active_id("none")

    def _on_preset_changed(self, data: PresetData):
        desired = data.game_id or "none"
        if desired not in self._game_ids and desired != "none":
            self._gui.append(desired, _("Unknown Game (%s)") % desired)
            self._game_ids.add(desired)

        with HandlerDisabled(self._gui, self._on_gtk_changed):
            self._gui.set_active_id(desired)

    def _on_gtk_changed(self, *_):
        game_id = self._gui.get_active_id()
        if game_id is None:
            return
        if not game_id or game_id == "none":
            self._controller.set_game_binding(None)
        else:
            self._controller.set_game_binding(game_id)


class ActiveWindowWatcher:
    """Poll the active window and log changes (debug-only helper)."""

    def __init__(self):
        self._last = None
        self._ticks = 0
        self._mode = os.environ.get("XDG_SESSION_TYPE", "").lower()
        logger.info("WINDOW_WATCHER started (poll=1000ms)")
        self._log_env()
        if self._mode == "wayland":
            self._ensure_gnome_extension()
        GLib.timeout_add(1000, self._poll)

    def _log_env(self):
        self._log_debug_kv(
            "env",
            {
                "XDG_SESSION_TYPE": os.environ.get("XDG_SESSION_TYPE", ""),
                "XDG_CURRENT_DESKTOP": os.environ.get("XDG_CURRENT_DESKTOP", ""),
                "XDG_SESSION_DESKTOP": os.environ.get("XDG_SESSION_DESKTOP", ""),
                "GNOME_SHELL_SESSION_MODE": os.environ.get(
                    "GNOME_SHELL_SESSION_MODE", ""
                ),
                "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", ""),
                "DISPLAY": os.environ.get("DISPLAY", ""),
            },
        )
        self._log_debug_kv(
            "cmds",
            {
                "gdbus": shutil.which("gdbus"),
                "gnome-extensions": shutil.which("gnome-extensions"),
                "xdotool": shutil.which("xdotool"),
                "wmctrl": shutil.which("wmctrl"),
                "swaymsg": shutil.which("swaymsg"),
            },
        )

    def _log_debug(self, message: str, *args):
        logger.info("WINDOW_WATCHER_DEBUG " + message, *args)

    def _log_debug_kv(self, label: str, mapping: dict):
        try:
            parts = []
            for key, value in mapping.items():
                parts.append(f"{key}={value!r}")
            logger.info("WINDOW_WATCHER_DEBUG %s %s", label, " ".join(parts))
        except Exception as exc:
            logger.info("WINDOW_WATCHER_DEBUG %s failed: %s", label, exc)

    def _ensure_gnome_extension(self):
        uuid = "input-remapper-active-window@inputremapper"
        source_dir = (
            "/usr/share/input-remapper/gnome-extension/input-remapper-active-window"
        )
        target_dir = os.path.join(
            os.path.expanduser("~"),
            ".local",
            "share",
            "gnome-shell",
            "extensions",
            uuid,
        )

        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
        session_desktop = os.environ.get("XDG_SESSION_DESKTOP", "")
        session_mode = os.environ.get("GNOME_SHELL_SESSION_MODE", "")
        self._log_debug(
            "env desktop=%s session_desktop=%s session_mode=%s",
            desktop,
            session_desktop,
            session_mode,
        )
        if "gnome" not in desktop.lower() and "gnome" not in session_desktop.lower():
            logger.info("WINDOW_WATCHER unsupported desktop for extension")
            return

        self._log_debug(
            "extension source_dir=%s exists=%s",
            source_dir,
            os.path.isdir(source_dir),
        )
        if not os.path.isdir(source_dir):
            logger.info("WINDOW_WATCHER extension source missing: %s", source_dir)
            return

        try:
            os.makedirs(target_dir, exist_ok=True)
            for filename in ("metadata.json", "extension.js"):
                src = os.path.join(source_dir, filename)
                dst = os.path.join(target_dir, filename)
                if os.path.exists(src):
                    shutil.copy2(src, dst)
            meta_path = os.path.join(target_dir, "metadata.json")
            ext_path = os.path.join(target_dir, "extension.js")
            self._log_debug(
                "extension installed to %s meta=%s ext=%s",
                target_dir,
                os.path.exists(meta_path),
                os.path.exists(ext_path),
            )
            try:
                import hashlib

                def _hash(path: str) -> str:
                    with open(path, "rb") as handle:
                        return hashlib.sha256(handle.read()).hexdigest()

                src_meta = os.path.join(source_dir, "metadata.json")
                src_ext = os.path.join(source_dir, "extension.js")
                if os.path.exists(src_meta) and os.path.exists(meta_path):
                    self._log_debug(
                        "meta sha src=%s dst=%s",
                        _hash(src_meta),
                        _hash(meta_path),
                    )
                if os.path.exists(src_ext) and os.path.exists(ext_path):
                    self._log_debug(
                        "ext sha src=%s dst=%s",
                        _hash(src_ext),
                        _hash(ext_path),
                    )
            except Exception as exc:
                logger.info("WINDOW_WATCHER extension hash failed: %s", exc)

            try:
                cache_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".cache",
                    "gnome-shell",
                    "extensions",
                    uuid,
                )
                if os.path.isdir(cache_dir):
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    self._log_debug("extension cache cleared: %s", cache_dir)
            except Exception as exc:
                logger.info("WINDOW_WATCHER extension cache clear failed: %s", exc)
        except Exception as exc:
            logger.info("WINDOW_WATCHER extension install failed: %s", exc)
            return

        try:
            version = subprocess.check_output(
                ["gnome-extensions", "--version"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug("gnome-extensions version: %s", version)
            enabled = subprocess.check_output(
                ["gnome-extensions", "list", "--enabled"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug("extensions enabled: %s", enabled)
            available = subprocess.check_output(
                ["gnome-extensions", "list"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug("extensions available: %s", available)
        except subprocess.CalledProcessError as exc:
            logger.info(
                "WINDOW_WATCHER gnome-extensions probe failed: %s output=%s",
                exc,
                exc.output,
            )
        except FileNotFoundError:
            logger.info("WINDOW_WATCHER gnome-extensions not found")
        except Exception as exc:
            logger.info("WINDOW_WATCHER gnome-extensions probe failed: %s", exc)

        try:
            subprocess.check_output(
                ["gnome-extensions", "enable", uuid],
                stderr=subprocess.STDOUT,
                text=True,
            )
            logger.info("WINDOW_WATCHER extension enabled")
            enabled = subprocess.check_output(
                ["gnome-extensions", "list", "--enabled"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug("extensions enabled: %s", enabled)
            info = subprocess.check_output(
                ["gnome-extensions", "info", uuid],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            logger.info("WINDOW_WATCHER extension info: %s", info)
        except subprocess.CalledProcessError as exc:
            logger.info(
                "WINDOW_WATCHER extension enable failed: %s output=%s",
                exc,
                exc.output,
            )
            self._try_shell_reexec(uuid)
        except Exception as exc:
            logger.info("WINDOW_WATCHER extension enable failed: %s", exc)
            self._try_shell_reexec(uuid)

    def _try_shell_reexec(self, uuid: str) -> None:
        try:
            logger.info("WINDOW_WATCHER attempting GNOME Shell reexec")
            subprocess.check_output(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.gnome.Shell",
                    "--object-path",
                    "/org/gnome/Shell",
                    "--method",
                    "org.gnome.Shell.Eval",
                    "global.reexec_self()",
                ],
                stderr=subprocess.STDOUT,
                text=True,
            )
            logger.info("WINDOW_WATCHER GNOME Shell reexec requested")
        except subprocess.CalledProcessError as exc:
            logger.info(
                "WINDOW_WATCHER GNOME Shell reexec failed: %s output=%s",
                exc,
                exc.output,
            )
            return
        except Exception as exc:
            logger.info("WINDOW_WATCHER GNOME Shell reexec failed: %s", exc)
            return

        try:
            enabled = subprocess.check_output(
                ["gnome-extensions", "list", "--enabled"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            logger.info("WINDOW_WATCHER extensions enabled: %s", enabled)
            info = subprocess.check_output(
                ["gnome-extensions", "info", uuid],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            logger.info("WINDOW_WATCHER extension info: %s", info)
        except Exception as exc:
            logger.info("WINDOW_WATCHER extension post-reexec check failed: %s", exc)

    def _poll(self):
        self._ticks += 1
        self._log_debug_kv("tick", {"ticks": self._ticks, "mode": self._mode})
        # One-shot, global probe: run all methods and log everything.
        self._probe_dbus_names()
        self._probe_gnome_introspect()
        self._probe_portal_window_tracker()
        self._poll_wayland()
        self._poll_wayland_gnome_eval()
        self._poll_x11()
        self._poll_x11_xdotool_fallback()
        self._poll_x11_wmctrl_fallback()
        self._probe_sway()
        self._probe_kwin()
        return True

    def _probe_dbus_names(self):
        self._log_debug("dbus list names attempt")
        try:
            result = subprocess.check_output(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.freedesktop.DBus",
                    "--object-path",
                    "/org/freedesktop/DBus",
                    "--method",
                    "org.freedesktop.DBus.ListNames",
                ],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug_kv("dbus list names output", {"output": result})
            wanted = [
                "org.inputremapper.ActiveWindow",
                "org.gnome.Shell",
                "org.freedesktop.portal.Desktop",
                "org.kde.KWin",
            ]
            for name in wanted:
                self._log_debug_kv(
                    "dbus name present",
                    {"name": name, "present": name in result},
                )
        except FileNotFoundError:
            self._log_debug("dbus list names: gdbus not found")
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "dbus list names error",
                {"error": exc, "output": exc.output},
            )
        except Exception as exc:
            self._log_debug_kv("dbus list names error", {"error": exc})

    def _probe_gnome_introspect(self):
        self._log_debug("gnome introspect attempt")
        try:
            result = subprocess.check_output(
                [
                    "gdbus",
                    "introspect",
                    "--session",
                    "--dest",
                    "org.gnome.Shell.Introspect",
                    "--object-path",
                    "/org/gnome/Shell/Introspect",
                ],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug_kv("gnome introspect", {"output": result})
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "gnome introspect error",
                {"error": exc, "output": exc.output},
            )
            return
        except FileNotFoundError:
            self._log_debug("gnome introspect: gdbus not found")
            return
        except Exception as exc:
            self._log_debug_kv("gnome introspect error", {"error": exc})
            return

        # Try common methods; log output/errors for each.
        methods = [
            "GetWindows",
            "GetRunningApplications",
            "GetWindow",
            "GetActiveWindow",
        ]
        for method in methods:
            try:
                output = subprocess.check_output(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        "org.gnome.Shell.Introspect",
                        "--object-path",
                        "/org/gnome/Shell/Introspect",
                        "--method",
                        f"org.gnome.Shell.Introspect.{method}",
                    ],
                    stderr=subprocess.STDOUT,
                    text=True,
                ).strip()
                self._log_debug_kv(
                    "gnome introspect call",
                    {"method": method, "output": output},
                )
            except subprocess.CalledProcessError as exc:
                self._log_debug_kv(
                    "gnome introspect call error",
                    {"method": method, "error": exc, "output": exc.output},
                )
            except Exception as exc:
                self._log_debug_kv(
                    "gnome introspect call error",
                    {"method": method, "error": exc},
                )

    def _probe_portal_window_tracker(self):
        self._log_debug("portal window tracker attempt")
        try:
            result = subprocess.check_output(
                [
                    "gdbus",
                    "introspect",
                    "--session",
                    "--dest",
                    "org.freedesktop.portal.Desktop",
                    "--object-path",
                    "/org/freedesktop/portal/desktop",
                ],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug_kv("portal introspect", {"output": result})
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "portal introspect error",
                {"error": exc, "output": exc.output},
            )
            return
        except FileNotFoundError:
            self._log_debug("portal introspect: gdbus not found")
            return
        except Exception as exc:
            self._log_debug_kv("portal introspect error", {"error": exc})
            return

        methods = [
            "GetActiveWindow",
            "GetFocusedWindow",
            "GetFocus",
            "GetWindows",
        ]
        for method in methods:
            try:
                output = subprocess.check_output(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        "org.freedesktop.portal.Desktop",
                        "--object-path",
                        "/org/freedesktop/portal/desktop",
                        "--method",
                        f"org.freedesktop.portal.WindowTracker.{method}",
                    ],
                    stderr=subprocess.STDOUT,
                    text=True,
                ).strip()
                self._log_debug_kv(
                    "portal window tracker call",
                    {"method": method, "output": output},
                )
            except subprocess.CalledProcessError as exc:
                self._log_debug_kv(
                    "portal window tracker call error",
                    {"method": method, "error": exc, "output": exc.output},
                )
            except Exception as exc:
                self._log_debug_kv(
                    "portal window tracker call error",
                    {"method": method, "error": exc},
                )

    def _probe_sway(self):
        self._log_debug("sway get_tree attempt")
        try:
            result = subprocess.check_output(
                ["swaymsg", "-t", "get_tree"],
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._log_debug_kv(
                "sway get_tree output",
                {"len": len(result), "head": result[:500]},
            )
        except FileNotFoundError:
            self._log_debug("sway get_tree: swaymsg not found")
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "sway get_tree error",
                {"error": exc, "output": exc.output},
            )
        except Exception as exc:
            self._log_debug_kv("sway get_tree error", {"error": exc})

    def _probe_kwin(self):
        self._log_debug("kwin activeWindow attempt")
        try:
            result = subprocess.check_output(
                ["qdbus", "org.kde.KWin", "/KWin", "org.kde.KWin.activeWindow"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug_kv("kwin activeWindow output", {"output": result})
        except FileNotFoundError:
            self._log_debug("kwin activeWindow: qdbus not found")
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "kwin activeWindow error",
                {"error": exc, "output": exc.output},
            )
        except Exception as exc:
            self._log_debug_kv("kwin activeWindow error", {"error": exc})

    def _poll_x11(self):
        self._log_debug("x11 gdk attempt")
        display = Gdk.Display.get_default()
        screen = Gdk.Screen.get_default()
        if not display or not screen:
            self._log_debug_kv(
                "x11 gdk no display/screen",
                {"display": display, "screen": screen},
            )
            return True

        window = screen.get_active_window()
        if window is None:
            self._log_debug("x11 gdk no active window")
            return True

        title = window.get_title() or ""
        wm_class = window.get_wm_class() or ("", "")
        xid = None
        if hasattr(window, "get_xid"):
            try:
                xid = window.get_xid()
            except Exception:
                xid = None

        current = (title, wm_class, xid)
        self._log_debug_kv(
            "x11 gdk values",
            {
                "title": title,
                "wm_class": wm_class,
                "xid": xid,
                "current": current,
                "last": self._last,
            },
        )
        if current != self._last:
            self._last = current
            logger.info(
                "WINDOW_WATCHER change title=%s wm_class=%s xid=%s",
                title,
                wm_class,
                xid,
            )
        elif self._ticks % 10 == 0:
            logger.info(
                "WINDOW_WATCHER heartbeat title=%s wm_class=%s xid=%s",
                title,
                wm_class,
                xid,
            )

        return True

    def _poll_x11_xdotool_fallback(self):
        self._log_debug("x11 xdotool attempt")
        try:
            xid = subprocess.check_output(
                ["xdotool", "getactivewindow"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            if not xid:
                self._log_debug("x11 xdotool no xid")
                return True

            title = subprocess.check_output(
                ["xdotool", "getwindowname", xid],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            try:
                wm_class = subprocess.check_output(
                    ["xdotool", "getwindowclassname", xid],
                    stderr=subprocess.STDOUT,
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                wm_class = ""

            current = (title, wm_class, xid)
            self._log_debug_kv(
                "x11 xdotool values",
                {
                    "title": title,
                    "wm_class": wm_class,
                    "xid": xid,
                    "current": current,
                    "last": self._last,
                },
            )
            if current != self._last:
                self._last = current
                logger.info(
                    "WINDOW_WATCHER change title=%s wm_class=%s xid=%s (xdotool)",
                    title,
                    wm_class,
                    xid,
                )
            elif self._ticks % 10 == 0:
                logger.info(
                    "WINDOW_WATCHER heartbeat title=%s wm_class=%s xid=%s (xdotool)",
                    title,
                    wm_class,
                    xid,
                )
        except FileNotFoundError:
            self._log_debug("x11 xdotool not found")
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "x11 xdotool error",
                {"error": exc, "output": exc.output},
            )
        except Exception as exc:
            self._log_debug_kv("x11 xdotool error", {"error": exc})

        return True

    def _poll_x11_wmctrl_fallback(self):
        self._log_debug("x11 wmctrl attempt")
        try:
            active = subprocess.check_output(
                ["wmctrl", "-lpG"],
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._log_debug_kv("x11 wmctrl raw", {"output": active.strip()})
        except FileNotFoundError:
            self._log_debug("x11 wmctrl not found")
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "x11 wmctrl error",
                {"error": exc, "output": exc.output},
            )
        except Exception as exc:
            self._log_debug_kv("x11 wmctrl error", {"error": exc})
        return True

    def _poll_wayland_gnome_eval(self):
        if self._mode != "wayland":
            return True
        self._log_debug("wayland gnome-shell eval attempt")
        try:
            result = subprocess.check_output(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.gnome.Shell",
                    "--object-path",
                    "/org/gnome/Shell",
                    "--method",
                    "org.gnome.Shell.Eval",
                    "JSON.stringify({"
                    "title:(global.display.get_focus_window()&&global.display.get_focus_window().get_title&&global.display.get_focus_window().get_title())||'',"
                    "wm_class:(global.display.get_focus_window()&&global.display.get_focus_window().get_wm_class&&global.display.get_focus_window().get_wm_class())||'',"
                    "app_id:(global.display.get_focus_window()&&global.display.get_focus_window().get_gtk_application_id&&global.display.get_focus_window().get_gtk_application_id())||'',"
                    "pid:(global.display.get_focus_window()&&global.display.get_focus_window().get_pid&&global.display.get_focus_window().get_pid())||0"
                    "})",
                ],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
            self._log_debug_kv("wayland gnome-shell eval output", {"output": result})
        except FileNotFoundError:
            self._log_debug("wayland gdbus not found")
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "wayland gnome-shell eval error",
                {"error": exc, "output": exc.output},
            )
        except Exception as exc:
            self._log_debug_kv("wayland gnome-shell eval error", {"error": exc})
        return True

    def _poll_wayland(self):
        self._log_debug("wayland extension gdbus attempt")
        try:
            result = subprocess.check_output(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.inputremapper.ActiveWindow",
                    "--object-path",
                    "/org/inputremapper/ActiveWindow",
                    "--method",
                    "org.inputremapper.ActiveWindow.GetActiveWindow",
                ],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
        except subprocess.CalledProcessError as exc:
            self._log_debug_kv(
                "wayland gdbus error",
                {"error": exc, "output": exc.output},
            )
            return True
        except Exception as exc:
            self._log_debug_kv("wayland gdbus error", {"error": exc})
            return True

        match = re.match(r"^\('(.*)'\)$", result)
        if not match:
            self._log_debug_kv("wayland gdbus output", {"output": result})
            return True

        payload_str = match.group(1).encode("utf-8").decode("unicode_escape")
        if not payload_str or payload_str == "{}":
            self._log_debug_kv(
                "wayland no active window",
                {"payload": payload_str},
            )
            return True

        try:
            data = json.loads(payload_str)
        except Exception:
            self._log_debug_kv("wayland bad json", {"payload": payload_str})
            return True

        title = data.get("title", "")
        wm_class = data.get("wm_class", "")
        app_id = data.get("app_id", "")
        pid = data.get("pid", 0)

        current = (title, wm_class, app_id, pid)
        self._log_debug_kv(
            "wayland gdbus values",
            {
                "title": title,
                "wm_class": wm_class,
                "app_id": app_id,
                "pid": pid,
                "current": current,
                "last": self._last,
                "raw": payload_str,
            },
        )
        if current != self._last:
            self._last = current
            logger.info(
                "WINDOW_WATCHER change title=%s wm_class=%s app_id=%s pid=%s",
                title,
                wm_class,
                app_id,
                pid,
            )
        elif self._ticks % 10 == 0:
            logger.info(
                "WINDOW_WATCHER heartbeat title=%s wm_class=%s app_id=%s pid=%s",
                title,
                wm_class,
                app_id,
                pid,
            )

        return True


class SteamProcessWatcher:
    """Scan running processes and attempt to detect Steam games."""

    def __init__(self):
        self._ticks = 0
        self._last = None
        self._games = get_steam_installed_game_paths()
        self._paths = []
        self._name_by_appid = {}
        for appid, name, path in self._games:
            self._paths.append((os.path.normpath(path), appid, name))
            self._name_by_appid[appid] = name
        # Longest paths first to reduce false positives.
        self._paths.sort(key=lambda item: len(item[0]), reverse=True)
        self._log_debug_kv(
            "init games",
            {"count": len(self._games), "games": self._games},
        )
        GLib.timeout_add(1000, self._poll)

    def _log_debug(self, message: str, *args):
        logger.info("GAME_WATCHER_DEBUG " + message, *args)

    def _log_debug_kv(self, label: str, mapping: dict):
        try:
            parts = []
            for key, value in mapping.items():
                parts.append(f"{key}={value!r}")
            logger.info("GAME_WATCHER_DEBUG %s %s", label, " ".join(parts))
        except Exception as exc:
            logger.info("GAME_WATCHER_DEBUG %s failed: %s", label, exc)

    def _poll(self):
        self._ticks += 1
        self._log_debug_kv("tick", {"ticks": self._ticks})
        hits = []
        steam_pids = []
        for pid in self._list_pids():
            info = self._inspect_pid(pid)
            if info.get("steam_client"):
                steam_pids.append(pid)
            if info.get("matches"):
                hits.append(info)
                self._log_debug_kv("proc match", info)
        self._log_debug_kv(
            "summary",
            {
                "steam_client_pids": steam_pids,
                "match_count": len(hits),
                "matches": hits,
            },
        )
        current_appids = sorted({match["appid"] for match in hits if match.get("appid")})
        if current_appids != self._last:
            self._last = current_appids
            logger.info("GAME_WATCHER change appids=%s", current_appids)
        return True

    def _list_pids(self):
        try:
            for entry in os.listdir("/proc"):
                if entry.isdigit():
                    yield int(entry)
        except Exception as exc:
            self._log_debug_kv("proc list error", {"error": exc})

    def _inspect_pid(self, pid: int) -> dict:
        exe = self._safe_readlink(f"/proc/{pid}/exe")
        cwd = self._safe_readlink(f"/proc/{pid}/cwd")
        cmdline = self._safe_read_cmdline(f"/proc/{pid}/cmdline")
        env = self._safe_read_environ(f"/proc/{pid}/environ")
        matches = []

        steam_client = False
        cmd_text = " ".join(cmdline)
        if cmdline and (
            "steam" in cmdline[0].lower()
            or "steam" in cmd_text.lower()
            or "pressure-vessel" in cmd_text.lower()
            or "reaper" in cmd_text.lower()
        ):
            steam_client = True

        appid_env = self._get_env_appid(env)
        if appid_env:
            matches.append(("env", appid_env))

        compat_appid = self._get_compat_appid(env)
        if compat_appid:
            matches.append(("compat", compat_appid))

        cmd_appid = self._get_cmd_appid(cmdline)
        if cmd_appid:
            matches.append(("cmdline", cmd_appid))

        path_appid = self._match_path_appid(exe, cwd, cmd_text)
        if path_appid:
            matches.append(("path", path_appid))

        appid = None
        if matches:
            appid = matches[0][1]

        info = {
            "pid": pid,
            "exe": exe,
            "cwd": cwd,
            "cmdline": cmdline,
            "env": env,
            "env_steam": {k: v for k, v in env.items() if "STEAM" in k or "Steam" in k},
            "steam_client": steam_client,
            "matches": matches,
            "appid": appid,
            "name": self._name_by_appid.get(appid, ""),
        }

        if steam_client and not matches:
            self._log_debug_kv("steam proc", info)

        return info

    def _safe_readlink(self, path: str):
        try:
            return os.readlink(path)
        except Exception:
            return ""

    def _safe_read_cmdline(self, path: str):
        try:
            with open(path, "rb") as handle:
                raw = handle.read().split(b"\0")
            return [item.decode("utf-8", "ignore") for item in raw if item]
        except Exception:
            return []

    def _safe_read_environ(self, path: str):
        try:
            with open(path, "rb") as handle:
                raw = handle.read().split(b"\0")
            env = {}
            for item in raw:
                if b"=" not in item:
                    continue
                key, value = item.split(b"=", 1)
                env[key.decode("utf-8", "ignore")] = value.decode("utf-8", "ignore")
            return env
        except Exception:
            return {}

    def _get_env_appid(self, env: dict) -> str:
        keys = ["SteamAppId", "SteamAppID", "STEAM_APP_ID", "SteamGameId"]
        for key in keys:
            value = env.get(key)
            if value and value.isdigit():
                return value
        return ""

    def _get_compat_appid(self, env: dict) -> str:
        for key in ["STEAM_COMPAT_APP_ID", "STEAM_COMPAT_DATA_PATH"]:
            value = env.get(key, "")
            if value.isdigit():
                return value
            match = re.search(r"compatdata[\\/](\d+)", value)
            if match:
                return match.group(1)
        return ""

    def _get_cmd_appid(self, cmdline: list) -> str:
        text = " ".join(cmdline)
        patterns = [
            r"SteamAppId[=:\s]+(\d+)",
            r"STEAM_APP_ID[=:\s]+(\d+)",
            r"steam_appid[=:\s]+(\d+)",
            r"-steamappid[=:\s]+(\d+)",
            r"-steamAppId[=:\s]+(\d+)",
            r"--appid[=:\s]+(\d+)",
            r"-appid[=:\s]+(\d+)",
            r"--app-id[=:\s]+(\d+)",
            r"-app-id[=:\s]+(\d+)",
            r"-gameid[=:\s]+(\d+)",
            r"-gameId[=:\s]+(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                if len(value) > 10:
                    try:
                        return str(int(value) & 0xFFFFFFFF)
                    except Exception:
                        return value
                return value
        return ""

    def _match_path_appid(self, exe: str, cwd: str, cmd_text: str) -> str:
        for base, appid, _name in self._paths:
            if exe and exe.startswith(base):
                return appid
            if cwd and cwd.startswith(base):
                return appid
            if cmd_text and base in cmd_text:
                return appid
        return ""


class ReleaseCombinationSwitch:
    """The switch used to set the active_mapping.release_combination_keys parameter."""

    def __init__(
        self, message_broker: MessageBroker, controller: Controller, switch: Gtk.Switch
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = switch

        self._gui.connect("state-set", self._on_gtk_toggle)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_changed)

    def _on_mapping_changed(self, data: MappingData):
        with HandlerDisabled(self._gui, self._on_gtk_toggle):
            self._gui.set_active(data.release_combination_keys)

    def _on_gtk_toggle(self, *_):
        self._controller.update_mapping(release_combination_keys=self._gui.get_active())


class InputConfigEntry(Gtk.ListBoxRow):
    """The ListBoxRow representing a single input config inside the CombinationListBox."""

    __gtype_name__ = "InputConfigEntry"

    def __init__(self, event: InputConfig, controller: Controller):
        super().__init__()

        self.input_event = event
        self._controller = controller

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hbox.set_margin_start(12)

        label = Gtk.Label()
        label.set_label(event.description())
        hbox.pack_start(label, False, False, 0)

        up_btn = Gtk.Button()
        up_btn.set_halign(Gtk.Align.END)
        up_btn.set_relief(Gtk.ReliefStyle.NONE)
        up_btn.get_style_context().add_class("no-v-padding")
        up_img = Gtk.Image.new_from_icon_name("go-up", Gtk.IconSize.BUTTON)
        up_btn.add(up_img)

        down_btn = Gtk.Button()
        down_btn.set_halign(Gtk.Align.END)
        down_btn.set_relief(Gtk.ReliefStyle.NONE)
        down_btn.get_style_context().add_class("no-v-padding")
        down_img = Gtk.Image.new_from_icon_name("go-down", Gtk.IconSize.BUTTON)
        down_btn.add(down_img)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.pack_start(up_btn, False, True, 0)
        vbox.pack_end(down_btn, False, True, 0)
        hbox.pack_end(vbox, False, False, 0)

        up_btn.connect(
            "clicked",
            lambda *_: self._controller.move_input_config_in_combination(
                self.input_event, "up"
            ),
        )
        down_btn.connect(
            "clicked",
            lambda *_: self._controller.move_input_config_in_combination(
                self.input_event, "down"
            ),
        )
        self.add(hbox)
        self.show_all()

        # only used in testing
        self._up_btn = up_btn
        self._down_btn = down_btn


class CombinationListbox:
    """The ListBox with all the events inside active_mapping.input_combination."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        listbox: Gtk.ListBox,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = listbox
        self._combination: Optional[InputCombination] = None

        self._message_broker.subscribe(
            MessageType.mapping,
            self._on_mapping_changed,
        )
        self._message_broker.subscribe(
            MessageType.selected_event,
            self._on_event_changed,
        )

        self._gui.connect("row-selected", self._on_gtk_row_selected)

    def _select_row(self, event: InputEvent):
        for row in self._gui.get_children():
            if row.input_event == event:
                self._gui.select_row(row)

    def _on_mapping_changed(self, mapping: MappingData):
        if self._combination == mapping.input_combination:
            return

        event_entries = self._gui.get_children()
        for event_entry in event_entries:
            self._gui.remove(event_entry)

        if self._controller.is_empty_mapping():
            self._combination = None
        else:
            self._combination = mapping.input_combination
            for event in self._combination:
                self._gui.insert(InputConfigEntry(event, self._controller), -1)

    def _on_event_changed(self, event: InputEvent):
        with HandlerDisabled(self._gui, self._on_gtk_row_selected):
            self._select_row(event)

    def _on_gtk_row_selected(self, *_):
        for row in self._gui.get_children():
            if row.is_selected():
                self._controller.load_input_config(row.input_event)
                break


class AnalogInputSwitch:
    """The switch that marks the active_input_config as analog input."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.Switch,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui
        self._input_config: Optional[InputConfig] = None

        self._gui.connect("state-set", self._on_gtk_toggle)
        self._message_broker.subscribe(MessageType.selected_event, self._on_event)

    def _on_event(self, input_cfg: InputConfig):
        with HandlerDisabled(self._gui, self._on_gtk_toggle):
            self._gui.set_active(input_cfg.defines_analog_input)
            self._input_config = input_cfg

        if input_cfg.type == EV_KEY:
            self._gui.set_sensitive(False)
            self._gui.set_opacity(0.5)
        else:
            self._gui.set_sensitive(True)
            self._gui.set_opacity(1)

    def _on_gtk_toggle(self, *_):
        self._controller.set_event_as_analog(self._gui.get_active())


class TriggerThresholdInput:
    """The number selection used to set the speed or position threshold of the
    active_input_config when it is an ABS or REL event used as a key."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.SpinButton,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui
        self._input_config: Optional[InputConfig] = None

        self._gui.set_increments(1, 1)
        self._gui.connect("value-changed", self._on_gtk_changed)
        self._message_broker.subscribe(MessageType.selected_event, self._on_event)

    def _on_event(self, input_config: InputConfig):
        if input_config.type == EV_KEY:
            self._gui.set_sensitive(False)
            self._gui.set_opacity(0.5)
        elif input_config.type == EV_ABS:
            self._gui.set_sensitive(True)
            self._gui.set_opacity(1)
            self._gui.set_range(-99, 99)
        else:
            self._gui.set_sensitive(True)
            self._gui.set_opacity(1)
            self._gui.set_range(-999, 999)

        with HandlerDisabled(self._gui, self._on_gtk_changed):
            self._gui.set_value(input_config.analog_threshold or 0)
            self._input_config = input_config

    def _on_gtk_changed(self, *_):
        self._controller.update_input_config(
            self._input_config.modify(analog_threshold=int(self._gui.get_value()))
        )


class ReleaseTimeoutInput:
    """The number selector used to set the active_mapping.release_timeout parameter."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.SpinButton,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui

        self._gui.set_increments(0.01, 0.01)
        self._gui.set_range(0, 2)
        self._gui.connect("value-changed", self._on_gtk_changed)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_message)

    def _on_mapping_message(self, mapping: MappingData):
        if EV_REL in [event.type for event in mapping.input_combination]:
            self._gui.set_sensitive(True)
            self._gui.set_opacity(1)
        else:
            self._gui.set_sensitive(False)
            self._gui.set_opacity(0.5)

        with HandlerDisabled(self._gui, self._on_gtk_changed):
            self._gui.set_value(mapping.release_timeout)

    def _on_gtk_changed(self, *_):
        self._controller.update_mapping(release_timeout=self._gui.get_value())


class RelativeInputCutoffInput:
    """The number selector to set active_mapping.rel_to_abs_input_cutoff."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.SpinButton,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui

        self._gui.set_increments(1, 1)
        self._gui.set_range(1, 1000)
        self._gui.connect("value-changed", self._on_gtk_changed)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_message)

    def _on_mapping_message(self, mapping: MappingData):
        if (
            EV_REL in [event.type for event in mapping.input_combination]
            and mapping.output_type == EV_ABS
        ):
            self._gui.set_sensitive(True)
            self._gui.set_opacity(1)
        else:
            self._gui.set_sensitive(False)
            self._gui.set_opacity(0.5)

        with HandlerDisabled(self._gui, self._on_gtk_changed):
            self._gui.set_value(mapping.rel_to_abs_input_cutoff)

    def _on_gtk_changed(self, *_):
        self._controller.update_mapping(rel_xy_cutoff=self._gui.get_value())


class OutputAxisSelector:
    """The dropdown menu used to select the output axis if the active_mapping is a
    mapping targeting an analog axis

    modifies the active_mapping.output_code and active_mapping.output_type parameters
    """

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.ComboBox,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui
        self._uinputs: Dict[str, Capabilities] = {}
        self.model = Gtk.ListStore(str, str)

        self._current_target: Optional[str] = None

        self._gui.set_model(self.model)
        renderer_text = Gtk.CellRendererText()
        self._gui.pack_start(renderer_text, False)
        self._gui.add_attribute(renderer_text, "text", 1)
        self._gui.set_id_column(0)

        self._gui.connect("changed", self._on_gtk_select_axis)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_message)
        self._message_broker.subscribe(MessageType.uinputs, self._on_uinputs_message)

    def _set_model(self, target: Optional[str]):
        if target == self._current_target:
            return

        self.model.clear()
        self.model.append(["None, None", _("No Axis")])

        if target is not None:
            capabilities = self._uinputs.get(target) or defaultdict(list)
            types_codes = [
                (EV_ABS, code) for code, absinfo in capabilities.get(EV_ABS) or ()
            ]
            types_codes.extend(
                (EV_REL, code) for code in capabilities.get(EV_REL) or ()
            )
            for type_, code in types_codes:
                key_name = get_evdev_constant_name(type_, code)
                if isinstance(key_name, list):
                    key_name = key_name[0]
                self.model.append([f"{type_}, {code}", key_name])

        self._current_target = target

    def _on_mapping_message(self, mapping: MappingData):
        with HandlerDisabled(self._gui, self._on_gtk_select_axis):
            self._set_model(mapping.target_uinput)
            self._gui.set_active_id(f"{mapping.output_type}, {mapping.output_code}")

    def _on_uinputs_message(self, uinputs: UInputsData):
        self._uinputs = uinputs.uinputs

    def _on_gtk_select_axis(self, *_):
        if self._gui.get_active_id() == "None, None":
            type_code = (None, None)
        else:
            type_code = tuple(int(i) for i in self._gui.get_active_id().split(","))
        self._controller.update_mapping(
            output_type=type_code[0], output_code=type_code[1]
        )


class KeyAxisStackSwitcher:
    """The controls used to switch between the gui to modify a key-mapping or
    an analog-axis mapping."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        stack: Gtk.Stack,
        key_macro_toggle: Gtk.ToggleButton,
        analog_toggle: Gtk.ToggleButton,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._stack = stack
        self._key_macro_toggle = key_macro_toggle
        self._analog_toggle = analog_toggle

        self._key_macro_toggle.connect("toggled", self._on_gtk_toggle)
        self._analog_toggle.connect("toggled", self._on_gtk_toggle)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_message)

    def _set_active(self, mapping_type: Literal["key_macro", "analog"]):
        if mapping_type == MappingType.ANALOG.value:
            self._stack.set_visible_child_name(OutputTypeNames.analog_axis)
            active = self._analog_toggle
            inactive = self._key_macro_toggle
        else:
            self._stack.set_visible_child_name(OutputTypeNames.key_or_macro)
            active = self._key_macro_toggle
            inactive = self._analog_toggle

        with HandlerDisabled(active, self._on_gtk_toggle):
            active.set_active(True)
        with HandlerDisabled(inactive, self._on_gtk_toggle):
            inactive.set_active(False)

    def _on_mapping_message(self, mapping: MappingData):
        # fist check the actual mapping
        if mapping.mapping_type == MappingType.ANALOG.value:
            self._set_active(MappingType.ANALOG.value)

        if mapping.mapping_type == MappingType.KEY_MACRO.value:
            self._set_active(MappingType.KEY_MACRO.value)

    def _on_gtk_toggle(self, btn: Gtk.ToggleButton):
        # get_active returns the new toggle state already
        was_active = not btn.get_active()

        if was_active:
            # cannot deactivate manually
            with HandlerDisabled(btn, self._on_gtk_toggle):
                btn.set_active(True)
            return

        if btn is self._key_macro_toggle:
            self._controller.update_mapping(mapping_type=MappingType.KEY_MACRO.value)
        else:
            self._controller.update_mapping(mapping_type=MappingType.ANALOG.value)


class TransformationDrawArea:
    """The graph which shows the relation between input- and output-axis."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gui: Gtk.DrawingArea,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gui = gui

        self._transformation: Callable[[Union[float, int]], float] = lambda x: x

        self._gui.connect("draw", self._on_gtk_draw)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_message)

    def _on_mapping_message(self, mapping: MappingData):
        self._transformation = Transformation(
            100, -100, mapping.deadzone, mapping.gain, mapping.expo
        )
        self._gui.queue_draw()

    def _on_gtk_draw(self, _, context: cairo.Context):
        points = [
            (x / 200 + 0.5, -0.5 * self._transformation(x) + 0.5)
            # leave some space left and right for the lineCap to be visible
            for x in range(-97, 97)
        ]
        width = self._gui.get_allocated_width()
        height = self._gui.get_allocated_height()
        b = min((width, height))
        scaled_points = [(x * b, y * b) for x, y in points]

        # x arrow
        context.move_to(0 * b, 0.5 * b)
        context.line_to(1 * b, 0.5 * b)
        context.line_to(0.96 * b, 0.52 * b)
        context.move_to(1 * b, 0.5 * b)
        context.line_to(0.96 * b, 0.48 * b)

        # y arrow
        context.move_to(0.5 * b, 1 * b)
        context.line_to(0.5 * b, 0)
        context.line_to(0.48 * b, 0.04 * b)
        context.move_to(0.5 * b, 0)
        context.line_to(0.52 * b, 0.04 * b)

        context.set_line_width(2)
        arrow_color = Gdk.RGBA(0.5, 0.5, 0.5, 0.2)
        context.set_source_rgba(
            arrow_color.red,
            arrow_color.green,
            arrow_color.blue,
            arrow_color.alpha,
        )
        context.stroke()

        # graph
        context.move_to(*scaled_points[0])
        for scaled_point in scaled_points[1:]:
            # Ploting point
            context.line_to(*scaled_point)

        line_color = Colors.get_accent_color()
        context.set_line_width(3)
        context.set_line_cap(cairo.LineCap.ROUND)
        # the default gtk adwaita highlight color:
        context.set_source_rgba(
            line_color.red,
            line_color.green,
            line_color.blue,
            line_color.alpha,
        )
        context.stroke()


class Sliders:
    """The different sliders to modify the gain, deadzone and expo parameters of the
    active_mapping."""

    def __init__(
        self,
        message_broker: MessageBroker,
        controller: Controller,
        gain: Gtk.Range,
        deadzone: Gtk.Range,
        expo: Gtk.Range,
    ):
        self._message_broker = message_broker
        self._controller = controller
        self._gain = gain
        self._deadzone = deadzone
        self._expo = expo

        self._gain.set_range(-2, 2)
        self._deadzone.set_range(0, 0.9)
        self._expo.set_range(-1, 1)

        self._gain.connect("value-changed", self._on_gtk_gain_changed)
        self._expo.connect("value-changed", self._on_gtk_expo_changed)
        self._deadzone.connect("value-changed", self._on_gtk_deadzone_changed)
        self._message_broker.subscribe(MessageType.mapping, self._on_mapping_message)

    def _on_mapping_message(self, mapping: MappingData):
        with HandlerDisabled(self._gain, self._on_gtk_gain_changed):
            self._gain.set_value(mapping.gain)

        with HandlerDisabled(self._expo, self._on_gtk_expo_changed):
            self._expo.set_value(mapping.expo)

        with HandlerDisabled(self._deadzone, self._on_gtk_deadzone_changed):
            self._deadzone.set_value(mapping.deadzone)

    def _on_gtk_gain_changed(self, *_):
        self._controller.update_mapping(gain=self._gain.get_value())

    def _on_gtk_deadzone_changed(self, *_):
        self._controller.update_mapping(deadzone=self._deadzone.get_value())

    def _on_gtk_expo_changed(self, *_):
        self._controller.update_mapping(expo=self._expo.get_value())
