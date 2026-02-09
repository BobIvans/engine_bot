# PR-Z.3 — Trailing Stop Dynamic Adjustment (Volatility + Volume Adaptive)

## Goal

Implement an adaptive mechanism for dynamically adjusting trailing stop distance based on:
- **Realized volatility (RV)** - expands distance during high volatility (noise protection)
- **Volume profile** - contracts distance with confirming volume (faster profit capture)

Fully optional (`--enable-dynamic-trailing`), thread-safe, works in both simulator and live execution.

## Scope

| File | Purpose |
|------|---------|
| [`execution/market_features.py`](execution/market_features.py) | `MarketContext` with volatility/volume fields |
| [`execution/trailing_adjuster.py`](execution/trailing_adjuster.py) | `TrailingAdjuster` class |
| [`integration/fixtures/trailing/`](integration/fixtures/trailing/) | Test fixtures |
| [`scripts/trailing_dynamic_smoke.sh`](scripts/trailing_dynamic_smoke.sh) | Smoke test |
| [`config/runtime_schema.py`](config/runtime_schema.py) | Dynamic trailing params |
| [`integration/reject_reasons.py`](integration/reject_reasons.py) | `REJECT_TRAILING_ADJUST_INVALID` |

## Adaptation Rules

### Volatility Adaptation

| Condition | Factor | Rationale |
|-----------|--------|-----------|
| `rv_5m > trailing_rv_threshold_high` (default: 8%) | `× trailing_volatility_multiplier` (default: 1.8) | Expand for noise protection |
| `rv_5m < trailing_rv_threshold_low` (default: 3%) | `× max(0.7, multiplier × 0.8)` | Contract for tighter stops |

### Volume Adaptation

| Condition | Factor | Rationale |
|-----------|--------|-----------|
| LONG + `volume_delta > +threshold` | `× trailing_volume_multiplier` (0.9) | Confirming volume → contract |
| SHORT + `volume_delta < -threshold` | `× trailing_volume_multiplier` (0.9) | Confirming volume → contract |
| Volume against direction (strong) | `× 1.2` | Contrarian volume → expand slightly |

**Note:** Volume adaptation only applies when `unrealized_pnl_pct > 0.5%`.

### Safety Clamps

```
distance = clamp(distance, base_distance * 0.5, trailing_max_distance_bps)
```

- **Hard cap:** `trailing_max_distance_bps` (default: 500 = 5%)
- **Soft floor:** 50% of base distance

## Configuration Parameters

```python
dynamic_trailing_enabled: bool = False          # Master switch
trailing_base_distance_bps: int = 150          # Base distance (1.5%)
trailing_volatility_multiplier: float = 1.8    # × when RV high
trailing_volume_multiplier: float = 0.9         # × with confirming volume
trailing_max_distance_bps: int = 500            # Hard cap (5%)
trailing_rv_threshold_high: float = 0.08       # RV > 8% = high volatility
trailing_rv_threshold_low: float = 0.03        # RV < 3% = low volatility
trailing_volume_confirm_threshold: float = 1.5 # Volume delta threshold
```

## API

### `TrailingAdjuster.compute_distance_bps()`

```python
def compute_distance_bps(
    self,
    base_distance_bps: int,
    market_ctx: MarketContext,
    position_side: Literal["LONG", "SHORT"],
    unrealized_pnl_pct: float,
    log: bool = False
) -> int:
    """
    Returns adaptive trailing distance in basis points.
    
    Args:
        base_distance_bps: Starting trailing distance.
        market_ctx: Market context with RV and volume features.
        position_side: Position direction.
        unrealized_pnl_pct: Current unrealized P&L %.
        log: Log adjustment to stderr.
    """
```

### `MarketContext` Fields

```python
@dataclass
class MarketContext:
    ts: float                      # Timestamp
    mint: str                      # Token mint
    price: Decimal                 # Current price
    
    # Volatility
    rv_5m: float                   # Realized volatility 5m (annualized)
    rv_15m: float                  # Realized volatility 15m
    
    # Volume
    volume_delta_1m: float         # Normalized imbalance [-1.0, +1.0]
    volume_profile_score: float   # 0..1 trend confirmation
    
    # Optional
    liquidity_usd: Optional[float]
    spread_bps: Optional[float]
```

## Integration

### Simulator Integration (`execution/simulator.py`)

```python
if self._config.dynamic_trailing_enabled and position.has_trailing_stop:
    new_distance = self._trailing_adjuster.compute_distance_bps(
        base_distance_bps=self._config.trailing_base_distance_bps,
        market_ctx=market_ctx,
        position_side=position.side,
        unrealized_pnl_pct=position.unrealized_pnl_pct
    )
    position.trailing_distance_bps = new_distance
```

### Live Executor Integration (`execution/live_executor.py`)

Similar pattern in `on_market_update()` callback with outlier rejection for extreme RV values.

## Smoke Test

```bash
bash scripts/trailing_dynamic_smoke.sh
```

Expected output:
```
[trailing] Adjusted: 150 → 270 bps (RV=0.12, volume=+0.50)
[trailing] Adjusted: 270 → 120 bps (RV=0.02, volume=+0.80)
[trailing_dynamic_smoke] All PR-Z.3 smoke tests passed!
[trailing_dynamic_smoke] OK
```

## GREP Points

```bash
grep -n "class TrailingAdjuster" execution/trailing_adjuster.py
grep -n "trailing_base_distance_bps" config/runtime_schema.py
grep -n "compute_distance_bps" execution/trailing_adjuster.py
grep -n "REJECT_TRAILING_ADJUST_INVALID" integration/reject_reasons.py
grep -n "PR-Z.3" strategy/docs/overlay/PR_DYNAMIC_TRAILING.md
```

## Safety Properties

1. **Idempotency:** Same `MarketContext` → same output (no randomness)
2. **Outlier rejection:** RV > 50% → use base distance
3. **Hard cap:** Distance never exceeds `trailing_max_distance_bps`
4. **Optional:** Disabled by default, enabled via `--enable-dynamic-trailing`
5. **Thread-safe:** No shared mutable state
