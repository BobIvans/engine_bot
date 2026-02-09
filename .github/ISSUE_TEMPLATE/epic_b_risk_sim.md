---
name: Epic B — Risk + execution simulator
about: Risk engine + TTL/slippage/latency simulator (paper/sim first)
title: "[EPIC-B] Risk + execution simulator (paper/sim first)"
labels: ["epic", "risk", "sim"]
---

## Outcome
Signals become *actionable* (sizing + simulated fills) without touching live keys.

## Scope
- Risk engine pure functions (fractional Kelly + limits + kill-switch)
- Execution simulator (TTL/slippage/latency, partial/zero fills)
- Metrics/counters per stage

## DoD
- `./scripts/smoke.sh` green
- `paper_pipeline` supports a sim path producing fill-rate/slippage/ttl-expired counters
- Forensics events show risk_filtered vs gate rejects distinctly
