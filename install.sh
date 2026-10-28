#!/bin/bash
# Installe le kiosque sur le speeder-pad (Ubuntu 20.04 du FLSUN, utilisateur pi) et le branche sur KlipperScreen.
# Usage : sudo ./install.sh [--route "<réseau/cidr> <passerelle>"]
# Idempotent. Aucun upgrade : wpasupplicant est gelé par apt-mark hold sur ce pad.
set -euo pipefail

USER_NAME=pi
APP_DIR=/home/$USER_NAME/kiosk
PRINTER_DATA=/home/$USER_NAME/printer_data
KS_CONF=$PRINTER_DATA/config/KlipperScreen.conf
ASVC=$PRINTER_DATA/moonraker.asvc
XORG_DIR=/etc/X11/xorg.conf.d
SRC=$(cd "$(dirname "$0")" && pwd)
PACKAGES=(xinit x11-xserver-utils xinput xserver-xorg-input-libinput xserver-xorg-video-fbdev python3-gi gir1.2-webkit2-4.0 python3.9 tzdata)

route=""
while [ $# -gt 0 ]; do
    case "$1" in
    --route) route=${2:?--route attend "<réseau/cidr> <passerelle>"}; shift 2 ;;
    *) echo "Argument inconnu : $1" >&2; exit 2 ;;
    esac
done

[ "$(id -u)" = 0 ] || { echo "À lancer avec sudo." >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "Utilisateur $USER_NAME introuvable : ce script vise le speeder-pad." >&2; exit 1; }

step() { printf '\n== %s\n' "$*"; }
# Fichiers de configuration créés vides, à compléter par l'utilisateur.
to_fill=()

step "Paquets"
apt-get install -y --no-install-recommends --no-upgrade "${PACKAGES[@]}"
# browser.py tourne sous python3.8 : c'est le seul interpréteur qui voit le binding gi du système.
sudo -u "$USER_NAME" /usr/bin/python3.8 -c 'import gi; gi.require_version("WebKit2", "4.0")' \
    || { echo "WebKit2 inutilisable sous python3.8." >&2; exit 1; }

