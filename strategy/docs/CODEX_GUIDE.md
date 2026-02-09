# Codex guide: two ZIP workflow (engine + strategy overlay)

## What are the two ZIPs?

1) **Engine repo ZIP** (this repository): contains runnable docker/scripts/integration and the **CANON** under:
- `vendor/gmee_canon/**` (read-only)

2) **Strategy overlay ZIP**: contains only **docs / PR-plan / manifests / guidance**.
It must **not** be treated as a source of truth for the CANON code or SQL.

## Golden rule

- **CANON = `vendor/gmee_canon/**`** and it is **read-only**.
- Allowed to edit only:
  - `integration/**`
  - `strategy/**`
  - `scripts/**`
  - `.github/workflows/**`

## P0 goal (Iteration-1)

Make this pass end-to-end:

```bash
bash ./scripts/iteration1.sh
```

It runs:
1) `./scripts/smoke.sh` (vendor local smoke: DDL + drift + canary + oracle)
2) `python3 -m integration.config_mapper` (strategy -> runtime cfg)
3) `python3 -m integration.run_exit_plan --seed-golden` (SQL04 run)

If it fails, share the **full log** of `./scripts/iteration1.sh` as one block.

## P1 helpers

These scripts are stable CLI entrypoints, and can also be imported via `integration/helpers.py`:

- `python3 -m integration.allowlist_loader --path strategy/wallet_allowlist.yaml`
- `python3 -m integration.write_signal ...`
- `python3 -m integration.write_wallet_score ...`

Both writers support `--dry-run` to validate inputs without touching ClickHouse.
