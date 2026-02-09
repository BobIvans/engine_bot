# Sprint plan (overlay)

This repo uses **rails** (schema + deterministic smokes) so strategy work stays verifiable.

The authoritative task registry is `strategy/docs/overlay/SPRINTS.md`.
This file is a short **"what's next"** view that is safe for an agent to follow.

## Rails that must stay green

- Lint: `bash scripts/overlay_lint.sh`
- Deterministic smoke: `bash scripts/paper_runner_smoke.sh`
- Dataset smoke: `bash scripts/features_smoke.sh`
- Config smokes:
  - `bash scripts/config_smoke.sh`
  - `bash scripts/config_negative_smoke.sh`

## Current state

Landmarks already present in this repo:

- Sprint-1 (data layers → dataset loop): token snapshots, wallet profiles, deterministic features + labels, exporter coverage
- PR labels SoT + lint integrated into overlay_lint
- Variant A:
  - PR-4A.1 config validator + config_smoke
  - PR-4A.2 negative fixtures + config_negative_smoke

## Next up

### PR-4A.3: Mode registry + metrics-by-mode

Goal: normalize *where modes come from* and emit per-mode counters in `paper_pipeline --summary-json` without breaking the **1 JSON line stdout** contract.

Implementation task (agent-ready): `strategy/docs/overlay/PR_MODES.md`.

DoD:

- `bash scripts/modes_smoke.sh`
- `bash scripts/overlay_lint.sh`
- `bash scripts/paper_runner_smoke.sh`
- `bash scripts/features_smoke.sh`

## Later

Sprint-2 (Risk → sim → +EV) remains the next major layer once Variant A mode observability is in place.
