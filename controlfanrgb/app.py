"""Ponto de entrada: GUI (Adw.Application) e CLI pra atalhos de teclado."""
import argparse
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import build_info, themes
from .client import get_backend

APP_ID = "io.github.leandrodukievicz.ControlFanRGB"

CSS = """
.pd-sw:first-child { border-radius: 8px 0 0 8px; }
.pd-sw:last-child  { border-radius: 0 8px 8px 0; }
.pd-sw-round       { border-radius: 7px; }
"""


class ControlFanRGB(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        if not hasattr(self, "_css_provider"):
            self._css_provider = Gtk.CssProvider()
            self._css_provider.load_from_string(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        from .window import Window
        win = self.props.active_window or Window(self)
        win.present()


# --------------------------------------------------------------------- CLI --
NOTIFY_ID = 7311          # fixo: cada toque substitui a notificação anterior


def _notify(title, body, icon="io.github.leandrodukievicz.ControlFanRGB"):
    """Notificação do sistema.

    É o caminho possível no GNOME: o Mutter não implementa `wlr-layer-shell`,
    então um app comum não consegue desenhar um OSD flutuante. Um overlay
    bonito exigiria uma extensão do GNOME Shell.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications", "Notify",
            GLib.Variant("(susssasa{sv}i)",
                         ("ControlFanRGB", NOTIFY_ID, icon, title, body, [],
                          {"transient": GLib.Variant("b", True),
                           "urgency": GLib.Variant("y", 1)}, 2500)),
            None, Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error:
        pass              # sem servidor de notificação: silêncio, não é fatal


def _turbo_cli(backend, action):
    if action == "toggle":
        on = backend.toggle_turbo()
    else:
        on = action == "on"
        backend.set_turbo(on)

    print("turbo ligado" if on else "turbo desligado")
    _notify("Turbo ligado" if on else "Turbo desligado",
            "ajustando ventoinhas…" if on else "voltando à curva automática")

    # as ventoinhas levam ~2 s para assumir a nova rotação; a segunda
    # notificação substitui a primeira com o número real
    GLib.usleep(2_200_000)
    st = backend.status()
    if st.get("fan_cpu"):
        _notify("Turbo ligado" if on else "Turbo desligado",
                f"CPU {st['fan_cpu']} rpm · GPU {st['fan_gpu']} rpm")


def _cli(args):
    """Modo sem janela, para o atalho global do GNOME chamar."""
    backend = get_backend()
    try:
        if args.turbo:
            _turbo_cli(backend, args.turbo)
        elif args.off:
            backend.off()
            print("teclado apagado")
            _notify("Teclado apagado", "")
        elif args.theme:
            if args.theme not in themes.THEMES:
                sys.exit(f"tema desconhecido. opções: {', '.join(themes.THEMES)}")
            backend.apply_theme(args.theme)
            print(f"tema {args.theme} aplicado")
            _notify("Tema aplicado", args.theme)
        elif args.status:
            st = backend.status()
            print(f"backend     : {backend.kind}")
            print(f"modo        : {st['mode']}"
                  + (f" ({st['effect']})" if st.get("effect") else ""))
            print(f"brilho      : {st['brightness']}%")
            print(f"turbo       : {'ligado' if st['turbo'] else 'desligado'}"
                  + ("" if st.get("turbo_available") else "  (indisponível)"))
            print(f"ventoinhas  : CPU {st['fan_cpu']} rpm · GPU {st['fan_gpu']} rpm")
            print(f"temp. CPU   : {st['cpu_temp']:.0f} °C")
        else:                                  # --apply
            backend.apply_profile()
            print("perfil aplicado")
    except Exception as e:                     # noqa: BLE001
        sys.exit(f"erro: {e}")
    finally:
        backend.close()


def main():
    p = argparse.ArgumentParser(
        prog="controlfanrgb",
        description="RGB e refrigeração para Acer Predator no Linux")
    p.add_argument("--version", action="version",
                   version=f"controlfanrgb {build_info.VERSION}")
    p.add_argument("--apply", action="store_true",
                   help="reaplica o perfil salvo e sai (sem abrir janela)")
    p.add_argument("--status", action="store_true",
                   help="mostra o estado atual e sai")
    p.add_argument("--off", action="store_true", help="apaga o teclado e sai")
    p.add_argument("--turbo", choices=("on", "off", "toggle"),
                   help="liga, desliga ou alterna o modo turbo e sai")
    p.add_argument("--theme", metavar="NOME",
                   help=f"aplica um tema e sai ({', '.join(themes.THEMES)})")
    args = p.parse_args()

    if args.apply or args.off or args.theme or args.turbo or args.status:
        _cli(args)
        return 0
    return ControlFanRGB().run([])


if __name__ == "__main__":
    sys.exit(main())
