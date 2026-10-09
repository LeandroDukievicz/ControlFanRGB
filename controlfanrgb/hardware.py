"""Camada de hardware: tudo que toca nos /dev e no hwmon mora aqui.

Mantida sem nenhuma dependência de GTK de propósito — é esta classe que vai virar
o `controlfanrgbd` depois, sem reescrita.

Protocolo do Acer Predator (4 zonas), descoberto por engenharia reversa do módulo
`facer`. Não está documentado em lugar nenhum, então fica registrado aqui:

    /dev/acer-gkbbl-static-0   4 bytes:  [bitmask_zona, R, G, B]
                               bitmask: 0b0001=zona1 … 0b1000=zona4 (combinável)
    /dev/acer-gkbbl-0         16 bytes:  [modo, velocidade, brilho, 8_se_onda,
                                          direção, R, G, B, 0, 1(commit), 0…]

CUIDADO: o device estático exige EXATAMENTE 4 bytes por syscall. Se a escrita for
bufferizada (open()/write() do Python junta writes pequenos num de 16 bytes), o
driver recusa e o processo trava em 100% de CPU num loop de retry. Por isso tudo
aqui usa os.write() em fd cru.
"""
import glob
import os

STATIC_DEV = "/dev/acer-gkbbl-static-0"
TURBO_SYSFS = "/sys/devices/platform/acer-wmi/turbo"
DYN_DEV = "/dev/acer-gkbbl-0"
ZONES = 4

# modos do firmware — os índices são os que o driver espera
STATIC, BREATH, NEON, WAVE, SHIFTING, ZOOM = range(6)

MODE_NAMES = {
    STATIC: "Estático",
    BREATH: "Respiração",
    NEON: "Neon",
    WAVE: "Onda",
    SHIFTING: "Shifting",
    ZOOM: "Zoom",
}
# modos em que a cor escolhida pelo usuário importa
MODES_WITH_COLOR = (STATIC, BREATH, SHIFTING, ZOOM)

RIGHT_TO_LEFT, LEFT_TO_RIGHT = 1, 2


class KeyboardUnavailable(Exception):
    """Os /dev não existem ou não têm permissão — módulo facer provavelmente fora."""


class Keyboard:
    """Controla o backlight. Abre os fds uma vez e reusa (escrita custa ~0,07 ms)."""

    def __init__(self):
        self._static = None
        self._dyn = None

    # ---------------------------------------------------------------- ciclo --
    @staticmethod
    def available():
        return all(os.path.exists(p) for p in (STATIC_DEV, DYN_DEV))

    def open(self):
        if self._static is not None:
            return
        try:
            self._static = os.open(STATIC_DEV, os.O_WRONLY)
            self._dyn = os.open(DYN_DEV, os.O_WRONLY)
        except FileNotFoundError as e:
            raise KeyboardUnavailable(
                "os devices do teclado não existem — rode: sudo modprobe facer") from e
        except PermissionError as e:
            raise KeyboardUnavailable(
                f"sem permissão em {STATIC_DEV}") from e

    def close(self):
        for fd in (self._static, self._dyn):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._static = self._dyn = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # --------------------------------------------------------------- escrita --
    def _commit(self, payload):
        self.open()
        os.write(self._dyn, bytes(payload))

    def set_zones(self, colors, brightness=100):
        """colors: 4 tuplas (r,g,b), da esquerda pra direita. 4 writes + 1 commit."""
        self.open()
        for zone, (r, g, b) in enumerate(colors[:ZONES]):
            os.write(self._static,
                     bytes([1 << zone, r & 0xFF, g & 0xFF, b & 0xFF]))
        payload = bytearray(16)
        payload[2] = _clamp(brightness, 0, 100)
        payload[9] = 1
        self._commit(payload)

    def set_effect(self, mode, speed=5, brightness=100,
                   direction=RIGHT_TO_LEFT, color=(0, 255, 255)):
        """Dispara um dos 6 efeitos do firmware. Para STATIC prefira set_zones()."""
        r, g, b = color
        payload = bytearray(16)
        payload[0] = mode
        payload[1] = _clamp(speed, 0, 9)
        payload[2] = _clamp(brightness, 0, 100)
        payload[3] = 8 if mode == WAVE else 0   # o firmware exige esse 8 na onda
        payload[4] = direction
        payload[5], payload[6], payload[7] = r & 0xFF, g & 0xFF, b & 0xFF
        payload[9] = 1
        self._commit(payload)

    def off(self):
        """Apaga sem perder o perfil — é só brilho 0."""
        self.set_effect(WAVE, brightness=0)


class Sensors:
    """Leitura de ventoinhas e temperatura. Nada aqui escreve."""

    def __init__(self):
        self._acer = _find_hwmon("acer")
        self._coretemp = _find_hwmon("coretemp")

    @property
    def fans_available(self):
        return self._acer is not None

    def fans(self):
        """(rpm_cpu, rpm_gpu) ou None.

        Só existe se o módulo facer foi carregado com a capability de leitura de
        ventoinha. Na quirk atual do PH315-54 ela vem desligada — ver fase 0 do
        roadmap, que corrige a quirk.
        """
        if self._acer is None:
            self._acer = _find_hwmon("acer")      # pode ter aparecido depois
            if self._acer is None:
                return None
        cpu = _read_int(f"{self._acer}/fan1_input")
        gpu = _read_int(f"{self._acer}/fan2_input")
        return None if cpu is None else (cpu, gpu or 0)

    def cpu_temp(self):
        """°C ou None."""
        if self._coretemp is None:
            return None
        milli = _read_int(f"{self._coretemp}/temp1_input")
        return None if milli is None else milli / 1000.0


# ----------------------------------------------------------------- helpers --
def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


def _find_hwmon(name):
    for path in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(f"{path}/name") as f:
                if f.read().strip() == name:
                    return path
        except OSError:
            continue
    return None


def _read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class Turbo:
    """Modo turbo: ventoinhas no máximo + overclock.

    Exige o módulo `facer` 1.1+ (o fork deste projeto). O facer original só
    alcança o turbo pelo handler da tecla física do chassi — não existe
    interface de userspace nenhuma nele.

    A escrita sem root depende da regra udev `99-controlfanrgb.rules`.
    """

    @staticmethod
    def available():
        return os.path.exists(TURBO_SYSFS)

    @staticmethod
    def writable():
        return os.access(TURBO_SYSFS, os.W_OK)

    @staticmethod
    def get():
        """True/False, ou None se o módulo não expõe o turbo."""
        try:
            with open(TURBO_SYSFS) as f:
                return f.read().strip() == "1"
        except OSError:
            return None

    @staticmethod
    def set(on):
        try:
            with open(TURBO_SYSFS, "w") as f:
                f.write("1" if on else "0")
        except PermissionError as e:
            raise KeyboardUnavailable(
                "sem permissão para escrever no turbo — falta a regra udev "
                "99-controlfanrgb.rules") from e
        except OSError as e:
            raise KeyboardUnavailable(
                "turbo indisponível — o módulo facer precisa ser o 1.1+") from e

    @staticmethod
    def toggle():
        state = Turbo.get()
        if state is None:
            raise KeyboardUnavailable("turbo indisponível")
        Turbo.set(not state)
        return not state
