"""pulsedeckd — serviço de sistema dono do hardware.

Por que existe:

* **Dono único dos devices.** Enquanto a GUI falava direto com `/dev`, qualquer
  segundo processo (um efeito rodando, um CLI) disputava o mesmo recurso — e
  chegou a travar a troca do módulo de kernel por "device in use".
* **Os efeitos por software sobrevivem à janela fechada.** O motor roda aqui.
* **Boot e resume.** Reaplica o perfil ao subir e ao acordar do suspend,
  substituindo o `acer-rgb.service` + `acer-rgb-resume.service` antigos.
* **É o que torna Flatpak/Snap viáveis.** A GUI vira só um cliente de D-Bus;
  nada confinado precisa tocar em `/dev`.

Fala no barramento de sistema em `io.github.leandrodukievicz.PulseDeck1`.
"""
import json
import os
import signal
import sys

import gi

from gi.repository import Gio, GLib  # noqa: E402

from . import effects, themes
from .hardware import Keyboard, KeyboardUnavailable, Sensors, Turbo

BUS_NAME = "io.github.leandrodukievicz.PulseDeck1"
OBJ_PATH = "/io/github/leandrodukievicz/PulseDeck1"
STATE_DIR = "/var/lib/pulsedeck"
STATE_PATH = os.path.join(STATE_DIR, "state.json")
POLL_SECONDS = 2
MAX_APPLY_RETRIES = 30      # ~15 s esperando o módulo criar os /dev

DEFAULT_STATE = {
    "mode": "zones",                  # zones | firmware | software
    "zones": [[255, 45, 111], [177, 74, 237], [79, 124, 255], [45, 226, 255]],
    "brightness": 100,
    "firmware_mode": 3,
    "speed": 5,
    "direction": 1,
    "color": [45, 226, 255],
    "software_effect": "",
}

INTROSPECTION = """
<node>
  <interface name="io.github.leandrodukievicz.PulseDeck1">
    <method name="SetZones">
      <arg type="a(uuu)" name="colors" direction="in"/>
      <arg type="u" name="brightness" direction="in"/>
    </method>
    <method name="SetFirmwareEffect">
      <arg type="u" name="mode" direction="in"/>
      <arg type="u" name="speed" direction="in"/>
      <arg type="u" name="brightness" direction="in"/>
      <arg type="u" name="direction" direction="in"/>
      <arg type="(uuu)" name="color" direction="in"/>
    </method>
    <method name="ApplyTheme">
      <arg type="s" name="name" direction="in"/>
    </method>
    <method name="StartEffect">
      <arg type="s" name="name" direction="in"/>
    </method>
    <method name="StopEffect"/>
    <method name="Off"/>
    <method name="ApplyProfile"/>
    <method name="SetBrightness">
      <arg type="u" name="value" direction="in"/>
    </method>
    <method name="SetTurbo">
      <arg type="b" name="on" direction="in"/>
    </method>
    <method name="ToggleTurbo">
      <arg type="b" name="state" direction="out"/>
    </method>
    <method name="GetStatus">
      <arg type="a{sv}" name="status" direction="out"/>
    </method>
    <signal name="TurboChanged">
      <arg type="b" name="on"/>
    </signal>
    <signal name="FansChanged">
      <arg type="u" name="cpu"/>
      <arg type="u" name="gpu"/>
    </signal>
  </interface>
</node>
"""


