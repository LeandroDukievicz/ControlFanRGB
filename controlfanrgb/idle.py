"""Observa a inatividade da sessão, para apagar o teclado sem uso.

Usa `org.gnome.Mutter.IdleMonitor`. Esse é o caminho porque no Wayland um
cliente comum **não vê** eventos de entrada que não sejam para as suas
próprias janelas — contar teclas dentro do app é impossível por design. O
logind tem `IdleHint`, mas no GNOME ele não acompanha atividade de teclado e
mouse, então serve para sessão remota e não para isto.

Como o IdleMonitor é de sessão, isto roda no tray e o resultado vai ao daemon
por D-Bus. O daemon, sendo de sistema, não tem como saber se você está
digitando.
"""
import gi

from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.gnome.Mutter.IdleMonitor"
PATH = "/org/gnome/Mutter/IdleMonitor/Core"


class IdleWatcher:
    """Chama `on_change(idle: bool)` quando a sessão para e quando volta.

    Nunca levanta: se o IdleMonitor não existir (sessão que não é GNOME),
    `start()` devolve False e o resto do app segue funcionando sem a função.
    """

    def __init__(self, on_change, timeout=120):
        self._on_change = on_change
        self._timeout = max(15, int(timeout))
        self._proxy = None
        self._idle_watch = None
        self._active_watch = None
        self._sub = None
        self.idle = False
        self.last_error = None

    # ---------------------------------------------------------------------
    def start(self):
        if self._proxy is not None:
            return True
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None, BUS, PATH, BUS, None)
            if self._proxy.get_name_owner() is None:
                raise GLib.Error.new_literal(
                    Gio.DBusError.quark(), "sem dono no barramento", 0)
        except GLib.Error as e:
            self._proxy = None
            self.last_error = e.message
            return False

        self._sub = self._proxy.connect("g-signal", self._on_signal)
        self._arm_idle()
        return True

    def stop(self):
        self._drop(self._idle_watch)
        self._drop(self._active_watch)
        self._idle_watch = self._active_watch = None
        if self._proxy is not None and self._sub is not None:
            self._proxy.disconnect(self._sub)
        self._sub = None
        self.idle = False

    def set_timeout(self, seconds):
        seconds = max(15, int(seconds))
        if seconds == self._timeout:
            return
        self._timeout = seconds
        if self._proxy is not None and not self.idle:
            self._drop(self._idle_watch)
            self._arm_idle()

    @property
    def available(self):
        return self._proxy is not None

    # ---------------------------------------------------------------------
    def _call(self, method, variant, reply):
        try:
            return self._proxy.call_sync(method, variant,
                                         Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error as e:
            self.last_error = e.message
            return None

    def _arm_idle(self):
        res = self._call("AddIdleWatch",
                         GLib.Variant("(t)", (self._timeout * 1000,)), "(u)")
        self._idle_watch = res.unpack()[0] if res is not None else None

    def _arm_active(self):
        res = self._call("AddUserActiveWatch", None, "(u)")
        self._active_watch = res.unpack()[0] if res is not None else None

    def _drop(self, watch_id):
        if watch_id is not None and self._proxy is not None:
            self._call("RemoveWatch", GLib.Variant("(u)", (watch_id,)), "()")

    def _on_signal(self, _proxy, _sender, signal_name, params):
        if signal_name != "WatchFired":
            return
        fired = params.unpack()[0]

        if fired == self._idle_watch:
            self._idle_watch = None
            self.idle = True
            self._on_change(True)
            # Um watch de usuário-ativo dispara uma vez e se remove sozinho;
            # é como o Mutter avisa que você voltou.
            self._arm_active()

        elif fired == self._active_watch:
            self._active_watch = None
            self.idle = False
            self._on_change(False)
            self._arm_idle()
