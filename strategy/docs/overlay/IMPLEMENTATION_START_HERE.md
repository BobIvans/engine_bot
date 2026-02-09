# IMPLEMENTATION_START_HERE (Iteration overlay)

Цель: **подключить стратегию как runtime-конфиг + минимальный paper/sim runner**, не трогая CANON.

## PR1 (docs + runtime конфиг)
1) Прочитай: `strategy/docs/overlay/SOLANA_COPY_SCALPING_SPEC_v0_2.md`.
2) Runtime YAML — **источник правды**: `strategy/config/params_base.yaml`.
3) Проверь, что allowlist и пример фич лежат тут:
   - `strategy/wallet_allowlist.yaml`
   - `strategy/wallet_features_example.json`
4) Прогон “rails”:
   - `bash scripts/overlay_lint.sh`
   - `bash scripts/iteration1.sh`

## PR2 (минимальный integration runner)
1) Loader конфига: `integration/config_loader.py` (читает YAML, отдаёт dict + config_hash).
2) Paper pipeline: `python3 -m integration.paper_pipeline`
   - пишет `forensics_events(kind="config_version")`
   - читает входные trade events (JSONL) → **минимально**: enrich/score stub → записывает events (или dry-run).

### Минимальный входной формат trade JSONL (для replay)
Одна строка = одно событие трейда.

**Обязательные поля:** `ts`, `wallet`, `mint`, `side`, `price`, `size_usd`.

**Опциональные:** `platform`, `tx_hash`, `pool_id`, `slot`, `size_token`, `source`.

Нормализатор (`integration/trade_normalizer.py`) принимает `BUY/SELL` и `buy/sell`,
и режектит: плохой JSON, отсутствие обязательных полей, `price<=0` или `size_usd<=0`.

3) Smoke:
   - `bash scripts/p1_smoke.sh`

## Где что лежит (важно)
- Docs-only overlay: `strategy/docs/overlay/**`
- Runtime (читает код): `strategy/config/**` + `strategy/*.yaml|json`
- CANON (read-only): `vendor/gmee_canon/**`

## miniML: dataset export (offline-first)

Этот репо поддерживает **детерминированный** экспорт датасета для обучения/аналитики.

Команда:

```bash
python3 tools/export_training_dataset.py \
  --trades-jsonl integration/fixtures/trades.sample.jsonl \
  --out-parquet /tmp/dataset.sample.parquet
```

Smoke (контракт ключей `f_*`):

```bash
bash scripts/features_smoke.sh
```

Примечание: утилита пишет Parquet через `duckdb` (рекомендовано). Если `duckdb` не
установлен в окружении, она автоматически падает назад на CSV.

## Release packaging (clean zip)

Чтобы в артефакты не попадали `__pycache__/` и `*.pyc`, собирайте zip **только из git-tracked файлов**:

```bash
bash scripts/build_zip_from_git.sh
```

## What to do next

* Sprint plan: `strategy/docs/overlay/SPRINT_PLAN.md`
* PR labeling rules: `strategy/docs/overlay/PR_LABELS.md`
* Current implementation map: `strategy/docs/overlay/STRATEGY_IMPL_MATRIX.md`
