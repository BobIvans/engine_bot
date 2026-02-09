# Iteration-2 Tasks: Strategy implementation on top of verified rails

**Goal:** make the repo ready to hand off to coding agents so they can implement the Free‑First Solana copy‑scalping
strategy *layer-by-layer* while keeping the rails verifiable and deterministic.

## Absolute invariants (do not break)
- CANON is read-only: `vendor/gmee_canon/**`
- No new SQL files outside CANON.
- CI == local: `./scripts/smoke.sh` is the single smoke entry.
- Any behavior change must be visible via:
  - deterministic fixtures + `expected_counts.json`
  - and/or queryable `forensics_events` by `run_trace_id`.

## Definition of Done for Iteration-2 (repo is “agent-ready”)
You are done when:
1) `./scripts/smoke.sh` is green
2) `python3 -m integration.paper_pipeline --dry-run --summary-json --trades-jsonl integration/fixtures/trades.sample.jsonl --token-snapshots integration/fixtures/token_snapshots.sample.csv --metrics-out /tmp/metrics.json` is green
3) You have **GitHub issue templates** and a single backlog entrypoint (`BACKLOG.md`) so an agent can start without questions.
4) The following contracts exist (even as stubs) + fixtures:
   - Token snapshots store + fixture
   - Wallet profiles store + fixture
   - Feature builder contract + feature smoke
   - Risk engine contract (pure functions)
   - Execution simulator contract (TTL/slippage/latency)

## Epic A — Data-track contracts beyond trade_v1 (fixtures first)
- [ ] A1. Token snapshot contract + store (local cache) — see `strategy/docs/overlay/NEXT_STEPS_STRATEGY_BACKLOG.md`
- [ ] A2. Wallet profile contract + store (tiering stub)
- [ ] A3. Import tools to convert CSV/JSON exports into parquet fixtures for replay

## Epic B — Risk + execution simulator (paper/sim first)
- [ ] B1. Risk engine (fractional Kelly + limits + kill-switch) as pure functions
- [ ] B2. Execution simulator: TTL + slippage + latency (+ partial/zero fill)
- [ ] B3. Counters/metrics per stage (rejects vs filtered vs risk_filtered vs fills)

## Epic C — Features + ML interfaces (model-off first)
- [ ] C1. Feature builder contract + expected keys fixture
- [ ] C2. Model interface (model-off / deterministic inference path)
- [ ] C3. Backtest harness wiring (replay trades_norm.parquet → sim outcomes → metrics)

## How to work (recommended PR order)
1) Epic A (contracts + fixtures)
2) Epic B (risk + sim)
3) Epic C (features + ML)

**No live trading keys** are needed in Iteration‑2.
