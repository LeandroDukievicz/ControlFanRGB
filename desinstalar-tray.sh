#!/bin/bash
set -euo pipefail
systemctl --user disable --now controlfanrgb-tray.service 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/controlfanrgb-tray.service"
systemctl --user daemon-reload
echo "tray removido."
