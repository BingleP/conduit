#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?usage: build-macos-dmg.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT/build/macos"
DIST_DIR="$ROOT/dist"
VENV_DIR="$BUILD_DIR/venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="Conduit"
APP_PATH="$BUILD_DIR/pyinstaller-dist/${APP_NAME}.app"
DMG_STAGING="$BUILD_DIR/dmg"
ICONSET_DIR="$BUILD_DIR/conduit.iconset"
ICNS_PATH="$BUILD_DIR/conduit.icns"
DMG_PATH="$DIST_DIR/Conduit-${VERSION}-macos.dmg"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$ICONSET_DIR"

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
pip install -r "$ROOT/requirements.txt" PyInstaller pyobjc

cp "$ROOT/frontend/icons/conduit-16.png" "$ICONSET_DIR/icon_16x16.png"
cp "$ROOT/frontend/icons/conduit-32.png" "$ICONSET_DIR/icon_16x16@2x.png"
cp "$ROOT/frontend/icons/conduit-32.png" "$ICONSET_DIR/icon_32x32.png"
cp "$ROOT/frontend/icons/conduit-64.png" "$ICONSET_DIR/icon_32x32@2x.png"
cp "$ROOT/frontend/icons/conduit-128.png" "$ICONSET_DIR/icon_128x128.png"
cp "$ROOT/frontend/icons/conduit-256.png" "$ICONSET_DIR/icon_128x128@2x.png"
cp "$ROOT/frontend/icons/conduit-256.png" "$ICONSET_DIR/icon_256x256.png"
cp "$ROOT/frontend/icons/conduit-512.png" "$ICONSET_DIR/icon_256x256@2x.png"
cp "$ROOT/frontend/icons/conduit-512.png" "$ICONSET_DIR/icon_512x512.png"
cp "$ROOT/frontend/icons/conduit-512.png" "$ICONSET_DIR/icon_512x512@2x.png"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

pyinstaller "$ROOT/desktop.py" \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "$APP_NAME" \
  --icon "$ICNS_PATH" \
  --distpath "$BUILD_DIR/pyinstaller-dist" \
  --workpath "$BUILD_DIR/pyinstaller-work" \
  --specpath "$BUILD_DIR" \
  --add-data "$ROOT/frontend:frontend" \
  --add-data "$ROOT/config.json:." \
  --hidden-import webview.platforms.cocoa \
  --collect-submodules uvicorn \
  --collect-submodules watchdog \
  --collect-data webview

mkdir -p "$DMG_STAGING"
cp -R "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DMG_PATH"

echo "Built $DMG_PATH"
