#!/usr/bin/env bash
# =============================================================================
# Conduit — Install Script
# =============================================================================
# Installs Conduit and its dependencies, creates a venv, installs a desktop
# launcher, and adds `conduit` to ~/.local/bin.
#
# Usage:
#   chmod +x install.sh && ./install.sh
#
# Supports: Arch/CachyOS, Debian/Ubuntu, Fedora/RHEL, openSUSE
# Requires: Python 3.10+, pip
# =============================================================================

set -e

CONDUIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$HOME/.local/bin/conduit"
DESKTOP="$HOME/.local/share/applications/conduit.desktop"
VENV="$CONDUIT_DIR/venv"
PYTHON=""

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

info()    { echo -e "\033[1;34m[Conduit]\033[0m $*"; }
success() { echo -e "\033[1;32m[Conduit]\033[0m $*"; }
warn()    { echo -e "\033[1;33m[Conduit]\033[0m $*"; }
error()   { echo -e "\033[1;31m[Conduit]\033[0m $*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# 1. Find Python 3.10+
# -----------------------------------------------------------------------------

info "Checking for Python 3.10+..."

for cmd in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON=$(command -v "$cmd")
            info "Found $PYTHON ($ver)"
            break
        fi
    fi
done

[ -z "$PYTHON" ] && error "Python 3.10+ is required but was not found. Please install it and re-run."

# -----------------------------------------------------------------------------
# 2. Install system-level webview dependency
# -----------------------------------------------------------------------------

info "Checking for Qt/WebKit system dependencies..."

NEEDS_QT=false
"$PYTHON" -c "from qtpy import QtCore" &>/dev/null 2>&1 || \
"$PYTHON" -c "import gi" &>/dev/null 2>&1 || NEEDS_QT=true

if [ "$NEEDS_QT" = true ]; then
    info "Installing system webview dependencies..."

    if command -v pacman &>/dev/null; then
        # Arch / CachyOS / Manjaro
        sudo pacman -S --noconfirm --needed python-pyqt6 qt6-webengine 2>/dev/null || \
        sudo pacman -S --noconfirm --needed webkit2gtk-4.1 python-gobject 2>/dev/null || \
        warn "Could not install system webview deps via pacman. Will try pip fallback."

    elif command -v apt-get &>/dev/null; then
        # Debian / Ubuntu
        sudo apt-get install -y python3-gi gir1.2-webkit2-4.1 python3-gi-cairo 2>/dev/null || \
        warn "Could not install system webview deps via apt. Will try pip fallback."

    elif command -v dnf &>/dev/null; then
        # Fedora / RHEL
        sudo dnf install -y python3-gobject webkit2gtk4.1 2>/dev/null || \
        warn "Could not install system webview deps via dnf. Will try pip fallback."

    elif command -v zypper &>/dev/null; then
        # openSUSE
        sudo zypper install -y python3-gobject typelib-1_0-WebKit2-4_1 2>/dev/null || \
        warn "Could not install system webview deps via zypper. Will try pip fallback."

    else
        warn "Unknown package manager. Will try pip fallback (PySide6)."
    fi
fi

# -----------------------------------------------------------------------------
# 3. Create virtual environment
# -----------------------------------------------------------------------------

info "Setting up Python virtual environment..."

if [ ! -d "$VENV" ]; then
    "$PYTHON" -m venv "$VENV"
    success "Virtual environment created."
else
    info "Virtual environment already exists, skipping."
fi

PIP="$VENV/bin/pip"
VENV_PYTHON="$VENV/bin/python3"

"$PIP" install --upgrade pip --quiet

# -----------------------------------------------------------------------------
# 4. Install pip dependencies
# -----------------------------------------------------------------------------

info "Installing Python dependencies..."
"$PIP" install -r "$CONDUIT_DIR/requirements.txt" --quiet
success "Python dependencies installed."

# Install PySide6 as pip fallback for pywebview if no system webview found
if ! "$VENV_PYTHON" -c "import webview.platforms.gtk" &>/dev/null 2>&1 && \
   ! "$VENV_PYTHON" -c "import webview.platforms.qt" &>/dev/null 2>&1; then
    info "Installing PySide6 for pywebview (Qt backend)..."
    "$PIP" install PySide6 qtpy --quiet
    success "PySide6 installed."
fi

# Verify webview works
if ! "$VENV_PYTHON" -c "import webview.platforms.qt; print('ok')" &>/dev/null 2>&1 && \
   ! "$VENV_PYTHON" -c "import webview.platforms.gtk; print('ok')" &>/dev/null 2>&1; then
    error "pywebview has no working GUI backend. Please install webkit2gtk or Qt WebEngine for your distro and re-run."
fi

# -----------------------------------------------------------------------------
# 5. Install launcher script
# -----------------------------------------------------------------------------

info "Installing launcher..."

mkdir -p "$HOME/.local/bin"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Conduit launcher
PROJECT="$CONDUIT_DIR"
PYTHON="\$PROJECT/venv/bin/python3"
exec "\$PYTHON" "\$PROJECT/desktop.py" "\$@"
EOF

chmod +x "$LAUNCHER"
success "Launcher installed at $LAUNCHER"

# -----------------------------------------------------------------------------
# 6. Install desktop entry
# -----------------------------------------------------------------------------

info "Installing desktop entry..."

mkdir -p "$HOME/.local/share/applications"

ICON_PATH="$CONDUIT_DIR/frontend/icon.png"
[ ! -f "$ICON_PATH" ] && ICON_PATH="video-display"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Conduit
Comment=Video library manager and optimizer
Exec=$LAUNCHER
Path=$CONDUIT_DIR
Icon=$ICON_PATH
Categories=AudioVideo;Video;
Terminal=false
StartupWMClass=Conduit
Keywords=media;video;encode;transcode;optimize;
EOF

chmod 644 "$DESKTOP"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
fi

success "Desktop entry installed."

# -----------------------------------------------------------------------------
# 7. Ensure ~/.local/bin is on PATH
# -----------------------------------------------------------------------------

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "~/.local/bin is not in your PATH."
    warn "Add the following to your ~/.bashrc or ~/.zshrc:"
    warn '  export PATH="$HOME/.local/bin:$PATH"'
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------

echo ""
success "Conduit installed successfully!"
echo ""
echo "  Launch from your app menu, or run:  conduit"
echo "  Headless mode:                       conduit --no-gui"
echo ""
