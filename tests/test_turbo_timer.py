"""Timer do modo turbo: ligar por N minutos e desligar sozinho.

Sem hardware: o sysfs do turbo é trocado por um dublê que guarda o estado.
"""
import json

import pytest
from gi.repository import GLib

from controlfanrgb import config, daemon as D, validation
from controlfanrgb.hardware import KeyboardUnavailable
from controlfanrgb.tray import Tray


class TurboFalso:
    """Faz o papel de /sys/devices/platform/acer-wmi/turbo."""

    def __init__(self, ligado=False, falha=False):
        self.ligado = ligado
        self.falha = falha
        self.escritas = []

    def get(self):
        return self.ligado

    def set(self, on):
        if self.falha:
            raise KeyboardUnavailable("turbo indisponível")
        self.escritas.append(bool(on))
        self.ligado = bool(on)

    def toggle(self):
        self.set(not self.ligado)
        return self.ligado


@pytest.fixture
def turbo(monkeypatch):
    t = TurboFalso()
    monkeypatch.setattr(D.Turbo, "get", staticmethod(t.get))
    monkeypatch.setattr(D.Turbo, "set", staticmethod(t.set))
    monkeypatch.setattr(D.Turbo, "toggle", staticmethod(t.toggle))
    return t


@pytest.fixture
def daemon():
    d = D.Daemon.__new__(D.Daemon)
    d._turbo_timer = 0
    d._turbo_deadline = 0.0
    d._last_turbo = None
    d._conn = None
    yield d
    d._cancel_turbo_timer()


# ---------------------------------------------------------- duração ------
@pytest.mark.parametrize("texto, segundos", [
    ("15", 900), ("1", 60), ("90s", 90), ("15m", 900), ("1h", 3600),
    ("1h30m", 5400), ("2m30s", 150), (" 10 M ", 600),
])
def test_duration_aceita_formatos(texto, segundos):
    assert validation.duration(texto) == segundos


@pytest.mark.parametrize("texto", ["", "0", "0m", "abc", "-5", "1.5", "m", "5x"])
def test_duration_recusa_lixo(texto):
    with pytest.raises(ValueError):
        validation.duration(texto)


@pytest.mark.parametrize("segundos, texto", [
    (0, "0:00"), (5, "0:05"), (725, "12:05"), (3725, "1:02:05"), (-3, "0:00"),
])
def test_format_remaining(segundos, texto):
    assert validation.format_remaining(segundos) == texto


# ------------------------------------------------------------ daemon ------
def test_set_turbo_timer_liga_e_agenda(turbo, daemon):
    daemon._dispatch("SetTurboTimer", (600,))

    assert turbo.ligado is True
    assert daemon._turbo_timer != 0
    assert 595 <= daemon._turbo_remaining() <= 600


def test_timer_desliga_o_turbo_quando_acaba(turbo, daemon):
    daemon._dispatch("SetTurboTimer", (600,))

    assert daemon._on_turbo_timer() == GLib.SOURCE_REMOVE
    assert turbo.ligado is False
    assert daemon._turbo_remaining() == 0


def test_timer_dispara_de_verdade_na_loop(turbo, daemon):
    """De ponta a ponta com o relógio real do GLib, um segundo."""
    loop = GLib.MainLoop()
    daemon._dispatch("SetTurboTimer", (1,))
    assert turbo.ligado is True

    def quando_desligar():
        if not turbo.ligado:
            loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(50, quando_desligar)
    guarda = GLib.timeout_add_seconds(5, loop.quit)
    loop.run()
    GLib.source_remove(guarda)

    assert turbo.ligado is False, "o timer não desligou o turbo em 5 s"
    assert turbo.escritas == [True, False]


def test_zero_cancela_o_timer_mas_mantem_o_turbo(turbo, daemon):
    daemon._dispatch("SetTurboTimer", (600,))
    daemon._dispatch("SetTurboTimer", (0,))

    assert turbo.ligado is True
    assert daemon._turbo_timer == 0
    assert daemon._turbo_remaining() == 0


def test_reprogramar_troca_o_prazo_sem_empilhar_timers(turbo, daemon):
    daemon._dispatch("SetTurboTimer", (600,))
    primeiro = daemon._turbo_timer
    daemon._dispatch("SetTurboTimer", (60,))

    assert daemon._turbo_timer != primeiro
    assert GLib.main_context_default().find_source_by_id(primeiro) is None
    assert daemon._turbo_remaining() <= 60


@pytest.mark.parametrize("metodo, args", [
    ("SetTurbo", (False,)), ("SetTurbo", (True,)), ("ToggleTurbo", ()),
])
def test_comando_manual_cancela_o_timer(turbo, daemon, metodo, args):
    """Ligar sem timer quer dizer "até eu desligar": o timer antigo não pode
    desligar depois por conta própria."""
    daemon._dispatch("SetTurboTimer", (600,))
    daemon._dispatch(metodo, args)
    assert daemon._turbo_timer == 0


def test_tecla_fisica_desligando_cancela_o_timer(turbo, daemon):
    daemon._dispatch("SetTurboTimer", (600,))
    turbo.ligado = False                     # tecla do chassi
    daemon._poll_turbo()

    assert daemon._turbo_timer == 0


