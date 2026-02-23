"""integration/token_snapshot_store.py

Local snapshot cache for token/pool metrics used by gates and (later) features.

P0.1 goals:
- No external API calls.
- Deterministic: read a local snapshot file produced by Data-track.
- Zero required dependencies: CSV is supported out of the box.
- Parquet is supported *optionally* if the environment has a reader (pandas+pyarrow/fastparquet).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TokenSnapshot:
    mint: str
    ts_snapshot: Optional[str] = None
    liquidity_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    spread_bps: Optional[float] = None
    top10_holders_pct: Optional[float] = None
    single_holder_pct: Optional[float] = None
    extra: Optional[Dict[str, Any]] = None

    def get_security_data(self) -> Optional[Dict[str, Any]]:
        """Access security data from snapshot.extra["security"].

        Returns:
            Optional dict containing security data, or None if not available.
            Security fields include:
            - is_honeypot: Optional[bool]
            - freeze_authority: Optional[bool]
            - mint_authority: Optional[bool]
            - top_holders_pct: Optional[float]
        """
        if self.extra is None:
            return None
        return self.extra.get("security")


class TokenSnapshotStore:
    """Loads token snapshots from a local file into an in-memory map."""

    def __init__(self, path: str = None, csv_path: str = None):
        # Compatibility: allow csv_path=... (used by tools/tune_strategy.py)
        if path is None and csv_path is not None:
            path = csv_path

        self.path = str(path)
        self._by_mint: Dict[str, TokenSnapshot] = {}

    # ------------------------------------------------------------------
    # Compatibility constructors (used by tools/ scripts)
    # ------------------------------------------------------------------
    @classmethod
    def from_csv(cls, path: str) -> "TokenSnapshotStore":
        """Load a snapshot store from a CSV file.

        This is a thin wrapper kept for backward compatibility with tooling
        (e.g. dataset exporter) that expects `from_csv`.
        """
        store = cls(path)
        store.load()
        return store

    @classmethod
    def from_parquet(cls, path: str) -> "TokenSnapshotStore":
        """Load a snapshot store from a Parquet file.

        This is a thin wrapper kept for backward compatibility with tooling
        (e.g. dataset exporter) that expects `from_parquet`.
        """
        store = cls(path)
        store.load()
        return store

    def load(self) -> None:
        path = Path(self.path)
        if not path.exists():
            return

        rows = _read_snapshot_rows(path)
        if not rows:
            return

        # Keep latest per mint if ts_snapshot is present (string-sorted).
        # Data-track should ideally emit ISO timestamps.
        latest: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            mint = str(r.get("mint", "")).strip()
            if not mint:
                continue
            prev = latest.get(mint)
            if prev is None:
                latest[mint] = r
                continue
            ts_prev = str(prev.get("ts_snapshot") or "")
            ts_cur = str(r.get("ts_snapshot") or "")
            if ts_cur >= ts_prev:
                latest[mint] = r

        for mint, r in latest.items():
            # Extract security data from row if present
            extra = _extract_extra_data(r)

            self._by_mint[mint] = TokenSnapshot(
                mint=mint,
                ts_snapshot=_opt_str(r.get("ts_snapshot")),
                liquidity_usd=_opt_float(r.get("liquidity_usd")),
                volume_24h_usd=_opt_float(r.get("volume_24h_usd")),
                spread_bps=_opt_float(r.get("spread_bps")),
                top10_holders_pct=_opt_float(r.get("top10_holders_pct")),
                single_holder_pct=_opt_float(r.get("single_holder_pct")),
                extra=extra,
            )


    def count(self) -> int:
        """Return number of snapshots loaded in memory."""
        return len(self._by_mint)
    def get(self, mint: str) -> Optional[TokenSnapshot]:
        return self._by_mint.get(mint)

    def get_latest(self, mint: str) -> Optional[TokenSnapshot]:
        """Alias for get().

        The store keeps only the latest snapshot per mint when loading.
        Some callers use the more explicit name `get_latest`.
        """
        return self.get(mint)


def _extract_extra_data(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract extra data from a snapshot row, including security information.

    This function looks for security-related columns and packages them into
    the extra dict under the "security" key. Non-standard columns that are
    not explicit TokenSnapshot fields are also captured into extra.

    Security fields extracted:
    - is_honeypot: bool
    - freeze_authority: bool
    - mint_authority: bool
    - top_holders_pct: float (from security data, distinct from top10_holders_pct)

    Feature v2 fields captured from extra columns:
    - volatility_30s: float
    - price_change_5m_pct: float
    - smart_buy_ratio: float

    Args:
        row: Dictionary representing a snapshot row from CSV/Parquet

    Returns:
        Optional dict with extra data, or None if no extra data found
    """
    # Define explicit TokenSnapshot fields to exclude from extra
    explicit_fields = {
        "mint", "ts_snapshot", "liquidity_usd", "volume_24h_usd",
        "spread_bps", "top10_holders_pct", "single_holder_pct",
        "is_honeypot", "freeze_authority", "mint_authority",
        "security_top_holders_pct", "extra"
    }

    extra: Dict[str, Any] = {}
    security: Dict[str, Any] = {}

    # Extract security fields if present
    is_honeypot = row.get("is_honeypot")
    if is_honeypot is not None:
        security["is_honeypot"] = _opt_bool(is_honeypot)

    freeze_authority = row.get("freeze_authority")
    if freeze_authority is not None:
        security["freeze_authority"] = _opt_bool(freeze_authority)

    mint_authority = row.get("mint_authority")
    if mint_authority is not None:
        security["mint_authority"] = _opt_bool(mint_authority)

    # Extract security-specific top_holders_pct if present
    # This is distinct from the top10_holders_pct field used in token gates
    security_top_holders = row.get("security_top_holders_pct")
    if security_top_holders is not None:
        security["top_holders_pct"] = _opt_float(security_top_holders)

    # If we have security data, add it to extra
    if security:
        extra["security"] = security

    # Check for JSON-formatted extra column
    extra_json = row.get("extra")
    if extra_json:
        try:
            parsed = json.loads(str(extra_json))
            if isinstance(parsed, dict):
                # Merge with existing extra data, security takes precedence
                extra = {**parsed, **extra}
        except (json.JSONDecodeError, TypeError):
            pass  # Invalid JSON, skip

    # Capture any remaining non-standard columns into extra
    # This enables Feature v2 fields like volatility_30s, price_change_5m_pct, smart_buy_ratio
    for key, value in row.items():
        key_lower = key.lower().strip()
        if key_lower in explicit_fields:
            continue
        if key_lower.startswith("extra_"):
            # Legacy: columns prefixed with extra_
            clean_key = key_lower[6:]  # Remove "extra_" prefix
            extra[clean_key] = _opt_float(value) if value not in (None, "") else value
        elif key_lower in {"volatility_30s", "price_change_5m_pct", "smart_buy_ratio"}:
            # Feature v2 specific fields
            extra[key_lower] = _opt_float(value) if value not in (None, "") else value
        elif value is not None and str(value).strip() != "":
            # Capture other non-standard columns
            # Try to parse as float, keep as-is if not parseable
            parsed = _opt_float(value)
            if parsed is not None:
                extra[key_lower] = parsed
            else:
                extra[key_lower] = str(value).strip()

    return extra if extra else None


def _read_snapshot_rows(path: Path) -> list[Dict[str, Any]]:
    ext = path.suffix.lower()
    if ext in {".parquet", ".pq"}:
        # Optional Parquet support
        try:
            import pandas as pd  # type: ignore
            df = pd.read_parquet(path)
            return df.to_dict(orient="records")
        except Exception:
            # Fall back to sibling CSV if present
            csv_path = path.with_suffix(".csv")
            if csv_path.exists():
                return _read_snapshot_rows(csv_path)
            raise

    # Default: CSV
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _opt_float(x) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None


def _opt_str(x) -> Optional[str]:
    if x is None:
        return None
    s = str(x)
    return s if s != "" else None


def _opt_bool(x) -> Optional[bool]:
    """Convert a value to Optional[bool].

    Handles various boolean representations:
    - True/False (bool)
    - "true"/"false" (case-insensitive string)
    - "1"/"0" (string numbers)
    - 1/0 (int)
    """
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    s = str(x).strip().lower()
    if s == "":
        return None
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return None
