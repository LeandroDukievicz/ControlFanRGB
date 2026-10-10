"""Testes dos defeitos que já aconteceram.

Cada teste aqui corresponde a um bug real encontrado em produção nesta
máquina, com a medição que o denunciou no comentário. Nenhum precisa de
hardware: o teclado, os sensores e o backend são dublês.
"""
import threading
import time
import types
import subprocess
import sys

import pytest
from gi.repository import GLib

from controlfanrgb import effects
from controlfanrgb.tray import Tray


# --------------------------------------------------------------- dublês --
class BackendFalso:
    kind = "falso"

    def __init__(self, status=None):
        self.chamadas = 0
        self._status = status or {"turbo": False, "fan_cpu": 0, "effect": ""}

    def status(self):
        self.chamadas += 1
        return dict(self._status)


class TecladoFalso:
    def __init__(self):
        self.escritas = 0

    def set_zones(self, colors, brightness):
        self.escritas += 1


def tray_sem_dbus(backend=None):
    """Instância de Tray sem __init__ — não toca no barramento."""
    t = object.__new__(Tray)
    t.backend = backend or BackendFalso()
    t._status = {}
    t._tooltip_text = "ControlFanRGB"
    t._conn = None
    t._audio_timer = None
    t._audio = None
    return t


# ------------------------------------------------- getter do SNI sem I/O --
@pytest.mark.parametrize("prop", [
    "Category", "Id", "Title", "Status", "WindowId", "IconName",
    "IconThemePath", "OverlayIconName", "AttentionIconName", "ItemIsMenu",
    "Menu", "ToolTip",
])
def test_sni_get_nunca_consulta_o_daemon(prop):
    """Medido: 690 GetStatus/s porque o getter montava ToolTip chamando
    backend.status(), mesmo quando o host pedia "Category"."""
    backend = BackendFalso()
    t = tray_sem_dbus(backend)

    valor = t._sni_get(None, None, None, None, prop)

    assert valor is not None, f"{prop} deveria ter valor"
    assert backend.chamadas == 0, (
        f"ler {prop} fez {backend.chamadas} chamada(s) ao daemon")


def test_sni_get_propriedade_desconhecida_devolve_none():
    assert tray_sem_dbus()._sni_get(None, None, None, None, "NaoExiste") is None


def test_tooltip_vem_do_snapshot_e_nao_do_barramento():
    backend = BackendFalso()
    t = tray_sem_dbus(backend)
    t._tooltip_text = "turbo ligado · CPU 5555 rpm · GPU 5769 rpm"

    v = t._sni_get(None, None, None, None, "ToolTip")

    assert v.unpack()[3] == "turbo ligado · CPU 5555 rpm · GPU 5769 rpm"
    assert backend.chamadas == 0


def test_tooltip_from_e_puro():
    assert Tray._tooltip_from({}) == "daemon indisponível"
    assert Tray._tooltip_from({"turbo": True, "fan_cpu": 0}) == "turbo ligado"
    assert "5555" in Tray._tooltip_from(
        {"turbo": True, "fan_cpu": 5555, "fan_gpu": 5769})


# -------------------------------------------- a primeira atualização ------
def test_refresh_once_nao_se_reagenda():
    """Medido: 632 chamadas/s. `GLib.idle_add(self._refresh)` com _refresh
    devolvendo True vira laço ocupado — idle que devolve True é reagendado
    de imediato."""
    t = tray_sem_dbus()
    t._sync_audio = lambda st: None
    t._sync_idle = lambda st: None
    t.item_turbo = {}
    t.item_fans = {}

    assert t._refresh_once() == GLib.SOURCE_REMOVE
    assert t._refresh() is True, "o timeout de 2 s precisa continuar vivo"


# ------------------------------------------- ciclo de vida do áudio -------
class AmostradorFalso:
    def __init__(self):
        self.running = False
        self.last_error = None
        self.paradas = 0

    def start(self):
        self.running = True
        return True

    def stop(self):
        self.running = False
        self.paradas += 1


