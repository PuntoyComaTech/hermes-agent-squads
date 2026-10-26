#!/usr/bin/env python3
"""Print the CV file to upload for an application, writing the named copy when it is missing or stale.

  upload_copy.py <P>/openings/<ID>/application [--contact <P>/contact.yaml]

The file a recruiter sees is `CV_<Name>_<Surname>.pdf`, a byte copy of `cv_ats.pdf` named by
jobs_common.cv_upload_name from `contact.yaml` (`short_name` wins over `name`), the same rule render_cv.py uses. A kit
rendered before that copy existed, or one whose copy no longer matches `cv_ats.pdf`, gets it rewritten here, so no bot
names the upload by hand. Older `CV_*.pdf` copies are removed. Prints the absolute path to upload.

Exit 0 printed, 1 no cv_ats.pdf or no usable name in contact.yaml, 2 usage error.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402


def upload_copy(application: Path, contact_file: Path) -> Path:
    canonical = application / jc.CV_FILE
    if not canonical.is_file():
        raise FileNotFoundError(f"{canonical} does not exist")
    contact = jc.read_data(contact_file) if contact_file.is_file() else {}
    if not isinstance(contact, dict):
        contact = {}
    name = jc.cv_upload_name(str(contact.get("name") or ""), str(contact.get("short_name") or ""))
    if not name:
        raise ValueError(f"{contact_file} has no usable name or short_name")
    target = application / name
    data = canonical.read_bytes()
    for old in application.glob("CV_*.pdf"):
        if old.name != name:
            old.unlink(missing_ok=True)
    if not target.is_file() or target.read_bytes() != data:
        shutil.copyfile(canonical, target)
    return target.resolve()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Print (and write when missing) the CV_<Name>_<Surname>.pdf to upload.")
    p.add_argument("application", type=Path, help="<P>/openings/<ID>/application")
    p.add_argument("--contact", type=Path, help="contact.yaml (default: <P>/contact.yaml, three folders up)")
    args = p.parse_args(argv)
    if not args.application.is_dir():
        print(f"upload_copy: {args.application} is not a folder", file=sys.stderr)
        return 2
    contact = args.contact or args.application.resolve().parents[2] / "contact.yaml"
    try:
        print(upload_copy(args.application, contact))
    except (FileNotFoundError, ValueError) as exc:
        print(f"upload_copy: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
