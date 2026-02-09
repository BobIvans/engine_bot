# Strategy Manifest (Repo Artifact)

This file exists so the strategy is not "chat memory".
It should stay short and stable.

## Goal
- What are we optimizing? (e.g. risk-adjusted PnL, latency, fill quality)

## Constraints
- Trading venue / chain constraints
- Risk limits
- Data collection constraints (ToS/compliance)

## Entities
- entity_type: wallet | token_mint | pool_id | route_id | rpc_arm | provider_id | market_symbol
- entity_id: ...

## Ground Truth Metrics
- What is considered "truth" (fills, confirmations, reorg handling)

## Done means
- What constitutes a closed loop (data → metrics → rule-pack → reproducible outcome)
