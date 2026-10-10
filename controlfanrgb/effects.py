"""Efeitos gerados por software.

O firmware tem 6 efeitos fixos. Como uma escrita custa ~0,07 ms, dá pra desenhar
qualquer coisa a 30-60 fps em userspace — é daqui que saem os efeitos que o
PredatorSense do Windows não tem.

O motor roda numa thread e chama `on_frame` pra UI poder espelhar as cores.
"""
import colorsys
import math
import random
import threading
import time

FPS = 30


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# -------------------------------------------------------------------- áudio --
class AudioState:
    """Níveis de áudio empurrados de fora, para o efeito reativo.

    O motor roda no daemon, que é de sistema e não alcança o PipeWire do
    usuário — o socket vive em `$XDG_RUNTIME_DIR`, e um serviço de root lendo
    o áudio de quem está logado seria a arquitetura errada. Então quem amostra
    é o processo de sessão (o tray, via `audio.Sampler`) e o que cruza o D-Bus
    são cinco números, nunca áudio.

    Se a fonte parar de empurrar, `fresh` fica falso e o efeito cai num modo
    discreto em vez de congelar no último quadro.
    """

    STALE_AFTER = 1.5          # segundos sem notícia = sem áudio

    def __init__(self):
        self.level = 0.0
        self.bands = [0.0, 0.0, 0.0, 0.0]
        self._at = 0.0

    def push(self, level, bands):
        self.level = max(0.0, min(1.0, float(level)))
        self.bands = [max(0.0, min(1.0, float(b))) for b in bands]
        self._at = time.monotonic()

    @property
    def fresh(self):
        return (time.monotonic() - self._at) < self.STALE_AFTER

    def read(self):
        if not self.fresh:
            return 0.0, [0.0, 0.0, 0.0, 0.0]
        return self.level, list(self.bands)


AUDIO = AudioState()


# ------------------------------------------------------------------ efeitos --
class Rainbow:
    nome = "Arco-íris"
    descricao = "Espectro completo correndo pelas 4 zonas"

    def frame(self, t, sensors):
        return [hsv(t * 0.15 + z * 0.08) for z in range(4)]


class CpuLoad:
    nome = "Carga da CPU"
    descricao = "As zonas viram uma barra: acende conforme a CPU sobe"

    def __init__(self):
        self._prev = None

    def _load(self):
        with open("/proc/stat") as f:
            fields = list(map(int, f.readline().split()[1:]))
        idle, total = fields[3] + fields[4], sum(fields)
        if self._prev is None:
            self._prev = (idle, total)
            return 0.0
        d_idle, d_total = idle - self._prev[0], total - self._prev[1]
        self._prev = (idle, total)
        if d_total <= 0:
            return 0.0
        return max(0.0, min(1.0, 1 - d_idle / d_total))

    def frame(self, t, sensors):
        load = self._load()
        out = []
        for z in range(4):
            floor = z / 4
            if load > floor:
                fill = min(1.0, (load - floor) * 4)
                out.append(hsv(0.33 - 0.33 * (z / 3), 1.0, 0.25 + 0.75 * fill))
            else:
                out.append((6, 8, 14))
        return out


class Thermometer:
    nome = "Termômetro"
    descricao = "Azul a 40 °C, vermelho a 90 °C — pulsa acima de 85 °C"

    def frame(self, t, sensors):
        c = sensors.cpu_temp() or 50.0
        h = max(0.0, min(0.6, 0.6 * (1 - (c - 40) / 50)))
        pulse = 1.0 if c < 85 else 0.55 + 0.45 * math.sin(t * 9)
        return [hsv(h, 1.0, pulse)] * 4


class Breathing:
    nome = "Respiração suave"
    descricao = "Mais lenta e com gradiente — a do firmware é dura demais"

    def __init__(self, base=(255, 45, 111)):
        self.base = base

    def frame(self, t, sensors):
        out = []
        for z in range(4):
            v = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 1.4 - z * 0.45))
            out.append(tuple(int(c * v) for c in self.base))
        return out


