# P0 Final Checklist (Variant A)

P0 считается реально закрытым только если **одновременно** выполняются условия:

1) **Variant A 100%**
- В `queries/04_glue_select.sql` нет захардкоженных порогов/epsilon/aggr/clamp, соответствующих значениям из YAML.
- Все значения приходят через `{param:Type}` placeholders.
- Проверяется: `python3 scripts/assert_no_drift.py`.

2) **Deterministic view**
- `wallet_profile_30d` anchored на детерминированном якоре (например `max(day)`), не `now()/today()`.

3) **Writer ordering + must-log IDs**
- Строгий ordering: `signals_raw → trade_attempts → rpc_events → trades → microticks_1s`.
- Must-log IDs всегда заполнены: `trace_id, trade_id, attempt_id, idempotency_token, config_hash, experiment_id`.

4) **Oracle gate ловит drift**
- Tiny seed dataset (`scripts/seed_golden_dataset.sql`) → `queries/04_glue_select.sql` → стабильный TSV → сравнение 1:1.
- Gate: `python3 ci/oracle_glue_select_gate.py` (или `pytest -k oracle_glue_select`).

Если хотя бы одно не выполняется — Codex начнёт “угадывать” и появятся “симы врут”.
