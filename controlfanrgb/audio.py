"""Amostragem do áudio que está tocando, para o efeito reativo.

Roda no **processo de sessão** (o tray), nunca no daemon: o daemon é de
sistema e não alcança o PipeWire do usuário, cujo socket vive em
`$XDG_RUNTIME_DIR`. E um serviço de root lendo o áudio de quem está logado
seria a arquitetura errada mesmo que fosse possível. Daqui saem só números —
nível geral e quatro bandas — que o tray entrega ao daemon por D-Bus.

A captura usa `stream.capture.sink=true`, que é o que faz o PipeWire entregar
o *monitor* do sink: o que está saindo pelas caixas, e não o microfone.
"""
import subprocess
import threading

# O numpy entra só aqui, e de forma opcional: o tray importa este módulo, e
# derrubar o ícone de bandeja inteiro porque falta uma dependência usada por
# um único efeito seria desproporcional. Sem numpy, `available()` diz não e o
# efeito de música cai no modo "esperando".
try:
    import numpy as np
except ImportError:                     # pragma: no cover
    np = None

RATE = 48000
CHUNK = 2048                 # ~43 ms → ~23 atualizações por segundo
SILENCE_RMS = 0.0015         # abaixo disto é silêncio, não sinal fraco
# Banda com menos de 0,2% da potência da banda mais forte é vazamento
# espectral, não conteúdo. Sem este corte o ganho por banda amplifica o
# vazamento e um grave puro acende os agudos (medido: zona 4 em 0,35 num tom
# de 80 Hz). O limite é baixo porque com janela de Hann os lóbulos laterais
# caem muito rápido — 8% chegava a apagar um agudo legítimo tocando junto com
# um grave.
BAND_GATE = 0.002

# Quatro faixas, uma por zona do teclado, em Hz. Os limites crescem de forma
# aproximadamente logarítmica porque é assim que se ouve: a diferença entre
# 100 e 200 Hz pesa o mesmo que entre 3 k e 6 k.
BANDS = ((20, 160), (160, 800), (800, 3200), (3200, 16000))

# ---------------------------------------------------- dinâmica da resposta --
# O ganho automático normaliza cada banda pelo próprio pico recente. Só isso
# não basta: tudo tende a 1 e as quatro zonas ficam no máximo o tempo todo —
# que foi exatamente o sintoma de "sem dinamicidade" (medido com música real:
# bandas em 0,75 / 0,89 / 0,86 / 0,95, praticamente coladas).
#
# CLAMP é o expansor que resolve: o que está abaixo dele vira 0 e o resto é
# reescalado para 0..1. É ele que cria o contraste entre a batida e o resto.
# Os valores vêm de uma varredura medida com uma faixa de batida a 2,2 Hz,
# olhando mediana, desvio padrão e quanto tempo a zona passa baixa:
#
#   clamp release  mediana  desvio   max   %<0,25
#    0,35   0,12     0,63    0,198   0,97     1,2   <- sem dinâmica, tudo aceso
#    0,50   0,25     0,39    0,315   0,99    40,6   <- escolhido
#    0,50   0,40     0,20    0,337   0,99    56,6   <- escuro mais da metade
#
# Um release baixo era o defeito principal: 0,12 por quadro dá constante de
# ~360 ms, e a batida tem período de 455 ms, então o envelope não descia entre
# as batidas e tudo virava um borrão claro.
CLAMP = 0.50
CURVE = 0.5                  # expoente sobre a potência normalizada
PEAK_DECAY = 0.96            # ~1 s de memória (antes 0,99 ≈ 3 s, grudava alto)

# Envelope por banda: sobe rápido para a batida estalar, cai mais devagar para
# dar o tombo — mas não tão devagar que apague o contraste.
ATTACK = 0.60
RELEASE = 0.25


