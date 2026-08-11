#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
APP="$ROOT/Serverkontroll.app"
SOURCE_ICON="$ROOT/icons/server-remote-app.svg"
RESOURCES="$APP/Contents/Resources"
DESKTOP_LINK="$HOME/Desktop/Serverkontroll.app"
TEMP="$(mktemp -d /tmp/serverkontroll-icon.XXXXXX)"
trap 'rm -rf "$TEMP"' EXIT

mkdir -p "$RESOURCES" "$TEMP/render" "$TEMP/Serverkontroll.iconset"
qlmanage -t -s 1024 -o "$TEMP/render" "$SOURCE_ICON" >/dev/null
PNG="$TEMP/render/${SOURCE_ICON:t}.png"

for points in 16 32 128 256 512; do
    sips -z "$points" "$points" "$PNG" \
        --out "$TEMP/Serverkontroll.iconset/icon_${points}x${points}.png" >/dev/null
    retina=$((points * 2))
    sips -z "$retina" "$retina" "$PNG" \
        --out "$TEMP/Serverkontroll.iconset/icon_${points}x${points}@2x.png" >/dev/null
done

iconutil -c icns -o "$RESOURCES/Serverkontroll.icns" \
    "$TEMP/Serverkontroll.iconset"
chmod +x "$APP/Contents/MacOS/Serverkontroll"

if [[ -e "$DESKTOP_LINK" && ! -L "$DESKTOP_LINK" ]]; then
    print -u2 "Avbryter: $DESKTOP_LINK finns redan och är inte en genväg."
    exit 1
fi
ln -sfn "$APP" "$DESKTOP_LINK"
touch "$APP"
print "Installerad: $DESKTOP_LINK -> $APP"
