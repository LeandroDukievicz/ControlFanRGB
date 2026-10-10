"""Renderiza cada página da janela num PNG, sem passar pela tela.

O GNOME Shell 50 recusa captura de tela por D-Bus a chamadores externos
("Screenshot is not allowed") e o portal exigiria aprovação manual a cada
imagem. Como a janela é GTK4, dá para pedir ao próprio toolkit que desenhe o
widget numa textura — e o resultado é melhor: sem cursor, sem sombra do
compositor, sempre no mesmo tamanho.
"""
import sys, os

# Funciona tanto a partir do repositório quanto da versão instalada.
_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(1, _repo if os.path.isdir(os.path.join(_repo, "controlfanrgb"))
                else "/usr/share/controlfanrgb")

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Gsk, Gdk

from controlfanrgb import config, window as W

DESTINO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
LARG = 1100
# Altura por página: a de Efeitos tem seis efeitos por software abaixo do
# grupo de firmware e cortava no rodapé com altura única.
ALTURAS = {
    "lighting": 960, "perkey": 900, "themes": 800,
    "effects": 1180, "cooling": 820, "about": 760,
}
ALT_PADRAO = 820

# Não mexer no teclado do usuário só para tirar print.
_load = config.load
config.load = lambda: {**_load(), "apply_on_start": False}

os.makedirs(DESTINO, exist_ok=True)
app = Adw.Application(application_id="io.github.leandrodukievicz.ControlFanRGB.Shot")
feitos = []


def desenhar(win, caminho):
    paintable = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, win.get_width(), win.get_height())
    node = snap.to_node()
    if node is None:
        return False
    tex = win.get_renderer().render_texture(node, None)
    tex.save_to_png(caminho)
    return True


def ao_ativar(a):
    win = W.Window(a)
    win.set_default_size(LARG, ALT_PADRAO)
    win.present()

    paginas = list(W.PAGES)
    estado = {"i": 0, "espera": 0}

    def passo():
        i = estado["i"]
        if i >= len(paginas):
            a.quit()
            return False
        nome, rotulo, _icone = paginas[i]
        if estado["espera"] == 0:
            win.set_default_size(LARG, ALTURAS.get(nome, ALT_PADRAO))
            linha = win.sidebar_list.get_row_at_index(i)
            win.sidebar_list.select_row(linha)
        estado["espera"] += 1
        if estado["espera"] < 12:           # deixa assentar, animar e redimensionar
            return True
        caminho = os.path.join(DESTINO, f"{i+1:02d}-{nome}.png")
        if desenhar(win, caminho):
            feitos.append((nome, rotulo, caminho))
            print(f"  {i+1}/{len(paginas)} {rotulo} -> {os.path.basename(caminho)}")
        else:
            print(f"  {i+1}/{len(paginas)} {rotulo} -> FALHOU (sem nó de render)")
        estado["i"] += 1
        estado["espera"] = 0
        return True

    GLib.timeout_add(120, passo)


app.connect("activate", ao_ativar)
app.run([])
print(f"\n  {len(feitos)} imagens em {DESTINO}")