class Sampler:
    """Lê o monitor do sink e chama `on_data(level, bands)` ~23 vezes/s.

    `on_data` é chamado da thread do amostrador, não da main loop — quem
    recebe precisa ser rápido ou repassar para a sua própria loop.
    """

    def __init__(self, on_data, rate=RATE, chunk=CHUNK):
        self._on_data = on_data
        self._rate = rate
        self._chunk = chunk
        self._stop = threading.Event()
        self._proc_lock = threading.Lock()
        self._thread = None
        self._proc = None
        self.last_error = None

    @staticmethod
    def available():
        if np is None:
            return False
        try:
            subprocess.run(["pw-record", "--help"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=3, check=False)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return not self._stop.is_set()
        if not self.available():
            self.last_error = ("numpy ausente" if np is None
                               else "pw-record não encontrado (pipewire-bin)")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        with self._proc_lock:
            proc = self._proc
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive() and proc is not None and proc.poll() is None:
                proc.kill()
                self._thread.join(timeout=2)
            if not self._thread.is_alive():
                self._thread = None

    # ---------------------------------------------------------------------
    def _spawn(self):
        return subprocess.Popen(
            ["pw-record", "--raw", f"--rate={self._rate}", "--channels=1",
             "--format=s16", "-P", "{ stream.capture.sink=true }", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _read_exact(self, stream, n):
        """Pipe entrega em pedaços; sem isto os quadros saem desalinhados."""
        buf = bytearray()
        while len(buf) < n and not self._stop.is_set():
            part = stream.read(n - len(buf))
            if not part:
                return None
            buf.extend(part)
        return bytes(buf) if len(buf) == n else None

    def _loop(self):
        try:
            proc = self._spawn()
        except OSError as e:
            self.last_error = str(e)
            return

        with self._proc_lock:
            self._proc = proc

        try:
            self._sample(proc)
        finally:
            if proc.stdout is not None:
                proc.stdout.close()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            with self._proc_lock:
                if self._proc is proc:
                    self._proc = None

    def _sample(self, proc):

        window = np.hanning(self._chunk).astype(np.float32)
        freqs = np.fft.rfftfreq(self._chunk, 1.0 / self._rate)
        idx = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in BANDS]
        # Ganho automático **por banda**, não global. Com uma referência só, o
        # grave (banda estreita, energia concentrada) empurra o pico para cima
        # e os agudos — espalhados por 3,2-16 kHz, onde a média dilui — nunca
        # acendem. Medido com tons puros: banda única dava 1,00 no grave e
        # 0,11 no agudo; por banda, cada zona reage ao seu próprio conteúdo.
        peaks = np.full(len(BANDS), 1e-3, dtype=np.float64)
        env = np.zeros(len(BANDS), dtype=np.float64)
        total_peak = 1e-3

        while not self._stop.is_set():
            raw = self._read_exact(proc.stdout, self._chunk * 2)
            if raw is None:
                break

            x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(x * x)))

            if rms < SILENCE_RMS:
                # Decai o envelope em vez de cortar para zero: um corte seco
                # faz o teclado piscar nas pausas da música.
                env *= (1.0 - RELEASE)
                self._emit(0.0, env.tolist())
                continue

            # Soma de potência, não média: a média divide pela quantidade de
            # bins, e as bandas têm larguras muito diferentes (140 Hz na
            # primeira, 12,8 kHz na última). Com média, dois tons de mesma
            # amplitude davam energias 20x diferentes só pela largura da
            # banda, e qualquer comparação entre bandas ficava sem sentido.
            power = np.square(np.abs(np.fft.rfft(x * window)))
            energy = np.array(
                [float(power[i].sum()) if i.size else 0.0 for i in idx])
            energy[energy < energy.max() * BAND_GATE] = 0.0
            peaks = np.maximum(peaks * PEAK_DECAY, np.maximum(energy, 1e-3))

            norm = np.minimum(1.0, (energy / peaks) ** CURVE)
            # Expansor: rodapé a zero e o resto reescalado. É o que separa a
            # batida do ruído de fundo em vez de deixar tudo aceso.
            norm = np.clip((norm - CLAMP) / (1.0 - CLAMP), 0.0, 1.0)

            rising = norm > env
            env = np.where(rising,
                           env + (norm - env) * ATTACK,
                           env + (norm - env) * RELEASE)

            # O nível geral recebe o mesmo tratamento. Antes era rms*8, que
            # saturava em 1,0 em qualquer música e não informava nada.
            total = float(energy.sum())
            total_peak = max(total_peak * PEAK_DECAY, total, 1e-3)
            level = min(1.0, (total / total_peak) ** CURVE)
            level = max(0.0, (level - CLAMP) / (1.0 - CLAMP))

            self._emit(level, env.tolist())

        if not self._stop.is_set():
            self.last_error = "pw-record encerrou sozinho"

    def _emit(self, level, bands):
        try:
            self._on_data(level, bands)
        except Exception as e:                      # noqa: BLE001
            self.last_error = f"callback falhou: {e!r}"
