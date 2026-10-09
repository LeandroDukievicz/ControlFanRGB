#!/bin/bash
# Instala o ícone de bandeja como serviço de usuário. NÃO use sudo.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo "não use sudo — o tray é da sua sessão"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNITS"

sed "s|__EXEC__|/usr/bin/python3 $HERE/pulsedeck-tray.py|" \
    "$HERE/data/pulsedeck-tray.service" > "$UNITS/pulsedeck-tray.service"

systemctl --user daemon-reload
systemctl --user enable --now pulsedeck-tray.service
sleep 2
systemctl --user --no-pager --lines=5 status pulsedeck-tray.service || true
