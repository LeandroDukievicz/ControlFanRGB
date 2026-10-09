"""Valores definidos no momento da instalação.

Este arquivo é o de **desenvolvimento**, usado quando se roda direto do
repositório com `python3 run.py`. O Meson instala no seu lugar uma versão
gerada de `build_info.py.in`, com a versão real e o caminho do executável.
"""

VERSION = "dev"

# None significa "descobrir o run.py ao lado do pacote". Na instalação isto
# vira o caminho absoluto de /usr/bin/controlfanrgb.
GUI_COMMAND = None
