"""Pré-visualização do teclado: desenha as teclas coloridas pela zona.

É só um Gtk.DrawingArea com cairo — leve o bastante pra redesenhar a 30 fps
enquanto um efeito por software está rodando.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# Larguras em "unidades de tecla". Layout do PH315-54 (com numpad).
MAIN_ROWS = [
    [("esc", 1), ("F1", 1), ("F2", 1), ("F3", 1), ("F4", 1), ("F5", 1), ("F6", 1),
     ("F7", 1), ("F8", 1), ("F9", 1), ("F10", 1), ("F11", 1), ("F12", 1), ("del", 2)],
    [("~", 1), ("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1),
     ("8", 1), ("9", 1), ("0", 1), ("-", 1), ("=", 1), ("⌫", 2)],
    [("tab", 1.5), ("Q", 1), ("W", 1), ("E", 1), ("R", 1), ("T", 1), ("Y", 1),
     ("U", 1), ("I", 1), ("O", 1), ("P", 1), ("[", 1), ("]", 1), ("\\", 1.5)],
    [("caps", 1.75), ("A", 1), ("S", 1), ("D", 1), ("F", 1), ("G", 1), ("H", 1),
     ("J", 1), ("K", 1), ("L", 1), (";", 1), ("'", 1), ("enter", 2.25)],
    [("shift", 2.25), ("Z", 1), ("X", 1), ("C", 1), ("V", 1), ("B", 1), ("N", 1),
     ("M", 1), (",", 1), (".", 1), ("/", 1), ("shift", 1.75), ("↑", 1)],
    [("ctrl", 1.25), ("fn", 1.25), ("⊞", 1.25), ("alt", 1.25), ("space", 4.75),
     ("alt", 1.25), ("ctrl", 1.25), ("←", 1), ("↓", 1), ("→", 1)],
]
NUM_ROWS = [
    [("num", 1), ("/", 1), ("*", 1), ("-", 1)],
    [("7", 1), ("8", 1), ("9", 1), ("+", 1)],
    [("4", 1), ("5", 1), ("6", 1), (None, 1)],
    [("1", 1), ("2", 1), ("3", 1), ("⏎", 1)],
    [("0", 2), (".", 1), (None, 1)],
]
MAIN_FRAC = 0.785          # fatia da largura que o bloco principal ocupa


def zone_of(center):
    """Em qual das 4 zonas físicas cai uma tecla, dado seu centro em 0..1."""
    return min(3, int(center * 4))


class KeyboardView(Gtk.DrawingArea):
    """Mostra as 4 zonas. `colors` são 4 tuplas (r,g,b) 0-255."""

    def __init__(self):
        super().__init__()
        self.colors = [(60, 60, 70)] * 4
        self.brightness = 100
        self.set_content_height(188)
        self.set_draw_func(self._draw)

    def update(self, colors, brightness=None):
        self.colors = list(colors)[:4]
        if brightness is not None:
            self.brightness = brightness
        self.queue_draw()

    # ------------------------------------------------------------- desenho --
    def _draw(self, _area, cr, width, height):
        pad = 10
        gap_blocks = 9
        inner_w = width - pad * 2 - gap_blocks
        main_w = inner_w * MAIN_FRAC
        num_w = inner_w - main_w

        gap = 4
        rows = len(MAIN_ROWS)
        key_h = min((height - pad * 2 - gap * (rows - 1)) / rows,
                    main_w / 15.5 * 0.92)
        total_h = key_h * rows + gap * (rows - 1)
        top = (height - total_h) / 2

        _rounded(cr, 1, 1, width - 2, height - 2, 11)
        cr.set_source_rgb(0.04, 0.045, 0.07)
        cr.fill()

        self._draw_block(cr, MAIN_ROWS, pad, top, main_w, key_h, gap, 0.0, MAIN_FRAC)
        self._draw_block(cr, NUM_ROWS, pad + main_w + gap_blocks, top, num_w,
                         key_h, gap, MAIN_FRAC, 1 - MAIN_FRAC, rows_units=4)

    def _draw_block(self, cr, rows, x0, y0, block_w, key_h, gap,
                    frac_start, frac_span, rows_units=None):
        dim = max(0.18, self.brightness / 100.0)
        for r, row in enumerate(rows):
            units = rows_units or sum(w for _, w in row)
            unit_w = (block_w - gap * (len(row) - 1)) / units
            x = x0
            cum = 0.0
            y = y0 + r * (key_h + gap)
            for label, w in row:
                kw = unit_w * w
                if label is not None:
                    center = frac_start + frac_span * (cum + w / 2) / units
                    cr.save()
                    self._draw_key(cr, x, y, kw, key_h,
                                   self.colors[zone_of(center)], dim, label)
                    cr.restore()
                x += kw + gap
                cum += w

    def _draw_key(self, cr, x, y, w, h, color, dim, label):
        r, g, b = (c / 255.0 for c in color)
        _rounded(cr, x, y, w, h, min(5, h / 5))
        cr.set_source_rgb(0.08 + r * 0.62 * dim,
                          0.085 + g * 0.62 * dim,
                          0.105 + b * 0.62 * dim)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.set_line_width(1)
        cr.stroke()

        size = max(6.0, min(10.0, h * 0.34 if len(label) <= 2 else h * 0.26))
        cr.select_font_face("Inter")
        cr.set_font_size(size)
        ext = cr.text_extents(label)
        cr.move_to(x + (w - ext.width) / 2 - ext.x_bearing,
                   y + (h - ext.height) / 2 - ext.y_bearing)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.show_text(label)


def _rounded(cr, x, y, w, h, r):
    from math import pi
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, pi / 2)
    cr.arc(x + r, y + h - r, r, pi / 2, pi)
    cr.arc(x + r, y + r, r, pi, 3 * pi / 2)
    cr.close_path()
