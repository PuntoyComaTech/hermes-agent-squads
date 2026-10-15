#!/usr/bin/env python3
"""Render a widget preview from a JSON data file."""
import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a widget preview from a JSON data file.")
    parser.add_argument("--input", required=True, help="path to the widget data JSON")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    print(json.dumps({"fields": sorted(data)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
