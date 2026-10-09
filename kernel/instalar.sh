#!/bin/bash
# Cria o DKMS facer-1.1 (fork com turbo em sysfs) a partir do facer-1.0.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "rode com sudo"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
SRC=/usr/src/facer-1.0
DST=/usr/src/facer-1.1

[[ -d $SRC ]] || { echo "erro: $SRC não existe — instale o facer original antes"; exit 1; }

if [[ ! -d $DST ]]; then
    cp -a "$SRC" "$DST"
    sed -i 's/^PACKAGE_VERSION="1.0"/PACKAGE_VERSION="1.1"/' "$DST/dkms.conf"
    patch -d "$DST" -p1 < "$HERE"/*.patch
fi

dkms add -m facer -v 1.1 2>/dev/null || true
dkms build -m facer -v 1.1 -k "$(uname -r)"
dkms uninstall -m facer -v 1.0 -k "$(uname -r)" 2>/dev/null || true
dkms install -m facer -v 1.1 -k "$(uname -r)"

install -m 0644 "$HERE/../data/99-controlfanrgb.rules" /etc/udev/rules.d/99-controlfanrgb.rules
udevadm control --reload-rules

echo
echo "feito. descarregue quem estiver usando o módulo e rode:"
echo "    sudo modprobe -r facer && sudo modprobe facer"
