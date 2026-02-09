#!/usr/bin/env python3
"""Policy checker for CI and agents.

Reads policy/agent_policy.yaml and enforces:
- No SQL/DDL/queries.yaml outside CANON
- No second-canon dirs outside CANON
- No legacy strings in overlay docs
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit("PyYAML is required to run scripts/policy_check.py") from e

REPO_ROOT = Path(__file__).resolve().parents[1]

def _load_policy() -> dict:
    p = REPO_ROOT / "policy" / "agent_policy.yaml"
    if not p.exists():
        raise SystemExit(f"Policy file not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p

def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except Exception:
        return False

def fail(msg: str) -> None:
    print(f"POLICY FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def main() -> None:
    pol = _load_policy()
    canon_rel = Path(pol["canon"]["path"])
    overlay_rel = Path(pol["strategy_docs"]["overlay_path"])
    canon = (REPO_ROOT / canon_rel).resolve()
    overlay = (REPO_ROOT / overlay_rel).resolve()

    if not canon.exists():
        fail(f"CANON path missing: {canon_rel}")

    # 1) Forbidden globs outside canon
    for glob_pat in pol["forbidden"]["globs_outside_canon"]:
        for p in REPO_ROOT.rglob(glob_pat):
            if p.is_dir():
                continue
            if _is_under(p.resolve(), canon):
                continue
            fail(f"Forbidden file outside CANON: {p.as_posix()} (matched {glob_pat})")

    # 2) Forbidden dirs outside canon
    for dname in pol["forbidden"]["dirs_outside_canon"]:
        for p in REPO_ROOT.rglob(dname):
            if not p.is_dir():
                continue
            if _is_under(p.resolve(), canon):
                continue
            # allow docs-only mentions inside overlay as directories? directories are still drift.
            fail(f"Forbidden directory outside CANON: {p.as_posix()}")

    # 3) Forbidden strings in overlay docs
    if overlay.exists():
        bad = pol["forbidden"].get("strings_in_overlay", [])
        # only check text-ish files
        exts = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}
        for f in _iter_files(overlay):
            if f.suffix.lower() not in exts:
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for s in bad:
                if s in txt:
                    fail(f"Forbidden string '{s}' found in overlay: {f.as_posix()}")

    print("OK policy_check")
    sys.exit(0)

if __name__ == "__main__":
    main()
