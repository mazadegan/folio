#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <input.(svg|png|pdf)> <output.icns> [size_px]"
  echo "Example: $0 folio-app.svg gui/FolioTauri/src-tauri/icons/icon.icns"
  exit 1
fi

INPUT_PATH="$1"
OUTPUT_ICNS="$2"
CANVAS_SIZE="${3:-1024}"

if [[ ! -f "$INPUT_PATH" ]]; then
  echo "Input file not found: $INPUT_PATH"
  exit 1
fi

for cmd in sips iconutil; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

if ! command -v magick >/dev/null 2>&1; then
  echo "Missing required command: magick (ImageMagick)"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

RAW_PNG="$TMP_DIR/raw.png"
MASTER_PNG="$TMP_DIR/master.png"
ICONSET_DIR="$TMP_DIR/App.iconset"
mkdir -p "$ICONSET_DIR"

EXT="${INPUT_PATH##*.}"
EXT_LOWER="$(printf '%s' "$EXT" | tr '[:upper:]' '[:lower:]')"

case "$EXT_LOWER" in
  svg)
    if command -v rsvg-convert >/dev/null 2>&1; then
      rsvg-convert -w "$CANVAS_SIZE" -h "$CANVAS_SIZE" "$INPUT_PATH" -o "$RAW_PNG"
    elif command -v inkscape >/dev/null 2>&1; then
      inkscape "$INPUT_PATH" --export-type=png --export-filename="$RAW_PNG" -w "$CANVAS_SIZE" -h "$CANVAS_SIZE"
    else
      echo "Need rsvg-convert or inkscape to rasterize SVG input."
      exit 1
    fi
    ;;
  png)
    cp "$INPUT_PATH" "$RAW_PNG"
    ;;
  pdf)
    sips -s format png "$INPUT_PATH" --out "$RAW_PNG" >/dev/null
    ;;
  *)
    echo "Unsupported input extension: .$EXT_LOWER (expected svg/png/pdf)"
    exit 1
    ;;
esac

# Create padded and rounded master icon.
# We resize artwork to ~80% canvas and mask with rounded-rectangle alpha.
ART_SIZE=$(( CANVAS_SIZE * 80 / 100 ))
RADIUS=$(( CANVAS_SIZE * 22 / 100 ))
LAST=$(( CANVAS_SIZE - 1 ))

magick "$RAW_PNG" \
  -resize "${ART_SIZE}x${ART_SIZE}" \
  -background none -gravity center -extent "${CANVAS_SIZE}x${CANVAS_SIZE}" \
  \( -size "${CANVAS_SIZE}x${CANVAS_SIZE}" xc:none -fill white -draw "roundrectangle 0,0 ${LAST},${LAST} ${RADIUS},${RADIUS}" \) \
  -compose CopyOpacity -composite \
  "$MASTER_PNG"

sips -z 16 16   "$MASTER_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
sips -z 32 32   "$MASTER_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
sips -z 32 32   "$MASTER_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
sips -z 64 64   "$MASTER_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$MASTER_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
sips -z 256 256 "$MASTER_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$MASTER_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
sips -z 512 512 "$MASTER_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$MASTER_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
cp "$MASTER_PNG" "$ICONSET_DIR/icon_512x512@2x.png"

mkdir -p "$(dirname "$OUTPUT_ICNS")"
iconutil -c icns "$ICONSET_DIR" -o "$OUTPUT_ICNS"

echo "Generated: $OUTPUT_ICNS"
