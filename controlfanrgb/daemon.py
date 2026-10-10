"""controlfanrgbd — serviço de sistema dono do hardware.

Por que existe:

* **Dono único dos devices.** Enquanto a GUI falava direto com `/dev`, qualquer
  segundo processo (um efeito rodando, um CLI) disputava o mesmo recurso — e
  chegou a travar a troca do módulo de kernel por "device in use".
* **Os efeitos por software sobrevivem à janela fechada.** O motor roda aqui.
* **Boot e resume.** Reaplica o perfil ao subir e ao acordar do suspend,
  substituindo o `acer-rgb.service` + `acer-rgb-resume.service` antigos.
* **É o que torna Flatpak/Snap viáveis.** A GUI vira só um cliente de D-Bus;
  nada confinado precisa tocar em `/dev`.

Fala no barramento de sistema em `io.github.leandrodukievicz.ControlFanRGB1`.
"""
import json
import os
import signal
import sys

import gi

from gi.repository import Gio, GLib  # noqa: E402

from . import effects, themes, validation
from .hardware import (BacklightTimeout, Keyboard, KeyboardUnavailable,
                       Sensors, Turbo)

BUS_NAME = "io.github.leandrodukievicz.ControlFanRGB1"
OBJ_PATH = "/io/github/leandrodukievicz/ControlFanRGB1"
STATE_DIR = "/var/lib/controlfanrgb"
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
    # Apagar o teclado quando a sessão fica inativa. Falso por padrão para não
    # mudar o comportamento de quem já usava o app.
    "idle_blank": False,
    "idle_timeout": 120,              # segundos
    # Deixar o firmware apagar o teclado sozinho depois de ~30 s. Falso por
    # padrão: quem instala este app quer que o app decida isso, e a opção da
    # sessão (idle_blank) faz o mesmo trabalho de forma configurável.
    "firmware_timeout": False,
}

INTROSPECTION = """
<node>
  <interface name="io.github.leandrodukievicz.ControlFanRGB1">
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
    <method name="SetIdleBlank">
      <arg type="b" name="enabled" direction="in"/>
      <arg type="u" name="timeout" direction="in"/>
    </method>
    <method name="SetFirmwareTimeout">
      <arg type="b" name="enabled" direction="in"/>
    </method>
    <method name="SetIdleState">
      <arg type="b" name="idle" direction="in"/>
    </method>
    <method name="SetAudioLevel">
      <arg type="d" name="level" direction="in"/>
      <arg type="ad" name="bands" direction="in"/>
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
    <signal name="EffectChanged">
      <arg type="s" name="name"/>
    </signal>
  </interface>
</node>
"""


