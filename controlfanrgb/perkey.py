"""Resolução de um mapa tecla-a-tecla para as 4 zonas físicas.

O PH315-54 tem 4 zonas e ponto — nem o PredatorSense do Windows faz per-key
nesse modelo. Então o app deixa você pintar tecla a tecla e resolve a cor de
cada zona antes de escrever no driver.

A média considera **apenas as teclas pintadas** de cada zona, não todas. Se
você pintar só o WASD de vermelho, a zona 1 fica vermelha — que é o que se
espera. Se a média incluísse as teclas não pintadas, a zona sairia quase
apagada e o resultado pareceria um bug.
"""
from .keyboardview import KEYS

ZONES = 4


def resolve_zones(key_colors, base=(0, 0, 0)):
    """{id_da_tecla: (r,g,b)} -> lista de 4 cores, uma por zona."""
    buckets = [[] for _ in range(ZONES)]
    for key_id, color in key_colors.items():
        key = KEYS.get(key_id)
        if key is not None:
            buckets[key["zone"]].append(color)

    out = []
    for painted in buckets:
        if not painted:
            out.append(tuple(base))
            continue
        n = len(painted)
        out.append(tuple(sum(c[i] for c in painted) // n for i in range(3)))
    return out


def fill_all(color):
    """Pinta o teclado inteiro de uma cor só."""
    return {key_id: tuple(color) for key_id in KEYS}


def zone_counts(key_colors):
    """Quantas teclas pintadas há em cada zona — usado no rótulo da UI."""
    counts = [0] * ZONES
    for key_id in key_colors:
        key = KEYS.get(key_id)
        if key is not None:
            counts[key["zone"]] += 1
    return counts
