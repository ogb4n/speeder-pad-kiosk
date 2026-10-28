#!/bin/bash
# Depuis le poste de travail : copie le dépôt sur le pad puis y lance install.sh sous sudo (le mot de passe se tape dans ce terminal).
# Usage : ./deploy.sh pi@<adresse-du-pad> [options d'install.sh]
set -euo pipefail

[ $# -ge 1 ] || { echo "usage : ./deploy.sh pi@<adresse-du-pad> [options de install.sh]" >&2; exit 2; }
target=$1
shift
here=$(cd "$(dirname "$0")" && pwd)
remote=/tmp/speeder-pad-install

# shellcheck disable=SC2029  # $remote est volontairement évalué côté poste.
tar -C "$here" --exclude=.git --exclude=__pycache__ -cf - . \
    | ssh "$target" "rm -rf $remote && mkdir -p $remote && tar -xf - -C $remote"
# shellcheck disable=SC2029  # $remote est volontairement évalué côté poste.
ssh -t "$target" "sudo $remote/install.sh$(printf ' %q' "$@"); status=\$?; rm -rf $remote; exit \$status"
