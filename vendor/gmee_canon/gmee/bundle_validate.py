from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    n = 0
    with path.open("rb") as f:
        for _ in f:
            n += 1
    return n


def validate_manifest(manifest_path: Path) -> List[str]:
    problems: list[str] = []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = data.get("files", {})
    if not isinstance(files, dict):
        return ["manifest.files must be a dict"]

    for rel, meta in files.items():
        fp = manifest_path.parent / rel
        if not fp.exists():
            problems.append(f"missing file: {rel}")
            continue
        want_sha = (meta or {}).get("sha256")
        want_lines = (meta or {}).get("row_count")
        got_sha = sha256_file(fp)
        if want_sha and got_sha != want_sha:
            problems.append(f"sha256 mismatch for {rel}: want={want_sha} got={got_sha}")
        if want_lines is not None:
            got_lines = count_lines(fp)
            if int(got_lines) != int(want_lines):
                problems.append(f"row_count mismatch for {rel}: want={want_lines} got={got_lines}")
    return problems


def validate_bundle(bundle_dir: Path) -> List[str]:
    """Validate a trade-bundle dir or trace-bundle dir."""
    problems: list[str] = []
    if (bundle_dir / "manifest.json").exists():
        problems.extend(validate_manifest(bundle_dir / "manifest.json"))
    if (bundle_dir / "trace_manifest.json").exists():
        problems.extend(validate_manifest(bundle_dir / "trace_manifest.json"))
        trades_dir = bundle_dir / "trades"
        if trades_dir.exists():
            for d in trades_dir.iterdir():
                if d.is_dir() and (d / "manifest.json").exists():
                    problems.extend(validate_manifest(d / "manifest.json"))
    if not ((bundle_dir / "manifest.json").exists() or (bundle_dir / "trace_manifest.json").exists()):
        problems.append("no manifest.json or trace_manifest.json found")
    return problems
