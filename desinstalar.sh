#!/bin/bash
# Remove a instalação feita pelo instalar.sh e devolve o boot/resume ao
# acer-rgb.service antigo. O perfil salvo em /var/lib/controlfanrgb fica.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo "não use sudo — o script chama sudo onde precisa"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

systemctl --user disable --now controlfanrgb-tray.service 2>/dev/null || true
sudo systemctl disable --now controlfanrgbd.service 2>/dev/null || true

if [[ -d build ]]; then
    sudo ninja -C build uninstall
else
    echo "sem diretório build/ — nada a desinstalar pelo Meson." >&2
    echo "recrie com 'meson setup build --prefix=/usr' e rode de novo." >&2
    exit 1
fi

sudo systemctl daemon-reload
sudo udevadm control --reload-rules

for unit in acer-rgb.service acer-rgb-resume.service; do
    sudo systemctl enable "$unit" 2>/dev/null || true
done
echo "removido. o acer-rgb.service voltou a cuidar do boot."
