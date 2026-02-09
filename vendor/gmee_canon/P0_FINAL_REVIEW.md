# P0 Final Review — Variant A closure checklist

This file is a **human-facing** checklist for the P0 closure rules.

## What must be true (P0 closed)

- Variant A enforced: `queries/04_glue_select.sql` has **no hardcoded thresholds/epsilon/aggr/clamp** (all via `{param:Type}` placeholders).
- `wallet_profile_30d` is deterministic: anchored on `max(day)` (or another deterministic anchor), **not** on `now()`.
- Writer ordering is cemented & testable:
  `signals_raw → trade_attempts → rpc_events → trades → microticks_1s`
- Must-log IDs always present:
  `trace_id, trade_id, attempt_id, idempotency_token, config_hash, experiment_id, env, chain`
- Oracle gate exists and is strict:
  seed tiny dataset → run `04_glue_select` → stable TSV → exact compare.

## Repo status (this skeleton)

- Variant A placeholders: OK
- Deterministic profile view: OK (anchored on `max(day)`)
- Canary checks are assertive: OK (uses `throwIf`)
- Oracle gate: OK (exact TSV compare in CI + python test)
