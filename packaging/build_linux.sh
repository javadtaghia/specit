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
PKG_NAME="SPECiT-${VERSION}-Linux-${ARCH}"
TAR_NAME="${PKG_NAME}.tar.gz"

echo "==> Building SPECiT ${VERSION} Linux bundle (${ARCH})"
"$PYTHON_BIN" packaging/generate_icons.py
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean packaging/specit.spec

STAGE_DIR="$ROOT_DIR/build/linux-stage/$PKG_NAME"
rm -rf "$ROOT_DIR/build/linux-stage"
mkdir -p "$STAGE_DIR"

cp "$ROOT_DIR/dist/SPECiT" "$STAGE_DIR/SPECiT"
chmod +x "$STAGE_DIR/SPECiT"
cp "$ROOT_DIR/packaging/icons/specit.png" "$STAGE_DIR/specit.png"
cp "$ROOT_DIR/LICENSE" "$STAGE_DIR/LICENSE"

cat > "$STAGE_DIR/specit.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=SPECiT
Comment=Local-first Architecture & Specification Studio
Exec=./SPECiT
Icon=specit
Categories=Development;Office;
Terminal=false
EOF

cat > "$STAGE_DIR/README-LINUX.txt" <<EOF
SPECiT ${VERSION} (Linux ${ARCH})
================================

Run directly:
  ./SPECiT

Headless / terminal-only mode:
  ./SPECiT --no-gui

Workspaces are stored in: ~/Documents/SPECiT/workspace
(override with SPECIT_WORKSPACE=/path/to/workspace)
EOF

rm -f "$ROOT_DIR/dist/$TAR_NAME"
tar -C "$ROOT_DIR/build/linux-stage" -czf "$ROOT_DIR/dist/$TAR_NAME" "$PKG_NAME"
rm -rf "$ROOT_DIR/build/linux-stage"

echo "==> Created dist/$TAR_NAME"
