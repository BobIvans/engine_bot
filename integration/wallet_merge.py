#!/usr/bin/env python3
"""integration/wallet_merge.py

PR-WD.5 Multi-Source Wallet Dedup & Merge.

Stage for merging wallet profiles from Dune, Flipside, and Kolscan sources
with deduplication by wallet_addr and best-effort conflict resolution:
- Numeric metrics (roi_30d, winrate_30d): value from profile with max trades_30d
- String fields (preferred_dex): priority source order - Dune > Flipside > Kolscan
- Lists (kolscan_flags): union of unique values from all sources

Output: wallets_merged.parquet in wallet_profile.v1 schema.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class WalletProfile:
    """Canonical wallet profile schema (wallet_profile.v1)."""
    wallet_addr: str
    roi_30d: Optional[float] = None
    winrate_30d: Optional[float] = None
    trades_30d: Optional[int] = None
    median_hold_sec: Optional[int] = None
    avg_size_usd: Optional[float] = None
    preferred_dex: Optional[str] = None
    memecoin_ratio: Optional[float] = None
    kolscan_rank: Optional[int] = None
    kolscan_flags: Optional[List[str]] = None
    last_active_ts: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values for parquet compatibility."""
        return {k: v for k, v in {
            "wallet_addr": self.wallet_addr,
            "roi_30d": self.roi_30d,
            "winrate_30d": self.winrate_30d,
            "trades_30d": self.trades_30d,
            "median_hold_sec": self.median_hold_sec,
            "avg_size_usd": self.avg_size_usd,
            "preferred_dex": self.preferred_dex,
            "memecoin_ratio": self.memecoin_ratio,
            "kolscan_rank": self.kolscan_rank,
            "kolscan_flags": self.kolscan_flags,
            "last_active_ts": self.last_active_ts,
        }.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WalletProfile":
        """Create from dictionary."""
        return cls(
            wallet_addr=str(data.get("wallet_addr", "")),
            roi_30d=data.get("roi_30d"),
            winrate_30d=data.get("winrate_30d"),
            trades_30d=data.get("trades_30d"),
            median_hold_sec=data.get("median_hold_sec"),
            avg_size_usd=data.get("avg_size_usd"),
            preferred_dex=data.get("preferred_dex"),
            memecoin_ratio=data.get("memecoin_ratio"),
            kolscan_rank=data.get("kolscan_rank"),
            kolscan_flags=data.get("kolscan_flags"),
            last_active_ts=data.get("last_active_ts"),
        )


def parse_csv_profiles(path: str) -> List[WalletProfile]:
    """Parse wallet profiles from CSV file."""
    profiles = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle kolscan_flags if present as comma-separated string
            kolscan_flags = None
            if row.get("kolscan_flags"):
                kolscan_flags = [f.strip() for f in row["kolscan_flags"].split(",") if f.strip()]
            
            # Parse numeric fields
            roi_30d = None
            if row.get("roi_30d"):
                try:
                    roi_30d = float(row["roi_30d"])
                except ValueError:
                    pass
            
            winrate_30d = None
            if row.get("winrate_30d"):
                try:
                    winrate_30d = float(row["winrate_30d"])
                except ValueError:
                    pass
            
            trades_30d = None
            if row.get("trades_30d"):
                try:
                    trades_30d = int(row["trades_30d"])
                except ValueError:
                    pass
            
            median_hold_sec = None
            if row.get("median_hold_sec"):
                try:
                    median_hold_sec = int(row["median_hold_sec"])
                except ValueError:
                    pass
            
            avg_size_usd = None
            if row.get("avg_size_usd"):
                try:
                    avg_size_usd = float(row["avg_size_usd"])
                except ValueError:
                    pass
            
            memecoin_ratio = None
            if row.get("memecoin_ratio"):
                try:
                    memecoin_ratio = float(row["memecoin_ratio"])
                except ValueError:
                    pass

            kolscan_rank = None
            if row.get("kolscan_rank"):
                try:
                    kolscan_rank = int(row["kolscan_rank"])
                except ValueError:
                    pass

            last_active_ts = None
            if row.get("last_active_ts"):
                try:
                    last_active_ts = int(row["last_active_ts"])
                except ValueError:
                    pass

            profiles.append(WalletProfile(
                wallet_addr=row.get("wallet_addr", ""),
                roi_30d=roi_30d,
                winrate_30d=winrate_30d,
                trades_30d=trades_30d,
                median_hold_sec=median_hold_sec,
                avg_size_usd=avg_size_usd,
                preferred_dex=row.get("preferred_dex"),
                memecoin_ratio=memecoin_ratio,
                kolscan_rank=kolscan_rank,
                kolscan_flags=kolscan_flags,
                last_active_ts=last_active_ts,
            ))
    return profiles


def parse_json_profiles(path: str) -> List[WalletProfile]:
    """Parse wallet profiles from JSON file."""
    profiles = []
    with open(path, "r") as f:
        data = json.load(f)
    
    # Handle both single object and list of objects
    if isinstance(data, dict):
        data = [data]
    
    for item in data:
        kolscan_flags = item.get("kolscan_flags")
        if kolscan_flags and isinstance(kolscan_flags, str):
            kolscan_flags = [f.strip() for f in kolscan_flags.split(",") if f.strip()]
        
        profiles.append(WalletProfile.from_dict(item))
    return profiles


def load_profiles(source: str, path: str) -> List[WalletProfile]:
    """Load wallet profiles from file based on source type."""
    if source in ("dune", "flipside"):
        return parse_csv_profiles(path)
    elif source == "kolscan":
        return parse_json_profiles(path)
    else:
        raise ValueError(f"Unknown source: {source}")


# Source priority for string fields (higher index = higher priority)
SOURCE_PRIORITY = {
    "kolscan": 0,
    "flipside": 1,
    "dune": 2,
}


def merge_wallet_profiles(
    sources: List[Tuple[str, List[WalletProfile]]]
) -> List[WalletProfile]:
    """Merge wallet profiles from multiple sources with conflict resolution.

    Args:
        sources: List of (source_name, profiles) tuples.
                 source_name ∈ {"dune", "flipside", "kolscan"}

    Returns:
        List of merged WalletProfile objects with deduplication.
        Sorted by wallet_addr for deterministic output.
    """
    # Collect all profiles by wallet address
    wallet_map: Dict[str, List[Tuple[str, WalletProfile]]] = {}
    for source_name, profiles in sources:
        for profile in profiles:
            if not profile.wallet_addr:
                continue
            if profile.wallet_addr not in wallet_map:
                wallet_map[profile.wallet_addr] = []
            wallet_map[profile.wallet_addr].append((source_name, profile))

    merged_profiles = []

    for wallet_addr, source_profiles in wallet_map.items():
        # Find max trades_30d for conflict resolution
        trades_30d_max = 0
        for _, profile in source_profiles:
            if profile.trades_30d is not None and profile.trades_30d > trades_30d_max:
                trades_30d_max = profile.trades_30d

        # For numeric fields: use value from profile with max trades_30d
        # For ties, use the first profile with max trades_30d
        profile_by_trades = {p.trades_30d or 0: p for _, p in source_profiles}
        primary_profile = profile_by_trades.get(trades_30d_max, source_profiles[0][1])

        # Build merged profile
        merged = WalletProfile(wallet_addr=wallet_addr)

        # Numeric fields: from profile with max trades_30d
        for field in ["roi_30d", "winrate_30d", "median_hold_sec", "avg_size_usd", "memecoin_ratio"]:
            value = getattr(primary_profile, field)
            setattr(merged, field, value)

        # String fields: from highest priority source
        for source_name, profile in source_profiles:
            if profile.preferred_dex:
                if merged.preferred_dex is None:
                    merged.preferred_dex = profile.preferred_dex
                elif SOURCE_PRIORITY.get(source_name, 0) > SOURCE_PRIORITY.get(
                    next((s for s, p in source_profiles if p.preferred_dex == merged.preferred_dex), ""), 0
                ):
                    merged.preferred_dex = profile.preferred_dex

        # For preferred_dex, find best source
        dex_sources = [(s, p) for s, p in source_profiles if p.preferred_dex]
        if dex_sources:
            best_source, _ = max(dex_sources, key=lambda x: SOURCE_PRIORITY.get(x[0], 0))
            for source_name, profile in dex_sources:
                if source_name == best_source:
                    merged.preferred_dex = profile.preferred_dex
                    break

        # kolscan_rank: take the first non-null value (any source can provide)
        for _, profile in source_profiles:
            if profile.kolscan_rank is not None:
                merged.kolscan_rank = profile.kolscan_rank
                break

        # kolscan_flags: union of all non-empty lists
        all_flags = set()
        for _, profile in source_profiles:
            if profile.kolscan_flags:
                all_flags.update(profile.kolscan_flags)
        merged.kolscan_flags = sorted(list(all_flags)) if all_flags else None

        # last_active_ts: take the most recent (larger value)
        last_active = None
        for _, profile in source_profiles:
            if profile.last_active_ts is not None:
                if last_active is None or profile.last_active_ts > last_active:
                    last_active = profile.last_active_ts
        merged.last_active_ts = last_active

        # trades_30d: take the maximum value
        max_trades = None
        for _, profile in source_profiles:
            if profile.trades_30d is not None:
                if max_trades is None or profile.trades_30d > max_trades:
                    max_trades = profile.trades_30d
        merged.trades_30d = max_trades

        merged_profiles.append(merged)

    # Sort by wallet_addr for deterministic output
    merged_profiles.sort(key=lambda p: p.wallet_addr)

    return merged_profiles


def write_parquet(profiles: List[WalletProfile], out_path: str) -> None:
    """Write profiles to Parquet file."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Build Arrow table
        rows = [p.to_dict() for p in profiles]
        if rows:
            schema = pa.schema([
                ("wallet_addr", pa.string()),
                ("roi_30d", pa.float64()),
                ("winrate_30d", pa.float64()),
                ("trades_30d", pa.int64()),
                ("median_hold_sec", pa.int64()),
                ("avg_size_usd", pa.float64()),
                ("preferred_dex", pa.string()),
                ("memecoin_ratio", pa.float64()),
                ("kolscan_rank", pa.int64()),
                ("kolscan_flags", pa.list_(pa.string())),
                ("last_active_ts", pa.int64()),
            ])

            # Create arrays for each field
            arrays = []
            for field_name, field_type in schema:
                values = []
                for row in rows:
                    val = row.get(field_name)
                    if val is None:
                        values.append(None)
                    elif isinstance(field_type, pa.ListType):
                        values.append(val)
                    else:
                        values.append(val)
                arrays.append(pa.array(values, type=field_type))

            table = pa.table(dict(zip([f.name for f in schema], arrays)))
            pq.write_table(table, out_path)
        else:
            # Empty table
            schema = pa.schema([
                ("wallet_addr", pa.string()),
                ("roi_30d", pa.float64()),
                ("winrate_30d", pa.float64()),
                ("trades_30d", pa.int64()),
                ("median_hold_sec", pa.int64()),
                ("avg_size_usd", pa.float64()),
                ("preferred_dex", pa.string()),
                ("memecoin_ratio", pa.float64()),
                ("kolscan_rank", pa.int64()),
                ("kolscan_flags", pa.list_(pa.string())),
                ("last_active_ts", pa.int64()),
            ])
            table = pa.table(schema)
            pq.write_table(table, out_path)

        print(f"[wallet_merge] Written {len(profiles)} profiles to {out_path}", file=sys.stderr)
    except ImportError:
        # Fallback: write as JSONL
        jsonl_path = out_path.replace(".parquet", ".jsonl")
        with open(jsonl_path, "w") as f:
            for p in profiles:
                f.write(json.dumps(p.to_dict()) + "\n")
        print(f"[wallet_merge] Written {len(profiles)} profiles to {jsonl_path} (JSONL fallback)", file=sys.stderr)


class WalletMergeStage:
    """Stage for merging wallet profiles from multiple sources."""

    def run(
        self,
        dune_profiles: List[WalletProfile],
        flipside_profiles: List[WalletProfile],
        kolscan_profiles: List[WalletProfile],
        out_path: str = "wallets_merged.parquet",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Run the merge stage.

        Args:
            dune_profiles: Wallet profiles from Dune source.
            flipside_profiles: Wallet profiles from Flipside source.
            kolscan_profiles: Wallet profiles from Kolscan source.
            out_path: Output file path.
            dry_run: If True, don't write to filesystem.

        Returns:
            Summary metrics dict.
        """
        print(f"[wallet_merge] Starting merge stage...", file=sys.stderr)
        print(f"[wallet_merge] Dune: {len(dune_profiles)} profiles", file=sys.stderr)
        print(f"[wallet_merge] Flipside: {len(flipside_profiles)} profiles", file=sys.stderr)
        print(f"[wallet_merge] Kolscan: {len(kolscan_profiles)} profiles", file=sys.stderr)

        # Build sources list with priority order for conflict resolution
        sources = [
            ("dune", dune_profiles),
            ("flipside", flipside_profiles),
            ("kolscan", kolscan_profiles),
        ]

        # Perform merge
        merged = merge_wallet_profiles(sources)

        print(f"[wallet_merge] Merged {len(merged)} unique wallets", file=sys.stderr)

        # Build summary
        summary = {
            "unique_wallets": len(merged),
            "sources_merged": sum(1 for _, profiles in sources if profiles),
            "schema_version": "wallet_profile.v1",
        }

        # Write output if not dry run
        if not dry_run:
            write_parquet(merged, out_path)
        else:
            print(f"[wallet_merge] Dry run - no file written", file=sys.stderr)

        return summary

    def to_summary_json(self, unique_wallets: int, sources_merged: int) -> str:
        """Generate summary JSON output."""
        return json.dumps({
            "unique_wallets": unique_wallets,
            "sources_merged": sources_merged,
            "schema_version": "wallet_profile.v1",
        })


def main() -> int:
    """CLI entry point for wallet merge stage."""
    ap = argparse.ArgumentParser(
        description="Multi-Source Wallet Dedup & Merge - Merge profiles from Dune, Flipside, Kolscan"
    )
    ap.add_argument("--input-dune", default="", help="Input Dune CSV file")
    ap.add_argument("--input-flipside", default="", help="Input Flipside CSV file")
    ap.add_argument("--input-kolscan", default="", help="Input Kolscan JSON file")
    ap.add_argument("--out-path", default="wallets_merged.parquet", help="Output Parquet file path")
    ap.add_argument("--dry-run", action="store_true", help="Don't write to filesystem")
    ap.add_argument(
        "--summary-json",
        action="store_true",
        help="Print summary as JSON to stdout",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output to stderr",
    )
    args = ap.parse_args()

    stage = WalletMergeStage()

    # Load profiles from input files
    dune_profiles = []
    flipside_profiles = []
    kolscan_profiles = []

    if args.input_dune:
        if args.verbose:
            print(f"[wallet_merge] Loading Dune profiles from {args.input_dune}", file=sys.stderr)
        dune_profiles = load_profiles("dune", args.input_dune)

    if args.input_flipside:
        if args.verbose:
            print(f"[wallet_merge] Loading Flipside profiles from {args.input_flipside}", file=sys.stderr)
        flipside_profiles = load_profiles("flipside", args.input_flipside)

    if args.input_kolscan:
        if args.verbose:
            print(f"[wallet_merge] Loading Kolscan profiles from {args.input_kolscan}", file=sys.stderr)
        kolscan_profiles = load_profiles("kolscan", args.input_kolscan)

    # Run merge stage
    summary = stage.run
    # Run merge stage
    summary = stage.run(
        dune_profiles=dune_profiles,
        flipside_profiles=flipside_profiles,
        kolscan_profiles=kolscan_profiles,
        out_path=args.out_path,
        dry_run=args.dry_run,
    )

    # Print summary
    if args.summary_json:
        print(stage.to_summary_json(summary["unique_wallets"], summary["sources_merged"]))
    else:
        print(f"[wallet_merge] Summary: {summary}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
