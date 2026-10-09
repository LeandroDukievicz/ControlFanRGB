#!/bin/bash
set -euo pipefail
systemctl --user disable --now pulsedeck-tray.service 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/pulsedeck-tray.service"
systemctl --user daemon-reload
echo "tray removido."
