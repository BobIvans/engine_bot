"""ingestion/sources/dune_source.py

Dune CSV source for historical trade data ingestion.
"""

from __future__ import annotations

import csv
from typing import Any, Dict, Iterator


class DuneSource:
    """Trade source for Dune CSV exports."""

    # Column mapping from Dune CSV columns to internal trade fields
    COLUMN_MAP = {
        "block_time": "ts",
        "tx_hash": "tx_hash",
        "tx_signer": "wallet",
        "token_bought_address": "mint",
        "usd_value": "size_usd",
    }

    def __init__(self, file_path: str):
        """Initialize with path to Dune CSV file.

        Args:
            file_path: Path to the CSV file exported from Dune.
        """
        self.file_path = file_path

    def iter_records(self) -> Iterator[Dict[str, Any]]:
        """Yield records from Dune CSV file mapped to internal format.

        Yields:
            Dict with mapped fields: ts, tx_hash, wallet, mint, size_usd,
            and extra info (token_sold_address).
        """
        with open(self.file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                record = self._map_row(row)
                if record is not None:
                    yield record

    def _map_row(self, row: Dict[str, str]) -> Dict[str, Any] | None:
        """Map a single CSV row to internal format.

        Args:
            row: Raw CSV row dict.

        Returns:
            Mapped record dict or None if required fields are missing.
        """
        # Extract and map fields
        ts = self._parse_timestamp(row.get("block_time"))
        tx_hash = row.get("tx_hash")
        wallet = row.get("tx_signer")
        mint = row.get("token_bought_address")
        size_usd = self._parse_float(row.get("usd_value"))
        token_sold_address = row.get("token_sold_address")

        # Skip rows with missing required fields
        if ts is None or tx_hash is None or wallet is None or mint is None:
            return None

        record: Dict[str, Any] = {
            "ts": ts,
            "tx_hash": tx_hash,
            "wallet": wallet,
            "mint": mint,
            "size_usd": size_usd,
        }

        # Add extra info if token_sold_address is present
        if token_sold_address:
            record["extra"] = {"token_sold_address": token_sold_address}

        return record

    def _parse_timestamp(self, value: str | None) -> str | None:
        """Parse timestamp string to ISO format.

        Args:
            value: Timestamp string (may be empty or null).

        Returns:
            Parsed timestamp string or None if invalid.
        """
        if not value or not value.strip():
            return None
        # Dune timestamps are typically ISO format
        # Return as-is if already valid, strip whitespace
        return value.strip()

    def _parse_float(self, value: str | None) -> float | None:
        """Parse float string to numeric value.

        Args:
            value: Numeric string (may be empty or null).

        Returns:
            Parsed float or None if invalid.
        """
        if not value or not value.strip():
            return None
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
