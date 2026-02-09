# Strategy Manifest — Solana Copy-Scalping (GMEE CANON v23) v0.6

**Goal (Iteration-1):** make an end-to-end runnable chain:

```bash
./scripts/smoke.sh
python integration/config_mapper.py
python integration/run_exit_plan.py --seed-golden
```

…where the **exit plan is computed only by CANON SQL04** (`vendor/gmee_canon/queries/04_glue_select.sql`) via **named params** (no string templating).

## Canon truth (single source of truth)

**CANON = `vendor/gmee_canon/**` (ZIP-2 v23)** — treated as read-only.

Source-of-truth files:
- Registry: `vendor/gmee_canon/configs/queries.yaml` → `functions.glue_select.params`
- Engine cfg schema + defaults: `vendor/gmee_canon/configs/golden_exit_engine.yaml`
- DDL: `vendor/gmee_canon/schemas/clickhouse.sql`
- Exit logic: `vendor/gmee_canon/queries/04_glue_select.sql`
- Oracle: `python vendor/gmee_canon/ci/oracle_glue_select_gate.py`

**Overlay/strategy docs never contain a second copy of CANON code.**

## P0 scope (Iteration-1)

### What we ship
- A strict config mapper:
  - input: `strategy/strategy.yaml` (human-friendly)
  - output: `integration/runtime/golden_exit_engine.yaml` (**CANON schema**)
  - strict check: params for SQL04 match registry exactly (extra/missing → hard fail)
- A runnable one-shot demo:
  - `python integration/run_exit_plan.py --seed-golden`
  - runs CANON SQL04 via named params
  - prints a 6-column TSV row
  - **writes back only as a forensics event** (`forensics_events`, kind=`exit_plan`)
- A single smoke path:
  - `./scripts/smoke.sh` is the only local/CI smoke entrypoint
  - smoke does: DDL → drift gate → explain gate → oracle gate

### What we explicitly do NOT ship in P0 (non-goals)
- Real on-chain execution quality (priority fees, MEV protection, Jito bundles, etc.)
- Online/streaming ML inside the engine
- Any “re-implementation” of exit math (thresholds/epsilon/aggr) outside SQL04
- Alternative SQL compilation paths (no `sed`, no regex templating)

## P0 invariants (anti-drift rules)

1) **Exit plan is computed only by CANON SQL04**.

2) **Single execution path**: CI and local runs execute the same gates and use the same runner.

3) **Registry-driven params**: `glue_select.params` is the only allowed param list.

4) **Chosen write-back pattern for P0**: write exit plans only to:
- `forensics_events(kind='exit_plan', details_json=...)`

No writes to planned_* columns in `trades` until Iteration-2.

## Signals (entry triggers) → `signals_raw`

**P0 entry trigger:** copy-trade signals from an allowlist of “successful” wallets.

Minimal `signals_raw` payload (see full MUST list in Data Contract Map):
- `trace_id` (UUID)
- `chain` = `solana`
- `env` = `canary|sim|paper|live`
- `source` = `wallet_copy`
- `signal_id` = stable deterministic id (e.g., sha256(wallet+mint+signal_time_ms))
- `signal_time` (DateTime64(3))
- `traced_wallet`
- `token_mint`, `pool_id`
- `confidence` (nullable)

## Selecting “successful wallets” (P0)

P0 is **not ML**.
- Wallet allowlist is loaded from `strategy/allowlist_wallets.csv|yaml`.
- Basic filters at ingestion are allowed (token/pool denylist, minimum liquidity, etc.).

## Mini-ML (P1, after P0 is green)

Mini-ML is allowed only as **a score + feature snapshot**, written as an event:
- `forensics_events(kind='wallet_score', details_json={model_version, features, score})`

Entry rule can use score thresholds, but CANON SQL/DDL/runner remain unchanged.

## Golden seed dataset (mandatory for Iteration-1 demo)

`run_exit_plan.py --seed-golden` must seed the dataset via:
- `vendor/gmee_canon/scripts/seed_golden_dataset.sql`

Reason: CANON tables (e.g., `trades`) often have many `NOT NULL` columns.
**Do not attempt to hand-insert a wide `trades` row** for the demo.

## Exit planning (GMEE)

- Load runtime engine cfg: `integration/runtime/golden_exit_engine.yaml` (CANON schema)
- Build params strictly from:
  - registry: `vendor/gmee_canon/configs/queries.yaml`
  - values: `integration/runtime/golden_exit_engine.yaml`
- Execute:
  - `vendor/gmee_canon/queries/04_glue_select.sql`
- Persist:
  - only `forensics_events(kind='exit_plan', details_json=...)` in P0



## Overlay docs

See `strategy/docs/OVERLAY_INDEX.md` and `strategy/docs/overlay/` for strategy pack guidance.
