> **Overlay-only**: This document is guidance. **CANON is `vendor/gmee_canon/**` (read-only)**.  
> Do not copy overlay code/queries/DDL into CANON. Implement changes only in `integration/**` and `strategy/**`.

# GMEE integration notes (P0/P1-safe)

Этот Strategy Pack специально держится **независимым** от канонического GMEE P0 (ClickHouse DDL/queries).

## Канонические файлы GMEE в этом zip

- **Конфиг:** `config/golden_mean_exit_engine.yaml` (v0.1)
- **Спецификация:** `docs/strategy_v0.1.md`
- **Полный all-in-one reference:** `docs/strategy_all_in_one_v11_1.md`

Если вы используете общий конфиг‑лоадер, самый простой путь — грузить `config/params_base.yaml` как базу и отдельно подмешивать `config/golden_mean_exit_engine.yaml` (merge по ключам; GMEE берёт только свой под‑ключ).

## Что уже готово в GMEE (по вашим версиям v22/v23)
- Канон ClickHouse (`schemas/clickhouse.sql`) + merge-gates.
- Writer Tier‑0 с DB-level ordering asserts (EPIC 4.1 guard).
- Investigate/Doctor bundle + (v22) premium capture: RAW → Universal Variables → labels.
- (v23) glue: `capture manifest → trace bundle` + soft-fail attach ссылок в `forensics_events`.

## Как маппить Strategy Pack → GMEE (минимально)
Strategy Pack оперирует сущностями:
- `trades_norm` (сделки/события)
- `signals`, `sim_fills`, `positions_pnl`

GMEE P0 оперирует:
- `signals_raw` (что увидели/решили)
- `trade_attempts` (попытки исполнения)
- `trades` (ground truth исполнения + план выхода + метрики)

**Минимальный мост:**
1) Когда в Strategy Pack формируется `Signal(decision=ENTER|SKIP)`:
   - ENTER/SKIP писать в GMEE как `signals_raw` + `forensics_events` (reject_reason, edge, режим, параметры TTL/SL/TP).
2) Симулятор/пейпер генерирует `sim_fills/positions`:
   - писать как `trade_attempts` + `trades` (или как отдельный offline артефакт и затем приклеивать через v23 capture glue).
3) Источники данных (RPC, экспорты, премиум‑trial):
   - складывать как артефакты через v22 pipeline: RAW → UV → labels + manifest.
   - для каждой сделки/трейса можно приклеить `snapshot_id/raw_sha256` в `forensics_events(kind='external_capture_ref')` (v23 soft‑fail attach).

## Практичный путь “сначала доказать edge”
- Держим Strategy Pack как **отдельный слой** (duckdb/parquet + офлайн сим).
- GMEE используем как:
  - канонический движок планирования/форензики/репортинга;
  - “evidence bundle” и воспроизводимость;
  - контроль drift/детерминизм/merge-gates.

Когда вы готовы подключать real execution:
- переносим `ExecutionSimulator` → “live execution adapter”
- из GMEE берём канонические проверки, форензику, и план выхода.
