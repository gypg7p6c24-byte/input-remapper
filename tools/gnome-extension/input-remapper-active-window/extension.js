const Gio = imports.gi.Gio;

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

let _service = null;
let _exported = null;
let _nameId = 0;

function init() {}

function enable() {
  _service = new ActiveWindowService();
  _exported = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, _service);
  _exported.export(Gio.DBus.session, "/org/inputremapper/ActiveWindow");

  _nameId = Gio.DBus.session.own_name(
    "org.inputremapper.ActiveWindow",
    Gio.BusNameOwnerFlags.NONE,
    null,
    null
  );
}

function disable() {
  if (_exported) {
    _exported.unexport();
    _exported = null;
  }
  if (_nameId) {
    Gio.DBus.session.unown_name(_nameId);
    _nameId = 0;
  }
  _service = null;
}
