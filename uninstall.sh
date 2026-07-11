#!/usr/bin/env bash
# ── Docker-Shell uninstall ───────────────────────────────────────
# Removes the app, venv, launcher and file manager integrations.
# NOTE: docker-compose.override.yml files written into your compose
# projects are NOT touched — remove them per project (or use the tool's
# "Reset project" beforehand).

set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${DATA_HOME}/docker-shell"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/docker-shell"

echo "=== Docker-Shell uninstall ==="

rm -rf "${INSTALL_DIR}"
rm -f  "$HOME/.local/bin/docker-shell"
rm -f  "${DATA_HOME}/nemo/actions/docker_konfig.nemo_action"
rm -f  "${DATA_HOME}/nautilus/scripts/Docker Konfig"
rm -f  "${DATA_HOME}/kio/servicemenus/docker-shell.desktop"
rm -f  "${DATA_HOME}/kservices5/ServiceMenus/docker-shell.desktop"
echo "App, venv, launcher and file manager integrations removed."

if [ -d "${CONFIG_DIR}" ]; then
    read -r -p "Also remove the config (${CONFIG_DIR})? [y/N] " answer
    case "${answer}" in
        [yY]*) rm -rf "${CONFIG_DIR}"; echo "Config removed." ;;
        *)     echo "Config kept." ;;
    esac
fi

echo "Done. Per-project docker-compose.override.yml files were left in place."
