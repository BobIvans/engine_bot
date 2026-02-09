"""integration/signals_dump.py

PR-8.1: Deterministic signals dump (JSONL) for DuckDB/Parquet.

This module provides atomic writing of signal records to JSONL files,
enabling deterministic sidecar dumps for offline analysis.

Key features:
- Atomic write via tmp file + os.replace
- Deterministic output (no randomness, no external calls)
- Schema version "signals.v1" for DuckDB/Parquet compatibility
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def write_signals_jsonl_atomic(path: str, rows: list[dict[Any, Any]]) -> None:
    """Write signals to tmp file then atomically replace.

    Args:
        path: Destination path for the JSONL file
        rows: List of signal record dictionaries to write

    Raises:
        OSError: On file write errors
    """
    if not rows:
        # If no rows, write empty file atomically
        with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(path) or ".", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        return

    # Write to temporary file first
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".signals_dump_",
        suffix=".jsonl",
        dir=os.path.dirname(path) or ".",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    # Atomic replace
    os.replace(tmp_path, path)
