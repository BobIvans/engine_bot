# FREE_FIRST_STACK (dependency policy)

Принцип: **ничего не должно требовать оплаты раньше, чем через 7 дней**.

## Green (в ядро без оговорок)
- DuckDB + Parquet (локально)
- Python OSS (xgboost/lightgbm/lifelines/networkx/sklearn и т.д.)
- Grafana OSS локально
- Telegram Bot API

## Amber (в ядро, но только с кэшем/лимитами/фейловером)
- Helius Free (лимиты по credits/RPS) → primary realtime
- Alchemy Free (лимиты зависят от плана) → fallback RPC
- BigQuery Sandbox (ограничения sandbox) → аналитика/агрегации
- Upstash Redis Free → очередь/кэш
- Jupiter quote/route API → цены/маршруты (кэш 5–15с)
- Dexscreener/Birdeye free endpoints → sanity-check (не SPOF)

## Red (не строим ядро на этом в итерации 1)
- Платные “copy-trade платформы” как критическая зависимость
- Jito/priority-fee “гонка” в live на первой неделе (разрешено только моделировать)

## Общие правила
- Все внешние API: **кэш + rate limit + backoff**.
- Никаких SPOF: всегда 2 источника (primary + fallback) либо graceful-degradation.