def test_sync_audio_limpa_timer_quando_amostrador_morreu_sozinho():
    """Se o pw-record morre e o usuário troca de efeito, o ramo de limpeza
    precisa rodar mesmo com `running` já falso — senão o timer de 45 ms fica
    acordando para sempre."""
    t = tray_sem_dbus()
    t._sampler = AmostradorFalso()
    removidos = []
    t._stop_audio_timer = lambda: removidos.append(t._audio_timer)

    t._audio_timer = 123            # sobrou de uma queda do pw-record
    t._sampler.running = False      # a thread já morreu
    t._sync_audio({"effect": "Arco-íris"})

    assert removidos == [123], "o timer órfão não foi removido"


def test_sync_audio_nao_empilha_timer_ao_religar():
    t = tray_sem_dbus()
    t._sampler = AmostradorFalso()
    t._audio_timer = 777            # timer da sessão anterior
    removidos = []
    t._stop_audio_timer = lambda: removidos.append(t._audio_timer)

    t._sync_audio({"effect": effects.Music.nome})

    assert removidos == [777], "religou sem remover o timer antigo"


def test_push_audio_nao_envia_sem_dado_novo():
    enviados = []
    t = tray_sem_dbus()
    t.backend.set_audio_level = lambda lv, b: enviados.append((lv, b))
    t._audio_timer = 1

    assert t._push_audio() is True
    assert enviados == [], "enviou sem dado novo"

    t._audio = (0.5, [0.1, 0.2, 0.3, 0.4])
    t._push_audio()
    assert len(enviados) == 1
    assert t._audio is None, "o dado deveria ser consumido"


