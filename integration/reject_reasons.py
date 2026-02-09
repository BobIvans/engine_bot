"""integration/reject_reasons.py

Canonical reject reasons for Iteration-1 pipeline.

Keep as simple string constants so we can:
- aggregate stats (why did we NOT emit a signal?)
- avoid ad-hoc reason strings drifting across modules
"""

# Input / enrichment
MISSING_SNAPSHOT = "missing_snapshot"
INVALID_TRADE = "invalid_trade"

# Token gates
MIN_LIQUIDITY_FAIL = "min_liquidity_fail"
MIN_VOLUME_24H_FAIL = "min_volume_24h_fail"
MAX_SPREAD_FAIL = "max_spread_fail"
TOP10_HOLDERS_FAIL = "top10_holders_fail"
SINGLE_HOLDER_FAIL = "single_holder_fail"

# Honeypot / rug (P0.1: boolean only)
HONEYPOT_FAIL = "honeypot_fail"

# Honeypot specific rejections (PR-B.3)
HONEYPOT_FLAG = "honeypot_flag"
HONEYPOT_FREEZE = "honeypot_freeze"
HONEYPOT_MINT_AUTH = "honeypot_mint_auth"

# Honeypot Safety Gate (PR-K.3)
HONEYPOT_DETECTED = "honeypot_detected"

# Simulation security checks (PR-K.1)
SIMULATION_FAIL = "simulation_fail"
HIGH_TAX_FAIL = "high_tax_fail"

# Security checks (from snapshot.extra["security"])
FREEZE_AUTHORITY_FAIL = "freeze_authority_fail"
MINT_AUTHORITY_FAIL = "mint_authority_fail"
SECURITY_TOP_HOLDERS_FAIL = "security_top_holders_fail"

# Wallet hard filters
WALLET_MIN_WINRATE_FAIL = "wallet_min_winrate_fail"
WALLET_MIN_ROI_FAIL = "wallet_min_roi_fail"
WALLET_MIN_TRADES_FAIL = "wallet_min_trades_fail"

# Promotion/Pruning (PR-H.3)
WALLET_WINRATE_7D_LOW = "wallet_winrate_7d_low"
WALLET_TRADES_7D_LOW = "wallet_trades_7d_low"
WALLET_ROI_7D_LOW = "wallet_roi_7d_low"

# Jito Bundle Execution (PR-G.4)
JITOBUNDLE_REJECTED = "jito_bundle_rejected"
JITOBUNDLE_TIMEOUT = "jito_bundle_timeout"
REJECT_BITQUERY_SCHEMA_MISMATCH = "REJECT_BITQUERY_SCHEMA_MISMATCH"
REJECT_INVALID_PRICE = "REJECT_INVALID_PRICE"
JITOBUNDLE_TIP_TOO_LOW = "jito_bundle_tip_too_low"
JITOBUNDLE_NETWORK_ERROR = "jito_bundle_network_error"

# State Reconciler (PR-X.1)
BALANCE_DISCREPANCY_DETECTED = "balance_discrepancy_detected"

# Order Manager (PR-E.5)
TTL_EXPIRED = "ttl_expired"
TP_HIT = "tp_hit"
SL_HIT = "sl_hit"
MANUAL_CLOSE = "manual_close"

# Risk (stubbed in P0.1)
RISK_LIMIT_FAIL = "risk_limit_fail"
RISK_KILL_SWITCH = "risk_kill_switch"
RISK_MAX_POSITIONS = "risk_max_positions"
RISK_POSITION_SIZE = "risk_position_size"
RISK_COOLDOWN = "risk_cooldown"
RISK_WALLET_TIER_LIMIT = "risk_wallet_tier_limit"
RISK_MODE_LIMIT = "risk_mode_limit"
RISK_MAX_EXPOSURE = "risk_max_exposure"

# Strategy
STRATEGY_LOW_EDGE = "strategy_low_edge"

