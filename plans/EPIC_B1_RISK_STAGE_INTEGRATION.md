# Epic B.1: Risk Stage Integration — Plan

## Overview
Добавить Risk Stage между Gates и Sim Preflight в пайплайн.

## Pipeline Sequence
```
INPUT (JSONL trade_v1)
  ↓
[1] trade_normalizer.py → Trade или reject
  ↓
[2] gates.py → GateDecision
  ↓
[3] 🆕 risk_stage.py ← INSERT HERE
  ↓
[4] sim_preflight.py → sim_metrics.v1
  ↓
[5] Write signals_raw + forensics_events
```

## Implementation Steps

### Step 1: Add RISK_* constants
**File:** `integration/reject_reasons.py`
```python
RISK_KILL_SWITCH = "risk_kill_switch"
RISK_MAX_POSITIONS = "risk_max_positions"
RISK_POSITION_SIZE = "risk_position_size"
```

### Step 2: Extend strategy/risk_engine.py
**File:** `strategy/risk_engine.py`
Add `apply_risk_limits()` function at the end:
- Pure function (no side effects)
- Kill-switch check → RISK_KILL_SWITCH
- Max positions check → RISK_MAX_POSITIONS
- Min position size (0.5% equity) → RISK_POSITION_SIZE
- Returns: (passed_signals, [(signal_id, reason)])

### Step 3: Create integration/risk_stage.py
**File:** `integration/risk_stage.py`
- Imports: `apply_risk_limits` from strategy.risk_engine
- Function: `risk_stage(signals, cfg, runner, ctx, portfolio, trace_id, dry_run)`
- Records rejects to forensics_events (if not dry_run)
- Returns: (passed_signals, reject_counts)

### Step 4: Integrate into paper_pipeline.py
**File:** `integration/paper_pipeline.py`
- Add `--skip-risk-engine` argument
- Insert risk_stage after gates, before sim_preflight
- Update global counts: `counts["rejected_by_risk"]`
- Initialize bucket counts to 0

### Step 5: Update expected_counts.json
**File:** `integration/fixtures/expected_counts.json`
```json
{
  "counts": {
    "rejected_by_risk": 0
  }
}
```

### Step 6: Create risk_engine_smoke.sh
**File:** `scripts/risk_engine_smoke.sh`
- Test kill-switch at 25% drawdown
- Test position sizing (fixed_pct)
- Test apply_risk_limits purity
- Test max positions limit

### Step 7: Update overlay_lint.sh
**File:** `scripts/overlay_lint.sh`
Add:
```bash
echo "[overlay_lint] Running risk_engine smoke..."
bash scripts/risk_engine_smoke.sh
```

## Critical Invariants
- ✅ `--summary-json` → stdout = exactly 1 line
- ✅ CANON untouched (git diff vendor/gmee_canon/ = empty)
- ✅ Pure functions only
- ✅ `assert_reason_known()` for all new reasons
- ✅ `open_positions = 0` in paper mode (static portfolio)
- ✅ No circular imports

## Future Extensions
Pattern for new stages:
1. Pure function in `strategy/<domain>.py`
2. Glue code in `integration/<stage>_stage.py`
3. Integrate in paper_pipeline.py (with --skip flag)
4. Update expected_counts.json
