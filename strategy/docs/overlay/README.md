> **Overlay-only**: This document is guidance. **CANON is `vendor/gmee_canon/**` (read-only)**.  
> Do not copy overlay code/queries/DDL into CANON. Implement changes only in `integration/**` and `strategy/**`.

# GMEE Strategy Pack v17 (canonical from v5)


**Что это:** v17, приведённый к канонической структуре Strategy Pack (основан на v5), с сохранением полезных материалов.

**Что изменилось относительно “hard_synced_merged v17”:**
- Каноническая структура и runnable `MVP_OFFLINE/` берутся из v5.
- Материалы из исходного v17 сохранены в `LEGACY_V17_SOURCE/` (для справки), а наиболее полезные выжимки — в `EXTRAS/`.
- Удалены `__pycache__`/`*.pyc`.

Этот архив содержит **каноническую стратегию** и **офлайн‑MVP каркас** (paper/backtest) для Solana copy‑scalping (memecoins), заточенный под:
- free‑first стек (free tier ≥ 7 дней / OSS)
- масштабирование на тысячи кошельков через tiering/батчи/кэш
- режимы U/S/M/L + Aggressive Layer (“режим ракеты”)
- Polymarket overlay (risk regime) как опциональный слой

## Что нового в v11.1 (patch)
- Расширён и уточнён **Polymarket overlay**: роли (regime/narrative/sanity‑check), фичи, логирование и правила влияния на δ/size/modes.
- Расширён **Wallet Discovery**: Kolscan + Dune + Flipside как primary лидерборды; SolanaFM/Covalent/Moralis/Birdeye как optional enrichment.
- Зафиксировано правило: **BullX/GMGN/Axiom = UI**, не источник данных; в ядре только on‑chain + replaceable adapters.
- Обновлены `RESOURCES_AND_APPS.*` и `config/datasources_example.yaml` (+ пример `config/polymarket_markets_example.yaml`).

## Основные документы
- `SOLANA_COPY_SCALPING_SPEC_v0_2.md` — главный стратегический документ (дизайн, режимы, фильтры, infra)
- `SOLANA_COPY_SCALPING_STRATEGY_KERNEL_v1.md` — компактный “канон ядра”
- `UNIFIED_DECISION_FORMULA_ONE_FORMULA.md` — единая формула принятия решения (ENTER/SKIP → mode → size → exec)
- `FREE_FIRST_MONEY_FILTER_AND_PARALLEL_TRACKS.md` — money‑filter + параллельные треки сборки
- `STRATEGY_TO_UV_MAPPING.md` — маппинг полей стратегии к UV (унифицированным переменным)
- `AGGRESSIVE_LAYER_ROCKET_MODE.md` — агрессивный слой (post‑entry)

## Offline MVP
Папка `MVP_OFFLINE/` — офлайн‑каркас пайплайна (ingest → signals → sim → metrics), пригодный для:
- “бумажных” прогонов на CSV/Parquet,
- быстрой проверки контрактов данных,
- бэктеста на stub/исторических данных после подмены источников.

См. `MVP_OFFLINE/README.md`.

Generated: 2025-12-28T19:18:48Z

## Добавлено для GMEE (Golden Mean Exit Engine)
- `config/golden_mean_exit_engine.yaml` — параметры GMEE (phi=0.618, режимы U/S/M/L, агрессия, overrides, telemetry)
- `docs/strategy_v0.1.md` — компактная спецификация данных/алгоритма GMEE (repo-ready)
- `docs/strategy_all_in_one_v11_1.md` — полный “all-in-one” документ со всеми параметрами/этапами/гейтами (для Codex/LLM)

## GMEE minimal schema (Codex-friendly)

Added MVP data/event schema and storage artifacts:
- `docs/gm_min_data_and_event_schema.md`
- `docs/gm_storage_keys_and_indexes.md`
- `docs/gm_read_queries_min.md`
- `docs/wallet_hold_stats_update_rules.md`
- `docs/gm_clickhouse_mvs_min.sql`
- `schemas/clickhouse/*.sql`
- `schemas/postgres/01_tables.sql`
- `docs/mapping_pack_v11_terms_to_min_schema.md`
## Golden Mean Exit Engine — repo skeleton (new)
LEGACY_PATH: Previously referenced `golden-engine-exit/`.

Use CANON at `vendor/gmee_canon/` instead (read-only):
- configs (golden_exit_engine.yaml, queries.yaml)
- schemas (ClickHouse + Postgres)
- SQL queries (profile/routing/microticks/glue)
- docs (SPEC/DATA_MODEL/RUNBOOK + idempotency/reorg/circuit-breaker + governance)
- ops runbooks + smoke/data-quality stubs

This is **scaffold only** (no trading code), intended for Codex/team to implement consistently.
