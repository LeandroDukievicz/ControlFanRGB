"""O GNOME Shell carrega os ícones da bandeja pelo GdkPixbuf."""
from pathlib import Path

import gi
import pytest

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio  # noqa: E402

from controlfanrgb.tray import Tray, WATCHER_NAME


ICONES = Path(__file__).resolve().parents[1] / "data" / "icons"
APP_ID = "io.github.leandrodukievicz.ControlFanRGB"


@pytest.mark.parametrize("arquivo", [
    ICONES / f"{size}x{size}" / f"{APP_ID}.png"
    for size in (16, 22, 24, 32, 48, 64, 128, 256, 512)
])
def test_icone_carrega_no_gdkpixbuf(arquivo):
    tamanho = int(arquivo.parent.name.split("x")[0])
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(arquivo))
    assert pixbuf.get_width() == tamanho
    assert pixbuf.get_height() == tamanho


def test_tray_registra_quando_watcher_aparece(monkeypatch):
    """A extensão do GNOME pode iniciar depois do serviço do tray."""
    chamadas = []
    observadores = []

    class ConexaoFalsa:
        def register_object_with_closures2(self, *args):
            pass

        def call(self, *args):
            chamadas.append(args)

    def observar(conn, nome, flags, apareceu, desapareceu):
        observadores.append((conn, nome, apareceu))
        return 42

    monkeypatch.setattr(Gio, "bus_watch_name_on_connection", observar)
    tray = object.__new__(Tray)
    tray._bus_name = "org.kde.StatusNotifierItem-123-1"
    conn = ConexaoFalsa()

    tray._on_bus_acquired(conn, tray._bus_name)
    assert chamadas == []
    assert tray._watcher_id == 42
    assert observadores[0][:2] == (conn, WATCHER_NAME)

    observadores[0][2](conn, WATCHER_NAME, ":1.1")
    assert chamadas[0][2] == WATCHER_NAME
    assert chamadas[0][3] == "RegisterStatusNotifierItem"
    assert chamadas[0][4].unpack() == (tray._bus_name,)
