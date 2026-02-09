# Partial Fill Retry Logic (PR-Z.2)

## Overview
This feature implements an adaptive retry mechanism for partially filled orders during live execution. It ensures that large orders are filled completely by retrying the remaining amount with optimized parameters, while preventing budget overruns and excessive spam.

## Key Features
- **Adaptive Sizing**: Subsequent attempts reduce size by a decay factor (`0.7^n`) to find available liquidity.
- **Priority Fee Adjustment**: Fees increase exponentially (`1.5^n`) to incentivize validation.
- **Idempotency**: All attempts are linked via `client_id` chain (`original_id` -> `original_id_retry_1`).
- **Budget Protection**: Ensures `cumulative_filled + attempt_size <= original_size`.

## Configuration (`RuntimeConfig`)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `partial_retry_enabled` | `False` | Master switch for the feature. |
| `partial_retry_max_attempts` | `3` | Max retries per order chain. |
| `partial_retry_size_decay` | `0.7` | Size multiplier for each attempt (70%). |
| `partial_retry_fee_multiplier` | `1.5` | Fee multiplier for each attempt (150%). |
| `partial_retry_ttl_sec` | `120` | Max duration for the entire retry chain. |

## Architecture
1. **LiveExecutor**: Intercepts `on_partial_fill` events.
2. **PartialFillRetryManager**: 
   - Tracks chain state (cumulative filled).
   - Calculates next size and fee.
   - Validates budget and limits.
3. **Rejection**:
   - `REJECT_PARTIAL_RETRY_BUDGET_EXCEEDED`
   - `REJECT_PARTIAL_RETRY_MAX_ATTEMPTS`
   - `REJECT_PARTIAL_RETRY_TTL_EXPIRED`

## Handling in Simulation
- **ExecutionSimulator (sim_fill.py)**: Does NOT perform retries.
- **Metrics**: Adds `partial_fill_retry_attempts` (always 0 in sim) for schema compatibility.

## Safety Mechanisms
- **RLock**: Thread-safe state management.
- **Min Size**: Retries below min size (implicitly via decay or logic) are skipped.
- **Cleanup**: Full fill or cancellation clears chain state.

## Verification
Run the smoke test to verify logic:
```bash
bash scripts/partial_retry_smoke.sh
```
