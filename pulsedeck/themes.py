"""Temas prontos: 4 cores, uma por zona (da esquerda pra direita)."""

def _hex(*codes):
    return [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in codes]


THEMES = {
    "Vapor":   _hex("ff2d6f", "b14aed", "4f7cff", "2de2ff"),
    "Matrix":  _hex("39ff14", "0aff9d", "00e0ff", "0066ff"),
    "Inferno": _hex("ff0040", "ff6a00", "ffd000", "ff3b00"),
    "Glacial": _hex("00e5ff", "2979ff", "7c4dff", "00e5ff"),
    "Âmbar":   _hex("ffe8c2", "ffd089", "ffb347", "ff8c42"),
    "Brasil":  _hex("009b3a", "ffdf00", "002776", "009b3a"),
    "Branco":  _hex("ffffff", "ffffff", "ffffff", "ffffff"),
}
