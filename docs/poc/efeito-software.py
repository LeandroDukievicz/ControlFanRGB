#!/usr/bin/env python3
"""Prova de conceito: efeitos de RGB gerados por SOFTWARE nas 4 zonas.

O firmware do Predator só tem 6 efeitos. Como escrever cor custa ~0,07 ms,
dá pra desenhar qualquer coisa em userspace. Isso aqui mostra três efeitos
que o PredatorSense do Windows não tem.

    python3 efeito-software.py arcoiris
    python3 efeito-software.py cpu          # zonas viram barra de carga da CPU
    python3 efeito-software.py termometro   # cor acompanha a temperatura

Ctrl+C restaura o perfil salvo (`acer-rgb apply`).

ATENÇÃO (pegadinha que me custou uns minutos): o /dev/acer-gkbbl-static-0 exige
EXATAMENTE 4 bytes por syscall. Se você usar open()/write() do Python, o buffer
junta várias escritas num write de 16 bytes, o driver recusa e o processo trava
em 100% de CPU. Por isso tudo aqui é os.write() em fd cru.
"""
import os, sys, time, math, colorsys, subprocess, signal

STATIC = "/dev/acer-gkbbl-static-0"
DYN    = "/dev/acer-gkbbl-0"
FPS    = 30

def abrir():
    try:
        return os.open(STATIC, os.O_WRONLY), os.open(DYN, os.O_WRONLY)
    except PermissionError:
        sys.exit("sem permissão nos /dev/acer-gkbbl-* — o módulo facer está carregado?")
    except FileNotFoundError:
        sys.exit("/dev/acer-gkbbl-* não existe — rode: sudo modprobe facer")

def desenhar(fd_s, fd_d, cores, brilho=100):
    """cores = lista de 4 tuplas (r,g,b). 4 writes + 1 commit."""
    for z, (r, g, b) in enumerate(cores):
        os.write(fd_s, bytes([1 << z, r & 255, g & 255, b & 255]))
    p = bytearray(16); p[2] = brilho; p[9] = 1
    os.write(fd_d, bytes(p))

def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)

# ------------------------------------------------------------------ efeitos --
def arcoiris(t):
    return [hsv(t * 0.15 + z * 0.08) for z in range(4)]

_prev = [0, 0]
def _carga_cpu():
    """% de uso agregado da CPU entre duas chamadas, lendo /proc/stat."""
    global _prev
    campos = list(map(int, open("/proc/stat").readline().split()[1:]))
    ocioso, total = campos[3] + campos[4], sum(campos)
    d_oc, d_tt = ocioso - _prev[0], total - _prev[1]
    _prev = [ocioso, total]
    return 0.0 if d_tt <= 0 else max(0.0, min(1.0, 1 - d_oc / d_tt))

def cpu(t):
    """As 4 zonas viram uma barra: acende da esquerda pra direita conforme a carga."""
    carga = _carga_cpu()
    cores = []
    for z in range(4):
        limiar = z / 4
        if carga > limiar:
            cheio = min(1.0, (carga - limiar) * 4)
            cores.append(hsv(0.33 - 0.33 * (z / 3), 1.0, 0.25 + 0.75 * cheio))
        else:
            cores.append((6, 8, 14))
    return cores

def _temp_cpu():
    for base in ("/sys/class/hwmon/hwmon5", "/sys/class/hwmon/hwmon4"):
        try:
            with open(base + "/temp1_input") as f:
                return int(f.read()) / 1000
        except OSError:
            continue
    return 50.0

def termometro(t):
    c = _temp_cpu()
    # 40 °C = azul (0.6) → 90 °C = vermelho (0.0)
    h = max(0.0, min(0.6, 0.6 * (1 - (c - 40) / 50)))
    pulso = 1.0 if c < 85 else 0.55 + 0.45 * math.sin(t * 9)
    return [hsv(h, 1.0, pulso)] * 4

EFEITOS = {"arcoiris": arcoiris, "cpu": cpu, "termometro": termometro}

def main():
    nome = sys.argv[1] if len(sys.argv) > 1 else "arcoiris"
    if nome not in EFEITOS:
        sys.exit(f"efeitos: {', '.join(EFEITOS)}")
    efeito = EFEITOS[nome]

    # sem isso um `timeout`/`kill` mata o processo antes do finally e o efeito
    # fica rodando órfão — aconteceu aqui, o teclado ficou em arco-íris por 40 min
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    signal.signal(signal.SIGHUP, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    fd_s, fd_d = abrir()
    print(f"rodando '{nome}' a {FPS} fps — Ctrl+C pra parar")
    t0, frames = time.perf_counter(), 0
    try:
        while True:
            t = time.perf_counter() - t0
            desenhar(fd_s, fd_d, efeito(t))
            frames += 1
            time.sleep(1 / FPS)
    except KeyboardInterrupt:
        dur = time.perf_counter() - t0
        print(f"\n{frames} frames em {dur:.1f}s ({frames/dur:.1f} fps) — restaurando perfil")
    finally:
        os.close(fd_s); os.close(fd_d)
        subprocess.run(["acer-rgb", "apply"], capture_output=True)

if __name__ == "__main__":
    main()
