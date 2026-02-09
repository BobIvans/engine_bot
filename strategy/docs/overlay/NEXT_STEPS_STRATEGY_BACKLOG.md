# Next steps backlog: Strategy implementation on top of verified rails

## Status snapshot

DONE in current repo iterations:
- Token snapshots + wallet profiles data layers are present (offline stores + fixtures)
- Feature contract is stable (`FEATURE_KEYS_V1`) and dataset export supports `y_*` labels
- Exporter coverage summary exists (PR-3) and is smoke-verified
- PR labels SoT + lint are part of `overlay_lint`
- Strategy config validator (`config_smoke.sh`) and negative validation suite (`config_negative_smoke.sh`) exist

NEXT (Variant A):
- **PR-4A.3: Mode registry + metrics-by-mode** (see `strategy/docs/overlay/PR_MODES.md`)

The remaining items below are historical / longer-horizon and may overlap with Variant A / Sprint-2.

This repo already has **verified rails**:

- Trade input contract: `integration/trade_schema.json` (+ validators)
- Deterministic smoke: fixtures → `paper_pipeline --summary-json` → compare to `expected_counts.json`
- Traceability: `run_trace_id`
- Queryable rejects: `forensics_events(kind='trade_reject')`

Below is the **exact** backlog to start implementing the Free‑First strategy without breaking rails.

## Epic A — Data contracts beyond trade_v1 (fixtures first)

A1. Token snapshot contract + store (local cache)
- Add `integration/token_snapshot_store.py` contract: `get_latest(mint) -> TokenSnapshot | None`
- Add fixture: `integration/fixtures/token_snapshots.sample.csv`
- Update `gates.py` to consume snapshot fields (liq/spread/vol) when enabled.

**DoD:** smoke remains green; a missing snapshot produces `trade_reject(stage='gates', reason='missing_snapshot')`.

A2. Wallet profile contract + store (tiering stub)
- Add `integration/wallet_profile_store.py` contract: `get(wallet) -> WalletProfile | None`
- Add fixture: `integration/fixtures/wallet_profiles.sample.csv` (good/bad/borderline wallets)
- Add wallet gates (min_trades_30d, min_roi_30d_pct, min_winrate_30d) guarded by config.

**DoD:** a known-bad wallet in fixture yields deterministic reject reason; smoke stays green.

## Epic B — Strategy decisions become executable (signal payload)

B1. Signal payload v1 (mode + parameters)
- Extend the signal payload_json to include:
  - `mode` (U/S/M/L + optional *_aggr)
  - `tp_pct`, `sl_pct`, `ttl_sec`
  - `max_slippage_bps`
  - `run_trace_id`

**DoD:** `signals_raw.payload_json` contains these keys and is queryable by trace.

B2. Risk engine v1 (no trading)
- Add `integration/risk_engine.py` with:
  - position sizing (fixed pct for now)
  - caps: max open positions, max exposure per token
  - kill-switch and cooldown stubs
- Add counter `risk_filtered_out` (do NOT mix with `rejected_by_gates`).

**DoD:** summary-json counts include `risk_filtered_out`; changes require updating expected_counts.

## Epic C — Execution simulator v1 (paper/sim, deterministic)

C1. Simulator core
- Add `execution/sim_fill.py` and `execution/latency_model.py`
- Implement TTL + slippage + partial/zero fill.

C2. Pipeline integration
- Add `--mode sim` to paper_pipeline (dry-run still available)
- Emit sim metrics to `--metrics-out`.

**DoD:** deterministic sim metrics on fixtures; no ClickHouse required.

## Epic D — Features / ML interfaces (model-off first)

D1. Feature builder contract
- Add `features/build_features.py` returning a dict
- Add fixture-based test/smoke that asserts feature keys are stable.

D2. Model interface
- Add `integration/model_inference.py`:
  - if model artifact exists → infer p_model
  - else → model_off mode with p_model = null

**DoD:** pipeline can run with model_off without code changes later.

