---
name: Epic A — Data-track contracts
about: Token snapshots, wallet profiles, import tools (fixtures first)
title: "[EPIC-A] Data-track contracts (fixtures first)"
labels: ["epic", "data-track"]
---

## Outcome
Contracts + fixtures exist so strategy logic can be tested deterministically offline.

## Scope
- Token snapshot store + fixture
- Wallet profile store + fixture
- Import tools (CSV/JSON → parquet) for replay

## DoD
- `./scripts/smoke.sh` green
- Paper runner can replay fixtures and produce stable summary/reject reasons
- Missing snapshot/profile has deterministic reject reason
