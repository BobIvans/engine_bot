# PR-H.3 — Wallet Pruning & Promotion Logic

**Status:** Implemented  
**Date:** 2024-01-15  
**Author:** Strategy Team

## Overview

Manages the daily refresh of the Active Wallet Universe:
- Prunes underperforming wallets based on 7-day metrics
- Promotes high-quality candidates from Discovery Universe
- Maintains Active Universe quality thresholds

## Architecture

### Components

1. **`strategy/promotion.py`** - Pure logic for pruning/promotion
   - `daily_prune_and_promote()` - Main deterministic function
   - `PromotionParams` - Configuration dataclass
   - `WalletProfileInput` - Input profile representation

2. **`integration/candidate_promotion_stage.py`** - Glue layer
   - Reads active/candidate wallets from CSV
   - Calls pure promotion logic
   - Saves updated Active Universe

3. **`integration/reject_reasons.py`** - Reject reason constants
   - `WALLET_WINRATE_7D_LOW` - 7-day winrate below threshold
   - `WALLET_TRADES_7D_LOW` - 7-day trades below threshold
   - `WALLET_ROI_7D_LOW` - 7-day ROI below threshold

## Configuration

### Config Structure (params_base.yaml)

```yaml
prune:
  winrate_7d_min: 0.55     # Minimum 7-day winrate to stay active
  min_trades_7d: 8          # Minimum 7-day trades to stay active
  roi_7d_min: -0.10         # Minimum 7-day ROI (allows small loss)

promote:
  min_winrate_30d: 0.62    # Minimum 30-day winrate for promotion
  min_roi_30d: 0.18         # Minimum 30-day ROI for promotion
  min_trades_30d: 45        # Minimum 30-day trades for promotion
  max_candidates_to_promote: 30
```

## Implementation Details

### Pure Function: `daily_prune_and_promote()`

```python
def daily_prune_and_promote(
    active_profiles: List[WalletProfileInput],
    candidate_profiles: List[WalletProfileInput],
    params: PromotionParams,
) -> Tuple[List[WalletProfileInput], List[Dict[str, Any]]]:
```

**Returns:**
- `remaining_active`: Wallets that passed pruning criteria
- `pruned_wallets`: List of `{wallet, reason, metrics}` dicts

### Pruning Logic

A wallet is **pruned** if ANY of:
1. `winrate_7d < prune.winrate_7d_min`
2. `trades_7d < prune.min_trades_7d`
3. `roi_7d < prune.roi_7d_min`

### Promotion Logic

A candidate is **promoted** if ALL of:
1. `winrate_30d >= promote.min_winrate_30d`
2. `roi_30d >= promote.min_roi_30d`
3. `trades_30d >= promote.min_trades_30d`

## Integration Points

### With Wallet Profile Store

```python
# In paper_pipeline.py with --skip-promotion=false
active_wallets = wallet_profile_store.load_active()
candidates = wallet_profile_store.load_candidates()

remaining, pruned = daily_prune_and_promote(active_wallets, candidates, params)

# Save updated active universe
wallet_profile_store.save_active(remaining)

# Log pruned wallets
for p in pruned:
    logger.info(f"PRUNED: {p['wallet']} reason={p['reason']}")
```

### CLI Flags

```bash
--skip-promotion         # Skip promotion stage (default: False)
--promotion-dry-run      # Don't save changes (for testing)
```

## Testing

### Smoke Test

```bash
bash scripts/promotion_smoke.sh
```

**Expected Output:**
```
[promotion_smoke] wallet_winrate_7d_low is known reason
[promotion_smoke] wallet_trades_7d_low is known reason
[promotion_smoke] wallet_roi_7d_low is known reason
[promotion_smoke] Test 2 PASSED: remaining_active_count correct
[promotion_smoke] Test 3 PASSED: all pruned wallets have valid reasons
[promotion_smoke] OK
```

### Test Cases

| Scenario | Input | Expected |
|----------|-------|----------|
| Prune low winrate | `winrate_7d=0.40` | `reason=wallet_winrate_7d_low` |
| Prune low trades | `trades_7d=5` | `reason=wallet_trades_7d_low` |
| Prune low ROI | `roi_7d=-0.20` | `reason=wallet_roi_7d_low` |
| Promote qualified | `winrate_30d=0.75, trades_30d=100` | Promoted |
| Reject unqualified | `winrate_30d=0.50` | Not promoted |

## Reject Reasons

All prune reasons are validated via `assert_reason_known()`:

```python
from integration.reject_reasons import (
    WALLET_WINRATE_7D_LOW,
    WALLET_TRADES_7D_LOW,
    WALLET_ROI_7D_LOW,
    assert_reason_known,
)

# Validate all reasons
for reason in [WALLET_WINRATE_7D_LOW, WALLET_TRADES_7D_LOW, WALLET_ROI_7D_LOW]:
    assert_reason_known(reason)
```

## Performance

- **Deterministic**: Same output for same input
- **O(n + m)**: Linear in active + candidate count
- **Memory**: O(n + m) for storing profiles

## Future Enhancements

1. **Weighted scoring**: Composite score instead of thresholds
2. **Batch promotion**: Gradual promotion over multiple days
3. **Rollback**: Ability to undo promotion/pruning
4. **Metrics tracking**: Historical pruning/promotion stats
