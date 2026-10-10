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

    def apply_profile(self):
        self._call("ApplyProfile")

    def start_effect(self, name):
        self._call("StartEffect", GLib.Variant("(s)", (name,)))

    def stop_effect(self):
        self._call("StopEffect")

    def set_brightness(self, value):
        self._call("SetBrightness", GLib.Variant("(u)", (value,)))

    def off(self):
        self._call("Off")

    def set_idle_blank(self, enabled, timeout):
        self._call("SetIdleBlank", GLib.Variant("(bu)", (enabled, int(timeout))))

    def set_idle_state(self, idle):
        self._call("SetIdleState", GLib.Variant("(b)", (idle,)))

    def set_audio_level(self, level, bands):
        """Mensagem crua, sem resposta esperada.

        São ~22 por segundo: um `call_sync` bloquearia a loop do tray em cada
        quadro de áudio, e perder um quadro é inócuo — o próximo vem em 43 ms.

        Mas `proxy.call()` com callback None também não serve: ele registra
        uma chamada pendente que ninguém colhe. Medido, enviando a 22/s:

            proxy.call()                          +70 B por envio (+91 kB/min)
            send_message(NO_REPLY_EXPECTED)        +0 B por envio

        Era isso que fazia o tray crescer ~84 kB/min com o efeito de música.
        """
        msg = Gio.DBusMessage.new_method_call(
            BUS_NAME, OBJ_PATH, BUS_NAME, "SetAudioLevel")
        msg.set_flags(Gio.DBusMessageFlags.NO_REPLY_EXPECTED)
        msg.set_body(GLib.Variant(
            "(dad)", (float(level), [float(b) for b in bands])))
        self._proxy.get_connection().send_message(
            msg, Gio.DBusSendMessageFlags.NONE)

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
        self._idle_blank = False
        self._idle_timeout = 120
        self._idle_active = False
        self._powered = True

    def status(self):
        fans = self.sensors.fans() or (0, 0)
        return {
            "mode": self._mode,
            "brightness": self._brightness,
            "powered": self._powered,
            "effect": self._effect,
            "firmware_mode": self._fw[0],
            "speed": self._fw[1],
            "direction": self._fw[2],
            "color": self._fw[3],
            "zones": self._zones,
            "turbo": bool(Turbo.get()),
            "turbo_available": Turbo.available() and Turbo.writable(),
            "fan_cpu": fans[0],
            "fan_gpu": fans[1],
            "cpu_temp": self.sensors.cpu_temp() or 0.0,
            "idle_blank": self._idle_blank,
            "idle_timeout": self._idle_timeout,
            "idle_active": self._idle_active,
            "audio_fresh": effects.AUDIO.fresh,
            "audio_level": effects.AUDIO.level,
            "audio_bands": list(effects.AUDIO.bands),
        }

    def set_zones(self, colors, brightness):
        self.engine.stop()
        self._powered = True
        self._effect, self._mode = "", "zones"
        self._zones, self._brightness = list(colors), brightness
        self.kb.set_zones(colors, brightness)

    def set_firmware_effect(self, mode, speed, brightness, direction, color):
        self.engine.stop()
        self._powered = True
        self._effect, self._mode = "", "firmware"
        self._fw = (mode, speed, direction, color)
        self._brightness = brightness
        self.kb.set_effect(mode, speed, brightness, direction, color)

    def apply_theme(self, name):
        self.set_zones(themes.THEMES[themes.resolve(name)], self._brightness)

    def apply_profile(self):
        self._powered = True
        if self._mode == "software" and self._effect:
            self.engine.start(self._classes[self._effect](), self._brightness)
        elif self._mode == "firmware":
            self.kb.set_effect(*self._fw[:2], self._brightness,
                               self._fw[2], self._fw[3])
        else:
            self.kb.set_zones(self._zones, self._brightness)

    def start_effect(self, name):
        self._powered = True
        self.engine.start(self._classes[name](), self._brightness)
        self._effect, self._mode = name, "software"

    def stop_effect(self):
        self.engine.stop()
        self._powered = True
        self._effect, self._mode = "", "zones"
        self.kb.set_zones(self._zones, self._brightness)

    def set_brightness(self, value):
        self._brightness = value
        if not self._powered:
            return
        if self.engine.running:
            self.engine.set_brightness(value)
        elif self._mode == "firmware":
            mode, speed, direction, color = self._fw
            self.kb.set_effect(mode, speed, value, direction, color)
        else:
            self.kb.set_zones(self._zones, value)

    def off(self):
        self.engine.stop()
        self.kb.off()
        self._powered = False

    def set_idle_blank(self, enabled, timeout):
        self._idle_blank = bool(enabled)
        self._idle_timeout = max(15, int(timeout))
        if not self._idle_blank and self._idle_active:
            self.set_idle_state(False)

    def set_idle_state(self, idle):
        if idle == self._idle_active:
            return
        if idle:
            if not self._idle_blank:
                return
            self._idle_active = True
            self.engine.stop()
            self.kb.off()
        else:
            self._idle_active = False
            if self._powered:
                self.apply_profile()

    def set_audio_level(self, level, bands):
        effects.AUDIO.push(level, bands)

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
