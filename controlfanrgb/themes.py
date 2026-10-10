"""Temas prontos: 4 cores, uma por zona (da esquerda pra direita).

As paletas de marca (Dracula, Cyberpunk) usam os valores oficiais, não
aproximações — a graça é o teclado ficar igual ao editor ou ao jogo.
"""

def _hex(*codes):
    return [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in codes]


THEMES = {
    "Vapor":     _hex("ff2d6f", "b14aed", "4f7cff", "2de2ff"),

    # Paleta oficial do Dracula (draculatheme.com): roxo, rosa, ciano e verde,
    # que é a sequência de destaque que todo mundo reconhece do tema.
    "Dracula":   _hex("bd93f9", "ff79c6", "8be9fd", "50fa7b"),

    # Cyberpunk 2077: o amarelo #fcee0a é a cor da marca; o resto é o neon
    # magenta/ciano/violeta dos letreiros do jogo.
    "Cyberpunk": _hex("fcee0a", "ff003c", "00f0ff", "b026ff"),

    # Steampunk não tem paleta canônica, então vai o metal: latão, cobre e
    # bronze, fechando no verdete — o verde do cobre oxidado, que é o que
    # separa isto do tema Âmbar em vez de virar outro degradê laranja.
    "Steampunk": _hex("d4af37", "c87533", "a0522d", "4f8f7f"),

    "Matrix":    _hex("39ff14", "0aff9d", "00e0ff", "0066ff"),
    "Summer":    _hex("ff0040", "ff6a00", "ffd000", "ff3b00"),
    "Glacial":   _hex("00e5ff", "2979ff", "7c4dff", "00e5ff"),
    "Âmbar":     _hex("ffe8c2", "ffd089", "ffb347", "ff8c42"),
    "Brasil":    _hex("009b3a", "ffdf00", "002776", "009b3a"),
    "Branco":    _hex("ffffff", "ffffff", "ffffff", "ffffff"),
}

# "Inferno" virou "Summer". Quem tinha o nome antigo salvo na configuração
# continua funcionando em vez de tomar KeyError.
ALIASES = {"Inferno": "Summer"}


def resolve(name):
    """Nome do tema, aceitando os que foram renomeados."""
    return ALIASES.get(name, name)
