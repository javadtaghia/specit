#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

VERSION="$("$PYTHON_BIN" -c "from engine.version import APP_VERSION; print(APP_VERSION)")"
ARCH="$(uname -m)"
DMG_NAME="SPECiT-${VERSION}-macOS-${ARCH}.dmg"

echo "==> Building SPECiT ${VERSION} macOS .app & .dmg (${ARCH})"
"$PYTHON_BIN" packaging/generate_icons.py
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean packaging/specit.spec

STAGE_DIR="$ROOT_DIR/build/dmg-stage"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -R "$ROOT_DIR/dist/SPECiT.app" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

rm -f "$ROOT_DIR/dist/$DMG_NAME"
hdiutil create \
  -volname "SPECiT ${VERSION}" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$ROOT_DIR/dist/$DMG_NAME"

rm -rf "$STAGE_DIR"
echo "==> Created dist/$DMG_NAME"
