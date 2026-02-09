> **Overlay-only**: This document is guidance. **CANON is `vendor/gmee_canon/**` (read-only)**.  
> Do not copy overlay code/queries/DDL into CANON. Implement changes only in `integration/**` and `strategy/**`.

# GMEE Strategy Overlay Manifest

This ZIP contains two logical parts:

1) **GMEE Canon Engine (P0 v0.4, Variant A)** — under:
   - `gmee_strategy_pack_v17_canonical/vendor/gmee_canon/`
   This is the *single source of truth* for P0: docs/configs/schemas/queries/scripts.

2) **Strategy Overlay** — this folder:
   - `gmee_strategy_pack_v17_canonical/strategy_overlay/`
   This contains *instructions and snippets* to integrate the canon into a main repository.

## Priority & Rules

- **Canon (`vendor/gmee_canon/`) is read-only** once vendored into a main repo.
- Any integration code MUST live outside the canon (e.g. `integration/gmee/*`).
- If any file exists both in overlay and canon, **canon wins**.

## Recommended layout in a main repo

- `vendor/gmee_canon/`  ← copy `vendor/gmee_canon/` here (read-only)
- `strategy/gmee_overlay/` ← copy this overlay folder here
- `integration/gmee/` ← new integration code (runner/writer wiring/CI glue)

See `PR_PLAN.md` for the minimal PR ordering.
