# PR-G.4 — Jito Bundle Strategy Executor (Live Path Only)

**Status:** Implemented  
**Date:** 2024-01-15  
**Author:** Strategy Team

## Overview

Enables Jito bundle submission for critical buy transactions in **live mode only**.  
Jito bundles provide:
- Atomic execution of swap + tip
- MEV protection through tip-based prioritization
- Faster block inclusion

## Architecture

### Components

1. **`execution/jito_structs.py`** - Data classes
   - `JitoBundleRequest` - Bundle submission request
   - `JitoBundleResponse` - Bundle submission response
   - `JitoTipAccount` - Tip account info
   - `JitoConfig` - Configuration dataclass

2. **`execution/jito_bundle_executor.py`** - JitoClient abstraction
   - `JitoClient` - Async client for Jito API
   - `build_buy_bundle()` - Bundle construction helper
   - `calculate_tip_amount()` - Tip calculation utility

3. **`integration/reject_reasons.py`** - Jito reject reasons
   - `JITOBUNDLE_REJECTED` - Bundle rejected
   - `JITOBUNDLE_TIMEOUT` - Bundle submission timeout
   - `JITOBUNDLE_TIP_TOO_LOW` - Tip below minimum
   - `JITOBUNDLE_NETWORK_ERROR` - Network error

## Bundle Structure

```
┌─────────────────────────────────────────────┐
│              Jito Bundle                     │
├─────────────────────────────────────────────┤
│ 1. Swap Instruction (Jupiter/Raydium)        │
│    - Token buy swap                          │
│    - VersionedTransaction format             │
├─────────────────────────────────────────────┤
│ 2. Tip Instruction (SystemProgram.transfer)  │
│    - Transfer lamports to validator tip acct │
│    - Amount: floor * multiplier (clamped)    │
├─────────────────────────────────────────────┤
│    ↓                                         │
│  Jito Block Engine REST API                  │
│    POST /api/v1/bundles                      │
└─────────────────────────────────────────────┘
```

## Configuration

### Config Structure (params_base.yaml)

```yaml
jito:
  enabled: false                   # OFF by default
  endpoint: "https://mainnet.block-engine.jito.wtf"
  tip_multiplier: 1.2              # 20% above floor
  min_tip_lamports: 10000         # 0.00001 SOL
  max_tip_lamports: 500000        # 0.0005 SOL
  timeout_seconds: 30
```

## CLI Integration

### Paper Pipeline

```bash
# Live mode without Jito
python -m integration.paper_pipeline --mode live

# Live mode WITH Jito bundles (CRITICAL BUYS ONLY)
python -m integration.paper_pipeline --mode live --use-jito-bundle

# Paper/sim mode - Jito is IGNORED
python -m integration.paper_pipeline --mode paper
python -m integration.paper_pipeline --mode sim
```

## Usage Example

```python
from execution.jito_bundle_executor import JitoClient, build_buy_bundle
from execution.jito_structs import JitoConfig
from solders.pubkey import Pubkey

# Initialize Jito client
config = JitoConfig(
    enabled=True,
    tip_multiplier=1.2,
    min_tip_lamports=10000,
    max_tip_lamports=500000,
)

async with JitoClient(config=config) as client:
    # Get current tip floor
    tip_floor = await client.get_tip_lamports_floor()
    
    # Build bundle
    bundle = build_buy_bundle(
        swap_instruction=swap_ix,
        payer_wallet=wallet_pubkey,
        tip_account=tip_account,
        tip_amount_lamports=int(tip_floor * 1.2),
    )
    
    # Submit bundle
    response = await client.send_bundle(bundle)
    
    if not response.accepted:
        reject("jito_bundle_rejected", response.rejection_reason)
```

## Hard Rules

| Rule | Enforcement |
|------|-------------|
| Jito NEVER in paper/sim | Check `--mode` before Jito initialization |
| Single JSON line in --summary | Bundle ID appended, not separate line |
| All errors logged to stderr | `logger.error("[jito] ...")` |
| Reject reasons validated | `assert_reason_known(reason)` |

## Integration Points

### With Live Executor

```python
# In execution/live_executor.py
async def execute_buy(self, signal: SignalInput) -> Tuple[str, bool]:
    # Get swap instruction
    swap_ix = await self.build_swap_instruction(signal)
    
    # Check if Jito should be used
    if self.use_jito_bundles and not self.dry_run:
        async with JitoClient(self.jito_config) as client:
            # Get tip floor
            tip_floor = await client.get_tip_lamports_floor()
            
            # Build and submit bundle
            bundle = build_buy_bundle(
                swap_instruction=swap_ix,
                payer_wallet=self.wallet,
                tip_account=client.tip_accounts[0],
                tip_amount_lamports=tip_floor,
            )
            
            response = await client.send_bundle(bundle)
            
            if not response.accepted:
                self.reject("jito_bundle_rejected", response.rejection_reason)
                return "", False
            
            return response.bundle_id, True
    else:
        # Fallback to regular sendTransaction
        return await self.send_transaction(swap_ix)
```

## Testing

### Smoke Test

```bash
bash scripts/jito_bundle_smoke.sh
```

**Expected Output:**
```
[jito_bundle_smoke] Testing Jito reject reasons are known...
[jito_bundle_smoke] jito_bundle_rejected is known reason
[jito_bundle_smoke] jito_bundle_timeout is known reason
[jito_bundle_smoke] jito_bundle_tip_too_low is known reason
[jito_bundle_smoke] jito_bundle_network_error is known reason
[jito_bundle_smoke] Test 1 PASSED: All Jito reject reasons known
[jito_bundle_smoke] Testing Jito data structures...
[jito_bundle_smoke] Test 2 PASSED: Jito data structures work
[jito_bundle_smoke] Testing bundle construction...
[jito_bundle_smoke] Test 3 PASSED: Bundle construction works
[jito_bundle_smoke] Testing JitoClient mock mode...
[jito_bundle_smoke] Test 4 PASSED: JitoClient mock mode works
[jito_bundle_smoke] Testing bundle rejection handling...
[jito_bundle_smoke] Test 5 PASSED: Rejection handling works
[jito_bundle_smoke] Testing JitoConfig validation...
[jito_bundle_smoke] Test 6 PASSED: Config validation works
[jito_bundle_smoke] Results: 6 passed, 0 failed
[jito_bundle_smoke] OK
```

### Test Fixtures

| File | Purpose |
|------|---------|
| `integration/fixtures/jito/mock_jupiter_quote.json` | Mock Jupiter quote response |
| `integration/fixtures/jito/mock_bundle_response.json` | Mock Jito bundle submission response |
| `integration/fixtures/jito/mock_tip_account.txt` | Mock tip accounts list |

## Reject Reasons

All Jito reject reasons are validated:

```python
from integration.reject_reasons import (
    JITOBUNDLE_REJECTED,
    JITOBUNDLE_TIMEOUT,
    JITOBUNDLE_TIP_TOO_LOW,
    JITOBUNDLE_NETWORK_ERROR,
    assert_reason_known,
)

for reason in [JITOBUNDLE_REJECTED, JITOBUNDLE_TIMEOUT, JITOBUNDLE_TIP_TOO_LOW, JITOBUNDLE_NETWORK_ERROR]:
    assert_reason_known(reason)
```

## Future Enhancements

1. **Bundle status polling** - Track bundle confirmation status
2. **Multiple tip accounts** - Load balance across validators
3. **Priority fee estimation** - Dynamic adjustment based on network congestion
4. **Bundle fallback** - Retry with higher tip on rejection
