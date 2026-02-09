"""integration/parquet_io.py

P0.2: Offline replay bridge between Data-track (Parquet) and Bot-track (paper pipeline).

Design goals:
- Stream rows (avoid loading the full file into memory).
- Keep dependencies minimal. We rely on DuckDB (Python package) which can read Parquet
  without requiring pyarrow/fastparquet.

Minimum required columns (by default):
  ts, wallet, mint, side, price, size_usd, platform, tx_hash

Optional columns supported:
  pool_id, liquidity_usd, volume_24h_usd, spread_bps, honeypot_pass,
  wallet_roi_30d_pct, wallet_winrate_30d, wallet_trades_30d

If your parquet uses different column names, pass a mapping dict and we will rename
columns on the fly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional


@dataclass(frozen=True)
class ParquetReadConfig:
    path: str
    limit: Optional[int] = None
    batch_size: int = 2000
    colmap: Optional[Dict[str, str]] = None  # target_col -> source_col


def iter_parquet_records(cfg: ParquetReadConfig) -> Iterator[Dict[str, Any]]:
    """Yield dict rows from a Parquet file.

    Uses DuckDB's read_parquet() and fetchmany() to stream.

    Raises RuntimeError with a friendly message if duckdb isn't available.
    """

    try:
        import duckdb  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "duckdb is required for Parquet replay. Install with: pip install -r requirements.txt"
        ) from e

    con = duckdb.connect(database=":memory:")

    # Read everything, but optionally only a subset of columns if colmap is provided.
    select_expr = "*"
    if cfg.colmap:
        # Select source columns and alias to target columns
        # Example: SELECT source_ts AS ts, source_wallet AS wallet, ...
        parts = []
        for target_col, source_col in cfg.colmap.items():
            parts.append(f"{duckdb.escape_identifier(source_col)} AS {duckdb.escape_identifier(target_col)}")
        select_expr = ", ".join(parts)

    q = f"SELECT {select_expr} FROM read_parquet(?)"
    if cfg.limit is not None:
        q += f" LIMIT {int(cfg.limit)}"

    cur = con.execute(q, [cfg.path])
    colnames = [d[0] for d in cur.description]

    while True:
        rows = cur.fetchmany(cfg.batch_size)
        if not rows:
            break
        for row in rows:
            yield {colnames[i]: row[i] for i in range(len(colnames))}

