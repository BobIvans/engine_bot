# AGENT_RULES

## Source of truth (non‑negotiable)
- **CANON ONLY**: `vendor/gmee_canon/**` (v23). Treat as read‑only.
- Never modify or copy CANON SQL/DDL/schemas/queries/registry into other paths.

## Strategy
- `strategy/docs/**` (including `strategy/docs/overlay/**`) is **docs-only**.
- Overlay is guidance; it is **not code** and **not canon**.

## Where code changes are allowed
- `integration/**`
- `scripts/**`
- `.github/workflows/**`

## Forbidden forever
- Any `.sql` / `.ddl` / `configs/queries.yaml` outside `vendor/gmee_canon/**`
- Any `schemas/` or `queries/` directories outside `vendor/gmee_canon/**`
- Any mention of `golden-engine-exit` in overlay docs
- Any “second canon”

## Definition of Done (must stay green)
- `./scripts/overlay_lint.sh`
- `./scripts/iteration1.sh`
- `./scripts/p1_smoke.sh`

## Engineering constraint
- `compute_exit_plan` is defined **only** by CANON SQL `queries/04_glue_select.sql`.
- Python wires params via CANON registry only (`vendor/gmee_canon/configs/queries.yaml`). No exit math in Python.
