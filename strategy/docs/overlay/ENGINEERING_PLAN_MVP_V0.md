# Engineering plan: MVP v0 (0$) — repo structure + module map

> **Docs-only.** This file is an implementation-oriented plan for building the Solana copy‑scalping MVP.
> It must **not** be treated as CANON code or SQL.
>
> **CANON ONLY** = `vendor/gmee_canon/**` (read-only)  
> **CODE** may live only in: `integration/**`, `scripts/**`, `.github/workflows/**`, `policy/**`  
> **STRATEGY DOCS** live in: `strategy/docs/**`

## Goal

Build a minimal end-to-end (paper/sim) path:

**wallet event → Trade → Signal → simulated entry/exit → PnL/metrics**

While keeping the project **free-first** (no required paid subscriptions).

## Proposed “team-ready” module layout (conceptual)

This is a **conceptual** layout to keep responsibilities clean. In this repo, implement code under
`integration/` and orchestration under `scripts/`.

- `core/` — dataclasses + shared contracts (`Trade`, `WalletProfile`, `TokenState`, `Signal`, `Position`)
- `ingestion/` — Dune/Kolscan loaders (history), RPC listener (realtime), token state fetchers (Jupiter/DEX)
- `features/` — wallet/token/trade features
- `models/` — training + prediction (optional for MVP v0)
- `strategy/` — mode selection (U/S/M/L), risk engine, exits, honeypot filter
- `execution/` — simulator (TTL/limit/slippage/latency), queues (in-memory/Redis), live executor stub
- `monitoring/` — metrics, exporters, alerts
- `pipelines/` — offline backtest, realtime paper loop, daily report

## Canonical data contracts (reminder)

Keep these contracts aligned with the Strategy Spec (`SOLANA_COPY_SCALPING_SPEC_v0_2.md`):
- `trades_norm`
- `token_snapshot`
- `wallet_profile`
- `signals`
- `sim_fills` / `positions_pnl`

## Mapping of responsibilities → modules

### Ingestion
- Dune/Kolscan seed + metrics → wallet tier lists
- Realtime listener (Helius/Alchemy free tier) → normalized `Trade`

### Enrichment
- Wallet profile lookup/update
- Token/pool snapshots (Jupiter + DEX SDK; optional sanity-check via Dexscreener/Birdeye with caching)

### Features + (optional) ML
- FeatureBuilder v1 (wallet + token + trade)
- MVP v0 can be **rule-based**; ML (LogReg/XGB) is an upgrade once sim loop is stable

### Strategy
- Mode selection U/S/M/L (+ optional *_aggr)
- Risk limits + **kill-switch**
- Exits: TP/SL/TIME + partial take + trailing (as configured)

### Execution simulator
- Limit + TTL + slippage + latency model
- Partial fills
- Exit simulation and PnL attribution

### Metrics
- ROI, winrate, max drawdown
- fill_rate, slippage, latency breakdown
- breakdown by mode / wallet / token / DEX

## MVP v0 (0$) — 7-day “doable” plan

1. **Day 1–2:** contracts + wallet discovery + tier list
2. **Day 3:** mode selector + basic exits + very simple fill model
3. **Day 4–5:** offline backtest that runs 10k+ trades and outputs PnL/ROI/DD/fill_rate
4. **Day 6:** risk limits + kill-switch + max open positions constraint
5. **Day 7:** realtime paper loop + daily report (CSV/Parquet)

## Acceptance criteria for “v0 ready”

- `backtest_offline` processes **≥10k** historical trades and reports: PnL/ROI/maxDD/fill_rate
- `paper_realtime` listens to **20–50** wallets and produces **≥100** simulated trades/day with an export report

## Implementation note (important)

**MVP offline backtest code (DuckDB/Parquet pipeline) lives outside CANON, only in allowed code dirs**:
`integration/**`, `scripts/**`, `.github/workflows/**`, `policy/**`.
