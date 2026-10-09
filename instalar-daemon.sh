#!/bin/bash
# Instala o pulsedeckd como serviço de sistema, rodando a partir deste
# diretório (instalação de desenvolvimento — o pacote final copia para /usr).
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "rode com sudo"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)

install -m 0644 "$HERE/data/io.github.leandrodukievicz.PulseDeck1.conf" \
    /etc/dbus-1/system.d/io.github.leandrodukievicz.PulseDeck1.conf

sed "s|__EXEC__|/usr/bin/python3 $HERE/pulsedeckd.py|" \
    "$HERE/data/pulsedeckd.service" > /etc/systemd/system/pulsedeckd.service

install -d -m 0755 /var/lib/pulsedeck

systemctl daemon-reload
systemctl reload dbus 2>/dev/null || systemctl reload dbus-broker 2>/dev/null || true

# o serviço antigo aplicava o perfil no boot e no resume — agora é o daemon
for unit in acer-rgb.service acer-rgb-resume.service; do
    if systemctl is-enabled "$unit" &>/dev/null; then
        echo "desativando $unit (o pulsedeckd assume o boot/resume)"
        systemctl disable --now "$unit" || true
    fi
done

systemctl enable --now pulsedeckd.service
sleep 2
systemctl --no-pager --lines=10 status pulsedeckd.service || true
