"""integration/wallet_profile_store.py

Wallet profile cache (offline / fixtures-first).

Iteration-2 goal:
- Allow deterministic enrichment of Trade fields (ROI/winrate/trades/tier/hold stats)
  without depending on Dune/BigQuery/Flipside.

The store is intentionally tiny:
- CSV/Parquet input
- in-memory dict keyed by wallet

This module does NOT decide anything. Gates/Signals/Risk consume the enriched fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class WalletProfile:
    wallet: str
    tier: Optional[str] = None
    roi_30d_pct: Optional[float] = None
    winrate_30d: Optional[float] = None
    trades_30d: Optional[int] = None
    median_hold_sec: Optional[float] = None
    avg_trade_size_sol: Optional[float] = None


class WalletProfileStore:
    def __init__(self, by_wallet: Dict[str, WalletProfile]):
        self._by_wallet = by_wallet

    def get(self, wallet: str) -> Optional[WalletProfile]:
        return self._by_wallet.get(wallet)

    @staticmethod
    def from_csv(path: str) -> "WalletProfileStore":
        import csv

        by_wallet: Dict[str, WalletProfile] = {}
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                w = (row.get("wallet") or "").strip()
                if not w:
                    continue
                by_wallet[w] = WalletProfile(
                    wallet=w,
                    tier=(row.get("tier") or "").strip() or None,
                    roi_30d_pct=_to_float(row.get("roi_30d_pct")),
                    winrate_30d=_to_float(row.get("winrate_30d")),
                    trades_30d=_to_int(row.get("trades_30d")),
                    median_hold_sec=_to_float(row.get("median_hold_sec")),
                    avg_trade_size_sol=_to_float(row.get("avg_trade_size_sol")),
                )
        return WalletProfileStore(by_wallet)

    @staticmethod
    def from_parquet(path: str) -> "WalletProfileStore":
        """Parquet loader (requires duckdb; already in requirements.txt)."""
        import duckdb

        rows = duckdb.sql(
            """
            SELECT
              wallet,
              tier,
              roi_30d_pct,
              winrate_30d,
              trades_30d,
              median_hold_sec,
              avg_trade_size_sol
            FROM read_parquet(?)
            """,
            [path],
        ).fetchall()

        by_wallet: Dict[str, WalletProfile] = {}
        for (
            wallet,
            tier,
            roi_30d_pct,
            winrate_30d,
            trades_30d,
            median_hold_sec,
            avg_trade_size_sol,
        ) in rows:
            if not wallet:
                continue
            by_wallet[str(wallet)] = WalletProfile(
                wallet=str(wallet),
                tier=str(tier) if tier is not None else None,
                roi_30d_pct=_to_float(roi_30d_pct),
                winrate_30d=_to_float(winrate_30d),
                trades_30d=_to_int(trades_30d),
                median_hold_sec=_to_float(median_hold_sec),
                avg_trade_size_sol=_to_float(avg_trade_size_sol),
            )
        return WalletProfileStore(by_wallet)


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None
