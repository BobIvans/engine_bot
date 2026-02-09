# PR-Z.5 — Multi-Wallet Coordination Detector

## Goal

Implement offline stage for detecting coordinated trading patterns (partner wallets, wash trading, pump schemes) through temporal pattern analysis and co-transaction graph construction.

Outputs `coordination_score` [0.0, 1.0] for each trade based on:
- (a) Temporal proximity of entries (<15s)
- (b) Graph structure (high-connectivity clusters)
- (c) Anomalous volume profile

## Scope

| File | Purpose |
|------|---------|
| [`strategy/coordinated_actions.py`](strategy/coordinated_actions.py) | Pure function [`detect_coordination()`](strategy/coordinated_actions.py:89) |
| [`integration/coordination_stage.py`](integration/coordination_stage.py) | Pipeline stage with sliding window |
| [`integration/fixtures/coordination/`](integration/fixtures/coordination/) | Test fixtures |
| [`scripts/coordination_smoke.sh`](scripts/coordination_smoke.sh) | Smoke test |
| [`strategy/docs/overlay/PR_COORDINATION_DETECTOR.md`](strategy/docs/overlay/PR_COORDINATION_DETECTOR.md) | This documentation |

## Algorithm (Fixed, No ML)

### Component Scores

| Score | Weight | Description |
|-------|--------|-------------|
| `temporal_proximity_score` | 0.4 | Fraction of wallet pairs with Δt < 15s in same token |
| `graph_density_score` | 0.4 | Edges / max_possible_edges for wallets in window |
| `volume_anomaly_score` | 0.2 | Z-score of token volume relative to historical mean |

### Final Score

```
coordination_score = 0.4*temporal + 0.4*graph + 0.2*volume
coordination_score = clamp(coordination_score, 0.0, 1.0)
```

## API

### Pure Logic: `detect_coordination()`

```python
def detect_coordination(
    trades_window: List[CoordinationTrade],
    window_sec: float = 60.0
) -> Dict[str, float]:
    """
    Detect coordinated trading patterns in a sliding window.

    Args:
        trades_window: List of trades (ts_block, wallet, mint, side, size, price).
        window_sec: Sliding window size in seconds (default 60s).

    Returns:
        Dictionary mapping wallet to coordination_score [0.0, 1.0].
    """
```

### CoordinationTrade Format

```python
class CoordinationTrade(TypedDict):
    ts_block: float       # Block timestamp
    wallet: str           # Wallet address
    mint: str            # Token mint
    side: Literal["BUY", "SELL"]
    size: float          # Trade size
    price: float         # Trade price
```

### Pipeline Stage

```python
@dataclass
class CoordinationStage:
    window_sec: float = 60.0
    enabled: bool = False
    coordination_threshold: float = 0.7
    
    def add_trade(self, trade: CoordinationTrade) -> Optional[CoordinationResult]:
        ...
    
    def compute_metrics(self) -> Dict[str, Any]:
        """
        Returns:
        {
            "coordination_score_avg": float,
            "coordination_score_max": float,
            "coordination_high_count": int,
        }
        """
```

## Configuration

```python
# In RuntimeConfig
coordination_threshold: float = 0.7  # ge=0.5, le=0.95
```

## CLI Integration

```bash
python -m integration.paper_pipeline \
    --enable-coordination-detection \
    --input trades.jsonl \
    --output signals.jsonl
```

## Smoke Test

```bash
bash scripts/coordination_smoke.sh
```

Expected output:
```
[coordination_smoke] Clustered test: PASSED (high coordination detected)
[coordination_smoke] Random test: PASSED (low coordination detected)
[coordination_smoke] Stage test: PASSED
[coordination_smoke] Disabled mode: PASSED
[coordination_smoke] Determinism: PASSED
[coordination_smoke] All PR-Z.5 smoke tests passed!
[coordination_smoke] OK
```

## GREP Points

```bash
grep -n "def detect_coordination" strategy/coordinated_actions.py
grep -n "coordination_score_avg" integration/coordination_stage.py
grep -n "REJECT_COORDINATION_INVALID_INPUT" integration/reject_reasons.py
grep -n "PR-Z.5" strategy/docs/overlay/PR_COORDINATION_DETECTOR.md
grep -n "\[coordination_smoke\] OK" scripts/coordination_smoke.sh
```

## Safety Properties

1. **Offline-only**: Works only on historical data (no real-time dependencies)
2. **Deterministic**: Same input → same output (no randomness)
3. **Optional**: Disabled by default, enabled via `--enable-coordination-detection`
4. **Validation**: Missing required fields → error with reject reason
5. **No vendor changes**: All code in strategy/ and integration/
