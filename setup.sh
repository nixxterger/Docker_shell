#!/usr/bin/env bash
# ── Docker-Shell setup ───────────────────────────────────────────
# Creates a venv, installs dependencies, installs the app under
# ~/.local/share/docker-shell and hooks it into the file manager.
# Run as your normal desktop user (never as root).

set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${DATA_HOME}/docker-shell"
VENV_DIR="${INSTALL_DIR}/venv"
TEMP_LEER="${INSTALL_DIR}/temp_leer"
BIN_DIR="$HOME/.local/bin"
PYTHON="${VENV_DIR}/bin/python"
APP="${INSTALL_DIR}/docker_shell.py"

echo "=== Docker-Shell setup ==="

# 0. Sanity checks
command -v python3 >/dev/null || { echo "ERROR: python3 not found."; exit 1; }
command -v docker  >/dev/null || { echo "ERROR: docker not found."; exit 1; }
docker compose version >/dev/null 2>&1 || {
    echo "ERROR: Docker Compose v2 ('docker compose') is required."; exit 1; }
python3 -c "import tkinter" 2>/dev/null || {
    echo "ERROR: python3-tk is missing. Install it first, e.g.:"
    echo "  Debian/Ubuntu/Mint: sudo apt install python3-tk"
    echo "  Fedora:             sudo dnf install python3-tkinter"
    echo "  Arch:               sudo pacman -S tk"
    exit 1; }

# 1. Directories
echo "[1/5] Creating directory structure..."
mkdir -p "${INSTALL_DIR}" "${TEMP_LEER}" "${BIN_DIR}"

# 2. App files
echo "[2/5] Installing app to ${INSTALL_DIR}..."
cp "${SOURCE_DIR}/docker_shell.py" "${APP}"
chmod +x "${APP}"

# 3. Virtual environment + dependencies
if [ -d "${VENV_DIR}" ]; then
    echo "[3/5] venv already exists — skipping creation."
else
    echo "[3/5] Creating venv at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --quiet --upgrade -r "${SOURCE_DIR}/requirements.txt"

# 4. CLI launcher
echo "[4/5] Installing CLI launcher ${BIN_DIR}/docker-shell..."
cat > "${BIN_DIR}/docker-shell" <<EOF
#!/usr/bin/env bash
exec "${PYTHON}" "${APP}" "\$@"
EOF
chmod +x "${BIN_DIR}/docker-shell"

# 5. File manager integration (whatever is present)
echo "[5/5] File manager integration..."
INSTALLED_FM=""
if command -v nemo >/dev/null; then
    NEMO_ACTIONS="${DATA_HOME}/nemo/actions"
    mkdir -p "${NEMO_ACTIONS}"
    sed -e "s|@PYTHON@|${PYTHON}|g" -e "s|@APP@|${APP}|g" \
        "${SOURCE_DIR}/integrations/nemo/docker_konfig.nemo_action.in" \
        > "${NEMO_ACTIONS}/docker_konfig.nemo_action"
    INSTALLED_FM="Nemo (right-click a folder → 'Docker Konfig')"
fi

echo ""
echo "=== Installation complete ==="
"${PYTHON}" --version
"${VENV_DIR}/bin/pip" list 2>/dev/null | grep -iE "customtkinter|pyyaml" || true
echo ""
echo "CLI:          docker-shell <folder>"
[ -n "${INSTALLED_FM}" ] && echo "File manager: ${INSTALLED_FM}"
echo "Mask folder:  ${TEMP_LEER}"
echo "Config file:  ${XDG_CONFIG_HOME:-$HOME/.config}/docker-shell/config.yml (optional)"
