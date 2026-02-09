#!/usr/bin/env python3
"""P0 repo audit.

- Verifies canonical file hashes.
- Ensures no Python bytecode caches are present.

No network. No ClickHouse required.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON_HASH_FILE = REPO_ROOT / "ci" / "canonical_sha256.txt"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_canonical_hashes() -> int:
    if not CANON_HASH_FILE.exists():
        print(f"ERROR: missing {CANON_HASH_FILE}")
        return 2

    bad = 0
    for line in CANON_HASH_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected, rel = line.split(maxsplit=1)
        p = REPO_ROOT / rel
        if not p.exists():
            print(f"MISSING: {rel}")
            bad += 1
            continue
        got = sha256_file(p)
        if got != expected:
            print(f"MISMATCH: {rel}\n  expected={expected}\n  got     ={got}")
            bad += 1

    if bad == 0:
        print("OK: canonical hashes")
        return 0
    print(f"FAIL: {bad} canonical hash mismatches")
    return 1


def check_no_bytecode() -> int:
    bad_paths = []
    for p in REPO_ROOT.rglob("*"):
        if p.is_dir() and p.name == "__pycache__":
            bad_paths.append(str(p.relative_to(REPO_ROOT)))
        elif p.is_file() and p.suffix == ".pyc":
            bad_paths.append(str(p.relative_to(REPO_ROOT)))

    if not bad_paths:
        print("OK: no __pycache__/*.pyc")
        return 0

    print("FAIL: bytecode caches present:")
    for bp in bad_paths:
        print(f"  - {bp}")
    return 1


def main() -> int:
    rc = 0
    rc |= check_canonical_hashes()
    rc |= check_no_bytecode()
    return 1 if rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
