# Iteration-1 Tasks (CANON v23)

This file is meant to be copied into the “execution chat” as a checklist.

## Definition of Done (P0)

You are **done with Iteration-1** when these three commands are green on your machine:

1. `./scripts/smoke.sh`
2. `python integration/config_mapper.py`
3. `python integration/run_exit_plan.py --seed-golden`

No Solana live ingestion until the above is green.

---

## P0 Tasks (make it runnable end-to-end)

- [ ] **Docker ClickHouse up**: `docker compose up -d clickhouse` works and ClickHouse responds on `http://localhost:8123`.
- [ ] **Smoke single-path (CI == local)**: `./scripts/smoke.sh` runs **only** CANON gates (no sed, no alternate renderers).
- [ ] **Config mapper strict**: `integration/config_mapper.py`
  - [ ] reads `strategy/strategy.yaml`
  - [ ] writes `integration/runtime/golden_exit_engine.yaml`
  - [ ] validates **SQL04 params** match `vendor/gmee_canon/configs/queries.yaml → functions.glue_select.params` (missing/extra = hard fail)
- [ ] **One-shot demo (seeded)**: `integration/run_exit_plan.py --seed-golden`
  - [ ] applies CANON DDL
  - [ ] runs CANON seed (`vendor/gmee_canon/scripts/seed_golden_dataset.sql`)
  - [ ] runs CANON SQL04 (`vendor/gmee_canon/queries/04_glue_select.sql`) via named params
  - [ ] prints 6-column TSV row
  - [ ] writes write-back as `forensics_events(kind='exit_plan', details_json=...)`
- [ ] **CI wiring** (optional for local dev, required for team): CI calls `./scripts/smoke.sh` (not a workflow-specific alternate path).

---

## P1 Tasks (Solana copy-scalping: “successful wallets”)

Keep CANON untouched.

- [ ] **Allowlist loader**: CSV/YAML allowlist in `strategy/` (versioned) and an ingest helper that checks allowlist.
- [ ] **signals_raw writer**: minimal MUST fields from Data Contract Map; deterministic `signal_id`.
- [ ] **Cheap filters**: token/pool sanity filters at ingestion.
- [ ] **Mini-ML (score only)**:
  - [ ] offline/batch score pipeline
  - [ ] write `forensics_events(kind='wallet_score', details_json=...)`
  - [ ] entry rule uses score threshold (still no CANON change)
- [ ] **Microticks window**: ensure `microticks_1s` written only in `[buy_time, buy_time + microticks.window_sec]`.

---

## P2 Tasks (hygiene / hardening)

- [ ] Artifact hygiene: ensure vendor/ and overlay/ do not include `__pycache__`, `*.pyc`, `.pytest_cache`.
- [ ] Observability: log every run with a stable `trace_id` and include config hash in `forensics_events`.
- [ ] Entry executor hardening (slippage, retries, priority fees) — out of Iteration-1 scope.
