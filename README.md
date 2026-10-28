# speeder-pad

Tableau de bord tactile pour le FLSUN Speeder Pad, à la place de KlipperScreen au démarrage : météo, tâches du jour (Notion), liste de courses (Notion), tuiles Home Assistant. KlipperScreen reste installé et se relance depuis le bouton imprimante du tableau de bord ; le menu de KlipperScreen ramène au tableau de bord.

Cible : Ubuntu 20.04 du pad, utilisateur `pi`, KlipperScreen + Moonraker déjà en place.

## Installer

Depuis le poste de travail (le mot de passe sudo se tape dans ce terminal) :

```bash
./deploy.sh pi@<adresse-du-pad>
```

Ou directement sur le pad, depuis un clone du dépôt :

```bash
sudo ./install.sh
```

`install.sh` est idempotent : le relancer met le code à jour sans toucher à la configuration existante. Il ne fait aucun upgrade apt (`wpasupplicant` est gelé sur ce pad).

| Option | Effet |
| --- | --- |
| `--route "<réseau/cidr> <passerelle>"` | route persistante NetworkManager (wlan0), pour joindre un réseau derrière une passerelle, ex. `--route "192.168.50.0/24 192.168.1.2"` |

## Ce que fait l'installateur

1. Paquets : `xinit`, `xinput`, pilotes Xorg fbdev/libinput, `python3-gi`, `gir1.2-webkit2-4.0`, `python3.9`, `tzdata`.
2. Copie `kiosk/` dans `/home/pi/kiosk` ; crée les fichiers de configuration absents depuis `config/*.example`.
3. Retire la rotation Xorg et la matrice tactile retournée d'un essai antérieur (voir *Rotation*).
4. Installe `kiosk.service`, désactive `KlipperScreen` au démarrage, active `kiosk`. Les deux se coupent mutuellement (`Conflicts=`).
5. KlipperScreen : pose `moonraker_api_key` (lue sur Moonraker en local) et deux entrées « Tableau de bord » (menu principal + menu d'erreur), sauvegarde `.bak-pre-kiosk`.
6. Ajoute `kiosk` à `moonraker.asvc` pour que Moonraker puisse piloter le service.
7. Redémarre le kiosque et attend la réponse du serveur local.

## Configuration

Créée vide ou d'exemple par l'installateur, à compléter ; ensuite `sudo systemctl restart kiosk`.

| Fichier (dans `/home/pi/kiosk`) | Contenu |
| --- | --- |
| `www/config.json` | fuseau horaire, nom et coordonnées de la météo (Open-Meteo, sans clé) |
| `notion.env` | `NOTION_TOKEN=` jeton d'une intégration Notion (mode 600) |
| `notion.json` | bases Notion : tâches et courses (`database_id`, noms des propriétés, états) ; chaque base doit être partagée avec l'intégration |
| `ha.env` | `HA_TOKEN=` jeton longue durée Home Assistant (mode 600) |
| `ha.json` | URL de Home Assistant et liste blanche des entités commandables (`light.*`, `switch.*`, `script.*`, `scene.*`, `input_boolean.*`) |

Sans configuration, les panneaux concernés affichent une erreur ; le reste fonctionne. Le pad doit pouvoir joindre Home Assistant (routage et pare-feu côté réseau, hors de ce dépôt).

## Rotation

Le pad est monté tête en bas. Le pilote `fbdev` ignore `Rotate=UD` de Xorg : seul le kiosque est retourné, en CSS (`?rotate=180` dans `browser.py`). KlipperScreen reste donc à l'envers, avec un tactile cohérent.

## Retour arrière

```bash
sudo ./uninstall.sh
```

Rend le démarrage à KlipperScreen ; `/home/pi/kiosk` et les entrées de menu restent, relancer `install.sh` suffit pour revenir.

## Dépannage

- Journaux : `/home/pi/kiosk/server.log`, `/home/pi/kiosk/browser.log`, `journalctl -u kiosk`.
- Écran noir au premier lancement : le serveur local démarre en même temps que le navigateur, qui réessaie toutes les 3 s.
- Bouton « Tableau de bord » en *Unauthorized* dans KlipperScreen : `moonraker_api_key` manquante, relancer `install.sh` avec Moonraker démarré.

## Polices

Roboto (Apache 2.0) et Noto Color Emoji (OFL 1.1) sont embarquées dans `kiosk/www/fonts/` : le pad n'a aucune police emoji.