class Matrix:
    nome = "Matrix"
    descricao = "Chuva de código: cada zona é uma coluna que acende e decai"

    GREEN = (57, 255, 20)      # #39ff14, o verde do filme
    HEAD = (205, 255, 205)     # a cabeça do rastro é quase branca
    FLOOR = (0, 10, 2)         # nunca apaga de vez: teclado preto parece defeito
    DECAY = 2.6                # queda por segundo

    def __init__(self):
        # Cada zona é uma coluna independente, com fase e ritmo próprios —
        # é o que impede as quatro de pulsarem juntas e parecer respiração.
        self._level = [random.random() for _ in range(4)]
        self._next = [random.uniform(0.0, 1.2) for _ in range(4)]
        self._last_t = 0.0

    def frame(self, t, sensors):
        dt = max(0.0, min(0.25, t - self._last_t))
        self._last_t = t
        out = []
        for z in range(4):
            self._next[z] -= dt
            if self._next[z] <= 0.0:
                self._level[z] = 1.0
                self._next[z] = random.uniform(0.35, 1.9)
            else:
                self._level[z] *= math.exp(-self.DECAY * dt)

            lv = self._level[z]
            c = [int(ch * lv) for ch in self.GREEN]
            if lv > 0.82:                       # clareia na cabeça
                f = (lv - 0.82) / 0.18
                c = [int(c[i] + (self.HEAD[i] - c[i]) * f) for i in range(3)]
            out.append(tuple(max(c[i], self.FLOOR[i]) for i in range(3)))
        return out


class Music:
    nome = "Música"
    descricao = ("Reage ao som que está tocando: graves à esquerda, "
                 "agudos à direita")

    # Uma cor por banda, da esquerda para a direita do teclado.
    HUES = (0.95, 0.78, 0.50, 0.33)     # rosa, violeta, ciano, verde

    def frame(self, t, sensors):
        level, bands = AUDIO.read()

        if not AUDIO.fresh:
            # Ninguém está amostrando (tray desligado, ou nada tocando ainda).
            # Uma respiração fraca comunica "esperando" melhor que apagado.
            v = 0.07 + 0.06 * (0.5 + 0.5 * math.sin(t * 1.6))
            return [hsv(0.58, 0.55, v)] * 4

        out = []
        for z in range(4):
            e = bands[z] if z < len(bands) else level
            v = 0.05 + 0.95 * e
            # Satura menos no pico: o brilho "estoura" para o branco em vez de
            # saturar na cor e perder a sensação de ataque.
            s = 1.0 - 0.4 * e
            out.append(hsv(self.HUES[z] + 0.03 * math.sin(t * 0.3), s, v))
        return out


SOFTWARE_EFFECTS = [Rainbow, Matrix, Music, CpuLoad, Thermometer, Breathing]


# ------------------------------------------------------------------- motor --
class Engine:
    """Roda um efeito numa thread. Só um por vez."""

    def __init__(self, keyboard, sensors, on_frame=None):
        self._kb = keyboard
        self._sensors = sensors
        self._on_frame = on_frame
        self._thread = None
        self._stop = threading.Event()
        self.current = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, effect, brightness=100):
        self.stop()
        self.current = effect
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(effect, brightness), daemon=True)
        self._thread.start()

    def stop(self):
        if not self.running:
            self.current = None
            return
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._thread = None
        self.current = None

    def _loop(self, effect, brightness):
        t0 = time.perf_counter()
        while not self._stop.is_set():
            t = time.perf_counter() - t0
            try:
                colors = effect.frame(t, self._sensors)
                self._kb.set_zones(colors, brightness)
            except OSError:
                break          # device sumiu (módulo descarregado) — sai limpo
            if self._on_frame:
                self._on_frame(colors)
            self._stop.wait(1 / FPS)