def test_leitura_atrasada_logo_apos_ligar_nao_mata_o_timer(turbo, daemon):
    """O poll só cancela numa transição ligado → desligado que ele viu."""
    daemon._last_turbo = False
    turbo.falha = False
    turbo.ligado = False
    daemon._turbo_timer = GLib.timeout_add_seconds(600, lambda: False)
    daemon._poll_turbo()
    assert daemon._turbo_timer != 0


def test_sem_permissao_nao_cria_timer(turbo, daemon):
    turbo.falha = True
    with pytest.raises(KeyboardUnavailable):
        daemon._dispatch("SetTurboTimer", (600,))
    assert daemon._turbo_timer == 0


@pytest.mark.parametrize("valor", [D.TURBO_TIMER_MAX + 1, -1, True])
def test_daemon_recusa_duracao_fora_da_faixa(turbo, daemon, valor):
    with pytest.raises(ValueError):
        daemon._dispatch("SetTurboTimer", (valor,))
    assert turbo.escritas == []


def test_status_expoe_o_tempo_restante(turbo, daemon, monkeypatch):
    class Sensores:
        def fans(self): return (5555, 5769)
        def cpu_temp(self): return 60.0

    class Motor:
        running = False
        last_error = None

    daemon.sensors = Sensores()
    daemon.engine = Motor()
    daemon.state = dict(D.DEFAULT_STATE)
    daemon._powered = True
    daemon._idle_active = False
    monkeypatch.setattr(D.Turbo, "available", staticmethod(lambda: True))

    assert daemon._status()["turbo_remaining"].unpack() == 0
    daemon._dispatch("SetTurboTimer", (120,))
    assert 115 <= daemon._status()["turbo_remaining"].unpack() <= 120


def test_encerrar_o_daemon_com_timer_desliga_o_turbo(turbo, daemon):
    """Ninguém mais desligaria depois: as ventoinhas ficariam no máximo."""
    class Nada:
        def stop(self): pass
        def close(self): pass
        def quit(self): pass

    daemon._save_timer = 0
    daemon.engine = daemon.kb = daemon.loop = Nada()
    daemon._dispatch("SetTurboTimer", (600,))
    daemon._quit()

    assert turbo.ligado is False
    assert daemon._turbo_timer == 0


def test_encerrar_sem_timer_nao_mexe_no_turbo(turbo, daemon):
    class Nada:
        def stop(self): pass
        def close(self): pass
        def quit(self): pass

    turbo.ligado = True
    daemon._save_timer = 0
    daemon.engine = daemon.kb = daemon.loop = Nada()
    daemon._quit()

    assert turbo.ligado is True and turbo.escritas == []


def test_introspeccao_declara_o_metodo():
    from gi.repository import Gio
    node = Gio.DBusNodeInfo.new_for_xml(D.INTROSPECTION)
    m = node.interfaces[0].lookup_method("SetTurboTimer")
    assert m is not None and m.in_args[0].signature == "u"


# -------------------------------------------------------------- tray ------
def test_tray_mostra_tempo_restante():
    st = {"turbo": True, "turbo_remaining": 61, "fan_cpu": 5555, "fan_gpu": 5769}
    assert Tray._turbo_label(st) == "Turbo (desliga em 2 min)"
    assert "desliga em 2 min" in Tray._tooltip_from(st)
    assert Tray._turbo_label({"turbo": True}) == "Turbo"
    assert Tray._turbo_label({"turbo": False, "turbo_remaining": 30}) == "Turbo"


def test_tray_menu_turbo_por_chama_o_backend():
    chamadas = []

    class Backend:
        def set_turbo_timer(self, s): chamadas.append(s)

    t = Tray.__new__(Tray)
    t.backend = Backend()
    root = t._build_menu()
    t._items = {}
    t._index(root)
    item = next(i for i in t._items.values()
                if i.get("action") == "turbo_for" and i.get("arg") == 1800)

    t._activate(item["id"])
    assert chamadas == [1800]


# --------------------------------------------------------------- CLI ------
def test_cli_sem_daemon_recusa_timer(monkeypatch):
    from controlfanrgb import app

    class Local:
        kind = "local"
        def set_turbo_timer(self, s): raise AssertionError("não pode chamar")

    with pytest.raises(SystemExit):
        app._turbo_for_cli(Local(), 900)


def test_cli_com_daemon_programa_timer(monkeypatch, capsys):
    from controlfanrgb import app
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)
    chamadas = []

    class Daemon:
        kind = "daemon"
        def set_turbo_timer(self, s): chamadas.append(s)

    app._turbo_for_cli(Daemon(), 900)
    assert chamadas == [900]
    assert "15:00" in capsys.readouterr().out


# ------------------------------------------------------------- config ------
@pytest.mark.parametrize("salvo, esperado", [
    (30, 30), (0, 0), (721, 0), ("30", 0), (None, 0),
])
def test_config_guarda_minutos_do_timer(tmp_path, monkeypatch, salvo, esperado):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"turbo_minutes": salvo}))
    monkeypatch.setattr(config, "PATH", str(path))
    assert config.load()["turbo_minutes"] == esperado
