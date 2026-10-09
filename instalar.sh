#!/bin/bash
# Compila e instala em /usr com o Meson, e ativa os serviços.
#
# Esta é a única forma de instalar: não existe mais instalação "de
# desenvolvimento" com unidades apontando para o diretório do projeto, porque
# uma unidade em /etc sombreia a de /usr/lib sem avisar. Para desenvolver sem
# instalar, use `python3 run.py`.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo "não use sudo — o script chama sudo onde precisa"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

[[ -d build ]] || meson setup build --prefix=/usr
meson configure build --prefix=/usr >/dev/null
sudo meson install -C build

# o serviço antigo aplicava o perfil no boot e no resume — agora é o daemon
for unit in acer-rgb.service acer-rgb-resume.service; do
    if systemctl is-enabled "$unit" &>/dev/null; then
        echo "desativando $unit (o controlfanrgbd assume o boot/resume)"
        sudo systemctl disable --now "$unit" || true
    fi
done

sudo systemctl enable --now controlfanrgbd.service
systemctl --user enable --now controlfanrgb-tray.service
sleep 2
systemctl --no-pager --lines=5 status controlfanrgbd.service || true
