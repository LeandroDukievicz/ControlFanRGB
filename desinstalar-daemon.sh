#!/bin/bash
# Remove o daemon e devolve o boot/resume para o acer-rgb.service antigo.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "rode com sudo"; exit 1; }

systemctl disable --now pulsedeckd.service 2>/dev/null || true
rm -f /etc/systemd/system/pulsedeckd.service
rm -f /etc/dbus-1/system.d/io.github.leandrodukievicz.PulseDeck1.conf
systemctl daemon-reload

for unit in acer-rgb.service acer-rgb-resume.service; do
    systemctl enable "$unit" 2>/dev/null || true
done
echo "daemon removido. o acer-rgb.service voltou a cuidar do boot."
