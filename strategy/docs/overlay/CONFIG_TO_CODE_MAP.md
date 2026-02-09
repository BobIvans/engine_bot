# Config → Code map (куда “пристёгивать” стратегию)

Цель этого файла: убрать спор “где правда” и показать агенту **в какие файлы** вносить изменения.

> Источник истины параметров стратегии: `config/params_base.yaml` (или другой единый YAML).

## Мэппинг секций

| Секция конфига | Что означает | Где реализовать/менять |
|---|---|---|
| `trade_schema.*` | контракт входного JSONL trade_v1 | `integration/trade_schema.json`, `integration/validate_trade_jsonl_json.py` |
| `gates.*` | hard‑фильтры (token/wallet) | `integration/gates.py` |
| `reject_reasons.*` | enum причин reject’а | `integration/reject_reasons.py` |
| `run_trace.*` | генерация/прокидывание trace_id | `integration/run_trace.py`, `integration/paper_pipeline.py` |
| `signals.*` | формат сигнала/пороговые правила | `integration/paper_pipeline.py` (позже: `strategy/signal_engine.py`) |
| `risk.*` | sizing/лимиты/kill‑switch | (план) `strategy/risk_engine.py` + вызов из `integration/paper_pipeline.py` |
| `execution.*` | TTL/slippage/latency симуляция | (план) `execution/sim_fill.py` + вызов из pipeline |
| `features.*` | контракт/окна фич | (план) `features/trade_features.py` |
| `model.*` | inference/retrain параметры | (план) `models/inference.py`, `models/train.py` |

## Правило PR

Если PR меняет:
- нормализацию/gates/reject reasons → обновляем fixtures + `expected_counts.json` + smoke.
- запись в ClickHouse → обновляем `CLICKHOUSE_TRACE_VALIDATION.md` (или добавляем запросы).
