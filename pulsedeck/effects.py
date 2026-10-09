"""Efeitos gerados por software.

O firmware tem 6 efeitos fixos. Como uma escrita custa ~0,07 ms, dá pra desenhar
qualquer coisa a 30-60 fps em userspace — é daqui que saem os efeitos que o
PredatorSense do Windows não tem.

O motor roda numa thread e chama `on_frame` pra UI poder espelhar as cores.
"""
import colorsys
import math
import threading
import time

FPS = 30


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


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


SOFTWARE_EFFECTS = [Rainbow, CpuLoad, Thermometer, Breathing]


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
