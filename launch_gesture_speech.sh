#!/usr/bin/env bash
cd "$(dirname "$0")" || exit

install_uv() {
    echo "uv non trouvé"
    echo "Tentative d'installation ..."
    wget https://astral.sh/uv/install.sh && chmod +x ./install.sh && ./install.sh && rm install.sh && echo "uv installé !"
}

setup_venv() {
    uv venv --python 3.10
}

sync() {
    echo "Synchronisation des dépendances"
    uv sync
    echo "Activation du venv"
    source .venv/bin/activate
}

launch() {
    echo "Lancement en cours..."
    uv run --with jupyter launcher.py
}

nil=/dev/null

uv help 1>$nil 2>$nil || install_uv
test -d .venv || setup_venv
sync && launch