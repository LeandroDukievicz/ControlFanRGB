#!/usr/bin/env python3
"""Recarrega systemd, D-Bus e udev depois de instalar.

Só roda numa instalação real: com DESTDIR definido estamos montando o
conteúdo de um pacote, e aí recarregar os serviços do sistema que está
construindo seria errado.
"""
import os
import subprocess
import sys

if os.environ.get("DESTDIR"):
    sys.exit(0)

for cmd in (
    ["gtk-update-icon-cache", "-qtf", "/usr/share/icons/hicolor"],
    ["systemctl", "daemon-reload"],
    ["udevadm", "control", "--reload-rules"],
):
    subprocess.call(cmd, stderr=subprocess.DEVNULL)

for unit in ("dbus", "dbus-broker"):
    if subprocess.call(["systemctl", "reload", unit],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL) == 0:
        break

print("ControlFanRGB instalado. Para ativar:")
print("  sudo systemctl enable --now controlfanrgbd.service")
print("  systemctl --user enable --now controlfanrgb-tray.service")
