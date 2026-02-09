# PR-S.2 — Unified Decision Logic

**Status:** Implemented
**Owner:** Strategy Layer
**Date:** 2025-02-07

## Overview

`CopyScalpStrategy` implements "One-Formula" decision logic that deterministically transforms state (Wallet + Token + Polymarket) into trading Signals (ENTER/SKIP) with execution parameters (Mode, Size, TP/SL).

## Decision Pipeline

```
Hard Gates → P_model → EV → Regime → Limits → Signal
```

### Stage 1: Hard Gates

Hard stops that reject tokens/wallets without further analysis:

| Gate | Parameter | Default | Description |
|------|-----------|---------|-------------|
| Token Liquidity | `min_liquidity_usd` | $10,000 | Minimum USD liquidity |
| Token Volume | `min_volume_24h` | $5,000 | 24h volume threshold |
| Wallet Winrate | `min_wallet_winrate` | 0.4 | Min win rate (40%) |
| Wallet ROI | `min_wallet_roi` | 0.0 | Min mean ROI |
| Trade Count | `min_trade_count` | 5 | Min number of trades |
| Buy Tax | `max_buy_tax_bps` | 1000 | Max buy tax (10%) |
| Sell Tax | `max_sell_tax_bps` | 1000 | Max sell tax (10%) |
| Honeypot | `is_honeypot` | false | Must not be honeypot |

### Stage 2: Polymarket Regime

Calculates market regime based on Polymarket probability:

```
r = clip(a*(2*bullish-1) - b*event_risk, -1, 1)
```

Where:
- `bullish = probability` (0-1)
- `event_risk = 1 - liquidity_score` (low liquidity = high risk)
- `a = regime_a` (default 1.0)
- `b = regime_b` (default 0.5)

Returns `r` in [-1, 1]:
- **1** = Strongly bullish
- **0** = Neutral
- **-1** = Strongly bearish

### Stage 3: P_model (Probability Model)

Estimates success probability:

```
p = wallet_winrate + regime_adjustment + smart_money_bonus
```

Where:
- `regime_adjustment = regime * 0.1` (max +/- 10%)
- `smart_money_bonus = smart_money_score * 0.05` (max +5%)

Threshold: `p0_enter = 0.5` (configurable)

### Stage 4: Expected Value (EV)

```
EV = p * (RR * size) - (1-p) * cost
```

Where:
- `RR = tp_multiplier / sl_multiplier` (Risk/Reward ratio)
- `size = base_size_pct` (default 2%)
- `cost = 0.001` (trading fees)

Positive EV required for entry.

### Stage 5: Mode Selection

Based on regime value:

| Regime | Mode | Size Multiplier |
|--------|------|-----------------|
| > 0.7 | XL | 1.5x |
| > 0.3 | L | 1.2x |
| else | M | 1.0x |

## Data Classes

### Signal

```python
@dataclass
class Signal:
    decision: Decision          # ENTER | SKIP
    reason: Optional[str]       # Reject reason if SKIP
    mode: Optional[Mode]        # M | L | S | XL
    size_pct: Optional[float]   # Position size
    tp_pct: Optional[float]     # Take profit %
    sl_pct: Optional[float]     # Stop loss %
    ev_score: Optional[float]   # EV calculation
    regime: Optional[float]     # Market regime
```

### StrategyParams

All thresholds are configurable via `StrategyParams` dataclass - no magic numbers in code.

## Reject Reasons

All SKIP decisions use canonical reasons from `integration/reject_reasons.py`:

| Reason | Description |
|--------|-------------|
| `token_liquidity_low` | Token liquidity below threshold |
| `token_volume_low` | Token volume below threshold |
| `wallet_winrate_low` | Wallet winrate below threshold |
| `wallet_roi_low` | Wallet ROI below threshold |
| `wallet_trades_low` | Wallet trade count below threshold |
| `high_tax` | Buy/sell tax above threshold |
| `honeypot` | Token is honeypot |
| `regime_unfavorable` | Regime below threshold |
| `p_below_enter` | Probability below p0_enter |
| `ev_below_threshold` | EV not positive |

## Integration

```python
from strategy.logic import CopyScalpStrategy, WalletProfile, TokenSnapshot

strategy = CopyScalpStrategy(params=my_params)

signal = strategy.decide_on_wallet_buy(
    wallet=wallet_profile,
    token=token_snapshot,
    polymarket=polymarket_snapshot,  # Optional
    portfolio_value=10000.0
)

if signal.decision == Decision.ENTER:
    # Execute trade with signal.mode, signal.size_pct, etc.
```

## Files

- `strategy/logic.py` - Pure logic implementation
- `integration/decision_stage.py` - Pipeline glue stage
- `integration/fixtures/decision/scenarios.jsonl` - Test scenarios
- `scripts/decision_smoke.sh` - Smoke test

## Testing

```bash
bash scripts/decision_smoke.sh
```

Expected output:
```
[decision_smoke] OK
```