step "Application → $APP_DIR"
install -d -o "$USER_NAME" -g "$USER_NAME" "$APP_DIR"
# Le dépôt ne contient aucun fichier de configuration vivant : la copie n'écrase donc jamais celle du pad.
cp -rT "$SRC/kiosk" "$APP_DIR"
chown -R "$USER_NAME:$USER_NAME" "$APP_DIR"
chmod 755 "$APP_DIR"/*.sh "$APP_DIR"/*.py

place_config() { # <exemple> <destination> <mode>
    if [ -e "$2" ]; then
        echo "conservé : $2"
    else
        install -m "$3" -o "$USER_NAME" -g "$USER_NAME" "$SRC/config/$1" "$2"
        to_fill+=("$2")
        echo "créé     : $2"
    fi
}
place_config config.json.example "$APP_DIR/www/config.json" 644
place_config ha.json.example "$APP_DIR/ha.json" 644
place_config notion.json.example "$APP_DIR/notion.json" 644
place_config ha.env.example "$APP_DIR/ha.env" 600
place_config notion.env.example "$APP_DIR/notion.env" 600

step "Tactile et affichage"
# La rotation de 180° est faite en CSS (fbdev ignore Rotate=UD) : une matrice tactile retournée inverserait KlipperScreen.
rm -f "$XORG_DIR/10-rotate-180.conf"
if grep -qs 'TransformationMatrix" "-1 0 1 0 -1 1 0 0 1"' "$XORG_DIR/05-touch.conf"; then
    sed -i '/TransformationMatrix/d' "$XORG_DIR/05-touch.conf"
    echo "matrice tactile retournée retirée de 05-touch.conf"
fi

step "Service systemd"
install -m 0644 "$SRC/system/kiosk.service" /etc/systemd/system/kiosk.service
systemctl daemon-reload
if systemctl cat KlipperScreen.service >/dev/null 2>&1; then
    systemctl disable KlipperScreen
fi
systemctl enable kiosk

step "KlipperScreen : retour depuis le menu"
if [ -f "$KS_CONF" ]; then
    [ -f "$KS_CONF.bak-pre-kiosk" ] || cp -p "$KS_CONF" "$KS_CONF.bak-pre-kiosk"
    if ! grep -q '^moonraker_api_key:' "$KS_CONF"; then
        # Sans clé valide, KlipperScreen envoie une clé vide, Moonraker retire la confiance de la connexion et machine.services.* répond Unauthorized.
        key=$(curl -fsS --max-time 5 http://127.0.0.1:7125/access/api_key | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])') \
            || { echo "Moonraker injoignable : clé API non posée, le bouton « Tableau de bord » ne marchera pas." >&2; key=""; }
        if [ -n "$key" ]; then
            sed -i "/^moonraker_port:/a moonraker_api_key: $key" "$KS_CONF"
            echo "moonraker_api_key posée"
        fi
    fi
    if ! grep -q '^\[menu __main kiosk\]' "$KS_CONF"; then
        # Deux entrées : le menu d'erreur (__splashscreen) est la seule page d'accueil tant que le MCU Klipper est injoignable.
        cat >> "$KS_CONF" <<'MENU'


# Retour au tableau de bord (kiosque speeder-pad)
[menu __main kiosk]
name: Tableau de bord
icon: home
method: machine.services.start
params: {"service": "kiosk"}


[menu __splashscreen kiosk]
name: Tableau de bord
icon: home
method: machine.services.start
params: {"service": "kiosk"}
MENU
        echo "entrées de menu ajoutées"
    fi
    # La clé API y est en clair.
    chown "$USER_NAME:$USER_NAME" "$KS_CONF"
    chmod 600 "$KS_CONF"
else
    echo "KlipperScreen.conf absent : rien à brancher."
fi

step "Moonraker : droit de piloter le service kiosk"
if [ -f "$ASVC" ] && ! grep -qx kiosk "$ASVC"; then
    [ -z "$(tail -c1 "$ASVC")" ] || echo >> "$ASVC"
    echo kiosk >> "$ASVC"
    # Moonraker ne relit moonraker.asvc qu'au démarrage.
    systemctl try-restart moonraker
    echo "kiosk ajouté à moonraker.asvc"
fi

if [ -n "$route" ]; then
    step "Route Wi-Fi : $route"
    connection=$(nmcli -t -f NAME,DEVICE connection show --active | awk -F: '$2=="wlan0" {print $1}')
    [ -n "$connection" ] || { echo "Aucune connexion NetworkManager active sur wlan0." >&2; exit 1; }
    if nmcli -g ipv4.routes connection show "$connection" | grep -qF "${route%% *}"; then
        echo "déjà déclarée sur « $connection »"
    else
        nmcli connection modify "$connection" +ipv4.routes "$route"
        # reapply évite la reconnexion Wi-Fi, qui a déjà posé problème sur ce pad.
        nmcli device reapply wlan0
    fi
fi

step "Démarrage"
systemctl restart kiosk
# Xorg démarre avant le serveur : sur le pad, la première réponse arrive après une dizaine de secondes.
up=""
for _ in $(seq 1 40); do
    if curl -fs --max-time 2 -o /dev/null http://127.0.0.1:8090/config.json; then up=1; break; fi
    sleep 1
done
[ -n "$up" ] || { echo "Le serveur du kiosque ne répond pas : voir $APP_DIR/server.log et browser.log." >&2; exit 1; }
echo "kiosque actif"

if [ ${#to_fill[@]} -gt 0 ]; then
    printf '\nÀ compléter (puis : sudo systemctl restart kiosk) :\n'
    printf '  %s\n' "${to_fill[@]}"
fi
