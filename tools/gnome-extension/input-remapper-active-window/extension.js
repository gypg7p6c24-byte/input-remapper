import Gio from 'gi://Gio';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const IFACE_XML = `<node>
  <interface name="org.inputremapper.ActiveWindow">
    <method name="GetActiveWindow">
      <arg type="s" direction="out" name="json"/>
    </method>
  </interface>
</node>`;

class ActiveWindowService {
  GetActiveWindow() {
    let win = null;
    try {
      win = global.display.get_focus_window();
    } catch (e) {
      win = null;
    }

    if (!win) {
      return JSON.stringify({});
    }

    const title = win.get_title ? win.get_title() : "";
    const wmClass = win.get_wm_class ? win.get_wm_class() : "";
    const appId = win.get_gtk_application_id ? win.get_gtk_application_id() : "";
    const pid = win.get_pid ? win.get_pid() : 0;

    return JSON.stringify({
      title: title,
      wm_class: wmClass,
      app_id: appId,
      pid: pid,
    });
  }
}

export default class InputRemapperActiveWindowExtension extends Extension {
  enable() {
    try {
      this._service = new ActiveWindowService();
      this._exported = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this._service);
      this._exported.export(Gio.DBus.session, "/org/inputremapper/ActiveWindow");
      this._nameId = Gio.bus_own_name(
        Gio.BusType.SESSION,
        "org.inputremapper.ActiveWindow",
        Gio.BusNameOwnerFlags.NONE,
        null,
        null
      );
    } catch (e) {
      logError(e, "input-remapper-active-window enable failed");
    }
  }

  disable() {
    try {
      if (this._exported) {
        this._exported.unexport();
        this._exported = null;
      }
      if (this._nameId) {
        Gio.bus_unown_name(this._nameId);
        this._nameId = 0;
      }
      this._service = null;
    } catch (e) {
      logError(e, "input-remapper-active-window disable failed");
    }
  }
}
