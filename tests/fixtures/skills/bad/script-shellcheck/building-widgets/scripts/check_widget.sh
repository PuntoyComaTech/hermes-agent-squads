#!/usr/bin/env bash
# Check a widget HTML file for required markers.
if [[ "${1:-}" == "--help" ]]; then
  echo "usage: check_widget.sh <widget.html>"
  exit 0
fi
grep -q data-widget $1
