# PARALLEL_TRACKS_PLAN (Data-track vs Bot-track)

## Трек A — Data-track (топливо)
**Цель:** история + живой поток в едином формате.

- A1. `wallet_profiler` (ночной батч): история свопов → `wallet_profile.parquet` + `tier_map.json`
- A2. `history_builder` (батчи): сделки Tier-листа → `trades_norm.parquet`
- A3. `token_snapshot_cache` (каждые 5–30с): liquidity/price/depth → `token_snapshot.parquet`

**SPOF запрет:** отсутствие одного снапшота не должно ломать всё — только деградация фич.

## Трек B — Bot-track (PnL/метрики)
**Цель:** “listener → features → score → signal → sim-fill → pnl” (paper).

- B1. Listener: realtime события Tier-1 → очередь `trade_events`
- B2. Workers: enrich/cache → features → (model stub/real) → signal → sim fill/exit
- B3. Metrics: агрегаты → Grafana/CSV + Telegram alerts

### Offline replay bridge (P0.2)
Если Data-track уже построил `trades_norm.parquet`, то Bot-track можно запустить без realtime:

- Прямой replay в пайплайн:
  - `python3 -m integration.paper_pipeline --trades-parquet data/trades_norm.parquet --only-buy`

- Или конвертировать Parquet → JSONL (удобно для отладки):
  - `python3 -m integration.parquet_to_jsonl --input data/trades_norm.parquet --output /tmp/trades.jsonl`
  - потом: `python3 -m integration.paper_pipeline --trades-jsonl /tmp/trades.jsonl --only-buy`

## Правило связки
- Формат `Trade` общий (см. `DATA_CONTRACT_MAP.md`).
- Data-track может лагать/падать — bot-track не должен умирать, только снижать качество решения.