def test_sampler_para_thread_e_recolhe_subprocesso(monkeypatch):
    from controlfanrgb.audio import Sampler

    sampler = Sampler(lambda level, bands: None)
    monkeypatch.setattr(sampler, "available", lambda: True)
    script = ("import os,time\n"
              "while True:\n"
              " os.write(1, b'\\0' * 4096)\n"
              " time.sleep(.02)\n")
    criado = []
    def spawn():
        proc = subprocess.Popen([sys.executable, "-u", "-c", script],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        criado.append(proc)
        return proc
    monkeypatch.setattr(sampler, "_spawn", spawn)
    assert sampler.start()
    deadline = time.monotonic() + 2
    while sampler._proc is None and time.monotonic() < deadline:
        time.sleep(.01)
    assert sampler._proc is not None
    sampler.stop()
    assert not sampler.running
    assert sampler._proc is None
    assert criado[0].returncode is not None
    assert criado[0].stdout.closed


# ------------------------------------------- envio de áudio sem resposta --
def test_set_audio_level_nao_espera_resposta():
    """Medido enviando a 22/s: `proxy.call()` com callback None retém 70 B por
    envio, porque registra uma chamada pendente que ninguém colhe. Com
    NO_REPLY_EXPECTED, zero."""
    from gi.repository import Gio
    from controlfanrgb.client import DaemonBackend

    enviadas = []

    class ConexaoFalsa:
        def send_message(self, msg, flags):
            enviadas.append(msg)

    class ProxyFalso:
        def get_connection(self):
            return ConexaoFalsa()

        def call(self, *a, **k):
            raise AssertionError("não deveria usar proxy.call — ele retém")

    b = object.__new__(DaemonBackend)
    b._proxy = ProxyFalso()
    b.set_audio_level(0.5, [0.1, 0.2, 0.3, 0.4])

    assert len(enviadas) == 1
    msg = enviadas[0]
    assert msg.get_flags() & Gio.DBusMessageFlags.NO_REPLY_EXPECTED
    assert msg.get_member() == "SetAudioLevel"
    assert msg.get_body().unpack() == (0.5, [0.1, 0.2, 0.3, 0.4])


# ----------------------------------------------- threads do motor ---------
class EfeitoLento:
    nome = "lento"

    def frame(self, t, sensors):
        time.sleep(0.03)
        return [(1, 2, 3)] * 4


def test_engine_nao_acumula_threads_em_trocas_rapidas():
    """Cada thread tem o seu Event. Antes, `stop()` desistia após 1 s e o
    `clear()` seguinte ressuscitava a thread antiga."""
    base = threading.active_count()
    motor = effects.Engine(TecladoFalso(), None)

    for _ in range(20):
        motor.start(EfeitoLento(), 100)
        time.sleep(0.01)
    motor.stop()
    time.sleep(0.4)

    assert threading.active_count() == base
    assert motor.running is False
    assert motor.current is None


def test_engine_stop_sem_start_nao_quebra():
    motor = effects.Engine(TecladoFalso(), None)
    motor.stop()
    assert motor.running is False


def test_engine_serializa_escritas_ao_trocar_efeito_bloqueado():
    entrou = threading.Event()
    liberar = threading.Event()
    escritas = []
    simultaneas = 0
    maximo = 0
    class Teclado:
        def set_zones(self, colors, brightness):
            nonlocal simultaneas, maximo
            simultaneas += 1
            maximo = max(maximo, simultaneas)
            try:
                escritas.append(colors[0])
                if len(escritas) == 1:
                    entrou.set()
                    liberar.wait(3)
            finally:
                simultaneas -= 1
    class Efeito:
        def __init__(self, cor): self.cor = cor
        def frame(self, t, sensors): return [self.cor] * 4
    motor = effects.Engine(Teclado(), None)
    motor.start(Efeito((1, 1, 1)))
    assert entrou.wait(2)
    motor.start(Efeito((2, 2, 2)))
    liberar.set()
    deadline = time.monotonic() + 2
    while len(escritas) < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    motor.stop()
    assert maximo == 1
    assert escritas[0] == (1, 1, 1)
    assert escritas[1] == (2, 2, 2)


def test_sensor_de_temperatura_limita_leituras_do_sysfs(monkeypatch):
    from controlfanrgb import hardware

    leituras = []
    instante = [10.0]
    monkeypatch.setattr(hardware.time, "monotonic", lambda: instante[0])
    monkeypatch.setattr(hardware, "_find_hwmon", lambda name: "/fake")
    monkeypatch.setattr(hardware, "_read_int", lambda path: leituras.append(path) or 50000)
    sensors = hardware.Sensors()
    for _ in range(30):
        assert sensors.cpu_temp() == 50.0
    assert len(leituras) == 1
    instante[0] += 0.5
    sensors.cpu_temp()
    assert len(leituras) == 2


def test_brilho_de_efeito_nao_reinicia_thread():
    class Teclado:
        def __init__(self): self.brilhos = []
        def set_zones(self, colors, brightness): self.brilhos.append(brightness)
    class Efeito:
        def frame(self, t, sensors): return [(1, 2, 3)] * 4
    kb = Teclado()
    motor = effects.Engine(kb, None)
    motor.start(Efeito(), 30)
    thread = motor._thread
    deadline = time.monotonic() + 1
    while not kb.brilhos and time.monotonic() < deadline:
        time.sleep(.01)
    motor.set_brightness(80)
    deadline = time.monotonic() + 1
    while 80 not in kb.brilhos and time.monotonic() < deadline:
        time.sleep(.01)
    assert motor._thread is thread
    motor.stop()
    assert motor._thread is None
    assert thread is not None and 80 in kb.brilhos


def test_keyboard_fecha_primeiro_fd_se_segundo_falhar(monkeypatch):
    from controlfanrgb import hardware

    fechados = []
    def abrir(path, flags):
        if path == hardware.DYN_DEV:
            raise FileNotFoundError(path)
        return 42

    monkeypatch.setattr(hardware.os, "open", abrir)
    monkeypatch.setattr(hardware.os, "close", fechados.append)
    kb = hardware.Keyboard()
    with pytest.raises(hardware.KeyboardUnavailable):
        kb.open()
    assert fechados == [42]
    assert kb._static is None and kb._dyn is None


def test_idle_watcher_pode_reiniciar_depois_de_stop():
    from controlfanrgb.idle import IdleWatcher

    class Proxy:
        def __init__(self): self.desconectados = []
        def disconnect(self, sub): self.desconectados.append(sub)

    watcher = IdleWatcher(lambda idle: None)
    proxy = Proxy()
    watcher._proxy = proxy
    watcher._sub = 7
    watcher.stop()
    assert proxy.desconectados == [7]
    assert watcher._proxy is None


def test_estado_salvo_invalido_recupera_campos_sem_perder_validos():
    from controlfanrgb import daemon, validation

    raw = {"mode": "software", "software_effect": "inválido",
           "zones": [[1, 2, 3]], "brightness": 70,
           "firmware_mode": 999, "idle_blank": True}
    state = validation.normalize_state(raw, daemon.DEFAULT_STATE,
                                       {cls.nome for cls in effects.SOFTWARE_EFFECTS})
    assert state["mode"] == "zones"
    assert state["zones"] == daemon.DEFAULT_STATE["zones"]
    assert state["brightness"] == 70
    assert state["firmware_mode"] == daemon.DEFAULT_STATE["firmware_mode"]
    assert state["idle_blank"] is True


def test_daemon_rejeita_arrays_invalidos_antes_de_mexer_no_hardware():
    from controlfanrgb import daemon

    class Motor:
        def stop(self): raise AssertionError("não pode parar antes de validar")
    obj = daemon.Daemon.__new__(daemon.Daemon)
    obj.engine = Motor()
    with pytest.raises(ValueError):
        obj._dispatch("SetZones", ([[1, 2, 3]], 80))
    with pytest.raises(ValueError):
        obj._dispatch("SetAudioLevel", (0.5, [0.1] * 1000))


def test_off_preserva_perfil_e_apply_profile_reacende():
    from controlfanrgb import daemon

    class Motor:
        def stop(self): pass
    class Teclado:
        def __init__(self): self.apagou = False
        def off(self): self.apagou = True
    obj = daemon.Daemon.__new__(daemon.Daemon)
    obj.engine = Motor()
    obj.kb = Teclado()
    obj._powered = True
    obj.state = {"mode": "software", "software_effect": "Música"}
    aplicados = []
    obj._apply_state = lambda: aplicados.append(True)

    obj._dispatch("Off", ())
    assert obj.kb.apagou and not obj._powered
    assert obj.state["software_effect"] == "Música"
    obj._dispatch("ApplyProfile", ())
    assert obj._powered and aplicados == [True]


def test_gui_reaplica_efeito_sem_trocar_por_zonas(monkeypatch):
    from controlfanrgb import window

    chamadas = []
    class Backend:
        def start_effect(self, name): chamadas.append(("effect", name))
        def set_zones(self, *args): chamadas.append(("zones", args))
    class Button:
        def set_label(self, value): pass
        def remove_css_class(self, value): pass
        def add_css_class(self, value): pass

    w = types.SimpleNamespace(
        cfg={"mode": "software", "software_effect": "Música"},
        backend=Backend(), effect_rows={"Música": (None, Button(), effects.Music())},
        _preview_effect=effects.Music(),
        _refresh_preview=lambda: None, _set_power_state=lambda value: None,
        _toast=lambda msg: None)
    monkeypatch.setattr(window.config, "save", lambda cfg: None)
    assert window.Window._apply_current(w) is False
    assert chamadas == [("effect", "Música")]


def test_brilho_da_gui_nao_substitui_efeito(monkeypatch):
    from controlfanrgb import window

    chamadas = []
    class Backend:
        def set_brightness(self, value): chamadas.append(("brightness", value))
        def set_zones(self, *args): chamadas.append(("zones", args))
    class Botao:
        def get_active(self): return False
    class Preview:
        colors = [(1, 2, 3)] * 4
        def update(self, colors, brightness): pass
    w = types.SimpleNamespace(
        _applying=False, cfg={"brightness": 50}, backend=Backend(),
        power_btn=Botao(), preview=Preview(), _save_id=0,
        _toast=lambda msg: None, _save_config=lambda: None)
    monkeypatch.setattr(window.GLib, "timeout_add", lambda ms, cb: 9)
    window.Window._on_brightness(w, types.SimpleNamespace(get_value=lambda: 42))
    assert chamadas == [("brightness", 42)]
    assert w._save_id == 9


# --------------------------------------------- interruptor de energia ----
def test_set_power_state_nao_dispara_o_proprio_handler():
    """O botão de power era de mão única: só apagava. Virou interruptor, e aí
    surge o risco de laço — `_turn_on` chama `_apply_current`, que sincroniza
    o botão, que dispararia `_on_power` de novo."""
    from controlfanrgb.window import Window

    disparos = []

    class BotaoFalso:
        def __init__(self):
            self._ativo = False
            self.bloqueado = False
            self.tooltip = None

        def get_active(self):
            return self._ativo

        def set_active(self, v):
            self._ativo = v
            if not self.bloqueado:
                disparos.append(v)

        def handler_block(self, _h):
            self.bloqueado = True

        def handler_unblock(self, _h):
            self.bloqueado = False

        def set_tooltip_text(self, t):
            self.tooltip = t

    # Window é GObject e recusa object.__new__; o método usa só dois
    # atributos, então vai desacoplado, com um objeto comum no lugar de self.
    w = types.SimpleNamespace(power_btn=BotaoFalso(), _power_handler=1)

    Window._set_power_state(w, True)
    assert w.power_btn.get_active() is True
    assert w.power_btn.tooltip == "Acender o teclado"

    Window._set_power_state(w, False)
    assert w.power_btn.get_active() is False
    assert w.power_btn.tooltip == "Apagar o teclado"

    assert disparos == [], "sincronizar o botão disparou o handler — vira laço"


def test_set_power_state_e_idempotente():
    from controlfanrgb.window import Window

    class BotaoFalso:
        def __init__(self): self.escritas = 0; self._a = False
        def get_active(self): return self._a
        def set_active(self, v): self._a = v; self.escritas += 1
        def handler_block(self, _h): pass
        def handler_unblock(self, _h): pass
        def set_tooltip_text(self, t): pass

    w = types.SimpleNamespace(power_btn=BotaoFalso(), _power_handler=1)
    Window._set_power_state(w, False)      # já está nesse estado
    assert w.power_btn.escritas == 0


# ------------------------------------------ o motor não morre calado ------
def test_engine_relata_a_morte_em_vez_de_sumir():
    """`except OSError: break` mudo escondia a thread do efeito morrendo: o
    teclado congelava no último quadro e não havia nada no log. Sintoma
    relatado como "acende e depois apaga sozinho"."""
    avisos = []

    class TecladoQueFalha:
        def __init__(self): self.n = 0
        def set_zones(self, cores, brilho):
            self.n += 1
            if self.n > 2:
                raise OSError(5, "Input/output error")

    class EfeitoSimples:
        nome = "simples"
        def frame(self, t, sensors): return [(10, 20, 30)] * 4

    motor = effects.Engine(TecladoQueFalha(), None,
                           on_error=lambda e: avisos.append(e))
    motor.start(EfeitoSimples(), 100)
    for _ in range(60):
        if not motor.running:
            break
        time.sleep(0.05)

    assert motor.running is False, "a thread deveria ter saído"
    assert avisos, "a morte passou em silêncio"
    assert motor.last_error and "Input/output" in motor.last_error
    assert motor.died_at is not None


# ------------------------------------------- o efeito nunca fica preto ----
def test_musica_nunca_renderiza_preto_sem_audio():
    """Relatado como "o teclado apaga sozinho": sem som o efeito caía para
    v=0,05, ou ~12/255, que é preto na prática."""
    effects.AUDIO.push(0.0, [0.0, 0.0, 0.0, 0.0])
    effects.AUDIO._at = 0.0                 # finge que ninguém amostra
    efeito = effects.Music()

    for i in range(240):                    # 8 s a 30 fps
        quadros = efeito.frame(i / 30.0, None)
        for cor in quadros:
            assert max(cor) >= 40, f"quadro {i} quase preto: {cor}"


def test_musica_reage_ao_subir_o_audio():
    efeito = effects.Music()
    for i in range(120):                    # estabiliza em repouso
        efeito.frame(i / 30.0, None)
    calmo = max(max(c) for c in efeito.frame(4.0, None))

    effects.AUDIO.push(1.0, [1.0, 1.0, 1.0, 1.0])
    for i in range(30):
        alto = max(max(c) for c in efeito.frame(4.0 + i / 30.0, None))

    assert alto > calmo + 60, f"reagiu pouco: {calmo} -> {alto}"


def test_matrix_colunas_nao_pulsam_juntas():
    efeito = effects.Matrix()
    iguais = 0
    for i in range(300):
        q = efeito.frame(i / 30.0, None)
        if len({c for c in q}) == 1:
            iguais += 1
    assert iguais < 150, "as 4 zonas estão em uníssono demais"
