#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from gmee.report_html import render_bundle_report

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="path to trade/trace evidence bundle directory")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    p = render_bundle_report(Path(args.bundle), limit_per_file=int(args.limit))
    print(str(p))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
