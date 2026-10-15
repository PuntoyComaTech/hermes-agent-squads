#!/usr/bin/env bash
# Check a widget HTML file for required markers.
set -euo pipefail
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "usage: check_widget.sh <widget.html>"
  exit 0
fi
file="${1:?usage: check_widget.sh <widget.html>}"
grep -q 'data-widget' "$file"
echo "ok: $file"
