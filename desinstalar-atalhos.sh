#!/bin/bash
set -euo pipefail
B=org.gnome.settings-daemon.plugins.media-keys
PREFIX=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
for slug in pulsedeck-turbo pulsedeck-off; do
    dconf reset -f "$PREFIX/$slug/" 2>/dev/null || true
done
gsettings set $B custom-keybindings "@as []"
echo "atalhos removidos."
