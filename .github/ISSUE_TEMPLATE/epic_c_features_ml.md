---
name: Epic C — Features + ML interfaces
about: Feature contract + model interface (model-off first)
title: "[EPIC-C] Features + ML interfaces (model-off first)"
labels: ["epic", "ml", "features"]
---

## Outcome
A stable feature contract and model interface so ML can be added later without rewiring.

## Scope
- Feature builder contract + fixture of expected keys
- Model interface (model-off deterministic path)
- Backtest harness wiring (replay → sim → metrics)

## DoD
- `./scripts/smoke.sh` green
- Feature smoke checks key stability
- Model can be enabled/disabled via config without code changes
