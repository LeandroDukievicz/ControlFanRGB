"""Backends que a GUI e o CLI usam.

Dois, com a mesma API:

* `DaemonBackend` — fala D-Bus com o `controlfanrgbd`. É o caminho normal.
* `LocalBackend` — toca o hardware direto. Serve para desenvolvimento e para
  quem só clonou o repositório e rodou `python3 run.py` sem instalar nada.

`get_backend()` escolhe sozinho. Assim a janela não sabe (nem precisa saber)
se existe um daemon rodando.
"""
import gi

from gi.repository import Gio, GLib  # noqa: E402

from . import effects, themes
from .daemon import BUS_NAME, OBJ_PATH
from .hardware import Keyboard, KeyboardUnavailable, Sensors, Turbo


class DaemonBackend:
    kind = "daemon"

    def __init__(self, proxy):
        self._proxy = proxy
        self._sensors = Sensors()          # leitura é livre, não precisa do bus

    @classmethod
    def try_connect(cls):
        try:
            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None,
                BUS_NAME, OBJ_PATH, BUS_NAME, None)
            if proxy.get_name_owner() is None:
                return None
            proxy.call_sync("GetStatus", None, Gio.DBusCallFlags.NONE, 2000, None)
            return cls(proxy)
        except GLib.Error:
            return None

    def _call(self, method, variant=None, reply="()"):
        return self._proxy.call_sync(method, variant, Gio.DBusCallFlags.NONE,
                                     5000, None)

    def status(self):
        res = self._call("GetStatus").unpack()[0]
        return {k: v for k, v in res.items()}

    def set_zones(self, colors, brightness):
        self._call("SetZones", GLib.Variant(
            "(a(uuu)u)", ([tuple(c) for c in colors], brightness)))

    def set_firmware_effect(self, mode, speed, brightness, direction, color):
        self._call("SetFirmwareEffect", GLib.Variant(
            "(uuuu(uuu))", (mode, speed, brightness, direction, tuple(color))))

    def apply_theme(self, name):
        self._call("ApplyTheme", GLib.Variant("(s)", (name,)))

    def start_effect(self, name):
        self._call("StartEffect", GLib.Variant("(s)", (name,)))

    def stop_effect(self):
        self._call("StopEffect")

    def set_brightness(self, value):
        self._call("SetBrightness", GLib.Variant("(u)", (value,)))

    def off(self):
        self._call("Off")

    def set_turbo(self, on):
        self._call("SetTurbo", GLib.Variant("(b)", (on,)))

    def toggle_turbo(self):
        return self._call("ToggleTurbo").unpack()[0]

    def close(self):
        pass


class LocalBackend:
    """Mesma API, sem daemon — escreve direto nos /dev."""
    kind = "local"

    def __init__(self):
        self.kb = Keyboard()
        self.sensors = Sensors()
        self.engine = effects.Engine(self.kb, self.sensors)
        self._classes = {cls().nome: cls for cls in effects.SOFTWARE_EFFECTS}
        self._effect = ""
        self._brightness = 100
        self._zones = [(255, 45, 111), (177, 74, 237), (79, 124, 255),
                       (45, 226, 255)]
        self._mode = "zones"
        self._fw = (3, 5, 1, (45, 226, 255))

    def status(self):
        fans = self.sensors.fans() or (0, 0)
        return {
            "mode": self._mode,
            "brightness": self._brightness,
            "effect": self._effect,
            "firmware_mode": self._fw[0],
            "zones": self._zones,
            "turbo": bool(Turbo.get()),
            "turbo_available": Turbo.available() and Turbo.writable(),
            "fan_cpu": fans[0],
            "fan_gpu": fans[1],
            "cpu_temp": self.sensors.cpu_temp() or 0.0,
        }

    def set_zones(self, colors, brightness):
        self.engine.stop()
        self._effect, self._mode = "", "zones"
        self._zones, self._brightness = list(colors), brightness
        self.kb.set_zones(colors, brightness)

    def set_firmware_effect(self, mode, speed, brightness, direction, color):
        self.engine.stop()
        self._effect, self._mode = "", "firmware"
        self._fw = (mode, speed, direction, color)
        self._brightness = brightness
        self.kb.set_effect(mode, speed, brightness, direction, color)

    def apply_theme(self, name):
        self.set_zones(themes.THEMES[name], self._brightness)

    def start_effect(self, name):
        self.engine.start(self._classes[name](), self._brightness)
        self._effect, self._mode = name, "software"

    def stop_effect(self):
        self.engine.stop()
        self._effect, self._mode = "", "zones"
        self.kb.set_zones(self._zones, self._brightness)

    def set_brightness(self, value):
        self._brightness = value
        if self.engine.running:
            self.engine.start(self._classes[self._effect](), value)
        elif self._mode == "firmware":
            mode, speed, direction, color = self._fw
            self.kb.set_effect(mode, speed, value, direction, color)
        else:
            self.kb.set_zones(self._zones, value)

    def off(self):
        self.engine.stop()
        self.kb.off()

    def set_turbo(self, on):
        Turbo.set(on)

    def toggle_turbo(self):
        return Turbo.toggle()

    def close(self):
        self.engine.stop()
        self.kb.close()


def get_backend(prefer_daemon=True):
    if prefer_daemon:
        backend = DaemonBackend.try_connect()
        if backend is not None:
            return backend
    return LocalBackend()