# Unified Decision Logic (PR-S.2)
WALLET_ROI_LOW = "wallet_roi_low"
EV_BELOW_THRESHOLD = "ev_below_threshold"
REGIME_UNFAVORABLE = "regime_unfavorable"
TOKEN_LIQUIDITY_LOW = "token_liquidity_low"
TOKEN_VOLUME_LOW = "token_volume_low"
P_BELOW_ENTER = "p_below_enter"

# Order Manager (PR-E.5)
TTL_EXPIRED = "ttl_expired"
TP_HIT = "tp_hit"
SL_HIT = "sl_hit"

# Aggressive Switch Logic (PR-S.3)
AGGR_WALLET_ROI_LOW = "aggr_wallet_roi_low"
AGGR_WALLET_WINRATE_LOW = "aggr_wallet_winrate_low"
AGGR_LIQUIDITY_LOW = "aggr_liquidity_low"
AGGR_SPREAD_HIGH = "aggr_spread_high"
AGGR_EXPOSURE_LIMIT = "aggr_exposure_limit"
AGGR_DAILY_TRADE_LIMIT = "aggr_daily_trade_limit"
AGGR_TIME_EXPIRED = "aggr_time_expired"
AGGR_INSUFFICIENT_IMPULSE = "aggr_insufficient_impulse"
AGGR_NO_TRIGGER = "aggr_no_trigger"
AGGR_UNKNOWN_MODE = "aggr_unknown_mode"

# Idempotency / Reorg (PR-G.2)
DUPLICATE_EXECUTION = "duplicate_execution"
TX_DROPPED = "tx_dropped"
TX_REORGED = "tx_reorged"

# Partial Fill & Reorg Handling (PR-G.5)
PARTIAL_FILL_UNRESOLVED = "partial_fill_unresolved"
PARTIAL_FILL_TIMEOUT = "partial_fill_timeout"
REORG_DETECTED = "reorg_detected"
REORG_POSITION_ROLLBACK = "reorg_position_rollback"

# Polymarket (PR-F.5)
POLYMARKET_DATA_STALE = "polymarket_data_stale"
POLYMARKET_DATA_MISSING = "polymarket_data_missing"

# Flipside Backfill (PR-Y.3)
FLIPSIDE_SCHEMA_MISMATCH = "flipside_schema_mismatch"
FLIPSIDE_MISSING_REQUIRED_FIELD = "flipside_missing_required_field"
FLIPSIDE_INVALID_PROGRAM_ID = "flipside_invalid_program_id"

# PR-Y.5: Config Hot-Reload
REJECT_CONFIG_INVALID_ON_RELOAD = "reject_config_invalid_on_reload"

# PR-Z.2: Partial Fill Retry
REJECT_PARTIAL_RETRY_BUDGET_EXCEEDED = "reject_partial_retry_budget_exceeded"
REJECT_PARTIAL_RETRY_MAX_ATTEMPTS = "reject_partial_retry_max_attempts"
REJECT_PARTIAL_RETRY_TTL_EXPIRED = "reject_partial_retry_ttl_expired"
REJECT_PARTIAL_RETRY_TOO_SMALL = "reject_partial_retry_too_small"

# PR-Z.3: Dynamic Trailing Adjustment
REJECT_TRAILING_ADJUST_INVALID = "reject_trailing_adjust_invalid"

# PR-Z.5: Multi-Wallet Coordination Detection
REJECT_COORDINATION_INVALID_INPUT = "coordination_invalid_input"
REJECT_COORDINATION_TOO_HIGH = "coordination_too_high"

# PR-Z.4: Exit Hazard Prediction Model
REJECT_HAZARD_FEATURES_INVALID = "hazard_features_invalid"

# -----------------------------
# Guardrail: enum-only reasons
# -----------------------------

# Collect all uppercase string constants defined in this module.
_KNOWN_REASONS = {
    v for k, v in globals().items() if k.isupper() and isinstance(v, str)
}


def assert_reason_known(reason: str) -> None:
    """Raise if the provided reason isn't in the canonical set.

    This is intentionally strict so any new reason requires:
    - updating this file
    - updating fixtures/expected_counts where applicable
    """

    if reason not in _KNOWN_REASONS:
        raise ValueError(f"Unknown reject_reason: {reason!r}. Add it to integration/reject_reasons.py")
