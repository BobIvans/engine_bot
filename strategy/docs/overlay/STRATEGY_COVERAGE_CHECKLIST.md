# Strategy coverage checklist (docs vs repo)

Goal: keep one place that answers “what’s already captured **in this repo**” vs “what’s still only in the spec”.

Legend:
- ✅ Done in repo
- 🟡 Documented / planned (spec or overlay docs exist), not implemented yet
- ❌ Missing / not written down yet

## A) Guardrails / anti-drift (agent-friendly)

- ✅ CANON declared read-only (`vendor/gmee_canon/**`)
- ✅ overlay docs-only (`strategy/docs/overlay/**`)
- ✅ `policy/agent_policy.yaml` + `allowed_edit_globs`
- ✅ pre-commit guard (`scripts/pre_commit_agent_guard.sh`)
- ✅ CI jobs for policy + overlay lint + shellcheck + smoke

## B) Free-first Solana copy-scalping strategy (v0.2)

### Data Map (sources)
- 🟡 Kolscan wallet discovery (documented)
- 🟡 Dune wallet metrics export (documented)
- 🟡 RPC realtime ingestion (Helius/Alchemy) (documented)
- 🟡 Jupiter quotes / routing (documented)
- 🟡 Raydium/Orca/Meteora pool data (documented)
- 🟡 Dexscreener/Birdeye sanity checks (documented)
- 🟡 Storage: Parquet + DuckDB (documented)
- 🟡 Optional BigQuery sandbox (documented)

### Canonical data contracts
- 🟡 `trades_norm` fields (documented)
- 🟡 `token_snapshot` fields (documented)
- 🟡 `wallet_profile` fields (documented)
- 🟡 `signals` fields (documented)
- 🟡 `sim_fills / positions / pnl` fields (documented)

### Gates / universe
- 🟡 token liquidity/spread/volume gates (documented)
- 🟡 wallet tiering gates (documented)
- 🟡 kill-switch (documented)

### Execution simulation
- 🟡 TTL / limit / slippage / latency model (documented)
- 🟡 modes U/S/M/L + optional aggressive (documented)

### ML / +EV (optional track)
- 🟡 logreg/xgb + calibration + time-series split (documented)
- 🟡 p_model threshold + edge threshold (documented)

## C) What is implemented today (code)

- ✅ P0 engine runnable chain (ClickHouse / CANON) via `scripts/iteration1.sh`
- ✅ writers for P1 events:
  - `integration/write_signal.py` → `signals_raw`
  - `integration/write_wallet_score.py` → `forensics_events(kind='wallet_score')`
  - allowlist hash loader (`integration/allowlist_loader.py`)
- ❌ Solana data ingestion / normalizer / backtest pipeline (not implemented in this repo yet)
  - Next step is PR#1 stubs (see `IMPLEMENTATION_START_HERE.md`)

## D) Next missing chunks (high value, lowest risk)

1) Offline MVP backtest skeleton under `integration/solana_mvp/` (no external APIs).
2) Define minimal `trades_norm` CSV/Parquet schema example + loader.
3) Implement simple rule-based gates + simulator loop (paper-only).
4) Only then: plug realtime ingestion and ML.