class Daemon:
    def __init__(self):
        self.kb = Keyboard()
        self.sensors = Sensors()
        self.state = _load_state()
        self.engine = effects.Engine(self.kb, self.sensors,
                                     on_error=self._on_engine_error)
        self._effects = {cls().nome: cls for cls in effects.SOFTWARE_EFFECTS}
        self._last_fans = None
        self._last_turbo = None
        self._idle_active = False      # apagado por inatividade agora mesmo
        self._powered = True           # Off é temporário; o perfil fica salvo
        self._conn = None
        self._save_timer = 0
        self.loop = GLib.MainLoop()

    # ------------------------------------------------------------- D-Bus ---
    def run(self):
        Gio.bus_own_name(Gio.BusType.SYSTEM, BUS_NAME,
                         Gio.BusNameOwnerFlags.NONE,
                         self._on_bus_acquired, None, self._on_name_lost)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._quit)

        GLib.timeout_add_seconds(POLL_SECONDS, self._poll)
        # O sysfs do firmware nasce junto com o device da plataforma, que o
        # módulo cria de forma assíncrona — mesma corrida dos /dev. Uma
        # tentativa por segundo até aparecer, no máximo dez.
        self._firmware_tries = 0
        GLib.timeout_add_seconds(1, self._try_firmware_timeout)
        GLib.idle_add(self._apply_state)
        self.loop.run()

    def _on_bus_acquired(self, conn, _name):
        self._conn = conn
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        # register_object_with_closures2, e não register_object: a primeira é
        # depreciada no PyGObject e **vaza** a cada chamada recebida. Medido
        # num serviço mínimo, sem nada deste projeto, a 22 chamadas/s:
        #   register_object               +1921 B por chamada
        #   register_object_with_closures2   +66 B por chamada
        # Com o efeito Música, que envia 22 SetAudioLevel/s, a diferença era
        # o daemon crescer ~2,4 MB por minuto sem parar.
        conn.register_object_with_closures2(
            OBJ_PATH, node.interfaces[0], self._on_call, None, None)
        # acordar do suspend derruba o backlight: o logind nos avisa
        conn.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Manager",
            "PrepareForSleep", "/org/freedesktop/login1", None,
            Gio.DBusSignalFlags.NONE, self._on_sleep, None)
        _log(f"no barramento como {BUS_NAME}")

    def _on_name_lost(self, _conn, _name):
        _log("não consegui o nome no barramento — já existe outro controlfanrgbd?")
        self._quit()

    def _on_sleep(self, _c, _s, _p, _i, _sig, params, _u):
        going_to_sleep = params.unpack()[0]
        if not going_to_sleep:                       # acordando
            GLib.timeout_add(1200, self._apply_state)
            # O firmware pode voltar ao padrão ao religar; é idempotente, só
            # escreve se tiver divergido.
            GLib.timeout_add(1500, self._apply_firmware_timeout)

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
            colors = validation.zones(colors)
            brightness = validation.integer(brightness, 0, 100)
            self.engine.stop()
            self._powered = True
            self.state.update(mode="zones", software_effect="",
                              zones=colors, brightness=brightness)
            self._apply_state()

        elif method == "SetFirmwareEffect":
            mode, speed, brightness, direction, color = args
            mode = validation.integer(mode, 0, 5)
            speed = validation.integer(speed, 0, 9)
            brightness = validation.integer(brightness, 0, 100)
            direction = validation.integer(direction, 1, 2)
            color = validation.color(color)
            self.engine.stop()
            self._powered = True
            self.state.update(mode="firmware", software_effect="",
                              firmware_mode=mode, speed=speed,
                              brightness=brightness,
                              direction=direction, color=color)
            self._apply_state()

        elif method == "ApplyTheme":
            name = themes.resolve(args[0])
            if name not in themes.THEMES:
                raise ValueError(f"tema desconhecido: {name}")
            self.engine.stop()
            self._powered = True
            self.state.update(mode="zones", software_effect="",
                              zones=[list(c) for c in themes.THEMES[name]])
            self._apply_state()

        elif method == "StartEffect":
            name = args[0]
            if name not in self._effects:
                raise ValueError(f"efeito desconhecido: {name}")
            self.state.update(mode="software", software_effect=name)
            self._powered = True
            self.engine.start(self._effects[name](), self.state["brightness"])
            _save_state(self.state)
            self._emit("EffectChanged", GLib.Variant("(s)", (name,)))

        elif method == "StopEffect":
            self.engine.stop()
            self._powered = True
            self.state.update(mode="zones", software_effect="")
            self._apply_state()
            self._emit("EffectChanged", GLib.Variant("(s)", ("",)))

        elif method == "SetBrightness":
            self.state["brightness"] = validation.integer(args[0], 0, 100)
            if self._powered:
                if self.engine.running:
                    self.engine.set_brightness(self.state["brightness"])
                else:
                    self._apply_state(persist=False)
            self._queue_save()

        elif method == "Off":
            self.engine.stop()
            self.kb.off()
            self._powered = False

        elif method == "ApplyProfile":
            self._powered = True
            self._apply_state()

        elif method == "SetTurbo":
            Turbo.set(bool(args[0]))
            self._poll_turbo(force=True)

        elif method == "ToggleTurbo":
            new = Turbo.toggle()
            self._poll_turbo(force=True)
            return GLib.Variant("(b)", (new,))

        elif method == "SetIdleBlank":
            enabled = bool(args[0])
            timeout = validation.integer(args[1], 15, 86400)
            self.state.update(idle_blank=enabled, idle_timeout=timeout)
            if not enabled and self._idle_active:
                # desligou a opção estando apagado: acende de volta na hora
                self._idle_active = False
                self._apply_state()
            else:
                _save_state(self.state)

        elif method == "SetFirmwareTimeout":
            self.state["firmware_timeout"] = bool(args[0])
            self._apply_firmware_timeout()
            _save_state(self.state)

        elif method == "SetIdleState":
            self._set_idle(bool(args[0]))

        elif method == "SetAudioLevel":
            effects.AUDIO.push(*validation.audio(args[0], args[1]))

        elif method == "GetStatus":
            return GLib.Variant("(a{sv})", (self._status(),))

        else:
            raise ValueError(f"método desconhecido: {method}")
        return None

    def _try_firmware_timeout(self):
        self._firmware_tries += 1
        if BacklightTimeout.available():
            self._apply_firmware_timeout()
            return False
        if self._firmware_tries >= 10:
            _log("o módulo não expõe backlight_timeout — precisa do facer 1.2+")
            return False
        return True

    def _on_engine_error(self, erro):
        """A thread do efeito morreu. Chamado da thread dela, não da loop."""
        _log(f"motor de efeitos parou: {erro!r}")

    # -------------------------------------------------------- inatividade ---
    def _set_idle(self, idle):
        """Apaga ou reacende por inatividade da sessão.

        Quem detecta a inatividade é o tray, via `org.gnome.Mutter.IdleMonitor`
        — é informação de sessão, e o daemon é de sistema. Aqui só se age.

        Apagar para o motor de efeitos em vez de só escrever preto: um efeito
        rodando sobrescreveria o apagado 30 vezes por segundo. Reacender passa
        por `_apply_state`, que religa o efeito de onde parou.
        """
        if idle == self._idle_active:
            return
        if idle:
            if not self.state.get("idle_blank"):
                return
            self._idle_active = True
            self.engine.stop()
            try:
                self.kb.off()
            except (KeyboardUnavailable, OSError) as e:
                _log(f"não consegui apagar na inatividade: {e}")
        else:
            self._idle_active = False
            if self._powered:
                self._apply_state()

    # ------------------------------------------------- timeout do firmware ---
    def _apply_firmware_timeout(self):
        """Alinha o timeout de backlight do firmware com a preferência.

        Separado de `_apply_state` de propósito. Aplicar perfil acontece a
        cada troca de cor; isto é uma chamada WMI ao firmware e não tem por
        que repetir a cada quadro ou a cada tema. Lê antes e só escreve se
        divergir.

        Degrada em silêncio se o atributo não existir: num kernel sem o módulo
        compilado, ou com o facer original, o resto do app continua inteiro.
        """
        if not BacklightTimeout.available():
            return False

        desejado = bool(self.state.get("firmware_timeout"))
        atual = BacklightTimeout.get()
        if atual is None or atual == desejado:
            return False

        try:
            BacklightTimeout.set(desejado)
        except KeyboardUnavailable as e:
            _log(f"não consegui ajustar o timeout de backlight: {e}")
            return False

        _log(f"timeout de backlight do firmware: "
             f"{'ligado' if desejado else 'desligado'}")
        return True

    # ------------------------------------------------------------- estado ---
    def _apply_state(self, attempt=0, persist=True):
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
        if self._idle_active or not self._powered:
            # Apagado por inatividade. Sem esta guarda, o poll do resume ou um
            # ApplyProfile reacenderia o teclado com a sessão ainda parada.
            return False
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
        if persist:
            _save_state(st)
        return False            # idle_add/timeout_add: não repetir

    def _queue_save(self):
        if self._save_timer:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(350, self._flush_state)

    def _flush_state(self):
        self._save_timer = 0
        _save_state(self.state)
        return GLib.SOURCE_REMOVE

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
            "powered": GLib.Variant("b", self._powered),
            "effect": GLib.Variant("s", self.state["software_effect"]),
            "firmware_mode": GLib.Variant("u", self.state["firmware_mode"]),
            "speed": GLib.Variant("u", self.state["speed"]),
            "direction": GLib.Variant("u", self.state["direction"]),
            "color": GLib.Variant("(uuu)", tuple(self.state["color"])),
            "zones": GLib.Variant("a(uuu)",
                                  [tuple(c) for c in self.state["zones"]]),
            "turbo": GLib.Variant("b", bool(turbo)),
            "turbo_available": GLib.Variant("b", Turbo.available()),
            "fan_cpu": GLib.Variant("u", fans[0]),
            "fan_gpu": GLib.Variant("u", fans[1]),
            "cpu_temp": GLib.Variant("d", temp),
            "idle_blank": GLib.Variant("b", bool(self.state.get("idle_blank"))),
            "idle_timeout": GLib.Variant(
                "u", int(self.state.get("idle_timeout", 120))),
            "idle_active": GLib.Variant("b", self._idle_active),
            # Diferença importante para diagnóstico: `effect` é o que o estado
            # diz que deveria estar rodando; `engine_running` é se a thread
            # está de fato viva. Divergência entre os dois é o bug.
            "firmware_timeout": GLib.Variant(
                "b", bool(self.state.get("firmware_timeout"))),
            "firmware_timeout_available": GLib.Variant(
                "b", BacklightTimeout.available()),
            "engine_running": GLib.Variant("b", self.engine.running),
            "engine_error": GLib.Variant(
                "s", self.engine.last_error or ""),
            "audio_fresh": GLib.Variant("b", effects.AUDIO.fresh),
            "audio_level": GLib.Variant("d", effects.AUDIO.level),
            "audio_bands": GLib.Variant("ad", list(effects.AUDIO.bands)),
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
        if self._save_timer:
            GLib.source_remove(self._save_timer)
            self._flush_state()
        self.engine.stop()
        self.kb.close()
        self.loop.quit()
        return GLib.SOURCE_REMOVE


# ---------------------------------------------------------------- estado ----
def _load_state():
    try:
        with open(STATE_PATH) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    return validation.normalize_state(
        raw, DEFAULT_STATE, {cls.nome for cls in effects.SOFTWARE_EFFECTS})


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
    print(f"controlfanrgbd: {msg}", file=sys.stderr, flush=True)


def main():
    if not Keyboard.available():
        _log("devices do teclado ausentes — o módulo facer está carregado?")
    Daemon().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