class Daemon:
    def __init__(self):
        self.kb = Keyboard()
        self.sensors = Sensors()
        self.state = _load_state()
        self.engine = effects.Engine(self.kb, self.sensors)
        self._effects = {cls().nome: cls for cls in effects.SOFTWARE_EFFECTS}
        self._last_fans = None
        self._last_turbo = None
        self._conn = None
        self.loop = GLib.MainLoop()

    # ------------------------------------------------------------- D-Bus ---
    def run(self):
        Gio.bus_own_name(Gio.BusType.SYSTEM, BUS_NAME,
                         Gio.BusNameOwnerFlags.NONE,
                         self._on_bus_acquired, None, self._on_name_lost)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._quit)

        GLib.timeout_add_seconds(POLL_SECONDS, self._poll)
        GLib.idle_add(self._apply_state)
        self.loop.run()

    def _on_bus_acquired(self, conn, _name):
        self._conn = conn
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        conn.register_object(OBJ_PATH, node.interfaces[0], self._on_call,
                             None, None)
        # acordar do suspend derruba o backlight: o logind nos avisa
        conn.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Manager",
            "PrepareForSleep", "/org/freedesktop/login1", None,
            Gio.DBusSignalFlags.NONE, self._on_sleep, None)
        _log(f"no barramento como {BUS_NAME}")

    def _on_name_lost(self, _conn, _name):
        _log("não consegui o nome no barramento — já existe outro pulsedeckd?")
        self._quit()

    def _on_sleep(self, _c, _s, _p, _i, _sig, params, _u):
        going_to_sleep = params.unpack()[0]
        if not going_to_sleep:                       # acordando
            GLib.timeout_add(1200, self._apply_state)

    def _on_call(self, _conn, _sender, _path, _iface, method, params, inv):
        try:
            result = self._dispatch(method, params.unpack())
        except KeyboardUnavailable as e:
            inv.return_dbus_error(BUS_NAME + ".Error.Hardware", str(e))
            return
        except Exception as e:                       # noqa: BLE001
            inv.return_dbus_error(BUS_NAME + ".Error.Failed", repr(e))
            return
        inv.return_value(result)

    def _dispatch(self, method, args):
        if method == "SetZones":
            colors, brightness = args
            self.engine.stop()
            self.state.update(mode="zones", software_effect="",
                              zones=[list(c) for c in colors],
                              brightness=int(brightness))
            self._apply_state()

        elif method == "SetFirmwareEffect":
            mode, speed, brightness, direction, color = args
            self.engine.stop()
            self.state.update(mode="firmware", software_effect="",
                              firmware_mode=int(mode), speed=int(speed),
                              brightness=int(brightness),
                              direction=int(direction), color=list(color))
            self._apply_state()

        elif method == "ApplyTheme":
            name = args[0]
            if name not in themes.THEMES:
                raise ValueError(f"tema desconhecido: {name}")
            self.engine.stop()
            self.state.update(mode="zones", software_effect="",
                              zones=[list(c) for c in themes.THEMES[name]])
            self._apply_state()

        elif method == "StartEffect":
            name = args[0]
            if name not in self._effects:
                raise ValueError(f"efeito desconhecido: {name}")
            self.state.update(mode="software", software_effect=name)
            self.engine.start(self._effects[name](), self.state["brightness"])
            _save_state(self.state)

        elif method == "StopEffect":
            self.engine.stop()
            self.state.update(mode="zones", software_effect="")
            self._apply_state()

        elif method == "SetBrightness":
            self.state["brightness"] = int(args[0])
            if self.engine.running:                  # reinicia com o novo brilho
                name = self.state["software_effect"]
                self.engine.start(self._effects[name](), self.state["brightness"])
                _save_state(self.state)
            else:
                self._apply_state()

        elif method == "Off":
            self.engine.stop()
            self.kb.off()

        elif method == "ApplyProfile":
            self._apply_state()

        elif method == "SetTurbo":
            Turbo.set(bool(args[0]))
            self._poll_turbo(force=True)

        elif method == "ToggleTurbo":
            new = Turbo.toggle()
            self._poll_turbo(force=True)
            return GLib.Variant("(b)", (new,))

        elif method == "GetStatus":
            return GLib.Variant("(a{sv})", (self._status(),))

        else:
            raise ValueError(f"método desconhecido: {method}")
        return None

    # ------------------------------------------------------------- estado ---
    def _apply_state(self, attempt=0):
        """Aplica o perfil, insistindo enquanto o hardware não estiver pronto.

        O módulo facer cria /dev/acer-gkbbl-* de forma **assíncrona**: no boot
        o modprobe do ExecStartPre volta antes dos devices existirem. Sem a
        reentativa, a primeira aplicação falha e o teclado fica apagado até
        alguém mexer. (O script acer-rgb original esperava por isso num laço
        de até 5 s — mesmo motivo.)

        Também cobre o caso de o módulo ser recarregado: os fds antigos ficam
        inválidos, então fechamos antes de tentar de novo.
        """
        st = self.state
        if not Keyboard.available():
            return self._retry(attempt, "devices do teclado ainda não existem")
        try:
            if st["mode"] == "software" and st["software_effect"]:
                name = st["software_effect"]
                if name in self._effects:
                    self.engine.start(self._effects[name](), st["brightness"])
            elif st["mode"] == "firmware":
                self.kb.set_effect(st["firmware_mode"], st["speed"],
                                   st["brightness"], st["direction"],
                                   tuple(st["color"]))
            else:
                self.kb.set_zones([tuple(c) for c in st["zones"]],
                                  st["brightness"])
        except (KeyboardUnavailable, OSError) as e:
            return self._retry(attempt, str(e))

        if attempt:
            _log(f"perfil aplicado na tentativa {attempt + 1}")
        _save_state(st)
        return False            # idle_add/timeout_add: não repetir

    def _retry(self, attempt, why):
        self.kb.close()                       # fds podem ter ficado inválidos
        if attempt == 0:
            _log(f"{why} — tentando de novo")
        if attempt < MAX_APPLY_RETRIES:
            GLib.timeout_add(500, self._apply_state, attempt + 1)
        else:
            _log(f"desisti de aplicar o perfil: {why}")
        return False

    def _status(self):
        fans = self.sensors.fans() or (0, 0)
        temp = self.sensors.cpu_temp() or 0.0
        turbo = Turbo.get()
        return {
            "mode": GLib.Variant("s", self.state["mode"]),
            "brightness": GLib.Variant("u", self.state["brightness"]),
            "effect": GLib.Variant("s", self.state["software_effect"]),
            "firmware_mode": GLib.Variant("u", self.state["firmware_mode"]),
            "zones": GLib.Variant("a(uuu)",
                                  [tuple(c) for c in self.state["zones"]]),
            "turbo": GLib.Variant("b", bool(turbo)),
            "turbo_available": GLib.Variant("b", Turbo.available()),
            "fan_cpu": GLib.Variant("u", fans[0]),
            "fan_gpu": GLib.Variant("u", fans[1]),
            "cpu_temp": GLib.Variant("d", temp),
        }

    # -------------------------------------------------------------- loop ----
    def _poll(self):
        fans = self.sensors.fans()
        if fans and fans != self._last_fans:
            self._last_fans = fans
            self._emit("FansChanged", GLib.Variant("(uu)", fans))
        self._poll_turbo()
        return True

    def _poll_turbo(self, force=False):
        turbo = Turbo.get()
        if turbo is not None and (force or turbo != self._last_turbo):
            self._last_turbo = turbo
            self._emit("TurboChanged", GLib.Variant("(b)", (turbo,)))

    def _emit(self, name, params):
        if self._conn is None:
            return
        self._conn.emit_signal(None, OBJ_PATH, BUS_NAME, name, params)

    def _quit(self, *_a):
        _log("encerrando")
        self.engine.stop()
        self.kb.close()
        self.loop.quit()
        return GLib.SOURCE_REMOVE


# ---------------------------------------------------------------- estado ----
def _load_state():
    st = dict(DEFAULT_STATE)
    try:
        with open(STATE_PATH) as f:
            st.update(json.load(f))
    except (OSError, ValueError):
        pass
    return st


def _save_state(st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except OSError as e:
        _log(f"não consegui salvar o estado: {e}")


def _log(msg):
    print(f"pulsedeckd: {msg}", file=sys.stderr, flush=True)


def main():
    if not Keyboard.available():
        _log("devices do teclado ausentes — o módulo facer está carregado?")
    Daemon().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
