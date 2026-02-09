# PR-WD.5: Multi-Source Wallet Dedup & Merge

## Overview

Stage for merging wallet profiles from Dune, Flipside, and Kolscan sources with deduplication and conflict resolution.

## Conflict Resolution Rules

| Field Type | Rule |
|------------|------|
| Numeric (roi_30d, winrate_30d, median_hold_sec, avg_size_usd, memecoin_ratio) | Value from profile with max `trades_30d` |
| String (preferred_dex) | Priority: Dune > Flipside > Kolscan |
| Lists (kolscan_flags) | Union of unique values from all sources |
| kolscan_rank | First non-null value found |
| last_active_ts | Most recent (larger value) |
| trades_30d | Maximum value across sources |

## Source Priority Order

1. **Dune** (highest priority for string fields)
2. **Flipside** (medium priority)
3. **Kolscan** (lowest priority, for enrichment only)

## CLI Usage

```bash
python3 -m integration.wallet_merge \
  --input-dune fixtures/discovery/dune_sample_merge.csv \
  --input-flipside fixtures/discovery/flipside_sample_merge.csv \
  --input-kolscan fixtures/discovery/kolscan_sample_merge.json \
  --out-path wallets_merged.parquet \
  --dry-run \
  --summary-json
```

## Output Schema

```json
{
  "wallet_addr": "W1",
  "roi_30d": 0.42,
  "winrate_30d": 0.75,
  "trades_30d": 142,
  "median_hold_sec": 120,
  "avg_size_usd": 2500,
  "preferred_dex": "Raydium",
  "memecoin_ratio": 0.85,
  "kolscan_rank": 17,
  "kolscan_flags": ["verified", "memecoin_specialist"],
  "last_active_ts": 1738945200
}
```

## Integration

```python
from integration.wallet_merge import WalletMergeStage, merge_wallet_profiles

stage = WalletMergeStage()
merged = stage.run(
    dune_profiles=dune_profiles,
    flipside_profiles=flipside_profiles,
    kolscan_profiles=kolscan_profiles,
    out_path="wallets_merged.parquet",
    dry_run=False
)
# Returns: {"unique_wallets": 4, "sources_merged": 3, "schema_version": "wallet_profile.v1"}
```

## Smoke Test

```bash
bash scripts/wallet_merge_smoke.sh
```

Expected output:
```
[wallet_merge_smoke] unique_wallets = 4 ✅
[wallet_merge_smoke] sources_merged = 3 ✅
[wallet_merge_smoke] W3 roi_30d = 0.49 (from Flipside) ✅
[wallet_merge_smoke] W1 kolscan_flags enriched ✅
[wallet_merge_smoke] OK
```

## Files

- `integration/wallet_merge.py` - Main merge stage implementation
- `scripts/wallet_merge_smoke.sh` - Smoke test
- `integration/fixtures/discovery/dune_sample_merge.csv` - Dune fixture
- `integration/fixtures/discovery/flipside_sample_merge.csv` - Flipside fixture
- `integration/fixtures/discovery/kolscan_sample_merge.json` - Kolscan fixture
