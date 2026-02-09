#!/usr/bin/env python3
"""integration/ch_client.py

Single source of truth for ClickHouse connection settings across integration scripts.

Environment variables:
- CLICKHOUSE_URL (default: http://localhost:8123)
- CLICKHOUSE_USER (default: default)
- CLICKHOUSE_PASSWORD (default: empty)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Vendored CANON runner
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR = REPO_ROOT / "vendor" / "gmee_canon"
sys.path.insert(0, str(VENDOR))

from gmee.clickhouse import ClickHouseQueryRunner  # type: ignore


@dataclass(frozen=True)
class ClickHouseConfig:
    url: str = os.getenv("CLICKHOUSE_URL", "http://localhost:8123")
    user: str = os.getenv("CLICKHOUSE_USER", "default")
    password: str = os.getenv("CLICKHOUSE_PASSWORD", "")

    @staticmethod
    def from_args(url: str | None, user: str | None, password: str | None) -> "ClickHouseConfig":
        return ClickHouseConfig(
            url=(url or os.getenv("CLICKHOUSE_URL", "http://localhost:8123")),
            user=(user or os.getenv("CLICKHOUSE_USER", "default")),
            password=(password or os.getenv("CLICKHOUSE_PASSWORD", "")),
        )


def make_runner(cfg: ClickHouseConfig) -> ClickHouseQueryRunner:
    return ClickHouseQueryRunner(base_url=cfg.url, user=cfg.user, password=cfg.password)
