#!/bin/sh
set -eu

PLACEHOLDER="__TURNSTILE_SITEKEY__"
SITEKEY="${TURNSTILE_SITEKEY:-}"
SITE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUTPUT_DIR="$SITE_DIR/dist"
TEMP_DIR=""

cleanup() {
  if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

if [ -z "$SITEKEY" ] || [ "$SITEKEY" = "$PLACEHOLDER" ]; then
  echo "TURNSTILE_SITEKEY must be configured; refusing to build an unprotected form." >&2
  exit 1
fi
if ! printf '%s' "$SITEKEY" | grep -Eq '^[A-Za-z0-9_-]{10,100}$'; then
  echo "TURNSTILE_SITEKEY has an invalid format." >&2
  exit 1
fi

for relative_page in index.html pl/index.html nl/index.html; do
  source_page="$SITE_DIR/$relative_page"
  placeholder_count=$({ grep -F -o "$PLACEHOLDER" "$source_page" || true; } | wc -l | tr -d '[:space:]')
  action_count=$({ grep -F -o 'data-action="arcadian_contact"' "$source_page" || true; } | wc -l | tr -d '[:space:]')
  disabled_submit_count=$({ grep -F -o 'disabled aria-disabled="true"' "$source_page" || true; } | wc -l | tr -d '[:space:]')
  explicit_script_count=$({ grep -F -o 'turnstile/v0/api.js?render=explicit' "$source_page" || true; } | wc -l | tr -d '[:space:]')
  if [ "$placeholder_count" != "1" ]; then
    echo "$relative_page must contain exactly one Turnstile sitekey placeholder; found $placeholder_count." >&2
    exit 1
  fi
  if [ "$action_count" != "1" ] || [ "$disabled_submit_count" != "1" ] || [ "$explicit_script_count" != "1" ]; then
    echo "$relative_page must keep explicit action=arcadian_contact and an initially disabled submit button." >&2
    exit 1
  fi
done

TEMP_DIR=$(mktemp -d "$SITE_DIR/.arcadian-dist.XXXXXX")
for entry in "$SITE_DIR"/*; do
  entry_name=$(basename "$entry")
  case "$entry_name" in
    dist|build-turnstile-site.sh)
      continue
      ;;
  esac
  cp -R "$entry" "$TEMP_DIR/"
done

for relative_page in index.html pl/index.html nl/index.html; do
  output_page="$TEMP_DIR/$relative_page"
  sed "s|$PLACEHOLDER|$SITEKEY|g" "$output_page" > "$output_page.tmp"
  mv "$output_page.tmp" "$output_page"
done

if grep -R -F -q "$PLACEHOLDER" "$TEMP_DIR"; then
  echo "Unresolved Turnstile sitekey placeholder remains in build output." >&2
  exit 1
fi

rm -rf "$OUTPUT_DIR"
mv "$TEMP_DIR" "$OUTPUT_DIR"
TEMP_DIR=""
echo "Static site built in $OUTPUT_DIR with three configured Turnstile widgets."
