#!/usr/bin/env python3
"""Guard: wallet_profile_30d VIEW must be deterministic (P0).

Requirements (P0):
- wallet_profile_30d must NOT be anchored on now()/today()/currentTimestamp.
- It MUST anchor on a deterministic dataset-derived reference (canonical: max(day) anchor).

This is a CI backstop, not a full SQL parser.
We only analyze the CREATE VIEW wallet_profile_30d statement inside schemas/clickhouse.sql.
"""

from __future__ import annotations

import re
from pathlib import Path

DDL_PATH = Path("schemas/clickhouse.sql")


def _extract_view_stmt(sql: str) -> str:
    # Capture from CREATE VIEW ... wallet_profile_30d AS ... ; (first semicolon)
    m = re.search(
        r"CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS\s+wallet_profile_30d\s+AS\s+.*?;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        raise SystemExit("Missing CREATE VIEW IF NOT EXISTS wallet_profile_30d statement in schemas/clickhouse.sql")
    return m.group(0)


def main() -> int:
    sql = DDL_PATH.read_text(encoding="utf-8")
    view = _extract_view_stmt(sql)
    vlow = view.lower()

    # Hard ban on time-now anchors (only within the view statement).
    banned_tokens = [
        "now(",
        "now64(",
        "today(",
        "today64(",
        "yesterday(",
        "current_timestamp",
        "currenttimestamp",
        "current_date",
        "currentdate",
        "toDate(now",
        "toDateTime(now",
    ]
    hits = [t for t in banned_tokens if t.lower() in vlow]
    if hits:
        print("Determinism guard failed: wallet_profile_30d uses non-deterministic time anchors:")
        for h in sorted(set(hits)):
            print(f"  - {h}")
        return 2

    # Positive signal: must include anchor_day computed from max(day)
    if "max(day)" not in vlow and "anchor_day" not in vlow:
        print("Determinism guard failed: wallet_profile_30d missing expected deterministic anchor (max(day)/anchor_day)")
        return 3

    print("OK: wallet_profile_30d appears deterministic (anchored on dataset, not now())")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
