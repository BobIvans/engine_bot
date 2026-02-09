# P0_FINAL_TASKS — GMEE v0.4 (Variant A)

Цель: закрыть P0 так, чтобы Codex мог писать бизнес-код без догадок.
Запрещено: P1/P2 (тюнинг, bandit, epsilon-controller jobs, новые фичи/источники, расширенный тик-архив).

## EPIC 0 — P0 Repro Baseline (чтобы CI не “плавал”)
0.1. Зафиксировать версию ClickHouse в CI (docker image/tag).
Acceptance:
- CI всегда использует один и тот же ClickHouse image/tag.
- Любые апдейты версии делаются осознанно отдельным PR.

0.2. Один источник truth для Oracle expected TSV.
Acceptance:
- expected TSV хранится в одном месте (oracle gate), и не “чинится руками” в других местах.

0.3. Oracle expected как файл-артефакт (единственный источник truth) + генератор.
Как зафиксировать:
- expected хранить в main-repo в CI-папке, например: `ci/oracle_expected.tsv`
- генерация делается отдельным скриптом (seed + YAML params + glue_select → TSV), например:
  `ci/generate_oracle_expected.py`
Acceptance:
- `ci/oracle_expected.tsv` — единственный источник truth для expected (CI сравнивает результат только с файлом).
- Нельзя “чинить expected” вручную: изменения expected допускаются только через генератор.
- Любой PR, меняющий expected, обязан менять *либо seed*, либо *YAML* (в diff это видно).
- Нюанс P0: seed/YAML — канон и в P0 не меняются, значит expected фиксируется один раз и дальше не трогается.

## EPIC 1 — Anti-drift “Single Source of Truth”
1. Подключить в main-repo канонические файлы (без правок):
   - docs/SPEC.md, docs/DATA_MODEL.md, docs/CONTRACT_MATRIX.md, docs/RUNBOOK.md
   - configs/golden_exit_engine.yaml, configs/queries.yaml
   - schemas/clickhouse.sql, schemas/postgres.sql
   - queries/01..04.sql
   - scripts/assert_no_drift.py, scripts/canary_*.sql, scripts/seed_golden_dataset.sql
   - CI gate (интегрировать шаги из .github/workflows/ch_compile_smoke.yml)
Acceptance:
- CI поднимает чистую ClickHouse и применяет DDL без ручных правок.
- EXPLAIN SYNTAX для queries/01..04 проходит.
- scripts/assert_no_drift.py проходит.

2. Variant A enforcement:
   - В 04_glue_select.sql нет захардкоженных значений порогов/epsilon/aggr/clamp из YAML.
Acceptance:
- assert_no_drift.py падает, если в SQL появились числа из YAML.
- params в configs/queries.yaml == placeholders в SQL (1:1).

1.3. Вторая линия обороны: yaml-derived literal ban guard для `queries/04_glue_select.sql`.
Требование:
- Не делать “общий ban на числа” (иначе флейки из-за 0/1/1970/30 и т.п.).
- Guard должен ловить **ровно значения из YAML**, относящиеся к thresholds/epsilon/aggr/clamp/microticks_window.
Реализация (любой вариант P0-ок):
- Вариант A (предпочтительнее): маленький скрипт, который читает `configs/golden_exit_engine.yaml`,
  вытаскивает числа (thresholds/epsilon/aggr/clamp/window) и проверяет, что они **не встречаются**
  в `queries/04_glue_select.sql` как литералы.
- Вариант B: статический список “запрещённых чисел” в guard (хуже, требует ручного обновления).
Acceptance:
- CI падает, если любое значение из YAML (thresholds/epsilon/aggr/clamp/window) встречается
  в `queries/04_glue_select.sql` как литерал.
- Guard не флейкает на служебных числах, не связанных с YAML (0/1/1970/30d и т.п.).

## EPIC 2 — Storage & Deterministic Views
3. ClickHouse schema P0-core:
   - signals_raw, trade_attempts, rpc_events, trades, microticks_1s,
     wallet_daily_agg_state, latency_arm_state, controller_state,
     provider_usage_daily, forensics_events
   - TTL/retention минимум: signals_raw, rpc_events, microticks_1s
Acceptance:
- DDL применим на пустой БД.
- TTL совпадает с YAML (проверяется assert_no_drift.py).

4. MV/VIEW минимум (ровно 2):
   - mv_wallet_daily_agg_state (quality filter)
   - wallet_profile_30d (deterministic, anchored on max(day))
Acceptance:
- wallet_profile_30d не использует now()/today() как якорь
- (ВАЖНО) детерминизм view проверяется CI guard/test (например schema_guard/runtime check),
  а не “только словами”.

## EPIC 3 — Canary + Oracle gates
5. Canary E2E:
   - scripts/canary_golden_trace.sql + scripts/canary_checks.sql
Acceptance:
- canary seed вставляется
- canary_checks.sql не падает (throwIf не триггерится)

6. Oracle test для exit-planner:
   - scripts/seed_golden_dataset.sql
   - запуск 04_glue_select.sql с параметрами из YAML
   - сравнение результата с ожидаемой TSV строкой
Acceptance:
- ожидаемый TSV стабилен и совпадает 1:1 в CI (expected берётся из oracle gate / `ci/oracle_expected.tsv`)

## EPIC 4 — Business-code P0 (в main-repo)
7. Tier-0 writer (ordering строго обязателен):
   - signals_raw → trade_attempts → rpc_events → trades → microticks_1s
   - must-log IDs всегда заполнены: trace_id, trade_id, attempt_id, idempotency_token, config_hash, experiment_id
Acceptance:
- canary trace восстанавливается end-to-end по trace_id
- нет “потерянных” попыток/confirm событий (rpc_events есть для каждого arm)

4.1. Writer runtime ordering asserts (последняя защита от “тихого мусора”).
Требование:
- Перед записью `trades`: в ClickHouse уже должны существовать `signals_raw` и `trade_attempts`
  для этого `trace_id/trade_id` (или эквивалентные ключи по канону).
- Перед записью `microticks_1s`: в ClickHouse уже должна существовать запись `trades`
  и `entry_confirm_quality='ok'` (или эквивалентный признак по канону).
Режимы (любой P0-ок):
- Hard fail (exception) — предпочтительно для dev/CI.
- Soft fail — писать `forensics_events(kind='ordering_violation', severity='crit')` и **не писать**
  downstream записи (не создавать мусор).
Acceptance:
- Нарушение ordering не приводит к частичным/битым данным: либо падение, либо критическая форензика + stop.
- CI/canary гарантируют, что ordering соблюдается.

8. compute_exit_plan() = SQL parity:
   - compute_exit_plan выполняет queries/04_glue_select.sql
   - параметры берёт из golden_exit_engine.yaml (все placeholders Variant A)
   - результат записывается в trades: mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag
Acceptance:
- SDK-oracle (если добавили) совпадает с SQL-oracle 1:1
- изменения порогов делаются только в YAML, CI ловит drift
