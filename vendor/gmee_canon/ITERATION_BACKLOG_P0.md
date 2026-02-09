# Iteration Backlog — P0-safe (Variant A)

This backlog is **P0-safe**: it improves determinism, debuggability, and data fidelity **without** changing canon (SQL/YAML/DDL/docs/scripts) and without implementing P1/P2 features.

## A) Data-fidelity & writer hardening
1) **Monotonic time assertion coverage**
   - Expand writer checks to cover all Tier-0 timestamps you already log.
   - Emit `forensics_events(kind='time_skew', severity='crit')` with a structured payload: `{field_a, field_b, delta_ms}`.
   - Acceptance: synthetic test triggers the event on forced skew; normal path produces none.

2) **Confirm quality propagation everywhere**
   - Ensure `confirm_quality` is validated and threaded through `rpc_events` and (where applicable) `trades` snapshots.
   - Emit forensics for `suspect` and `reorged`.
   - Acceptance: any invalid value raises; suspect/reorged always creates forensics.

3) **Idempotency guarantees (stronger)**
   - Current implementation is best-effort (pre-check + retry). Add an optional “dedupe readback” mode:
     - After insert, read back row count by `idempotency_token` to ensure exactly one row.
   - Acceptance: retry storm does not create duplicates in canary.

## B) Deterministic trace reconstruction (debug-grade data capture)
4) **Trace dump utility**
   - Add `gmee/trace_dump.py`:
     - `dump_trace(trace_id, out_path)` pulls `signals_raw`, `trade_attempts`, `rpc_events`, `trades`, `microticks_1s`, `forensics_events`.
     - Writes a deterministic JSONL with stable ordering.
   - Acceptance: running twice on same DB produces byte-identical output.

5) **Replay utility**
   - Add `gmee/replay.py` that replays a dumped JSONL back into an empty ClickHouse.
   - Acceptance: dump → replay → oracle gates produce identical results.

## C) CI & reproducibility upgrades (still P0)
6) **One-command local CI harness**
   - Add a `tools/local_ci.sh` (NOT under `scripts/`) that runs:
     - DDL apply → EXPLAIN → drift gate → canary gate → oracle gate.
   - Acceptance: developers can reproduce CI failures locally.

7) **Contract snapshot pinning**
   - Add `ci/contract_snapshot.json` (generated) containing canonical hashes.
   - Add a CI step that fails if canonical hashes changed without explicit approval.
   - Acceptance: drift is blocked even if drift-check scripts are bypassed.

## D) Higher-resolution data capture (P0-compliant)
8) **RPC event payload capture**
   - Without changing schema, encode extra per-arm telemetry into existing free-form/text columns (if present) or into `forensics_events.payload`.
   - Keep it compact and deterministic.
   - Acceptance: payload is consistent and does not break canary.

9) **Microticks window integrity**
   - Add a post-write check: microticks exist only in post-entry window and are linked to `trade_id`.
   - Acceptance: test fails if a microtick precedes entry.

---

### Recommended next iteration order
1) Trace dump utility → 2) Replay utility → 3) One-command local harness.

This gives you a “black box flight recorder” for every canary/oracle failure.
