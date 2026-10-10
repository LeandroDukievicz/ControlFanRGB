"""Ícone de bandeja (StatusNotifierItem), como processo próprio da sessão.

Por que não é um AppIndicator: o binding `AppIndicator3` é GTK-3 e o GObject
Introspection não deixa carregar Gtk 3.0 e Gtk 4.0 no mesmo processo. Então o
jeito certo num app GTK4 é falar o protocolo direto — `org.kde.StatusNotifierItem`
mais o menu em `com.canonical.dbusmenu`, ambos no barramento de sessão.

Por que é um processo separado da janela: um tray que morre quando você fecha
a janela não é um tray. Este fala com o `controlfanrgbd` pelo barramento de
sistema e sobrevive sozinho.
"""
import os
import signal
import sys

import gi

from gi.repository import Gio, GLib  # noqa: E402

from . import build_info, effects, themes
from .audio import Sampler
from .client import get_backend
from .idle import IdleWatcher

SNI_IFACE = "org.kde.StatusNotifierItem"
MENU_IFACE = "com.canonical.dbusmenu"
WATCHER_NAME = "org.kde.StatusNotifierWatcher"
SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
ICON = "io.github.leandrodukievicz.ControlFanRGB-symbolic"

SNI_XML = f"""
<node>
  <interface name="{SNI_IFACE}">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/><arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/><arg type="i" name="y" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/><arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg type="s" name="status"/></signal>
  </interface>
</node>
"""

MENU_XML = f"""
<node>
  <interface name="{MENU_IFACE}">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{{sv}}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{{sv}})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{{sv}})" name="updated"/>
      <arg type="a(ias)" name="removed"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/><arg type="i" name="parent"/>
    </signal>
  </interface>
</node>
"""


