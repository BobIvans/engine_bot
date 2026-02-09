# Definition of Done (DoD) для PR в этом репо

Этот чеклист прикладывается к каждому PR (копипаст в описание PR).

## Обязательное

- [ ] `bash scripts/overlay_lint.sh` зелёный
- [ ] `bash scripts/paper_runner_smoke.sh` зелёный
- [ ] `python3 -m integration.paper_pipeline --dry-run --summary-json ...` печатает **ровно одну** JSON‑строку в stdout
- [ ] Если PR меняет логику counts → обновлён `integration/fixtures/expected_counts.json`

## Если PR пишет в ClickHouse / меняет CH payload

- [ ] Прогон в write‑режиме выполнен с фиксированным `--run-trace-id`
- [ ] Ручная проверка по `strategy/docs/overlay/CLICKHOUSE_TRACE_VALIDATION.md` прошла (скрин/лог в PR)

## Если PR добавляет/меняет reject_reason

- [ ] `integration/reject_reasons.py` обновлён
- [ ] fixtures/expected_counts обновлены (если меняются числа)
