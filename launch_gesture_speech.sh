#!/usr/bin/env bash
cd "$(dirname "$0")" || exit

install_uv() {
    echo "uv not found"
    echo "Trying to install ..."
    wget https://astral.sh/uv/install.sh && chmod +x ./install.sh && ./install.sh && rm install.sh && echo "uv installé !"
}

setup_venv() {
    uv venv --python 3.10
}

sync() {
    echo "Syncing dependencies"
    uv sync
    echo "venv activation"
    source .venv/bin/activate
}

launch() {
    echo "Launching..."
    uv run python main.py
}

nil=/dev/null

uv help 1>$nil 2>$nil || install_uv
test -d .venv || setup_venv
sync && launch