class Tray:
    def __init__(self):
        self.backend = get_backend()
        self.loop = GLib.MainLoop()
        self._conn = None
        self._revision = 1
        self._items = {}
        self._root = self._build_menu()
        self._index(self._root)

        # Partes que só um processo de sessão consegue fazer. O daemon é de
        # sistema: não vê o PipeWire do usuário nem sabe se ele está digitando.
        self._sampler = Sampler(self._on_audio)
        self._audio = None
        self._audio_timer = None
        self._idle = IdleWatcher(self._on_idle_change)
        self._idle_armed = False

        # Último status conhecido. Os getters de propriedade do D-Bus
        # respondem DAQUI e nunca fazem I/O — ver _sni_get.
        self._status = {}
        self._tooltip_text = "ControlFanRGB"

    # --------------------------------------------------------- modelo ------
    def _build_menu(self):
        next_id = iter(range(1, 500))

        def node(label=None, **props):
            item = {"id": next(next_id), "children": []}
            if label is not None:
                item["label"] = label
            item.update(props)
            return item

        root = {"id": 0, "children": []}
        add = root["children"].append

        self.item_turbo = node("Turbo", action="turbo",
                               **{"toggle-type": "checkmark", "toggle-state": 0})
        add(self.item_turbo)

        self.item_fans = node("Ventoinhas: —", enabled=False)
        add(self.item_fans)

        add(node(type="separator"))

        temas = node("Temas", **{"children-display": "submenu"})
        for name in themes.THEMES:
            temas["children"].append(node(name, action="theme", arg=name))
        add(temas)

        efeitos = node("Efeitos", **{"children-display": "submenu"})
        for cls in effects.SOFTWARE_EFFECTS:
            nome = cls().nome
            efeitos["children"].append(node(nome, action="effect", arg=nome))
        efeitos["children"].append(node(type="separator"))
        efeitos["children"].append(node("Parar efeito", action="stop"))
        add(efeitos)

        add(node(type="separator"))
        add(node("Apagar teclado", action="off"))
        add(node("Abrir ControlFanRGB…", action="open"))
        add(node(type="separator"))
        add(node("Sair do tray", action="quit"))
        return root

    def _index(self, item):
        self._items[item["id"]] = item
        for child in item.get("children", []):
            self._index(child)

    @staticmethod
    def _props(item, names=None):
        out = {}
        if item.get("type") == "separator":
            out["type"] = GLib.Variant("s", "separator")
            return out
        if "label" in item:
            out["label"] = GLib.Variant("s", item["label"])
        out["enabled"] = GLib.Variant("b", item.get("enabled", True))
        out["visible"] = GLib.Variant("b", item.get("visible", True))
        if "toggle-type" in item:
            out["toggle-type"] = GLib.Variant("s", item["toggle-type"])
            out["toggle-state"] = GLib.Variant("i", item.get("toggle-state", 0))
        if "children-display" in item:
            out["children-display"] = GLib.Variant("s", item["children-display"])
        if names:
            out = {k: v for k, v in out.items() if k in names}
        return out

    def _layout(self, item, depth, names):
        """Devolve a tupla (id, props, filhos) do dbusmenu.

        Tupla, não Variant: o struct aninhado é montado pelo format string de
        quem chama. Só os filhos vão como Variant, porque `av` exige isso.
        """
        children = []
        if depth != 0:
            for child in item.get("children", []):
                children.append(GLib.Variant(
                    "(ia{sv}av)", self._layout(child, depth - 1, names)))
        return (item["id"], self._props(item, names), children)

    # ---------------------------------------------------------- D-Bus ------
    def run(self):
        self._bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        Gio.bus_own_name(Gio.BusType.SESSION, self._bus_name,
                         Gio.BusNameOwnerFlags.NONE,
                         self._on_bus_acquired, None, self._on_name_lost)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._quit)
        GLib.timeout_add_seconds(2, self._refresh)
        GLib.idle_add(self._refresh_once)     # não espera os 2 s do primeiro poll
        self.loop.run()

    def _refresh_once(self):
        """Primeira atualização, fora do ritmo do timer.

        Precisa de um invólucro: `_refresh` devolve True para manter vivo o
        timeout de 2 s, e uma fonte *idle* que devolve True é reagendada
        imediatamente. Passar `_refresh` direto para `idle_add` transformava a
        atualização num laço ocupado — medido em 632 chamadas de GetStatus por
        segundo, com o daemon relendo sysfs em cada uma (70% de CPU) e o tray
        girando a 26%.
        """
        self._refresh()
        return GLib.SOURCE_REMOVE

    def _on_bus_acquired(self, conn, _name):
        self._conn = conn
        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        # register_object_with_closures2, e não register_object: a primeira é
        # depreciada no PyGObject e **vaza** a cada chamada recebida. Medido
        # num serviço mínimo, sem nada deste projeto, a 22 chamadas/s:
        #   register_object               +1921 B por chamada
        #   register_object_with_closures2   +66 B por chamada
        # Com o efeito Música, que envia 22 SetAudioLevel/s, a diferença era
        # o daemon crescer ~2,4 MB por minuto sem parar.
        conn.register_object_with_closures2(
            SNI_PATH, sni, self._sni_call, self._sni_get, None)
        conn.register_object_with_closures2(
            MENU_PATH, menu, self._menu_call, self._menu_get, None)
        conn.call(WATCHER_NAME, "/StatusNotifierWatcher", WATCHER_NAME,
                  "RegisterStatusNotifierItem",
                  GLib.Variant("(s)", (self._bus_name,)), None,
                  Gio.DBusCallFlags.NONE, 3000, None, self._on_registered)

    def _on_registered(self, conn, res):
        try:
            conn.call_finish(res)
            _log("registrado no StatusNotifierWatcher")
        except GLib.Error as e:
            _log(f"o watcher recusou o registro: {e.message}")

    def _on_name_lost(self, *_a):
        _log("perdi o nome no barramento")
        self._quit()

    # Propriedades constantes: montadas uma vez, não a cada consulta.
    _SNI_CONST = {
        "Category": GLib.Variant("s", "Hardware"),
        "Id": GLib.Variant("s", "controlfanrgb"),
        "Title": GLib.Variant("s", "ControlFanRGB"),
        "Status": GLib.Variant("s", "Active"),
        "WindowId": GLib.Variant("i", 0),
        "IconName": GLib.Variant("s", ICON),
        "IconThemePath": GLib.Variant("s", ""),
        "OverlayIconName": GLib.Variant("s", ""),
        "AttentionIconName": GLib.Variant("s", ""),
        "ItemIsMenu": GLib.Variant("b", True),
        "Menu": GLib.Variant("o", MENU_PATH),
    }

    def _sni_get(self, _c, _s, _p, _i, prop):
        """Responde da memória. **Nunca** faz I/O nem chamada D-Bus.

        O host do tray lê propriedades com muita frequência, e várias por
        atualização. A versão anterior montava o dicionário inteiro a cada
        consulta e, ao montar a entrada ToolTip, chamava backend.status() —
        uma chamada D-Bus *síncrona* ao daemon — mesmo quando o host havia
        pedido só "Category".

        Medido antes da correção: 690 GetStatus por segundo, daemon em 71% de
        CPU e ~1.900 openat/s em sysfs, porque cada GetStatus relê ventoinhas,
        temperatura e turbo. Pior, _refresh emitia NewToolTip a cada 2 s, o
        que fazia o host reler as propriedades e realimentar o ciclo.

        O tooltip agora vem de _tooltip_text, atualizado pelo _refresh.
        """
        const = self._SNI_CONST.get(prop)
        if const is not None:
            return const
        if prop == "ToolTip":
            return GLib.Variant("(sa(iiay)ss)",
                                (ICON, [], "ControlFanRGB", self._tooltip_text))
        return None

    def _menu_get(self, _c, _s, _p, _i, prop):
        return {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }.get(prop)

    def _sni_call(self, _c, _s, _p, _i, method, params, inv):
        if method == "Activate":
            _spawn_gui()
        elif method == "SecondaryActivate":
            self._safe(lambda: self.backend.toggle_turbo())
        elif method == "Scroll":
            delta = params.unpack()[0]
            self._scroll_brightness(delta)
        inv.return_value(None)

    def _menu_call(self, _c, _s, _p, _i, method, params, inv):
        args = params.unpack()
        if method == "GetLayout":
            parent, depth, names = args
            item = self._items.get(parent, self._root)
            inv.return_value(GLib.Variant(
                "(u(ia{sv}av))", (self._revision, self._layout(item, depth, names))))
        elif method == "GetGroupProperties":
            ids, names = args
            wanted = ids or list(self._items)
            inv.return_value(GLib.Variant("(a(ia{sv}))", ([
                (i, self._props(self._items[i], names))
                for i in wanted if i in self._items],)))
        elif method == "GetProperty":
            item_id, name = args
            props = self._props(self._items.get(item_id, {}))
            inv.return_value(GLib.Variant(
                "(v)", (props.get(name, GLib.Variant("s", "")),)))
        elif method == "Event":
            item_id, event_id = args[0], args[1]
            if event_id == "clicked":
                self._activate(item_id)
            inv.return_value(None)
        elif method == "AboutToShow":
            self._refresh()
            inv.return_value(GLib.Variant("(b)", (True,)))
        else:
            inv.return_value(None)

    # ---------------------------------------------------------- ações ------
    def _activate(self, item_id):
        item = self._items.get(item_id)
        if not item:
            return
        action, arg = item.get("action"), item.get("arg")
        if action == "turbo":
            self._safe(lambda: self.backend.toggle_turbo())
        elif action == "theme":
            self._safe(lambda: self.backend.apply_theme(arg))
        elif action == "effect":
            self._safe(lambda: self.backend.start_effect(arg))
        elif action == "stop":
            self._safe(lambda: self.backend.stop_effect())
        elif action == "off":
            self._safe(lambda: self.backend.off())
        elif action == "open":
            _spawn_gui()
        elif action == "quit":
            self._quit()
        GLib.timeout_add(600, self._refresh)

    def _scroll_brightness(self, delta):
        def go():
            st = self.backend.status()
            value = max(0, min(100, int(st["brightness"]) + (10 if delta > 0 else -10)))
            self.backend.set_brightness(value)
        self._safe(go)

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:                       # noqa: BLE001
            _log(f"falhou: {e}")

    # --------------------------------------------------------- refresh -----
    @staticmethod
    def _tooltip_from(st):
        """Texto do tooltip a partir de um status já em mãos — não consulta nada."""
        if not st:
            return "daemon indisponível"
        turbo = "turbo ligado" if st.get("turbo") else "turbo desligado"
        if st.get("fan_cpu"):
            return f"{turbo} · CPU {st['fan_cpu']} rpm · GPU {st['fan_gpu']} rpm"
        return turbo

    def _refresh(self):
        """Única fonte de I/O periódico do tray.

        Consulta o daemon uma vez e guarda o resultado em `self._status`.
        Todos os getters de propriedade leem desse snapshot, nunca do
        barramento — é isso que mantém o GetStatus em ~0,5/s em vez de 690/s.
        """
        try:
            st = self.backend.status()
        except Exception:                            # noqa: BLE001
            self._status = {}
            return True

        self._status = st
        changed = []
        turbo = 1 if st.get("turbo") else 0
        if self.item_turbo.get("toggle-state") != turbo:
            self.item_turbo["toggle-state"] = turbo
            changed.append(self.item_turbo)

        label = (f"Ventoinhas: {st['fan_cpu']} / {st['fan_gpu']} rpm"
                 if st.get("fan_cpu") else "Ventoinhas: indisponível")
        if self.item_fans.get("label") != label:
            self.item_fans["label"] = label
            changed.append(self.item_fans)

        self._sync_audio(st)
        self._sync_idle(st)

        if self._conn is not None:
            if changed:
                self._conn.emit_signal(
                    None, MENU_PATH, MENU_IFACE, "ItemsPropertiesUpdated",
                    GLib.Variant("(a(ia{sv})a(ias))",
                                 ([(i["id"], self._props(i)) for i in changed], [])))
            # NewToolTip só quando o texto muda de fato. Emitir sempre fazia o
            # host reler as propriedades a cada 2 s sem motivo.
            texto = self._tooltip_from(st)
            if texto != self._tooltip_text:
                self._tooltip_text = texto
                self._conn.emit_signal(None, SNI_PATH, SNI_IFACE,
                                       "NewToolTip", None)
        return True

    # ------------------------------------------------------------- áudio ----
    def _stop_audio_timer(self):
        if self._audio_timer is not None:
            GLib.source_remove(self._audio_timer)
            self._audio_timer = None

    def _sync_audio(self, st):
        """Liga o amostrador só enquanto o efeito de música estiver ativo.

        Trata os quatro estados, e não só os dois óbvios. O `pw-record` pode
        morrer sozinho (PipeWire reiniciado, por exemplo): aí a thread termina
        mas o timer de envio continua vivo. A versão anterior, ao religar,
        somava um segundo timer sem remover o primeiro; e se o usuário
        trocasse de efeito depois de uma queda, o ramo de limpeza nem rodava,
        porque testava `running`, que já era falso. O timer órfão não
        duplicava o tráfego D-Bus — `_push_audio` consome o dado e os extras
        encontram None — mas acordava a cada 45 ms para nada.
        """
        quer = st.get("effect") == effects.Music.nome

        if not quer:
            if self._sampler.running or self._audio_timer is not None:
                self._sampler.stop()
                self._stop_audio_timer()
                self._audio = None
                _log("amostragem de áudio encerrada")
            return

        if not self._sampler.running:
            self._stop_audio_timer()        # pode ter sobrado de uma queda
            if self._sampler.start():
                self._audio_timer = GLib.timeout_add(45, self._push_audio)
                _log("amostrando o áudio da sessão")
            else:
                _log(f"sem áudio: {self._sampler.last_error}")

    def _on_audio(self, level, bands):
        """Chamado da thread do amostrador — só guarda o valor.

        Falar D-Bus daqui seria falar de outra thread que não a da main loop.
        Quem envia é `_push_audio`, na loop.
        """
        self._audio = (level, bands)

    def _push_audio(self):
        if self._audio_timer is None:
            return GLib.SOURCE_REMOVE
        data, self._audio = self._audio, None
        if data is not None:
            try:
                self.backend.set_audio_level(*data)
            except Exception:                        # noqa: BLE001
                pass                                 # daemon caiu; o poll reconcilia
        return True

    # -------------------------------------------------------- inatividade ---
    def _sync_idle(self, st):
        """Arma ou desarma o observador conforme a preferência do daemon."""
        quer = bool(st.get("idle_blank"))
        if quer and not self._idle_armed:
            if self._idle.start():
                self._idle.set_timeout(st.get("idle_timeout", 120))
                self._idle_armed = True
                _log(f"apagar após {st.get('idle_timeout', 120)} s sem uso")
            else:
                _log(f"sem detecção de inatividade: {self._idle.last_error}")
        elif not quer and self._idle_armed:
            self._idle.stop()
            self._idle_armed = False
            _log("detecção de inatividade desligada")
        elif quer and self._idle_armed:
            self._idle.set_timeout(st.get("idle_timeout", 120))

    def _on_idle_change(self, idle):
        try:
            self.backend.set_idle_state(idle)
        except Exception as e:                       # noqa: BLE001
            _log(f"não consegui avisar o daemon da inatividade: {e!r}")

    def _quit(self, *_a):
        self._sampler.stop()
        self._stop_audio_timer()
        self._idle.stop()
        self.loop.quit()
        return GLib.SOURCE_REMOVE


def _spawn_gui():
    """Abre a janela.

    Instalado, `build_info.GUI_COMMAND` traz o caminho absoluto gravado pelo
    Meson. Rodando do repositório ele é None, e aí a janela é o `run.py` ao
    lado do pacote — é o que mantém o `python3 run.py` funcionando sem build.
    """
    if build_info.GUI_COMMAND:
        argv = [build_info.GUI_COMMAND]
    else:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        argv = [sys.executable, os.path.join(here, "run.py")]

    GLib.spawn_async(argv,
                     flags=GLib.SpawnFlags.SEARCH_PATH
                     | GLib.SpawnFlags.STDOUT_TO_DEV_NULL
                     | GLib.SpawnFlags.STDERR_TO_DEV_NULL)


def _log(msg):
    print(f"controlfanrgb-tray: {msg}", file=sys.stderr, flush=True)


def main():
    Tray().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
