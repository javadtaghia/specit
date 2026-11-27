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
APP_BUNDLE="$ROOT_DIR/dist/SPECiT.app"
ENTITLEMENTS="$ROOT_DIR/packaging/entitlements.plist"

echo "==> Building SPECiT ${VERSION} macOS .app & .dmg (${ARCH})"
"$PYTHON_BIN" packaging/generate_icons.py
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean packaging/specit.spec

SIGN_IDENTITY="${MACOS_SIGN_IDENTITY:--}"
if [ "$SIGN_IDENTITY" != "-" ]; then
  echo "==> Signing SPECiT.app with Developer ID (Hardened Runtime + Timestamp)"
  # Sign nested dylibs/so/binaries inside the bundle first, then the top-level .app
  find "$APP_BUNDLE/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) | while read -r bin; do
    codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$bin" 2>/dev/null || true
  done
  codesign --force --deep --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
else
  echo "==> Ad-hoc code-signing SPECiT.app (set MACOS_SIGN_IDENTITY for Developer ID signing)"
  codesign --force --deep --sign - "$APP_BUNDLE"
fi

codesign --verify --deep --strict "$APP_BUNDLE"

STAGE_DIR="$ROOT_DIR/build/dmg-stage"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -R "$APP_BUNDLE" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

DMG_PATH="$ROOT_DIR/dist/$DMG_NAME"
rm -f "$DMG_PATH"
hdiutil create \
  -volname "SPECiT ${VERSION}" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGE_DIR"

if [ "$SIGN_IDENTITY" != "-" ]; then
  echo "==> Signing DMG with Developer ID"
  codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG_PATH"

  if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] && [ -n "${APPLE_APP_PASSWORD:-}" ]; then
    echo "==> Submitting DMG to Apple Notarization service..."
    xcrun notarytool submit "$DMG_PATH" \
      --apple-id "$APPLE_ID" \
      --team-id "$APPLE_TEAM_ID" \
      --password "$APPLE_APP_PASSWORD" \
      --wait
    echo "==> Stapling notarization ticket to DMG..."
    xcrun stapler staple "$DMG_PATH"
    xcrun stapler validate "$DMG_PATH"
  else
    echo "==> Skipping Apple notarization (set APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD to enable)"
  fi
fi

echo "==> Created dist/$DMG_NAME"
