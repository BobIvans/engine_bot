#!/usr/bin/env python3
"""integration/allowlist_loader.py

Loads a wallet allowlist from strategy artifacts and produces a deterministic hash.

Why this exists:
- Wallet allowlists are strategy-owned (strategy/**), not CANON (vendor/**).
- We need allowlist_hash to log into ClickHouse (forensics_events) so runs are
  reproducible and debuggable.

Supported formats:
- YAML: either {"wallets": [...]} or a plain list
- CSV: first column contains wallet addresses (header optional)
- TXT: one wallet per line; "#" comments allowed

Outputs:
- wallets: de-duplicated list preserving input order
- allowlist_hash: sha256 of normalized wallets joined by "\n"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


class AllowlistError(RuntimeError):
    pass


def _normalize_wallet(w: str) -> str:
    return w.strip()


def _dedupe_preserve(xs: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in xs:
        x = _normalize_wallet(str(x))
        if not x or x.startswith("#"):
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _hash_wallets(wallets: List[str]) -> str:
    blob = "\n".join(wallets).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_allowlist(path: str | Path) -> Tuple[List[str], str]:
    """Return (wallets, allowlist_hash)."""
    p = Path(path)
    if not p.exists():
        raise AllowlistError(f"Allowlist file not found: {p}")

    suffix = p.suffix.lower()

    if suffix in (".yml", ".yaml"):
        if yaml is None:
            raise AllowlistError("PyYAML is required to load YAML allowlists.")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
        if isinstance(data, dict):
            wallets = data.get("wallets", [])
        else:
            wallets = data
        if not isinstance(wallets, list):
            raise AllowlistError("YAML allowlist must be a list or a dict with key 'wallets'.")
        wl = _dedupe_preserve([str(x) for x in wallets])
        return wl, _hash_wallets(wl)

    if suffix == ".csv":
        rows: List[str] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if not row:
                    continue
                first = str(row[0]).strip()
                if i == 0 and first.lower() in ("wallet", "address", "wallet_address"):
                    continue
                rows.append(first)
        wl = _dedupe_preserve(rows)
        return wl, _hash_wallets(wl)

    # Default: TXT (or unknown extension) — one per line
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    wl = _dedupe_preserve(lines)
    return wl, _hash_wallets(wl)


def main() -> None:
    ap = argparse.ArgumentParser(description="Load wallet allowlist and print hash.")
    ap.add_argument("--path", "--allowlist-path", dest="path", default="strategy/wallet_allowlist.yaml", help="Path to allowlist file.")
    ap.add_argument("--show", type=int, default=5, help="Show up to N sample wallets.")
    args = ap.parse_args()

    wallets, h = load_allowlist(args.path)
    out = {
        "path": str(args.path),
        "wallets_count": len(wallets),
        "allowlist_hash": h,
        "sample_wallets": wallets[: max(0, args.show)],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
