#!/bin/bash
# Volta para o facer-1.0 original.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "rode com sudo"; exit 1; }

dkms uninstall -m facer -v 1.1 -k "$(uname -r)" 2>/dev/null || true
dkms remove -m facer -v 1.1 --all 2>/dev/null || true
rm -f /etc/udev/rules.d/99-controlfanrgb.rules
udevadm control --reload-rules

dkms add -m facer -v 1.0 2>/dev/null || true
dkms build -m facer -v 1.0 -k "$(uname -r)"
dkms install -m facer -v 1.0 -k "$(uname -r)"

echo "revertido para facer-1.0. rode: sudo modprobe -r facer && sudo modprobe facer"
