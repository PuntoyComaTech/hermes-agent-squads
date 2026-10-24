#!/usr/bin/env python3
"""Print the kit hash of an application/ folder: the kit_sha256 the manager writes into consent.json.

  kit_hash.py APP_DIR

The submit gate (submitting-applications/check_submission.py) recomputes the same hash from jobs_common. Exit 1 and a
message on stderr when APP_DIR has no cv_ats.pdf. Stdlib only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args and args[0] in ("-h", "--help") else 2
    digest = jc.kit_sha256(Path(args[0]))
    if digest is None:
        print(f"error: {args[0]} has no cv_ats.pdf", file=sys.stderr)
        return 1
    print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
