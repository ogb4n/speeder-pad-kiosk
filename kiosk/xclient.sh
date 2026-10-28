#!/bin/bash
cd /home/pi/kiosk || exit 1

# Écran allumé en continu : le speeder-pad sert d'afficheur posé sur le frigo.
xset s off -dpms s noblank

# python3.9 explicite : le serveur utilise zoneinfo, absent de python3.8.
/usr/bin/python3.9 server.py > server.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null' EXIT

# browser.log n'est plus tronqué à chaque démarrage (il effaçait la cause des plantages) ; borné à ~200 Ko.
[ "$(stat -c %s browser.log 2>/dev/null || echo 0)" -gt 200000 ] && : > browser.log
echo "$(date +%T) démarrage du navigateur" >> browser.log
/usr/bin/python3.8 browser.py >> browser.log 2>&1
code=$?
echo "$(date +%T) browser.py terminé, code $code" >> browser.log
