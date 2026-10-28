#!/bin/bash
# Même mécanique que KlipperScreen-start.sh : xinit sur :0, tty7 fourni par l'unité systemd.
XDG_RUNTIME_DIR=/run/user/$(id -u)
export XDG_RUNTIME_DIR

exec /usr/bin/xinit /home/pi/kiosk/xclient.sh
