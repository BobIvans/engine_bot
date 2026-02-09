# RUNBOOK (P0) — GMEE

This runbook covers P0 operational checks only: canary, QA, anti-drift, and promotion gates.
No tuning (P1/P2) here.

---

## Daily checks (P0)

Run these daily (or on every deploy):

1) Anti-drift gate:
- `scripts/assert_no_drift.py` passes

2) Canary E2E trace:
- seed: `scripts/canary_golden_trace.sql`
- checks: `scripts/canary_checks.sql`

3) Data QA (minimal):
- monotonicity: `signal_time <= entry_local_send_time <= entry_first_confirm_time`
- Tier-0 null rates (core trade fields)
- forensics spikes (by kind/severity)

4) Budget/quota:
- `provider_usage_daily` within budget; throttle if exceeded

---

## Canary / Testnet philosophy (P0)

- Canary is not “profit test”.
- It is a **contract test**: storage + query compilation + writer ordering + no forensics anomalies.

---

## Incident playbook (P0)

### confirm_quality=suspect spikes

Action:
- mark affected RPC arms degraded (cooldown)
- pause learning updates (ε/controller) if implemented

Record:
- `forensics_events(kind='suspect_confirm')`

### reorg event

Action:
- mark trade `failure_mode='reorg'`, `confirm_quality='reorged'`
- exclude from aggregates and ε updates

Record:
- `forensics_events(kind='reorg')`

### schema drift / query mismatch

Action:
- CI must catch; rollback the change

Record:
- `forensics_events(kind='schema_mismatch')` if discovered in prod

### budget blow-up

Action:
- set `provider_usage_daily.throttled=1` for non-critical collectors
- reduce microticks window / disable tier1_capture

Record:
- controller_state snapshot with reason + approved_by + ticket_ref

---

## Promotion gates (P0)

Before any move from canary → paper → live:
- CI gates green
- Canary checks green
- Promotions must be written to Postgres `promotions_audit`:
  who/when/decision/config_hash/signed_snapshot_uri

---

## Quick commands (local)

One command:
```bash
bash scripts/local_smoke.sh
```

Manual:

Apply DDL:
```bash
docker exec -i clickhouse clickhouse-client --multiquery < schemas/clickhouse.sql
```

Run canary:
```bash
docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_golden_trace.sql
docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_checks.sql
```

Oracle test:
```bash
bash scripts/oracle_test.sh
```
