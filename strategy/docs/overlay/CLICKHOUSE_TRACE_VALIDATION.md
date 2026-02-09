# ClickHouse: ручная проверка по `run_trace_id` (P1 PR#2)

Цель: одним `run_trace_id` подтвердить, что:

- прогон зафиксирован в `forensics_events` (run_start / run_end / config_version)
- сигналы (если включены) попали в `signals_raw`
- все reject’ы видны как `forensics_events(kind='trade_reject')`

> Примечание: writers в репо пишут в базу ClickHouse `default` (см. `integration/ch_client.py`). Если вы используете другую БД — добавьте префикс `db.` в запросах.

## Мини-чеклист (3–4 SELECT’а)

Замените `{TRACE_ID}` на ваш `run_trace_id`.

### 1) Базовые события прогона (должны существовать)

```sql
SELECT
  kind,
  count() AS n,
  min(ts) AS first_ts,
  max(ts) AS last_ts
FROM default.forensics_events
WHERE trace_id = '{TRACE_ID}'
  AND kind IN ('run_start', 'run_end', 'config_version')
GROUP BY kind
ORDER BY kind;
```

Ожидаемо:
- `run_start` = 1
- `run_end` = 1
- `config_version` = 1 (или больше, если намеренно пишете несколько)

### 2) Сигналы, записанные в `signals_raw` (если режим пишет сигналы)

```sql
SELECT
  count() AS signals,
  min(ts) AS first_ts,
  max(ts) AS last_ts
FROM default.signals_raw
WHERE trace_id = '{TRACE_ID}';
```

### 3) Top причин reject’ов (normalizer/gates)

```sql
SELECT
  JSONExtractString(details_json, 'stage') AS stage,
  JSONExtractString(details_json, 'reason') AS reason,
  count() AS n
FROM default.forensics_events
WHERE trace_id = '{TRACE_ID}'
  AND kind = 'trade_reject'
GROUP BY stage, reason
ORDER BY n DESC, stage ASC, reason ASC
LIMIT 30;
```

### 4) Примеры reject’ов (чтобы увидеть payload)

```sql
SELECT
  ts,
  JSONExtractString(details_json, 'stage') AS stage,
  JSONExtractString(details_json, 'reason') AS reason,
  JSONExtractInt(details_json, 'lineno') AS lineno,
  JSONExtractString(details_json, 'wallet') AS wallet,
  JSONExtractString(details_json, 'mint') AS mint,
  JSONExtractString(details_json, 'tx_hash') AS tx_hash,
  details_json
FROM default.forensics_events
WHERE trace_id = '{TRACE_ID}'
  AND kind = 'trade_reject'
ORDER BY ts DESC
LIMIT 50;
```

## Один агрегирующий запрос “всё в одном”

Этот запрос даёт компактную сводку по одному trace.

```sql
SELECT
  '{TRACE_ID}' AS trace_id,
  countIf(fe.kind = 'run_start') AS run_start,
  countIf(fe.kind = 'run_end') AS run_end,
  countIf(fe.kind = 'config_version') AS config_version,
  countIf(fe.kind = 'trade_reject') AS trade_reject_events,
  countIf(JSONExtractString(fe.details_json, 'stage') = 'normalizer' AND fe.kind = 'trade_reject') AS rejects_normalizer,
  countIf(JSONExtractString(fe.details_json, 'stage') = 'gates' AND fe.kind = 'trade_reject') AS rejects_gates,
  anyHeavy(JSONExtractString(fe.payload_json, 'allowlist_version')) AS allowlist_version_any,
  (SELECT count() FROM default.signals_raw sr WHERE sr.trace_id = '{TRACE_ID}') AS signals_raw
FROM default.forensics_events fe
WHERE fe.trace_id = '{TRACE_ID}';
```

> Если `allowlist_version` хранится у вас в другом поле — уберите или поправьте строку `allowlist_version_any`.
