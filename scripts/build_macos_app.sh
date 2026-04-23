#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${CODEX_SCOPE_BUILD_PYTHON:-/opt/homebrew/bin/python3.13}"
VENV_DIR="$ROOT_DIR/.venv"
ICON_SRC="$ROOT_DIR/assets/app-icon.png"
ICNS_PATH="$ROOT_DIR/assets/CodexScope.icns"
APP_NAME="Codex Scope"
APP_VERSION="${CODEX_SCOPE_VERSION:-}"
APP_PATH="$ROOT_DIR/dist/$APP_NAME.app"
DMG_PATH="$ROOT_DIR/dist/Codex-Scope-macOS.dmg"
DMG_STAGE_DIR="$ROOT_DIR/build/dmg"
DMG_VOLUME_NAME="Codex Scope Installer"

if [[ -z "$APP_VERSION" && -f "$ROOT_DIR/VERSION" ]]; then
  APP_VERSION="$(tr -d '\r\n' < "$ROOT_DIR/VERSION")"
fi

if [[ -z "$APP_VERSION" ]]; then
  APP_VERSION="26.4.23.1"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python runtime not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Missing icon source: $ICON_SRC" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/build"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install pyinstaller pillow >/dev/null

"$VENV_DIR/bin/python" - <<'PY'
from pathlib import Path
from PIL import Image

icon_src = Path("assets/app-icon.png")
icns_path = Path("assets/CodexScope.icns")
img = Image.open(icon_src).convert("RGBA")
img.save(
    icns_path,
    format="ICNS",
    sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
)
PY

PYINSTALLER_CONFIG_DIR=/tmp/pyinstaller "$VENV_DIR/bin/pyinstaller" \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ICNS_PATH" \
  --osx-bundle-identifier "com.xiaobin.codexscope" \
  --hidden-import codex_continue_summary \
  --hidden-import codex_context_inspector \
  --hidden-import codex_i18n \
  "$ROOT_DIR/codex_token_widget.py"

/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.xiaobin.codexscope" "$APP_PATH/Contents/Info.plist" >/dev/null
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_PATH/Contents/Info.plist" >/dev/null
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_PATH/Contents/Info.plist" >/dev/null
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $APP_VERSION" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP_PATH/Contents/Info.plist" >/dev/null
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$APP_PATH/Contents/Info.plist" >/dev/null
/usr/libexec/PlistBuddy -c "Add :CodexScopeAuthor string xiaobin" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CodexScopeAuthor xiaobin" "$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CodexScopeContact string happyyou2009@gmail.com" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CodexScopeContact happyyou2009@gmail.com" "$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string xiaobin · happyyou2009@gmail.com" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :NSHumanReadableCopyright xiaobin · happyyou2009@gmail.com" "$APP_PATH/Contents/Info.plist"

rm -rf "$DMG_STAGE_DIR" "$DMG_PATH"
mkdir -p "$DMG_STAGE_DIR"
cp -R "$APP_PATH" "$DMG_STAGE_DIR/"
ln -s /Applications "$DMG_STAGE_DIR/Applications"

hdiutil create \
  -volname "$DMG_VOLUME_NAME" \
  -srcfolder "$DMG_STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH" >/dev/null

echo "Built app: $APP_PATH"
echo "App version: $APP_VERSION"
echo "Release dmg: $DMG_PATH"
