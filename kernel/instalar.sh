#!/bin/bash
# Cria o DKMS facer-1.2 a partir do facer-1.0 original.
#
# O 1.2 traz três coisas que o módulo de origem não tem neste modelo:
#   - turbo acessível do userspace, em sysfs
#   - leitura de RPM das ventoinhas (.predator_v4 na quirk do PH315-54)
#   - desligar o timeout de backlight do firmware, que apaga o teclado depois
#     de ~30 s sem tecla pressionada e ignora as escritas de cor
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "rode com sudo"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
SRC=/usr/src/facer-1.0
VER=1.2
DST=/usr/src/facer-$VER
PATCH=$(ls "$HERE"/*.patch)

[[ -d $SRC ]] || { echo "erro: $SRC não existe — instale o facer original antes"; exit 1; }

# Se o patch mudou, a árvore antiga não serve: refaz do zero. Sem isto, editar
# o patch não tinha efeito nenhum, porque o diretório já existia.
if [[ -d $DST ]] && [[ $PATCH -nt $DST/src/facer.c ]]; then
    echo "patch mais novo que a árvore — refazendo /usr/src/facer-$VER"
    dkms remove -m facer -v $VER --all 2>/dev/null || true
    rm -rf "$DST"
fi

if [[ ! -d $DST ]]; then
    cp -a "$SRC" "$DST"
    sed -i "s/^PACKAGE_VERSION=.*/PACKAGE_VERSION=\"$VER\"/" "$DST/dkms.conf"
    patch -d "$DST" -p1 < "$PATCH"
fi

dkms add -m facer -v $VER 2>/dev/null || true
dkms build -m facer -v $VER -k "$(uname -r)"
for velha in 1.0 1.1; do
    dkms uninstall -m facer -v $velha -k "$(uname -r)" 2>/dev/null || true
done
dkms install -m facer -v $VER -k "$(uname -r)"

install -m 0644 "$HERE/../data/99-controlfanrgb.rules" /etc/udev/rules.d/99-controlfanrgb.rules
udevadm control --reload-rules

echo
echo "feito. pare o daemon, troque o módulo e volte:"
echo "    sudo systemctl stop controlfanrgbd"
echo "    sudo modprobe -r facer && sudo modprobe facer"
echo "    sudo systemctl start controlfanrgbd"
