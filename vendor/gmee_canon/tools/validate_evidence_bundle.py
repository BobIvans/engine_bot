#!/usr/bin/env python3
"""Validate an evidence bundle (trade or trace scope)."""

from __future__ import annotations

import argparse
from pathlib import Path

from gmee.bundle_validate import validate_bundle


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="Path to a trade bundle dir or trace bundle dir")
    args = ap.parse_args()

    bundle = Path(args.bundle).resolve()
    if not bundle.exists():
        print("bundle not found")
        return 2

    problems = validate_bundle(bundle)
    if not problems:
        print("OK")
        return 0
    for p in problems:
        print("ERROR:", p)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
