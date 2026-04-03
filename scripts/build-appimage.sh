#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?usage: build-appimage.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT/build/appimage"
VENV_DIR="$BUILD_DIR/venv"
APPDIR="$BUILD_DIR/AppDir"
DIST_DIR="$ROOT/dist"
PYTHON_BIN="${PYTHON_BIN:-python3}"

rm -rf "$BUILD_DIR" "$ROOT/build/pyinstaller-appimage"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
pip install -r "$ROOT/requirements.txt" PyInstaller PySide6 qtpy

pyinstaller "$ROOT/packaging/conduit-appimage.spec" \
  --noconfirm \
  --clean \
  --distpath "$BUILD_DIR/pyinstaller-dist" \
  --workpath "$ROOT/build/pyinstaller-appimage"

mkdir -p "$APPDIR/usr/bin"
cp -a "$BUILD_DIR/pyinstaller-dist/conduit/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/appimage/conduit.desktop" "$APPDIR/conduit.desktop"
cp "$ROOT/frontend/icons/conduit-256.png" "$APPDIR/conduit.png"
cp "$ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"

LINUXDEPLOY="$BUILD_DIR/linuxdeploy-x86_64.AppImage"
curl -L -o "$LINUXDEPLOY" https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
chmod +x "$LINUXDEPLOY"

OUTPUT_PATH="$DIST_DIR/Conduit-${VERSION}-x86_64.AppImage"
export OUTPUT="$OUTPUT_PATH"
export LDAI_OUTPUT="$OUTPUT_PATH"
export ARCH=x86_64
export PYWEBVIEW_GUI=qt
export QTWEBENGINE_DISABLE_SANDBOX=1
"$LINUXDEPLOY" \
  --appdir "$APPDIR" \
  --desktop-file "$APPDIR/conduit.desktop" \
  --icon-file "$APPDIR/conduit.png" \
  --output appimage

if [[ ! -f "$OUTPUT_PATH" ]]; then
  echo "Expected AppImage not found at $OUTPUT_PATH" >&2
  exit 1
fi

echo "Built $OUTPUT_PATH"
