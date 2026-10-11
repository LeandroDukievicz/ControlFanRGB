#!/usr/bin/env python3
"""Recarrega systemd, D-Bus e udev depois de instalar.

Só roda numa instalação real: com DESTDIR definido estamos montando o
conteúdo de um pacote, e aí recarregar os serviços do sistema que está
construindo seria errado.
"""
import os
from pathlib import Path
import subprocess
import sys

if os.environ.get("DESTDIR"):
    sys.exit(0)

# O ícone anterior era SVG. Removê-lo evita que o tema prefira uma cópia
# antiga à nova versão PNG após uma atualização pelo Meson.
prefix = Path(os.environ.get("MESON_INSTALL_PREFIX", "/usr"))
icons = prefix / "share" / "icons" / "hicolor"
app_id = "io.github.leandrodukievicz.ControlFanRGB"
legacy_icons = [
    icons / "scalable" / "apps" / f"{app_id}.svg",
    icons / "symbolic" / "apps" / f"{app_id}-symbolic.svg",
    *(icons / size / "apps" / f"{app_id}.svg"
      for size in ("16x16", "22x22", "24x24", "32x32")),
]
for path in legacy_icons:
    path.unlink(missing_ok=True)

for cmd in (
    ["gtk-update-icon-cache", "-qtf", str(icons)],
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
