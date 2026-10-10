"""Janela principal — layout do mockup B: sidebar de navegação + conteúdo.

A pré-visualização do teclado fica fixa no topo, fora do stack, porque ela é
útil em todas as páginas (inclusive enquanto um efeito por software roda).
"""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gdk, Gtk  # noqa: E402

from . import config, effects, perkey, themes
from .client import get_backend
from .hardware import (MODE_NAMES, MODES_WITH_COLOR, STATIC,
                       Keyboard, KeyboardUnavailable, Sensors)
from .keyboardview import KeyboardView

PAGES = [
    ("lighting", "Iluminação", "display-brightness-symbolic"),
    ("perkey", "Tecla a tecla", "document-edit-symbolic"),
    ("themes", "Temas", "applications-graphics-symbolic"),
    ("effects", "Efeitos", "media-playback-start-symbolic"),
    ("cooling", "Resfriamento", "temperature-symbolic"),
    ("about", "Sobre", "help-about-symbolic"),
]


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="ControlFanRGB")
        self.set_default_size(980, 720)

        self.cfg = config.load()
        self.backend = get_backend()
        self._initial_status = {}
        if self.backend.kind == "daemon":
            try:
                self._initial_status = self.backend.status()
            except Exception:  # daemon pode reiniciar enquanto a janela abre
                pass
            else:
                for key in ("mode", "zones", "brightness", "firmware_mode",
                            "speed", "direction", "color", "software_effect"):
                    source = "effect" if key == "software_effect" else key
                    if source in self._initial_status:
                        self.cfg[key] = self._initial_status[source]
        self.sensors = Sensors()        # leitura local, só para a prévia
        self._applying = False          # evita loop ao popular os widgets
        self._preview_effect = None
        self.key_colors = {k: tuple(v) for k, v in self.cfg["key_colors"].items()}
        self._paint_apply_id = 0
        self._preview_t0 = 0.0
        self._preview_id = 0
        self._save_id = 0

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)

        split = Adw.NavigationSplitView(min_sidebar_width=200, max_sidebar_width=240)
        self.toasts.set_child(split)
        split.set_sidebar(self._build_sidebar())
        split.set_content(self._build_content())

        self._refresh_preview()
        self._sensor_id = GLib.timeout_add_seconds(2, self._tick_sensors)
        self._tick_sensors()

        if self.backend.kind == "daemon":
            self._restore_preview_from_status(self._initial_status)
        elif self.cfg["apply_on_start"]:
            GLib.idle_add(self._apply_current)

        self.connect("close-request", self._on_close)

    # ------------------------------------------------------------- sidebar --
    def _build_sidebar(self):
        self.sidebar_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.sidebar_list.connect("row-selected", self._on_page_selected)
        for name, label, icon in PAGES:
            row = Adw.ActionRow(title=label)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            row.page_name = name
            self.sidebar_list.append(row)

        tv = Adw.ToolbarView()
        sub = ("daemon conectado" if self.backend.kind == "daemon"
               else "modo direto (sem daemon)")
        tv.add_top_bar(Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title="ControlFanRGB", subtitle=f"4 zonas · {sub}")))
        tv.set_content(Gtk.ScrolledWindow(child=self.sidebar_list, vexpand=True))
        return Adw.NavigationPage(title="ControlFanRGB", child=tv)

    def _on_page_selected(self, _list, row):
        if row is None:
            return
        self.stack.set_visible_child_name(row.page_name)
        self.content_title.set_title(row.get_title())
        painting = row.page_name == "perkey"
        self.preview.set_paint_mode(painting, self.key_colors)
        if painting:
            self._refresh_zone_strip()
        else:
            self._refresh_preview()

    # ------------------------------------------------------------ conteúdo --
    def _build_content(self):
        self.preview = KeyboardView()
        self.preview.on_key_paint = self._on_key_paint
        self.preview.set_margin_start(14)
        self.preview.set_margin_end(14)
        self.preview.set_margin_top(12)

        self.banner = Adw.Banner(revealed=False)
        if not Keyboard.available():
            self.banner.set_title(
                "Teclado não encontrado — rode: sudo modprobe facer")
            self.banner.set_revealed(True)

        self.stack = Adw.ViewStack(vexpand=True)
        self.stack.add_named(self._page_lighting(), "lighting")
        self.stack.add_named(self._page_perkey(), "perkey")
        self.stack.add_named(self._page_themes(), "themes")
        self.stack.add_named(self._page_effects(), "effects")
        self.stack.add_named(self._page_cooling(), "cooling")
        self.stack.add_named(self._page_about(), "about")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.banner)
        box.append(self.preview)
        box.append(self.stack)

        self.content_title = Adw.WindowTitle(title="Iluminação")
        header = Adw.HeaderBar(title_widget=self.content_title)
        # Interruptor, não botão de mão única: antes ele só apagava, e para
        # reacender era preciso ir aplicar um tema ou mexer numa cor.
        self.power_btn = Gtk.ToggleButton(
            icon_name="system-shutdown-symbolic",
            tooltip_text="Apagar o teclado")
        self._power_handler = self.power_btn.connect("toggled", self._on_power)
        header.pack_end(self.power_btn)

        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        tv.set_content(box)
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))
        return Adw.NavigationPage(title="Iluminação", child=tv)

    # -------------------------------------------------------------- páginas --
    def _page_lighting(self):
        page = Adw.PreferencesPage()

        g = Adw.PreferencesGroup(title="Cor por zona",
                                 description="Da esquerda para a direita do teclado")
        self.zone_buttons = []
        for i in range(4):
            row = Adw.ActionRow(title=f"Zona {i + 1}",
                                subtitle=_hexstr(self.cfg["zones"][i]))
            btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False),
                                        valign=Gtk.Align.CENTER)
            btn.set_rgba(_rgba(self.cfg["zones"][i]))
            btn.connect("notify::rgba", self._on_zone_color, i, row)
            row.add_suffix(btn)
            self.zone_buttons.append(btn)
            g.add(row)
        page.add(g)

        g2 = Adw.PreferencesGroup(title="Brilho")
        row = Adw.ActionRow(title="Intensidade")
        self.brightness = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.brightness.set_value(self.cfg["brightness"])
        self.brightness.set_size_request(280, -1)
        self.brightness.set_draw_value(True)
        self.brightness.set_valign(Gtk.Align.CENTER)
        self.brightness.connect("value-changed", self._on_brightness)
        row.add_suffix(self.brightness)
        g2.add(row)
        page.add(g2)

        st = self._initial_status
        if not st:
            try:
                st = self.backend.status()
            except Exception:                        # noqa: BLE001
                st = {}

        g3 = Adw.PreferencesGroup(
            title="Quando a sessão fica sem uso",
            description="Depende do ícone de bandeja estar rodando: quem "
                        "percebe a inatividade é a sessão, e o daemon de "
                        "sistema não tem como saber se você está digitando.")

        self.always_on = Adw.SwitchRow(
            title="Sempre aceso",
            subtitle="Desligue para o teclado apagar sozinho depois de um "
                     "tempo parado")
        self.always_on.set_active(not st.get("idle_blank", False))
        self.always_on.connect("notify::active", self._on_always_on)
        g3.add(self.always_on)

        self.idle_minutes = Adw.SpinRow.new_with_range(1, 60, 1)
        self.idle_minutes.set_title("Apagar após")
        self.idle_minutes.set_subtitle("minutos sem teclado nem mouse")
        self.idle_minutes.set_value(
            max(1, round(int(st.get("idle_timeout", 120)) / 60)))
        self.idle_minutes.set_sensitive(not self.always_on.get_active())
        self.idle_minutes.connect("notify::value", self._on_idle_timeout)
        g3.add(self.idle_minutes)
        page.add(g3)
        return page

    def _page_perkey(self):
        """Pintura tecla a tecla, resolvida para as 4 zonas antes de escrever."""
        page = Adw.PreferencesPage()

        g = Adw.PreferencesGroup(
            title="Pincel",
            description="Clique ou arraste sobre o teclado acima. O hardware "
                        "tem 4 zonas, então a cor de cada zona é a média das "
                        "teclas que você pintou nela.")
        row = Adw.ActionRow(title="Cor", subtitle="#FF3B30")
        self.brush_sub = row
        self.brush = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        self.brush.set_rgba(_rgba((255, 59, 48)))
        self.brush.connect("notify::rgba", lambda *_: self.brush_sub.set_subtitle(
            _hexstr(_from_rgba(self.brush.get_rgba()))))
        row.add_suffix(self.brush)
        g.add(row)

        palette = Gtk.Box(spacing=6, margin_top=4, margin_bottom=4)
        for hexcode in ("ff3b30", "ff6a00", "ffb020", "ffe100", "9dff3c",
                        "00d4a0", "2de2ff", "4f7cff", "b14aed", "ffffff"):
            color = tuple(int(hexcode[i:i + 2], 16) for i in (0, 2, 4))
            sw = Gtk.Box(hexpand=True, height_request=30)
            sw.add_css_class("pd-sw-round")
            _set_bg(sw, color)
            btn = Gtk.Button(child=sw, css_classes=["flat"])
            btn.connect("clicked", self._on_palette, color)
            palette.append(btn)
        prow = Adw.ActionRow(title="Paleta")
        prow.add_suffix(palette)
        g.add(prow)

        self.eraser = Adw.SwitchRow(
            title="Borracha",
            subtitle="Clicar apaga a tecla em vez de pintar")
        g.add(self.eraser)
        page.add(g)

        g2 = Adw.PreferencesGroup(
            title="Como vai sair no teclado",
            description="O que o driver realmente recebe")
        self.zone_strip = Gtk.Box(spacing=6, margin_top=6, margin_bottom=6,
                                  homogeneous=True)
        self.zone_boxes, self.zone_labels = [], []
        for i in range(4):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            sw = Gtk.Box(height_request=30)
            sw.add_css_class("pd-sw-round")
            lbl = Gtk.Label(label=f"Zona {i + 1}", css_classes=["caption"])
            box.append(sw)
            box.append(lbl)
            self.zone_boxes.append(sw)
            self.zone_labels.append(lbl)
            self.zone_strip.append(box)
        srow = Adw.ActionRow()
        srow.set_child(self.zone_strip)
        g2.add(srow)
        page.add(g2)

        g3 = Adw.PreferencesGroup()
        clear = Adw.ButtonRow(title="Limpar tudo")
        clear.connect("activated", lambda *_: self._perkey_clear())
        g3.add(clear)
        fill = Adw.ButtonRow(title="Pintar todas as teclas com a cor do pincel")
        fill.connect("activated", lambda *_: self._perkey_fill())
        g3.add(fill)
        page.add(g3)
        return page

    def _on_palette(self, _btn, color):
        self.brush.set_rgba(_rgba(color))
        self.eraser.set_active(False)

    def _brush_color(self):
        return _from_rgba(self.brush.get_rgba())

    def _on_key_paint(self, key_id):
        if self.eraser.get_active():
            self.key_colors.pop(key_id, None)
        else:
            self.key_colors[key_id] = self._brush_color()
        self.preview.key_colors = self.key_colors
        self.preview.queue_draw()
        self._refresh_zone_strip()
        # agrupa cliques seguidos numa escrita só
        if self._paint_apply_id:
            GLib.source_remove(self._paint_apply_id)
        self._paint_apply_id = GLib.timeout_add(180, self._apply_perkey)

    def _apply_perkey(self):
        self._paint_apply_id = 0
        self.cfg["key_colors"] = {k: list(v) for k, v in self.key_colors.items()}
        self.cfg["zones"] = perkey.resolve_zones(self.key_colors)
        self.cfg["mode"] = "zones"
        self._applying = True
        for i, btn in enumerate(self.zone_buttons):
            btn.set_rgba(_rgba(self.cfg["zones"][i]))
        self._applying = False
        self._stop_engine()
        self._apply_current(toast=False)
        return False

    def _refresh_zone_strip(self):
        zones = perkey.resolve_zones(self.key_colors)
        counts = perkey.zone_counts(self.key_colors)
        for i, (box, lbl) in enumerate(zip(self.zone_boxes, self.zone_labels)):
            _set_bg(box, zones[i])
            n = counts[i]
            lbl.set_label(f"{_hexstr(zones[i])} · {n} tecla"
                          + ("s" if n != 1 else ""))

    def _perkey_clear(self):
        self.key_colors = {}
        self.preview.key_colors = self.key_colors
        self.preview.queue_draw()
        self._refresh_zone_strip()
        self._apply_perkey()
        self._toast("Teclas limpas")

    def _perkey_fill(self):
        self.key_colors = perkey.fill_all(self._brush_color())
        self.preview.key_colors = self.key_colors
        self.preview.queue_draw()
        self._refresh_zone_strip()
        self._apply_perkey()

    def _page_themes(self):
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(
            title="Temas prontos",
            description="Aplica as quatro cores de uma vez")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           max_children_per_line=3, row_spacing=10,
                           column_spacing=10, margin_top=6, homogeneous=True)
        for name, colors in themes.THEMES.items():
            flow.append(self._theme_card(name, colors))
        g.add(flow)
        page.add(g)
        return page

    def _theme_card(self, name, colors):
        strip = Gtk.Box(spacing=0, height_request=34)
        strip.add_css_class("pd-strip")
        for c in colors:
            sw = Gtk.Box(hexpand=True)
            sw.add_css_class("pd-sw")
            _set_bg(sw, c)
            strip.append(sw)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(strip)
        box.append(Gtk.Label(label=name, xalign=0, css_classes=["caption-heading"]))
        btn = Gtk.Button(child=box, css_classes=["card"])
        btn.connect("clicked", lambda *_: self._apply_theme(name))
        return btn

    def _page_effects(self):
        page = Adw.PreferencesPage()

        g = Adw.PreferencesGroup(
            title="Efeitos do firmware",
            description="Rodam no próprio controlador — não gastam CPU")
        self.mode_combo = Adw.ComboRow(
            title="Efeito",
            model=Gtk.StringList.new([MODE_NAMES[i] for i in range(6)]))
        self.mode_combo.set_selected(self.cfg["firmware_mode"])
        self.mode_combo.connect("notify::selected", self._on_firmware_mode)
        g.add(self.mode_combo)

        self.speed = Adw.SpinRow.new_with_range(0, 9, 1)
        self.speed.set_title("Velocidade")
        self.speed.set_value(self.cfg["speed"])
        self.speed.connect("notify::value", self._on_firmware_mode)
        g.add(self.speed)

        self.direction = Adw.ComboRow(
            title="Direção",
            model=Gtk.StringList.new(["Direita → esquerda", "Esquerda → direita"]))
        self.direction.set_selected(self.cfg["direction"] - 1)
        self.direction.connect("notify::selected", self._on_firmware_mode)
        g.add(self.direction)

        self.effect_color_row = Adw.ActionRow(
            title="Cor do efeito",
            subtitle="Usada em estático, respiração, shifting e zoom")
        self.effect_color = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        self.effect_color.set_rgba(_rgba(self.cfg["color"]))
        self.effect_color.connect("notify::rgba", self._on_firmware_mode)
        self.effect_color_row.add_suffix(self.effect_color)
        g.add(self.effect_color_row)
        page.add(g)

        g2 = Adw.PreferencesGroup(
            title="Efeitos por software",
            description="Estes o PredatorSense do Windows não tem. "
                        "Rodam a 30 fps e param sozinhos ao fechar o app.")
        self.effect_rows = {}
        for cls in effects.SOFTWARE_EFFECTS:
            inst = cls()
            row = Adw.ActionRow(title=inst.nome, subtitle=inst.descricao)
            btn = Gtk.Button(label="Ativar", valign=Gtk.Align.CENTER,
                             css_classes=["suggested-action"])
            btn.connect("clicked", self._on_software_effect, inst)
            row.add_suffix(btn)
            self.effect_rows[inst.nome] = (row, btn, inst)
            g2.add(row)
        page.add(g2)
        return page

    def _page_cooling(self):
        page = Adw.PreferencesPage()

        g = Adw.PreferencesGroup(title="Sensores")
        self.row_cpu_fan = Adw.ActionRow(title="Ventoinha da CPU", subtitle="—")
        self.row_gpu_fan = Adw.ActionRow(title="Ventoinha da GPU", subtitle="—")
        self.row_temp = Adw.ActionRow(title="Temperatura da CPU", subtitle="—")
        for r in (self.row_cpu_fan, self.row_gpu_fan, self.row_temp):
            g.add(r)
        page.add(g)

        g2 = Adw.PreferencesGroup(title="Turbo")
        self.row_turbo = Adw.SwitchRow(
            title="Modo turbo",
            subtitle="Ventoinhas no máximo + overclock")
        self.row_turbo.connect("notify::active", self._on_turbo)
        g2.add(self.row_turbo)

        st = self._initial_status
        if not st:
            try:
                st = self.backend.status()
            except Exception:
                st = {}
        if not st.get("turbo_available", False):
            self.row_turbo.set_sensitive(False)
            self.row_turbo.set_subtitle(
                "indisponível — precisa do módulo facer 1.1+ e da regra udev "
                "(veja kernel/instalar.sh)")
        page.add(g2)
        return page

    def _page_about(self):
        status = Adw.StatusPage(
            icon_name="keyboard-brightness-symbolic",
            title="ControlFanRGB",
            description=(
                "Controle de RGB e refrigeração para notebooks Acer Predator "
                "no Linux.\n\n"
                "Este notebook tem <b>4 zonas</b> de iluminação — o hardware não "
                "suporta cor por tecla individual, nem no Windows.\n\n"
                "Escrever cor custa ~0,07 ms, o que torna os efeitos por "
                "software viáveis a 60 fps."))
        status.set_vexpand(True)
        return status

    # ---------------------------------------------------------- callbacks ---
    def _on_zone_color(self, btn, _p, index, row):
        if self._applying:
            return
        color = _from_rgba(btn.get_rgba())
        self.cfg["zones"][index] = color
        self.cfg["mode"] = "zones"
        row.set_subtitle(_hexstr(color))
        self._stop_engine()
        self._apply_current()

    def _on_brightness(self, scale):
        if self._applying:
            return
        self.cfg["brightness"] = int(scale.get_value())
        try:
            self.backend.set_brightness(self.cfg["brightness"])
        except Exception as e:
            self._toast(f"Falhou: {e}")
            return
        if not self.power_btn.get_active():
            self.preview.update(self.preview.colors, self.cfg["brightness"])
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(350, self._save_config)

    def _save_config(self):
        self._save_id = 0
        config.save(self.cfg)
        return GLib.SOURCE_REMOVE

    def _on_firmware_mode(self, *_a):
        if self._applying:
            return
        mode = self.mode_combo.get_selected()
        self.cfg["firmware_mode"] = mode
        self.cfg["speed"] = int(self.speed.get_value())
        self.cfg["direction"] = self.direction.get_selected() + 1
        self.cfg["color"] = _from_rgba(self.effect_color.get_rgba())
        self.cfg["mode"] = "zones" if mode == STATIC else "firmware"
        self.effect_color_row.set_sensitive(mode in MODES_WITH_COLOR)
        self._stop_engine()
        self._apply_current()

    def _on_software_effect(self, button, inst):
        if self._preview_effect is not None and type(self._preview_effect) is type(inst):
            self._stop_engine()
            self._apply_current(toast=False)
            return
        self._stop_engine()
        try:
            self.backend.start_effect(inst.nome)
        except Exception as e:  # noqa: BLE001
            self._toast(str(e))
            return
        self._start_preview(type(inst)())
        self._set_power_state(False)     # efeito ativo também é "aceso"
        self.cfg["mode"] = "software"
        self.cfg["software_effect"] = inst.nome
        config.save(self.cfg)
        button.set_label("Parar")
        button.remove_css_class("suggested-action")
        button.add_css_class("destructive-action")
        self._toast(f"{inst.nome} ativo")

        if inst.nome == effects.Music.nome:
            # Quem amostra o áudio é o tray. Se ele não estiver no ar, o efeito
            # roda mas nunca reage — melhor dizer do que deixar o usuário
            # achando que está quebrado.
            GLib.timeout_add_seconds(3, self._check_audio_arriving)

    def _on_always_on(self, row, _p):
        if self._applying:
            return
        blank = not row.get_active()
        self.idle_minutes.set_sensitive(blank)
        self._push_idle(blank)

    def _on_idle_timeout(self, _row, _p):
        if self._applying or self.always_on.get_active():
            return
        self._push_idle(True)

    def _push_idle(self, blank):
        minutos = int(self.idle_minutes.get_value())
        try:
            self.backend.set_idle_blank(blank, minutos * 60)
        except Exception as e:                       # noqa: BLE001
            self._toast(str(e))
            return
        self._toast(f"Apaga após {minutos} min sem uso" if blank
                    else "Teclado sempre aceso")

    def _check_audio_arriving(self):
        try:
            st = self.backend.status()
        except Exception:                            # noqa: BLE001
            return GLib.SOURCE_REMOVE
        if st.get("effect") == effects.Music.nome and not st.get("audio_fresh"):
            self._toast("Sem áudio chegando — o ícone de bandeja precisa "
                        "estar rodando")
        return GLib.SOURCE_REMOVE

    def _on_turbo(self, row, _p):
        if self._applying:
            return
        want = row.get_active()
        try:
            self.backend.set_turbo(want)
        except Exception as e:  # noqa: BLE001
            self._toast(str(e))
            self._applying = True
            row.set_active(not want)
            self._applying = False
            return
        self._toast("Turbo ligado — ventoinhas no máximo"
                    if want else "Turbo desligado")

    def _start_preview(self, inst):
        """Redesenha o teclado da tela acompanhando o efeito.

        O daemon é quem escreve no hardware; aqui só recalculamos o mesmo
        efeito a 15 fps para a prévia, em vez de trafegar 30 frames por
        segundo pelo D-Bus.
        """
        self._preview_effect = inst
        self._preview_t0 = time.perf_counter()
        self._preview_id = GLib.timeout_add(66, self._tick_preview)

    def _restore_preview_from_status(self, st):
        self._set_power_state(not st.get("powered", True))
        if not st.get("powered", True):
            self.preview.update(self.cfg["zones"], 0)
            return
        name = st.get("effect") if st.get("mode") == "software" else None
        if name in self.effect_rows:
            _row, btn, inst = self.effect_rows[name]
            self._start_preview(type(inst)())
            btn.set_label("Parar")
            btn.remove_css_class("suggested-action")
            btn.add_css_class("destructive-action")

    def _tick_preview(self):
        if self._preview_effect is None:
            return False
        if not self.get_mapped():
            return True
        t = time.perf_counter() - self._preview_t0
        self.preview.update(self._preview_effect.frame(t, self.sensors),
                            self.cfg["brightness"])
        return True

    def _stop_engine(self):
        if self._preview_effect is None:
            return
        self._preview_effect = None
        if self._preview_id:
            GLib.source_remove(self._preview_id)
            self._preview_id = 0
        try:
            self.backend.stop_effect()
        except Exception:  # noqa: BLE001
            pass
        for _row, btn, _inst in self.effect_rows.values():
            btn.set_label("Ativar")
            btn.remove_css_class("destructive-action")
            btn.add_css_class("suggested-action")

    # ------------------------------------------------------------- ações ----
    def _apply_theme(self, name):
        self.cfg["zones"] = list(themes.THEMES[name])
        self.cfg["theme"] = name
        self.cfg["mode"] = "zones"
        self._applying = True
        for i, btn in enumerate(self.zone_buttons):
            btn.set_rgba(_rgba(self.cfg["zones"][i]))
        self._applying = False
        self._stop_engine()
        self._apply_current()
        self._toast(f"Tema {name} aplicado")

    def _apply_current(self, toast=True):
        try:
            if self.cfg["mode"] == "software":
                name = self.cfg.get("software_effect")
                if name not in self.effect_rows:
                    raise ValueError(f"efeito desconhecido: {name}")
                self.backend.start_effect(name)
                if self._preview_effect is None:
                    self._start_preview(type(self.effect_rows[name][2])())
                _row, btn, _inst = self.effect_rows[name]
                btn.set_label("Parar")
                btn.remove_css_class("suggested-action")
                btn.add_css_class("destructive-action")
            elif self.cfg["mode"] == "firmware":
                self.backend.set_firmware_effect(
                    self.cfg["firmware_mode"], self.cfg["speed"],
                    self.cfg["brightness"], self.cfg["direction"],
                    self.cfg["color"])
            else:
                self.backend.set_zones(self.cfg["zones"], self.cfg["brightness"])
        except Exception as e:  # noqa: BLE001  (D-Bus ou hardware)
            self._toast(f"Falhou: {e}")
            return False
        config.save(self.cfg)
        self._refresh_preview()
        self._set_power_state(False)     # acendeu: o interruptor volta
        return False

    def _on_power(self, btn):
        if btn.get_active():
            self._turn_off()
        else:
            self._turn_on()

    def _set_power_state(self, apagado):
        """Sincroniza o botão sem disparar o handler.

        Sem o bloqueio isto entraria em laço: `_turn_on` chama
        `_apply_current`, que chama este método, que mexeria no botão e
        dispararia `_on_power` outra vez.
        """
        btn = getattr(self, "power_btn", None)
        if btn is None or btn.get_active() == apagado:
            return
        btn.handler_block(self._power_handler)
        btn.set_active(apagado)
        btn.handler_unblock(self._power_handler)
        btn.set_tooltip_text("Acender o teclado" if apagado
                             else "Apagar o teclado")

    def _turn_off(self):
        self._stop_engine()
        try:
            self.backend.off()
        except Exception as e:  # noqa: BLE001
            self._toast(f"Falhou: {e}")
            self._set_power_state(False)
            return
        self.preview.update(self.cfg["zones"], 0)
        self.power_btn.set_tooltip_text("Acender o teclado")
        self._toast("Teclado apagado")

    def _turn_on(self):
        """Devolve o teclado ao que ele estava fazendo antes de apagar.

        Se havia um efeito por software, ele volta a rodar; senão vale o
        perfil de cores ou o efeito de firmware.
        """
        try:
            self.backend.apply_profile()
            st = self.backend.status()
        except Exception as e:
            self._toast(f"Falhou: {e}")
            self._set_power_state(True)
            return
        self._refresh_preview()
        self._restore_preview_from_status(st)
        self._toast("Teclado aceso")

    def _refresh_preview(self):
        if self.cfg["mode"] == "firmware" and self.cfg["firmware_mode"] != STATIC:
            mode = self.cfg["firmware_mode"]
            base = self.cfg["color"] if mode in MODES_WITH_COLOR else (120, 200, 255)
            self.preview.update([base] * 4, self.cfg["brightness"])
        else:
            self.preview.update(self.cfg["zones"], self.cfg["brightness"])

    def _tick_sensors(self):
        if not self.get_mapped():
            return True
        try:
            st = self.backend.status()
        except Exception:  # noqa: BLE001  (daemon reiniciando)
            return True

        if st.get("fan_cpu"):
            self.row_cpu_fan.set_subtitle(f"{st['fan_cpu']} rpm")
            self.row_gpu_fan.set_subtitle(f"{st['fan_gpu']} rpm")
        else:
            indisp = ("indisponível — o módulo precisa da quirk predator_v4 "
                      "(fork facer 1.1)")
            self.row_cpu_fan.set_subtitle(indisp)
            self.row_gpu_fan.set_subtitle(indisp)

        temp = st.get("cpu_temp") or 0
        self.row_temp.set_subtitle(f"{temp:.0f} °C" if temp else "indisponível")

        # o turbo também muda pela tecla física do chassi, então espelhamos
        if st.get("turbo") != self.row_turbo.get_active():
            self._applying = True
            self.row_turbo.set_active(bool(st.get("turbo")))
            self._applying = False
        self._set_power_state(not st.get("powered", True))
        return True

    def _toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=2))

    def _on_close(self, *_a):
        # o efeito continua no daemon de propósito — só paramos a prévia
        if self._preview_id:
            GLib.source_remove(self._preview_id)
            self._preview_id = 0
        if self._paint_apply_id:
            GLib.source_remove(self._paint_apply_id)
            self._apply_perkey()
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save_id = 0
        if self._sensor_id:
            GLib.source_remove(self._sensor_id)
            self._sensor_id = 0
        self.backend.close()
        config.save(self.cfg)
        return False


# ----------------------------------------------------------------- helpers --
def _rgba(color):
    r, g, b = color
    c = Gdk.RGBA()
    c.red, c.green, c.blue, c.alpha = r / 255, g / 255, b / 255, 1.0
    return c


def _from_rgba(c):
    return (int(c.red * 255), int(c.green * 255), int(c.blue * 255))


def _hexstr(color):
    return "#%02X%02X%02X" % tuple(color)


def _set_bg(widget, color):
    provider = Gtk.CssProvider()
    provider.load_from_string(
        "box { background:%s; }" % _hexstr(color))
    widget.get_style_context().add_provider(
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
