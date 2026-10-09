#!/bin/bash
# Registra os atalhos globais do GNOME. Roda como usuário, NÃO com sudo.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo "não use sudo — os atalhos são da sua sessão"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
B=org.gnome.settings-daemon.plugins.media-keys
PREFIX=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings

add() {  # add <slug> <nome> <tecla> <argumentos do run.py>
    local path="$PREFIX/$1/"
    gsettings set "$B.custom-keybinding:$path" name "$2"
    gsettings set "$B.custom-keybinding:$path" binding "$3"
    gsettings set "$B.custom-keybinding:$path" command "/usr/bin/python3 $HERE/run.py $4"
    echo "  $3 → $2"
}

add controlfanrgb-turbo "ControlFanRGB: turbo"  "<Super>t" "--turbo toggle"
add controlfanrgb-off   "ControlFanRGB: apagar" "<Super>k" "--off"

gsettings set $B custom-keybindings \
    "['$PREFIX/controlfanrgb-turbo/', '$PREFIX/controlfanrgb-off/']"

echo "atalhos registrados. remova com ./desinstalar-atalhos.sh"
