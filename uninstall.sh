#!/bin/bash
# Rend le démarrage à KlipperScreen. Laisse $HOME/kiosk et les entrées de menu en place : relancer install.sh suffit pour revenir.
# Usage : sudo ./uninstall.sh
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "À lancer avec sudo." >&2; exit 1; }

systemctl disable --now kiosk
rm -f /etc/systemd/system/kiosk.service
systemctl daemon-reload
systemctl enable KlipperScreen
systemctl start KlipperScreen
echo "KlipperScreen rétabli au démarrage."
